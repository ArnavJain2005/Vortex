"""Output contract: one finite pose per input data row, same order, exact timestamps, unit quaternion."""

import pytest

from vortex import check_output

HEADER = "#timestamp [ns],w_RS_S_x,w_RS_S_y,w_RS_S_z,a_RS_S_x,a_RS_S_y,a_RS_S_z"
IMU = (HEADER + "\n"
       "1403636579758555392,0,0,0,9.8,0,0\n"
       "\n"
       "1403636579763555584,nan,0,0,9.8,0,0\n"
       "1403636579763555584,0,0\n"                  # duplicate timestamp, short row
       "5,0,0,0,9.8,0,0\n")
GOOD = ("1403636579.758555392 0.000000 0.000000 0.000000 0.0000000 0.0000000 0.0000000 1.0000000\n"
        "1403636579.763555584 0.1 0.2 0.3 0.5 0.5 0.5 0.5\n"
        "1403636579.763555584 -1e-3 0 0 0 0 0.7071068 0.7071068\n"
        "0.000000005 0 0 0 0 0 0 1\n")


def _files(tmp_path, imu=IMU, out=GOOD, out_newline="\n"):
    a, b = tmp_path / "data.csv", tmp_path / "est.txt"
    a.write_text(imu)
    b.write_bytes(out.replace("\n", out_newline).encode())
    return a, b


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_good_output_passes(tmp_path, nl):
    r = check_output.check(*_files(tmp_path, out_newline=nl))
    assert r["ok"], r["errors"]
    assert r["input_rows"] == 4 and r["output_rows"] == 4


def _broken(tmp_path, out):
    r = check_output.check(*_files(tmp_path, out=out))
    assert not r["ok"]
    return " ".join(r["errors"])


def test_missing_row_fails(tmp_path):
    assert "row count" in _broken(tmp_path, "".join(GOOD.splitlines(True)[:3]))


def test_extra_row_fails(tmp_path):
    assert "row count" in _broken(tmp_path, GOOD + GOOD.splitlines(True)[0])


def test_nan_fails(tmp_path):
    assert "finite" in _broken(tmp_path, GOOD.replace("0.1 0.2 0.3", "nan 0.2 0.3"))


def test_inf_fails(tmp_path):
    assert "finite" in _broken(tmp_path, GOOD.replace("0.1 0.2 0.3", "inf 0.2 0.3"))


def test_wrong_or_rounded_timestamp_fails(tmp_path):
    assert "timestamp" in _broken(tmp_path, GOOD.replace("1403636579.758555392", "1403636579.758555"))


def test_swapped_rows_fail(tmp_path):
    lines = GOOD.splitlines(True)
    assert "timestamp" in _broken(tmp_path, lines[0] + lines[3] + lines[2] + lines[1])


def test_non_unit_quaternion_fails(tmp_path):
    assert "unit" in _broken(tmp_path, GOOD.replace("0.5 0.5 0.5 0.5", "0.5 0.5 0.5 0.6"))


def test_wrong_field_count_fails(tmp_path):
    assert "8 fields" in _broken(tmp_path, GOOD.replace(" 0.5 0.5 0.5 0.5", " 0.5 0.5 0.5"))


def test_comma_separator_fails(tmp_path):
    assert "8 fields" in _broken(tmp_path, GOOD.replace("0.1 0.2 0.3", "0.1,0.2,0.3"))


def test_header_line_in_output_fails(tmp_path):
    assert "header" in _broken(tmp_path, "# timestamp tx ty tz qx qy qz qw\n" + GOOD)


def test_cli_exit_codes(tmp_path, capsys):
    a, b = _files(tmp_path)
    assert check_output.main([str(a), str(b)]) == 0
    b.write_text("garbage\n")
    assert check_output.main([str(a), str(b)]) == 1
    assert "FAIL" in capsys.readouterr().out

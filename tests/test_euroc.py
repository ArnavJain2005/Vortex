"""EuRoC / TUM-VI loader: every data row is kept, in file order, with its original timestamp text."""

import math

import numpy as np
import pytest

from vortex.data import euroc

HEADER = ("#timestamp [ns],w_RS_S_x [rad s^-1],w_RS_S_y [rad s^-1],w_RS_S_z [rad s^-1],"
          "a_RS_S_x [m s^-2],a_RS_S_y [m s^-2],a_RS_S_z [m s^-2]")


# ---------- timestamp text ----------

@pytest.mark.parametrize("field, expected", [
    ("1403636579758555392", "1403636579.758555392"),
    ("1234567890", "1.234567890"),
    ("123456789", "0.123456789"),
    ("5", "0.000000005"),
    ("0", "0.000000000"),
    ("  1403636579758555392 ", "1403636579.758555392"),
    ("1403636579758555392\r\n", "1403636579.758555392"),
    ("", None),
    ("nan", None),
    ("-5", None),
    ("1.4e18", None),
])
def test_seconds_text_is_exact_string_shift(field, expected):
    assert euroc.seconds_text(field) == expected


def test_seconds_text_bytes_input():
    assert euroc.seconds_text(b"1403636579758555392") == "1403636579.758555392"


# ---------- row definition ----------

@pytest.mark.parametrize("line, is_row", [
    ("1,2,3,4,5,6,7\n", True),
    ("1,2,3\n", True),          # short rows are still rows
    ("1,nan,,,,,\n", True),
    ("#timestamp...\n", False),
    ("\n", False),
    ("   \r\n", False),
    ("", False),
])
def test_is_data_line(line, is_row):
    assert euroc.is_data_line(line) is is_row


# ---------- reader ----------

def _write(tmp_path, body, newline="\n"):
    p = tmp_path / "data.csv"
    p.write_bytes((HEADER + "\n" + body).replace("\n", newline).encode("ascii"))
    return p


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_reader_keeps_every_row_in_order(tmp_path, newline):
    body = ("1000000000,0.1,0.2,0.3,9.8,0.0,0.1\n"
            "\n"                                        # blank: not a row
            "1005000000,nan,0.2,0.3,9.8,0.0,0.1\n"      # NaN value
            "1010000000,,,,,,\n"                        # empty fields (pandas na_rep='')
            "1010000000,0.1,0.2,0.3,9.8,0.0,0.1\n"      # duplicate timestamp
            "1007500000,0.1,0.2,0.3,9.8,0.0,0.1\n"      # out of order
            "1020000000,0.1,0.2\n"                      # short row
            "1025000000,0.4,0.5,0.6,9.7,0.1,0.2")       # no final newline
    raw = euroc.read_imu_csv(_write(tmp_path, body, newline))
    assert len(raw) == 7
    assert raw.t_text == ["1000000000", "1005000000", "1010000000", "1010000000", "1007500000",
                          "1020000000", "1025000000"]
    assert raw.t_ns.tolist() == [1000000000, 1005000000, 1010000000, 1010000000, 1007500000,
                                 1020000000, 1025000000]
    assert raw.valid.tolist() == [True, False, False, True, True, False, True]
    assert math.isnan(raw.gyro[1, 0]) and raw.gyro[1, 1] == 0.2
    assert np.all(np.isnan(raw.gyro[2])) and np.all(np.isnan(raw.accel[2]))
    assert raw.gyro[5].tolist()[:2] == [0.1, 0.2] and math.isnan(raw.gyro[5, 2])
    assert np.all(np.isnan(raw.accel[5]))
    assert raw.accel[6].tolist() == [9.7, 0.1, 0.2]
    assert raw.header.startswith("#timestamp")


def test_reader_bad_timestamp_kept_with_flag(tmp_path):
    raw = euroc.read_imu_csv(_write(tmp_path, "abc,0.1,0.2,0.3,9.8,0.0,0.1\n"))
    assert len(raw) == 1 and raw.t_ns[0] == -1 and not raw.valid[0]


def test_write_roundtrip_is_exact(tmp_path):
    body = "1403636579758555392,-0.099134701513277898,0.14730578886832778,0.02722713633111154," \
           "8.1476917083333333,-0.37592158333333331,-2.4026292499999999\n"
    raw = euroc.read_imu_csv(_write(tmp_path, body))
    out = tmp_path / "out.csv"
    euroc.write_imu_csv(raw, out)
    back = euroc.read_imu_csv(out)
    assert back.t_text == raw.t_text
    assert np.array_equal(back.gyro, raw.gyro) and np.array_equal(back.accel, raw.accel)


@pytest.mark.parametrize("nan_text", ["nan", ""])
def test_write_nan_text_reads_back_as_nan(tmp_path, nan_text):
    raw = euroc.read_imu_csv(_write(tmp_path, "1000000000,nan,nan,nan,nan,nan,nan\n"))
    out = tmp_path / "out.csv"
    euroc.write_imu_csv(raw, out, nan_text=nan_text)
    assert out.read_text().splitlines()[1] == "1000000000" + ("," + nan_text) * 6
    back = euroc.read_imu_csv(out)
    assert len(back) == 1 and np.all(np.isnan(back.gyro))


def test_to_imu_data_requires_clean_rows(tmp_path):
    good = euroc.read_imu_csv(_write(tmp_path, "1000000000,0.1,0.2,0.3,9.8,0,0.1\n"
                                                "1005000000,0.1,0.2,0.3,9.8,0,0.1\n"))
    imu = good.to_imu_data()
    assert np.allclose(imu.t, [1.0, 1.005]) and imu.accel.shape == (2, 3)
    bad = euroc.read_imu_csv(_write(tmp_path, "1000000000,nan,0.2,0.3,9.8,0,0.1\n"))
    with pytest.raises(ValueError):
        bad.to_imu_data()


# ---------- layout and ground truth (scoring only) ----------

def _make_layout(tmp_path, gt_folder, gt_rows):
    mav0 = tmp_path / "MH_01_easy" / "mav0"
    (mav0 / "imu0").mkdir(parents=True)
    (mav0 / "imu0" / "data.csv").write_text(HEADER + "\n1000000000,0,0,0,9.8,0,0\n")
    (mav0 / gt_folder).mkdir()
    (mav0 / gt_folder / "data.csv").write_text("#timestamp,...\n" + "\n".join(gt_rows) + "\n")
    return tmp_path / "MH_01_easy"


def test_find_paths_and_euroc_ground_truth(tmp_path):
    # EuRoC: t, p(3), q(w,x,y,z), v(3), bw(3), ba(3)
    rows = ["1000000000,1,2,3,1,0,0,0,0,0,0,0,0,0,0,0,0",
            "1005000000,1.1,2,3,0.7071067811865476,0,0,0.7071067811865476,0,0,0,0,0,0,0,0,0"]
    seq = _make_layout(tmp_path, "state_groundtruth_estimate0", rows)
    assert euroc.imu_path(seq).name == "data.csv"
    assert euroc.imu_path(seq / "mav0" / "imu0" / "data.csv") == seq / "mav0" / "imu0" / "data.csv"
    gt = euroc.load_ground_truth(seq)
    assert np.allclose(gt.t, [1.0, 1.005])
    assert np.allclose(gt.p[1], [1.1, 2, 3])
    assert np.allclose(gt.q[1], [0.7071067811865476, 0, 0, 0.7071067811865476])   # (w, x, y, z)


def test_tumvi_mocap_ground_truth(tmp_path):
    rows = ["1000000000,1,2,3,1,0,0,0", "1005000000,1,2,4,1,0,0,0"]
    seq = _make_layout(tmp_path, "mocap0", rows)
    gt = euroc.load_ground_truth(seq)
    assert len(gt) == 2 and gt.p[1, 2] == 4


def test_missing_layout_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        euroc.imu_path(tmp_path)

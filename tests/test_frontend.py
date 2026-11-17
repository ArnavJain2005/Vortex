"""Input front end (Step 2): column order, timestamp unit and accelerometer unit from the data, in the
reference (vortex/core/frontend.py) and its copy in pathfinder.py. All inputs SYNTHETIC."""

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pytest

from vortex.core import frontend as fe
from vortex.core import witness as wx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_core_equivalence import _compare  # noqa: E402
from test_strapdown import _move_rest_move  # noqa: E402

G = fe.G_SCRIPT
ACC_FIRST_HEADER = ("#timestamp [ns],a_RS_S_x [m s^-2],a_RS_S_y [m s^-2],a_RS_S_z [m s^-2],"
                    "w_RS_S_x [rad s^-1],w_RS_S_y [rad s^-1],w_RS_S_z [rad s^-1]")


def _load_pf():
    spec = importlib.util.spec_from_file_location("vortex_pf_frontend", ROOT / "pathfinder.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pf = _load_pf()


@pytest.fixture(scope="module")
def rows():
    r, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.002, acc_noise=0.02, seed=3)
    return r


def _write(path, rows, order="gyro_first", unit="ns", g=False, header=True, hdr_text=None):
    """rows: (t_ns, (gx, gy, gz, ax, ay, az)). Writes the layout asked for."""
    lines = []
    if header:
        lines.append(hdr_text or (fe.CANON_HEADER if order == "gyro_first" else ACC_FIRST_HEADER))
    for t, v in rows:
        gy, ac = list(v[:3]), list(v[3:])
        if g:
            ac = [x / G for x in ac]
        vals = gy + ac if order == "gyro_first" else ac + gy
        s = str(t)
        if unit == "us":
            s = s[:-3] + "." + s[-3:]
        elif unit == "ms":
            s = s[:-6] + "." + s[-6:]
        elif unit == "s":
            s = s[:-9] + "." + s[-9:]
        elif unit == "ms_int":
            s = str(t // 1_000_000)
        lines.append(s + "," + ",".join(repr(float(x)) for x in vals))
    Path(path).write_text("\n".join(lines) + "\n")
    return str(path)


def _run_pf(src, dst):
    n = pf.run(str(src), str(dst))
    return n, Path(dst).read_bytes()


def test_canonical_euroc_is_left_alone(tmp_path, rows):
    src = _write(tmp_path / "a.csv", rows)
    lay = fe.detect(src)
    assert lay["canonical"] and lay["order_from"] == "data" and lay["header_order"] == "gyro_first"
    n, out = _run_pf(src, tmp_path / "o.txt")
    assert pf.LAST["frontend"]["canonical"] and not os.path.exists(str(tmp_path / "o.txt") + ".vortex_in.csv")
    pf.FRONT_ON = False
    try:
        assert _run_pf(src, tmp_path / "o2.txt") == (n, out)        # front end is a no-op here
    finally:
        pf.FRONT_ON = True


@pytest.mark.parametrize("header", [True, False])
def test_accel_first_gives_the_same_bytes(tmp_path, rows, header):
    ref = _run_pf(_write(tmp_path / "g.csv", rows), tmp_path / "g.txt")
    src = _write(tmp_path / "a.csv", rows, order="accel_first", header=header)
    lay = fe.detect(src)
    assert lay["order"] == "accel_first" and lay["order_from"] == "data" and not lay["canonical"]
    assert _run_pf(src, tmp_path / "a.txt") == ref
    assert not os.path.exists(str(tmp_path / "a.txt") + ".vortex_in.csv")          # temp file removed


@pytest.mark.parametrize("unit", ["us", "ms", "s"])
def test_decimal_timestamp_units_give_the_same_bytes(tmp_path, rows, unit):
    ref = _run_pf(_write(tmp_path / "g.csv", rows), tmp_path / "g.txt")
    src = _write(tmp_path / "u.csv", rows, unit=unit)
    assert fe.detect(src)["ts_unit"] == unit
    assert _run_pf(src, tmp_path / "u.txt") == ref


def test_integer_ms_timestamps_are_seconds_exactly(tmp_path, rows):
    src = _write(tmp_path / "m.csv", rows, unit="ms_int")
    assert fe.detect(src)["ts_unit"] == "ms"
    pf.run(src, str(tmp_path / "m.txt"))
    got = [l.split()[0] for l in (tmp_path / "m.txt").read_text().splitlines()]
    want = ["%d.%09d" % divmod((t // 1_000_000) * 1_000_000, 10 ** 9) for t, _ in rows]
    assert got == want


def test_accel_in_g_is_scaled(tmp_path, rows):
    ref = np.array([[float(x) for x in l.split()[1:]] for l in
                    _run_pf(_write(tmp_path / "g.csv", rows), tmp_path / "g.txt")[1].decode().splitlines()])
    src = _write(tmp_path / "gg.csv", rows, order="accel_first", g=True)
    lay = fe.detect(src)
    assert lay["accel_unit"] == "g" and lay["order"] == "accel_first"
    _, out = _run_pf(src, tmp_path / "gg.txt")
    got = np.array([[float(x) for x in l.split()[1:]] for l in out.decode().splitlines()])
    assert got.shape == ref.shape and np.abs(got - ref).max() < 1e-4   # x / G * G is not always exact


@pytest.mark.parametrize("case", ["accel_first", "g", "s"])
def test_reference_and_pathfinder_agree(tmp_path, rows, monkeypatch, case):
    kw = {"accel_first": {"order": "accel_first"}, "g": {"order": "accel_first", "g": True},
          "s": {"unit": "s"}}[case]
    src = _write(tmp_path / "x.csv", rows, **kw)
    _compare(src, tmp_path, monkeypatch, reference=wx.estimate_file)


def test_ambiguous_data_falls_back_to_the_header(tmp_path):
    # both triples look like an accelerometer: the data cannot decide
    rows = [(10 ** 18 + 5_000_000 * i, (0.0, 0.0, 9.81 + 0.01 * (i % 7), 0.0, 9.81 - 0.01 * (i % 5), 0.0))
            for i in range(500)]
    src = _write(tmp_path / "h.csv", rows, order="accel_first")
    lay = fe.detect(src)
    assert lay["order_from"] == "header" and lay["order"] == "accel_first"
    src = _write(tmp_path / "n.csv", rows, header=False)
    lay = fe.detect(src)
    assert lay["order_from"] == "default" and lay["order"] == "gyro_first"


def test_pathfinder_detect_matches_the_reference(tmp_path, rows):
    for kw in ({}, {"order": "accel_first"}, {"order": "accel_first", "g": True, "unit": "ms"},
               {"header": False, "unit": "us"}):
        src = _write(tmp_path / "d.csv", rows, **kw)
        assert pf._fe_detect(src) == fe.detect(src)


def test_deg_per_s_gyro_is_flagged_not_converted(tmp_path, rows):
    deg = [(t, tuple(x * 57.29577951308232 for x in v[:3]) + tuple(v[3:])) for t, v in rows]
    deg = [(t, (v[0] + 200.0, v[1], v[2]) + v[3:]) for t, v in deg]     # a large rate, as deg/s can be
    lay = fe.detect(_write(tmp_path / "deg.csv", deg))
    assert lay["gyro_suspect"] and lay["order"] == "gyro_first"


def test_ns_text():
    assert fe.ns_text(b"1403636579.758555392", 9) == b"1403636579758555392"
    assert fe.ns_text(b"12.5", 9) == b"12500000000"
    assert fe.ns_text(b"1403636579758", 6) == b"1403636579758000000"
    assert fe.ns_text(b"0.000000001", 9) == b"1"
    assert fe.ns_text(b"1.2345678912", 9) == b"1234567891"                # beyond ns: truncated
    assert fe.ns_text(b"1403636579758555392", 0) == b"1403636579758555392"
    assert fe.ns_text(b"1403636579758555392.0", 0) == b"1403636579758555392"
    assert fe.ns_text(b"nan", 9) == b"nan" and fe.ns_text(b"-1.5", 9) == b"-1.5"

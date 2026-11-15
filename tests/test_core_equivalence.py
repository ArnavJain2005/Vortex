"""main.py (optimised) and vortex/core/strapdown.py (reference) give the same poses.

Criterion (from the plan): position difference < 1e-6 m and quaternion difference < 1e-7 on every
row. main.py is run with a full-precision output format so rounding of the submission format
(6 / 7 decimals) does not hide or cause differences. All inputs are SYNTHETIC."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from vortex import degrade
from vortex.core import strapdown as sd
from vortex.data import euroc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import synth_euroc  # noqa: E402
from test_main import MESSY  # noqa: E402
from test_strapdown import _move_rest_move, _moving, _static_rows  # noqa: E402

FULL = b"%s.%s %.17g %.17g %.17g %.17g %.17g %.17g %.17g\n"


def _load_main():
    spec = importlib.util.spec_from_file_location("vortex_main_equiv", ROOT / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


main = _load_main()


def _compare(src, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FMT", FULL)
    dst = tmp_path / "est.txt"
    n = main.run(str(src), str(dst))
    got = np.array([[float(x) for x in line.split()[1:]] for line in dst.read_text().splitlines()])
    ref = np.array(sd.estimate_file(src))                 # (px, py, pz, qw, qx, qy, qz)
    assert n == len(ref) == len(got)
    if n == 0:
        return 0.0, 0.0
    dp = np.abs(got[:, :3] - ref[:, :3]).max()
    dq = np.abs(got[:, [6, 3, 4, 5]] - ref[:, 3:]).max()   # main writes qx qy qz qw
    assert dp < 1e-6 and dq < 1e-7, (dp, dq)
    return dp, dq


def _write_rows(path, rows):
    with open(path, "w", newline="\n") as f:
        f.write(euroc.HEADER + "\n")
        for t, v in rows:
            f.write("%s,%s\n" % ("bad" if t is None else t, ",".join(repr(float(x)) for x in v)))
    return path


def test_parameters_identical():
    for name in ("INIT_S", "INIT_MAX_ROWS", "STILL_GYRO_STD", "STILL_ACC_STD", "G_DEFAULT", "MAX_DT",
                 "MAX_JUMP_S", "MAX_SUMSQ", "CAL_HORIZON_S", "BLOCK_S", "BLOCK_MIN_ROWS", "MIN_STILL_S",
                 "STUCK_STD", "ACC_NORM_MIN", "ACC_NORM_MAX", "STEADY_GYRO", "STEADY_ACC", "TRIM_S",
                 "PRE_MAX_ROWS"):
        assert getattr(main, name) == getattr(sd, name), name


def test_messy_file(tmp_path, monkeypatch):
    src = tmp_path / "imu.csv"
    src.write_bytes(MESSY)
    _compare(src, tmp_path, monkeypatch)


def test_random_synthetic_file(tmp_path, monkeypatch):
    src = synth_euroc.write(tmp_path / "imu.csv", rows=6000, seed=0)
    _compare(src, tmp_path, monkeypatch)


@pytest.mark.parametrize("mode, nan_text", [("nan", ""), ("missing", "nan")])
def test_degraded_synthetic_file(tmp_path, monkeypatch, mode, nan_text):
    clean = synth_euroc.write(tmp_path / "clean.csv", rows=6000, seed=0)
    raw, _ = degrade.degrade(euroc.read_imu_csv(clean),
                             degrade.DegradeConfig(dropout_mode=mode, healthy_s=5.0, dropout_count=2,
                                                   duplicate_rows=3, swap_rows=3), seed=5)
    src = tmp_path / "deg.csv"
    euroc.write_imu_csv(raw, src, nan_text=nan_text)
    _compare(src, tmp_path, monkeypatch)


def test_physical_motion_with_still_start(tmp_path, monkeypatch):
    rows, _, _ = _moving(seconds=20.0)
    still = _static_rows(2.0, np.eye(3), bias=(0.002, -0.001, 0.0005))
    shift = still[-1][0] + 5_000_000 - rows[0][0]
    allrows = still + [(t + shift, v) for t, v in rows]
    src = _write_rows(tmp_path / "imu.csv", allrows)
    dp, dq = _compare(src, tmp_path, monkeypatch)
    assert dp < 1e-9                                         # same arithmetic order: rounding only


def test_move_rest_move_backward_pass(tmp_path, monkeypatch):
    rows, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.002, acc_noise=0.02, seed=3)
    # sprinkle the messy cases into the stored (pre-anchor) part and after it
    nan = float("nan")
    rows = list(rows)
    rows.insert(300, (None, rows[300][1]))
    rows.insert(500, (rows[499][0], rows[499][1]))                       # duplicate
    rows.insert(700, (rows[699][0] + 2_500_000, (nan,) * 6))              # NaN row
    rows.insert(900, (rows[899][0] - 10**9, rows[899][1]))                # out of order
    rows = rows[:1200] + [(t + 300_000_000, v) for t, v in rows[1200:]]  # 0.3 s gap
    src = _write_rows(tmp_path / "imu.csv", rows)
    assert sd.calibrate(sd.rows_from_raw(euroc.read_imu_csv(src))).run_s is not None
    dp, dq = _compare(src, tmp_path, monkeypatch)
    assert dp < 1e-9 and main.LAST["calibrated"] and main.LAST["pre_rows"] > 1000


def test_pre_segment_cap_fallback(tmp_path, monkeypatch):
    rows, _, _ = _move_rest_move(seconds=24.0, gyro_noise=1e-3, acc_noise=1e-2)
    src = _write_rows(tmp_path / "imu.csv", rows)
    monkeypatch.setattr(sd, "PRE_MAX_ROWS", 100)
    monkeypatch.setattr(main, "PRE_MAX_ROWS", 100)
    _compare(src, tmp_path, monkeypatch)
    assert not main.LAST["calibrated"] and main.LAST["pre_rows"] == 0


def test_header_only(tmp_path, monkeypatch):
    src = tmp_path / "imu.csv"
    src.write_text(euroc.HEADER + "\n")
    _compare(src, tmp_path, monkeypatch)

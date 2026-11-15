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
from test_strapdown import _moving, _static_rows  # noqa: E402

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
                 "MAX_JUMP_S", "MAX_SUMSQ"):
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


def test_header_only(tmp_path, monkeypatch):
    src = tmp_path / "imu.csv"
    src.write_text(euroc.HEADER + "\n")
    _compare(src, tmp_path, monkeypatch)

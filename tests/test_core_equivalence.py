"""main.py (optimised) and vortex/core/witness.py (reference, on top of strapdown.py) give the same
poses; with the witnesses switched off, main.py equals strapdown.py (step 6b).

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
from vortex.core import witness as wx
from vortex.data import euroc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import synth_euroc  # noqa: E402
from test_main import MESSY  # noqa: E402
from test_strapdown import _move_rest_move, _moving, _static_rows  # noqa: E402
from test_witness import _profile  # noqa: E402

FULL = b"%s.%s %.17g %.17g %.17g %.17g %.17g %.17g %.17g\n"


def _load_main():
    spec = importlib.util.spec_from_file_location("vortex_main_equiv", ROOT / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


main = _load_main()


def _compare(src, tmp_path, monkeypatch, reference=None):
    monkeypatch.setattr(main, "FMT", FULL)
    dst = tmp_path / "est.txt"
    n = main.run(str(src), str(dst))
    got = np.array([[float(x) for x in line.split()[1:]] for line in dst.read_text().splitlines()])
    ref = np.array((reference or wx.estimate_file)(src))   # (px, py, pz, qw, qx, qy, qz)
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
    for name in ("TICK_S", "GYRO_NOISE", "ACC_NOISE", "GYRO_WALK", "ACC_WALK", "P0_VEL", "P0_TILT", "P0_YAW",
                 "P0_BG", "P0_BA", "P0_TILT_FALLBACK", "P0_BG_FALLBACK", "ZUPT_SIGMA", "ZARU_SIGMA_MIN",
                 "V2_SIGMA_H", "V2_SIGMA_V", "V2P_SIGMA_H", "V2P_SIGMA_V", "V2P_TAU", "V1_ON", "V2_ON",
                 "V2P_ON", "JAM_TAU", "GAP_H_TICKS", "GAP_TAU", "JAM_ON", "GAP_ON", "STUCK_ROWS", "DEAD_ON", "FC_TAU",
                 "FC_ON", "PRE_HOLD", "N"):
        assert getattr(main, name) == getattr(wx, name), name


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


@pytest.mark.parametrize("hold", [False, True])
def test_move_rest_move_backward_pass(tmp_path, monkeypatch, hold):
    for mod in (main, wx):
        monkeypatch.setattr(mod, "PRE_HOLD", hold)
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
    if hold:
        first = (tmp_path / "est.txt").read_text().splitlines()[0].split()
        assert [float(x) for x in first[1:4]] == [0.0, 0.0, 0.0]


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


@pytest.fixture(scope="module")
def second_rest_rows():
    rows, _, _ = _profile(46.0, [(8, 10, -1), (24, 26, +1), (34, 36, -1)], bias_step_s=25.0,
                          gyro_step=(0.0, 0.0, 0.01), acc_step=(0.08, -0.06, 0.0))
    return rows


def test_witnesses_fire_and_match(tmp_path, monkeypatch, second_rest_rows):
    src = _write_rows(tmp_path / "imu.csv", second_rest_rows)
    dp, dq = _compare(src, tmp_path, monkeypatch)
    assert dp < 1e-9                                         # same arithmetic order: rounding only
    assert main.LAST["zupt_ticks"] > 30 and abs(main.LAST["ba"][0]) > 1e-3


def test_witnesses_off_equals_step_6b(tmp_path, monkeypatch, second_rest_rows):
    for name in ("V1_ON", "V2_ON", "V2P_ON", "PRE_HOLD"):
        monkeypatch.setattr(main, name, False)
    src = _write_rows(tmp_path / "imu.csv", second_rest_rows)
    dp, dq = _compare(src, tmp_path, monkeypatch, reference=sd.estimate_file)
    assert dp == 0.0 and dq == 0.0
    assert main.LAST["zupt_ticks"] == 0 and main.LAST["ba"] == (0.0, 0.0, 0.0)


@pytest.fixture(scope="module")
def noisy_gappy_rows():
    """SYNTHETIC: noise above the filter's datasheet densities (the meter acts), a 2 s NaN dropout
    and a 2 s hole with no rows (the dropout covariance acts)."""
    rows, _, _ = _profile(40.0, [(8, 10, -1), (22, 24, +1)], gyro_noise=0.03, acc_noise=0.4, seed=6)
    nan = float("nan")
    rows = list(rows)
    rows[6000:6400] = [(t, (nan,) * 6) for t, _ in rows[6000:6400]]
    return rows[:7000] + rows[7400:]


@pytest.mark.parametrize("jam, gap", [(True, True), (True, False), (False, True), (False, False)])
def test_meter_and_gap_match(tmp_path, monkeypatch, noisy_gappy_rows, jam, gap):
    for mod in (main, wx):
        monkeypatch.setattr(mod, "JAM_ON", jam)
        monkeypatch.setattr(mod, "GAP_ON", gap)
    src = _write_rows(tmp_path / "imu.csv", noisy_gappy_rows)
    dp, dq = _compare(src, tmp_path, monkeypatch)
    assert dp < 1e-9                                         # same arithmetic order: rounding only
    if jam:
        assert main.LAST["jam"][0] > main.GYRO_NOISE ** 2 and main.LAST["jam"][1] > main.ACC_NOISE ** 2
    else:
        assert main.LAST["jam"] == (-1.0, -1.0)
    assert (main.LAST["tilt2"] > 0.0) == gap


@pytest.fixture(scope="module")
def failing_rows():
    """SYNTHETIC: a 2 s NaN dropout, a gyro stuck for 0.5 s (accel live), two all-zero accelerometer rows,
    then a stuck failure (last row repeated) for the final 5 s."""
    rows, _, _ = _profile(40.0, [(8, 10, -1), (22, 24, +1)], gyro_noise=0.03, acc_noise=0.4, seed=7)
    nan = float("nan")
    rows = list(rows)
    rows[5000:5400] = [(t, (nan,) * 6) for t, _ in rows[5000:5400]]
    g = rows[5999][1][:3]
    rows[6000:6100] = [(t, g + v[3:]) for t, v in rows[6000:6100]]
    rows[6500:6502] = [(t, v[:3] + (0.0, 0.0, 0.0)) for t, v in rows[6500:6502]]
    rows[7000:] = [(t, rows[6999][1]) for t, _ in rows[7000:]]
    return rows


@pytest.mark.parametrize("dead, fc", [(True, True), (True, False), (False, True), (False, False)])
def test_dead_and_forecaster_match(tmp_path, monkeypatch, failing_rows, dead, fc):
    for mod in (main, wx):
        monkeypatch.setattr(mod, "DEAD_ON", dead)
        monkeypatch.setattr(mod, "FC_ON", fc)
    src = _write_rows(tmp_path / "imu.csv", failing_rows)
    dp, dq = _compare(src, tmp_path, monkeypatch)
    assert dp < 1e-9


def test_failing_rows_exercise_both_switches(failing_rows):
    base = wx.estimate(failing_rows, dead=False, fc=False)
    assert wx.estimate(failing_rows, dead=True, fc=False) != base
    assert wx.estimate(failing_rows, dead=False, fc=True) != base

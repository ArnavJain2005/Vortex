import json

import numpy as np
import pytest

from vortex import baselines, metrics
from vortex.cli import main
from vortex.data import advio, synthetic
from vortex.geometry import (
    matrix_to_quat,
    quat_from_rotvec,
    quat_multiply,
    quat_slerp_series,
    quat_to_matrix,
    quat_to_rotvec,
)
from vortex.trajectory_io import read_tum, write_tum
from vortex.types import ImuData, Trajectory


# ---------- geometry ----------

def test_rotvec_roundtrip_and_matrix():
    rng = np.random.default_rng(1)
    rv = rng.uniform(-2, 2, size=(50, 3))
    q = quat_from_rotvec(rv)
    assert np.allclose(quat_to_rotvec(q), rv, atol=1e-9)
    for qi in q:
        R = quat_to_matrix(qi)
        assert np.allclose(R @ R.T, np.eye(3), atol=1e-12)
        q2 = matrix_to_quat(R)
        assert np.allclose(np.abs(np.dot(q2, qi)), 1.0, atol=1e-9)


def test_multiply_matches_matrix_product():
    a, b = quat_from_rotvec(np.array([0.3, -0.2, 0.9])), quat_from_rotvec(np.array([-1.1, 0.4, 0.2]))
    assert np.allclose(quat_to_matrix(quat_multiply(a, b)), quat_to_matrix(a) @ quat_to_matrix(b))


def test_slerp_endpoints_and_midpoint():
    q0 = np.array([1.0, 0, 0, 0])
    q1 = quat_from_rotvec(np.array([0, 0, 1.0]))
    out = quat_slerp_series(np.array([0.0, 1.0]), np.stack([q0, q1]), np.array([0.0, 0.5, 1.0]))
    assert np.allclose(quat_to_rotvec(out), [[0, 0, 0], [0, 0, 0.5], [0, 0, 1.0]], atol=1e-9)


# ---------- containers ----------

def test_trajectory_rejects_bad_input():
    with pytest.raises(ValueError):
        Trajectory(t=np.array([0.0, 0.0]), p=np.zeros((2, 3)), q=np.tile([1.0, 0, 0, 0], (2, 1)))
    with pytest.raises(ValueError):
        ImuData(t=np.arange(3.0), gyro=np.zeros((3, 3)), accel=np.full((3, 3), np.nan))


# ---------- synthetic data and dead reckoning ----------

def test_synthetic_imu_reads_gravity_at_rest_level():
    seq = synthetic.make_sequence(duration=5.0)
    # Specific force magnitude stays near g for a gentle walk.
    norms = np.linalg.norm(seq.imu.accel, axis=1)
    assert 9.0 < norms.mean() < 10.6


def test_dead_reckoning_tracks_noiseless_synthetic():
    """Kinematics check: perfect IMU + perfect initial state must reproduce ground truth closely."""
    seq = synthetic.make_sequence(duration=20.0)
    # Tiny velocity window: the 2 Hz head bob makes a wide central difference inexact.
    est = baselines.run_dead_reckoning(seq, gravity=synthetic.GRAVITY_WORLD, dv=0.005)
    r = metrics.evaluate(est, seq.ground_truth, align="none")
    assert r["final_error_m"] < 0.05, r["final_error_m"]


def test_dead_reckoning_drifts_with_bias():
    seq = synthetic.make_sequence(duration=20.0, accel_bias=(0.05, 0.0, 0.0))
    est = baselines.run_dead_reckoning(seq, gravity=synthetic.GRAVITY_WORLD)
    r = metrics.evaluate(est, seq.ground_truth, align="none")
    # 0.5 * 0.05 * 20^2 = 10 m of drift from a constant bias, give or take rotation of the body.
    assert r["final_error_m"] > 2.0


def test_oracle_gravity_recovers_world_gravity():
    seq = synthetic.make_sequence(duration=60.0)
    g = baselines.oracle_gravity(seq)
    assert np.linalg.norm(g - synthetic.GRAVITY_WORLD) < 0.05


def test_accel_sign_detection():
    seq = synthetic.make_sequence(duration=40.0)
    assert baselines.detect_accel_sign(seq)["better"] == "as_loaded"
    flipped = ImuData(t=seq.imu.t, gyro=seq.imu.gyro, accel=-seq.imu.accel)
    seq.imu = flipped
    assert baselines.detect_accel_sign(seq)["better"] == "negated"


# ---------- freeze-on-loss ----------

def test_freeze_on_loss_holds_last_pose():
    t = np.arange(10.0)
    p = np.column_stack([t, np.zeros(10), np.zeros(10)])
    traj = Trajectory(t=t, p=p, q=np.tile([1.0, 0, 0, 0], (10, 1)))
    avail = baselines.mask_from_windows(t, [(3.0, 4.0)])  # out for t in [3, 7)
    assert list(avail) == [True] * 3 + [False] * 4 + [True] * 3
    out = baselines.freeze_on_loss(traj, avail)
    assert list(out.p[:, 0]) == [0, 1, 2, 2, 2, 2, 2, 7, 8, 9]


def test_freeze_on_loss_leading_gap_uses_first_available():
    t = np.arange(5.0)
    traj = Trajectory(t=t, p=np.column_stack([t, t * 0, t * 0]), q=np.tile([1.0, 0, 0, 0], (5, 1)))
    out = baselines.freeze_on_loss(traj, np.array([False, False, True, True, True]))
    assert list(out.p[:, 0]) == [2, 2, 2, 3, 4]


# ---------- metrics ----------

def _line(n=200):
    t = np.linspace(0, 20, n)
    p = np.column_stack([t, np.sin(t), 0.1 * t])
    return Trajectory(t=t, p=p, q=np.tile([1.0, 0, 0, 0], (n, 1)), name="x")


def test_ate_zero_after_rigid_motion():
    gt = _line()
    R = quat_to_matrix(quat_from_rotvec(np.array([0.2, -0.4, 1.3])))
    moved = Trajectory(t=gt.t, p=gt.p @ R.T + [5, -2, 1], q=gt.q, name="moved")
    assert metrics.evaluate(moved, gt, align="full")["ate_rmse_m"] < 1e-9
    assert metrics.evaluate(moved, gt, align="prefix", prefix_s=5)["ate_rmse_m"] < 1e-9
    assert metrics.evaluate(moved, gt, align="none")["ate_rmse_m"] > 1.0
    T = metrics.alignment_transform(moved, gt)
    assert metrics.evaluate(moved, gt, align="given", transform=T)["ate_rmse_m"] < 1e-9


def test_constant_offset_without_alignment():
    gt = _line()
    off = Trajectory(t=gt.t, p=gt.p + [0.3, 0.4, 0.0], q=gt.q)
    r = metrics.evaluate(off, gt, align="none")
    assert r["ate_rmse_m"] == pytest.approx(0.5)
    assert r["final_error_m"] == pytest.approx(0.5)
    assert r["rpe_rmse_m"] == pytest.approx(0.0, abs=1e-12)
    assert r["time_to_1m_s"] is None
    assert r["drift_per_m"] == pytest.approx(0.5 / gt.path_length(), rel=1e-6)


# ---------- I/O ----------

def test_tum_roundtrip(tmp_path):
    seq = synthetic.make_sequence(duration=2.0)
    write_tum(seq.pose, tmp_path / "a.tum")
    back = read_tum(tmp_path / "a.tum")
    assert np.allclose(back.p, seq.pose.p, atol=1e-8)
    assert np.allclose(back.q, seq.pose.q, atol=1e-8)


def _write_fake_advio(root, number=3):
    """A tiny sequence in ADVIO's on-disk layout, built from synthetic data."""
    seq = synthetic.make_sequence(duration=30.0, imu_rate=100.0)
    d = root / f"advio-{number:02d}"
    (d / "ground-truth").mkdir(parents=True)
    (d / "iphone").mkdir()
    gt = seq.ground_truth
    np.savetxt(d / "ground-truth" / "poses.csv", np.column_stack([gt.t, gt.p, gt.q]), delimiter=",")
    np.savetxt(d / "iphone" / "arkit.csv", np.column_stack([seq.pose.t, seq.pose.p, seq.pose.q]), delimiter=",")
    # ADVIO stores accelerometer in g with CoreMotion's sign (negated specific force).
    acc_g = -seq.imu.accel / advio.STANDARD_GRAVITY
    np.savetxt(d / "iphone" / "accelerometer.csv", np.column_stack([seq.imu.t, acc_g]), delimiter=",")
    gyro = np.column_stack([seq.imu.t, seq.imu.gyro])
    gyro = np.vstack([gyro, gyro[5]])  # a duplicated row, which the loader must drop
    np.savetxt(d / "iphone" / "gyro.csv", gyro, delimiter=",")
    return seq


def test_advio_loader_reads_layout(tmp_path):
    ref = _write_fake_advio(tmp_path)
    seq = advio.load_sequence(tmp_path, 3, remove_bias=False)
    assert seq.name == "advio-03"
    assert seq.meta["dropped_non_increasing"]["gyro"] == 1
    assert np.allclose(seq.imu.accel, ref.imu.accel, atol=1e-6)
    assert np.allclose(seq.ground_truth.p, ref.ground_truth.p)
    with pytest.raises(FileNotFoundError):
        advio.load_sequence(tmp_path, 4)


def test_advio_bias_table_lookup():
    assert advio.bias_for(1)["accel"][0] == 0.0407
    assert advio.bias_for(15)["gyro"][1] == 0.0055
    assert advio.bias_for(23) is not None and advio.bias_for(24) is None


# ---------- CLI end to end ----------

def test_cli_baselines_on_fake_advio(tmp_path, capsys):
    _write_fake_advio(tmp_path / "data")
    out = tmp_path / "res"
    rc = main(["baselines", "--advio", str(tmp_path / "data"), "--seq", "3", "--blackout", "10", "5",
               "--out", str(out), "--no-plot"])
    assert rc == 0
    res = json.loads((out / "advio-03" / "baselines.json").read_text())["results"]
    assert res["pose_clean"]["ate_rmse_m"] < 0.01
    # A 5 s freeze while walking at ~0.7 m/s must cost metres, not centimetres.
    assert res["freeze_on_loss"]["ate_max_m"] > 1.0
    assert (out / "advio-03" / "freeze_on_loss.tum").is_file()


def test_cli_check_synthetic(capsys):
    assert main(["check", "--synthetic"]) == 0
    assert "OK" in capsys.readouterr().out

"""Naive baselines the robust estimator is compared against.

1. Dead reckoning: integrate the IMU alone from a known initial state. Shows how fast inertial-only
   tracking drifts. It is given every advantage: the initial pose and velocity come from ground truth,
   and the gravity vector is estimated with ground-truth orientation (an "oracle" no real system has).
2. Freeze-on-loss: pass the device's own tracking pose through while it is available and hold the
   last pose while it is missing. This is what many XR apps visibly do when tracking is lost.
"""

from __future__ import annotations

import numpy as np

from .geometry import (
    matrix_to_quat,
    quat_from_rotvec,
    quat_multiply,
    quat_normalize,
    quat_slerp_series,
    quat_to_matrix,
)
from .types import ImuData, Sequence, Trajectory


def dead_reckoning(
    imu: ImuData,
    p0: np.ndarray,
    v0: np.ndarray,
    q0: np.ndarray,
    gravity_world: np.ndarray,
    t_start: float | None = None,
    t_end: float | None = None,
) -> Trajectory:
    """Strapdown integration. q0 is the IMU (body) orientation in the world frame at t_start."""
    m = np.ones(len(imu.t), dtype=bool)
    if t_start is not None:
        m &= imu.t >= t_start
    if t_end is not None:
        m &= imu.t <= t_end
    t, gyro, acc = imu.t[m], imu.gyro[m], imu.accel[m]
    n = len(t)
    if n < 2:
        raise ValueError("need at least two IMU samples in the window")

    g = np.asarray(gravity_world, dtype=float)
    p = np.empty((n, 3))
    q = np.empty((n, 4))
    p[0], q[0] = p0, quat_normalize(q0)
    v = np.asarray(v0, dtype=float).copy()
    for k in range(n - 1):
        dt = t[k + 1] - t[k]
        a_w = quat_to_matrix(q[k]) @ acc[k] + g
        p[k + 1] = p[k] + v * dt + 0.5 * a_w * dt * dt
        v = v + a_w * dt
        q[k + 1] = quat_normalize(quat_multiply(q[k], quat_from_rotvec(gyro[k] * dt)))
    return Trajectory(t=t, p=p, q=q, name="dead_reckoning")


def body_orientation_from_gt(gt: Trajectory, t: np.ndarray, r_cam_imu: np.ndarray) -> np.ndarray:
    """IMU orientation in the world frame, from ground-truth camera orientation: R_wi = R_wc R_ci."""
    q_wc = quat_slerp_series(gt.t, gt.q, t)
    q_ci = matrix_to_quat(np.asarray(r_cam_imu, dtype=float))
    return quat_normalize(quat_multiply(q_wc, np.broadcast_to(q_ci, q_wc.shape)))


def oracle_gravity(seq: Sequence) -> np.ndarray:
    """Gravity in the ground-truth world frame, estimated as -mean(R_wi f) over the sequence.

    Valid because the average linear acceleration over a long walk is close to zero. Uses
    ground-truth orientation, so it is only for setting up the baseline, never for the estimator.
    """
    imu = seq.imu
    inside = (imu.t >= seq.ground_truth.t[0]) & (imu.t <= seq.ground_truth.t[-1])
    q_wi = body_orientation_from_gt(seq.ground_truth, imu.t[inside], np.array(seq.meta["R_cam_imu"]))
    f_world = np.einsum("nij,nj->ni", quat_to_matrix(q_wi), imu.accel[inside])
    return -f_world.mean(axis=0)


def initial_state_from_gt(seq: Sequence, t0: float, dv: float = 0.1) -> tuple:
    """(p0, v0, q0_body) at time t0 from ground truth; velocity by central difference over +-dv s."""
    gt = seq.ground_truth
    p_at = lambda tt: np.array([np.interp(tt, gt.t, gt.p[:, i]) for i in range(3)])  # noqa: E731
    p0 = p_at(t0)
    v0 = (p_at(t0 + dv) - p_at(t0 - dv)) / (2 * dv)
    q0 = body_orientation_from_gt(gt, np.array([t0]), np.array(seq.meta["R_cam_imu"]))[0]
    return p0, v0, q0


def run_dead_reckoning(
    seq: Sequence,
    t_start: float | None = None,
    t_end: float | None = None,
    gravity: np.ndarray | None = None,
    dv: float = 0.05,
) -> Trajectory:
    """Dead reckoning initialised from ground truth. dv: half-window (s) for the initial velocity."""
    gt = seq.ground_truth
    t0 = max(seq.imu.t[0], gt.t[0] + dv) if t_start is None else t_start
    t1 = min(seq.imu.t[-1], gt.t[-1] - dv) if t_end is None else t_end
    p0, v0, q0 = initial_state_from_gt(seq, t0, dv=dv)
    g = oracle_gravity(seq) if gravity is None else gravity
    return dead_reckoning(seq.imu, p0, v0, q0, g, t_start=t0, t_end=t1)


def freeze_on_loss(pose: Trajectory, available: np.ndarray) -> Trajectory:
    """Hold the last available pose while the pose stream is unavailable.

    available: (N,) bool aligned with pose.t. Samples before the first available one take the first
    available pose (there is nothing earlier to hold).
    """
    available = np.asarray(available, dtype=bool)
    if available.shape != pose.t.shape:
        raise ValueError("available must have one entry per pose sample")
    if not available.any():
        raise ValueError("pose stream is never available")
    idx = np.where(available, np.arange(len(available)), -1)
    idx = np.maximum.accumulate(idx)
    idx[idx < 0] = int(np.argmax(available))
    return Trajectory(t=pose.t.copy(), p=pose.p[idx], q=pose.q[idx], name="freeze_on_loss")


def mask_from_windows(t: np.ndarray, windows: list[tuple[float, float]]) -> np.ndarray:
    """True where the stream is available, False inside any (start, duration) outage window."""
    available = np.ones(len(t), dtype=bool)
    for start, duration in windows:
        available &= ~((t >= start) & (t < start + duration))
    return available


def detect_accel_sign(seq: Sequence, window: float = 2.0, n_windows: int = 10) -> dict:
    """Decide empirically whether the loaded accelerometer sign is right.

    Dead-reckons short windows spread over the sequence with the loaded data and with the
    accelerometer negated, and compares median end-of-window error against ground truth.
    """
    gt = seq.ground_truth
    lo = max(seq.imu.t[0], gt.t[0]) + 0.5
    hi = min(seq.imu.t[-1], gt.t[-1]) - window - 0.5
    if hi <= lo:
        raise ValueError("sequence too short for the sign check")
    starts = np.linspace(lo, hi, n_windows)
    errors = {}
    for sign in (1.0, -1.0):
        flipped = ImuData(t=seq.imu.t, gyro=seq.imu.gyro, accel=sign * seq.imu.accel)
        s = Sequence(seq.name, flipped, seq.pose, gt, seq.meta)
        g = oracle_gravity(s)
        errs = []
        for t0 in starts:
            est = run_dead_reckoning(s, t0, t0 + window, gravity=g)  # default dv
            p_true = np.array([np.interp(est.t[-1], gt.t, gt.p[:, i]) for i in range(3)])
            errs.append(float(np.linalg.norm(est.p[-1] - p_true)))
        errors["as_loaded" if sign > 0 else "negated"] = float(np.median(errs))
    verdict = "as_loaded" if errors["as_loaded"] <= errors["negated"] else "negated"
    return {"window_s": window, "n_windows": n_windows, "median_end_error_m": errors, "better": verdict}

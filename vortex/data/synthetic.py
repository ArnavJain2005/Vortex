"""Synthetic walking-style sequences with exact ground truth.

Used by the tests and to exercise the whole pipeline before real data is available. Nothing measured
from synthetic data is a claim about real devices.

Construction: the body angular velocity is defined analytically and the orientation is obtained by
integrating it with the same exponential map the estimators use, so a noiseless gyroscope is exactly
consistent with the ground truth. Position is analytic; specific force is R^T (a_world - g_world).
"""

from __future__ import annotations

import numpy as np

from ..geometry import quat_from_rotvec, quat_multiply, quat_normalize, quat_slerp_series, quat_to_matrix
from ..types import ImuData, Sequence, Trajectory

GRAVITY_WORLD = np.array([0.0, 0.0, -9.81])


def make_sequence(
    duration: float = 30.0,
    imu_rate: float = 200.0,
    pose_rate: float = 60.0,
    gyro_noise: float = 0.0,
    accel_noise: float = 0.0,
    gyro_bias: tuple = (0.0, 0.0, 0.0),
    accel_bias: tuple = (0.0, 0.0, 0.0),
    pose_pos_noise: float = 0.0,
    seed: int = 0,
    still_s: float = 0.0,
    ramp_s: float = 2.0,
) -> Sequence:
    """A person walking a slow figure-eight with head bob and gentle head turns.

    Noise values are per-sample standard deviations (rad/s, m/s^2, m). Defaults are noiseless.
    still_s > 0 adds that many seconds at rest first, then eases into the walk over ramp_s seconds
    (as in our phone walk protocol). With still_s = 0 everything is analytic; with still_s > 0 the
    acceleration is differentiated numerically, accurate to about 1e-3 m/s^2 at 200 Hz.
    """
    rng = np.random.default_rng(seed)
    dt = 1.0 / imu_rate
    t = np.arange(0.0, duration + 0.5 * dt, dt)
    w = 0.12

    def walk_pos(tau: np.ndarray) -> np.ndarray:
        # Figure-eight of radius ~3 m at ~0.7 m/s plus a 2 Hz, 2 cm vertical bob.
        return np.column_stack(
            [3.0 * np.sin(w * tau), 1.5 * np.sin(2 * w * tau), 1.6 + 0.02 * np.sin(2 * np.pi * 2.0 * tau)]
        )

    def walk_omega(tau: np.ndarray) -> np.ndarray:
        # Body angular velocity: slow yaw sweep plus small pitch and roll oscillations.
        return np.column_stack(
            [
                0.15 * np.cos(2 * np.pi * 0.3 * tau),
                0.10 * np.sin(2 * np.pi * 0.5 * tau),
                0.25 * np.sin(2 * np.pi * 0.05 * tau),
            ]
        )

    if still_s <= 0:
        p = walk_pos(t)
        a = np.column_stack(
            [
                -3.0 * w**2 * np.sin(w * t),
                -1.5 * (2 * w) ** 2 * np.sin(2 * w * t),
                -0.02 * (2 * np.pi * 2.0) ** 2 * np.sin(2 * np.pi * 2.0 * t),
            ]
        )
        omega = walk_omega(t)
    else:
        # Speed factor h rises smoothly 0 -> 1 after the still period; walk time tau = integral of h.
        u = np.clip((t - still_s) / ramp_s, 0.0, 1.0)
        h = u * u * u * (u * (6 * u - 15) + 10)  # smootherstep: zero 1st and 2nd derivative at the ends
        tau = np.concatenate([[0.0], np.cumsum(0.5 * (h[1:] + h[:-1]) * dt)])
        p = walk_pos(tau)
        a = np.gradient(np.gradient(p, t, axis=0, edge_order=2), t, axis=0, edge_order=2)
        a[t < still_s] = 0.0
        omega = walk_omega(tau) * h[:, None]
    q = np.empty((len(t), 4))
    q[0] = [1.0, 0.0, 0.0, 0.0]
    for k in range(len(t) - 1):
        q[k + 1] = quat_normalize(quat_multiply(q[k], quat_from_rotvec(omega[k] * dt)))

    R = quat_to_matrix(q)
    f = np.einsum("nji,nj->ni", R, a - GRAVITY_WORLD)  # R^T (a - g)

    # Gyro sample k is the rate over [t_k, t_k+1), matching the integration above.
    gyro = omega + np.asarray(gyro_bias) + gyro_noise * rng.standard_normal(omega.shape)
    accel = f + np.asarray(accel_bias) + accel_noise * rng.standard_normal(f.shape)

    gt = Trajectory(t=t, p=p, q=q, name="ground_truth")
    imu = ImuData(t=t.copy(), gyro=gyro, accel=accel)

    tp = np.arange(0.0, duration, 1.0 / pose_rate)
    pp = np.column_stack([np.interp(tp, t, p[:, i]) for i in range(3)])
    pp = pp + pose_pos_noise * rng.standard_normal(pp.shape)
    pose = Trajectory(t=tp, p=pp, q=quat_slerp_series(t, q, tp), name="pose")

    meta = {
        "dataset": "synthetic",
        "seed": seed,
        "gravity_world": GRAVITY_WORLD.tolist(),
        "R_cam_imu": np.eye(3).tolist(),
    }
    return Sequence(name=f"synthetic-s{seed}", imu=imu, pose=pose, ground_truth=gt, meta=meta)

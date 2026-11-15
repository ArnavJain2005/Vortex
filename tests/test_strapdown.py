"""Reference estimator step 6a (vortex/core/strapdown.py): initialisation and strapdown integration.
All data here is SYNTHETIC."""

import math

import numpy as np
import pytest

from vortex.core import strapdown as sd
from vortex.geometry import quat_from_rotvec, quat_multiply, quat_normalize, quat_to_matrix

T0 = 1403636579758555392
DT_NS = 5_000_000
G = 9.81


def _static_rows(seconds, R, bias=(0, 0, 0), gyro_noise=0.0, acc_noise=0.0, seed=0, g=G):
    rng = np.random.default_rng(seed)
    n = int(seconds * 200)
    f = R.T @ np.array([0.0, 0.0, g])
    rows = []
    for k in range(n):
        gyro = np.asarray(bias, float) + gyro_noise * rng.standard_normal(3)
        acc = f + acc_noise * rng.standard_normal(3)
        rows.append((T0 + k * DT_NS, tuple(float(x) for x in (*gyro, *acc))))
    return rows


def _gravity_dir_error(q, f_mean):
    """Angle between R(q) f_mean and world +z."""
    w = np.array(sd.rotate(q, *f_mean))
    return math.acos(np.clip(w[2] / np.linalg.norm(w), -1, 1))


# ---------- initialisation ----------

def test_init_static_tilted_with_bias():
    R = quat_to_matrix(quat_from_rotvec(np.array([0.3, -0.5, 1.2])))
    rows = _static_rows(2.0, R, bias=(0.01, -0.02, 0.005), gyro_noise=0.002, acc_noise=0.02, g=9.806)
    win = sd.init_window(rows)
    assert len(win) == 201                                   # [t0, t0 + 1 s] inclusive at 200 Hz
    ini = sd.initialise(win)
    assert ini.still
    assert np.allclose(ini.bg, (0.01, -0.02, 0.005), atol=5e-4)
    assert ini.g == pytest.approx(9.806, abs=0.01)
    f_mean = np.mean([v[3:] for v in win], axis=0)
    assert _gravity_dir_error(ini.q, f_mean) < 1e-9
    assert sum(c * c for c in ini.q) == pytest.approx(1.0)


def test_init_upside_down():
    rows = _static_rows(1.5, np.diag([1.0, -1.0, -1.0]))     # body z points down
    ini = sd.initialise(sd.init_window(rows))
    assert _gravity_dir_error(ini.q, (0, 0, -G)) < 1e-9


def test_init_not_still_uses_default_g_and_zero_bias():
    rows = _static_rows(1.5, np.eye(3), bias=(0.05, 0, 0), gyro_noise=0.2, acc_noise=0.5, seed=4)
    ini = sd.initialise(sd.init_window(rows))
    assert not ini.still and ini.bg == (0.0, 0.0, 0.0) and ini.g == sd.G_DEFAULT


def test_init_skips_invalid_rows_and_handles_none():
    nan = float("nan")
    rows = [(None, (0, 0, 0, 0, 0, G)), (T0, (nan,) * 6)] + _static_rows(1.5, np.eye(3))
    assert len(sd.init_window(rows)) == 201
    ini = sd.initialise([])
    assert ini.q == (1.0, 0.0, 0.0, 0.0) and ini.rows == 0


# ---------- integration ----------

def test_static_stays_at_origin():
    R = quat_to_matrix(quat_from_rotvec(np.array([0.2, 0.4, -0.7])))
    rows = _static_rows(60.0, R, bias=(0.003, -0.001, 0.002))
    out = sd.estimate(rows)
    assert len(out) == len(rows)
    assert max(abs(c) for c in out[-1][:3]) < 1e-6


def _moving(seconds=30.0, rate=200, sub=20):
    """SYNTHETIC instantaneous IMU samples of an analytic motion; truth attitude integrated with
    `sub` midpoint sub-steps per sample. Starts at rest velocity, attitude identity."""
    dt = 1.0 / rate
    n = int(seconds * rate) + 1
    t = np.arange(n) * dt
    A, w = np.array([1.5, 1.0, 0.3]), np.array([0.4, 0.55, 0.9])
    p = A * (1 - np.cos(np.outer(t, w)))
    a = A * w ** 2 * np.cos(np.outer(t, w))
    omega = lambda s: np.column_stack([0.3 * np.sin(0.7 * s), 0.2 * np.cos(0.5 * s) - 0.2,  # noqa: E731
                                       0.4 * np.sin(0.3 * s)])
    h = dt / sub
    ts = (np.arange((n - 1) * sub) + 0.5) * h
    dq = quat_from_rotvec(omega(ts) * h)
    q = np.empty((n, 4))
    cur = np.array([1.0, 0, 0, 0])
    q[0] = cur
    for k in range(n - 1):
        for j in range(sub):
            cur = quat_multiply(cur, dq[k * sub + j])
        cur = quat_normalize(cur)
        q[k + 1] = cur
    R = quat_to_matrix(q)
    f = np.einsum("nji,nj->ni", R, a + np.array([0, 0, G]))
    gyro = omega(t)
    rows = [(T0 + k * DT_NS, tuple(float(x) for x in (*gyro[k], *f[k]))) for k in range(n)]
    return rows, p, q


@pytest.fixture(scope="module")
def moving():
    return _moving()


def test_noiseless_motion_tracks_truth(moving):
    rows, p, q = moving
    ini = sd.Init((1.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0), G, True, 0)
    out = np.array(sd.estimate(rows, init=ini))
    err = np.linalg.norm(out[:, :3] - p, axis=1)
    assert err.max() < 0.01                                    # 30 s of motion, noiseless
    dot = np.abs(np.sum(out[:, 3:] * q, axis=1))
    att = 2 * np.arccos(np.clip(dot, -1, 1))
    assert att.max() < 1e-5                                    # rad


def test_rows_without_timestamp_or_values_never_break_output(moving):
    rows, p, _ = moving
    nan, inf = float("nan"), float("inf")
    bad = list(rows[:400])
    bad.insert(100, (None, rows[100][1]))                      # no timestamp
    bad.insert(150, (bad[149][0], bad[149][1]))                # duplicate
    bad.insert(200, (T0 - 10**9, bad[199][1]))                 # out of order
    bad.insert(250, (bad[249][0] + 10**12, bad[249][1]))       # corrupt forward jump (1000 s)
    bad.insert(300, (bad[299][0] + DT_NS // 2, (nan, 0, 0, 0, 0, inf)))
    bad.insert(320, (bad[319][0] + DT_NS // 2, (1e300,) * 6))  # finite but absurd
    out = sd.estimate(bad)
    assert len(out) == len(bad)
    flat = [c for row in out for c in row]
    assert all(math.isfinite(c) for c in flat)
    for i in (100, 150, 200, 250):                             # ignored rows repeat the previous pose
        assert out[i] == out[i - 1]
    for r in out:
        assert sum(c * c for c in r[3:]) == pytest.approx(1.0)


def test_gap_is_bridged_at_constant_velocity():
    # moving at constant world velocity is impossible to start (v0 = 0), so check the rule directly:
    rows = _static_rows(3.0, np.eye(3))
    gap = rows[:300] + [(t + 2 * 10**9, v) for t, v in rows[300:]]   # a 2 s hole after 1.5 s
    out = sd.estimate(gap)
    assert len(out) == len(gap)
    assert max(abs(c) for c in out[-1][:3]) < 1e-9            # at rest, v = 0, so it stays put

"""Step L2 (TILT_ON): windowed gravity alignment with a gyro noise meter. All inputs SYNTHETIC.

Checks: sign conventions of the tilt pseudo-measurement and of the window rotation (finite differences on
exact rotations); the meter's weight and its robustness to spikes; no change at all when the meter reads a
clean gyro; steady banked flight (15 deg, thrust-aligned with a drag-like offset: the instantaneous
accelerometer tilt is wrong by about 15 deg) where the windowed form must stay within its stated bias;
a jammed gyro with a clean accelerometer, where the tilt must be held.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from vortex.core import witness as wx
from vortex.geometry import quat_from_rotvec, quat_to_matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
T0 = 1403636579758555392
DT_NS = 5_000_000
G = 9.81


def _rv(R):
    """Rotation vector of a rotation matrix (small or moderate angles)."""
    c = max(-1.0, min(1.0, (np.trace(R) - 1.0) / 2.0))
    th = math.acos(c)
    w = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    return w * (0.5 if th < 1e-9 else th / (2.0 * math.sin(th)))


def _flight(seconds, pos, rest=4.0, ramp=4.0, offset_deg=3.0, rate=200, sub=10, gyro=None, seed=0):
    """SYNTHETIC multirotor-like flight: at rest for `rest` s, then pos(t) faded in over `ramp` s. Attitude:
    body z along the specific force (thrust), yaw fixed, then pitched about body y by an angle proportional to
    speed (offset_deg at 2 m/s; a drag-like offset, so the accelerometer is not pure body-z thrust). Exact IMU:
    f_b = R^T (a + g z), gyro from consecutive rotations. gyro(rng, k, n): optional added gyro error per row.
    Returns rows, true rotation matrices per row."""
    h = 1.0 / (rate * sub)
    n = int(seconds * rate) + 1
    tf = np.arange((n + 4) * sub) * h            # padded: np.gradient's end rows are not used

    def env(t):
        x = np.clip((t - rest) / ramp, 0.0, 1.0)
        return x * x * x * (10 - 15 * x + 6 * x * x)     # C2: continuous thrust direction

    P = pos(tf) * env(tf)[:, None]
    V = np.gradient(P, h, axis=0)
    A = np.gradient(V, h, axis=0)
    Rs = []
    for k in range(len(tf)):
        f = A[k] + np.array([0.0, 0.0, G])
        b3 = f / np.linalg.norm(f)
        b2 = np.cross(b3, [1.0, 0.0, 0.0])
        b2 /= np.linalg.norm(b2)
        b1 = np.cross(b2, b3)
        R = np.column_stack([b1, b2, b3])
        d = math.radians(offset_deg) * np.linalg.norm(V[k]) / 2.0
        Ry = np.array([[math.cos(d), 0, math.sin(d)], [0, 1, 0], [-math.sin(d), 0, math.cos(d)]])
        Rs.append(R @ Ry)
    rng = np.random.default_rng(seed)
    rows, Rt = [], []
    for k in range(n):
        i = k * sub
        R = Rs[i]
        om = _rv(R.T @ Rs[i + 1]) / h
        fb = R.T @ (A[i] + np.array([0.0, 0.0, G]))
        if gyro is not None:
            om = om + gyro(rng, k, n)
        rows.append((T0 + k * DT_NS, tuple(float(x) for x in (*om, *fb))))
        Rt.append(R)
    return rows, Rt


def _circle(r=1.56, w=1.3):
    """Horizontal circle: centripetal 2.64 m/s^2, i.e. a 15 deg bank, speed 2.0 m/s."""
    return lambda t: np.column_stack([r * np.cos(w * t) - r, r * np.sin(w * t), 0.0 * t])


def _tilt_err_deg(out, Rt, start_s):
    errs = []
    for k in range(int(start_s * 200), len(out)):
        q = np.array(out[k][3:])
        Re = quat_to_matrix(q)
        ze, zt = Re[2, :], Rt[k][2, :]
        errs.append(math.degrees(math.acos(max(-1.0, min(1.0, float(ze @ zt))))))
    return np.array(errs)


@pytest.fixture
def tilt_forced(monkeypatch):
    """Weight 1 whatever the meter reads (so the tilt update is exercised on clean gyros too)."""
    monkeypatch.setattr(wx, "TILT_G_LO", -1.0)
    monkeypatch.setattr(wx, "TILT_G_HI", 0.0)


def test_shipped_state_off():
    assert wx.TILT_ON is False


def test_measurement_sign_matches_finite_difference():
    """F_hat = R_hat f_b with R = Exp(dth) R_hat. For level truth, F_hat = Exp(-dth) (0, 0, g):
    dth_x = F_y / g and dth_y = -F_x / g to first order; the opposite sign is far off."""
    for dth in ([0.01, 0.0, 0.0], [0.0, -0.02, 0.0], [0.015, 0.01, 0.05]):
        dth = np.array(dth)
        F = quat_to_matrix(quat_from_rotvec(-dth)) @ np.array([0.0, 0.0, G])
        tol = float(dth @ dth)                  # second order
        assert abs(F[1] / G - dth[0]) < tol and abs(-F[0] / G - dth[1]) < tol
        assert abs(-F[1] / G - dth[0]) > 1e-2 or abs(dth[0]) < 1e-9


def test_window_rotation_after_injection():
    """After injecting dth_hat (q+ = Exp(dth_hat) q), a window built with the old attitude becomes
    Exp(dth_hat) F; the code uses F + dth_hat x F (first order)."""
    F = np.array([0.3, -0.2, 9.8])
    d = np.array([0.01, -0.02, 0.05])
    exact = quat_to_matrix(quat_from_rotvec(d)) @ F
    approx = F + np.cross(d, F)
    assert np.abs(exact - approx).max() < float(d @ d) * np.linalg.norm(F)     # second order
    assert np.abs(exact - (F - np.cross(d, F))).max() > 10 * np.abs(exact - approx).max()
    # full correction of the measured tilt levels the window
    dth = np.array([F[1] / G, -F[0] / G, 0.0])
    lev = F + np.cross(dth, F)
    k = abs(1.0 - F[2] / G)                       # exact for F_z = g
    assert abs(lev[0]) <= abs(F[0]) * k + 1e-12 and abs(lev[1]) <= abs(F[1]) * k + 1e-12


def test_weight_and_spike_robustness():
    lo, hi = wx.TILT_G_LO, wx.TILT_G_HI
    assert wx.tilt_weight([lo * lo] * 5)[0] == 0.0
    assert wx.tilt_weight([hi * hi] * 5)[0] == 1.0
    mid = 0.5 * (lo + hi)
    assert abs(wx.tilt_weight([mid * mid] * 5)[0] - 0.5) < 1e-12
    clean = [0.04 ** 2] * 40
    spiky = clean[:]
    for i in range(0, 40, 4):        # one tick in four carries a spike (far more than the script's rate)
        spiky[i] = 0.5
    assert wx.tilt_weight(spiky)[0] == 0.0


def test_clean_gyro_changes_nothing():
    """Meter below TILT_G_LO (a clean gyro): TILT_ON changes no output at all."""
    rows, _ = _flight(40.0, _circle())
    off = wx.estimate(rows, tilt=False)
    on = wx.estimate(rows, tilt=True)
    assert off == on


def test_banked_flight_stays_within_bias(tilt_forced):
    """Steady 15 deg banked circle with a drag-like pitch offset; the accelerometer's instantaneous tilt is
    wrong by about 15 deg. With weight 1 the windowed alignment must not pull the attitude by more than its
    stated bias (TILT_DV / (g TILT_TAU), about 1 deg) plus 1 deg of margin, compared with TILT_ON off."""
    rows, Rt = _flight(70.0, _circle())
    off = _tilt_err_deg(wx.estimate(rows, tilt=False), Rt, 20.0)
    on = _tilt_err_deg(wx.estimate(rows, tilt=True), Rt, 20.0)
    bias = math.degrees(wx.TILT_DV / (G * wx.TILT_TAU))
    assert on.max() < off.max() + bias + 1.0, (on.max(), off.max(), bias)
    # instantaneous accelerometer tilt in this flight, for scale: about 15 deg off
    inst = []
    for (t, v), R in zip(rows[int(20 * 200):], Rt[int(20 * 200):]):
        fb = np.array(v[3:]) / np.linalg.norm(v[3:])
        inst.append(math.degrees(math.acos(max(-1.0, min(1.0, float(fb @ R[2, :]))))))
    assert np.mean(inst) > 10.0
    assert on.max() < 0.25 * np.mean(inst)


def test_jammed_gyro_tilt_held():
    """Reading-a-like gyro (white 0.2 rad/s per sample, a roll-axis bias appearing after the calibration
    rest, spikes), clean accelerometer. TILT_ON (meter-weighted, shipped constants) holds the tilt; off it is
    lost."""
    def jam(rng, k, n):
        t = k / 200.0
        e = rng.standard_normal(3) * 0.2
        if t > 6.0:
            e = e + np.array([0.03, -0.02, 0.0])
        if rng.random() < 0.003:
            e = e + rng.choice([-1.0, 1.0]) * 3.0
        return e
    rows, Rt = _flight(80.0, lambda t: np.column_stack([0.8 * np.sin(0.4 * t), 0.6 * np.sin(0.3 * t), 0.0 * t]),
                       gyro=jam, seed=3)
    off = _tilt_err_deg(wx.estimate(rows, tilt=False), Rt, 30.0)
    on = _tilt_err_deg(wx.estimate(rows, tilt=True), Rt, 30.0)
    rms = lambda x: float(np.sqrt(np.mean(x * x)))  # noqa: E731
    assert rms(off) > 20.0, rms(off)
    assert rms(on) < 6.0, (rms(on), rms(off))


def test_window_memory_is_bounded():
    """The meter ring never exceeds TILT_MED_TICKS entries (state: 3 + 2 + 2 floats + the ring)."""
    rows, _ = _flight(30.0, _circle(), gyro=lambda rng, k, n: rng.standard_normal(3) * 0.2)
    log = []
    wx.estimate(rows, tilt=True, log=log)
    assert len(log) > 2 * wx.TILT_MED_TICKS
    assert max(d["tring"] for d in log) == wx.TILT_MED_TICKS
    assert max(d["tw"] for d in log) == 1.0 and any(d["tup"] for d in log)

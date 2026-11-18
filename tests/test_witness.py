"""Reference estimator step 7a (vortex/core/witness.py): error-state filter, V1 stillness, V2 flight
envelope. All data here is SYNTHETIC."""

import math

import numpy as np
import pytest

from vortex.core import strapdown as sd
from vortex.core import witness as wx
from vortex.geometry import quat_from_rotvec, quat_multiply, quat_normalize, quat_to_matrix
from test_strapdown import DT_NS, G, T0, _move_rest_move


# ---------- filter algebra against dense numpy ----------

def _rand_spd(rng, n=wx.N):
    a = rng.standard_normal((n, n)) * 0.1
    return a @ a.T + np.eye(n) * 1e-3


def test_kf_propagate_matches_dense():
    rng = np.random.default_rng(1)
    P0 = _rand_spd(rng)
    q = quat_normalize(rng.standard_normal(4))
    R = quat_to_matrix(q)
    f = np.array([0.3, -0.7, 9.6])
    T = 0.25
    A = np.zeros((15, 15))
    A[0:3, 3:6] = np.eye(3) * T
    skew = np.array([[0, -f[2], f[1]], [f[2], 0, -f[0]], [-f[1], f[0], 0]])
    A[3:6, 6:9] = -T * skew
    A[3:6, 12:15] = -T * R
    A[6:9, 9:12] = -T * R
    Phi = np.eye(15) + A
    Q = np.diag([0, 0, 0] + [wx.ACC_NOISE ** 2 * T] * 3 + [wx.GYRO_NOISE ** 2 * T] * 3
                + [wx.GYRO_WALK ** 2 * T] * 3 + [wx.ACC_WALK ** 2 * T] * 3)
    want = Phi @ P0 @ Phi.T + Q
    P = [float(x) for x in P0.ravel()]
    wx.kf_propagate(P, tuple(float(x) for x in R.ravel()), *map(float, f), T)
    assert np.allclose(np.array(P).reshape(15, 15), want, rtol=1e-12, atol=1e-14)


def test_kf_update_matches_dense():
    rng = np.random.default_rng(2)
    P0 = _rand_spd(rng)
    dx0 = rng.standard_normal(15) * 0.01
    k, z, var = 4, 0.3, 0.05
    H = np.zeros(15)
    H[k] = 1.0
    S = H @ P0 @ H + var
    K = P0 @ H / S
    want_dx = dx0 + K * (z - dx0[k])
    want_P = P0 - np.outer(K, H @ P0)
    P = [float(x) for x in P0.ravel()]
    dx = [float(x) for x in dx0]
    wx.kf_update(P, dx, k, z, var)
    assert np.allclose(dx, want_dx, rtol=1e-12, atol=1e-15)
    assert np.allclose(np.array(P).reshape(15, 15), want_P, rtol=1e-12, atol=1e-15)


def test_rot_matrix_matches_geometry():
    q = quat_normalize(np.array([0.3, -0.2, 0.9, 0.1]))
    assert np.allclose(np.array(wx.rot_matrix(tuple(q))).reshape(3, 3), quat_to_matrix(q), atol=1e-15)


# ---------- switches ----------

def test_witnesses_off_equals_step_6b():
    rows, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.002, acc_noise=0.02)
    # the smoother is a separate post-pass (with zero corrections it still renormalises the quaternions)
    assert wx.estimate(rows, v1=False, v2=False, v2p=False, pre_hold=False, smooth=False) == sd.estimate(rows)


# ---------- synthetic profile with a second rest and a bias step after calibration ----------

def _ss(u):
    u = np.clip(u, 0, 1)
    return u ** 3 * (u * (6 * u - 15) + 10), 30 * u ** 2 * (u - 1) ** 2


def _profile(seconds, transitions, sub=10, gyro_noise=2e-3, acc_noise=2e-2, bias_step_s=None,
             gyro_step=(0, 0, 0), acc_step=(0, 0, 0), seed=0):
    """SYNTHETIC. Motion amplitude e(t) starts at 1 and toggles smoothly at each (start, end, +-1)
    transition; e = 0 is rest. Box-bounded motion (|p| <= 1.5 m). From bias_step_s on, constant gyro
    and accel bias steps are added (body frame): biases that the still-run calibration cannot see."""
    rng = np.random.default_rng(seed)
    rate = 200
    dt = 1.0 / rate
    n = int(seconds * rate) + 1
    h = dt / sub
    tf = np.arange((n - 1) * sub + 1) * h

    def env(t):
        e, de = np.ones_like(t), np.zeros_like(t)
        for a0, a1, sgn in transitions:
            s, d = _ss((t - a0) / (a1 - a0))
            e, de = e + sgn * s, de + sgn * d / (a1 - a0)
        return e, de

    A, w = np.array([1.5, 1.0, 0.3]), np.array([0.4, 0.55, 0.9])
    e, de = env(tf)
    V = A * w * np.sin(np.outer(tf, w))
    a = de[:, None] * V + e[:, None] * (A * w ** 2 * np.cos(np.outer(tf, w)))
    v = e[:, None] * V
    p = np.concatenate([np.zeros((1, 3)), np.cumsum(0.5 * (v[1:] + v[:-1]) * h, axis=0)])
    om = lambda s: np.column_stack([0.3 * np.sin(0.7 * s), 0.2 * np.cos(0.5 * s) - 0.2,  # noqa: E731
                                    0.6 * np.sin(0.3 * s)]) * env(s)[0][:, None]
    dq = quat_from_rotvec(om(tf[:-1] + 0.5 * h) * h)
    qf = np.empty((n, 4))
    cur = np.array([1.0, 0, 0, 0])
    qf[0] = cur
    for k in range(n - 1):
        for j in range(sub):
            cur = quat_multiply(cur, dq[k * sub + j])
        cur = quat_normalize(cur)
        qf[k + 1] = cur
    idx = np.arange(n) * sub
    R = quat_to_matrix(qf)
    f = np.einsum("nji,nj->ni", R, a[idx] + np.array([0, 0, G]))
    gyro = om(tf[idx]) + 0.002 + gyro_noise * rng.standard_normal((n, 3))
    f = f + acc_noise * rng.standard_normal((n, 3))
    if bias_step_s is not None:
        on = (tf[idx] >= bias_step_s)[:, None]
        gyro = gyro + on * np.asarray(gyro_step, float)
        f = f + on * np.asarray(acc_step, float)
    rows = [(T0 + k * DT_NS, tuple(float(x) for x in (*gyro[k], *f[k]))) for k in range(n)]
    return rows, p[idx], qf


@pytest.fixture(scope="module")
def second_rest():
    # move 0..8, rest 10..24 (the longest: calibration), move 26..34, rest 36..46; biases step at 25 s
    return _profile(46.0, [(8, 10, -1), (24, 26, +1), (34, 36, -1)], bias_step_s=25.0,
                    gyro_step=(0.0, 0.0, 0.01), acc_step=(0.08, -0.06, 0.0))


def test_v1_stops_drift_at_the_second_rest(second_rest):
    from test_strapdown import _in_our_frame
    rows, p, q = second_rest
    cal = sd.calibrate(rows)
    t = (np.array([r[0] for r in rows]) - T0) * 1e-9
    i0, i1 = np.searchsorted(t, 42.0), len(rows) - 1        # well inside the second rest
    res = {}
    for v1 in (True, False):
        out = np.array(wx.estimate(rows, v1=v1, v2=False, v2p=False))
        pt, _ = _in_our_frame(out.tolist(), p, q, cal.anchor)
        res[v1] = (np.linalg.norm(out[i1, :3] - pt[i1]), np.linalg.norm(out[i1, :3] - out[i0, :3]))
    # the unseen bias steps give ~12 m of error by the end of the motion (36 s). The ZUPTs stop the
    # drift and, through the position-velocity correlation, take most of that error back.
    assert res[True][0] < 2.0 and res[True][1] < 0.2, res
    assert res[False][0] > 30.0 and res[False][1] > 10.0, res


def test_v1_zaru_finds_the_new_gyro_bias(second_rest):
    rows, _, _ = second_rest
    log = []
    wx.estimate(rows, v1=True, v2=False, v2p=False, log=log)
    assert any(L["zupt"] for L in log if L["t"] > T0 + 37 * 10**9)
    bg = log[-1]["bg"]
    assert np.allclose(bg, (0.002, 0.002, 0.012), atol=1e-3), bg
    log_off = []
    wx.estimate(rows, v1=False, v2=False, v2p=False, log=log_off)
    assert abs(log_off[-1]["bg"][2] - 0.002) < 1e-3          # without V1 the old bias stays


@pytest.fixture(scope="module")
def long_flight():
    # rest 0..12 s only (calibration), then 110 s of box-bounded motion with an accel bias step
    return _profile(122.0, [(-2, 0, -1), (12, 14, +1)], sub=4, bias_step_s=13.0,
                    acc_step=(0.06, -0.05, 0.03), seed=3)


def test_v2_bounds_drift_under_an_unseen_accel_bias(long_flight):
    rows, p, q = long_flight
    cal = sd.calibrate(rows)

    def end_error(**sw):
        out = np.array(wx.estimate(rows, **sw))
        # yaw and origin are arbitrary: compare in the estimator's frame fixed at the anchor
        from test_strapdown import _in_our_frame
        pt, _ = _in_our_frame(out.tolist(), p, q, cal.anchor)
        return np.linalg.norm(out[:, :3] - pt, axis=1).max()

    off = end_error(v1=True, v2=False, v2p=False)
    speed = end_error(v1=True, v2=True, v2p=False)
    both = end_error(v1=True, v2=True, v2p=True)
    assert off > 50.0, off                  # 0.08 m/s^2 unseen for 108 s: hundreds of metres
    assert speed < 10.0, speed
    assert both < 5.0, both


def test_v2_estimates_the_unseen_accel_bias(long_flight):
    rows, _, _ = long_flight
    log = []
    wx.estimate(rows, log=log)
    ba = np.array(log[-1]["ba"])
    true = np.array((0.06, -0.05, 0.03))
    assert np.linalg.norm(ba - true) < 0.5 * np.linalg.norm(true), ba


def test_never_nan_with_witnesses_on(second_rest):
    rows, _, _ = second_rest
    nan, inf = float("nan"), float("inf")
    bad = list(rows[:6000])
    bad.insert(100, (None, rows[100][1]))
    bad.insert(2500, (bad[2499][0], bad[2499][1]))
    bad.insert(3000, (T0 - 10**9, bad[2999][1]))
    bad.insert(3500, (bad[3499][0] + 10**12, bad[3499][1]))
    bad.insert(4000, (bad[3999][0] + DT_NS // 2, (nan, 0, 0, 0, 0, inf)))
    bad.insert(4500, (bad[4499][0] + DT_NS // 2, (1e300,) * 6))
    bad[5000:5400] = [(t, (nan,) * 6) for t, _ in bad[5000:5400]]      # a 2 s dropout
    out = wx.estimate(bad)
    assert len(out) == len(bad)
    assert all(math.isfinite(c) for row in out for c in row)
    for r in out:
        assert sum(c * c for c in r[3:]) == pytest.approx(1.0)


# ---------- step 6c: noise meter and dropout covariance (SYNTHETIC) ----------

def test_gap_inflate_matches_constant_acceleration_model():
    rng = np.random.default_rng(4)
    P0 = _rand_spd(rng)
    L, tilt2, dv2 = 1.5, 4e-3, (0.3, 0.2, 0.05)
    s = (L / (wx.GAP_H_TICKS * wx.TICK_S)) ** 2
    want = P0.copy()
    for k in range(3):
        G = np.zeros(15)
        G[k], G[3 + k] = L / 2, 1.0            # p += v L, v += a L with a constant: p gets a L^2 / 2
        want += np.outer(G, G) * dv2[k] * s
    want[6, 6] += 0.5 * tilt2 * s
    want[7, 7] += 0.5 * tilt2 * s
    P = [float(x) for x in P0.ravel()]
    wx.gap_inflate(P, L, tilt2, dv2)
    assert np.allclose(np.array(P).reshape(15, 15), want, rtol=1e-13, atol=1e-15)


def test_gap_switch_changes_nothing_without_gaps(second_rest):
    rows, _, _ = second_rest
    assert wx.estimate(rows, gap_on=True) == wx.estimate(rows, gap_on=False)


def test_noise_meter_below_datasheet_changes_nothing(second_rest):
    rows, _, _ = second_rest     # 2e-3 rad/s and 2e-2 m/s^2 per sample: below the filter's densities
    log = []
    assert wx.estimate(rows, jam=True, log=log) == wx.estimate(rows, jam=False)
    jg = np.median([L["jg"] for L in log])
    assert jg < wx.GYRO_NOISE ** 2


def test_noise_meter_reads_the_added_white_noise():
    rows, _, _ = _profile(40.0, [(8, 10, -1), (24, 26, +1)], gyro_noise=0.03, acc_noise=0.4, seed=5)
    log = []
    wx.estimate(rows, log=log, jam=True)
    dt = DT_NS * 1e-9
    jg = np.median([L["jg"] for L in log[40:]])
    ja = np.median([L["ja"] for L in log[40:]])
    # the profile's smooth motion barely shows in second differences: the meter reads the noise
    assert jg == pytest.approx(0.03 ** 2 * dt, rel=0.1)
    assert ja == pytest.approx(0.4 ** 2 * dt, rel=0.1)


def test_dropout_inflates_velocity_and_tilt_variance(second_rest):
    rows, _, _ = second_rest
    i0 = 6000                                               # 30 s: moving, after the calibration rest
    bad = list(rows)
    bad[i0:i0 + 400] = [(t, (float("nan"),) * 6) for t, _ in bad[i0:i0 + 400]]   # a 2 s dropout
    t_end = bad[i0 + 400][0]
    after = {}
    for on in (True, False):
        log = []
        wx.estimate(bad, gap_on=on, log=log)
        L = next(L for L in log if L["t"] >= t_end - DT_NS)   # closed by the first row after it
        assert L["gap"] == pytest.approx(2.0, abs=0.01)
        after[on] = L
    assert after[True]["pv"] > 2 * after[False]["pv"]
    assert after[True]["ptilt"] > 2 * after[False]["ptilt"]


# ---------------------------------------------------------------- step 8: dead sensor, forecaster

NAN6 = (float("nan"),) * 6


def _fail(rows, i0, mode):
    """SYNTHETIC failure from row i0 on: 'nan', 'zero' (all six 0.0) or 'stuck' (row i0 - 1 repeated)."""
    val = {"nan": NAN6, "zero": (0.0,) * 6, "stuck": rows[i0 - 1][1]}[mode]
    return list(rows[:i0]) + [(t, val) for t, _ in rows[i0:]]


def test_dead_detection_changes_nothing_on_live_data(second_rest):
    rows, _, _ = second_rest
    assert wx.estimate(rows, dead=True) == wx.estimate(rows, dead=False)


def test_zero_rows_coast_like_nan_rows(second_rest):
    rows = second_rest[0][:7000]
    i0 = 6000                                               # 30 s, moving; 5 s of failure
    ref = wx.estimate(_fail(rows, i0, "nan"), dead=False)
    assert wx.estimate(_fail(rows, i0, "zero"), dead=True) == ref
    off = wx.estimate(_fail(rows, i0, "zero"), dead=False)  # integrated: zero specific force
    assert math.dist(off[-1][:3], ref[-1][:3]) > 20.0     # (66 m here; V2 holds the vertical)


def test_stuck_rows_coast_from_the_stuck_rows_th_repeat(second_rest):
    rows = second_rest[0][:7000]
    i0 = 6000
    stuck = _fail(rows, i0, "stuck")
    k = i0 - 2 + wx.STUCK_ROWS                              # the run starts at row i0 - 1
    expect = stuck[:k] + [(t, NAN6) for t, _ in stuck[k:]]
    assert wx.estimate(stuck, dead=True) == wx.estimate(expect, dead=False)
    assert wx.estimate(stuck, dead=False) != wx.estimate(expect, dead=False)


def test_one_stuck_sensor_is_enough(second_rest):
    rows = second_rest[0][:7000]
    i0 = 6000
    g = rows[i0 - 1][1][:3]
    stuck = list(rows[:i0]) + [(t, g + v[3:]) for t, v in rows[i0:]]   # gyro stuck, accel live
    k = i0 - 2 + wx.STUCK_ROWS
    expect = stuck[:k] + [(t, NAN6) for t, _ in stuck[k:]]
    assert wx.estimate(stuck, dead=True) == wx.estimate(expect, dead=False)


def test_coast_decays_velocity_toward_zero():
    p, v = wx.coast([1.0, 2.0, 3.0], [1.0, -2.0, 0.5], 3.0, 2.0)
    e = math.exp(-1.5)
    assert v == pytest.approx([e, -2.0 * e, 0.5 * e], rel=1e-15)
    assert p == pytest.approx([1.0 + 2.0 * (1 - e), 2.0 - 4.0 * (1 - e), 3.0 + 1.0 * (1 - e)], rel=1e-15)
    p2, v2 = wx.coast(*wx.coast([1.0, 2.0, 3.0], [1.0, -2.0, 0.5], 1.0, 2.0), 2.0, 2.0)
    assert p2 == pytest.approx(p, rel=1e-12) and v2 == pytest.approx(v, rel=1e-12)  # composes
    assert wx.coast([0.0] * 3, [1.0, 0.0, 0.0], 3.0, None) == ([3.0, 0.0, 0.0], [1.0, 0.0, 0.0])
    assert wx.coast([0.0] * 3, [1.0, 0.0, 0.0], 1e6, 2.0)[0][0] == pytest.approx(2.0)  # bounded


def test_forecaster_acts_only_while_coasting(second_rest):
    rows = second_rest[0][:7000]
    assert wx.estimate(rows, fc=True) == wx.estimate(rows, fc=False)    # no gaps: identical
    i0 = 6000
    bad = _fail(rows, i0, "nan")
    on, off = wx.estimate(bad, fc=True), wx.estimate(bad, fc=False)
    assert on[:i0] == off[:i0]
    L = (rows[-1][0] - rows[i0 - 1][0]) * 1e-9
    want = wx.FC_TAU * (1.0 - math.exp(-L / wx.FC_TAU)) / L
    for k in range(3):
        d_on, d_off = on[-1][k] - on[i0 - 1][k], off[-1][k] - off[i0 - 1][k]
        assert d_on == pytest.approx(want * d_off, rel=1e-9, abs=1e-12)


# ---------------------------------------------------------------- step 6d: hold before the anchor

def test_pre_hold_keeps_the_anchor_position_and_backward_attitude():
    rows, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.002, acc_noise=0.02, seed=3)
    anchor = sd.calibrate(rows).anchor
    assert anchor > 100
    on, off = wx.estimate(rows, pre_hold=True), wx.estimate(rows, pre_hold=False)
    assert on[anchor:] == off[anchor:]                       # nothing after the anchor changes
    assert all(o[:3] == (0.0, 0.0, 0.0) for o in on[:anchor])
    assert [o[3:] for o in on[:anchor]] == [o[3:] for o in off[:anchor]]
    assert max(abs(c) for o in off[:anchor] for c in o[:3]) > 0.01   # the backward pass did move


# ---------------------------------------------------------------- step 7b: denoised V1 (reference only)

def test_denoised_zupt_fires_in_a_noisy_rest_after_the_run_length():
    # SYNTHETIC: rest 10..24 s and 36..46 s with white noise above the strict still thresholds
    rows, _, _ = _profile(46.0, [(8, 10, -1), (24, 26, +1), (34, 36, -1)], gyro_noise=0.03, acc_noise=0.15, seed=8)
    for on in (False, True):
        log = []
        wx.estimate(rows, zden=on, log=log)
        late = [L for L in log if L["t"] - rows[0][0] > 37e9]                # the second rest
        n = sum(L["zupt"] for L in late)
        if on:
            assert n >= 0.7 * len(late)                                         # 29 of 36 here
            first = next(i for i, L in enumerate(late) if L["zupt"])
            assert late[first]["zr"] >= wx.ZUPT_DEN_BINS
        else:
            assert n == 0                                                     # strict test: noise too high
    moving = [L for L in log if 26e9 < L["t"] - rows[0][0] < 33e9]
    assert not any(L["zupt"] for L in moving)


def test_denoised_zupt_off_changes_nothing(second_rest):
    rows, _, _ = second_rest
    assert wx.estimate(rows, zden=False) == wx.estimate(rows)


# ---------------------------------------------------------------- step 8b: per-row sigma (W6)

def test_row_sigma_grows_with_time_and_gaps():
    cov = (1.0, 0.1, 0.04)
    assert wx.row_sigma(cov, 0.0, 0.0, -1.0, [0.0] * 3) == pytest.approx(1.0)
    assert wx.row_sigma(cov, 0.5, 0.0, -1.0, [0.0] * 3) == pytest.approx(math.sqrt(1.0 + 0.1 + 0.01))
    h = wx.GAP_H_TICKS * wx.TICK_S
    want = 1.0 + 0.6 * (2.0 / h) ** 2 * 4.0 * 0.25
    assert wx.row_sigma(cov, 0.0, 2.0, 0.01, [0.2, 0.2, 0.2]) == pytest.approx(math.sqrt(want))
    assert wx.row_sigma(cov, 0.0, 2.0, -1.0, [0.2, 0.2, 0.2]) == pytest.approx(1.0)   # no motion learned yet


def test_row_sigma_is_reporting_only(second_rest):
    rows, _, _ = second_rest
    sig = []
    assert wx.estimate(rows, sig=sig) == wx.estimate(rows)
    anchor = sd.calibrate(rows).anchor
    assert len(sig) == len(rows) and all(math.isnan(x) for x in sig[:anchor])
    assert all(x >= 0.0 and math.isfinite(x) for x in sig[anchor:])


# ---- Step 4: envelope learned per file (LEARN_ON) ----

def test_learned_envelope_reference_and_pathfinder_agree(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    import test_core_equivalence as tce
    from test_core_equivalence import _compare, _write_rows
    from test_strapdown import _move_rest_move
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("vortex_pf_learn", root / "pathfinder.py")
    pf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pf)
    rows, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.002, acc_noise=0.02, seed=5)
    src = _write_rows(tmp_path / "imu.csv", rows)
    for iters, k in ((1, 1.0), (2, 1.5)):
        for mod in (wx, pf):
            monkeypatch.setattr(mod, "LEARN_ON", True)
            monkeypatch.setattr(mod, "LEARN_ITERS", iters)
            monkeypatch.setattr(mod, "LEARN_K", k)
        monkeypatch.setattr(tce, "main", pf)
        _compare(src, tmp_path, monkeypatch, reference=wx.estimate_file)
        assert pf.LAST["env"] == wx.LAST_ENV[0] and pf.LAST["env"] is not None


def test_learn_env_window_and_clamps(monkeypatch):
    acc = []
    for k in range(10):                        # ticks at t = 0..9; speed^2 1 in the first half, 100 later
        acc += [float(k), 1.0 if k < 5 else 100.0, 0.0, 4.0, 1e6]
    monkeypatch.setattr(wx, "LEARN_FRAC", 0.5)
    env = wx.learn_env(acc, 0, 9)              # window t <= 4.5: ticks 0..4
    assert env[0] == 1.0 and env[1] == wx.LEARN_MIN[1] and env[2] == 2.0 and env[3] == wx.LEARN_MAX[3]
    monkeypatch.setattr(wx, "LEARN_K", 1.5)
    assert wx.learn_env(acc, 0, 9)[0] == 1.5 and wx.learn_env(acc, 0, 9)[2] == 3.0
    assert wx.learn_env([], 0, 9) == (wx.V2_SIGMA_H, wx.V2_SIGMA_V, wx.V2P_SIGMA_H, wx.V2P_SIGMA_V)


def test_learn_off_changes_nothing(tmp_path):
    from test_core_equivalence import _write_rows
    from test_strapdown import _move_rest_move
    rows, _, _ = _move_rest_move(seed=6, gyro_noise=0.001, acc_noise=0.01)
    assert not wx.LEARN_ON
    assert wx.estimate_learned(rows) == wx.estimate(rows)


# ---------- step E / Step 6: fixed-interval (RTS) smoother (SMOOTH_ON, on since Step 6) ----------

def test_smooth_gain_matches_dense():
    rng = np.random.default_rng(5)
    Pp = _rand_spd(rng)
    q = quat_normalize(rng.standard_normal(4))
    R = tuple(float(x) for x in quat_to_matrix(q).ravel())
    A = wx.phi_entries(R, 0.3, -0.7, 9.6, 0.25)
    Phi = np.eye(15)
    for i, j, a in A:
        Phi[i, j] += a
    Pm = Phi @ Pp @ Phi.T + np.eye(15) * 1e-4
    C = wx.smooth_gain([float(x) for x in Pp.ravel()], A, [float(x) for x in Pm.ravel()])
    assert np.allclose(np.array(C).reshape(15, 15), Pp @ Phi.T @ np.linalg.inv(Pm), rtol=1e-9, atol=1e-12)
    assert wx.smooth_gain([float(x) for x in Pp.ravel()], [], [0.0] * 225) is None   # not positive definite


def test_smooth_default_is_on_and_the_switch_works(second_rest):
    rows, _, _ = second_rest
    assert wx.SMOOTH_ON is True                 # Step 6: ships on (rule passed on held-out copies, 18 Nov)
    assert wx.estimate(rows) == wx.estimate(rows, smooth=True)
    assert wx.estimate(rows) != wx.estimate(rows, smooth=False)


def test_smoother_carries_the_second_rest_back(second_rest):
    """SYNTHETIC: with V1 only, the bias steps after calibration are seen only at the second rest. The
    smoother carries that back over the second motion; the last pose (the filtered one) is unchanged."""
    from test_strapdown import _in_our_frame
    rows, p, q = second_rest
    cal = sd.calibrate(rows)
    t = (np.array([r[0] for r in rows]) - T0) * 1e-9
    m = (t >= 26.0) & (t <= 36.0)
    err, outs = {}, {}
    for on in (False, True):
        out = np.array(wx.estimate(rows, v1=True, v2=False, v2p=False, smooth=on))
        pt, _ = _in_our_frame(out.tolist(), p, q, cal.anchor)
        err[on], outs[on] = np.linalg.norm(out[:, :3] - pt, axis=1), out
    assert err[False][m].max() > 10.0 and err[True][m].max() < 1.0, (err[False][m].max(), err[True][m].max())
    assert np.array_equal(outs[True][:cal.anchor], outs[False][:cal.anchor])   # rows before the anchor
    assert np.array_equal(outs[True][-1], outs[False][-1])                     # after the last tick


def test_smoother_store_never_exceeds_the_cap(second_rest, monkeypatch):
    """The store merges adjacent blocks when full; a small cap must still help and never grow."""
    rows, _, _ = second_rest
    seen = []
    real = wx.smooth_push

    def spy(blocks, blk, cap):
        real(blocks, blk, cap)
        seen.append(len(blocks))
    monkeypatch.setattr(wx, "SMOOTH_MAX_BLOCKS", 16)
    monkeypatch.setattr(wx, "smooth_push", spy)
    out = wx.estimate(rows, v1=True, v2=False, v2p=False, smooth=True)
    assert max(seen) <= 16 and len(seen) > 100
    assert all(math.isfinite(x) for o in out for x in o)


def test_smooth_merge_composes_exactly():
    rng = np.random.default_rng(7)
    mk = lambda: (0, wx._f32(rng.standard_normal(225) * 0.2), wx._f32(rng.standard_normal(15)),  # noqa: E731
                  wx._f32(rng.standard_normal(15)))
    b1, b2 = mk(), mk()
    e_end = rng.standard_normal(15)
    A1, c1 = np.array(b1[1]).reshape(15, 15), np.array(b1[2])
    A2, c2 = np.array(b2[1]).reshape(15, 15), np.array(b2[2])
    want = A1 @ (A2 @ e_end + c2) + c1
    t, A, c, d = wx.smooth_merge(b1, b2)
    got = np.array(A).reshape(15, 15) @ e_end + np.array(c)
    assert np.allclose(got, want, rtol=1e-5, atol=1e-5) and d == b1[3]

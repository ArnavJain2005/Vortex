"""Step F: gyro-bias cap on the still tests (strapdown.BGCAP_ON), covariance reset (witness.RESET_ON) and
refresh of the cached previous sample (witness.REFRESH_ON) after an injection, fallback velocity uncertainty
(witness.P0V_ON); reference and pathfinder.py copy. All SYNTHETIC."""

import importlib.util
import math
import random
import sys
from pathlib import Path

import numpy as np
import pytest

from vortex.core import strapdown as sd
from vortex.core import witness as wx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_core_equivalence as tce  # noqa: E402
from test_core_equivalence import _compare, _write_rows  # noqa: E402
from test_faults import _degraded_rows  # noqa: E402
from test_strapdown import _move_rest_move  # noqa: E402


def _load_pf():
    spec = importlib.util.spec_from_file_location("vortex_pf_stepF", ROOT / "pathfinder.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pf = _load_pf()
T0 = 1403636579758555392
DT = 5_000_000
RATE = 0.3                     # rad/s, steady yaw


def _set(monkeypatch, bgcap=False, reset=False, p0v=False, refresh=None):
    refresh = reset if refresh is None else refresh
    for mod, name, val in ((sd, "BGCAP_ON", bgcap), (pf, "BGCAP_ON", bgcap), (wx, "RESET_ON", reset),
                           (pf, "RESET_ON", reset), (wx, "REFRESH_ON", refresh), (pf, "REFRESH_ON", refresh),
                           (wx, "P0V_ON", p0v), (pf, "P0V_ON", p0v)):
        monkeypatch.setattr(mod, name, val)


def _rotating(n=1600, seed=0):
    """Level sensor turning about gravity at RATE from the first row; seeded noise (gyro 0.002, accel 0.01)."""
    rng = random.Random(seed)
    return [(T0 + i * DT, (rng.gauss(0, 0.002), rng.gauss(0, 0.002), RATE + rng.gauss(0, 0.002),
                           rng.gauss(0, 0.01), rng.gauss(0, 0.01), 9.81 + rng.gauss(0, 0.01))) for i in range(n)]


def _yaw(path):
    qx, qy, qz, qw = (float(x) for x in path.read_text().splitlines()[-1].split()[4:8])
    return math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))


def test_parameters_identical_and_shipped_state():
    for name in ("BG_MAX", "BGCAP_ON"):
        assert getattr(pf, name) == getattr(sd, name), name
    for name in ("RESET_ON", "REFRESH_ON", "P0V_ON"):
        assert getattr(pf, name) == getattr(wx, name), name
    # judged 17 Nov 2026 (tools/judge_stepF.py): BGCAP, P0V, REFRESH on; RESET off
    assert sd.BGCAP_ON and wx.P0V_ON and wx.REFRESH_ON and not wx.RESET_ON


# ---- bias cap ----

def test_steady_rotation_is_not_taken_for_bias(tmp_path, monkeypatch):
    """The failure the cap targets: 8 s of steady 0.3 rad/s yaw. Off: calibrated as rest with a 0.3 rad/s
    bias, the turn is erased. On: no still run, no bias, the turn is integrated."""
    src = _write_rows(tmp_path / "imu.csv", _rotating())
    true_yaw = RATE * (1600 - 1) * DT * 1e-9                  # 2.3985 rad
    wrapped = math.atan2(math.sin(true_yaw), math.cos(true_yaw))
    yaw = {}
    for on in (False, True):
        _set(monkeypatch, bgcap=on)
        pf.run(str(src), str(tmp_path / "o.txt"))
        yaw[on] = _yaw(tmp_path / "o.txt")
        assert pf.LAST["calibrated"] is (not on)
    assert abs(yaw[False]) < 0.01                               # the documented failure
    assert abs(yaw[True] - wrapped) < 0.02, yaw


def test_cap_keeps_a_real_bias(tmp_path, monkeypatch):
    """A still run with a realistic bias (|bg| = 0.083, the MH level) still calibrates, with the same output."""
    rows, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.002, acc_noise=0.02, seed=3)
    src = _write_rows(tmp_path / "imu.csv", rows)
    out = {}
    for on in (False, True):
        _set(monkeypatch, bgcap=on)
        pf.run(str(src), str(tmp_path / "o.txt"))
        assert pf.LAST["calibrated"]
        out[on] = (tmp_path / "o.txt").read_bytes()
    assert out[True] == out[False]


def test_cap_applies_to_every_still_test(monkeypatch):
    n = 50
    s = [0.0, 0.0, 0.2 * n, 0.0, 0.0, 9.81 * n]               # mean gyro 0.2 rad/s about z
    ss = [1e-4 * n, 1e-4 * n, (0.04 + 1e-4) * n, 1e-4 * n, 1e-4 * n, (9.81 ** 2 + 1e-4) * n]
    nd, d2 = n - 2, [1e-6 * (n - 2)] * 6
    win = [(0.0, 0.0, 0.2, 0.0, 0.0, 9.81)] * 10 + [(1e-3, 0.0, 0.2, 0.0, 1e-3, 9.81)] * 10
    for on in (False, True):
        monkeypatch.setattr(sd, "BGCAP_ON", on)
        assert sd.bin_is_still(n, s, ss) is (not on)
        assert sd.bin_is_still_denoised(n, s, ss, nd, d2) is (not on)
        assert sd.initialise(win).still is (not on)


# ---- covariance reset ----

def _qexp(v):
    th = np.linalg.norm(v)
    if th < 1e-15:
        return np.array([1.0, 0.0, 0.0, 0.0])
    return np.concatenate([[math.cos(th / 2)], math.sin(th / 2) * v / th])


def _qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def _qlog(q):
    q = q if q[0] >= 0 else -q
    s = np.linalg.norm(q[1:])
    return np.zeros(3) if s < 1e-15 else 2.0 * math.atan2(s, q[0]) * q[1:] / s


def _reset_jacobian(dhat, h=1e-6):
    """d dth+ / d dth at dth = dhat, dth+ = Log(Exp(dth) Exp(-dhat)): finite differences, no formula."""
    J = np.zeros((3, 3))
    for k in range(3):
        e = np.zeros(3)
        e[k] = h
        J[:, k] = (_qlog(_qmul(_qexp(dhat + e), _qexp(-dhat))) - _qlog(_qmul(_qexp(dhat - e), _qexp(-dhat)))) / (2 * h)
    return J


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_reset_matches_the_finite_difference_jacobian(seed):
    rng = np.random.default_rng(seed)
    dhat = rng.normal(0, 0.03, 3)
    A = rng.normal(0, 1, (wx.N, wx.N))
    P0 = A @ A.T                                              # symmetric positive definite
    P = list(P0.ravel())
    wx.kf_reset(P, *dhat)
    got = np.array(P).reshape(wx.N, wx.N)
    G = np.eye(wx.N)
    G[6:9, 6:9] = _reset_jacobian(dhat)
    want = G @ P0 @ G.T
    scale = np.abs(P0).max()
    err = np.abs(got - want).max() / scale
    assert err < np.dot(dhat, dhat), err                      # second order in |dhat|
    assert np.abs(P0 - want).max() / scale > 10 * err         # no reset is first order: the test can see it
    Pw = list(P0.ravel())
    wx.kf_reset(Pw, *(-dhat))                                 # the opposite sign (local-error convention)
    assert np.abs(np.array(Pw).reshape(wx.N, wx.N) - want).max() / scale > 10 * err
    assert np.allclose(got, got.T, rtol=0, atol=1e-12 * scale)
    assert np.array_equal(np.delete(np.delete(got, [6, 7, 8], 0), [6, 7, 8], 1),
                          np.delete(np.delete(P0, [6, 7, 8], 0), [6, 7, 8], 1))
    P2 = list(P0.ravel())
    pf._kf_reset(P2, *dhat)
    assert P2 == P                                            # the copy is bit-identical


def test_refresh_equals_resampling_with_the_corrected_state():
    rng = random.Random(4)
    q = sd.qmul_normalised((0.9, 0.1, -0.2, 0.3), (1.0, 0.0, 0.0, 0.0))
    bg, ba = (0.01, -0.02, 0.08), (0.05, -0.03, 0.1)
    raw = (0.3, -0.1, 0.2, 0.4, -0.2, 9.7)
    prev = sd._sample(q, raw[:3] + tuple(raw[3 + k] - ba[k] for k in range(3)), *bg)
    dx = [rng.gauss(0, 0.01) for _ in range(wx.N)]
    qn, _, _, bgn, ban = wx.inject(q, [0.0] * 3, [0.0] * 3, bg, ba, dx)
    want = sd._sample(qn, raw[:3] + tuple(raw[3 + k] - ban[k] for k in range(3)), *bgn)
    got = wx.refresh_prev(prev, q, qn, dx)
    assert max(abs(a - b) for a, b in zip(got, want)) < 1e-12
    assert max(abs(a - b) for a, b in zip(prev, want)) > 1e-3   # without the refresh it is stale
    assert pf._refresh_prev(*prev, *q, *qn, dx) == got


# ---- fallback velocity uncertainty ----

def test_p0v_only_changes_the_fallback(monkeypatch):
    for still in (True, False):
        monkeypatch.setattr(wx, "P0V_ON", False)
        off = wx.kf_init(still)
        monkeypatch.setattr(wx, "P0V_ON", True)
        on = wx.kf_init(still)
        if still:
            assert on == off
        else:
            assert [on[k * (wx.N + 1)] for k in (3, 4, 5)] == [wx.V2_SIGMA_H ** 2, wx.V2_SIGMA_H ** 2,
                                                                wx.V2_SIGMA_V ** 2]
            assert [on[k * (wx.N + 1)] for k in range(6, 15)] == [off[k * (wx.N + 1)] for k in range(6, 15)]
        monkeypatch.setattr(pf, "P0V_ON", True)
        assert pf._kf_init(still) == on


# ---- reference and pathfinder.py agree with the switches on ----

@pytest.mark.parametrize("bgcap,reset,p0v,refresh", [(True, True, True, True), (False, True, False, False),
                                                    (False, False, False, True), (True, False, True, False)])
@pytest.mark.parametrize("case", ["move_rest_move", "rotating", "degraded"])
def test_reference_and_pathfinder_agree(tmp_path, monkeypatch, case, bgcap, reset, p0v, refresh):
    if case == "move_rest_move":
        rows, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.002, acc_noise=0.02, seed=5)
    elif case == "rotating":
        rows = _rotating(4000, seed=1)
    else:
        rows = _degraded_rows()
    src = _write_rows(tmp_path / "imu.csv", rows)
    _set(monkeypatch, bgcap, reset, p0v, refresh)
    monkeypatch.setattr(tce, "main", pf)
    _compare(src, tmp_path, monkeypatch, reference=wx.estimate_file)


@pytest.mark.parametrize("which", ["reset", "refresh"])
def test_each_switch_changes_the_output(tmp_path, monkeypatch, which):
    """Guards against a switch wired to nothing: on the moving file each must change the poses."""
    rows, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.002, acc_noise=0.02, seed=5)
    src = _write_rows(tmp_path / "imu.csv", rows)
    out = {}
    for on in (False, True):
        _set(monkeypatch, reset=on and which == "reset", refresh=on and which == "refresh")
        pf.run(str(src), str(tmp_path / "o.txt"))
        out[on] = (tmp_path / "o.txt").read_bytes()
    assert out[True] != out[False]

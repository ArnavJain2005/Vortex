"""Step L3 (BLIND_ON): blind window from a trusted state (Docs/TRACK3_PLAN.md, Step L3). SYNTHETIC data only.

Candidate B2, L = 3 s, beta = 1: rows from ta = t_b - BLIND_L keep the anchor's attitude and move from the anchor
toward the centroid of the rows before ta, the pull ramping over BLIND_L and full from the blind start t_b on.
t_b is the first row of a trailing run of rejected rows spanning >= BLIND_MIN_S, else the last BLIND_FALLBACK_S."""
import sys
from pathlib import Path

import numpy as np
import pytest

from vortex.core import witness as wx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

DT_NS = 5_000_000
NAMES = ("BLIND_ON", "BLIND_MIN_S", "BLIND_FALLBACK_S", "BLIND_L", "BLIND_BETA")


def _rows(seconds=40.0, dead_s=5.0, dead="zeros", seed=7):
    """SYNTHETIC motion (test_witness._profile), the last dead_s seconds replaced by a failure."""
    from test_witness import _profile
    rows, _, _ = _profile(seconds, [(8, 10, -1), (22, 24, +1)], gyro_noise=0.03, acc_noise=0.4, seed=seed)
    rows = list(rows)
    k = len(rows) - int(round(dead_s * 200))
    if dead_s > 0:
        if dead == "zeros":
            rows[k:] = [(t, (0.0,) * 6) for t, _ in rows[k:]]
        elif dead == "nan":
            rows[k:] = [(t, (float("nan"),) * 6) for t, _ in rows[k:]]
    return rows, k


def _times(rows):
    return np.array([t for t, _ in rows], dtype=float) * 1e-9


def test_shipped_state_off():
    import test_core_equivalence as tce
    assert wx.BLIND_ON is False and tce.main.BLIND_ON is False and tce.LAB.BLIND_ON is False


def test_parameters_identical():
    import test_core_equivalence as tce
    for name in NAMES:
        assert getattr(tce.main, name) == getattr(wx, name) == getattr(tce.LAB, name), name


def test_off_changes_nothing():
    rows, _ = _rows()
    assert wx.estimate(rows, blind=False) == wx.estimate(rows)


@pytest.mark.parametrize("dead", ["zeros", "nan"])
def test_geometry_of_the_blend(dead):
    rows, k = _rows(dead=dead)
    off = np.array(wx.estimate(rows, blind=False))
    on = np.array(wx.estimate(rows, blind=True))
    t = _times(rows)
    tb = t[k]
    ta = tb - wx.BLIND_L
    i0 = int(np.argmax(t >= ta))
    np.testing.assert_array_equal(on[:i0], off[:i0])                 # rows before ta untouched
    c = off[:i0, :3].mean(axis=0)
    a = off[i0 - 1]
    np.testing.assert_allclose(on[k:, :3], np.broadcast_to(c, on[k:, :3].shape), atol=1e-12)   # beta = 1: centroid
    np.testing.assert_allclose(on[i0:, 3:], np.broadcast_to(a[3:], on[i0:, 3:].shape), atol=0)  # anchor attitude
    tn = np.array([r[0] for r in rows[i0:k]], dtype=np.int64)          # integer ns, as the estimator does
    ta_ns = rows[k][0] - int(wx.BLIND_L * 1e9)
    w = np.clip((tn - ta_ns) * 1e-9 / wx.BLIND_L, 0.0, 1.0) * wx.BLIND_BETA
    np.testing.assert_allclose(on[i0:k, :3], a[:3] + w[:, None] * (c - a[:3]), atol=1e-9)    # the ramp
    assert np.linalg.norm(on[i0, :3] - a[:3]) < 0.01                 # no jump at ta


def test_short_trailing_run_falls_back_to_last_5_s():
    rows, k = _rows(dead_s=0.5)                                       # 0.5 s < BLIND_MIN_S
    off = np.array(wx.estimate(rows, blind=False))
    on = np.array(wx.estimate(rows, blind=True))
    t = _times(rows)
    tb = t[-1] - wx.BLIND_FALLBACK_S
    i0 = int(np.argmax(t >= tb - wx.BLIND_L))
    np.testing.assert_array_equal(on[:i0], off[:i0])
    assert not np.array_equal(on[i0 + 1:], off[i0 + 1:])


def test_clean_file_uses_the_fallback():
    rows, _ = _rows(dead_s=0.0)
    off = np.array(wx.estimate(rows, blind=False))
    on = np.array(wx.estimate(rows, blind=True))
    t = _times(rows)
    tb = t[-1] - wx.BLIND_FALLBACK_S
    i0 = int(np.argmax(t >= tb - wx.BLIND_L))
    np.testing.assert_array_equal(on[:i0], off[:i0])
    c = off[:i0, :3].mean(axis=0)
    np.testing.assert_allclose(on[t >= tb, :3], np.broadcast_to(c, on[t >= tb, :3].shape), atol=1e-12)


def test_mid_file_dead_run_is_not_the_blind_window():
    rows, _ = _rows(dead_s=0.0)
    rows[3000:4000] = [(t, (0.0,) * 6) for t, _ in rows[3000:4000]]  # 5 s dead in the middle, live to the end
    off = np.array(wx.estimate(rows, blind=False))
    on = np.array(wx.estimate(rows, blind=True))
    np.testing.assert_array_equal(on[:4000], off[:4000])              # only the 5 s fallback at the end acts


@pytest.mark.parametrize("case", ["zeros", "nan", "fallback"])
def test_reference_and_pathfinder_agree(tmp_path, monkeypatch, case):
    import test_core_equivalence as tce
    from test_core_equivalence import _compare, _write_rows
    pf = tce.main
    for mod in (wx, pf):
        monkeypatch.setattr(mod, "BLIND_ON", True)
    rows, _ = _rows(dead_s=0.0 if case == "fallback" else 5.0, dead="nan" if case == "nan" else "zeros")
    src = _write_rows(tmp_path / "imu.csv", rows)
    dp, dq = _compare(src, tmp_path, monkeypatch)
    assert dp < 1e-9


def test_pathfinder_switch_acts_and_lab_matches(tmp_path, monkeypatch):
    import test_core_equivalence as tce
    from test_core_equivalence import _write_rows
    pf, lab = tce.main, tce.LAB
    rows, k = _rows()
    src = _write_rows(tmp_path / "imu.csv", rows)
    off = tmp_path / "off.txt"
    pf.run(str(src), str(off))
    for mod in (pf, lab):
        monkeypatch.setattr(mod, "BLIND_ON", True)
    a, b = tmp_path / "pf.txt", tmp_path / "lab.txt"
    pf.run(str(src), str(a))
    lab.run(str(src), str(b))
    assert a.read_bytes() == b.read_bytes()
    assert pf.LAST["blind_t"] == rows[k][0]                          # the blind start is the first zero row
    la, lo = a.read_text().splitlines(), off.read_text().splitlines()
    assert len(la) == len(lo) == len(rows)
    changed = [i for i, (x, y) in enumerate(zip(la, lo)) if x != y]
    assert changed and changed[0] >= k - int(wx.BLIND_L * 200) - 1 and changed[-1] == len(rows) - 1


def test_built_switch_reproduces_the_tuning_harness():
    """tools/blind_tune.py scored candidate B2 (L = 3, beta = 1) by rewriting the shipped output; the built switch
    must give the same rows."""
    import blind_tune
    from vortex.geometry import quat_to_matrix
    rows, k = _rows()
    off = np.array(wx.estimate(rows, blind=False))
    on = np.array(wx.estimate(rows, blind=True))
    t = _times(rows)
    R = np.array([quat_to_matrix(q) for q in off[:, 3:]])
    p2, R2 = blind_tune.apply(("B2", wx.BLIND_L, wx.BLIND_BETA), t, off[:, :3], R, t[k])
    # the harness works in float seconds (resolution ~2e-7 s at 1.4e9 s), the estimator in integer ns
    np.testing.assert_allclose(p2, on[:, :3], atol=1e-6)
    np.testing.assert_allclose(R2, np.array([quat_to_matrix(q) for q in on[:, 3:]]), atol=1e-12)

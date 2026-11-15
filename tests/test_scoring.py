"""evo-style scoring: association, alignment, APE/RPE, phase split (dropouts, blind 5 s, waypoint proxies)."""

import json

import numpy as np
import pytest

from vortex import scoring
from vortex.geometry import quat_from_rotvec, quat_to_matrix

T0 = 1403636579.758555392
DT = 0.005


def _gt(n=4000, rotate=True):
    t = T0 + np.arange(n) * DT
    s = t - T0
    p = np.column_stack([np.sin(0.3 * s) * 3, np.cos(0.2 * s) * 2, 0.05 * s])
    rv = np.column_stack([0.1 * np.sin(s), 0.05 * np.cos(s), 0.4 * s]) if rotate else np.zeros((n, 3))
    return scoring.Traj(t=t, p=p, R=quat_to_matrix(quat_from_rotvec(rv)))


def _rigid(tr, R, t, c=1.0):
    return scoring.Traj(t=tr.t.copy(), p=c * tr.p @ R.T + t, R=R @ tr.R)


def _rot(rv):
    return quat_to_matrix(quat_from_rotvec(np.asarray(rv, float)))


# ---------- alignment and APE ----------

@pytest.mark.parametrize("mode", ["none", "origin", "se3", "sim3"])
def test_identical_is_zero(mode):
    g = _gt()
    r = scoring.score(g, g, align=mode)
    assert r["ape"]["rmse"] == pytest.approx(0, abs=1e-9)
    assert r["rpe"]["1"]["rmse"] == pytest.approx(0, abs=1e-9)


def test_rigid_transform_removed_by_se3_sim3_origin():
    g = _gt()
    e = _rigid(g, _rot([0.2, -0.1, 1.0]), np.array([5.0, -2.0, 1.0]))
    assert scoring.score(g, e, align="none")["ape"]["rmse"] > 1.0
    for mode in ["origin", "se3", "sim3"]:
        assert scoring.score(g, e, align=mode)["ape"]["rmse"] == pytest.approx(0, abs=1e-8), mode
    # RPE is invariant to a rigid transform of the estimate
    assert scoring.score(g, e, align="none")["rpe"]["200"]["rmse"] == pytest.approx(0, abs=1e-9)


def test_scale_needs_sim3():
    g = _gt()
    e = _rigid(g, np.eye(3), np.zeros(3), c=1.5)
    assert scoring.score(g, e, align="se3")["ape"]["rmse"] > 0.1
    r = scoring.score(g, e, align="sim3")
    assert r["ape"]["rmse"] == pytest.approx(0, abs=1e-8)
    assert r["alignment"]["scale"] == pytest.approx(1 / 1.5)


def test_constant_offset_without_alignment():
    g = _gt()
    e = scoring.Traj(t=g.t, p=g.p + [1.0, 0, 0], R=g.R)
    r = scoring.score(g, e, align="none")
    assert r["ape"]["rmse"] == pytest.approx(1.0)
    assert r["ape"]["max"] == pytest.approx(1.0)


def test_n_to_align_uses_prefix_only():
    g = _gt()
    s = g.t - T0
    e = scoring.Traj(t=g.t, p=g.p + np.column_stack([np.clip(s - 10, 0, None) * 0.1, 0 * s, 0 * s]), R=g.R)
    full = scoring.score(g, e, align="se3")["ape"]["rmse"]
    prefix = scoring.score(g, e, align="se3", n_to_align=1000)["ape"]["rmse"]   # first 5 s are exact
    assert prefix > full


def test_given_alignment_from_clean_run():
    g = _gt()
    R, t = _rot([0.0, 0.0, 0.7]), np.array([1.0, 2.0, 0.0])
    clean = _rigid(g, R, t)
    drift = np.column_stack([(g.t - T0) * 0.01, np.zeros(len(g.t)), np.zeros(len(g.t))])
    deg = scoring.Traj(t=g.t, p=(g.p + drift) @ R.T + t, R=R @ g.R)
    given = scoring.fit_alignment(g, clean, "se3")
    r = scoring.score(g, deg, align="given", given=given)
    assert r["ape"]["rmse"] == pytest.approx(np.sqrt(np.mean(np.sum(drift ** 2, axis=1))), rel=1e-6)


# ---------- association ----------

def test_association_nearest_within_max_diff():
    g = _gt(n=400)
    e = scoring.Traj(t=g.t[::2] + 0.002, p=g.p[::2], R=g.R[::2])     # 100 Hz, 2 ms late
    ref_s, est_s = scoring.associate(g, e, max_diff=0.01)
    assert len(ref_s.t) == len(e.t) == 200
    assert np.allclose(ref_s.t, g.t[::2])
    sparse = scoring.Traj(t=g.t[::10] + 0.02, p=g.p[::10], R=g.R[::10])   # 20 Hz, 20 ms off a 5 ms grid
    assert len(scoring.associate(g, sparse, max_diff=0.01)[0].t) == 40          # lands on other samples
    with pytest.raises(ValueError):
        scoring.associate(g, scoring.Traj(t=g.t + 100.0, p=g.p, R=g.R), max_diff=0.01)


# ---------- RPE ----------

def test_rpe_linear_drift_exact():
    g = _gt(rotate=False)
    v = 0.2   # m/s along x, orientation identity, so body and world frames agree
    e = scoring.Traj(t=g.t, p=g.p + np.column_stack([(g.t - T0) * v, 0 * g.t, 0 * g.t]), R=g.R)
    r = scoring.score(g, e, align="none", rpe_deltas=(1, 200))
    assert r["rpe"]["1"]["rmse"] == pytest.approx(v * DT)
    assert r["rpe"]["200"]["rmse"] == pytest.approx(v * DT * 200)
    assert r["rpe"]["200"]["n"] == (len(g.t) - 1) // 200


def test_rpe_all_pairs_count():
    g = _gt(n=1000)
    r = scoring.rpe(g, g, delta=10, all_pairs=True)
    assert len(r) == 990


# ---------- phases ----------

def _events(t0_rel_fail=15.0, drops=((5.0, 7.0),)):
    return {"t0_ns": int(round(T0 * 1e9)), "healthy_end_s": 3.0,
            "dropouts_s": [list(d) for d in drops], "failure_at_s": t0_rel_fail,
            "end_s": t0_rel_fail + 5.0}


def test_phase_split_dropout_and_blind():
    g = _gt(n=4000)                               # 20 s
    s = g.t - T0
    err = np.zeros((len(s), 3))
    in_drop = (s >= 5.0) & (s < 7.0)
    err[in_drop, 1] = 0.5
    blind = s >= 15.0
    err[blind, 0] = 0.2 * (s[blind] - 15.0)       # 1 m after 5 s
    e = scoring.Traj(t=g.t, p=g.p + err, R=g.R)
    r = scoring.score(g, e, align="none", events=_events())
    ph = r["phases"]
    assert ph["healthy"]["rmse"] == pytest.approx(0, abs=1e-12)
    assert ph["dropouts"][0]["rmse"] == pytest.approx(0.5)
    assert ph["blind"]["end_error"] == pytest.approx(1.0, abs=0.002)
    assert ph["blind"]["growth"] == pytest.approx(1.0, abs=0.002)
    assert ph["blind"]["window_s"] == [15.0, 20.0]


def test_waypoint_proxies_every_n_seconds():
    g = _gt(n=4001)                               # 0 .. 20 s
    e = scoring.Traj(t=g.t, p=g.p + [0.3, 0, 0], R=g.R)
    r = scoring.score(g, e, align="none", waypoint_every_s=5.0)
    wp = r["waypoints_proxy"]
    assert [w["t_rel_s"] for w in wp["points"]] == [0.0, 5.0, 10.0, 15.0, 20.0]
    assert wp["rmse"] == pytest.approx(0.3)


# ---------- files and CLI ----------

def _write_tum(path, tr):
    q = scoring.matrices_to_quat_xyzw(tr.R)
    with open(path, "w") as f:
        for t, p, qq in zip(tr.t, tr.p, q):
            f.write("%.9f %.6f %.6f %.6f %.7f %.7f %.7f %.7f\n" % (t, *p, *qq))


def test_read_tum_sorts_and_drops_duplicates(tmp_path):
    g = _gt(n=50)
    _write_tum(tmp_path / "a.txt", g)
    lines = (tmp_path / "a.txt").read_text().splitlines(True)
    lines = lines[:10] + [lines[9]] + [lines[11], lines[10]] + lines[12:]   # duplicate + swap
    (tmp_path / "b.txt").write_text("".join(lines))
    tr, info = scoring.read_tum(tmp_path / "b.txt")
    assert len(tr.t) == 50 and np.all(np.diff(tr.t) > 0)
    assert info["duplicates_dropped"] == 1 and info["was_unsorted"]


def test_cli_end_to_end(tmp_path, capsys):
    g = _gt(n=2000)
    _write_tum(tmp_path / "gt.txt", g)
    e = scoring.Traj(t=g.t, p=g.p + [0.1, 0, 0], R=g.R)
    _write_tum(tmp_path / "est.txt", e)
    (tmp_path / "ev.json").write_text(json.dumps(_events(t0_rel_fail=4.0, drops=((1.0, 3.0),))))
    out = tmp_path / "score.json"
    assert scoring.main(["--gt", str(tmp_path / "gt.txt"), "--est", str(tmp_path / "est.txt"),
                         "--events", str(tmp_path / "ev.json"), "--align", "none", "--json", str(out)]) == 0
    r = json.loads(out.read_text())
    assert r["ape"]["rmse"] == pytest.approx(0.1, abs=1e-5)
    assert "blind" in r["phases"]
    assert "ATE" in capsys.readouterr().out

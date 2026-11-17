"""Q6 drag go/no-go tool: recovers a known drag constant on SYNTHETIC data and applies the rule."""

import importlib.util
import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("drag_fit", os.path.join(ROOT, "tools", "drag_fit.py"))
drag_fit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drag_fit)


@pytest.fixture(scope="module")
def with_drag(tmp_path_factory):
    return drag_fit.synth_sequence(str(tmp_path_factory.mktemp("drag")), k=0.3, seconds=90.0, seed=1)


def test_recovers_k_and_says_go(with_drag):
    res = drag_fit.analyse(drag_fit.load(with_drag))
    assert res["thrust_axis"] == "x"
    assert set(res["axes"]) == {"y", "z"}
    for a in res["axes"].values():
        assert a["k_full"] == pytest.approx(0.3, rel=0.05)
        assert a["k_diff_velocity"] == pytest.approx(0.3, rel=0.05)
        assert a["pass"]
    assert res["decision"] == "GO"
    assert res["bias_removed"] and res["velocity_source"].startswith("ground-truth velocity")


def test_no_drag_says_no_go(tmp_path):
    seq = drag_fit.synth_sequence(str(tmp_path), k=0.0, seconds=90.0, seed=2)
    res = drag_fit.analyse(drag_fit.load(seq))
    assert res["decision"] == "NO-GO"
    for a in res["axes"].values():
        assert abs(a["k_full"]) < 0.05


def test_other_settings_are_not_a_decision(with_drag):
    res = drag_fit.analyse(drag_fit.load(with_drag), win_s=0.5)
    assert res["decision"].startswith("n/a")


def test_save_and_render(with_drag, tmp_path):
    res = drag_fit.analyse(drag_fit.load(with_drag))
    clean = drag_fit.save(res, "SYNTH", out_dir=str(tmp_path))
    assert json.loads((tmp_path / "SYNTH.json").read_text())["decision"] == "GO"
    assert (tmp_path / "SYNTH.svg").read_text().startswith("<svg")
    md = drag_fit.render(out_dir=str(tmp_path), md_path=str(tmp_path / "DRAG.md"))
    text = open(md, encoding="utf-8").read()
    assert "| SYNTH |" in text and "GO" in text
    assert clean["rule"]["min_r2_test"] == 0.5


def test_longest_rest_end_and_exploratory_flag(with_drag):
    import numpy as np
    t = np.arange(0, 60, 0.005)
    v = np.zeros((len(t), 3))
    v[t < 10, 0] = 0.5                  # carried
    v[(t >= 10) & (t < 12), 0] = 0.0    # short rest
    v[(t >= 12) & (t < 20), 0] = 0.4
    v[t >= 35, 0] = 1.0                 # rest 20 .. 35 s, then flight
    assert drag_fit.longest_rest_end(t, v) == pytest.approx(35.0, abs=0.01)
    res = drag_fit.analyse(drag_fit.load(with_drag, after_rest=True))
    assert res["decision"].startswith("n/a (EXPLORATORY")


# ---------- rule v2 (pre-registered 16 Nov 2026; decision data: Vicon Room 1) ----------

def test_v2_rule_is_frozen():
    r = drag_fit.RULE_V2
    assert (r["k_fixed"], r["min_r2"], r["max_k_rel_dev"], r["min_pass"], r["smooth_s"]) == (0.20, 0.5, 0.3, 2, 1.0)
    assert r["decision_sequences"] == ["V1_01_easy", "V1_02_medium", "V1_03_difficult"]


def test_v2_perp_axes_are_orthonormal_and_perpendicular():
    import numpy as np
    for u in ([0.94, -0.01, -0.34], [0.0, 0.0, 1.0], [0.0, 0.0, -9.8], [1.0, 2.0, 3.0]):
        u = np.asarray(u) / np.linalg.norm(u)
        a, b = drag_fit.perp_axes(u)
        M = np.array([u, a, b])
        assert np.allclose(M @ M.T, np.eye(3), atol=1e-12)


@pytest.mark.parametrize("k, passes", [(0.2, True), (0.0, False), (0.4, False)])
def test_v2_passes_only_near_the_fixed_k(tmp_path, k, passes):
    seq = drag_fit.synth_sequence(str(tmp_path / "s"), k=k, seconds=90.0, seed=2, vib=0.3)
    res = drag_fit.analyse_v2(drag_fit.load(seq, use_bias=True, after_rest=True))
    assert res["pass"] is passes, {n: (a["k_free"], a["r2_fixed_k"]) for n, a in res["axes"].items()}
    if k:
        for a in res["axes"].values():
            assert a["k_free"] == pytest.approx(k, rel=0.08)


def test_v2_decision_needs_two_of_three_decision_sequences():
    ok, bad = {"pass": True}, {"pass": False}
    names = drag_fit.RULE_V2["decision_sequences"]
    assert drag_fit.decide_v2({names[0]: ok, names[1]: ok}).startswith("INCOMPLETE")
    assert drag_fit.decide_v2({names[0]: ok, names[1]: ok, names[2]: bad}) == "GO"
    assert drag_fit.decide_v2({names[0]: ok, names[1]: bad, names[2]: bad}) == "NO-GO"
    assert drag_fit.decide_v2({"MH_01_easy": ok, names[0]: bad, names[1]: bad, names[2]: ok}) == "NO-GO"

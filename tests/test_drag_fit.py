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

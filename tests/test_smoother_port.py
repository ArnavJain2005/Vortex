"""Step 6: the smoother (SMOOTH_ON) in pathfinder.py against the reference (vortex/core/witness.py), on
SYNTHETIC files: storage, merging under a small cap, row corrections. Also the switch-off path."""

import importlib.util
import sys
from pathlib import Path

import pytest

from vortex.core import witness as wx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_core_equivalence as tce  # noqa: E402
from test_core_equivalence import _compare, _write_rows  # noqa: E402
from test_strapdown import _move_rest_move  # noqa: E402


def _load_pf():
    spec = importlib.util.spec_from_file_location("vortex_pf_smooth", ROOT / "pathfinder.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pf = _load_pf()


def _rows(seed=7, gap=True):
    rows, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.002, acc_noise=0.02, seed=seed)
    if gap:
        rows = [r for i, r in enumerate(rows) if not 5200 < i < 5300]      # a 0.5 s dropout after the anchor
    return rows


@pytest.mark.parametrize("cap", [1024, 16, 15])
def test_smoother_reference_and_pathfinder_agree(tmp_path, monkeypatch, cap):
    src = _write_rows(tmp_path / "imu.csv", _rows())
    for mod in (wx, pf):
        monkeypatch.setattr(mod, "SMOOTH_ON", True)
        monkeypatch.setattr(mod, "SMOOTH_MAX_BLOCKS", cap)
    monkeypatch.setattr(tce, "main", pf)
    _compare(src, tmp_path, monkeypatch, reference=wx.estimate_file)
    assert pf.LAST["smooth_blocks"] <= cap


def test_smoother_with_learned_envelope_agrees(tmp_path, monkeypatch):
    src = _write_rows(tmp_path / "imu.csv", _rows(seed=8))
    for mod in (wx, pf):
        monkeypatch.setattr(mod, "SMOOTH_ON", True)
        monkeypatch.setattr(mod, "LEARN_ON", True)
    monkeypatch.setattr(tce, "main", pf)
    _compare(src, tmp_path, monkeypatch, reference=wx.estimate_file)


def test_smoother_changes_the_output_and_merging_keeps_it_close(tmp_path, monkeypatch):
    src = _write_rows(tmp_path / "imu.csv", _rows())
    outs = {}
    for name, on, cap in (("off", False, 1024), ("on", True, 1024), ("cap16", True, 16)):
        monkeypatch.setattr(pf, "SMOOTH_ON", on)
        monkeypatch.setattr(pf, "SMOOTH_MAX_BLOCKS", cap)
        pf.run(str(src), str(tmp_path / (name + ".txt")))
        outs[name] = [[float(x) for x in l.split()[1:4]] for l in (tmp_path / (name + ".txt")).read_text().splitlines()]
    d_on = max(abs(a - b) for ra, rb in zip(outs["off"], outs["on"]) for a, b in zip(ra, rb))
    d_cap = max(abs(a - b) for ra, rb in zip(outs["on"], outs["cap16"]) for a, b in zip(ra, rb))
    assert d_on > 1e-3                      # the smoother does something
    assert d_cap < d_on                     # merged blocks approximate the full store
    assert outs["on"][-1] == outs["off"][-1]   # the last row (after the last tick) keeps the filtered pose

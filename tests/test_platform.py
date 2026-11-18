"""Step 7: platform detection (vortex/core/platform.py) and the hand-held envelope (PLATFORM_ON), in the
reference, pathfinder.py and tools/pathfinder_lab.py. All SYNTHETIC."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from vortex.core import platform as pl
from vortex.core import strapdown as sd
from vortex.core import witness as wx
from vortex.data import euroc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_core_equivalence as tce  # noqa: E402
from test_core_equivalence import _compare, _write_rows  # noqa: E402
from test_main import MESSY  # noqa: E402
from test_strapdown import _move_rest_move  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pf = _load("vortex_pf_platform", ROOT / "pathfinder.py")
lab = _load("vortex_lab_platform", ROOT / "tools" / "pathfinder_lab.py")
SHARED = ("PLATFORM_ON", "PLAT_WIN_NS", "PLAT_Q", "PLAT_HF", "PLAT_MIN_TERMS", "HH_V2_SIGMA_H", "HH_V2_SIGMA_V",
          "HH_V2P_SIGMA_H", "HH_V2P_SIGMA_V", "HH_V2P_TAU")


def _handheld_rows(seed=3):
    """Smooth, low-frequency motion: hand-held."""
    rows, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.002, acc_noise=0.02, seed=seed)
    return rows


def _rotor_rows(seed=4):
    """The same motion plus accelerometer vibration near Nyquist (rotor-like, 2 m/s^2): multirotor."""
    rng = np.random.default_rng(seed)
    out = []
    for i, (t, v) in enumerate(_handheld_rows(seed)):
        s = 2.0 * (1.0 if i % 2 else -1.0) * (0.8 + 0.4 * rng.random())
        out.append((t, v[:3] + (v[3] + s, v[4] - s, v[5] + 0.5 * s)))
    return out


def _stat_pf(mod, src):
    return mod._plat_stat(str(src))


def _stat_ref(src):
    return pl.hf_stat(sd.rows_from_raw(euroc.read_imu_csv(str(src))))


def test_constants_match_the_reference_and_are_off():
    assert pl.PLATFORM_ON is False
    for mod in (pf, lab):
        for n in SHARED:
            assert getattr(mod, n) == getattr(pl, n), n


@pytest.mark.parametrize("kind", ["handheld", "rotor"])
def test_detector_classifies_and_matches_the_reference(tmp_path, kind):
    rows = _handheld_rows() if kind == "handheld" else _rotor_rows()
    src = _write_rows(tmp_path / "imu.csv", rows)
    st = _stat_ref(src)
    assert st == _stat_pf(pf, src) == _stat_pf(lab, src)
    assert pl.is_handheld(st) is (kind == "handheld")
    assert (st < 0.05) if kind == "handheld" else (st > 2.0), st


def test_detector_row_rules_match_the_reference(tmp_path):
    """Bad timestamps, NaN, all-zero accelerometer (the blind window) and a hole end the difference chain
    in both implementations; a messy file with BOM, CRLF and blank lines; an empty file."""
    rows = _rotor_rows(seed=6)
    nan = float("nan")
    rows[700:705] = [(t, (nan,) * 6) for t, _ in rows[700:705]]
    rows[1500] = (None, rows[1500][1])
    rows[-1000:] = [(t, v[:3] + (0.0, 0.0, 0.0)) for t, v in rows[-1000:]]
    rows = rows[:3000] + rows[3300:]
    src = _write_rows(tmp_path / "imu.csv", rows)
    st = _stat_ref(src)
    assert st is not None and st == _stat_pf(pf, src) == _stat_pf(lab, src)
    messy = tmp_path / "messy.csv"
    messy.write_bytes(MESSY)
    assert _stat_pf(pf, messy) is None and _stat_pf(lab, messy) is None    # too few rows: no window counts
    empty = tmp_path / "empty.csv"
    empty.write_bytes(b"#timestamp [ns],w_x,w_y,w_z,a_x,a_y,a_z\n")
    assert _stat_pf(pf, empty) is None and pl.is_handheld(None) is False


@pytest.mark.parametrize("which", ["pathfinder", "lab"])
def test_handheld_envelope_matches_the_reference(tmp_path, monkeypatch, which):
    mod = pf if which == "pathfinder" else lab
    src = _write_rows(tmp_path / "imu.csv", _handheld_rows(seed=9))
    monkeypatch.setattr(pl, "PLATFORM_ON", True)
    monkeypatch.setattr(mod, "PLATFORM_ON", True)
    monkeypatch.setattr(tce, "main", mod)
    _compare(src, tmp_path, monkeypatch, reference=wx.estimate_file)
    assert wx.LAST_HH[0] is True
    assert mod.LAST["platform"] is not None and mod.LAST["platform"] < mod.PLAT_HF


def test_switch_equals_the_envelope_set_by_hand(tmp_path, monkeypatch):
    """On a hand-held file PLATFORM_ON is exactly the tuned constants set globally (how they were tuned)."""
    src = _write_rows(tmp_path / "imu.csv", _handheld_rows(seed=10))
    monkeypatch.setattr(pf, "PLATFORM_ON", True)
    pf.run(str(src), str(tmp_path / "on.txt"))
    monkeypatch.setattr(pf, "PLATFORM_ON", False)
    for a, b in (("V2_SIGMA_H", "HH_V2_SIGMA_H"), ("V2_SIGMA_V", "HH_V2_SIGMA_V"), ("V2P_SIGMA_H", "HH_V2P_SIGMA_H"),
                 ("V2P_SIGMA_V", "HH_V2P_SIGMA_V"), ("V2P_TAU", "HH_V2P_TAU")):
        monkeypatch.setattr(pf, a, getattr(pf, b))
    pf.run(str(src), str(tmp_path / "set.txt"))
    assert (tmp_path / "on.txt").read_bytes() == (tmp_path / "set.txt").read_bytes()


def test_multirotor_output_unchanged_by_the_switch(tmp_path, monkeypatch):
    src = _write_rows(tmp_path / "imu.csv", _rotor_rows(seed=11))
    pf.run(str(src), str(tmp_path / "off.txt"))
    monkeypatch.setattr(pf, "PLATFORM_ON", True)
    pf.run(str(src), str(tmp_path / "on.txt"))
    assert pf.LAST["platform"] > pf.PLAT_HF
    assert (tmp_path / "off.txt").read_bytes() == (tmp_path / "on.txt").read_bytes()
    hand = _write_rows(tmp_path / "hand.csv", _handheld_rows(seed=12))
    pf.run(str(hand), str(tmp_path / "h_on.txt"))
    monkeypatch.setattr(pf, "PLATFORM_ON", False)
    pf.run(str(hand), str(tmp_path / "h_off.txt"))
    assert (tmp_path / "h_on.txt").read_bytes() != (tmp_path / "h_off.txt").read_bytes()

"""Rule G2's judge (tools/judge_stepG2.py) on SYNTHETIC result tables: the new conditions 7 and 10 can each fail on
their own, and the conditions shared with rule G still apply."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import judge_stepG2 as jg2  # noqa: E402

CLEAN = ["MH_01_easy", "MH_02_easy", "MH_03_medium", "MH_04_difficult", "MH_05_difficult", "V1_01_easy",
         "V1_02_medium", "V1_03_difficult"]


def _h(ape=5.0, scale=None, rpe=1.0, gap=5.0, blind=7.0):
    tab = {}
    for s in jg2.SEQS:
        for rd in ("a", "b"):
            for seed in jg2.SEEDS:
                n = "%s_%s_s%d" % (s, rd, seed)
                f = scale(s, rd) if scale else 1.0
                tab[n] = {"sequence": n, "reading": rd, "seed": seed, "contract": "PASS", "ape_se3_rmse": ape * f,
                          "rpe200_rmse": rpe, "gap_rmse_mean": gap, "blind_rmse": blind}
    return tab


def _c(ape=3.6):
    return {n: {"sequence": n, "contract": "PASS", "ate_se3_rmse": ape} for n in CLEAN}


def _run(on=None, off_rev=None, on_rev=None, gate="PASS", off=None, c_on=None):
    return jg2.judge(_h(ape=3.7), off or _h(), on or _h(ape=4.0, rpe=0.9), off_rev or _h(ape=4.5),
                     on_rev or _h(ape=4.4), _c(), c_on or _c(), None, None, None, None, gate)


def test_all_pass(capsys):
    assert _run()                                     # gain 1.0 m against 0.1 m on the reversed outputs
    out = capsys.readouterr().out
    assert "weaker evidence" in out and "ships ON" in out


def test_did_null_fails_when_reversed_gain_is_as_large():
    assert not _run(off_rev=_h(ape=5.0), on_rev=_h(ape=4.0))    # 1.0 vs 1.0: the gain does not need time order


def test_did_null_passes_even_if_on_loses_to_its_own_reversal():
    # rule G's condition 7 (on < on reversed) would fail here; G2 asks about the gain, not the level
    assert _run(on=_h(ape=4.0, rpe=0.9), on_rev=_h(ape=3.9), off_rev=_h(ape=4.2))


def test_reading_b_sequence_harm_fails():
    def sc(s, rd):
        if rd == "a":
            return 0.6
        return 1.03 if s == "V1_03_difficult" else 1.0
    assert not _run(on=_h(scale=sc))


def test_reading_b_small_harm_passes():
    def sc(s, rd):
        if rd == "a":
            return 0.6
        return 1.005 if s == "V1_03_difficult" else 1.0
    assert _run(on=_h(scale=sc))


def test_shared_conditions_still_apply():
    assert not _run(on=_h(ape=4.95))                  # condition 1
    assert not _run(gate="FAIL")                      # condition 9
    assert not _run(c_on=_c(ape=3.62))                # condition 5


def test_wrong_seeds_refused():
    off = {k.replace("_s16", "_s10"): v for k, v in _h().items()}
    with pytest.raises(AssertionError):
        _run(off=off)

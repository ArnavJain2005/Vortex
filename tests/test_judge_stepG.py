"""Rule G's judge (tools/judge_stepG.py) on SYNTHETIC result tables: each condition can fail on its own."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import judge_stepG as jg  # noqa: E402

CLEAN = ["MH_01_easy", "MH_02_easy", "MH_03_medium", "MH_04_difficult", "MH_05_difficult", "V1_01_easy",
         "V1_02_medium", "V1_03_difficult"]


def _h(ape=5.0, scale=None, rpe=1.0, gap=5.0, blind=7.0):
    tab = {}
    for s in jg.SEQS:
        for rd in ("a", "b"):
            for seed in jg.SEEDS:
                n = "%s_%s_s%d" % (s, rd, seed)
                f = scale(s, rd) if scale else 1.0
                tab[n] = {"sequence": n, "reading": rd, "seed": seed, "contract": "PASS", "ape_se3_rmse": ape * f,
                          "rpe200_rmse": rpe, "gap_rmse_mean": gap, "blind_rmse": blind}
    return tab


def _c(ape=3.6):
    return {n: {"sequence": n, "contract": "PASS", "ate_se3_rmse": ape} for n in CLEAN}


def _run(on=None, rev=None, c_on=None, gate="PASS", off=None):
    off = off or _h()
    return jg.judge(_h(ape=3.7), off, on or _h(ape=4.0, rpe=0.9), rev or _h(ape=4.5), _c(), c_on or _c(),
                    None, None, None, None, gate)


def test_all_pass(capsys):
    assert _run()
    assert "motion recovered" in capsys.readouterr().out


def test_small_gain_fails():
    assert not _run(on=_h(ape=4.95))


def test_sequence_consistency_fails():
    # big gain on 3 sequences only, slight loss on the other 3
    def sc(s, rd):
        return 0.5 if s in jg.SEQS[:3] else 1.01
    assert not _run(on=_h(scale=sc))


def test_reading_harm_fails():
    def sc(s, rd):
        return 0.6 if rd == "a" else 1.02
    assert not _run(on=_h(scale=sc))


def test_blind_harm_fails():
    assert not _run(on=_h(ape=4.0, blind=7.2))


def test_clean_harm_fails():
    assert not _run(c_on=_c(ape=3.62))


def test_reversed_null_fails():
    assert not _run(rev=_h(ape=3.9))


def test_gate_and_contract():
    assert not _run(gate="FAIL")
    bad = _h(ape=4.0)
    bad[next(iter(bad))]["contract"] = "FAIL"
    assert not _run(on=bad)


def test_wrong_seeds_refused():
    off = _h()
    k = next(iter(off))
    off[k.replace("_s10", "_s4")] = off.pop(k)
    with pytest.raises(AssertionError):
        _run(off=off)


def test_better_aligned_wording(capsys):
    assert _run(on=_h(ape=4.0, rpe=1.1))
    assert "better aligned APE" in capsys.readouterr().out

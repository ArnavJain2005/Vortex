"""Rule H's judge (tools/judge_stepH.py) on SYNTHETIC result tables: each condition can fail on its own."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import judge_stepH as jh  # noqa: E402

CLEAN = ["MH_01_easy", "MH_02_easy", "MH_03_medium", "MH_04_difficult", "MH_05_difficult", "V1_01_easy",
         "V1_02_medium", "V1_03_difficult"]
ROOMS = ["dataset-room%d_512_16" % i for i in (1, 2, 3, 4)]


def _h(ape=4.0, blind=3.4, gap=3.5, scale=None):
    tab = {}
    for s in jh.SEQS:
        for rd in ("a", "b"):
            for seed in jh.SEEDS:
                n = "%s_%s_s%d" % (s, rd, seed)
                f = scale(s, rd) if scale else 1.0
                tab[n] = {"sequence": n, "reading": rd, "seed": seed, "contract": "PASS", "ape_se3_rmse": ape,
                          "rpe200_rmse": 0.6, "gap_rmse_mean": gap, "blind_rmse": blind * f, "blind_growth": 0.5}
    return tab


def _t(ape=2.2, blind=1.0):
    return {"%s_%s_s%d" % (r, rd, s): {"sequence": "%s_%s_s%d" % (r, rd, s), "contract": "PASS", "ape_se3_rmse": ape,
                                       "blind_rmse": blind}
            for r in jh.T_ROOMS for rd in ("a", "b") for s in jh.SEEDS}


def _c(names, ape):
    return {n: {"sequence": n, "contract": "PASS", "ate_se3_rmse": ape} for n in names}


def _run(on=None, off=None, t_on=None, c_on=None, ct_on=None, gate="PASS"):
    return jh.judge(_h(blind=2.5), off or _h(), on or _h(blind=2.6), _c(CLEAN, 3.6), c_on or _c(CLEAN, 3.6),
                    _t(), t_on or _t(blind=0.7), _c(ROOMS, 0.83), ct_on or _c(ROOMS, 0.83), gate)


def test_all_pass(capsys):
    assert _run()
    out = capsys.readouterr().out
    assert "ships ON" in out and "trust policy" in out


def test_blind_gain_too_small():
    assert not _run(on=_h(blind=3.35))                       # -1.5 %


def test_sequence_consistency():
    def sc(s, rd):                                           # 3 of 6 sequences worse
        return 1.4 if s in ("MH_03_medium", "MH_04_difficult", "MH_05_difficult") else 0.5
    assert not _run(on=_h(blind=3.4, scale=sc))


def test_one_reading_worse():
    def sc(s, rd):
        return 0.5 if rd == "a" else 1.02
    assert not _run(on=_h(blind=3.4, scale=sc))


def test_ape_gap_tumvi_clean_and_gate_each_fail():
    assert not _run(on=_h(ape=4.03, blind=2.6))              # 4: APE +0.75 %
    assert not _run(on=_h(gap=3.6, blind=2.6))               # 5: gap +2.9 %
    assert not _run(t_on=_t(blind=1.03))                     # 6: T blind +3 %
    assert not _run(t_on=_t(ape=2.22, blind=0.7))            # 6: T APE +0.9 %
    assert not _run(c_on=_c(CLEAN, 3.62))                    # 7: clean EuRoC
    assert not _run(ct_on=_c(ROOMS, 0.84))                   # 7: clean TUM-VI
    assert not _run(gate="FAIL")                             # 8


def test_contract_fail():
    bad = _h(blind=2.6)
    next(iter(bad.values()))["contract"] = "FAIL"
    assert not _run(on=bad)


def test_wrong_seeds_refused():
    off = {k.replace("_s13", "_s10"): v for k, v in _h().items()}
    with pytest.raises(AssertionError):
        _run(off=off)


def _reseed(tab):
    out = {}
    for k, v in tab.items():
        n = k.replace("_s13", "_s22").replace("_s14", "_s23").replace("_s15", "_s24")
        out[n] = dict(v, sequence=n, seed=int(n.rsplit("_s", 1)[1]))
    return out


def test_rule_hp_takes_seeds_22_24_only(capsys):
    hp = (_reseed(_h(blind=2.5)), _reseed(_h()), _reseed(_h(blind=2.6)), _c(CLEAN, 3.6), _c(CLEAN, 3.6),
          _reseed(_t()), _reseed(_t(blind=0.7)), _c(ROOMS, 0.83), _c(ROOMS, 0.83), "PASS")
    assert jh.judge(*hp, seeds=jh.SEEDS_HP, switch="BLIND_ON + BLIND_DEAD_ONLY")
    assert "BLIND_ON + BLIND_DEAD_ONLY ships ON" in capsys.readouterr().out
    with pytest.raises(AssertionError):
        jh.judge(*hp)                                        # rule H's seeds refuse the H' copies
    with pytest.raises(AssertionError):
        jh.judge(_h(blind=2.5), _h(), _h(blind=2.6), _c(CLEAN, 3.6), _c(CLEAN, 3.6), _t(), _t(blind=0.7),
                 _c(ROOMS, 0.83), _c(ROOMS, 0.83), "PASS", seeds=jh.SEEDS_HP)   # and H' refuses seeds 13-15

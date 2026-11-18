"""Apply the Step L1 decision rule (Docs/TRACK3_PLAN.md, Step L1; committed before the held-out copies existed)
to the result tags. Reads Docs/results/<tag>.json; prints each condition and the verdict per arm.

Held-out set H7: MH_03..05, V1_01..03 x readings a, b x seeds 7, 8, 9 (36 official-script copies made after
the rule commit). Clean set C: MH_01..05, V1_01..03.

Objective per copy (as in tools/shrink_tune.py): 60 x (30 APE/APE_f + 20 blind/blind_f + 10 gap/gap_f) /
(sum of the weights present), x_f = the never-moving floor's value on the same copy; the floor scores 60.

    python tools/judge_stepL1.py --floor stepL1-H-floor --off stepL1-H-off
        --lo stepL1-H-lo --lo-rev stepL1-H-lo-rev --hi stepL1-H-hi --hi-rev stepL1-H-hi-rev
        --c-off stepL1-C-off --c-lo stepL1-C-lo --c-hi stepL1-C-hi
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEDS = (7, 8, 9)
SEQS = ("MH_03_medium", "MH_04_difficult", "MH_05_difficult", "V1_01_easy", "V1_02_medium", "V1_03_difficult")
W = (("ape_se3_rmse", 30.0), ("blind_rmse", 20.0), ("gap_rmse_mean", 10.0))
GAIN, SEQ_MIN, NO_HARM = 0.02, 5, 0.005


def load(tag):
    with open(os.path.join(ROOT, "Docs", "results", tag + ".json"), encoding="utf-8") as f:
        return {r["sequence"]: r for r in json.load(f)["results"]}


def objective(r, f):
    num = den = 0.0
    for k, w in W:
        if r.get(k) is not None and f.get(k):
            num += w * r[k] / f[k]
            den += w
    return 60.0 * num / den


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs)


def arm(name, reading, floor, off, on, rev, other_off, other_on, c_off, c_on, clean_gate):
    names = [n for n in floor if n.split("_")[-2] == reading]
    others = [n for n in floor if n.split("_")[-2] != reading]
    assert len(names) == 18 and all(int(n.split("_s")[-1]) in SEEDS for n in floor), "H7 must be the seed 7-9 copies"
    ob = lambda tab, ns: mean(objective(tab[n], floor[n]) for n in ns)  # noqa: E731
    checks = []
    o_off, o_on, o_rev = ob(off, names), ob(on, names), ob(rev, names)
    d = (o_on - o_off) / o_off
    checks.append(("1 reading %s mean objective improves >= 2 %%" % reading,
                   "%.2f -> %.2f (%+.2f %%)" % (o_off, o_on, 100 * d), d <= -GAIN))
    better = 0
    for s in SEQS:
        ns = [n for n in names if n.startswith(s)]
        better += ob(on, ns) < ob(off, ns)
    checks.append(("2 >= 5 of 6 sequences improve", "%d of 6" % better, better >= SEQ_MIN))
    checks.append(("3 beats its own reversed output (null floor)", "%.2f vs %.2f reversed" % (o_on, o_rev),
                   o_on < o_rev))
    if other_off is not None:
        a, b = ob(other_off, others), ob(other_on, others)
        checks.append(("4 other reading not worse by > 0.5 %", "%.2f -> %.2f (%+.2f %%)" % (a, b, 100 * (b - a) / a),
                       (b - a) / a <= NO_HARM))
    ca = mean(r["ate_se3_rmse"] for r in c_off.values())
    cb = mean(r["ate_se3_rmse"] for r in c_on.values())
    dc = (cb - ca) / ca
    checks.append(("5 clean mean APE " + ("not worse by > 0.5 %" if clean_gate else "(reported, not a gate)"),
                   "%.4f -> %.4f m (%+.2f %%)" % (ca, cb, 100 * dc), dc <= NO_HARM if clean_gate else True))
    ok = all(r.get("contract") == "PASS" and "error" not in r
             for tab in (off, on, rev, c_on) for r in tab.values())
    checks.append(("6 contract PASS on every run", "", ok))
    print("%s (reading %s)" % (name, reading))
    for c, v, p in checks:
        print("  %-48s %-36s %s" % (c, v, "pass" if p else "FAIL"))
    for k, lab in W:
        print("    reported: mean %-14s off %.3f  on %.3f  reversed %.3f  floor %.3f" % (
            k, mean(off[n][k] for n in names if off[n].get(k) is not None),
            mean(on[n][k] for n in names if on[n].get(k) is not None),
            mean(rev[n][k] for n in names if rev[n].get(k) is not None),
            mean(floor[n][k] for n in names if floor[n].get(k) is not None)))
    verdict = all(p for _, _, p in checks)
    print("  VERDICT: %s" % ("ships ON" if verdict else "ships OFF"))
    return verdict


def main(argv):
    get = lambda k: argv[argv.index(k) + 1]  # noqa: E731
    floor, off = load(get("--floor")), load(get("--off"))
    lo, lo_rev, hi, hi_rev = load(get("--lo")), load(get("--lo-rev")), load(get("--hi")), load(get("--hi-rev"))
    c_off, c_lo, c_hi = load(get("--c-off")), load(get("--c-lo")), load(get("--c-hi"))
    assert len(floor) == len(off) == len(lo) == len(hi) == len(lo_rev) == len(hi_rev) == 36
    assert len(c_off) == len(c_lo) == len(c_hi) == 8
    lo_ok = arm("Arm LO: SHRINK_ON, alpha_lo 0.10, alpha_hi 1.0 (judged against off)", "a",
                floor, off, lo, lo_rev, off, lo, c_off, c_lo, clean_gate=True)
    base, c_base = (lo, c_lo) if lo_ok else (off, c_off)
    hi_ok = arm("Arm HI: alpha_hi 0.20 (judged against arm LO's decided state)", "b",
                floor, base, hi, hi_rev, base, hi, c_base, c_hi, clean_gate=False)
    print("SHIPPED: SHRINK_ON = %s, SHRINK_ALPHA_LO = %s, SHRINK_ALPHA_HI = %s" % (
        lo_ok or hi_ok, "0.10" if lo_ok else "1.0", "0.20" if hi_ok else "1.0"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

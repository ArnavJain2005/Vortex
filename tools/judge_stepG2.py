"""Apply rule G2 (Step L2 re-judge, TILT_ON; Docs/TRACK3_PLAN.md, Step L2, rule G2) to the result tags.

WRITTEN AFTER SEEING RULE G'S RESULT; WEAKER EVIDENCE; SAME 6 FLIGHTS. Committed, with every TILT_* constant
unchanged since rule G (5fd288c), BEFORE the seed 16-18 copies exist. Seeds 16-18 are the last reserve.

Base: `main` with the Step 6 smoother shipped ON (merged into the L2 branch); rule G judged L2 without it.
Held-out H: MH_03..05, V1_01..03 x readings a, b x seeds 16, 17, 18 (36 copies). TUM-VI block T: room3, room4
x a, b x seeds 16-18 (12 copies). Clean C: MH_01..05, V1_01..03; clean TUM-VI CT: room1..4.

Conditions 1-6, 8, 9: identical to rule G (tools/judge_stepG.py), same thresholds. Condition 7 is replaced:
  7. difference-in-differences null: the gain mean_H(APE off - APE on) must exceed the same gain measured on
     both outputs reversed in time, mean_H(APE off-reversed - APE on-reversed). Asks whether L2's gain needs the
     right time order (the question the null exists for); the reversed outputs keep each estimate's spread.
New:
 10. no reading-b sequence worse by more than 2 % (mean of its 3 seeds, on against off): where the switch fires
     on reading b (V1_03 b fired under rule G), it must not hurt.

    python tools/judge_stepG2.py --floor stepG2-H-floor --off stepG2-H-off --on stepG2-H-on
        --off-rev stepG2-H-off-rev --on-rev stepG2-H-on-rev --c-off stepG2-C-off --c-on stepG2-C-on
        --t-off ../tumvi/stepG2-T-off --t-on ../tumvi/stepG2-T-on --ct-off ../tumvi/stepG2-CT-off
        --ct-on ../tumvi/stepG2-CT-on --gate PASS
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from judge_stepG import (CLEAN, GAIN, GAP_BLIND, READING, SEQ_MIN, SEQS, T_ROOMS, TUMVI, apem, load,  # noqa: E402
                         mean)

SEEDS = (16, 17, 18)
READING_B_SEQ = 0.02


def judge(floor, off, on, off_rev, on_rev, c_off, c_on, t_off, t_on, ct_off, ct_on, gate):
    H = sorted(off)
    assert len(H) == 36 and set(H) == set(on) == set(off_rev) == set(on_rev) == set(floor), "H: 36 copies per tag"
    assert all(int(n.rsplit("_s", 1)[1]) in SEEDS for n in H), "H must be the seed 16-18 copies"
    assert all(any(n.startswith(s) for s in SEQS) for n in H)
    assert len(c_off) == len(c_on) == 8, "C: the 8 clean EuRoC sequences"
    rel = lambda a, b: (b - a) / a  # noqa: E731
    checks = []
    a0, a1 = apem(off), apem(on)
    checks.append(("1 mean APE over H improves >= 2 %", "%.3f -> %.3f m (%+.2f %%)" % (a0, a1, 100 * rel(a0, a1)),
                   rel(a0, a1) <= -GAIN))
    per = []
    for s in SEQS:
        ns = [n for n in H if n.startswith(s)]
        assert len(ns) == 6
        nb = [n for n in ns if off[n]["reading"] == "b"]
        per.append((s, apem(off, ns), apem(on, ns), apem(floor, ns), apem(off_rev, ns), apem(on_rev, ns),
                    apem(off, nb), apem(on, nb), mean(off, "rpe200_rmse", ns), mean(on, "rpe200_rmse", ns)))
    better = sum(1 for p in per if p[2] < p[1])
    checks.append(("2 paired gain > 0 on >= 4 of 6 sequences", "%d of 6" % better, better >= SEQ_MIN))
    for rd in ("a", "b"):
        ns = [n for n in H if off[n]["reading"] == rd]
        x0, x1 = apem(off, ns), apem(on, ns)
        checks.append(("3 reading %s mean APE not worse by > 1 %%" % rd,
                       "%.3f -> %.3f m (%+.2f %%)" % (x0, x1, 100 * rel(x0, x1)), rel(x0, x1) <= READING))
    for k, lab in (("gap_rmse_mean", "gap RMSE"), ("blind_rmse", "blind RMSE")):
        x0, x1 = mean(off, k), mean(on, k)
        checks.append(("4 mean %s over H not worse by > 2 %%" % lab,
                       "%.3f -> %.3f m (%+.2f %%)" % (x0, x1, 100 * rel(x0, x1)), rel(x0, x1) <= GAP_BLIND))
    x0, x1 = apem(c_off), apem(c_on)
    checks.append(("5 clean EuRoC mean APE not worse by > 0.5 %", "%.4f -> %.4f m (%+.3f %%)" % (
        x0, x1, 100 * rel(x0, x1)), rel(x0, x1) <= CLEAN))
    if ct_off is not None:
        x0, x1 = apem(ct_off), apem(ct_on)
        checks.append(("5 clean TUM-VI mean APE not worse by > 0.5 %", "%.4f -> %.4f m (%+.3f %%)" % (
            x0, x1, 100 * rel(x0, x1)), rel(x0, x1) <= CLEAN))
    if t_off is not None:
        assert len(t_off) == len(t_on) == 12 and all(any(n.startswith(r) for r in T_ROOMS) for n in t_off)
        assert all(int(n.rsplit("_s", 1)[1]) in SEEDS for n in t_off)
        x0, x1 = apem(t_off), apem(t_on)
        checks.append(("6 TUM-VI block mean APE not worse by > 1 %", "%.3f -> %.3f m (%+.2f %%)" % (
            x0, x1, 100 * rel(x0, x1)), rel(x0, x1) <= TUMVI))
    else:
        checks.append(("6 TUM-VI block", "not present", True))
    g_fwd = apem(off) - apem(on)
    g_rev = apem(off_rev) - apem(on_rev)
    checks.append(("7 gain exceeds the gain on reversed outputs", "%.3f vs %.3f m (reversed)" % (g_fwd, g_rev),
                   g_fwd > g_rev))
    tabs = [off, on, off_rev, on_rev, c_off, c_on] + [t for t in (t_off, t_on, ct_off, ct_on) if t is not None]
    ok = all(r.get("contract") == "PASS" and "error" not in r for t in tabs for r in t.values())
    checks.append(("8 contract PASS on every run", "%d runs" % sum(len(t) for t in tabs), ok))
    checks.append(("9 benchmark gate with TILT_ON", gate, gate == "PASS"))
    worst = max(per, key=lambda p: rel(p[6], p[7]))
    checks.append(("10 no reading-b sequence worse by > 2 %", "worst %s %+.2f %%" % (
        worst[0], 100 * rel(worst[6], worst[7])), all(rel(p[6], p[7]) <= READING_B_SEQ for p in per)))
    for c, v, p in checks:
        print("  %-46s %-38s %s" % (c, v, "pass" if p else "FAIL"))
    verdict = all(p for _, _, p in checks)
    print("\nPer sequence (mean of 6 copies: readings a, b x seeds 16-18; MH/V1 seeds re-use the same 6 flights)")
    print("| Sequence | APE off | APE on | gain % | floor | off reversed | on reversed | b off | b on | RPE 1 s off | RPE 1 s on |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    gains = []
    for s, o, n, f, orv, nrv, bo, bn, r0, r1 in per:
        g = 100 * (o - n) / o
        gains.append(g)
        print("| %s | %.3f | %.3f | %+.1f | %.3f | %.3f | %.3f | %.3f | %.3f | %.3f | %.3f |" % (
            s, o, n, g, f, orv, nrv, bo, bn, r0, r1))
    mg = sum(gains) / len(gains)
    sd = math.sqrt(sum((g - mg) ** 2 for g in gains) / (len(gains) - 1))
    r0, r1 = mean(off, "rpe200_rmse"), mean(on, "rpe200_rmse")
    print("Sequence-level paired gain: mean %+.1f %%, sd %.1f %% (n = 6). Floor over H: %.3f m. RPE 1 s %.3f -> %.3f."
          % (mg, sd, apem(floor), r0, r1))
    print("Rule G2 was written after seeing rule G's result: weaker evidence; same 6 flights.")
    if verdict:
        print("Wording: %s" % ("motion recovered (APE and RPE 1 s both better)" if r1 < r0 else
                               "better aligned APE (RPE 1 s not better)"))
    print("VERDICT: %s" % ("TILT_ON ships ON" if verdict else "TILT_ON ships OFF (for good: the reserve is spent)"))
    return verdict


def main(argv):
    get = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    try:
        tabs = [load(get(k)) for k in ("--floor", "--off", "--on", "--off-rev", "--on-rev", "--c-off", "--c-on")]
    except (TypeError, FileNotFoundError):
        print(__doc__)
        return 2
    opt = [load(get(k)) if get(k) else None for k in ("--t-off", "--t-on", "--ct-off", "--ct-on")]
    return 0 if judge(*tabs, *opt, get("--gate", "not run")) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

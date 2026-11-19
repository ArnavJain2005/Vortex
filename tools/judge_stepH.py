"""Apply rule H (Step L3, BLIND_ON; Docs/TRACK3_PLAN.md, Step L3, rule H) to the result tags.

Committed with every BLIND_* constant frozen, BEFORE the EuRoC seed 13-15 copies exist and before anything is run
on the TUM-VI seed 13-15 copies. Base: the shipped build (SMOOTH_ON, PLATFORM_ON, TILT_ON) at the rule commit.
Held-out H: MH_03..05, V1_01..03 x readings a, b x seeds 13, 14, 15 (36 copies). TUM-VI block T: room3, room4 x a, b
x seeds 13-15 (12 copies). Clean C: MH_01..05, V1_01..03; clean TUM-VI CT: room1..4.

BLIND_ON ships on only if all hold (off = shipped build, on = the same with BLIND_ON = True):
  1. mean blind RMSE over H improves by >= 2 %
  2. the paired blind gain is positive on >= 4 of the 6 H sequences (readings and seeds pooled per sequence)
  3. neither reading's mean blind RMSE over H is worse by > 1 %
  4. mean APE over H is not worse by > 0.5 %
  5. mean gap RMSE over H is not worse by > 2 %
  6. TUM-VI block T: mean blind RMSE not worse by > 2 %, and mean APE not worse by > 0.5 %
  7. clean APE not worse by > 0.5 %: clean EuRoC (8) and clean TUM-VI (4), each
  8. contract PASS on every run, and the benchmark gate PASSes with BLIND_ON
A trust policy, not recovered motion: the blind rows go to the estimate's centroid, which can tie the never-moving
floor in the blind window, never beat it. If the rule fails, BLIND_ON stays off and there is no re-judge.

    python tools/judge_stepH.py --floor stepH-H-floor --off stepH-H-off --on stepH-H-on --c-off stepH-C-off
        --c-on stepH-C-on --t-off ../tumvi/stepH-T-off --t-on ../tumvi/stepH-T-on --ct-off ../tumvi/stepH-CT-off
        --ct-on ../tumvi/stepH-CT-on [--t-floor ../tumvi/stepH-T-floor] --gate PASS
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from judge_stepG import SEQS, T_ROOMS, apem, load, mean  # noqa: E402

SEEDS = (13, 14, 15)
BLIND_GAIN = 0.02
SEQ_MIN = 4
READING = 0.01
APE_H = 0.005
GAP = 0.02
T_BLIND = 0.02
T_APE = 0.005
CLEAN = 0.005


def judge(floor, off, on, c_off, c_on, t_off, t_on, ct_off, ct_on, gate, t_floor=None):
    H = sorted(off)
    assert len(H) == 36 and set(H) == set(on) == set(floor), "H: 36 copies per tag"
    assert all(int(n.rsplit("_s", 1)[1]) in SEEDS for n in H), "H must be the seed 13-15 copies"
    assert all(any(n.startswith(s) for s in SEQS) for n in H)
    assert len(c_off) == len(c_on) == 8, "C: the 8 clean EuRoC sequences"
    assert len(t_off) == len(t_on) == 12 and set(t_off) == set(t_on), "T: 12 TUM-VI copies"
    assert all(any(n.startswith(r) for r in T_ROOMS) and int(n.rsplit("_s", 1)[1]) in SEEDS for n in t_off)
    assert len(ct_off) == len(ct_on) == 4, "CT: clean TUM-VI room1..4"
    rel = lambda a, b: (b - a) / a  # noqa: E731
    checks = []
    b0, b1 = mean(off, "blind_rmse"), mean(on, "blind_rmse")
    checks.append(("1 mean blind RMSE over H improves >= 2 %", "%.3f -> %.3f m (%+.2f %%)" % (b0, b1, 100 * rel(b0, b1)),
                   rel(b0, b1) <= -BLIND_GAIN))
    per = []
    for s in SEQS:
        ns = [n for n in H if n.startswith(s)]
        assert len(ns) == 6
        per.append((s, mean(off, "blind_rmse", ns), mean(on, "blind_rmse", ns), mean(floor, "blind_rmse", ns),
                    apem(off, ns), apem(on, ns), apem(floor, ns)))
    better = sum(1 for p in per if p[2] < p[1])
    checks.append(("2 paired blind gain > 0 on >= 4 of 6 sequences", "%d of 6" % better, better >= SEQ_MIN))
    for rd in ("a", "b"):
        ns = [n for n in H if off[n]["reading"] == rd]
        x0, x1 = mean(off, "blind_rmse", ns), mean(on, "blind_rmse", ns)
        checks.append(("3 reading %s blind RMSE not worse by > 1 %%" % rd,
                       "%.3f -> %.3f m (%+.2f %%)" % (x0, x1, 100 * rel(x0, x1)), rel(x0, x1) <= READING))
    x0, x1 = apem(off), apem(on)
    checks.append(("4 mean APE over H not worse by > 0.5 %", "%.3f -> %.3f m (%+.2f %%)" % (x0, x1, 100 * rel(x0, x1)),
                   rel(x0, x1) <= APE_H))
    x0, x1 = mean(off, "gap_rmse_mean"), mean(on, "gap_rmse_mean")
    checks.append(("5 mean gap RMSE over H not worse by > 2 %", "%.3f -> %.3f m (%+.2f %%)" % (x0, x1, 100 * rel(x0, x1)),
                   rel(x0, x1) <= GAP))
    x0, x1 = mean(t_off, "blind_rmse"), mean(t_on, "blind_rmse")
    checks.append(("6 TUM-VI block blind RMSE not worse by > 2 %", "%.3f -> %.3f m (%+.2f %%)" % (
        x0, x1, 100 * rel(x0, x1)), rel(x0, x1) <= T_BLIND))
    x0, x1 = apem(t_off), apem(t_on)
    checks.append(("6 TUM-VI block APE not worse by > 0.5 %", "%.3f -> %.3f m (%+.2f %%)" % (
        x0, x1, 100 * rel(x0, x1)), rel(x0, x1) <= T_APE))
    for lab, a, b in (("EuRoC", c_off, c_on), ("TUM-VI", ct_off, ct_on)):
        x0, x1 = apem(a), apem(b)
        checks.append(("7 clean %s APE not worse by > 0.5 %%" % lab, "%.4f -> %.4f m (%+.3f %%)" % (
            x0, x1, 100 * rel(x0, x1)), rel(x0, x1) <= CLEAN))
    tabs = [off, on, c_off, c_on, t_off, t_on, ct_off, ct_on]
    ok = all(r.get("contract") == "PASS" and "error" not in r for t in tabs for r in t.values())
    checks.append(("8 contract PASS on every run", "%d runs" % sum(len(t) for t in tabs), ok))
    checks.append(("8 benchmark gate with BLIND_ON", gate, gate == "PASS"))
    for c, v, p in checks:
        print("  %-46s %-38s %s" % (c, v, "pass" if p else "FAIL"))
    verdict = all(p for _, _, p in checks)
    print("\nPer sequence (mean of 6 copies: readings a, b x seeds 13-15; MH/V1 seeds re-use the same 6 flights)")
    print("| Sequence | blind off | blind on | paired blind effect | floor blind | APE off | APE on | floor APE |")
    print("|---|---|---|---|---|---|---|---|")
    gains = []
    for s, bo, bn, bf, ao, an, af in per:
        g = 100 * (bo - bn) / bo
        gains.append(g)
        print("| %s | %.3f | %.3f | %+.3f m (%+.1f %%) | %.3f | %.3f | %.3f | %.3f |" % (s, bo, bn, bo - bn, g, bf, ao, an, af))
    mg = sum(gains) / len(gains)
    sd = math.sqrt(sum((g - mg) ** 2 for g in gains) / (len(gains) - 1))
    print("Sequence-level paired blind gain: mean %+.1f %%, sd %.1f %% (n = 6). Floor over H: blind %.3f m, APE %.3f m."
          % (mg, sd, mean(floor, "blind_rmse"), apem(floor)))
    print("Error at failure is not in the eval tags; blind growth over H: %.3f -> %.3f m." % (
        mean(off, "blind_growth"), mean(on, "blind_growth")))
    if t_floor is not None:
        print("TUM-VI block floor: blind %.3f m, APE %.3f m." % (mean(t_floor, "blind_rmse"), apem(t_floor)))
    print("A trust policy, not recovered motion: blind rows at the estimate's centroid tie the floor at best.")
    print("VERDICT: %s" % ("BLIND_ON ships ON" if verdict else "BLIND_ON ships OFF (no re-judge; escalate to Arnav)"))
    return verdict


def main(argv):
    get = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    try:
        tabs = [load(get(k)) for k in ("--floor", "--off", "--on", "--c-off", "--c-on", "--t-off", "--t-on",
                                         "--ct-off", "--ct-on")]
    except (TypeError, FileNotFoundError):
        print(__doc__)
        return 2
    tf = load(get("--t-floor")) if get("--t-floor") else None
    return 0 if judge(*tabs, get("--gate", "not run"), t_floor=tf) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

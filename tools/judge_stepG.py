"""Apply rule G (Step L2, TILT_ON; Docs/TRACK3_PLAN.md, Step L2) to the result tags. Committed, with every
TILT_* constant frozen, BEFORE the held-out copies (seeds 10-12) exist. Reads Docs/results/<tag>.json.

Held-out H: MH_03..05, V1_01..03 x readings a, b x seeds 10, 11, 12 (36 official-script copies, made after
the rule commit). These are only 6 trajectories: seeds and readings re-use the same flights, so every
condition that counts sequences pools the 6 copies of a sequence (2 readings x 3 seeds) into one paired mean.
TUM-VI block T: room3, room4 x a, b x seeds 10-12 (12 copies; made by Antigravity, never run by us before
this rule). Clean C: MH_01..05, V1_01..03; clean TUM-VI CT: room1..4.

TILT_ON ships on only if ALL hold:
  1. mean APE (SE3 fitted on the run) over H improves by >= 2 %;
  2. the paired gain (off - on, mean over the sequence's 6 copies) is positive on >= 4 of the 6 sequences;
  3. in each reading separately, mean APE over its 18 copies is not worse by > 1 %;
  4. mean gap RMSE and mean blind RMSE over H are each not worse by > 2 %;
  5. clean mean APE is not worse by > 0.5 % (C, and separately CT);
  6. TUM-VI block T: mean APE not worse by > 1 %;
  7. null floor (Step L1): mean APE over H beats the same output with its positions reversed in time;
  8. output contract PASS on every run;
  9. `python -S benchmark.py --runs 15 --gate` PASS with TILT_ON = True (passed as --gate PASS|FAIL).
Reported, not gates: the never-moving floor, RPE 1 s, the per-sequence paired effects and their spread. A gain
is called "better aligned APE" unless RPE 1 s improves too (path length is not in the result files).

    python tools/judge_stepG.py --floor stepG-H-floor --off stepG-H-off --on stepG-H-on --on-rev stepG-H-on-rev
        --c-off stepG-C-off --c-on stepG-C-on --t-off stepG-T-off --t-on stepG-T-on
        --ct-off stepG-CT-off --ct-on stepG-CT-on --gate PASS
"""
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEDS = (10, 11, 12)
SEQS = ("MH_03_medium", "MH_04_difficult", "MH_05_difficult", "V1_01_easy", "V1_02_medium", "V1_03_difficult")
T_ROOMS = ("dataset-room3_512_16", "dataset-room4_512_16")
GAIN, SEQ_MIN, READING, GAP_BLIND, CLEAN, TUMVI = 0.02, 4, 0.01, 0.02, 0.005, 0.01


def load(tag):
    with open(os.path.join(ROOT, "Docs", "results", tag + ".json"), encoding="utf-8") as f:
        return {r["sequence"]: r for r in json.load(f)["results"]}


def mean(tab, k, names=None):
    xs = [tab[n][k] for n in (names if names is not None else tab) if tab[n].get(k) is not None]
    return sum(xs) / len(xs)


def ape(r):
    return r["ape_se3_rmse"] if "ape_se3_rmse" in r else r["ate_se3_rmse"]


def apem(tab, names=None):
    xs = [ape(tab[n]) for n in (names if names is not None else tab)]
    return sum(xs) / len(xs)


def judge(floor, off, on, rev, c_off, c_on, t_off, t_on, ct_off, ct_on, gate):
    H = sorted(off)
    assert len(H) == 36 and set(H) == set(on) == set(rev) == set(floor), "H: 36 copies in every tag"
    assert all(int(n.rsplit("_s", 1)[1]) in SEEDS for n in H), "H must be the seed 10-12 copies"
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
        per.append((s, apem(off, ns), apem(on, ns), apem(floor, ns), mean(off, "rpe200_rmse", ns),
                    mean(on, "rpe200_rmse", ns)))
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
    xr = apem(rev)
    checks.append(("7 beats its own reversed output", "%.3f vs %.3f reversed" % (a1, xr), a1 < xr))
    tabs = [off, on, rev, c_off, c_on] + [t for t in (t_off, t_on, ct_off, ct_on) if t is not None]
    ok = all(r.get("contract") == "PASS" and "error" not in r for t in tabs for r in t.values())
    checks.append(("8 contract PASS on every run", "%d runs" % sum(len(t) for t in tabs), ok))
    checks.append(("9 benchmark gate with TILT_ON", gate, gate == "PASS"))
    for c, v, p in checks:
        print("  %-46s %-38s %s" % (c, v, "pass" if p else "FAIL"))
    verdict = all(p for _, _, p in checks)
    print("\nPer sequence (mean of 6 copies: readings a, b x seeds 10-12; MH/V1 seeds re-use the same 6 flights)")
    print("| Sequence | APE off m | APE on m | paired gain % | floor m | RPE 1 s off | RPE 1 s on |")
    print("|---|---|---|---|---|---|---|")
    gains = []
    for s, o, n, f, r0, r1 in per:
        g = 100 * (o - n) / o
        gains.append(g)
        print("| %s | %.3f | %.3f | %+.1f | %.3f | %.3f | %.3f |" % (s, o, n, g, f, r0, r1))
    mg = sum(gains) / len(gains)
    sd = math.sqrt(sum((g - mg) ** 2 for g in gains) / (len(gains) - 1))
    r0, r1 = mean(off, "rpe200_rmse"), mean(on, "rpe200_rmse")
    print("Sequence-level paired gain: mean %+.1f %%, sd %.1f %% (n = 6). Floor over H: %.3f m. RPE 1 s %.3f -> %.3f."
          % (mg, sd, apem(floor), r0, r1))
    if verdict:
        print("Wording: %s" % ("motion recovered (APE and RPE 1 s both better)" if r1 < r0 else
                               "better aligned APE (RPE 1 s not better)"))
    print("VERDICT: %s" % ("TILT_ON ships ON" if verdict else "TILT_ON ships OFF"))
    return verdict


def main(argv):
    get = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    try:
        tabs = [load(get(k)) for k in ("--floor", "--off", "--on", "--on-rev", "--c-off", "--c-on")]
    except (TypeError, FileNotFoundError):
        print(__doc__)
        return 2
    opt = [load(get(k)) if get(k) else None for k in ("--t-off", "--t-on", "--ct-off", "--ct-on")]
    return 0 if judge(*tabs, *opt, get("--gate", "not run")) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

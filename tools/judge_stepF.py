"""Apply the Step F decision rule (Docs/TRACK3_PLAN.md, Step F; committed before any held-out run) to an
off/on pair of tags. Reads Docs/results/<tag>.json; prints each condition and the verdict.

Held-out set H: MH_03..05, V1_01..03 x readings a, b x seeds 4, 5, 6 (36 official-script copies made for
this step). Clean set C: MH_01..05, V1_01..03. A no-harm rule: these switches fix demonstrated defects
(steady rotation taken for bias, missing covariance reset, stale cached sample, overconfident fallback
velocity); they do not add a new hint, so they must not cost accuracy rather than gain it.

    python tools/judge_stepF.py --name BGCAP --h-off stepF-H-off --h-on stepF-H-bgcap
                                --c-off stepF-C-off --c-on stepF-C-bgcap
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEDS = (4, 5, 6)
APE_H, APE_READING, GAP_BLIND, APE_C = 0.005, 0.01, 0.02, 0.005


def load(tag):
    with open(os.path.join(ROOT, "Docs", "results", tag + ".json"), encoding="utf-8") as f:
        return json.load(f)["results"]


def mean(rs, k, reading=None):
    xs = [r[k] for r in rs if r.get(k) is not None and (reading is None or r["reading"] == reading)]
    return sum(xs) / len(xs)


def judge(name, h_off, h_on, c_off, c_on):
    ho, hn, co, cn = load(h_off), load(h_on), load(c_off), load(c_on)
    assert len(ho) == len(hn) == 36 and all(r["seed"] in SEEDS for r in ho + hn), "H must be the 36 seed 4-6 copies"
    assert len(co) == len(cn) == 8, "C must be the 8 clean sequences"
    rel = lambda a, b: (b - a) / a  # noqa: E731
    checks = []
    d = rel(mean(ho, "ape_se3_rmse"), mean(hn, "ape_se3_rmse"))
    checks.append(("1 mean APE over H not worse by > 0.5 %", "%.3f -> %.3f m (%+.2f %%)" % (
        mean(ho, "ape_se3_rmse"), mean(hn, "ape_se3_rmse"), 100 * d), d <= APE_H))
    for rd in ("a", "b"):
        d = rel(mean(ho, "ape_se3_rmse", rd), mean(hn, "ape_se3_rmse", rd))
        checks.append(("2 reading %s mean APE not worse by > 1 %%" % rd, "%.3f -> %.3f m (%+.2f %%)" % (
            mean(ho, "ape_se3_rmse", rd), mean(hn, "ape_se3_rmse", rd), 100 * d), d <= APE_READING))
    for k, lab in (("gap_rmse_mean", "gap RMSE"), ("blind_rmse", "blind RMSE")):
        d = rel(mean(ho, k), mean(hn, k))
        checks.append(("3 mean %s over H not worse by > 2 %%" % lab, "%.3f -> %.3f m (%+.2f %%)" % (
            mean(ho, k), mean(hn, k), 100 * d), d <= GAP_BLIND))
    d = rel(mean(co, "ate_se3_rmse"), mean(cn, "ate_se3_rmse"))
    checks.append(("4 clean mean APE not worse by > 0.5 %", "%.4f -> %.4f m (%+.3f %%)" % (
        mean(co, "ate_se3_rmse"), mean(cn, "ate_se3_rmse"), 100 * d), d <= APE_C))
    ok = all(r.get("contract") == "PASS" and "error" not in r for r in ho + hn + co + cn)
    checks.append(("5 contract PASS on every run", "%d runs" % len(ho + hn + co + cn), ok))
    print("%s (%s vs %s; clean %s vs %s)" % (name, h_off, h_on, c_off, c_on))
    for c, v, p in checks:
        print("  %-44s %-34s %s" % (c, v, "pass" if p else "FAIL"))
    verdict = all(p for _, _, p in checks)
    print("  VERDICT (conditions 1-5; BGCAP also needs tests/test_stepF.py): %s" % ("ships ON" if verdict else "ships OFF"))
    return verdict


def main(argv):
    get = lambda k: argv[argv.index(k) + 1]  # noqa: E731
    try:
        a = [get(k) for k in ("--name", "--h-off", "--h-on", "--c-off", "--c-on")]
    except (ValueError, IndexError):
        print(__doc__)
        return 2
    return 0 if judge(*a) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

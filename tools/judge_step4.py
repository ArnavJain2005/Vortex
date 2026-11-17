"""Apply the Step 4 decision rule (Docs/TRACK3_PLAN.md, Step 4; committed before any held-out run of
LEARN_ON) to the learned-envelope tags. Reads Docs/results/<tag>.json; prints each condition and the verdict.

    python tools/judge_step4.py --h-on step4-H-learn --floor step2-floor-off --h-off step3-H-off
                                --c-off step3-C-off --c-on step4-C-learn

Deciding: (1) mean APE over the 36 held-out copies <= the never-moving floor's on the same copies;
(2) clean mean APE not worse than today's by more than 0.5 %; (3) contract PASS on every run.
Reported only: the change against today's fixed envelope (--h-off), per reading, gap and blind RMSE.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELD = ("MH_03_medium", "MH_04_difficult", "MH_05_difficult", "V1_01_easy", "V1_02_medium", "V1_03_difficult")


def load(tag):
    with open(os.path.join(ROOT, "Docs", "results", tag + ".json"), encoding="utf-8") as f:
        return json.load(f)["results"]


def held(rs):
    return [r for r in rs if r.get("base") in HELD and r.get("seed") in (1, 2, 3)]


def mean(rs, k, reading=None):
    xs = [r[k] for r in rs if r.get(k) is not None and (reading is None or r["reading"] == reading)]
    return sum(xs) / len(xs)


def judge(h_on, floor, h_off, c_off, c_on):
    hn, fl, ho = held(load(h_on)), held(load(floor)), held(load(h_off))
    co, cn = load(c_off), load(c_on)
    key = lambda r: (r["base"], r["reading"], r["seed"])  # noqa: E731
    assert len(hn) == len(fl) == len(ho) == 36, (len(hn), len(fl), len(ho))
    assert sorted(map(key, hn)) == sorted(map(key, fl)) == sorted(map(key, ho)), "H copies differ"
    assert sorted(r["sequence"] for r in co) == sorted(r["sequence"] for r in cn), "clean sets differ"
    rel = lambda a, b: (b - a) / a  # noqa: E731
    checks = []
    a, b = mean(fl, "ape_se3_rmse"), mean(hn, "ape_se3_rmse")
    checks.append(("1 mean APE over H <= never-moving floor", "floor %.3f, learned %.3f m (%+.2f %%)" % (
        a, b, 100 * rel(a, b)), b <= a))
    a, b = mean(co, "ate_se3_rmse"), mean(cn, "ate_se3_rmse")
    checks.append(("2 clean mean APE not worse by > 0.5 %", "%.4f -> %.4f m (%+.3f %%)" % (
        a, b, 100 * rel(a, b)), rel(a, b) <= 0.005))
    ok = all(r.get("contract") == "PASS" and "error" not in r for r in hn + cn)
    checks.append(("3 contract PASS on every run", "%d runs" % len(hn + cn), ok))
    print("LEARN_ON (%s vs floor %s; clean %s vs %s)" % (h_on, floor, c_off, c_on))
    for c, v, p in checks:
        print("  %-42s %-40s %s" % (c, v, "pass" if p else "FAIL"))
    verdict = all(p for _, _, p in checks)
    print("  VERDICT: %s" % ("ships ON" if verdict else "ships OFF"))
    print("  reported only (fixed envelope today -> learned):")
    for lab, k, rd in (("APE H", "ape_se3_rmse", None), ("APE reading a", "ape_se3_rmse", "a"),
                       ("APE reading b", "ape_se3_rmse", "b"), ("gap RMSE", "gap_rmse_mean", None),
                       ("blind RMSE", "blind_rmse", None), ("RPE 1 s", "rpe200_rmse", None)):
        try:
            a, b = mean(ho, k, rd), mean(hn, k, rd)
        except (KeyError, ZeroDivisionError):
            continue
        print("    %-14s %.3f -> %.3f m (%+.2f %%); floor %s" % (
            lab, a, b, 100 * rel(a, b), "%.3f" % mean(fl, k, rd) if any(r.get(k) is not None for r in fl) else "-"))
    return verdict


def main(argv):
    get = lambda k: argv[argv.index(k) + 1]  # noqa: E731
    try:
        a = [get(k) for k in ("--h-on", "--floor", "--h-off", "--c-off", "--c-on")]
    except (ValueError, IndexError):
        print(__doc__)
        return 2
    judge(*a)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

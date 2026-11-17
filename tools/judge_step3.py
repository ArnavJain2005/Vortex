"""Apply the Step 3 decision rule (Docs/TRACK3_PLAN.md, Step 3; committed at 99bf25b before any held-out
run) to an off/on pair of tags. Reads Docs/results/<tag>.json; prints each condition and the verdict.

    python tools/judge_step3.py --name STUCK6 --h-off step3-H-off --h-on step3-H-stuck
                                --c-off step3-C-off --c-on step3-C-stuck
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(tag):
    with open(os.path.join(ROOT, "Docs", "results", tag + ".json"), encoding="utf-8") as f:
        return json.load(f)["results"]


def mean(rs, k, reading=None):
    xs = [r[k] for r in rs if r.get(k) is not None and (reading is None or r["reading"] == reading)]
    return sum(xs) / len(xs)


def judge(name, h_off, h_on, c_off, c_on):
    ho, hn, co, cn = load(h_off), load(h_on), load(c_off), load(c_on)
    assert len(ho) == len(hn) == 36 and all(r["seed"] in (1, 2, 3) for r in ho + hn), "H must be the 36 copies"
    rel = lambda a, b: (b - a) / a  # noqa: E731
    checks = []
    d = rel(mean(ho, "ape_se3_rmse"), mean(hn, "ape_se3_rmse"))
    checks.append(("1 mean APE over H improves >= 1 %", "%.3f -> %.3f m (%+.2f %%)" % (
        mean(ho, "ape_se3_rmse"), mean(hn, "ape_se3_rmse"), 100 * d), d <= -0.01))
    for rd in ("a", "b"):
        d = rel(mean(ho, "ape_se3_rmse", rd), mean(hn, "ape_se3_rmse", rd))
        checks.append(("2 reading %s mean APE not worse by > 1 %%" % rd, "%.3f -> %.3f m (%+.2f %%)" % (
            mean(ho, "ape_se3_rmse", rd), mean(hn, "ape_se3_rmse", rd), 100 * d), d <= 0.01))
    for k, lab in (("gap_rmse_mean", "gap RMSE"), ("blind_rmse", "blind RMSE")):
        d = rel(mean(ho, k), mean(hn, k))
        checks.append(("3 mean %s over H not worse by > 2 %%" % lab, "%.3f -> %.3f m (%+.2f %%)" % (
            mean(ho, k), mean(hn, k), 100 * d), d <= 0.02))
    d = rel(mean(co, "ate_se3_rmse"), mean(cn, "ate_se3_rmse"))
    checks.append(("4 clean mean APE not worse by > 0.5 %", "%.4f -> %.4f m (%+.3f %%)" % (
        mean(co, "ate_se3_rmse"), mean(cn, "ate_se3_rmse"), 100 * d), d <= 0.005))
    ok = all(r.get("contract") == "PASS" and "error" not in r for r in ho + hn + co + cn)
    checks.append(("5 contract PASS on every run", "%d runs" % len(ho + hn + co + cn), ok))
    print("%s (%s vs %s; clean %s vs %s)" % (name, h_off, h_on, c_off, c_on))
    for c, v, p in checks:
        print("  %-44s %-34s %s" % (c, v, "pass" if p else "FAIL"))
    verdict = all(p for _, _, p in checks)
    print("  VERDICT: %s" % ("ships ON" if verdict else "ships OFF"))
    return verdict


def main(argv):
    get = lambda k: argv[argv.index(k) + 1]  # noqa: E731
    try:
        a = [get(k) for k in ("--name", "--h-off", "--h-on", "--c-off", "--c-on")]
    except (ValueError, IndexError):
        print(__doc__)
        return 2
    judge(*a)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

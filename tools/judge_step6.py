"""Apply the Step 6 decision rule (Docs/TRACK3_PLAN.md, Step 6; committed before any held-out run of the
smoother) to tools/smooth_eval.py outputs (Docs/smooth/<tag>.json: off and on from the same harness).

    python tools/judge_step6.py --h step6-H --c step6-C --floor step2-floor-off [--r42 step6-R42]

Deciding (H = 36 held-out copies, seeds 1..3; C = 8 clean sequences):
  1 mean APE over H improves by >= 2 %;  2 mean gap RMSE over H improves by >= 2 %;
  3 mean clean APE over C not worse by > 0.5 %.
Reported only: per reading, RPE 1 s, blind RMSE, the never-moving floor on the same copies, seed 42.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELD = ("MH_03_medium", "MH_04_difficult", "MH_05_difficult", "V1_01_easy", "V1_02_medium", "V1_03_difficult")
CLEAN = ("MH_01_easy", "MH_02_easy") + HELD


def sm(tag):
    with open(os.path.join(ROOT, "Docs", "smooth", tag + ".json"), encoding="utf-8") as f:
        return json.load(f)["results"]


def mean(rs, k, reading=None):
    xs = [r[k] for r in rs if r.get(k) is not None and (reading is None or r.get("reading") == reading)]
    return sum(xs) / len(xs)


def judge(h, c, floor, r42=None):
    H = [r for r in sm(h) if r["seq"] in HELD and r["seed"] in (1, 2, 3)]
    off, on = [r for r in H if not r["on"]], [r for r in H if r["on"]]
    assert len(off) == len(on) == 36, (len(off), len(on))
    C = [r for r in sm(c) if r.get("copy") is None and r["seq"] in CLEAN]
    coff, con = [r for r in C if not r["on"]], [r for r in C if r["on"]]
    assert len(coff) == len(con) == 8, (len(coff), len(con))
    with open(os.path.join(ROOT, "Docs", "results", floor + ".json"), encoding="utf-8") as f:
        fl = [r for r in json.load(f)["results"] if r["base"] in HELD and r["seed"] in (1, 2, 3)]
    assert len(fl) == 36
    rel = lambda a, b: (b - a) / a  # noqa: E731
    chk = []
    a, b = mean(off, "ape"), mean(on, "ape")
    chk.append(("1 mean APE over H improves >= 2 %", "%.3f -> %.3f m (%+.2f %%)" % (a, b, 100 * rel(a, b)),
                rel(a, b) <= -0.02))
    a, b = mean(off, "gap_rmse"), mean(on, "gap_rmse")
    chk.append(("2 mean gap RMSE over H improves >= 2 %", "%.3f -> %.3f m (%+.2f %%)" % (a, b, 100 * rel(a, b)),
                rel(a, b) <= -0.02))
    a, b = mean(coff, "ape"), mean(con, "ape")
    chk.append(("3 clean mean APE not worse by > 0.5 %", "%.4f -> %.4f m (%+.3f %%)" % (a, b, 100 * rel(a, b)),
                rel(a, b) <= 0.005))
    print("SMOOTH_ON (%s, clean %s)" % (h, c))
    for t, v, p in chk:
        print("  %-40s %-34s %s" % (t, v, "pass" if p else "FAIL"))
    print("  VERDICT: %s" % ("passes (port to pathfinder.py before shipping)" if all(p for *_, p in chk)
                            else "ships OFF"))
    print("  reported only (off -> on; floor):")
    for lab, k, fk, rd in (("APE reading a", "ape", "ape_se3_rmse", "a"), ("APE reading b", "ape", "ape_se3_rmse", "b"),
                           ("RPE 1 s", "rpe1s", "rpe200_rmse", None), ("blind RMSE", "blind_rmse", "blind_rmse", None),
                           ("gap RMSE a", "gap_rmse", "gap_rmse_mean", "a"), ("gap RMSE b", "gap_rmse", "gap_rmse_mean", "b")):
        a, b = mean(off, k, rd), mean(on, k, rd)
        print("    %-14s %.3f -> %.3f m (%+.2f %%); floor %.3f" % (lab, a, b, 100 * rel(a, b), mean(fl, fk, rd)))
    print("    floor APE over H %.3f m" % mean(fl, "ape_se3_rmse"))
    if r42:
        R = sm(r42)
        for rd in ("a", "b"):
            o = [r for r in R if not r["on"] and r["reading"] == rd]
            n = [r for r in R if r["on"] and r["reading"] == rd]
            print("    seed 42 reading %s: APE %.3f -> %.3f m (%d copies)" % (rd, mean(o, "ape"), mean(n, "ape"), len(o)))


def main(argv):
    get = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    if not (get("--h") and get("--c") and get("--floor")):
        print(__doc__)
        return 2
    judge(get("--h"), get("--c"), get("--floor"), get("--r42"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

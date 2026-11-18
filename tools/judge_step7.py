"""Apply the Step 7 decision rule (Docs/TRACK3_PLAN.md, Step 7; committed before the held-out run).

    python tools/judge_step7.py [--off step7-H-off --on step7-H-on --coff step7-HC-off --con step7-HC-on
                                 --floor step7-H-floor --detect step7-detect]

Inputs (Docs/tumvi/<tag>.json): tools/eval_euroc.py --root data/tumvi [--official] runs of main.py with
--set PLATFORM_ON=False / True on room3, room4 (official copies seeds 7-9, readings a, b; clean), the
never-moving floor (tools/baseline_still.py) on the same copies, and tools/platform_check.py.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOMS = ("dataset-room3_512_16", "dataset-room4_512_16")


def load(tag):
    with open(os.path.join(ROOT, "Docs", "tumvi", tag + ".json"), encoding="utf-8") as f:
        return json.load(f)


def held(tag):
    rs = [r for r in load(tag)["results"] if r.get("base") in ROOMS and r.get("seed") in (7, 8, 9)]
    assert len(rs) == 12, (tag, len(rs))
    return rs


def mean(rs, k):
    return sum(r[k] for r in rs) / len(rs)


def judge(off, on, coff, con, floor, detect):
    H0, H1, F = held(off), held(on), held(floor)
    C0 = [r for r in load(coff)["results"] if r["sequence"] in ROOMS]
    C1 = [r for r in load(con)["results"] if r["sequence"] in ROOMS]
    assert len(C0) == len(C1) == 2
    det = load(detect)["summary"]
    rel = lambda a, b: (b - a) / a  # noqa: E731
    chk = []
    ok_a = not det["wrong"]
    chk.append(("A detector right on every file (%d files)" % det["files"],
                "wrong %d; smallest multirotor %.3f, largest hand-held %.3f (threshold %.1f)" % (
                    len(det["wrong"]), det["min_multirotor_stat"], det["max_handheld_stat"], det["threshold"]),
                ok_a))
    a, b = mean(H0, "ape_se3_rmse"), mean(H1, "ape_se3_rmse")
    chk.append(("B1 held-out mean APE improves >= 10 %", "%.3f -> %.3f m (%+.1f %%)" % (a, b, 100 * rel(a, b)),
                rel(a, b) <= -0.10))
    a, b = mean(H0, "gap_rmse_mean"), mean(H1, "gap_rmse_mean")
    chk.append(("B2 held-out mean gap RMSE improves >= 5 %", "%.3f -> %.3f m (%+.1f %%)" % (a, b, 100 * rel(a, b)),
                rel(a, b) <= -0.05))
    per = []
    for room in ROOMS:
        a = mean([r for r in H0 if r["base"] == room], "ape_se3_rmse")
        b = mean([r for r in H1 if r["base"] == room], "ape_se3_rmse")
        per.append((room[8:13], a, b))
    chk.append(("B3 each room improves (paired)", ", ".join("%s %.3f -> %.3f" % p for p in per),
                all(b < a for _, a, b in per)))
    a, b = mean(C0, "ate_se3_rmse"), mean(C1, "ate_se3_rmse")
    chk.append(("B4 clean room3/4 mean APE not worse > 5 %", "%.3f -> %.3f m (%+.1f %%)" % (a, b, 100 * rel(a, b)),
                rel(a, b) <= 0.05))
    ident = det["identity"]
    chk.append(("C EuRoC byte-identical with PLATFORM_ON (%d copies)" % len(ident),
                "%d of %d identical" % (sum(1 for x in ident if x["identical"]), len(ident)),
                bool(ident) and all(x["identical"] for x in ident)))
    if all("stat_equal" in x for x in ident):
        print("  (detector statistic inside main.py's run equals the check's on %d of %d copies)" % (
            sum(1 for x in ident if x["stat_equal"]), len(ident)))
    print("PLATFORM_ON (held-out room3/room4, seeds 7-9)")
    for t, v, p in chk:
        print("  %-52s %-58s %s" % (t, v, "pass" if p else "FAIL"))
    print("  VERDICT: %s" % ("ships ON" if all(p for *_, p in chk) else "ships OFF"))
    print("  reported only (off -> on; floor on the same copies):")
    for lab, k, rd in (("APE reading a", "ape_se3_rmse", "a"), ("APE reading b", "ape_se3_rmse", "b"),
                       ("RPE 1 s", "rpe200_rmse", None), ("blind RMSE", "blind_rmse", None),
                       ("gap RMSE", "gap_rmse_mean", None)):
        sel = (lambda rs: [r for r in rs if rd is None or r["reading"] == rd])
        print("    %-14s %.3f -> %.3f m; floor %.3f" % (lab, mean(sel(H0), k), mean(sel(H1), k), mean(sel(F), k)))
    print("    APE floor (12 copies) %.3f m; clean %s" % (
        mean(F, "ape_se3_rmse"), ", ".join("%s %.3f -> %.3f" % (c0["sequence"][8:13], c0["ate_se3_rmse"],
                                                                   c1["ate_se3_rmse"]) for c0, c1 in zip(C0, C1))))
    return 0


def main(argv):
    get = lambda k, d: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    return judge(get("--off", "step7-H-off"), get("--on", "step7-H-on"), get("--coff", "step7-HC-off"),
                 get("--con", "step7-HC-on"), get("--floor", "step7-H-floor"), get("--detect", "step7-detect"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

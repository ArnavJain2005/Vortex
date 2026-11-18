"""Step L2 tuning grid (TUNING DATA ONLY: MH_01/02 official copies, seeds 1-3, and clean MH_01/02).

For each setting (a set of --set NAME=VALUE overrides on top of TILT_ON=True) every file is run once with the
chosen main (default the reference, tools/ref_main.py), scored as the organisers score it (APE with SE3 fitted
on the run, gap and blind RMSE; tools/eval_euroc.py evaluate_official) and for tilt error by phase
(tools/tilt_eval.py). Writes Docs/tilt/<tag>.json and prints one table per reading.

Usage:
  python tools/tilt_tune.py --tag stepL2-tune [--main tools/ref_main.py]
         --grid "TILT_R_K=1" --grid "TILT_R_K=0.1;TILT_TAU=6" ...   (the first column is always TILT_ON=False)
"""
import argparse
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import eval_euroc  # noqa: E402
import tilt_eval  # noqa: E402

TUNE = ["MH_01_easy", "MH_02_easy"]
SEEDS = [1, 2, 3]
KEYS = ("ape_se3_rmse", "rpe200_rmse", "gap_rmse_mean", "blind_rmse")


def files():
    out = []
    for b in TUNE:
        for r in ("a", "b"):
            for s in SEEDS:
                out.append(("%s_%s_s%d" % (b, r, s), r))
    return out + [(b, "clean") for b in TUNE]


def run_setting(main_path, sets, tmp):
    wrapped = eval_euroc.wrapper(main_path, sets, tmp)
    res = []
    for name, reading in files():
        if reading == "clean":
            r = eval_euroc.evaluate(wrapped, name, tmp)
            r["reading"] = "clean"
            r["ape_se3_rmse"] = r.get("ate_se3_rmse")
            gt_dir = os.path.join(eval_euroc.DATA, name)
            est = os.path.join(tmp, name + ".txt")
            bw = None
        else:
            r = eval_euroc.evaluate_official(wrapped, name, tmp)
            base = eval_euroc.official_base(name)[0]
            gt_dir = os.path.join(eval_euroc.DATA, base)
            est = os.path.join(tmp, name + ".txt")
            bw = tilt_eval.blind_window(os.path.join(eval_euroc.OFFICIAL, name))
        if "error" not in r:
            r["tilt"] = tilt_eval.tilt_errors(gt_dir, est, bw)
        res.append(r)
    return res


def summary(res):
    by = {}
    for r in res:
        if "error" in r:
            continue
        d = by.setdefault(r["reading"], {k: [] for k in KEYS + ("tilt_all", "tilt_hover", "tilt_manoeuvre")})
        for k in KEYS:
            if r.get(k) is not None:
                d[k].append(r[k])
        for ph in ("all", "hover", "manoeuvre"):
            x = r["tilt"][ph]["rms_deg"]
            if x is not None:
                d["tilt_" + ph].append(x)
    return {rd: {k: (sum(v) / len(v) if v else None) for k, v in d.items()} for rd, d in by.items()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--main", default=os.path.join(ROOT, "tools", "ref_main.py"))
    ap.add_argument("--grid", action="append", default=[])
    args = ap.parse_args(argv)
    settings = [[("TILT_ON", "False")]]
    for g in args.grid:
        settings.append([("TILT_ON", "True")] + [tuple(x.split("=", 1)) for x in g.split(";") if x])
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for sets in settings:
            res = run_setting(os.path.abspath(args.main), sets, tmp)
            s = summary(res)
            out.append({"set": sets, "summary": s, "runs": res})
            print(";".join("%s=%s" % kv for kv in sets), flush=True)
            for rd in ("a", "b", "clean"):
                if rd in s:
                    x = s[rd]
                    print("  %-5s APE %.3f  RPE %.3f  gap %s  blind %s  tilt all %.2f hover %.2f man %.2f" % (
                        rd, x["ape_se3_rmse"], x["rpe200_rmse"],
                        "%.3f" % x["gap_rmse_mean"] if x["gap_rmse_mean"] is not None else "-",
                        "%.3f" % x["blind_rmse"] if x["blind_rmse"] is not None else "-",
                        x["tilt_all"], x["tilt_hover"], x["tilt_manoeuvre"]), flush=True)
    os.makedirs(tilt_eval.OUT, exist_ok=True)
    with open(os.path.join(tilt_eval.OUT, args.tag + ".json"), "w", encoding="utf-8") as f:
        json.dump({"tag": args.tag, "main": os.path.relpath(args.main, ROOT), "files": files(), "settings": out},
                  f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

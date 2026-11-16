"""Run a main.py on EuRoC sequences, score each output, keep the results by tag. OFFLINE (reads GT).

For every sequence under data/euroc/ (or the ones named): `python -S <main> imu0/data.csv out.txt`
in a subprocess, the output contract check, then vortex/scoring.py (APE after SE3 and Sim3 Umeyama
alignment, final position error after SE3, RPE translation over 200 frames = 1 s). Results go to
Docs/results/<tag>.json; --render rebuilds Docs/RESULTS.md from all of them (never edit by hand).

Usage:
  python tools/eval_euroc.py --tag step6b [--main main.py] [--seqs MH_01_easy,MH_02_easy]
                             [--set V2_ON=False --set V2P_TAU=20]   (ablations: module constants of
                             the main script, set by a temporary wrapper; main.py itself is unchanged)
  python tools/eval_euroc.py --tag NAME --degraded [--seqs MH_01_easy_s1,...]
                             (every folder under data/degraded/, made by `python -m vortex.degrade`;
                             named <sequence>_s<seed>. Alignment is fitted ONCE on the same main's run
                             on the clean sequence (align "given"), so it cannot absorb a fault; errors
                             are split by phase from degrade.json)
  python tools/eval_euroc.py --render
"""
import glob
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from vortex import check_output, scoring  # noqa: E402

DATA = os.path.join(ROOT, "data", "euroc")
DEGRADED = os.path.join(ROOT, "data", "degraded")
OUT_DIR = os.path.join(ROOT, "Docs", "results")


def wrapper(main_path, sets, tmp):
    """A temporary script that imports main_path, sets module constants, then runs it."""
    lines = ["import sys, importlib.util",
             "spec = importlib.util.spec_from_file_location('m', %r)" % main_path,
             "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)"]
    for name, value in sets:
        lines.append("assert hasattr(m, %r), 'no constant %s'" % (name, name))
        lines.append("m.%s = %s" % (name, value))
    lines.append("sys.exit(m.main(sys.argv))")
    path = os.path.join(tmp, "wrapped_main.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def evaluate(main_path, seq, tmp):
    imu = os.path.join(DATA, seq, "mav0", "imu0", "data.csv")
    est = os.path.join(tmp, seq + ".txt")
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, "-S", main_path, imu, est], capture_output=True, text=True)
    wall = time.perf_counter() - t0
    if p.returncode != 0:
        return {"sequence": seq, "error": p.stderr[-400:]}
    chk = check_output.check(imu, est)
    ref = scoring.read_ground_truth(os.path.join(DATA, seq))
    e, _ = scoring.read_tum(est)
    r_se3 = scoring.score(ref, e, align="se3", rpe_deltas=(200,))
    r_sim3 = scoring.score(ref, e, align="sim3", rpe_deltas=(200,))
    return {"sequence": seq, "rows": chk["input_rows"], "contract": "PASS" if chk["ok"] else "FAIL",
            "wall_s": wall, "ate_se3_rmse": r_se3["ape"]["rmse"], "final_se3": r_se3["final_error"],
            "ate_sim3_rmse": r_sim3["ape"]["rmse"], "sim3_scale": r_sim3["alignment"]["scale"],
            "rpe200_rmse": r_se3["rpe"]["200"]["rmse"]}


def run_main(main_path, imu, est):
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, "-S", main_path, imu, est], capture_output=True, text=True)
    return p, time.perf_counter() - t0


def evaluate_degraded(main_path, name, tmp, clean_cache):
    """One degraded copy: score with the alignment fitted on the clean run of the same main."""
    base = name.rsplit("_s", 1)[0]
    seq_dir = os.path.join(DEGRADED, name)
    imu = os.path.join(seq_dir, "mav0", "imu0", "data.csv")
    with open(os.path.join(seq_dir, "degrade.json"), encoding="utf-8") as f:
        events = json.load(f)
    ref = scoring.read_ground_truth(os.path.join(DATA, base))
    if base not in clean_cache:
        clean_est = os.path.join(tmp, base + "_clean.txt")
        p, _ = run_main(main_path, os.path.join(DATA, base, "mav0", "imu0", "data.csv"), clean_est)
        if p.returncode != 0:
            return {"sequence": name, "error": "clean run: " + p.stderr[-400:]}
        clean_cache[base] = scoring.fit_alignment(ref, scoring.read_tum(clean_est)[0], "se3")
    est = os.path.join(tmp, name + ".txt")
    p, wall = run_main(main_path, imu, est)
    if p.returncode != 0:
        return {"sequence": name, "error": p.stderr[-400:]}
    chk = check_output.check(imu, est)
    e, _ = scoring.read_tum(est)
    r = scoring.score(ref, e, align="given", given=clean_cache[base], rpe_deltas=(200,), events=events)
    ph = r["phases"]
    drops = [d for d in ph["dropouts"] if d.get("n")]
    return {"sequence": name, "rows": chk["input_rows"], "contract": "PASS" if chk["ok"] else "FAIL",
            "wall_s": wall, "seed": events["seed"], "ape_given_rmse": r["ape"]["rmse"],
            "rpe200_rmse": r["rpe"]["200"]["rmse"], "final_given": r["final_error"],
            "degraded_rmse": ph["degraded"].get("rmse"),
            "dropout_rmse_mean": sum(d["rmse"] for d in drops) / len(drops) if drops else None,
            "dropout_growth_mean": sum(d["growth"] for d in drops) / len(drops) if drops else None,
            "blind_rmse": ph["blind"].get("rmse"), "blind_growth": ph["blind"].get("growth"),
            "blind_end": ph["blind"].get("end_error")}


DEG_COLS = [("ape_given_rmse", "APE m"), ("rpe200_rmse", "RPE 1 s m"), ("dropout_growth_mean", "Dropout growth m"),
            ("blind_growth", "Blind 5 s growth m"), ("blind_rmse", "Blind RMSE m")]


def pivot_degraded(runs):
    """Summary of degraded runs: one row per tag, means over all degraded copies."""
    L = ["## Degraded runs: means over every copy (seeded `vortex.degrade`, placeholder levels)", "",
         "| Tag | Copies | " + " | ".join(c[1] for c in DEG_COLS) + " |", "|---|---|" + "---|" * len(DEG_COLS)]
    for run in runs:
        ok = [r for r in run["results"] if "error" not in r]
        cells = []
        for k, _ in DEG_COLS:
            xs = [r[k] for r in ok if r.get(k) is not None]
            cells.append("%.3f" % (sum(xs) / len(xs)) if xs and len(ok) == len(run["results"]) else "-")
        L.append("| %s | %d | %s |" % (run["tag"], len(ok), " | ".join(cells)))
    return L


def pivot(runs):
    """Summary: one row per tag, APE SE3 / RPE 1 s per sequence and the mean over sequences."""
    seqs = sorted({r["sequence"] for run in runs for r in run["results"]})
    L = ["## Summary: APE SE3 m / RPE 1 s m", "",
         "| Tag | " + " | ".join(s[:5] for s in seqs) + " | Mean APE | Mean RPE 1 s |",
         "|---|" + "---|" * (len(seqs) + 2)]
    for run in runs:
        by = {r["sequence"]: r for r in run["results"] if "error" not in r}
        cells, a, b = [], [], []
        for s in seqs:
            if s in by:
                cells.append("%.2f / %.3f" % (by[s]["ate_se3_rmse"], by[s]["rpe200_rmse"]))
                a.append(by[s]["ate_se3_rmse"])
                b.append(by[s]["rpe200_rmse"])
            else:
                cells.append("-")
        full = len(a) == len(seqs)
        L.append("| %s | %s | %s | %s |" % (run["tag"], " | ".join(cells),
                                            "%.2f" % (sum(a) / len(a)) if full else "-",
                                            "%.3f" % (sum(b) / len(b)) if full else "-"))
    return L


def render():
    files = sorted(glob.glob(os.path.join(OUT_DIR, "*.json")))
    every = [json.load(open(p, encoding="utf-8")) for p in files]
    runs = [r for r in every if not r.get("degraded")]
    deg = [r for r in every if r.get("degraded")]
    L = ["# Results on EuRoC (generated by `python tools/eval_euroc.py --render`; do not edit by hand)", "",
         "Clean (undegraded) IMU input. APE = absolute position error after Umeyama alignment of the whole "
         "trajectory (SE3, or Sim3 with scale). Final = position error of the last pose after SE3. "
         "RPE 1 s = relative translation error over 200 frames. Sim3 can shrink a badly drifting "
         "trajectory toward a point (see the scale column), so it flatters drift; SE3 is the honest number.",
         ""] + pivot(runs) + ["", "## Every run", "", "| Tag | Main (settings) | Commit | Date | Sequence | Contract | APE SE3 m | Final m | APE Sim3 m | Sim3 scale | RPE 1 s m | Wall s |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for run in runs:
        how = run.get("main", "main.py") + "".join(" %s=%s" % kv for kv in sorted(run.get("set", {}).items()))
        for r in run["results"]:
            if "error" in r:
                L.append("| %s | %s | %s | %s | %s | ERROR | - | - | - | - | - | - |" % (
                    run["tag"], how, run["commit"], run["date"], r["sequence"]))
                continue
            L.append("| %s | %s | %s | %s | %s | %s | %.2f | %.2f | %.2f | %.3g | %.3f | %.2f |" % (
                run["tag"], how, run["commit"], run["date"], r["sequence"], r["contract"], r["ate_se3_rmse"],
                r["final_se3"], r["ate_sim3_rmse"], r["sim3_scale"], r["rpe200_rmse"], r["wall_s"]))
    if deg:
        L += ["", "# Degraded input", "",
              "Copies made by `python -m vortex.degrade <clean sequence> data/degraded/<sequence>_s<seed> "
              "--seed <seed>` with the default (placeholder) levels: rising white noise, bias random walk, "
              "three 2 s NaN dropouts, total failure (NaN) at 85 % of the sequence, cut 5 s later. "
              "The organisers' script is unknown (Q2). APE uses the SE3 alignment fitted once on the same "
              "main's CLEAN run (align given), so it cannot absorb a fault. Growth = how far the position "
              "error vector moves across the window (start to end).", ""] + pivot_degraded(deg)
        L += ["", "## Every degraded run", "",
              "| Tag | Main (settings) | Commit | Date | Copy | Contract | " + " | ".join(c[1] for c in DEG_COLS)
              + " | Wall s |", "|---|---|---|---|---|---|" + "---|" * (len(DEG_COLS) + 1)]
        for run in deg:
            how = run.get("main", "main.py") + "".join(" %s=%s" % kv for kv in sorted(run.get("set", {}).items()))
            for r in run["results"]:
                if "error" in r:
                    L.append("| %s | %s | %s | %s | %s | ERROR |%s" % (run["tag"], how, run["commit"], run["date"],
                                                                     r["sequence"], " - |" * (len(DEG_COLS) + 1)))
                    continue
                L.append("| %s | %s | %s | %s | %s | %s | %s | %.2f |" % (
                    run["tag"], how, run["commit"], run["date"], r["sequence"], r["contract"],
                    " | ".join("-" if r.get(k) is None else "%.3f" % r[k] for k, _ in DEG_COLS), r["wall_s"]))
    L.append("")
    path = os.path.join(ROOT, "Docs", "RESULTS.md")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))
    return path


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--render" in argv:
        print("wrote", os.path.relpath(render(), ROOT))
        return 0
    get = lambda k, d: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    tag = get("--tag", None)
    if not tag:
        print(__doc__)
        return 2
    main_path = os.path.abspath(get("--main", os.path.join(ROOT, "main.py")))
    sets = [a.split("=", 1) for i, a in enumerate(argv) if i > 0 and argv[i - 1] == "--set"]
    degraded = "--degraded" in argv
    seqs = get("--seqs", None)
    seqs = seqs.split(",") if seqs else sorted(os.listdir(DEGRADED if degraded else DATA))
    commit = get("--commit", None) or subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                                      capture_output=True, text=True).stdout.strip()
    tmp = tempfile.mkdtemp(prefix="vortex_eval_")
    run_path = wrapper(main_path, sets, tmp) if sets else main_path
    results = []
    clean_cache = {}
    for s in seqs:
        r = evaluate_degraded(run_path, s, tmp, clean_cache) if degraded else evaluate(run_path, s, tmp)
        results.append(r)
        if "error" in r:
            print("%-16s ERROR %s" % (s, r["error"]))
        elif degraded:
            print("%-19s %s  " % (s, r["contract"]) + "  ".join(
                "%s %s" % (lab, "-" if r.get(k) is None else "%.3f" % r[k]) for k, lab in DEG_COLS))
        else:
            print("%-16s %s  APE se3 %9.2f m  final %9.2f m  APE sim3 %6.2f m (scale %.3g)  RPE 1 s %.3f m" % (
                s, r["contract"], r["ate_se3_rmse"], r["final_se3"], r["ate_sim3_rmse"], r["sim3_scale"],
                r["rpe200_rmse"]))
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, tag + ".json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"tag": tag, "commit": commit, "date": time.strftime("%Y-%m-%d"), "main": os.path.relpath(
            main_path, ROOT) if main_path.startswith(ROOT) else os.path.basename(main_path),
            "set": {k: v for k, v in sets}, "degraded": degraded,
            "python": sys.version.split()[0], "results": results}, f, indent=1, sort_keys=True)
        f.write("\n")
    print("wrote", os.path.relpath(render(), ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())

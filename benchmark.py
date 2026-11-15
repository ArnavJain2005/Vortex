"""Budget ledger for main.py: generates Docs/BUDGET.md (never edit that file by hand). Stdlib only.

Measures, on one input:
  - per-stage cost in us per row, in-process (main.run with stage switches; median of --runs);
  - tracemalloc peak of main.run;
  - whole process, `python -S main.py IN OUT` and `python main.py IN OUT`: wall and CPU ms per
    IMU-second, us per row, peak RSS (Windows PeakWorkingSetSize, Linux GNU time %M), peak private
    bytes (Windows);
  - bytes stored for the offline passes (none yet);
  - whether the output passes vortex/check_output.py.
Results go to Docs/budget/<tag>.json; --render rebuilds Docs/BUDGET.md from all of them.

Usage:
  python -S benchmark.py [--rows 36000] [--runs 9] [--input FILE] [--tag NAME] [--commit SHA] [--gate]
  python benchmark.py --render
--gate exits 1 if the design targets are missed: process <= 50 us per row with -S,
tracemalloc <= 4 MB, output passes the checker. Timing gates are flaky: run on a quiet machine.
"""
import importlib.util
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
import measure_floor  # noqa: E402  (run_measured, summarise, cpu name)
import synth_euroc  # noqa: E402
from vortex import check_output  # noqa: E402  (stdlib only)

OUT_DIR = os.path.join(ROOT, "Docs", "budget")
IMU_HZ = 200.0
BUDGET_US_ROW, TARGET_US_ROW = 100.0, 50.0
BUDGET_MS_PER_S = 20.0
BUDGET_RSS_MB, TARGET_TRACE_MB = 8.0, 4.0

# Stage switches passed to main.run, cumulative. Each new filter stage or witness adds a row here.
STAGES = [
    ("parse (read, split, 6 floats, timestamp)", {"write": False, "integrate": False}),
    ("parse + write (identity poses)", {"integrate": False}),
    ("parse + init + strapdown integrator", {"write": False}),
    ("parse + init + strapdown integrator + write (full main.py)", {}),
]
PASSES = ["forward (single pass; no smoother yet)"]


def load_main():
    spec = importlib.util.spec_from_file_location("vortex_main_bench", os.path.join(ROOT, "main.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def measure(a):
    rows, runs = a["rows"], a["runs"]
    tmp = tempfile.gettempdir()
    src = a["input"]
    label = "real: " + os.path.relpath(src, ROOT).replace(os.sep, "/") if src else None
    if not src:
        src = os.path.join(tmp, "vortex_synth_%d.csv" % rows)
        synth_euroc.write(src, rows=rows, seed=0)
        label = "SYNTHETIC (tools/synth_euroc.py, seed 0)"
    dst = os.path.join(tmp, "vortex_bench_out.txt")
    main = load_main()
    n = main.run(src, dst)
    imu_s = n / IMU_HZ

    res = {"platform": platform.system(), "platform_release": platform.release(),
           "cpu": measure_floor._cpu_name(), "python": platform.python_version(),
           "date": time.strftime("%Y-%m-%d"), "commit": a["commit"] or git_commit(),
           "input": label, "rows": n, "imu_seconds": imu_s, "runs": runs}

    stages = []
    for name, kw in STAGES:
        ts = []
        for _ in range(runs):
            t0 = time.perf_counter()
            main.run(src, dst, **kw)
            ts.append(time.perf_counter() - t0)
        us = statistics.median(ts) / n * 1e6
        stages.append({"stage": name, "us_per_row": us, "us_per_row_min": min(ts) / n * 1e6})
        print("  stage %-45s %6.2f us/row" % (name, us))
    res["stages"] = stages
    res["passes"] = [{"pass": p, "us_per_row": stages[-1]["us_per_row"]} for p in PASSES]

    tracemalloc.start()
    main.run(src, dst)
    res["tracemalloc_peak_kb"] = tracemalloc.get_traced_memory()[1] / 1024.0
    tracemalloc.stop()
    print("  tracemalloc peak %.1f KB" % res["tracemalloc_peak_kb"])

    res["stored_bytes_per_block"] = 0
    res["stored_bytes_worst_case"] = 0

    procs = []
    for label_p, cmd in [("python -S main.py", [sys.executable, "-S", os.path.join(ROOT, "main.py"), src, dst]),
                         ("python main.py", [sys.executable, os.path.join(ROOT, "main.py"), src, dst])]:
        s = measure_floor.summarise(measure_floor.repeat(cmd, runs))
        s["case"] = label_p
        s["wall_ms_per_imu_s"] = s["wall_ms_median"] / imu_s
        s["cpu_ms_per_imu_s"] = s["cpu_ms_median"] / imu_s
        s["us_per_row"] = s["wall_ms_median"] * 1e3 / n
        procs.append(s)
        print("  %-18s %6.2f us/row  %5.2f ms/imu-s  rss %5.2f MB"
              % (label_p, s["us_per_row"], s["wall_ms_per_imu_s"], s["peak_rss_mb_median"]))
    res["process"] = procs

    chk = check_output.check(src, dst)
    res["output_check"] = "PASS" if chk["ok"] else "FAIL: " + "; ".join(chk["errors"][:3])
    print("  output check:", res["output_check"])
    return res


def gate(res):
    fails = []
    p = res["process"][0]
    if p["us_per_row"] > TARGET_US_ROW:
        fails.append("process %.2f us/row > %.0f" % (p["us_per_row"], TARGET_US_ROW))
    if res["tracemalloc_peak_kb"] > TARGET_TRACE_MB * 1024:
        fails.append("tracemalloc %.0f KB > %.0f MB" % (res["tracemalloc_peak_kb"], TARGET_TRACE_MB))
    if res["output_check"] != "PASS":
        fails.append("output check failed")
    return fails


def _f(x, d=2):
    return "-" if x is None else "%.*f" % (d, x)


def render():
    import glob
    files = sorted(glob.glob(os.path.join(OUT_DIR, "*.json")))
    data = [(os.path.basename(p)[:-5], json.load(open(p, encoding="utf-8"))) for p in files]
    L = ["# Budget ledger (generated by `python benchmark.py --render`; do not edit by hand)", "",
         "Organisers' limits: peak RAM 8 MB; 20 ms compute per 1 s of IMU (100 us per row at 200 Hz); "
         "single thread; offline.",
         "Our design targets (2x margin for an unknown evaluator CPU): 50 us per row; 4 MB tracemalloc peak.",
         "",
         "Peak RSS includes the CPython interpreter (8.4 MB on Linux, 9.5 MB on Windows before any work; "
         "see `Docs/FLOOR.md`). Whether the 8 MB limit means whole-process RSS is open question Q4.",
         "Timing varies about +-15% between reruns on the same laptop.", "",
         "## Runs", "",
         "| Run | Commit | Date | OS | CPU | Python | Input | Rows |",
         "|---|---|---|---|---|---|---|---|"]
    for tag, d in data:
        L.append("| %s | %s | %s | %s %s | %s | %s | %s | %d (%.0f s) |" % (
            tag, d.get("commit") or "-", d["date"], d["platform"], d["platform_release"], d["cpu"],
            d["python"], d["input"], d["rows"], d["imu_seconds"]))
    L += ["", "## Summary: `python -S main.py` against the budget", "",
          "| Run | us per row | Left of 100 (of 50 target) | Wall ms per IMU-s | CPU ms per IMU-s | Left of 20 ms "
          "| Peak RSS MB | Peak private MB | tracemalloc KB | Left of 4 MB | Output |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for tag, d in data:
        p = d["process"][0]
        L.append("| %s | %s | %s (%s) | %s | %s | %s | %s | %s | %s | %s KB | %s |" % (
            tag, _f(p["us_per_row"]), _f(BUDGET_US_ROW - p["us_per_row"], 1),
            _f(TARGET_US_ROW - p["us_per_row"], 1), _f(p["wall_ms_per_imu_s"]), _f(p["cpu_ms_per_imu_s"]),
            _f(BUDGET_MS_PER_S - p["wall_ms_per_imu_s"], 1), _f(p["peak_rss_mb_median"]),
            _f(p["peak_private_mb_median"]), _f(d["tracemalloc_peak_kb"], 1),
            _f(TARGET_TRACE_MB * 1024 - d["tracemalloc_peak_kb"], 0), d["output_check"]))
    L += ["", "## Stages (in-process, cumulative, median us per row)", "",
          "| Run | Stage | us per row | min |", "|---|---|---|---|"]
    for tag, d in data:
        for s in d["stages"]:
            L.append("| %s | %s | %s | %s |" % (tag, s["stage"], _f(s["us_per_row"]), _f(s["us_per_row_min"])))
    L += ["", "## Passes", "", "| Run | Pass | us per row |", "|---|---|---|"]
    for tag, d in data:
        for s in d["passes"]:
            L.append("| %s | %s | %s |" % (tag, s["pass"], _f(s["us_per_row"])))
    L += ["", "## Witnesses", "", "None implemented yet.", "",
          "## Stored state for offline passes", "",
          "| Run | Bytes per stored block | Worst-case total bytes |", "|---|---|---|"]
    for tag, d in data:
        L.append("| %s | %d | %d |" % (tag, d["stored_bytes_per_block"], d["stored_bytes_worst_case"]))
    L += ["", "## With and without `-S`", "",
          "| Run | Command | us per row | Wall ms per IMU-s | Peak RSS MB |", "|---|---|---|---|---|"]
    for tag, d in data:
        for p in d["process"]:
            L.append("| %s | `%s` | %s | %s | %s |" % (tag, p["case"], _f(p["us_per_row"]),
                                                      _f(p["wall_ms_per_imu_s"]), _f(p["peak_rss_mb_median"])))
    L.append("")
    path = os.path.join(ROOT, "Docs", "BUDGET.md")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))
    print("wrote", os.path.relpath(path, ROOT))


def main(argv):
    if "--render" in argv:
        render()
        return 0
    get = lambda k, d: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    a = {"rows": int(get("--rows", 36000)), "runs": int(get("--runs", 9)), "input": get("--input", None),
         "commit": get("--commit", None)}
    print("benchmark: Python %s" % platform.python_version())
    res = measure(a)
    os.makedirs(OUT_DIR, exist_ok=True)
    tag = get("--tag", None) or "%s-py%s" % (platform.system().lower(),
                                             "".join(platform.python_version_tuple()[:2]))
    with open(os.path.join(OUT_DIR, tag + ".json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(res, f, indent=1, sort_keys=True)
        f.write("\n")
    print("wrote Docs/budget/%s.json" % tag)
    if "--gate" in argv:
        fails = gate(res)
        print("GATE:", "PASS" if not fails else "FAIL: " + "; ".join(fails))
        return 1 if fails else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

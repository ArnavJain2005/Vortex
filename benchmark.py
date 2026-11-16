"""Budget ledger for main.py (stub) and pathfinder.py (estimator): generates Docs/BUDGET.md (never edit that file by hand). Stdlib only.

Measures, on one input:
  - per-stage cost in us per row, in-process (pathfinder.run with stage switches; median of --runs);
  - tracemalloc peak of pathfinder.run;
  - whole process, `python -S main.py IN OUT` (bytecode cached), `python main.py IN OUT`, the same with
    no cached bytecode, and `python -S pathfinder.py IN OUT` (source compiled each run): wall and CPU ms per
    IMU-second, us per row, peak RSS (Windows PeakWorkingSetSize, Linux GNU time %M), peak private
    bytes (Windows);
  - bytes stored for the offline passes (none yet);
  - whether the output passes vortex/check_output.py.
Results go to Docs/budget/<tag>.json; --render rebuilds Docs/BUDGET.md from all of them.

Usage:
  python -S benchmark.py [--rows 36000] [--runs 9] [--input FILE] [--tag NAME] [--commit SHA] [--gate]
                         [--cbin PATH]    # also the C core (main.cpp built to PATH): process, RSS, output
                         [--allow-rss]
  python benchmark.py --render
--gate exits 1 if a limit or design target is missed, for `python -S main.py` (bytecode cached):
  - peak RSS of the worst run (max, not median) <= 8,000,000 bytes: the stricter reading of "8 MB"
    (7.63 MiB), whole process (open question Q4);
  - wall ms per IMU-second <= 20, IMU seconds taken from the input's timestamps (not rows / 200);
  - process <= 50 us per row with -S (design target); tracemalloc <= 4 MB; output passes the checker.
With --cbin, the C core is gated the same way (worst-run RSS <= 8,000,000 bytes, <= 20 ms per IMU-s,
<= 50 us per row) and its output must be identical to main.py's and pass the checker.
--allow-rss skips only the RSS check of `python -S main.py` (never the C core's), for tracking the
Python fallback's timing; it prints "RSS NOT CHECKED", and that result is not a budget pass for
main.py. Timing gates are flaky: run on a quiet machine.
RSS is measured in MiB (2^20 bytes); the JSON keys say "mb" for history, the ledger says MiB.
"""
import importlib.util
import json
import os
import platform
import py_compile
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
from vortex.rowspec import BOM, is_data_line  # noqa: E402  (stdlib only)

OUT_DIR = os.path.join(ROOT, "Docs", "budget")
IMU_HZ = 200.0                # nominal rate; used only when the input has fewer than two timestamps
BUDGET_US_ROW, TARGET_US_ROW = 100.0, 50.0
BUDGET_MS_PER_S = 20.0
TARGET_TRACE_MB = 4.0
BUDGET_RSS_BYTES = 8_000_000  # "8 MB" read as decimal (stricter than 8 MiB); see the docstring
MIB = 2 ** 20                 # measure_floor reports peak RSS in MiB

# Stage switches passed to main.run, cumulative. Each new filter stage or witness adds a row here.
STAGES = [
    ("parse (read, split, 6 floats, timestamp)", {"write": False, "integrate": False}),
    ("parse + write (identity poses)", {"integrate": False}),
    ("parse + init + strapdown integrator", {"write": False}),
    ("parse + init + strapdown integrator + write (full main.py)", {}),
]
PASSES = ["calibration scan + backward pre-anchor pass + forward pass (no smoother yet)"]


def load_main():
    spec = importlib.util.spec_from_file_location("vortex_main_bench", os.path.join(ROOT, "pathfinder.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def imu_seconds(src):
    """Sensor time covered by the input: (max - min) integer ns timestamp of the data rows, times
    n / (n - 1) so n rows at period T count as n * T (36,000 rows at 200 Hz -> 180 s). Dropped rows
    inside a dropout still count as covered time. Returns (seconds, source); falls back to
    rows / IMU_HZ when fewer than two rows carry an integer timestamp."""
    lo = hi = None
    n = rows = 0
    with open(src, "rb") as f:
        for line in f:
            if not is_data_line(line):
                continue
            rows += 1
            s = line.split(b",", 1)[0].strip()
            if s[:3] == BOM:
                s = s[3:].strip()
            if not s.isdigit():
                continue
            t = int(s)
            n += 1
            if lo is None or t < lo:
                lo = t
            if hi is None or t > hi:
                hi = t
    if n < 2 or hi == lo:
        return rows / IMU_HZ, "rows / %.0f Hz (fewer than two distinct timestamps)" % IMU_HZ
    return (hi - lo) * 1e-9 * n / (n - 1), "timestamps"


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
    imu_s, imu_src = imu_seconds(src)

    res = {"platform": platform.system(), "platform_release": platform.release(),
           "cpu": measure_floor._cpu_name(), "python": platform.python_version(),
           "date": time.strftime("%Y-%m-%d"), "commit": a["commit"] or git_commit(),
           "input": label, "rows": n, "imu_seconds": imu_s, "imu_seconds_source": imu_src, "runs": runs}

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

    main.run(src, dst)
    res["stored_rows"] = main.LAST.get("pre_rows", 0)            # rows kept for the backward pass
    res["stored_bytes_per_block"] = 64                            # per stored row: 8 B time + 7 doubles
    res["stored_bytes_this_run"] = 64 * res["stored_rows"]
    res["stored_bytes_worst_case"] = 64 * main.PRE_MAX_ROWS

    procs = []
    stub, core = os.path.join(ROOT, "main.py"), os.path.join(ROOT, "pathfinder.py")
    # The bytecode the bundle ships (tools/make_bundle.py), written explicitly: a warm-up run would not
    # write it when PYTHONDONTWRITEBYTECODE is set (it was in the Windows shell used for step 9a).
    py_compile.compile(core, cfile=importlib.util.cache_from_source(core), doraise=True,
                       invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH)
    cold = tempfile.mkdtemp(prefix="vortex_nocache_")                     # empty: nothing cached, -B: none written
    for label_p, cmd in [("python -S main.py", [sys.executable, "-S", stub, src, dst]),
                         ("python main.py", [sys.executable, stub, src, dst]),
                         ("python -S main.py, no cached bytecode",
                          [sys.executable, "-S", "-B", "-X", "pycache_prefix=" + cold, stub, src, dst]),
                         ("python -S pathfinder.py", [sys.executable, "-S", core, src, dst])]:
        s = measure_floor.summarise(measure_floor.repeat(cmd, runs))
        s["case"] = label_p
        s["wall_ms_per_imu_s"] = s["wall_ms_median"] / imu_s
        s["cpu_ms_per_imu_s"] = s["cpu_ms_median"] / imu_s
        s["us_per_row"] = s["wall_ms_median"] * 1e3 / n
        procs.append(s)
        print("  %-18s %6.2f us/row  %5.2f ms/imu-s  rss %5.2f MiB"
              % (label_p, s["us_per_row"], s["wall_ms_per_imu_s"], s["peak_rss_mb_median"]))
    res["process"] = procs

    if a.get("cbin"):
        pdst = dst                                   # the runs above left main.py's output there
        cdst = dst + ".c"
        s = measure_floor.summarise(measure_floor.repeat([a["cbin"], src, cdst], runs))
        s["case"] = "C core (main.cpp)"
        s["wall_ms_per_imu_s"] = s["wall_ms_median"] / imu_s
        s["cpu_ms_per_imu_s"] = s["cpu_ms_median"] / imu_s
        s["us_per_row"] = s["wall_ms_median"] * 1e3 / n
        with open(pdst, "rb") as f1, open(cdst, "rb") as f2:
            s["output_identical_to_main_py"] = f1.read() == f2.read()
        c = check_output.check(src, cdst)
        s["output_check"] = "PASS" if c["ok"] else "FAIL: " + "; ".join(c["errors"][:3])
        res["ccore"] = s
        print("  %-18s %6.2f us/row  %5.2f ms/imu-s  rss %5.2f MiB  identical to main.py: %s  check: %s"
              % ("C core", s["us_per_row"], s["wall_ms_per_imu_s"], s["peak_rss_mb_median"],
                 s["output_identical_to_main_py"], s["output_check"]))

    chk = check_output.check(src, dst)
    res["output_check"] = "PASS" if chk["ok"] else "FAIL: " + "; ".join(chk["errors"][:3])
    print("  output check:", res["output_check"])
    return res


def _worst_rss(s):
    """Peak RSS of the worst run in MiB (older ledgers may only have the median)."""
    return s.get("peak_rss_mb_max", s.get("peak_rss_mb_median"))


def _rss_fail(s, who):
    worst = _worst_rss(s)
    if worst is None:
        return "%s peak RSS not measured" % who
    if worst * MIB > BUDGET_RSS_BYTES:
        return "%s peak RSS %.0f bytes (%.2f MiB) > %d bytes" % (who, worst * MIB, worst, BUDGET_RSS_BYTES)
    return None


def gate(res, rss=True):
    """Failures of `python -S main.py` (process[0]) and, if measured, the C core against the limits
    and design targets. rss=False skips only main.py's peak-RSS limit (see --allow-rss)."""
    fails = []
    p = res["process"][0]
    if rss:
        f = _rss_fail(p, "main.py")
        if f:
            fails.append(f)
    if p["wall_ms_per_imu_s"] > BUDGET_MS_PER_S:
        fails.append("process %.2f ms per IMU-s > %.0f" % (p["wall_ms_per_imu_s"], BUDGET_MS_PER_S))
    if p["us_per_row"] > TARGET_US_ROW:
        fails.append("process %.2f us/row > %.0f" % (p["us_per_row"], TARGET_US_ROW))
    if res["tracemalloc_peak_kb"] > TARGET_TRACE_MB * 1024:
        fails.append("tracemalloc %.0f KB > %.0f MB" % (res["tracemalloc_peak_kb"], TARGET_TRACE_MB))
    if res["output_check"] != "PASS":
        fails.append("output check failed")
    c = res.get("ccore")
    if c:
        f = _rss_fail(c, "C core")
        if f:
            fails.append(f)
        if c["wall_ms_per_imu_s"] > BUDGET_MS_PER_S:
            fails.append("C core %.2f ms per IMU-s > %.0f" % (c["wall_ms_per_imu_s"], BUDGET_MS_PER_S))
        if c["us_per_row"] > TARGET_US_ROW:
            fails.append("C core %.2f us/row > %.0f" % (c["us_per_row"], TARGET_US_ROW))
        if not c["output_identical_to_main_py"] or c["output_check"] != "PASS":
            fails.append("C core output differs from main.py or fails the checker")
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
         "Peak RSS is whole-process and in MiB (2^20 bytes). It includes the CPython interpreter: on our "
         "machines a bare `python -S` peaks at 8.4 MiB (WSL2, Python 3.12) and 9.5 MiB (Windows) before any "
         "work (`Docs/FLOOR.md`); other Python builds and OSes differ, so this floor is not universal. "
         "Whether the 8 MB limit means whole-process RSS, and MB or MiB, is open question Q4.",
         "`--gate` uses the strictest reading: the worst run's peak RSS <= 8,000,000 bytes (7.63 MiB). "
         "IMU seconds come from the input's timestamps (runs recorded before this change used rows / 200).",
         "`main.py` is a stub that imports `pathfinder.py`, so Python loads its cached bytecode instead of "
         "compiling it (step 9a); the process table also shows a run with no cached bytecode.",
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
          "| Peak RSS MiB (median / max) | Under 8,000,000 B | Peak private MiB | tracemalloc KB | Left of 4 MB "
          "| Output |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for tag, d in data:
        p = d["process"][0]
        worst = _worst_rss(p)
        under = "-" if worst is None else ("yes" if worst * MIB <= BUDGET_RSS_BYTES else "**NO**")
        L.append("| %s | %s | %s (%s) | %s | %s | %s | %s / %s | %s | %s | %s | %s KB | %s |" % (
            tag, _f(p["us_per_row"]), _f(BUDGET_US_ROW - p["us_per_row"], 1),
            _f(TARGET_US_ROW - p["us_per_row"], 1), _f(p["wall_ms_per_imu_s"]), _f(p["cpu_ms_per_imu_s"]),
            _f(BUDGET_MS_PER_S - p["wall_ms_per_imu_s"], 1), _f(p["peak_rss_mb_median"]), _f(worst), under,
            _f(p["peak_private_mb_median"]), _f(d["tracemalloc_peak_kb"], 1),
            _f(TARGET_TRACE_MB * 1024 - d["tracemalloc_peak_kb"], 0), d["output_check"]))
    L += ["", "## Summary: the C core (`main.cpp`) against the budget", "",
          "Runs measured with `--cbin`. Its output is compared byte for byte with `python -S main.py`'s.", "",
          "| Run | us per row | Wall ms per IMU-s | CPU ms per IMU-s | Peak RSS MiB (median / max) "
          "| Under 8,000,000 B | Peak private MiB | Same bytes as main.py | Output |",
          "|---|---|---|---|---|---|---|---|---|"]
    for tag, d in data:
        c = d.get("ccore")
        if not c:
            continue
        worst = _worst_rss(c)
        under = "-" if worst is None else ("yes" if worst * MIB <= BUDGET_RSS_BYTES else "**NO**")
        L.append("| %s | %s | %s | %s | %s / %s | %s | %s | %s | %s |" % (
            tag, _f(c["us_per_row"]), _f(c["wall_ms_per_imu_s"]), _f(c["cpu_ms_per_imu_s"]),
            _f(c["peak_rss_mb_median"]), _f(worst), under,
            _f(c["peak_private_mb_median"]), "yes" if c["output_identical_to_main_py"] else "NO",
            c["output_check"]))
    L += ["", "## Stages (in-process, cumulative, median us per row)", "",
          "| Run | Stage | us per row | min |", "|---|---|---|---|"]
    for tag, d in data:
        for s in d["stages"]:
            L.append("| %s | %s | %s | %s |" % (tag, s["stage"], _f(s["us_per_row"]), _f(s["us_per_row_min"])))
    L += ["", "## Passes", "", "| Run | Pass | us per row |", "|---|---|---|"]
    for tag, d in data:
        for s in d["passes"]:
            L.append("| %s | %s | %s |" % (tag, s["pass"], _f(s["us_per_row"])))
    L += ["", "## Witnesses", "",
          "The shipped witnesses (V1 stillness, V2 envelope and position prior; switches in `pathfinder.py`) "
          "run inside the forward pass: their cost is in the last stage row above, not timed separately.", "",
          "## Stored state for offline passes", "",
          "| Run | Bytes per stored row | Stored this run | Worst-case total bytes |", "|---|---|---|---|"]
    for tag, d in data:
        L.append("| %s | %d | %s | %d |" % (tag, d["stored_bytes_per_block"],
                                            "-" if "stored_bytes_this_run" not in d else
                                            "%d (%d rows)" % (d["stored_bytes_this_run"], d["stored_rows"]),
                                            d["stored_bytes_worst_case"]))
    L += ["", "## Process variants", "",
          "| Run | Command | us per row | Wall ms per IMU-s | Peak RSS MiB |", "|---|---|---|---|---|"]
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
         "commit": get("--commit", None),
         "cbin": os.path.abspath(get("--cbin", None)) if "--cbin" in argv else None}
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
        rss = "--allow-rss" not in argv
        fails = gate(res, rss=rss)
        verdict = "PASS" if not fails else "FAIL: " + "; ".join(fails)
        print("GATE:", verdict + ("" if rss else "  (RSS NOT CHECKED: not a budget pass)"))
        return 1 if fails else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

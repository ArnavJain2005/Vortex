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
                         [--cbin PATH]    # RECORDED EXPERIMENT ONLY: also time the old C core; never gated
  python benchmark.py --render
--gate exits 1 if a limit or design target is missed, for `python -S main.py` (bytecode cached):
  - heap peak (tracemalloc) <= 4 MB design target (organisers' limit 8 MB, measured at algorithm / heap
    level per the FAQ of 17 Nov 2026), taking the larger of two readings: pathfinder.run in-process,
    and the whole `main.py` run (import included, shipped bytecode cached) under tracemalloc in a fresh
    interpreter; and the same whole run WITHOUT cached bytecode (pathfinder.py compiled while traced,
    about 4 MB of parser/compiler heap) <= the 8 MB limit;
  - wall ms per IMU-second <= 20, IMU seconds taken from the input's timestamps (not rows / 200);
  - process <= 50 us per row with -S (design target); output passes the checker.
Peak RSS is still measured and reported, but not gated: the FAQ says the interpreter is not counted.
--allow-rss is accepted and ignored (older command lines). Timing gates are flaky: run on a quiet machine.
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
TARGET_TRACE_MB = 4.0          # design target (2x margin) on the heap peak
BUDGET_HEAP_BYTES = 8_000_000  # organisers' 8 MB, algorithm / heap level (FAQ, 17 Nov), read as decimal
BUDGET_RSS_BYTES = 8_000_000   # reported only (the old whole-process reading); not gated since the FAQ
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


HEAP_PROBE = (
    "import runpy, sys, tracemalloc\n"
    "tracemalloc.start()\n"
    "sys.argv = sys.argv[1:]\n"
    "try:\n"
    "    runpy.run_path(sys.argv[0], run_name='__main__')\n"
    "except SystemExit as e:\n"
    "    code = e.code\n"
    "else:\n"
    "    code = 0\n"
    "peak = tracemalloc.get_traced_memory()[1]\n"
    "tracemalloc.stop()\n"
    "print('HEAP_PEAK', peak, code)\n")


def heap_peak_process(stub, src, dst, no_cache_dir=None):
    """tracemalloc peak in bytes of a whole `python -S main.py SRC DST` run in a fresh interpreter,
    tracing from before main.py runs (so importing pathfinder, the file buffers and every list count).
    With no_cache_dir (an empty folder) no cached bytecode is found or written, so pathfinder.py is
    compiled inside the traced run: the parser and compiler allocate on the traced heap (about 4 MB).
    Returns (peak_bytes, exit_code)."""
    extra = ["-B", "-X", "pycache_prefix=" + no_cache_dir] if no_cache_dir else []
    p = subprocess.run([sys.executable, "-S"] + extra + ["-c", HEAP_PROBE, stub, src, dst],
                       capture_output=True, text=True, timeout=600)
    for line in p.stdout.splitlines():
        if line.startswith("HEAP_PEAK "):
            _, peak, code = line.split()
            return int(peak), (0 if code == "None" else int(code))
    raise RuntimeError("heap probe failed: %s" % p.stderr[-500:])


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
    peak, code = heap_peak_process(stub, src, dst)
    res["tracemalloc_process_peak_kb"] = peak / 1024.0
    peak_c, code_c = heap_peak_process(stub, src, dst, no_cache_dir=cold)
    res["tracemalloc_process_nocache_peak_kb"] = peak_c / 1024.0
    print("  tracemalloc peak, whole main.py run: %.1f KB with the shipped bytecode, %.1f KB compiling "
          "pathfinder.py (exit %d, %d)" % (peak / 1024.0, peak_c / 1024.0, code, code_c))
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


def heap_kb(res):
    """The gated heap peak: the larger of the in-process and whole-run tracemalloc readings (KB)."""
    return max(res["tracemalloc_peak_kb"], res.get("tracemalloc_process_peak_kb") or 0.0)


def gate(res, rss=None):
    """Failures of `python -S main.py` (process[0]) against the limits and design targets. Memory is
    gated at heap level (tracemalloc), as the organisers measure it (FAQ, 17 Nov 2026); peak RSS and the
    old C core (--cbin) are reported only. `rss` is accepted for old callers and ignored."""
    fails = []
    p = res["process"][0]
    heap = heap_kb(res)
    cold = res.get("tracemalloc_process_nocache_peak_kb")
    if heap * 1024 > BUDGET_HEAP_BYTES:
        fails.append("heap peak %.0f bytes > %d bytes (8 MB limit)" % (heap * 1024, BUDGET_HEAP_BYTES))
    elif heap > TARGET_TRACE_MB * 1024:
        fails.append("heap peak %.0f KB > %.0f MB design target" % (heap, TARGET_TRACE_MB))
    if cold is not None and cold * 1024 > BUDGET_HEAP_BYTES:
        fails.append("heap peak without cached bytecode %.0f bytes > %d bytes (8 MB limit)"
                     % (cold * 1024, BUDGET_HEAP_BYTES))
    if p["wall_ms_per_imu_s"] > BUDGET_MS_PER_S:
        fails.append("process %.2f ms per IMU-s > %.0f" % (p["wall_ms_per_imu_s"], BUDGET_MS_PER_S))
    if p["us_per_row"] > TARGET_US_ROW:
        fails.append("process %.2f us/row > %.0f" % (p["us_per_row"], TARGET_US_ROW))
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
         "Our design targets (2x margin for an unknown evaluator CPU): 50 us per row; 4 MB heap peak.",
         "",
         "**Memory is gated at heap level** (organisers' FAQ, 17 Nov 2026: the 8 MB is measured at algorithm "
         "/ heap level, not process RSS). The gated number is the larger of two tracemalloc peaks: "
         "`pathfinder.run` in-process, and the whole `python -S main.py` run in a fresh interpreter with "
         "tracing started before `main.py` runs (import of the estimator from its shipped bytecode "
         "included). The same whole run with no cached bytecode compiles `pathfinder.py` while traced; "
         "the parser and compiler then add about 4 MB, so that reading is held to the 8 MB limit only. "
         "Runs recorded before 17 Nov have only the first reading.",
         "Peak RSS (whole process, MiB = 2^20 bytes) is still reported for the record; it includes the "
         "CPython interpreter (8.4 to 9.7 MiB bare on our machines, `Docs/FLOOR.md`) and is not gated.",
         "`main.py` is a stub that imports `pathfinder.py`, so Python loads its cached bytecode instead of "
         "compiling it (step 9a); the process table also shows a run with no cached bytecode.",
         "The C core (`main.cpp`, step 9b) is a recorded experiment: the organisers accept Python only. Its "
         "rows below are history.",
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
          "| Heap peak KB in-process / whole run | Left of 4 MB target | Heap KB, whole run, no cached bytecode "
          "| Peak RSS MiB (median / max, not gated) | Peak private MiB | Output |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for tag, d in data:
        p = d["process"][0]
        worst = _worst_rss(p)
        L.append("| %s | %s | %s (%s) | %s | %s | %s | %s / %s | %s KB | %s | %s / %s | %s | %s |" % (
            tag, _f(p["us_per_row"]), _f(BUDGET_US_ROW - p["us_per_row"], 1),
            _f(TARGET_US_ROW - p["us_per_row"], 1), _f(p["wall_ms_per_imu_s"]), _f(p["cpu_ms_per_imu_s"]),
            _f(BUDGET_MS_PER_S - p["wall_ms_per_imu_s"], 1), _f(d["tracemalloc_peak_kb"], 1),
            _f(d.get("tracemalloc_process_peak_kb"), 1), _f(TARGET_TRACE_MB * 1024 - heap_kb(d), 0),
            _f(d.get("tracemalloc_process_nocache_peak_kb"), 1), _f(p["peak_rss_mb_median"]), _f(worst), _f(p["peak_private_mb_median"]), d["output_check"]))
    L += ["", "## Recorded experiment: the C core (`main.cpp`), not submitted", "",
          "Runs measured with `--cbin` (step 9b, step A). Its output is compared byte for byte with "
          "`python -S main.py`'s. Not part of the gate since the FAQ of 17 Nov 2026 (Python only).", "",
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
        fails = gate(res)
        verdict = "PASS" if not fails else "FAIL: " + "; ".join(fails)
        print("GATE:", verdict + "  (memory gated at heap level; peak RSS %.2f MiB reported, not gated)"
              % (_worst_rss(res["process"][0]) or -1))
        return 1 if fails else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

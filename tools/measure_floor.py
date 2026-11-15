"""Measure the efficiency floor: what the interpreter and the bare I/O path cost before any estimator.

Stdlib only (no psutil). Each child process is measured from outside:
  Windows: GetProcessMemoryInfo (PeakWorkingSetSize = peak RSS, PeakPagefileUsage = peak private
           commit) and GetProcessTimes (user + kernel CPU), via ctypes.
  Linux:   os.wait4 rusage of that one child (ru_maxrss = peak RSS, ru_utime + ru_stime = CPU).
Wall time is perf_counter around spawn + wait, so it includes process creation.

Writes Docs/floor/<platform>-py<ver>.json. `--render` rebuilds Docs/FLOOR.md from every JSON there.

Usage:
  python tools/measure_floor.py [--input FILE] [--rows 36000] [--runs 25] [--cbin PATH] [--tag NAME]
  python tools/measure_floor.py --render
"""
import glob
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT_DIR = os.path.join(REPO, "Docs", "floor")
IMU_HZ = 200.0

sys.path.insert(0, HERE)
import synth_euroc  # noqa: E402

# --------------------------------------------------------------------------- process measurement

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class _PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    _k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4

    def _ft(ft):
        return ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) * 1e-7

    def run_measured(cmd):
        t0 = time.perf_counter()
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        wall = time.perf_counter() - t0
        h = wintypes.HANDLE(int(p._handle))   # still open after wait; closed when p is collected
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(_PMC)
        if not _k32.K32GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
            raise OSError(ctypes.get_last_error())
        c, e, k, u = (wintypes.FILETIME() for _ in range(4))
        _k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u))
        return {"rc": p.returncode, "wall_s": wall, "cpu_s": _ft(k) + _ft(u),
                "peak_rss_mb": pmc.PeakWorkingSetSize / 2**20,
                "peak_private_mb": pmc.PeakPagefileUsage / 2**20,
                "stdout": out.decode(errors="replace"), "stderr": err.decode(errors="replace")}
else:
    # Linux carries a process's RSS high-water mark across fork/vfork + exec (signal->maxrss is
    # seeded from the old mm at exec), so wait4() on a child of this ~15 MB Python harness reports
    # the HARNESS's peak, not the child's. GNU time is a ~2 MB C program: its child inherits only
    # that, and %M is the child's true peak RSS (the way an evaluator would likely measure it).
    GNU_TIME = "/usr/bin/time"

    def run_measured(cmd):
        if not os.path.exists(GNU_TIME):
            raise RuntimeError("needs GNU time at /usr/bin/time (apt install time)")
        t0 = time.perf_counter()
        p = subprocess.run([GNU_TIME, "-f", "VORTEXTIME %M %U %S"] + cmd, capture_output=True)
        wall = time.perf_counter() - t0
        err = p.stderr.decode(errors="replace")
        tail = [l for l in err.splitlines() if l.startswith("VORTEXTIME ")][-1].split()
        return {"rc": p.returncode, "wall_s": wall, "cpu_s": float(tail[2]) + float(tail[3]),
                "peak_rss_mb": int(tail[1]) / 1024.0,   # GNU time %M is KiB
                "peak_private_mb": None,
                "stdout": p.stdout.decode(errors="replace"), "stderr": err}


def repeat(cmd, runs):
    rs = []
    for _ in range(runs):
        r = run_measured(cmd)
        if r["rc"] != 0:
            raise RuntimeError("%s failed rc=%s: %s" % (cmd, r["rc"], r["stderr"][-500:]))
        rs.append(r)
    return rs


def med(rs, key):
    vals = [r[key] for r in rs if r[key] is not None]
    return statistics.median(vals) if vals else None


def summarise(rs):
    return {"runs": len(rs),
            "wall_ms_median": med(rs, "wall_s") * 1e3,
            "wall_ms_min": min(r["wall_s"] for r in rs) * 1e3,
            "cpu_ms_median": med(rs, "cpu_s") * 1e3,
            "peak_rss_mb_median": med(rs, "peak_rss_mb"),
            "peak_rss_mb_max": max(r["peak_rss_mb"] for r in rs),
            "peak_private_mb_median": med(rs, "peak_private_mb")}


# --------------------------------------------------------------------------- experiments

def interpreter_floor(py, runs):
    cases = [
        ("python -c pass", [py, "-c", "pass"]),
        ("python -S -c pass", [py, "-S", "-c", "pass"]),
        ("python -I -S -c pass", [py, "-I", "-S", "-c", "pass"]),
        ("python -S -c 'import math, array'", [py, "-S", "-c", "import math, array"]),
        ("python -S -c 'import math, array, json'", [py, "-S", "-c", "import math, array, json"]),
    ]
    out = []
    for label, cmd in cases:
        s = summarise(repeat(cmd, runs))
        s["case"] = label
        out.append(s)
        print("  %-42s wall %6.1f ms  rss %5.2f MB" % (label, s["wall_ms_median"], s["peak_rss_mb_median"]))
    return out


def worker_runs(cmd_base, label, src, rows, runs, extra=()):
    dst = os.path.join(tempfile.gettempdir(), "vortex_floor_out.txt")
    rs = repeat(cmd_base + [src, dst] + list(extra), runs)
    s = summarise(rs)
    s["case"] = label
    loops = []
    for r in rs:
        line = r["stdout"].strip()
        if line:
            loops.append(json.loads(line))
    if loops:
        s["rows"] = loops[0]["rows"]
        s["loop_us_per_row_median"] = statistics.median(l["loop_wall_s"] for l in loops) / max(rows, 1) * 1e6
        s["loop_us_per_row_min"] = min(l["loop_wall_s"] for l in loops) / max(rows, 1) * 1e6
    imu_s = rows / IMU_HZ
    s["proc_wall_ms_per_imu_s"] = s["wall_ms_median"] / imu_s
    s["proc_cpu_ms_per_imu_s"] = s["cpu_ms_median"] / imu_s
    s["proc_wall_us_per_row"] = s["wall_ms_median"] * 1e3 / rows
    if os.path.exists(dst):
        s["out_bytes"] = os.path.getsize(dst)
    return s


def run_all(args):
    py = sys.executable
    rows = args["rows"]
    runs = args["runs"]
    tmp = tempfile.gettempdir()
    src = args["input"]
    label = "real"
    if not src:
        src = os.path.join(tmp, "vortex_synth_%d.csv" % rows)
        synth_euroc.write(src, rows=rows, seed=0)
        label = "SYNTHETIC (tools/synth_euroc.py seed 0, repr doubles)"
    src6 = os.path.join(tmp, "vortex_synth_%d_6dp.csv" % rows)
    synth_euroc.write(src6, rows=rows, seed=0, decimals=6)

    res = {"platform": platform.system(), "platform_release": platform.release(),
           "machine": platform.machine(), "cpu": _cpu_name(), "python": platform.python_version(),
           "python_impl": platform.python_implementation(), "date": time.strftime("%Y-%m-%d"),
           "input": label, "input_bytes": os.path.getsize(src), "rows": rows,
           "imu_seconds": rows / IMU_HZ, "runs": runs}

    print("Interpreter floor (%s, %d runs each)" % (py, runs))
    res["interpreter"] = interpreter_floor(py, runs)

    wk = [py, "-S", os.path.join(HERE, "floor_worker.py")]
    wruns = max(5, runs // 3)
    print("I/O path, %d rows, %d runs each" % (rows, wruns))
    io = []
    for mode in ["noop", "read", "parse_bytes", "parse_str", "pw_bytes_id", "pw_str_id",
                 "pw_bytes_real", "pw_str_real"]:
        s = worker_runs(wk + [mode], mode, src, rows, wruns)
        tr = run_measured(wk + [mode, src, os.path.join(tmp, "vortex_floor_out.txt"), "--trace"])
        s["tracemalloc_peak_kb"] = json.loads(tr["stdout"])["tracemalloc_peak"] / 1024.0
        io.append(s)
        print("  %-14s loop %6.2f us/row  proc %6.2f ms/imu-s  rss %5.2f MB  tracemalloc %6.1f KB"
              % (mode, s.get("loop_us_per_row_median", 0), s["proc_wall_ms_per_imu_s"],
                 s["peak_rss_mb_median"], s["tracemalloc_peak_kb"]))
    res["io"] = io

    # same pipeline with site enabled (no -S), to see what site costs on a real run
    s = worker_runs([py, os.path.join(HERE, "floor_worker.py"), "pw_bytes_real"],
                    "pw_bytes_real (no -S)", src, rows, wruns)
    res["io_with_site"] = s
    print("  pw_bytes_real without -S: proc %6.2f ms/imu-s  rss %5.2f MB"
          % (s["proc_wall_ms_per_imu_s"], s["peak_rss_mb_median"]))

    # 6-decimal input: does field length change parse cost?
    s = worker_runs(wk + ["pw_bytes_real"], "pw_bytes_real, 6-decimal input", src6, rows, wruns)
    res["io_6dp"] = s
    print("  pw_bytes_real 6dp input: loop %6.2f us/row" % s["loop_us_per_row_median"])

    print("Read buffer sweep")
    sweep = []
    for b in [8192, 65536, 262144, 1048576]:
        s = worker_runs(wk + ["pw_bytes_real"], "pw_bytes_real buf=%d" % b, src, rows, wruns,
                        ["--buf", str(b)])
        s["buf"] = b
        sweep.append(s)
        print("  buf %8d: loop %6.2f us/row  rss %5.2f MB" % (b, s["loop_us_per_row_median"],
                                                          s["peak_rss_mb_median"]))
    res["buf_sweep"] = sweep

    print("Output chunk sweep (lines per write)")
    csweep = []
    for c in [64, 256, 1024, 4096]:
        s = worker_runs(wk + ["pw_bytes_real"], "pw_bytes_real chunk=%d" % c, src, rows, wruns,
                        ["--chunk", str(c)])
        tr = run_measured(wk + ["pw_bytes_real", src, os.path.join(tmp, "vortex_floor_out.txt"),
                                "--chunk", str(c), "--trace"])
        s["tracemalloc_peak_kb"] = json.loads(tr["stdout"])["tracemalloc_peak"] / 1024.0
        s["chunk"] = c
        csweep.append(s)
        print("  chunk %5d: loop %6.2f us/row  rss %5.2f MB  tracemalloc %6.1f KB"
              % (c, s["loop_us_per_row_median"], s["peak_rss_mb_median"], s["tracemalloc_peak_kb"]))
    res["chunk_sweep"] = csweep

    if args["cbin"]:
        print("C++ floor (%s)" % args["cbin"])
        cres = []
        for mode in ["noop", "pw_id", "pw_real"]:
            s = worker_runs([args["cbin"], mode], "c++ " + mode, src, rows, wruns)
            cres.append(s)
            print("  %-8s proc %6.2f ms/imu-s  %6.2f us/row  rss %5.2f MB"
                  % (mode, s["proc_wall_ms_per_imu_s"], s["proc_wall_us_per_row"], s["peak_rss_mb_median"]))
        res["cxx"] = cres

    os.makedirs(OUT_DIR, exist_ok=True)
    tag = args["tag"] or "%s-py%s" % (platform.system().lower(), "".join(platform.python_version_tuple()[:2]))
    path = os.path.join(OUT_DIR, tag + ".json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(res, f, indent=1, sort_keys=True)
        f.write("\n")
    print("wrote", os.path.relpath(path, REPO))


def _cpu_name():
    try:
        if os.name == "nt":
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor()


# --------------------------------------------------------------------------- render

def _f(x, d=2):
    return "-" if x is None else ("%.*f" % (d, x))


def render():
    files = sorted(glob.glob(os.path.join(OUT_DIR, "*.json")))
    data = [json.load(open(p, encoding="utf-8")) for p in files]
    L = ["# Efficiency floor (generated by `tools/measure_floor.py --render`; do not edit by hand)", ""]
    L.append("Budget: 100 us per row at 200 Hz (20 ms per IMU-second), peak RAM 8 MB.")
    L.append("Design target: 50 us per row, 4 MB tracemalloc peak.")
    L.append("")
    L.append("Peak RSS: Windows = PeakWorkingSetSize, private = PeakPagefileUsage (GetProcessMemoryInfo); "
             "Linux = GNU time %M (wait4 on a child of the Python harness is wrong: Linux seeds the "
             "child's maxrss with the parent's at exec). CPU time comes in clock ticks (Windows 15.6 ms, "
             "GNU time 10 ms), so CPU for processes shorter than ~50 ms is quantised; trust wall time there. "
             "Timing varies about +-15% between reruns on this laptop.")
    L.append("")
    L.append("## Machines")
    L.append("")
    L.append("| Run | OS | CPU | Python | Input | Rows |")
    L.append("|---|---|---|---|---|---|")
    for p, d in zip(files, data):
        L.append("| %s | %s %s | %s | %s | %s | %d (%.0f s) |" % (
            os.path.basename(p)[:-5], d["platform"], d["platform_release"], d["cpu"], d["python"],
            d["input"], d["rows"], d["imu_seconds"]))
    L.append("")
    L.append("## Interpreter alone (median of N runs)")
    L.append("")
    L.append("| Run | Command | Wall ms | CPU ms | Peak RSS MB | Peak private MB |")
    L.append("|---|---|---|---|---|---|")
    for p, d in zip(files, data):
        for s in d["interpreter"]:
            L.append("| %s | `%s` | %s | %s | %s | %s |" % (
                os.path.basename(p)[:-5], s["case"], _f(s["wall_ms_median"], 1), _f(s["cpu_ms_median"], 1),
                _f(s["peak_rss_mb_median"]), _f(s["peak_private_mb_median"])))
    L.append("")
    L.append("## I/O path (worker run with `python -S`)")
    L.append("")
    L.append("Loop = in-process time of the read/parse/write loop only. Process = whole process incl. "
             "interpreter start, measured from outside.")
    L.append("")
    L.append("| Run | Mode | Loop us/row | Process us/row | Process wall ms per IMU-s | Process CPU ms per IMU-s "
             "| Peak RSS MB | tracemalloc peak KB |")
    L.append("|---|---|---|---|---|---|---|---|")
    for p, d in zip(files, data):
        rows = d["io"] + [d["io_with_site"], d["io_6dp"]] + d.get("cxx", [])
        for s in rows:
            L.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
                os.path.basename(p)[:-5], s["case"], _f(s.get("loop_us_per_row_median")),
                _f(s["proc_wall_us_per_row"]), _f(s["proc_wall_ms_per_imu_s"]), _f(s["proc_cpu_ms_per_imu_s"]),
                _f(s["peak_rss_mb_median"]), _f(s.get("tracemalloc_peak_kb"), 1)))
    L.append("")
    L.append("## Read buffer size (pw_bytes_real)")
    L.append("")
    L.append("| Run | Buffer bytes | Loop us/row | Peak RSS MB |")
    L.append("|---|---|---|---|")
    for p, d in zip(files, data):
        for s in d["buf_sweep"]:
            L.append("| %s | %d | %s | %s |" % (os.path.basename(p)[:-5], s["buf"],
                                                 _f(s["loop_us_per_row_median"]), _f(s["peak_rss_mb_median"])))
    L.append("")
    L.append("## Output chunk size (pw_bytes_real, lines joined per write)")
    L.append("")
    L.append("| Run | Lines per write | Loop us/row | Peak RSS MB | tracemalloc peak KB |")
    L.append("|---|---|---|---|---|")
    for p, d in zip(files, data):
        for s in d.get("chunk_sweep", []):
            L.append("| %s | %d | %s | %s | %s |" % (os.path.basename(p)[:-5], s["chunk"],
                                                      _f(s["loop_us_per_row_median"]), _f(s["peak_rss_mb_median"]),
                                                      _f(s["tracemalloc_peak_kb"], 1)))
    L.append("")
    path = os.path.join(REPO, "Docs", "FLOOR.md")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))
    print("wrote", os.path.relpath(path, REPO))


def main(argv):
    if "--render" in argv:
        render()
        return 0
    get = lambda k, d: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    run_all({"input": get("--input", None), "rows": int(get("--rows", 36000)), "runs": int(get("--runs", 25)),
             "cbin": get("--cbin", None), "tag": get("--tag", None)})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

"""Rule K (Docs/TRACK3_PLAN.md, "Freeze build"): measure the PLAIN and CHUNKED bundle layouts. Stdlib only.

    python tools/bundle_layouts.py measure [--data data] [--runs 5]
        Under THIS Python, for each layout and each input (MH_01_easy_b_s1, MH_01_easy_a_s1, the longest
        official copy MH_01_easy_a_s3, dataset-room1_512_16_b_s1): the whole-run tracemalloc peak with the
        bundle compiled from source (tracing started before the file is compiled; no bytecode of ours
        exists), the same under `python -X tracemalloc=1 -S main.py IN OUT` (tracing from start-up), the
        estimator-only peak (pathfinder.run in-process, compile excluded), and us per row
        (median wall time of --runs runs of `python -S main.py IN OUT`, the two layouts interleaved). Also the compile-only peak of the
        largest CHUNKED chunk. Writes Docs/bundle/matrix-<os>-py<ver>.json.
    python tools/bundle_layouts.py identity [--data data]
        Under THIS Python: the repo build (`python -S main.py`, which imports pathfinder.py), PLAIN and
        CHUNKED on every official and clean copy on disk; V2_* and TUM-VI rooms 5-6 excluded (final test data). Writes
        Docs/bundle/identity-<os>-py<ver>.json; exit 1 on any difference.
"""
import argparse
import glob
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
import make_bundle  # noqa: E402

OUT = os.path.join(ROOT, "Docs", "bundle")
INPUTS = [("official", "MH_01_easy_b_s1"), ("official", "MH_01_easy_a_s1"), ("official", "MH_01_easy_a_s3"),
          ("official_tumvi", "dataset-room1_512_16_b_s1")]
FINAL = ("V2_", "dataset-room5", "dataset-room6")   # EuRoC V2_01..03 and TUM-VI rooms 5-6: final test data
PROBE = ("import runpy, sys, tracemalloc\ntracemalloc.start()\nsys.argv = sys.argv[1:]\n"
         "try:\n    runpy.run_path(sys.argv[0], run_name='__main__')\nexcept SystemExit as e:\n    code = e.code\n"
         "else:\n    code = 0\nprint('HEAP_PEAK', tracemalloc.get_traced_memory()[1], code)\n")


def _tag():
    return "%s-py%s" % (platform.system().lower(), "".join(platform.python_version_tuple()[:2]))


def _imu(d):
    return os.path.join(d, "mav0", "imu0", "data.csv")


def _sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _bundles(tmp):
    out = {}
    for layout in make_bundle.LAYOUTS:
        p = os.path.join(tmp, "%s_main.py" % layout)
        make_bundle.write_single(p, layout)
        out[layout] = p
    return out


def whole_run_peak(bundle, imu, dst):
    """tracemalloc peak of a whole run, tracing started before the bundle is compiled. Standard-library
    bytecode is used as normal (an evaluator's Python has it); the bundle itself has none."""
    p = subprocess.run([sys.executable, "-S", "-c", PROBE, bundle, imu, dst], capture_output=True, text=True,
                       timeout=1800)
    for line in p.stdout.splitlines():
        if line.startswith("HEAP_PEAK "):
            _, peak, code = line.split()
            return int(peak), int(code) if code != "None" else 0
    raise RuntimeError(p.stderr[-400:])


XWRAP = ("import runpy, sys, tracemalloc\nsys.argv = sys.argv[1:]\n"
         "try:\n    runpy.run_path(sys.argv[0], run_name='__main__')\nexcept SystemExit:\n    pass\n"
         "print('XPEAK', tracemalloc.get_traced_memory()[1])\n")


def x_tracemalloc_peak(bundle, imu, dst):
    """`python -X tracemalloc=1 -S main.py IN OUT` with a peak report: tracing from interpreter start-up."""
    p = subprocess.run([sys.executable, "-X", "tracemalloc=1", "-S", "-c", XWRAP, bundle, imu, dst],
                       capture_output=True, text=True, timeout=1800)
    for line in p.stdout.splitlines():
        if line.startswith("XPEAK "):
            return int(line.split()[1])
    raise RuntimeError(p.stderr[-400:])


def estimator_only_peak(imu, dst):
    import importlib.util
    spec = importlib.util.spec_from_file_location("vortex_pf_measure", os.path.join(ROOT, "pathfinder.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tracemalloc.start()
    rows = mod.run(imu, dst)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return peak, rows


def largest_chunk_compile():
    src, tree = make_bundle._entry_free_source()
    worst = (0, "")
    for a, b, line in make_bundle._chunks(src, tree, make_bundle.CHUNK_LINES):
        text = "\n" * (line - 1) + src[a:b]
        tracemalloc.start()
        code = compile(text, "main.py", "exec")
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        del code
        if peak > worst[0]:
            name = next((s.split("(")[0][4:] for s in src[a:b].split("\n") if s.startswith("def ")), "?")
            worst = (peak, name)
    return worst


def measure(data, runs):
    tmp = tempfile.mkdtemp(prefix="vx_layouts_")
    bundles = _bundles(tmp)
    dst = os.path.join(tmp, "out.txt")
    res = {"python": platform.python_version(), "os": "%s %s" % (platform.system(), platform.release()),
           "date": time.strftime("%Y-%m-%d"), "commit": make_bundle._commit(), "chunk_lines": make_bundle.CHUNK_LINES,
           "runs": runs, "rows": []}
    cpk, cname = largest_chunk_compile()
    res["largest_chunk_compile_kb"] = cpk / 1024.0
    res["largest_chunk_function"] = cname
    print("python %s: largest CHUNKED chunk (%s) compiles at %.0f KB" % (res["python"], cname, cpk / 1024.0))
    for sub, name in INPUTS:
        imu = _imu(os.path.join(data, sub, name))
        if not os.path.exists(imu):
            print("missing", imu)
            continue
        est, rows = estimator_only_peak(imu, dst)
        row = {"input": name, "rows": rows, "estimator_only_kb": est / 1024.0}
        ts = {layout: [] for layout in bundles}
        for _ in range(runs):                        # interleaved, so machine load hits both layouts alike
            for layout, b in bundles.items():
                t0 = time.perf_counter()
                subprocess.run([sys.executable, "-S", b, imu, dst], check=True)
                ts[layout].append(time.perf_counter() - t0)
        for layout, b in bundles.items():
            peak, code = whole_run_peak(b, imu, dst)
            xpeak = x_tracemalloc_peak(b, imu, dst)
            row[layout] = {"whole_run_kb": peak / 1024.0, "x_tracemalloc_kb": xpeak / 1024.0, "exit": code,
                           "us_per_row": statistics.median(ts[layout]) / rows * 1e6, "sha256": _sha(dst)}
        row["same_output"] = row["plain"]["sha256"] == row["chunked"]["sha256"]
        res["rows"].append(row)
        print("%-28s rows %6d  estimator-only %6.0f KB | PLAIN %6.0f KB (-X %6.0f) %6.2f us/row | CHUNKED %6.0f KB "
              "(-X %6.0f) %6.2f us/row | same output %s"
              % (name, rows, est / 1024.0, row["plain"]["whole_run_kb"], row["plain"]["x_tracemalloc_kb"],
                 row["plain"]["us_per_row"], row["chunked"]["whole_run_kb"], row["chunked"]["x_tracemalloc_kb"],
                 row["chunked"]["us_per_row"], row["same_output"]), flush=True)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "matrix-%s.json" % _tag())
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(res, f, indent=1, sort_keys=True)
        f.write("\n")
    print("wrote", os.path.relpath(path, ROOT))
    return 0


def _copies(data):
    out = []
    for sub in ("official", "official_tumvi", "euroc", "tumvi"):
        for d in sorted(glob.glob(os.path.join(data, sub, "*"))):
            n = os.path.basename(d)
            if n.startswith(FINAL):                   # final test sets: never read
                continue
            if os.path.exists(_imu(d)):
                out.append(("%s/%s" % (sub, n), _imu(d)))
    return out


def identity(data):
    tmp = tempfile.mkdtemp(prefix="vx_ident_")
    bundles = _bundles(tmp)
    copies = _copies(data)
    diffs, n = [], 0
    for name, imu in copies:
        outs = {}
        for label, cmd in (("repo", [sys.executable, "-S", os.path.join(ROOT, "main.py")]),
                           ("plain", [sys.executable, "-S", bundles["plain"]]),
                           ("chunked", [sys.executable, "-S", bundles["chunked"]])):
            dst = os.path.join(tmp, label + ".txt")
            p = subprocess.run(cmd + [imu, dst], capture_output=True, text=True)
            outs[label] = (p.returncode, _sha(dst) if p.returncode == 0 else None, p.stderr.strip()[:200])
        same = len({v[1] for v in outs.values()}) == 1 and all(v[0] == 0 and not v[2] for v in outs.values())
        n += 1
        if not same:
            diffs.append({"copy": name, "results": outs})
            print("DIFFERS", name, outs)
        if n % 25 == 0:
            print("%d/%d copies, %d differences" % (n, len(copies), len(diffs)), flush=True)
    res = {"python": platform.python_version(), "os": "%s %s" % (platform.system(), platform.release()),
           "date": time.strftime("%Y-%m-%d"), "commit": make_bundle._commit(), "chunk_lines": make_bundle.CHUNK_LINES,
           "copies": n, "identical": n - len(diffs), "differences": diffs,
           "copy_names": [c[0] for c in copies]}
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "identity-%s.json" % _tag())
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(res, f, indent=1, sort_keys=True)
        f.write("\n")
    print("IDENTITY: %s (%d of %d copies identical across repo build, PLAIN and CHUNKED; Python %s); wrote %s"
          % ("PASS" if not diffs else "FAIL", n - len(diffs), n, res["python"], os.path.relpath(path, ROOT)))
    return 0 if not diffs else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["measure", "identity"])
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--runs", type=int, default=11)
    a = ap.parse_args(argv)
    return measure(a.data, a.runs) if a.cmd == "measure" else identity(a.data)


if __name__ == "__main__":
    sys.exit(main())

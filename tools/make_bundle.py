"""Build the submission zip (step 9). Stdlib only. Layout (PRD, "Deliverables"; Python only per the
organisers' FAQ of 17 Nov 2026, so the C core main.cpp is not shipped):

    estimated_trajectory.txt   our output for the organisers' evaluation input (from `eval`)
    metadata.json              runtime, memory and compute specs of that run (from `eval`)
    src/main.py, src/pathfinder.py, src/__pycache__/pathfinder.cpython-3XX.pyc   Python entry point
    README.md, Dockerfile, LICENSE, MANIFEST.txt

    python tools/make_bundle.py stage [--dir dist/stage]
        Copies the files into the stage folder and compiles pathfinder.py to a hash-checked .pyc for
        THIS Python (valid whatever the file times are after unzipping). Run it once with each Python
        the bundle should carry bytecode for, e.g. py -3.13, py -3.14, and python3 in WSL.
    python tools/make_bundle.py eval IMU.csv [--dir dist/stage] [--runs 5]
        Runs `python -S src/main.py` on the evaluation input: writes estimated_trajectory.txt and
        metadata.json into the stage (time and peak RSS measured as benchmark.py does, and the heap
        peak with tracemalloc, the level the organisers measure).
    python tools/make_bundle.py zip --name NAME [--dir dist/stage] [--out dist]
        Writes dist/NAME.zip (sorted, fixed entry times) and MANIFEST.txt.
    python tools/make_bundle.py verify dist/NAME.zip
        Extracts it and, on a SYNTHETIC file: `python -I -S src/main.py` twice (output equal to the
        repo's pathfinder.py, checker PASS, shipped bytecode loaded if there is one for this Python), and
        a zip that still carries src/main.cpp is refused.

A stage folder whose sources differ from the repo's is refused (delete it and stage again).
"""
import argparse
import datetime
import hashlib
import json
import os
import platform
import py_compile
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

FILES = [("main.py", "src/main.py"), ("pathfinder.py", "src/pathfinder.py"),
         ("bundle/README.md", "README.md"), ("bundle/Dockerfile", "Dockerfile"), ("LICENSE", "LICENSE")]
EVAL_FILES = ["estimated_trajectory.txt", "metadata.json"]
NOT_SHIPPED = ["src/main.cpp"]   # the C core is a recorded experiment (FAQ: Python only)
ZIP_TIME = (2026, 11, 20, 0, 0, 0)


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _tag():
    return sys.implementation.cache_tag      # e.g. cpython-314


def _commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True).stdout.strip() or "?"
    except OSError:
        return "?"


def stage(d):
    for _, dst in FILES:
        os.makedirs(os.path.dirname(os.path.join(d, dst)) or d, exist_ok=True)
    for src, dst in FILES:
        s, t = os.path.join(ROOT, src), os.path.join(d, dst)
        if os.path.exists(t) and _sha(t) != _sha(s):
            raise SystemExit("stage %s: %s differs from the repo; delete the stage folder and stage again"
                             % (d, dst))
        shutil.copyfile(s, t)
    pyc = os.path.join(d, "src", "__pycache__", "pathfinder.%s.pyc" % _tag())
    py_compile.compile(os.path.join(d, "src", "pathfinder.py"), cfile=pyc, doraise=True,
                       invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH)
    print("staged %s, bytecode %s" % (d, os.path.relpath(pyc, d)))


def evaluate(d, imu, runs):
    import benchmark
    import measure_floor
    from vortex import check_output
    out = os.path.join(d, "estimated_trajectory.txt")
    stale = [p for p in NOT_SHIPPED if os.path.exists(os.path.join(d, p))]
    if stale:
        raise SystemExit("stage %s still holds %s (C core, not shipped); delete the stage and stage again"
                         % (d, ", ".join(stale)))
    main_py = os.path.join(d, "src", "main.py")
    cmd = [sys.executable, "-S", main_py, imu, out]
    entry = "python -S src/main.py"
    s = measure_floor.summarise(measure_floor.repeat(cmd, runs))
    heap, code = benchmark.heap_peak_process(main_py, imu, out)
    if code != 0:
        raise SystemExit("main.py exited %d under the heap probe" % code)
    chk = check_output.check(imu, out)
    if not chk["ok"]:
        raise SystemExit("output fails the checker: %s" % "; ".join(chk["errors"][:3]))
    with open(out, "rb") as f:
        rows = sum(1 for _ in f)
    imu_s, imu_src = benchmark.imu_seconds(imu)
    meta = {"input": os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(imu)))))
            or os.path.basename(imu),
            "input_sha256": _sha(imu), "rows": rows, "imu_seconds": imu_s, "imu_seconds_source": imu_src,
            "entry_point": entry,
            "runs": runs, "wall_s_median": s["wall_ms_median"] / 1e3,
            "ms_compute_per_imu_second": s["wall_ms_median"] / imu_s, "cpu_s_median": s["cpu_ms_median"] / 1e3,
            "heap_peak_bytes": heap,
            "heap_measured_with": "tracemalloc peak over the whole `python -S src/main.py` run, started "
                                  "before main.py runs (algorithm / heap level, as in the organisers' FAQ)",
            "peak_rss_mib_median": s["peak_rss_mb_median"], "peak_rss_mib_max": s["peak_rss_mb_max"],
            "rss_measured_with": ("Windows GetProcessMemoryInfo PeakWorkingSetSize" if os.name == "nt"
                                  else "GNU time %M (peak resident set size)")
            + "; whole process including the CPython interpreter; for the record only",
            "single_thread": True, "network": False,
            "os": "%s %s" % (platform.system(), platform.release()), "cpu": measure_floor._cpu_name(),
            "python": platform.python_version(), "source_commit": _commit(),
            "date": datetime.date.today().isoformat()}
    with open(os.path.join(d, "metadata.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=1)
        f.write("\n")
    print("wrote %s and metadata.json: %d rows, %.2f ms per IMU-second, heap peak %.0f KB (peak RSS %.2f MiB)"
          % (out, rows, meta["ms_compute_per_imu_second"], heap / 1024.0, meta["peak_rss_mib_median"]))


def make_zip(d, name, out):
    stale = [p for p in NOT_SHIPPED if os.path.exists(os.path.join(d, p))]
    if stale:
        raise SystemExit("stage %s still holds %s (C core, not shipped); delete the stage and stage again"
                         % (d, ", ".join(stale)))
    for src, dst in FILES:
        if _sha(os.path.join(d, dst)) != _sha(os.path.join(ROOT, src)):
            raise SystemExit("%s differs from the repo's %s; stage again" % (dst, src))
    cache = os.path.join(d, "src", "__pycache__")
    pycs = sorted(os.listdir(cache)) if os.path.isdir(cache) else []
    rel = [dst for _, dst in FILES] + ["src/__pycache__/" + p for p in pycs]
    rel += [e for e in EVAL_FILES if os.path.exists(os.path.join(d, e))]
    man = ["Vortex Track 3 submission, built from commit %s by tools/make_bundle.py." % _commit(),
           "Bytecode for: %s" % (", ".join(p.split(".")[1] for p in pycs) or "none"),
           "Evaluation output: %s" % ("included" if "metadata.json" in rel else "NOT included (run `eval`)"),
           "", "sha256:"]
    man += ["%s  %s" % (_sha(os.path.join(d, r)), r) for r in rel]
    with open(os.path.join(d, "MANIFEST.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(man) + "\n")
    rel.append("MANIFEST.txt")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, name + ".zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for r in sorted(rel):
            info = zipfile.ZipInfo(r, ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(os.path.join(d, r), "rb") as f:
                z.writestr(info, f.read())
    print("wrote %s (%d files, bytecode for %s; %s)" % (path, len(rel), ", ".join(pycs) or "none", man[2]))


def verify(zpath):
    import synth_euroc
    from vortex import check_output
    tmp = tempfile.mkdtemp(prefix="vortex_bundle_")
    app = os.path.join(tmp, "app")
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        z.extractall(app)
    ok = True
    for p in NOT_SHIPPED:
        if p in names:
            print("%s is in the zip: the C core is not accepted (FAQ); stage again" % p)
            ok = False
    imu = os.path.join(tmp, "imu.csv")
    synth_euroc.write(imu, rows=6000, seed=0)
    ref = os.path.join(tmp, "ref.txt")
    subprocess.run([sys.executable, "-S", os.path.join(ROOT, "pathfinder.py"), imu, ref], check=True)
    shipped = os.path.exists(os.path.join(app, "src", "__pycache__", "pathfinder.%s.pyc" % _tag()))
    for i in (1, 2):
        est = os.path.join(tmp, "est%d.txt" % i)
        p = subprocess.run([sys.executable, "-I", "-S", "-v", os.path.join(app, "src", "main.py"), imu, est],
                           cwd=tmp, capture_output=True, text=True)
        src = [l for l in p.stderr.splitlines() if "code object from" in l and "pathfinder" in l]
        from_pyc = bool(src) and src[0].rstrip("'").endswith(".pyc")
        same = p.returncode == 0 and _sha(est) == _sha(ref)
        chk = check_output.check(imu, est)["ok"] if p.returncode == 0 else False
        print("python run %d: exit %d, output %s, checker %s, pathfinder from %s" % (
            i, p.returncode, "identical" if same else "DIFFERS", "PASS" if chk else "FAIL",
            "bytecode" if from_pyc else "source"))
        ok &= same and chk and (from_pyc or not shipped)
    print("bytecode for %s %s in the zip" % (_tag(), "is" if shipped else "is NOT"))
    for e in EVAL_FILES:
        print("%s %s" % (e, "included" if os.path.exists(os.path.join(app, e)) else "NOT included"))
    print("VERIFY:", "PASS" if ok else "FAIL")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["stage", "eval", "zip", "verify"])
    ap.add_argument("path", nargs="?", help="eval: the evaluation IMU csv; verify: the zip")
    ap.add_argument("--dir", default=os.path.join(ROOT, "dist", "stage"))
    ap.add_argument("--name")
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--runs", type=int, default=5)
    a = ap.parse_args(argv)
    if a.cmd == "stage":
        stage(a.dir)
    elif a.cmd == "eval":
        if not a.path:
            ap.error("eval needs the IMU csv")
        evaluate(a.dir, a.path, a.runs)
    elif a.cmd == "zip":
        if not a.name:
            ap.error("zip needs --name")
        make_zip(a.dir, a.name, a.out)
    else:
        if not a.path:
            ap.error("verify needs the zip path")
        return verify(a.path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

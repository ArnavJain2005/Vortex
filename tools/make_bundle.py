"""Build the submission zip (step 9). Stdlib only.

    python tools/make_bundle.py stage [--dir dist/stage]
        Copies main.py, pathfinder.py, bundle/README.md, bundle/Dockerfile and LICENSE into the stage
        folder, then compiles pathfinder.py to a hash-checked .pyc for THIS Python (valid whatever the
        file times are after unzipping). Run it once with each Python the bundle should carry
        bytecode for, e.g. py -3.13, py -3.14, and python3 in WSL.
    python tools/make_bundle.py zip --name NAME [--dir dist/stage] [--out dist]
        Writes dist/NAME.zip (files under NAME/, fixed entry times, sorted) and MANIFEST.txt.
    python tools/make_bundle.py verify dist/NAME.zip
        Extracts to a temporary folder and, with THIS Python, runs `python -I -S main.py` twice on a
        SYNTHETIC file: the output must equal `python -S pathfinder.py` from the repo, pass the output
        checker, and, if the zip carries bytecode for this Python, the runs must load it.

A stage folder whose sources differ from the repo's is refused (delete it and stage again).
"""
import argparse
import hashlib
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

FILES = [("main.py", "main.py"), ("pathfinder.py", "pathfinder.py"), ("bundle/README.md", "README.md"),
         ("bundle/Dockerfile", "Dockerfile"), ("LICENSE", "LICENSE")]
ZIP_TIME = (2026, 11, 20, 0, 0, 0)


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _tag():
    return sys.implementation.cache_tag      # e.g. cpython-314


def stage(d):
    os.makedirs(d, exist_ok=True)
    for src, dst in FILES:
        s, t = os.path.join(ROOT, src), os.path.join(d, dst)
        if os.path.exists(t) and _sha(t) != _sha(s):
            raise SystemExit("stage %s: %s differs from the repo; delete the stage folder and stage again"
                             % (d, dst))
        shutil.copyfile(s, t)
    pyc = os.path.join(d, "__pycache__", "pathfinder.%s.pyc" % _tag())
    py_compile.compile(os.path.join(d, "pathfinder.py"), cfile=pyc, doraise=True,
                       invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH)
    print("staged %s, bytecode %s" % (d, os.path.relpath(pyc, d)))


def make_zip(d, name, out):
    for src, dst in FILES:
        if _sha(os.path.join(d, dst)) != _sha(os.path.join(ROOT, src)):
            raise SystemExit("%s differs from the repo's %s; stage again" % (dst, src))
    pycs = sorted(os.listdir(os.path.join(d, "__pycache__"))) if os.path.isdir(os.path.join(d, "__pycache__")) else []
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                                text=True).stdout.strip()
    except OSError:
        commit = "?"
    rel = [dst for _, dst in FILES] + ["__pycache__/" + p for p in pycs]
    man = ["Vortex Track 3 submission, built from commit %s by tools/make_bundle.py." % commit,
           "Bytecode for: %s" % (", ".join(p.split(".")[1] for p in pycs) or "none"), "", "sha256:"]
    man += ["%s  %s" % (_sha(os.path.join(d, r)), r) for r in rel]
    with open(os.path.join(d, "MANIFEST.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(man) + "\n")
    rel.append("MANIFEST.txt")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, name + ".zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for r in sorted(rel):
            info = zipfile.ZipInfo(name + "/" + r, ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(os.path.join(d, r), "rb") as f:
                z.writestr(info, f.read())
    print("wrote %s (%d files, bytecode for %s)" % (path, len(rel), ", ".join(pycs) or "none"))


def verify(zpath):
    import synth_euroc
    from vortex import check_output
    tmp = tempfile.mkdtemp(prefix="vortex_bundle_")
    with zipfile.ZipFile(zpath) as z:
        z.extractall(tmp)
        top = z.namelist()[0].split("/")[0]
    app = os.path.join(tmp, top)
    imu = os.path.join(tmp, "imu.csv")
    synth_euroc.write(imu, rows=6000, seed=0)
    ref = os.path.join(tmp, "ref.txt")
    subprocess.run([sys.executable, "-S", os.path.join(ROOT, "pathfinder.py"), imu, ref], check=True)
    shipped = os.path.exists(os.path.join(app, "__pycache__", "pathfinder.%s.pyc" % _tag()))
    ok = True
    for i in (1, 2):
        est = os.path.join(tmp, "est%d.txt" % i)
        p = subprocess.run([sys.executable, "-I", "-S", "-v", os.path.join(app, "main.py"), imu, est],
                           cwd=tmp, capture_output=True, text=True)
        src = [l for l in p.stderr.splitlines() if "code object from" in l and "pathfinder" in l]
        from_pyc = bool(src) and src[0].rstrip("'").endswith(".pyc")
        same = p.returncode == 0 and _sha(est) == _sha(ref)
        chk = check_output.check(imu, est)["ok"] if p.returncode == 0 else False
        print("run %d: exit %d, output %s, checker %s, pathfinder from %s" % (
            i, p.returncode, "identical" if same else "DIFFERS", "PASS" if chk else "FAIL",
            "bytecode" if from_pyc else "source"))
        ok &= same and chk and (from_pyc or not shipped)
    print("bytecode for %s %s in the zip" % (_tag(), "is" if shipped else "is NOT"))
    print("VERIFY:", "PASS" if ok else "FAIL")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["stage", "zip", "verify"])
    ap.add_argument("zipfile", nargs="?")
    ap.add_argument("--dir", default=os.path.join(ROOT, "dist", "stage"))
    ap.add_argument("--name")
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    a = ap.parse_args(argv)
    if a.cmd == "stage":
        stage(a.dir)
    elif a.cmd == "zip":
        if not a.name:
            ap.error("zip needs --name")
        make_zip(a.dir, a.name, a.out)
    else:
        if not a.zipfile:
            ap.error("verify needs the zip path")
        return verify(a.zipfile)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Build the submission zip (step 9; frozen build rules of 19 Nov 2026). Stdlib only. Layout (PRD,
"Deliverables"; Python only per the organisers' FAQ of 17 Nov 2026):

    estimated_trajectory.txt   our output for the organisers' evaluation input (from `eval`)
    metadata.json              commit, build flags, input, rows, cal_source, heap peak, time (from `eval`)
    src/main.py                ONE self-contained file, standard library only, GENERATED from pathfinder.py
    README.md, Dockerfile, LICENSE, MANIFEST.txt

src/main.py is pathfinder.py (the estimator; standalone, a bit-identical copy of the vortex/core rules
that never imports the `vortex` package) with a generated header. No bytecode, no C, no ctypes ships: the
build fails if the generated file imports anything outside the standard modules it needs, names ctypes,
importlib, marshal or subprocess, calls exec/eval/compile/__import__, or mentions a .pyc, __pycache__ or
compiled-library path, and the zip is refused if it holds any compiled file.

    python tools/make_bundle.py single [--out dist/stage/src/main.py]
        Writes the single file and runs the reachability check on it.
    python tools/make_bundle.py stage [--dir dist/stage]
        The single file plus README, Dockerfile, LICENSE into the stage folder.
    python tools/make_bundle.py same [--dir dist/stage] [--data data] [--seqs a,b] [--seeds 1,2,3]
        Byte-identity of the single file against the repo build (`python -S main.py`, which imports
        pathfinder.py) on official copies, by default MH_03_medium and dataset-room3_512_16, readings a and
        b, seeds 1, 2, 3. Exit 1 on any difference.
    python tools/make_bundle.py eval IMU.csv [--dir dist/stage] [--runs 5]
        Runs `python -S src/main.py` on the evaluation input: writes estimated_trajectory.txt and
        metadata.json into the stage (time and peak RSS measured as benchmark.py does, the heap peak with
        tracemalloc over the whole run, the level the organisers measure).
    python tools/make_bundle.py zip --name NAME [--dir dist/stage] [--out dist]
        Writes dist/NAME.zip (sorted, fixed entry times) and MANIFEST.txt.
    python tools/make_bundle.py verify dist/NAME.zip
        Extracts it and, on a SYNTHETIC file, runs src/main.py with and without -S, under -I, from another
        working directory and with every argument form: output equal to the repo's pathfinder.py, checker
        PASS. A zip with any compiled file (.pyc, .pyd, .so, .dll, .exe) or C source is refused.

A stage folder whose files differ from a fresh build is refused (delete it and stage again).
"""
import argparse
import ast
import datetime
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

SOURCE = "pathfinder.py"
SINGLE = "src/main.py"
COPIED = [("bundle/README.md", "README.md"), ("bundle/Dockerfile", "Dockerfile"), ("LICENSE", "LICENSE")]
EVAL_FILES = ["estimated_trajectory.txt", "metadata.json"]
COMPILED = (".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe", ".o", ".a", ".lib", ".cpp", ".c", ".h")
ALLOWED_IMPORTS = {"math", "os", "sys", "array"}
FORBIDDEN_NAMES = {"ctypes", "cffi", "importlib", "marshal", "subprocess", "imp", "zipimport", "runpy",
                   "exec", "eval", "compile", "__import__", "__loader__", "load_dynamic", "CDLL", "dlopen"}
FORBIDDEN_TEXT = ("__pycache__", ".pyc", ".pyd", ".so", ".dll", ".dylib", "main.cpp", "cbin", "ctypes")
ZIP_TIME = (2026, 11, 20, 0, 0, 0)
DEFAULT_SEQS = ("MH_03_medium", "dataset-room3_512_16")


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _commit():
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                             text=True).stdout.strip() or "?"
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                               capture_output=True, text=True).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except OSError:
        return "?"


# ---------------------------------------------------------------- the single file
def _switches(tree):
    """Module-level `NAME = True/False` assigned once: the shipped on/off switches."""
    seen, out = {}, {}
    for n in ast.walk(tree):
        for t in (n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(n, (ast.AugAssign, ast.AnnAssign)) else []):
            for x in ast.walk(t):
                if isinstance(x, ast.Name):
                    seen[x.id] = seen.get(x.id, 0) + 1
    for n in tree.body:
        if (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                and isinstance(n.value, ast.Constant) and isinstance(n.value.value, bool)):
            out[n.targets[0].id] = n.value.value
    return {k: v for k, v in out.items() if seen.get(k) == 1}


class _Fold(ast.NodeTransformer):
    """Removes docstrings and folds `if`s whose test is decided by a shipped switch (also through a local
    alias `x = SWITCH` / `a, b = S1, S2` that the function never reassigns)."""

    def __init__(self, consts):
        self.consts = [dict(consts)]

    def _value(self, e):
        """True / False if decided by the switches, else None."""
        if isinstance(e, ast.Constant) and isinstance(e.value, bool):
            return e.value
        if isinstance(e, ast.Name):
            for scope in reversed(self.consts):
                if e.id in scope:
                    return scope[e.id]
            return None
        if isinstance(e, ast.UnaryOp) and isinstance(e.op, ast.Not):
            v = self._value(e.operand)
            return None if v is None else not v
        if isinstance(e, ast.BoolOp):
            vals = [self._value(x) for x in e.values]
            if isinstance(e.op, ast.And):
                if False in vals:
                    return False
                return True if all(v is True for v in vals) else None
            if True in vals:
                return True
            return False if all(v is False for v in vals) else None
        return None

    def _simplify(self, e):
        """`a and SWITCH_ON` -> `a` (a bool test only: used where the value is read as a condition)."""
        if isinstance(e, ast.BoolOp):
            keep = [x for x in e.values if self._value(x) is None]
            if len(keep) == 1:
                return keep[0]
            if keep and len(keep) < len(e.values):
                return ast.BoolOp(op=e.op, values=keep)
        return e

    def _aliases(self, fn):
        names, count = {}, {}
        for n in ast.walk(fn):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(
                n, (ast.AugAssign, ast.AnnAssign, ast.For)) else []
            for t in targets:
                for x in ast.walk(t):
                    if isinstance(x, ast.Name):
                        count[x.id] = count.get(x.id, 0) + 1
            if isinstance(n, ast.Assign) and len(n.targets) == 1:
                t, v = n.targets[0], n.value
                pairs = [(t, v)] if isinstance(t, ast.Name) else list(zip(t.elts, v.elts)) if (
                    isinstance(t, ast.Tuple) and isinstance(v, ast.Tuple) and len(t.elts) == len(v.elts)) else []
                for a, b in pairs:
                    if isinstance(a, ast.Name):
                        r = self._value(b)
                        if r is not None:
                            names[a.id] = r
        args = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
        return {k: v for k, v in names.items() if count.get(k) == 1 and k not in args}

    def _strip_doc(self, node):
        b = node.body
        if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) and isinstance(b[0].value.value, str):
            node.body = b[1:] or [ast.Pass()]

    def visit_Module(self, node):
        self._strip_doc(node)
        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node):
        self._strip_doc(node)
        self.consts.append(self._aliases(node))
        self.generic_visit(node)
        self.consts.pop()
        if not node.body:
            node.body = [ast.Pass()]
        return node

    visit_ClassDef = visit_Module

    def visit_If(self, node):
        v = self._value(node.test)
        if v is not None:
            out = []
            for s in (node.body if v else node.orelse):
                r = self.visit(s)
                out.extend(r if isinstance(r, list) else [r] if r is not None else [])
            return out or None
        node.test = self._simplify(node.test)
        self.generic_visit(node)
        if not node.body:
            node.body = [ast.Pass()]
        return node

    def visit_IfExp(self, node):
        v = self._value(node.test)
        if v is not None:
            return self.visit(node.body if v else node.orelse)
        self.generic_visit(node)
        return node


def _drop_dead_assignments(tree):
    """After folding: `x = NAME_OR_CONSTANT` (also tuple form) whose targets are never read anywhere are
    removed, in functions and at module level (switch constants nothing reads any more). No side effects:
    only names and constants on the right-hand side."""
    loads = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    loads |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for n in ast.walk(tree):                      # names read through globals()/getattr strings stay
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            loads.add(n.value)

    def pure(v):
        return isinstance(v, (ast.Name, ast.Constant)) or (
            isinstance(v, ast.Tuple) and all(isinstance(e, (ast.Name, ast.Constant)) for e in v.elts))

    def dead(s):
        if not (isinstance(s, ast.Assign) and len(s.targets) == 1 and pure(s.value)):
            return False
        t = s.targets[0]
        names = [t] if isinstance(t, ast.Name) else t.elts if isinstance(t, ast.Tuple) else None
        return bool(names) and all(isinstance(x, ast.Name) and x.id not in loads for x in names)

    for n in ast.walk(tree):
        for f in ("body", "orelse", "finalbody"):
            b = getattr(n, f, None)
            if isinstance(b, list) and b and isinstance(b[0], ast.stmt):
                keep = [s for s in b if not dead(s)]
                if len(keep) != len(b):
                    setattr(n, f, keep or [ast.Pass()])
    return tree


def single_text(source=None):
    """src/main.py: pathfinder.py without docstrings, comments and the code of the shipped switches' OFF
    side, under a generated header. LF line ends. Same behaviour by construction (`same` checks the bytes).
    source: another estimator text (tests only)."""
    if source is None:
        with open(os.path.join(ROOT, SOURCE), "rb") as f:
            raw = f.read()
    else:
        raw = source.encode("utf-8")
    tree = ast.parse(raw.decode("utf-8"))
    tree = _Fold(_switches(tree)).visit(tree)
    for n in ast.walk(tree):                      # a block emptied by the folding still needs a statement
        b = getattr(n, "body", None)
        if isinstance(b, list) and not b:
            n.body = [ast.Pass()]
    tree = _drop_dead_assignments(tree)
    body = ast.unparse(ast.fix_missing_locations(tree)) + "\n"
    head = ('"""Vortex, Samsung PRISM XR Hackathon 2026, Track 3: 6-DoF trajectory from a degraded IMU.\n\n'
            "    python main.py [IN [OUT]]            (also: --input IN --output OUT, -i IN -o OUT)\n\n"
            "IN: the IMU csv or a sequence folder (searched for imu0/data.csv, mav0/imu0/data.csv, data.csv,\n"
            "a single *.csv); no IN: the current folder. OUT: the trajectory file or a folder; no OUT:\n"
            "estimated_trajectory.txt in the current folder. One line `timestamp tx ty tz qx qy qz qw` per\n"
            "input data row. If the estimator fails, every row gets a constant pose and the exit code is 0.\n\n"
            "ONE self-contained file: standard library only (math, os, sys, array), single thread, offline,\n"
            "deterministic; no bytecode, no compiled code. GENERATED by tools/make_bundle.py from the\n"
            "repository's pathfinder.py (sha256 %s); do not edit.\n"
            '"""\n' % hashlib.sha256(raw).hexdigest()[:16])
    return head + body


def check_single(text):
    """Problems that make a single file unacceptable (empty list: fine)."""
    bad = []
    try:
        tree = ast.parse(text, feature_version=(3, 10))
    except SyntaxError as e:
        return ["not valid Python 3.10 syntax: %s" % e]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [node.module or ""]
            if node.level:
                bad.append("relative import at line %d" % node.lineno)
        else:
            mods = []
        for m in mods:
            if m.split(".")[0] not in ALLOWED_IMPORTS:
                bad.append("import %s at line %d (allowed: %s)" % (m, node.lineno, ", ".join(sorted(ALLOWED_IMPORTS))))
        name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None
        if name in FORBIDDEN_NAMES:
            bad.append("name %s at line %d" % (name, node.lineno))
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
            v = node.value if isinstance(node.value, str) else node.value.decode("latin-1")
            for t in FORBIDDEN_TEXT:
                if t in v:
                    bad.append("text %r at line %d" % (t, node.lineno))
    return bad


# ---------------------------------------------------------------- CHUNKED layout (rule K, Docs/TRACK3_PLAN.md)
def _entry_free_source(source=None):
    """pathfinder.py (LF) without its trailing `if __name__ == "__main__":` block: the text CHUNKED embeds."""
    if source is None:
        with open(os.path.join(ROOT, SOURCE), "rb") as f:
            source = f.read().decode("utf-8")
    src = source.replace("\r\n", "\n")
    if "'''" in src or "\r" in src or src.rstrip("\n").endswith("\\"):
        raise SystemExit("CHUNKED refused: the source holds ''' , a CR or ends in a backslash (cannot be a raw string)")
    tree = ast.parse(src)
    last = tree.body[-1]
    if (isinstance(last, ast.If) and isinstance(last.test, ast.Compare) and isinstance(last.test.left, ast.Name)
            and last.test.left.id == "__name__"):
        src = "".join(src.splitlines(keepends=True)[:last.lineno - 1])
        tree = ast.parse(src)
    return src, tree


def _chunks(src, tree, n):
    """(char start, char end, first line) per chunk: neighbouring top-level statements merged while a chunk
    stays within n lines (a longer statement is a chunk of its own). The chunks tile src exactly."""
    lines = src.splitlines(keepends=True)
    off = [0]
    for l in lines:
        off.append(off[-1] + len(l))
    starts = [1] + [(s.decorator_list[0].lineno if getattr(s, "decorator_list", None) else s.lineno)
                    for s in tree.body[1:]]
    bounds = starts + [len(lines) + 1]
    spans = [(bounds[i], bounds[i + 1]) for i in range(len(starts))]   # [first line, next first line)
    out = []
    a, b = spans[0]
    for s, e in spans[1:]:
        if e - a <= n:
            b = e
        else:
            out.append((a, b))
            a, b = s, e
    out.append((a, b))
    return tuple((off[x - 1], off[y - 1], x) for x, y in out)


LOADER = '''# HOW THIS FILE RUNS: the estimator below (SRC) is our pathfinder.py VERBATIM, kept as plain source text.
# Compiling a 1,700-line file in one go costs the Python parser about 7 MB of memory, so this short loader
# compiles it one function (a few neighbouring statements) at a time instead, keeping parser memory low.
# Line numbers in error messages are those of pathfinder.py. Standard library only; no bytecode ships.
import sys

CHUNKS = %s


def _paths(argv):
    """Minimal IN / OUT for the loader's own fallback (only if the estimator itself cannot be loaded)."""
    a, src, dst, pos = list(argv[1:]), None, None, []
    while a:
        x = a.pop(0)
        if x in ("-i", "--input") and a:
            src = a.pop(0)
        elif x in ("-o", "--output") and a:
            dst = a.pop(0)
        elif x.startswith("--input="):
            src = x[8:]
        elif x.startswith("--output="):
            dst = x[9:]
        else:
            pos.append(x)
    src = src or (pos[0] if pos else "data.csv")
    dst = dst or (pos[1] if len(pos) > 1 else "estimated_trajectory.txt")
    return src, dst


def _constant_pose(argv, err):
    tb = err.__traceback__
    while tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    where = " (%%s line %%d)" %% (tb.tb_frame.f_code.co_filename, tb.tb_lineno) if tb is not None else ""
    sys.stderr.write("main.py: the estimator could not be loaded: %%s: %%s%%s; writing a constant pose for "
                     "every row\\n" %% (type(err).__name__, err, where))
    src, dst = _paths(argv)
    n, first, sec = 0, True, "0.000000000"
    with open(src, "rb") as f, open(dst, "w", newline="\\n") as g:
        for line in f:
            s = line.strip().lstrip(b"\\xef\\xbb\\xbf").strip()
            if not s or s[:1] == b"#":
                continue
            if first:
                first = False
                if s.upper() != s.lower() and all(not x.strip().replace(b".", b"").replace(b"-", b"").isdigit()
                                                  for x in s.split(b",")):
                    continue
            t = s.split(b",", 1)[0].strip()
            if t.isdigit():
                t = int(t)
                sec = "%%d.%%09d" %% (t // 1000000000, t %% 1000000000)
            g.write(sec + " 0.000000 0.000000 0.000000 0.0000000 0.0000000 0.0000000 1.0000000\\n")
            n += 1
    return 0


_G = None


def main(argv):
    global _G
    try:
        g = {"__name__": "pathfinder", "__builtins__": __builtins__}
        for a, b, line in CHUNKS:
            exec(compile("\\n" * (line - 1) + SRC[a:b], "main.py", "exec"), g)
        _G = g
    except KeyboardInterrupt:
        raise
    except BaseException as e:      # noqa: BLE001 (never fail: the estimator could not be loaded)
        try:
            return _constant_pose(argv, e)
        except Exception as e2:     # noqa: BLE001
            sys.stderr.write("main.py: %%s\\n" %% e2)
            return 1
    return g["main"](argv)


SRC = r\'\'\'%s\'\'\'

if __name__ == "__main__":
    sys.exit(main(sys.argv))
'''


def chunked_text(n, source=None):
    src, tree = _entry_free_source(source)
    ch = _chunks(src, tree, n)
    head = ('"""Vortex, Samsung PRISM XR Hackathon 2026, Track 3: 6-DoF trajectory from a degraded IMU.\n\n'
            "    python main.py [IN [OUT]]            (also: --input IN --output OUT, -i IN -o OUT)\n\n"
            "ONE self-contained file, standard library only, single thread, offline, deterministic; no bytecode.\n"
            "GENERATED by tools/make_bundle.py (layout CHUNKED, %d chunks of at most %d lines) from the\n"
            "repository's pathfinder.py (sha256 %s); do not edit.\n"
            '"""\n' % (len(ch), n, hashlib.sha256(src.encode("utf-8")).hexdigest()[:16]))
    return head + LOADER % (repr(ch), src)


def check_chunked(text):
    """CHUNKED: the loader may import only sys and is the only place exec/compile appear; the embedded
    source must pass check_single (no exec, no C, no bytecode, stdlib only)."""
    try:
        tree = ast.parse(text, feature_version=(3, 10))
    except SyntaxError as e:
        return ["not valid Python 3.10 syntax: %s" % e]
    src = [n.value.value for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "SRC"]
    if len(src) != 1:
        return ["no SRC string"]
    bad = ["embedded source: " + p for p in check_single(src[0])]
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "SRC":
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or "."]
            if mods != ["sys"]:
                bad.append("loader import %s" % mods)
        name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None
        if name in FORBIDDEN_NAMES - {"exec", "compile"}:
            bad.append("loader name %s" % name)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value is not src[0]:
            for t in FORBIDDEN_TEXT:
                if t in node.value:
                    bad.append("loader text %r" % t)
    return bad


LAYOUTS = ("plain", "chunked")
DEFAULT_LAYOUT = "plain"       # set by rule K (Docs/TRACK3_PLAN.md, "Freeze build")
CHUNK_LINES = 120


def bundle_text(layout=None, n=None):
    layout = layout or DEFAULT_LAYOUT
    return single_text() if layout == "plain" else chunked_text(n or CHUNK_LINES)


def check_bundle(text):
    return check_chunked(text) if "\nSRC = r'''" in text else check_single(text)


def write_single(path, layout=None, n=None):
    text = bundle_text(layout, n)
    bad = check_bundle(text)
    if bad:
        raise SystemExit("single file REFUSED (%d problems): %s" % (len(bad), "; ".join(bad[:5])))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return text


def _compiled_files(d):
    out = []
    for base, dirs, files in os.walk(d):
        for n in dirs:
            if n == "__pycache__":
                out.append(os.path.relpath(os.path.join(base, n), d))
        for n in files:
            if n.lower().endswith(COMPILED):
                out.append(os.path.relpath(os.path.join(base, n), d))
    return sorted(out)


def stage(d, layout=None, n=None):
    os.makedirs(os.path.join(d, "src"), exist_ok=True)
    for src, dst in COPIED:
        s, t = os.path.join(ROOT, src), os.path.join(d, dst)
        if os.path.exists(t) and _sha(t) != _sha(s):
            raise SystemExit("stage %s: %s differs from the repo; delete the stage folder and stage again" % (d, dst))
        shutil.copyfile(s, t)
    t = os.path.join(d, SINGLE)
    text = bundle_text(layout, n)
    if os.path.exists(t):
        with open(t, "rb") as f:
            if f.read() != text.encode("utf-8"):
                raise SystemExit("stage %s: %s differs from a fresh build; delete the stage and stage again" % (d, SINGLE))
    write_single(t, layout, n)
    stale = _compiled_files(d)
    if stale:
        raise SystemExit("stage %s holds compiled or C files (%s); delete the stage folder and stage again"
                         % (d, ", ".join(stale)))
    print("staged %s: %s (layout %s, %d lines, standard library only, reachability check passed)"
          % (d, SINGLE, layout or DEFAULT_LAYOUT, text.count("\n")))


def _check_stage(d):
    stale = _compiled_files(d)
    if stale:
        raise SystemExit("stage %s holds compiled or C files (%s); delete the stage and stage again"
                         % (d, ", ".join(stale)))
    t = os.path.join(d, SINGLE)
    if not os.path.exists(t):
        raise SystemExit("no %s in %s: run `stage` first" % (SINGLE, d))
    with open(t, "rb") as f:
        have = f.read()
    if have not in (bundle_text("plain").encode("utf-8"), bundle_text("chunked").encode("utf-8")):
        raise SystemExit("%s differs from a fresh build of pathfinder.py (plain, or chunked with %d lines); stage again"
                         % (SINGLE, CHUNK_LINES))
    for src, dst in COPIED:
        if _sha(os.path.join(d, dst)) != _sha(os.path.join(ROOT, src)):
            raise SystemExit("%s differs from the repo's %s; stage again" % (dst, src))


# ---------------------------------------------------------------- byte-identity on official copies
def same(d, data, seqs, readings, seeds):
    single = os.path.join(d, SINGLE)
    if not os.path.exists(single):
        raise SystemExit("no %s in %s: run `stage` first" % (SINGLE, d))
    copies = []
    for seq in seqs:
        sub = "official_tumvi" if seq.startswith("dataset-") else "official"
        for r in readings:
            for s in seeds:
                p = os.path.join(data, sub, "%s_%s_s%s" % (seq, r, s))
                imu = os.path.join(p, "mav0", "imu0", "data.csv")
                if os.path.exists(imu):
                    copies.append((os.path.basename(p), imu))
                else:
                    print("missing: %s" % imu)
    if not copies:
        raise SystemExit("no official copies found under %s" % data)
    tmp = tempfile.mkdtemp(prefix="vortex_same_")
    ok = True
    for name, imu in copies:
        a, b = os.path.join(tmp, name + "_repo.txt"), os.path.join(tmp, name + "_single.txt")
        pa = subprocess.run([sys.executable, "-S", os.path.join(ROOT, "main.py"), imu, a], capture_output=True, text=True)
        pb = subprocess.run([sys.executable, "-S", single, imu, b], capture_output=True, text=True, cwd=tmp)
        eq = pa.returncode == 0 and pb.returncode == 0 and _sha(a) == _sha(b)
        with open(b, "rb") as f:
            rows = sum(1 for _ in f)
        print("%-34s %s  rows %d  exit %d/%d%s" % (name, "IDENTICAL" if eq else "DIFFERS", rows, pa.returncode,
                                                  pb.returncode, "" if not pb.stderr else "  stderr: " + pb.stderr.strip()[:120]))
        ok &= eq and not pb.stderr
    shutil.rmtree(tmp, ignore_errors=True)
    print("SAME: %s (%d copies; Python %s)" % ("PASS" if ok else "FAIL", len(copies), platform.python_version()))
    return 0 if ok else 1


# ---------------------------------------------------------------- eval, zip, verify
def _build_flags(ns):
    """Every shipped on/off switch of the estimator (boolean UPPER_CASE constants)."""
    return {k: v for k, v in sorted(ns.items()) if k.isupper() and isinstance(v, bool)}


def _load_single(path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("vortex_single_main", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def evaluate(d, imu, runs):
    import benchmark
    import measure_floor
    from vortex import check_output
    _check_stage(d)
    out = os.path.join(d, "estimated_trajectory.txt")
    main_py = os.path.join(d, SINGLE)
    cmd = [sys.executable, "-S", main_py, imu, out]
    s = measure_floor.summarise(measure_floor.repeat(cmd, runs))
    heap, code = benchmark.heap_peak_process(main_py, imu, out)
    if code != 0:
        raise SystemExit("main.py exited %d under the heap probe" % code)
    chk = check_output.check(imu, out)
    if not chk["ok"]:
        raise SystemExit("output fails the checker: %s" % "; ".join(chk["errors"][:3]))
    with open(out, "rb") as f:
        rows = sum(1 for _ in f)
    # cal_source and fallback: the same file run once more in-process (the switches it ships with, LAST)
    mod = _load_single(main_py)
    probe = os.path.join(tempfile.mkdtemp(prefix="vortex_eval_"), "est.txt")
    mod.main(["main.py", imu, probe])
    ns = mod._G if getattr(mod, "_G", None) else vars(mod)        # CHUNKED: the estimator's namespace
    if _sha(probe) != _sha(out):
        raise SystemExit("in-process run differs from the command-line run")
    shutil.rmtree(os.path.dirname(probe), ignore_errors=True)
    cal = "still_run" if ns["LAST"].get("calibrated") else "first_second"
    imu_s, imu_src = benchmark.imu_seconds(imu)
    seq = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(imu)))))
    meta = {"source_commit": _commit(), "single_file_sha256": _sha(main_py),
            "layout": "chunked" if getattr(mod, "_G", None) else "plain",
            "build_flags": _build_flags(ns),
            "input": seq or os.path.basename(imu), "input_file": os.path.basename(imu),
            "input_sha256": _sha(imu), "rows": rows,
            "cal_source": cal,
            "cal_source_meaning": "still_run: gyro bias, gravity and tilt from the longest still run in the first "
                                  "60 s; first_second: no still run passed, initialised from the first second",
            "fallback": ns["LAST"].get("fallback"),
            "imu_seconds": imu_s, "imu_seconds_source": imu_src, "entry_point": "python -S src/main.py",
            "runs": runs, "wall_s_median": s["wall_ms_median"] / 1e3,
            "ms_compute_per_imu_second": s["wall_ms_median"] / imu_s, "cpu_s_median": s["cpu_ms_median"] / 1e3,
            "heap_peak_bytes": heap,
            "heap_measured_with": "tracemalloc peak over the whole `python -S src/main.py` run, started before "
                                  "main.py is compiled (algorithm / heap level, as in the organisers' FAQ); "
                                  "includes compiling the single file, since no bytecode ships",
            "peak_rss_mib_median": s["peak_rss_mb_median"], "peak_rss_mib_max": s["peak_rss_mb_max"],
            "rss_measured_with": ("Windows GetProcessMemoryInfo PeakWorkingSetSize" if os.name == "nt"
                                  else "GNU time %M (peak resident set size)")
            + "; whole process including the CPython interpreter; for the record only",
            "single_thread": True, "network": False,
            "os": "%s %s" % (platform.system(), platform.release()), "cpu": measure_floor._cpu_name(),
            "python": platform.python_version(), "date": datetime.date.today().isoformat()}
    with open(os.path.join(d, "metadata.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=1)
        f.write("\n")
    print("wrote %s and metadata.json: %d rows, cal_source %s, %.2f ms per IMU-second, heap peak %.0f KB "
          "(peak RSS %.2f MiB)" % (out, rows, cal, meta["ms_compute_per_imu_second"], heap / 1024.0,
                                   meta["peak_rss_mib_median"]))


def make_zip(d, name, out):
    _check_stage(d)
    rel = [SINGLE] + [dst for _, dst in COPIED]
    rel += [e for e in EVAL_FILES if os.path.exists(os.path.join(d, e))]
    man = ["Vortex Track 3 submission, built from commit %s by tools/make_bundle.py." % _commit(),
           "Entry point: src/main.py (one file, standard library only, no bytecode, no compiled code).",
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
    print("wrote %s (%d files; %s)" % (path, len(rel), man[2]))


def verify(zpath):
    import synth_euroc
    from vortex import check_output
    tmp = tempfile.mkdtemp(prefix="vortex_bundle_")
    app = os.path.join(tmp, "app")
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        z.extractall(app)
    ok = True
    bad = [n for n in names if n.lower().endswith(COMPILED) or "__pycache__" in n]
    if bad:
        print("compiled or C files in the zip: %s" % ", ".join(bad))
        ok = False
    single = os.path.join(app, SINGLE)
    with open(single, encoding="utf-8") as f:
        problems = check_bundle(f.read())
    if problems:
        print("src/main.py fails the reachability check: %s" % "; ".join(problems[:5]))
        ok = False
    seq = os.path.join(tmp, "seq")
    imu = os.path.join(seq, "mav0", "imu0", "data.csv")
    os.makedirs(os.path.dirname(imu))
    synth_euroc.write(imu, rows=6000, seed=0)
    ref = os.path.join(tmp, "ref.txt")
    subprocess.run([sys.executable, "-S", os.path.join(ROOT, "pathfinder.py"), imu, ref], check=True)
    other = os.path.join(tmp, "elsewhere")
    os.makedirs(other)
    est = os.path.join(other, "estimated_trajectory.txt")
    cases = [("-I -S, IN OUT", ["-I", "-S"], [imu, est], other, est),
             ("no -S, IN OUT", [], [imu, est], other, est),
             ("-S, --input/--output", ["-S"], ["--input", imu, "--output", est], other, est),
             ("-S, -i/-o", ["-S"], ["-i", imu, "-o", est], other, est),
             ("-S, sequence folder as IN", ["-S"], [seq], other, est),
             ("-S, no arguments (in imu0)", ["-S"], [], os.path.dirname(imu),
              os.path.join(os.path.dirname(imu), "estimated_trajectory.txt"))]
    for label, flags, args, cwd, out in cases:
        if os.path.exists(out):
            os.remove(out)
        p = subprocess.run([sys.executable] + flags + [single] + args, cwd=cwd, capture_output=True, text=True)
        same_ = p.returncode == 0 and os.path.exists(out) and _sha(out) == _sha(ref)
        chk = check_output.check(imu, out)["ok"] if same_ else False
        print("%-30s exit %d, output %s, checker %s" % (label, p.returncode, "identical" if same_ else "DIFFERS",
                                                        "PASS" if chk else "FAIL"))
        ok &= same_ and chk
    for e in EVAL_FILES:
        print("%s %s" % (e, "included" if os.path.exists(os.path.join(app, e)) else "NOT included"))
    print("VERIFY:", "PASS" if ok else "FAIL")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["single", "stage", "same", "eval", "zip", "verify"])
    ap.add_argument("path", nargs="?", help="eval: the evaluation IMU csv; verify: the zip")
    ap.add_argument("--dir", default=os.path.join(ROOT, "dist", "stage"))
    ap.add_argument("--name")
    ap.add_argument("--out")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--seqs", default=",".join(DEFAULT_SEQS))
    ap.add_argument("--readings", default="a,b")
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--layout", choices=LAYOUTS, help="default: %s (rule K)" % DEFAULT_LAYOUT)
    ap.add_argument("--chunk-lines", type=int, help="CHUNKED: lines per chunk (default %d)" % CHUNK_LINES)
    a = ap.parse_args(argv)
    if a.cmd == "single":
        out = a.out or os.path.join(a.dir, SINGLE)
        text = write_single(out, a.layout, a.chunk_lines)
        print("wrote %s (%d lines); reachability check passed" % (out, text.count("\n")))
    elif a.cmd == "stage":
        stage(a.dir, a.layout, a.chunk_lines)
    elif a.cmd == "same":
        seqs = a.seqs.split(",")
        if any(s.startswith("V2_") for s in seqs):
            ap.error("V2_* is the final test set")
        return same(a.dir, a.data, seqs, a.readings.split(","), a.seeds.split(","))
    elif a.cmd == "eval":
        if not a.path:
            ap.error("eval needs the IMU csv")
        evaluate(a.dir, a.path, a.runs)
    elif a.cmd == "zip":
        if not a.name:
            ap.error("zip needs --name")
        make_zip(a.dir, a.name, a.out or os.path.join(ROOT, "dist"))
    else:
        if not a.path:
            ap.error("verify needs the zip path")
        return verify(a.path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

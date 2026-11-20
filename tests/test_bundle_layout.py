"""Bundle rule K (Docs/TRACK3_PLAN.md, "Freeze build"): the CHUNKED bundle layout. pathfinder.py is embedded verbatim
and compiled one chunk of top-level statements at a time. The B1/B2/B4/B5 tests for both layouts are in
tests/test_freeze.py (its `single` fixture runs every layout)."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import make_bundle  # noqa: E402
import synth_euroc  # noqa: E402

from vortex import check_output  # noqa: E402


def _source():
    return (ROOT / "pathfinder.py").read_bytes().decode("utf-8").replace("\r\n", "\n")


@pytest.mark.parametrize("n", [40, 120, 400])
def test_chunks_join_to_pathfinder_without_its_entry_block(n):
    src = _source()
    entry = src.rindex('\nif __name__ == "__main__":')
    want = src[:entry + 1]
    got, tree = make_bundle._entry_free_source()
    assert got == want
    ch = make_bundle._chunks(got, tree, n)
    assert "".join(got[a:b] for a, b, _ in ch) == want                    # byte for byte
    assert ch[0][0] == 0 and all(ch[i][1] == ch[i + 1][0] for i in range(len(ch) - 1))
    for a, b, line in ch:
        assert got[:a].count("\n") + 1 == line                           # line numbers kept
        ast.parse(got[a:b])                                               # each chunk compiles on its own
        if got[a:b].count("\n") > n:                                      # longer than n: one statement only
            assert len(ast.parse(got[a:b]).body) == 1


def test_embedded_source_is_verbatim_and_loader_only_imports_sys():
    text = make_bundle.bundle_text("chunked")
    tree = ast.parse(text)
    src = [x.value.value for x in tree.body if isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == "SRC"]
    assert src == [make_bundle._entry_free_source()[0]]
    assert make_bundle.check_chunked(text) == []
    assert "compiles it one function" in text                             # the plain-English note


@pytest.mark.parametrize("bad", ["x = '''a'''\n", "x = 1\ry = 2\n", "p = 1  # \\"])
def test_build_refuses_a_source_that_cannot_be_a_raw_string(bad):
    with pytest.raises(SystemExit):
        make_bundle.chunked_text(120, source=_source() + bad)


def test_reachability_check_still_applies_to_the_embedded_source():
    text = make_bundle.chunked_text(120, source=_source().replace("import math\n", "import math\nimport ctypes\n", 1))
    assert any("ctypes" in p for p in make_bundle.check_chunked(text))
    loader_bad = make_bundle.bundle_text("chunked").replace("import sys\n", "import sys\nimport os\n", 1)
    assert any("loader import" in p for p in make_bundle.check_chunked(loader_bad))


@pytest.fixture(scope="module")
def imu(tmp_path_factory):
    p = tmp_path_factory.mktemp("imu") / "imu.csv"
    synth_euroc.write(str(p), rows=2000, seed=4)
    return p


def _write(tmp_path, text):
    p = tmp_path / "main.py"
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


def test_injected_failure_in_the_estimator_names_main_py_and_pathfinders_line(imu, tmp_path):
    """A failure inside an estimator function: pathfinder's own fallback (exit 0, every row)."""
    src = _source()
    i = src.index("def _run_smoothed(")
    body = src.index("\n", src.index('"""', src.index('"""', i) + 3)) + 1      # after the docstring
    src = src[:body] + "    raise ZeroDivisionError('forced at run time')\n" + src[body:]
    line = src[:body].count("\n") + 1
    for layout in ("plain", "chunked"):
        text = make_bundle.chunked_text(120, source=src) if layout == "chunked" else make_bundle.single_text(source=src)
        p = _write(tmp_path, text)
        out = tmp_path / ("o_%s.txt" % layout)
        r = subprocess.run([sys.executable, "-S", str(p), str(imu), str(out)], capture_output=True, text=True)
        assert r.returncode == 0 and "ZeroDivisionError: forced at run time" in r.stderr, (layout, r.stderr)
        assert check_output.check(str(imu), str(out))["ok"]
        if layout == "chunked":                     # stderr names main.py with pathfinder.py's line number
            assert "(main.py line %d)" % line in r.stderr, r.stderr
        else:
            assert "main.py line " in r.stderr, r.stderr
    # the line number a traceback reports for the chunked file is pathfinder's
    text = make_bundle.chunked_text(120, source=src)
    p = _write(tmp_path, text)
    code = ("import sys, runpy, traceback\nsys.argv=['main.py']\nm = runpy.run_path(%r)\n"
            "try:\n    m['_G'] is None\n    g = {'__name__': 'pathfinder', '__builtins__': __builtins__}\n"
            "    for a, b, line in m['CHUNKS']:\n        exec(compile('\\n' * (line - 1) + m['SRC'][a:b], 'main.py', 'exec'), g)\n"
            "    g['_run_smoothed']('x', 'y', True, True)\nexcept ZeroDivisionError as e:\n"
            "    tb = traceback.extract_tb(e.__traceback__)[-1]\n    print(tb.filename, tb.lineno, tb.line)\n" % str(p))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    fname, lineno, rest = r.stdout.split(" ", 2)
    assert fname == "main.py" and int(lineno) == line, r.stdout


def test_injected_failure_while_loading_uses_the_loaders_fallback(imu, tmp_path):
    """A failure in the exec loop itself (module level of a chunk): the loader writes every row, exit 0,
    and names main.py with pathfinder's line number."""
    src = _source()
    i = src.index("\ndef _tilt(")
    src = src[:i + 1] + "1 / 0\n" + src[i + 1:]
    line = src[:i + 1].count("\n") + 1
    p = _write(tmp_path, make_bundle.chunked_text(120, source=src))
    out = tmp_path / "o.txt"
    for args in ([str(imu), str(out)], ["--input", str(imu), "--output", str(out)], ["-i", str(imu), "-o", str(out)]):
        if out.exists():
            out.unlink()
        r = subprocess.run([sys.executable, "-S", str(p)] + args, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert "could not be loaded: ZeroDivisionError" in r.stderr and "(main.py line %d)" % line in r.stderr
        assert check_output.check(str(imu), str(out))["ok"]
        ref = tmp_path / "ref.txt"
        subprocess.run([sys.executable, "-S", str(ROOT / "pathfinder.py"), str(imu), str(ref)], check=True)
        ts = [l.split()[0] for l in out.read_text().splitlines()]
        assert ts == [l.split()[0] for l in ref.read_text().splitlines()]          # exact timestamps


def test_chunked_bundle_output_equals_plain(imu, tmp_path):
    a = _write(tmp_path, make_bundle.bundle_text("plain"))
    b = tmp_path / "chunked.py"
    b.write_text(make_bundle.bundle_text("chunked"), encoding="utf-8", newline="\n")
    oa, ob = tmp_path / "a.txt", tmp_path / "b.txt"
    subprocess.run([sys.executable, "-S", str(a), str(imu), str(oa)], check=True)
    subprocess.run([sys.executable, "-S", str(b), str(imu), str(ob)], check=True)
    assert oa.read_bytes() == ob.read_bytes()

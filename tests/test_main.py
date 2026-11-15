"""main.py (the submission entry point): output contract on messy input, standalone run, memory gate."""

import ast
import importlib.util
import shutil
import subprocess
import sys
import tracemalloc
from pathlib import Path

import pytest

from vortex import check_output, degrade
from vortex.data import euroc
from vortex.rowspec import is_data_line

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
sys.path.insert(0, str(ROOT / "tools"))
import synth_euroc  # noqa: E402

ALLOWED_IMPORTS = {"sys", "math", "array", "json"}


def _load_main():
    spec = importlib.util.spec_from_file_location("vortex_main_under_test", MAIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


main = _load_main()

MESSY = (b"\xef\xbb\xbf#timestamp [ns],w_RS_S_x,w_RS_S_y,w_RS_S_z,a_RS_S_x,a_RS_S_y,a_RS_S_z\r\n"
         b"abc,0.1,0.2,0.3,9.8,0,0\r\n"                     # bad timestamp before any good one
         b"1403636579758555392,0.1,0.2,0.3,9.8,0,0\r\n"
         b"\r\n"
         b"   \n"
         b"# a comment in the middle\n"
         b"1403636579763555584,nan,nan,nan,nan,nan,nan\n"
         b"1403636579768555520,,,,,,\n"                     # pandas-style NaN
         b"1403636579773555456,0.1,0.2\n"                   # short
         b"1403636579778555392,0.1,0.2,0.3,9.8,0,0,extra\n" # extra column
         b"1403636579778555392,0.1,0.2,0.3,9.8,0,0\n"       # duplicate
         b"1403636579771000000,0.1,0.2,0.3,9.8,0,0\n"       # out of order
         b"xyz,0.1,0.2,0.3,9.8,0,0\n"                       # bad timestamp mid-file
         b"  1403636579783555328 ,0.1,0.2,0.3,9.8,0,0\n"    # padded timestamp
         b"5,0.1,0.2,0.3,9.8,0,0\n"                         # short timestamp
         b"1403636579793555200,1e999,-inf,0.3,9.8,0,0")     # inf, no final newline


def _count_rows(path):
    with open(path, "rb") as f:
        return sum(1 for line in f if is_data_line(line))


def test_imports_are_stdlib_allowlist():
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names <= ALLOWED_IMPORTS, names - ALLOWED_IMPORTS


def test_messy_input_meets_contract(tmp_path):
    src, dst = tmp_path / "imu.csv", tmp_path / "est.txt"
    src.write_bytes(MESSY)
    n = main.run(str(src), str(dst))
    assert n == _count_rows(src) == 12
    r = check_output.check(src, dst)
    assert r["ok"], r["errors"]
    lines = dst.read_text().splitlines()
    assert lines[0].split()[0] == "0.000000000"                 # bad first timestamp
    assert lines[1].split()[0] == "1403636579.758555392"
    assert lines[8].split()[0] == lines[7].split()[0] == "1403636579.771000000"  # bad mid ts holds previous
    assert lines[9].split()[0] == "1403636579.783555328"
    assert lines[10].split()[0] == "0.000000005"


def test_parse_only_mode_writes_nothing(tmp_path):
    src, dst = tmp_path / "imu.csv", tmp_path / "est.txt"
    src.write_bytes(MESSY)
    assert main.run(str(src), str(dst), write=False) == 12
    assert dst.read_bytes() == b""


def test_header_only_input_gives_empty_output(tmp_path):
    src, dst = tmp_path / "imu.csv", tmp_path / "est.txt"
    src.write_text(euroc.HEADER + "\n")
    assert main.run(str(src), str(dst)) == 0
    assert dst.read_bytes() == b""
    assert check_output.check(src, dst)["ok"]


@pytest.mark.parametrize("mode, nan_text", [("nan", ""), ("nan", "nan"), ("missing", "")])
def test_degraded_synthetic_passes_checker(tmp_path, mode, nan_text):
    clean = tmp_path / "clean.csv"
    synth_euroc.write(clean, rows=6000, seed=0)
    raw, _ = degrade.degrade(euroc.read_imu_csv(clean),
                             degrade.DegradeConfig(dropout_mode=mode, healthy_s=5.0, dropout_count=2,
                                                   duplicate_rows=2, swap_rows=2), seed=3)
    src = tmp_path / "deg.csv"
    euroc.write_imu_csv(raw, src, nan_text=nan_text)
    dst = tmp_path / "est.txt"
    assert main.run(str(src), str(dst)) == len(raw)
    r = check_output.check(src, dst)
    assert r["ok"], r["errors"]


def test_deterministic_bytes(tmp_path):
    src = tmp_path / "imu.csv"
    src.write_bytes(MESSY)
    main.run(str(src), str(tmp_path / "a.txt"))
    main.run(str(src), str(tmp_path / "b.txt"))
    assert (tmp_path / "a.txt").read_bytes() == (tmp_path / "b.txt").read_bytes()


def test_runs_standalone_from_src_folder(tmp_path):
    """Copied alone into src/ and run isolated (-I -S): no vortex package, no site-packages."""
    srcdir = tmp_path / "src"
    srcdir.mkdir()
    shutil.copy(MAIN, srcdir / "main.py")
    (tmp_path / "imu.csv").write_bytes(MESSY)
    p = subprocess.run([sys.executable, "-I", "-S", str(srcdir / "main.py"), "imu.csv", "est.txt"],
                       cwd=tmp_path, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert p.stdout == "" and p.stderr == ""
    assert check_output.check(tmp_path / "imu.csv", tmp_path / "est.txt")["ok"]


def test_cli_errors(tmp_path):
    p = subprocess.run([sys.executable, "-S", str(MAIN)], capture_output=True, text=True)
    assert p.returncode == 2 and "usage" in p.stderr.lower()
    p = subprocess.run([sys.executable, "-S", str(MAIN), str(tmp_path / "nope.csv"), str(tmp_path / "o.txt")],
                       capture_output=True, text=True)
    assert p.returncode == 1 and "nope.csv" in p.stderr


def _traced_peak(src, dst):
    tracemalloc.start()
    try:
        main.run(str(src), str(dst))
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_memory_gate_bounded_and_flat(tmp_path):
    """tracemalloc peak < 4 MB, and does not grow with flight length (3 min vs 15 min, SYNTHETIC)."""
    short, long_ = tmp_path / "short.csv", tmp_path / "long.csv"
    synth_euroc.write(short, rows=36_000, seed=0)
    synth_euroc.write(long_, rows=180_000, seed=1)
    p_short = _traced_peak(short, tmp_path / "o1.txt")
    p_long = _traced_peak(long_, tmp_path / "o2.txt")
    assert p_long < 4 * 2**20, p_long
    assert p_long - p_short < 64 * 1024, (p_short, p_long)

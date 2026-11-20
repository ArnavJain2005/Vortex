"""Unit tests for tools/clean_machine_check.py (AG-3 harness). All inputs SYNTHETIC."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
import clean_machine_check as cmc  # noqa: E402

_DUMMY_SINGLE_MAIN = textwrap.dedent('''
import os
import sys

_SEARCH = (("imu0", "data.csv"), ("mav0", "imu0", "data.csv"), ("data.csv",))


def _find_input(folder):
    for parts in _SEARCH:
        p = os.path.join(folder, *parts)
        if os.path.isfile(p):
            return p
    csvs = [n for n in os.listdir(folder) if n.lower().endswith(".csv") and os.path.isfile(os.path.join(folder, n))]
    if len(csvs) == 1:
        return os.path.join(folder, csvs[0])
    raise ValueError("no input found")


def _parse_args(argv):
    src = dst = None
    pos = []
    a = list(argv[1:])
    while a:
        x = a.pop(0)
        if x in ("-i", "--input"):
            src = a.pop(0)
        elif x in ("-o", "--output"):
            dst = a.pop(0)
        else:
            pos.append(x)
    if src is None and pos:
        src = pos.pop(0)
    if dst is None and pos:
        dst = pos.pop(0)
    if src is None:
        src = _find_input(os.getcwd())
    elif os.path.isdir(src):
        src = _find_input(src)
    if dst is None:
        dst = "estimated_trajectory.txt"
    return src, dst


def _write_rows(src, dst, constant=False):
    out = []
    first = True
    with open(src, "rb") as f:
        for raw in f:
            s = raw.strip()
            if not s or s.startswith(b"#"):
                continue
            ts = s.split(b",", 1)[0].strip()
            if first and not ts.isdigit():
                first = False
                continue
            first = False
            t = int(ts)
            px = 0.0 if constant else 0.1
            out.append(f"{t // 1000000000}.{t % 1000000000:09d} {px:.6f} 0.000000 0.000000 0.0000000 0.0000000 0.0000000 1.0000000\\n")
    with open(dst, "w", encoding="ascii", newline="\\n") as g:
        g.writelines(out)


def run(src, dst):
    _write_rows(src, dst, constant=False)


def main(argv):
    try:
        src, dst = _parse_args(argv)
    except Exception as e:
        sys.stderr.write(f"usage error: {e}\\n")
        return 2
    try:
        run(src, dst)
        return 0
    except Exception as e:
        sys.stderr.write(f"fallback triggered: {e}\\n")
    try:
        _write_rows(src, dst, constant=True)
        return 0
    except Exception as e:
        sys.stderr.write(f"fatal: {e}\\n")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
''')


def test_make_b2_variants_preserves_data_row_count(tmp_path):
    base = tmp_path / "base.csv"
    t0 = 1403636579758555392
    rows = ["#timestamp [ns],w_x,w_y,w_z,a_x,a_y,a_z"]
    for i in range(10):
        rows.append(f"{t0 + i * 5_000_000},0.0,0.0,0.0,0.0,0.0,9.81")
    base.write_text("\n".join(rows) + "\n", encoding="ascii")

    variants = cmc.make_b2_variants(base, tmp_path)
    assert set(variants) == {
        "crlf", "no_hash_header", "no_header", "blank_lines", "spaces_after_commas", "extra_columns"
    }
    assert b"\r\n" in variants["crlf"].read_bytes()
    assert not variants["no_hash_header"].read_text(encoding="ascii").startswith("#")
    assert variants["no_header"].read_text(encoding="ascii").startswith(str(t0))


def test_clean_machine_harness_host_venv_passes_on_synthetic_single_file(tmp_path):
    main_py = tmp_path / "main.py"
    main_py.write_text(_DUMMY_SINGLE_MAIN, encoding="utf-8")

    base = tmp_path / "imu.csv"
    t0 = 1403636579758555392
    rows = ["#timestamp [ns],w_x,w_y,w_z,a_x,a_y,a_z"]
    for i in range(12):
        rows.append(f"{t0 + i * 5_000_000},0.0,0.0,0.0,0.0,0.0,9.81")
    base.write_text("\n".join(rows) + "\n", encoding="ascii")

    out_md = tmp_path / "CLEAN_MACHINE.md"
    out_json = tmp_path / "clean_machine.json"
    rc = cmc.main([
        "--main", str(main_py),
        "--input", str(base),
        "--envs", "host-venv",
        "--bench-runs", "1",
        "--commit", "synthetic",
        "--out", str(out_md),
        "--json", str(out_json),
    ])
    assert rc == 0
    md = out_md.read_text(encoding="utf-8")
    assert "PASS (all identical)" in md
    assert "From-Source Heap" in md
    assert "NONE (all <= 7 MB)" in md
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["all_passed"] is True
    assert data["all_versions_byte_identical"] is True
    assert data["any_heap_gt_7mb"] is False
    assert data["any_heap_gt_8mb"] is False
    e = data["environments"][0]
    assert len(e["b1"]) == 11
    assert len(e["b2"]) == 6
    assert len(e["b4"]) == 2
    m = e["metrics"]
    assert m["rows"] == 12
    assert m["bench_runs"] == 1
    assert m["heap_from_source_kb"] > 0
    assert m["heap_from_source_rc"] == 0
    assert m["heap_x_tracemalloc_kb"] > 0
    assert m["us_per_row"] > 0
    assert m["wall_ms_per_imu_s"] > 0
    assert m["flag_heap_gt_7mb"] is False
    assert m["flag_heap_gt_8mb"] is False


def test_format_markdown_flags_heap_over_7mb_and_8mb():
    report = {
        "artifact": "synthetic.zip",
        "commit": "deadbeef",
        "main_sha256": "0" * 64,
        "input": "imu.csv",
        "unique_ref_sha256": ["a" * 64],
        "all_versions_byte_identical": True,
        "all_passed": True,
        "any_heap_gt_7mb": True,
        "any_heap_gt_8mb": True,
        "environments": [
            {
                "env": "docker-3.12",
                "python": "3.12.7",
                "platform": "Linux",
                "ref_sha256": "a" * 64,
                "b1": [],
                "b2": [],
                "b4": [],
                "metrics": {
                    "heap_from_source_kb": 7300.5,
                    "heap_x_tracemalloc_kb": 8100.0,
                    "us_per_row": 35.12,
                    "wall_ms_per_imu_s": 6.84,
                    "bench_runs": 5,
                    "flag_heap_gt_7mb": True,
                    "flag_heap_gt_8mb": False,
                    "flag_wall_gt_15ms": False,
                    "flag_wall_gt_20ms": False,
                },
            },
            {
                "env": "docker-3.13",
                "python": "3.13.18",
                "platform": "Linux",
                "ref_sha256": "a" * 64,
                "b1": [],
                "b2": [],
                "b4": [],
                "metrics": {
                    "heap_from_source_kb": 8500.0,
                    "heap_x_tracemalloc_kb": 9200.0,
                    "us_per_row": 90.00,
                    "wall_ms_per_imu_s": 17.50,
                    "bench_runs": 5,
                    "flag_heap_gt_7mb": True,
                    "flag_heap_gt_8mb": True,
                    "flag_wall_gt_15ms": True,
                    "flag_wall_gt_20ms": False,
                },
            },
        ],
    }
    md = cmc.format_markdown(report)
    assert "FLAGGED" in md
    assert "**FLAG (> 7 MB)**" in md
    assert "**FAIL (> 8 MB)**" in md
    assert "**FLAG (> 15 ms)**" in md

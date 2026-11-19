"""Unit tests for tools/tumvi_l2_check.py (Task G7a). All inputs SYNTHETIC."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

from vortex.data import euroc
from vortex.geometry import quat_from_rotvec

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
import tumvi_l2_check as l2_check  # noqa: E402

MOCAP_HEADER = (
    "#timestamp [ns], p_RS_R_x [m], p_RS_R_y [m], p_RS_R_z [m], "
    "q_RS_w [], q_RS_x [], q_RS_y [], q_RS_z []"
)


def _make_synthetic_room(base_dir: Path, name: str, gyro_std: float = 0.06, acc_std: float = 0.18, n: int = 1600):
    seq = base_dir / name
    imu_dir = seq / "mav0" / "imu0"
    mocap_dir = seq / "mav0" / "mocap0"
    imu_dir.mkdir(parents=True)
    mocap_dir.mkdir(parents=True)

    t0_ns = 1520530424_000_000_000
    dt_ns = 5_000_000
    t_ns = t0_ns + np.arange(n, dtype=np.int64) * dt_ns
    s = np.arange(n) * 0.005

    p = np.column_stack([
        np.where(s > 1.0, 0.4 * np.sin(0.7 * (s - 1.0)), 0.0),
        np.where(s > 1.0, 0.3 * (1.0 - np.cos(0.7 * (s - 1.0))), 0.0),
        np.where(s > 1.0, 0.04 * (s - 1.0), 0.0),
    ])
    rv = np.column_stack([0.02 * np.sin(s), 0.02 * np.cos(s), 0.08 * s])
    q_wxyz = quat_from_rotvec(rv)

    rng = np.random.default_rng(11)
    g_noise = rng.normal(0.0, gyro_std, size=(n, 3))
    a_noise = rng.normal(0.0, acc_std, size=(n, 3))

    imu_lines = [euroc.HEADER]
    mocap_lines = [MOCAP_HEADER]
    for i in range(n):
        gx, gy, gz = 0.002 + g_noise[i, 0], -0.001 + g_noise[i, 1], 0.003 + g_noise[i, 2]
        ax, ay, az = a_noise[i, 0], a_noise[i, 1], 9.81 + a_noise[i, 2]
        imu_lines.append(f"{t_ns[i]},{gx:.6f},{gy:.6f},{gz:.6f},{ax:.6f},{ay:.6f},{az:.6f}")
        mocap_lines.append(
            f"{t_ns[i]},{p[i,0]:.6f},{p[i,1]:.6f},{p[i,2]:.6f},"
            f"{q_wxyz[i,0]:.7f},{q_wxyz[i,1]:.7f},{q_wxyz[i,2]:.7f},{q_wxyz[i,3]:.7f}"
        )

    (imu_dir / "data.csv").write_text("\n".join(imu_lines) + "\n", encoding="ascii")
    (mocap_dir / "data.csv").write_text("\n".join(mocap_lines) + "\n", encoding="ascii")
    return seq


def _make_synthetic_official_copy(clean_seq: Path, off_root: Path, reading: str, seed: int):
    copy_name = f"{clean_seq.name}_{reading}_s{seed}"
    cdir = off_root / copy_name
    imu_dir = cdir / "mav0" / "imu0"
    imu_dir.mkdir(parents=True)

    lines = (clean_seq / "mav0" / "imu0" / "data.csv").read_text(encoding="ascii").splitlines()
    hdr, data = lines[0], lines[1:]
    # Drop a 10-row burst around row 400..410 and zero the final 200 rows (1.0 s blind tail)
    kept = []
    for idx, line in enumerate(data):
        if 400 <= idx < 410:
            continue
        if idx >= len(data) - 200:
            ts = line.split(",", 1)[0]
            kept.append(f"{ts},0.0,0.0,0.0,0.0,0.0,0.0")
        else:
            kept.append(line)
    (imu_dir / "data.csv").write_text("\n".join([hdr] + kept) + "\n", encoding="ascii")

    t0_ns = int(data[0].split(",", 1)[0])
    t_before = (int(data[399].split(",", 1)[0]) - t0_ns) / 1e9
    t_after = (int(data[410].split(",", 1)[0]) - t0_ns) / 1e9
    t_end = (int(data[-1].split(",", 1)[0]) - t0_ns) / 1e9
    events = {
        "source": "synthetic test",
        "seed": seed,
        "reading": reading,
        "t0_ns": t0_ns,
        "healthy_end_s": 0.5,
        "dropouts_s": [[t_before, t_after]],
        "dropout_rows": [10],
        "single_missing_rows": 0,
        "failure_at_s": t_end - 1.0,
        "end_s": t_end,
        "blind_s": 1.0,
    }
    (cdir / "degrade.json").write_text(json.dumps(events, indent=1) + "\n", encoding="ascii")
    return cdir


def _make_fake_worktree(dst: Path):
    dst.mkdir(parents=True)
    shutil.copy(ROOT / "main.py", dst / "main.py")
    shutil.copy(ROOT / "pathfinder.py", dst / "pathfinder.py")
    tools_dir = dst / "tools"
    tools_dir.mkdir()
    shutil.copy(ROOT / "tools" / "baseline_still.py", tools_dir / "baseline_still.py")
    return dst


def test_guard_refuses_held_out_rooms_v2_and_reserved_seeds(tmp_path):
    for bad_seq in (
        "dataset-room3_512_16",
        "dataset-room4_512_16",
        "dataset-room5_512_16",
        "dataset-room6_512_16",
        "V2_01_easy",
    ):
        with pytest.raises(SystemExit):
            l2_check.guard_inputs([bad_seq], [1, 2, 3])

    for bad_seed in range(10, 19):
        with pytest.raises(SystemExit):
            l2_check.guard_inputs(["dataset-room1_512_16"], [bad_seed])


def test_compare_builds_and_cli_on_synthetic_rooms(tmp_path, capsys):
    tumvi_root = tmp_path / "tumvi"
    off_root = tmp_path / "official_tumvi"
    s1 = _make_synthetic_room(tumvi_root, "dataset-room1_512_16")
    for reading in ("a", "b"):
        _make_synthetic_official_copy(s1, off_root, reading, seed=1)

    w_off = _make_fake_worktree(tmp_path / "wt_off")
    w_on = _make_fake_worktree(tmp_path / "wt_on")
    out_json = tmp_path / "report.json"

    rc = l2_check.main([
        "--dir-off", str(w_off),
        "--dir-on", str(w_on),
        "--commit-off", "d1fc504",
        "--commit-on", "3559fe4",
        "--tumvi-root", str(tumvi_root),
        "--official-root", str(off_root),
        "--seqs", "dataset-room1_512_16",
        "--readings", "a,b",
        "--seeds", "1",
        "--json", str(out_json),
    ])
    assert rc == 0
    md = capsys.readouterr().out
    assert "### Per-copy comparison (`off = d1fc504`, `on = 3559fe4`)" in md
    assert "### Summary by reading (`off = d1fc504`, `on = 3559fe4`)" in md
    assert "`dataset-room1_512_16_a_s1`" in md

    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["commit_off"] == "d1fc504"
    assert data["commit_on"] == "3559fe4"
    assert len(data["rows"]) == 3  # 1 clean + 2 official copies
    for row in data["rows"]:
        assert row["contract_off"] == "PASS"
        assert row["contract_on"] == "PASS"
        assert row["byte_identical"] is True
        assert row["ape_diff"] == pytest.approx(0.0, abs=1e-12)
        assert row["cal_source_off"] in {"still_run", "init_window_still", "fallback_zero"}
    assert data["summary"]["a+b"]["ape_counts"] == {"better": 0, "worse": 0, "same": 2, "total": 2}

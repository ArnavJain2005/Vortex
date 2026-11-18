"""Unit tests for tools/tumvi_still_probe.py (Task G6). All inputs SYNTHETIC."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from vortex.data import euroc

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
import tumvi_still_probe as probe  # noqa: E402


def _write_synthetic_room(base_dir: Path, name: str, gyro_std: float, acc_std: float, n: int = 1200):
    seq = base_dir / name
    imu_dir = seq / "mav0" / "imu0"
    mocap_dir = seq / "mav0" / "mocap0"
    imu_dir.mkdir(parents=True)
    mocap_dir.mkdir(parents=True)

    rng = np.random.default_rng(7)
    t0_ns = 1520530308_000_000_000
    t_ns = t0_ns + np.arange(n, dtype=np.int64) * 5_000_000
    g = rng.normal(0.0, gyro_std, size=(n, 3)) + np.array([0.01, -0.01, 0.005])
    a = rng.normal(0.0, acc_std, size=(n, 3)) + np.array([0.0, 0.0, 9.81])

    imu_lines = [euroc.HEADER]
    mocap_lines = ["#timestamp [ns],p_x,p_y,p_z,q_w,q_x,q_y,q_z"]
    for i in range(n):
        imu_lines.append(f"{t_ns[i]},{g[i,0]:.6f},{g[i,1]:.6f},{g[i,2]:.6f},{a[i,0]:.6f},{a[i,1]:.6f},{a[i,2]:.6f}")
        mocap_lines.append(f"{t_ns[i]},0.0,0.0,1.0,1.0,0.0,0.0,0.0")

    (imu_dir / "data.csv").write_text("\n".join(imu_lines) + "\n", encoding="ascii")
    (mocap_dir / "data.csv").write_text("\n".join(mocap_lines) + "\n", encoding="ascii")
    return seq


def test_still_probe_identifies_passing_and_failing_windows(tmp_path):
    # Room 1: quiet enough to pass (gyro_std ~ 0.002 < 0.02, acc_std ~ 0.02 < 0.1)
    _write_synthetic_room(tmp_path, "dataset-room1_512_16", gyro_std=0.002, acc_std=0.02, n=1200)
    # Room 2: hand-tremor level (gyro_std ~ 0.06 > 0.02, acc_std ~ 0.18 > 0.1)
    _write_synthetic_room(tmp_path, "dataset-room2_512_16", gyro_std=0.06, acc_std=0.18, n=1200)

    out_json = tmp_path / "probe.json"
    rc = probe.main(["--root", str(tmp_path), "--json", str(out_json)])
    assert rc == 0
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["rule"]["constants"]["STILL_GYRO_STD"] == pytest.approx(0.02)
    assert data["rule"]["constants"]["STILL_ACC_STD"] == pytest.approx(0.1)

    p1, p2 = data["probes"]
    assert p1["windows_1s_passing_count"] == 6
    assert p1["best_1s_window_combined"]["gyro_std_factor"] < 1.0
    assert p1["best_1s_window_combined"]["acc_std_factor"] < 1.0

    assert p2["windows_1s_passing_count"] == 0
    assert p2["best_1s_window_combined"]["gyro_std_factor"] > 2.0
    assert p2["best_1s_window_combined"]["acc_std_factor"] > 1.2


def test_still_probe_refuses_held_out_and_v2_sequences(tmp_path):
    for bad in ("dataset-room3_512_16", "dataset-room4_512_16", "V2_01_easy"):
        with pytest.raises(SystemExit):
            probe.main(["--root", str(tmp_path), "--seqs", bad])

"""Ground-truth CSV and sequence-directory support for the independent scorer."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

SCORER = Path(__file__).resolve().parents[2] / "tools" / "ape_check.py"


@pytest.mark.parametrize("folder", ["state_groundtruth_estimate0", "mocap0"])
def test_20_row_real_layout_ground_truth_from_sequence_and_csv(tmp_path: Path, folder: str) -> None:
    """Independently construct EuRoC and TUM-VI layouts, including w-first quaternions."""
    sequence = tmp_path / "sequence"
    csv_path = sequence / "mav0" / folder / "data.csv"
    csv_path.parent.mkdir(parents=True)
    estimate = tmp_path / "estimate.txt"
    t0 = 1_403_636_579_758_555_392
    rows, estimates = ["#timestamp [ns],p_x,p_y,p_z,q_w,q_x,q_y,q_z\n"], []
    for i in range(20):
        x, y, z = (i * 0.2, (i % 4) * 0.3, (i * i % 7) * 0.1)
        ns = t0 + i * 50_000_000
        # Nonidentity w,x,y,z ensures quaternion columns cannot be read as position.
        quaternion = "0.7071067811865476,0,0,0.7071067811865476"
        extra = ",0,0,0,0,0,0,0,0,0" if folder == "state_groundtruth_estimate0" else ""
        rows.append(f"{ns},{-y + 3},{x - 4},{z + 2},{quaternion}{extra}\n")
        estimates.append(f"{ns / 1e9:.9f} {x} {y} {z} 0 0 0 1\n")
    csv_path.write_text("".join(rows), encoding="ascii")
    estimate.write_text("".join(estimates), encoding="ascii")
    for gt in (sequence, csv_path):
        result = subprocess.run([sys.executable, str(SCORER), "--gt", str(gt), "--est", str(estimate)],
                                capture_output=True, text=True, timeout=10, check=False)
        assert result.returncode == 0, result.stderr
        assert "Matched poses: 20" in result.stdout
        assert float(next(line.split(": ")[1] for line in result.stdout.splitlines()
                          if line.startswith("ATE RMSE m:"))) < 1e-9

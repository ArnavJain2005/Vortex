"""Exact synthetic answers for the separately written SE(3) scorer."""

from __future__ import annotations

import math
from pathlib import Path
import subprocess
import sys

import pytest

SCORER = Path(__file__).resolve().parents[2] / "tools" / "ape_check.py"


def _write(path: Path, points: list[tuple[float, float, float]], *, shift_s: float = 0) -> None:
    path.write_text("".join(
        f"{i * 0.1 + shift_s:.6f} {x:.12f} {y:.12f} {z:.12f} 0 0 0 1\n"
        for i, (x, y, z) in enumerate(points)
    ), encoding="ascii")


def _score(tmp_path: Path, truth: list[tuple[float, float, float]],
           estimate: list[tuple[float, float, float]], shift_s: float = 0) -> dict[str, float]:
    gt_file, est_file = tmp_path / "truth.txt", tmp_path / "estimate.txt"
    _write(gt_file, truth)
    _write(est_file, estimate, shift_s=shift_s)
    result = subprocess.run([sys.executable, str(SCORER), str(gt_file), str(est_file)],
                            capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    return {line.split(": ")[0]: float(line.split(": ")[1]) for line in result.stdout.splitlines()}


def test_known_rigid_transform_has_zero_ape(tmp_path: Path) -> None:
    estimate = [(0, 0, 0), (2, 0, 0), (0, 3, 0), (0, 0, 4), (1, 2, 3), (-2, 1, 4)]
    truth = [(-y + 7, x - 4, z + 2) for x, y, z in estimate]  # 90-degree yaw + translation
    scores = _score(tmp_path, truth, estimate, shift_s=0.004)
    assert scores["ATE RMSE m"] < 1e-9
    assert scores["Matched poses"] == len(truth)


def test_full_3d_rigid_rotation_has_zero_ape(tmp_path: Path) -> None:
    estimate = [(0, 0, 0), (1, 2, -1), (-3, 0, 2), (4, -2, 5), (2, 1, 3)]
    # Compose a quarter-turn about x with a quarter-turn about z.
    truth = [(-y + 3, -z - 7, x + 2) for x, y, z in estimate]
    scores = _score(tmp_path, truth, estimate)
    assert scores["ATE RMSE m"] < 1e-9


def test_single_known_offset_after_alignment(tmp_path: Path) -> None:
    truth = [(x, 0, 0) for x in (-2, -1, 0, 1, 2)]
    estimate = truth.copy()
    estimate[2] = (0, 0, 2)
    scores = _score(tmp_path, truth, estimate)
    # The offset has zero covariance with x. Centring leaves residuals 1.6
    # for the middle point and 0.4 for each other point: RMSE = 0.8.
    assert scores["ATE RMSE m"] == pytest.approx(0.8, abs=1e-10)
    assert scores["ATE mean m"] == pytest.approx(0.64, abs=1e-10)
    assert scores["ATE max m"] == pytest.approx(1.6, abs=1e-10)


def test_never_moving_floor_is_truth_spread(tmp_path: Path) -> None:
    truth = [(0, 0, 0), (2, 0, 0), (0, 3, 0), (0, 0, 4), (1, 2, 3)]
    estimate = [(100, -50, 10)] * len(truth)
    centre = tuple(sum(point[k] for point in truth) / len(truth) for k in range(3))
    expected = math.sqrt(sum(math.dist(point, centre) ** 2 for point in truth) / len(truth))
    scores = _score(tmp_path, truth, estimate)
    assert scores["ATE RMSE m"] == pytest.approx(expected, abs=1e-10)
    assert scores["Matched poses"] == len(truth)


def test_default_association_rejects_more_than_10_ms(tmp_path: Path) -> None:
    gt = tmp_path / "truth.txt"
    est = tmp_path / "estimate.txt"
    gt.write_text("0.000 0 0 0 0 0 0 1\n0.100 1 0 0 0 0 0 1\n", encoding="ascii")
    est.write_text("0.009 0 0 0 0 0 0 1\n0.111 1 0 0 0 0 0 1\n", encoding="ascii")
    result = subprocess.run([sys.executable, str(SCORER), str(gt), str(est)],
                            capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    assert "Matched poses: 1" in result.stdout



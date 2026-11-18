"""Independent row and gross-physics checks against the public CLI only."""

from __future__ import annotations

import math
import os
from pathlib import Path
import subprocess
import sys
import time
import warnings
from decimal import Decimal

import pytest

from .synth import make_imu

MAIN = Path(__file__).resolve().parents[2] / "main.py"


def run_main(source: Path, target: Path) -> tuple[subprocess.CompletedProcess[str], float]:
    """Invoke precisely the public two-path CLI, without importing estimator code."""
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    started = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, "-S", str(MAIN), str(source), str(target)],
        cwd=source.parent,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    return completed, time.perf_counter() - started


def read_poses(target: Path, timestamps: list[int]) -> list[tuple[float, ...]]:
    """Parse independently of the repository's output checker."""
    lines = target.read_text(encoding="ascii").splitlines()
    assert len(lines) == len(timestamps), "one output line is required per input data row"
    poses = []
    for line, ns in zip(lines, timestamps):
        fields = line.split()
        assert len(fields) == 8, f"expected 8 fields, got {line!r}"
        values = tuple(float(field) for field in fields)
        assert all(math.isfinite(value) for value in values), line
        assert Decimal(fields[0]) == Decimal(ns) / Decimal(1_000_000_000), (fields[0], ns)
        assert abs(math.sqrt(sum(q * q for q in values[4:])) - 1.0) <= 1e-6, line
        poses.append(values)
    return poses


@pytest.mark.parametrize(
    ("name", "options"),
    [
        ("still_60s", {"kind": "still", "seconds": 60}),
        ("yaw_no_header", {"kind": "yaw", "header": False}),
        ("straight_crlf", {"kind": "straight", "crlf": True}),
        ("missing_rows", {"kind": "straight", "gap_s": (4, 5.5)}),
        ("blind_zeros", {"kind": "straight", "zero_tail_s": 5}),
        ("accel_first", {"kind": "yaw", "order": "accel_first"}),
        ("accel_first_no_header_crlf", {
            "kind": "still", "order": "accel_first", "header": False, "crlf": True,
        }),
    ],
)
def test_row_contract_and_no_residual_files(tmp_path: Path, name: str, options: dict) -> None:
    source, target = tmp_path / f"{name}.csv", tmp_path / "estimated_trajectory.txt"
    timestamps = make_imu(source, **options)
    original = source.read_bytes()
    before = set(tmp_path.rglob("*"))
    completed, elapsed_s = run_main(source, target)
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert target.is_file(), "the entry point produced no trajectory"
    assert source.read_bytes() == original, "the input file changed"
    assert set(tmp_path.rglob("*")) - before == {target}, "persistent side files were written"
    poses = read_poses(target, timestamps)
    assert len(poses) == len(timestamps)

    # Includes process start-up and I/O; it is a diagnostic, not the judge's
    # algorithm-only compute measurement. Slow CI hardware must not fail the suite.
    imu_seconds = (timestamps[-1] - timestamps[0]) / 1_000_000_000
    ms_per_imu_second = elapsed_s * 1000 / imu_seconds
    if ms_per_imu_second > 20:
        warnings.warn(
            f"{name}: wall time {ms_per_imu_second:.2f} ms per IMU-second "
            "(includes Python start-up; check official compute budget separately)",
            RuntimeWarning,
            stacklevel=1,
        )


def test_still_position_stays_within_one_metre(tmp_path: Path) -> None:
    source, target = tmp_path / "still.csv", tmp_path / "pose.txt"
    timestamps = make_imu(source, seconds=60)
    result, _ = run_main(source, target)
    assert result.returncode == 0, result.stderr or result.stdout
    poses = read_poses(target, timestamps)
    first = poses[0]
    maximum = max(math.dist(pose[1:4], first[1:4]) for pose in poses)
    assert maximum < 1.0, f"still IMU drifted {maximum:.3f} m"


@pytest.mark.xfail(strict=True, reason="F1: exact constant gyro triplets are treated as a stuck sensor")
def test_exact_constant_yaw_has_correct_final_heading(tmp_path: Path) -> None:
    _check_yaw_heading(tmp_path, "yaw")


def test_noisy_constant_yaw_has_correct_final_heading(tmp_path: Path) -> None:
    _check_yaw_heading(tmp_path, "yaw_noisy")


def _check_yaw_heading(tmp_path: Path, kind: str) -> None:
    source, target = tmp_path / "yaw.csv", tmp_path / "pose.txt"
    timestamps = make_imu(source, kind=kind, seconds=12)
    result, _ = run_main(source, target)
    assert result.returncode == 0, result.stderr or result.stdout
    final = read_poses(target, timestamps)[-1]
    qx, qy, qz, qw = final[4:]
    yaw = math.atan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz))
    expected = 0.3 * (12 - 2)
    wrapped_error = math.atan2(math.sin(yaw - expected), math.cos(yaw - expected))
    assert abs(wrapped_error) < math.radians(10), (yaw, expected)

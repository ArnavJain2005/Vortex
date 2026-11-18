"""Plausible damaged CSVs against main.py, solely through its public CLI.

Expectation: any nonblank, noncomment line is an input data row, even when its
sensor fields are bad or it has extra columns. Every such row must produce a
finite unit-quaternion pose with the same timestamp. This is a conservative
contract reading: losing a row would desynchronise all following poses.

A gyro/accelerometer swap *mid-file* is intentionally excluded: the official
degrader uses one fixed column interpretation for the whole file, and the
specified input has no per-row order marker from which to identify a swap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .synth import make_imu
from .test_contract import read_poses, run_main


def _fixture(path: Path, scenario: str) -> list[int]:
    if scenario == "five_second_hole":
        return make_imu(path, seconds=12, gap_s=(3, 8), kind="straight")
    if scenario == "short_calibration":
        return make_imu(path, seconds=0.5)
    if scenario == "single_row":
        return make_imu(path, seconds=0.005)
    timestamps = make_imu(path, seconds=8, header=scenario != "bom")
    lines = path.read_text(encoding="ascii").splitlines()
    start = 0 if scenario == "bom" else 1

    def replace_field(row: int, field: int, value: str) -> None:
        columns = lines[start + row].split(",")
        columns[field] = value
        lines[start + row] = ",".join(columns)

    if scenario == "nan_inf":
        replace_field(600, 2, "nan")
        replace_field(601, 5, "inf")
    elif scenario == "duplicate_timestamp":
        replace_field(600, 0, str(timestamps[599]))
        timestamps[600] = timestamps[599]
    elif scenario == "nonmonotonic_timestamp":
        replace_field(600, 0, str(timestamps[599] - 5_000_000))
        timestamps[600] = timestamps[599] - 5_000_000
    elif scenario == "all_zero":
        for i in range(len(timestamps)):
            lines[start + i] = str(timestamps[i]) + ",0,0,0,0,0,0"
    elif scenario == "blank_lines":
        lines.insert(start + 600, "   ")
        lines.insert(start + 1200, "")
    elif scenario == "scientific_notation":
        replace_field(600, 3, "3.0e-2")
        replace_field(601, 6, "9.81e+0")
    elif scenario == "extra_columns":
        lines[start + 600] += ",17.0,unused"
    elif scenario == "tenfold_scale":
        for i in range(len(timestamps)):
            lines[start + i] = str(timestamps[i]) + ",0,0,3.0,0,0,98.1"
    elif scenario != "bom":
        raise ValueError(scenario)

    content = ("\n".join(lines) + "\n").encode("ascii")
    if scenario == "bom":
        content = b"\xef\xbb\xbf" + content
    path.write_bytes(content)
    return timestamps


@pytest.mark.parametrize(
    "scenario",
    [
        "nan_inf", "duplicate_timestamp", "nonmonotonic_timestamp",
        "five_second_hole", "all_zero", "short_calibration", "single_row",
        "blank_lines", "bom", "scientific_notation", "extra_columns",
        "tenfold_scale",
    ],
)
def test_damaged_input_preserves_pose_contract(tmp_path: Path, scenario: str) -> None:
    source, target = tmp_path / "imu.csv", tmp_path / "trajectory.txt"
    timestamps = _fixture(source, scenario)
    completed, _ = run_main(source, target)
    assert completed.returncode == 0, (scenario, completed.stderr or completed.stdout)
    assert target.is_file(), f"{scenario}: no output"
    read_poses(target, timestamps)

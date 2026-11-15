"""Loader for the ADVIO dataset (Cortes et al., ECCV 2018).

Data: https://github.com/AaltoVision/ADVIO (CC BY-NC 4.0; cite the paper, no commercial use).
Download the per-sequence archives (advio-01.zip ... advio-23.zip) and unzip them so that

    <root>/advio-01/ground-truth/poses.csv
    <root>/advio-01/iphone/accelerometer.csv
    <root>/advio-01/iphone/gyroscope.csv   (some copies call it gyro.csv)
    <root>/advio-01/iphone/arkit.csv
    <root>/advio-01/pixel/arcore.csv       (optional)

File formats, as read by ADVIO's own scripts (scripts/visualization/my_utils.py,
scripts/rosbag/sync-data.py):
- Every CSV is headerless; column 0 is a timestamp in seconds on a clock shared by all sensors.
- Pose files (poses.csv, arkit.csv, arcore.csv): t, px, py, pz, qw, qx, qy, qz.
- accelerometer.csv, gyroscope.csv: t, x, y, z. Accelerometer in g (README); gyroscope assumed rad/s.

Unverified until run on the real files (see `vortex check`):
- ACCEL_SIGN. Apple CoreMotion reports about -1 g on the axis pointing up when the phone is at rest,
  i.e. the negative of specific force, so the default is -1. `vortex check` tests both signs against
  ground truth and reports which one fits.
- Gyroscope units (rad/s) and that the gyroscope axes match the accelerometer axes.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..types import ImuData, Sequence, Trajectory
from ..geometry import quat_normalize

STANDARD_GRAVITY = 9.80665

# Named parameter, not a measured fact: see module docstring.
ACCEL_SIGN = -1.0

# Approximate additive IMU biases published in ADVIO calibration/README.md, per collection batch,
# in raw units (accelerometer in g, gyroscope in rad/s). Corrected = raw - bias, matching ADVIO's
# own advio_to_rosbag.py. Keys are inclusive sequence-number ranges.
ADVIO_IMU_BIAS = {
    (1, 12): {"accel": (0.0407, -0.0623, 0.1017), "gyro": (-0.0067, 0.0070, -0.0065)},
    (13, 17): {"accel": (0.0415, -0.0617, 0.1008), "gyro": (-0.0065, 0.0055, -0.0064)},
    (18, 19): {"accel": (0.0393, -0.0635, 0.1024), "gyro": (-0.0069, 0.0062, -0.0067)},
    (20, 23): {"accel": (0.0405, -0.0620, 0.1012), "gyro": (-0.0066, 0.0065, -0.0063)},
}

# Rotation part of T_cam_imu from ADVIO calibration (Kalibr), identical in all four batch files.
# Maps vectors from the IMU frame into the camera frame.
R_CAM_IMU = np.array(
    [
        [0.9999763379093255, -0.004079205042965442, -0.005539287650170447],
        [-0.004066386342107199, -0.9999890330121858, 0.0023234365646622014],
        [-0.00554870467502187, -0.0023008567036498766, -0.9999819588046867],
    ]
)


def sequence_dir(root: str | Path, number: int) -> Path:
    return Path(root) / f"advio-{number:02d}"


def bias_for(number: int) -> dict | None:
    for (lo, hi), b in ADVIO_IMU_BIAS.items():
        if lo <= number <= hi:
            return b
    return None


def load_sequence(
    root: str | Path,
    number: int,
    pose_source: str = "arkit",
    accel_sign: float = ACCEL_SIGN,
    remove_bias: bool = True,
) -> Sequence:
    """Load one ADVIO sequence.

    pose_source: "arkit" (iPhone, 60 Hz) or "arcore" (Pixel, 30 Hz). This is the stream we degrade.
    """
    d = sequence_dir(root, number)
    if not d.is_dir():
        raise FileNotFoundError(f"{d} not found. Unzip advio-{number:02d}.zip into {Path(root)}.")

    gt = read_pose_csv(d / "ground-truth" / "poses.csv", name="ground_truth")
    if pose_source == "arkit":
        pose = read_pose_csv(d / "iphone" / "arkit.csv", name="arkit")
    elif pose_source == "arcore":
        pose = read_pose_csv(d / "pixel" / "arcore.csv", name="arcore")
    else:
        raise ValueError("pose_source must be 'arkit' or 'arcore'")

    gyro_path = _first_existing(d / "iphone" / "gyroscope.csv", d / "iphone" / "gyro.csv")
    t_g, gyro, dropped_g = read_xyz_csv(gyro_path)
    t_a, acc, dropped_a = read_xyz_csv(d / "iphone" / "accelerometer.csv")

    bias = bias_for(number) if remove_bias else None
    if bias is not None:
        gyro = gyro - np.asarray(bias["gyro"])
        acc = acc - np.asarray(bias["accel"])

    # Resample the accelerometer onto gyroscope timestamps (as ADVIO's sync-data.py does),
    # keeping only the time span both sensors cover.
    keep = (t_g >= t_a[0]) & (t_g <= t_a[-1])
    t = t_g[keep]
    acc_on_g = np.column_stack([np.interp(t, t_a, acc[:, i]) for i in range(3)])
    imu = ImuData(t=t, gyro=gyro[keep], accel=accel_sign * STANDARD_GRAVITY * acc_on_g)

    meta = {
        "dataset": "ADVIO",
        "sequence": number,
        "pose_source": pose_source,
        "accel_sign": accel_sign,
        "imu_bias_removed": bias is not None,
        "dropped_non_increasing": {"gyro": dropped_g, "accel": dropped_a, **gt.meta, **pose.meta},
        "R_cam_imu": R_CAM_IMU.tolist(),
        "body_frame_note": "ground truth and ARKit poses are camera poses; IMU is in the IMU frame",
    }
    return Sequence(name=f"advio-{number:02d}", imu=imu, pose=pose, ground_truth=gt, meta=meta)


def read_pose_csv(path: str | Path, name: str = "") -> Trajectory:
    arr = _read_numeric(path, ncols=8)
    arr, dropped = _strictly_increasing(arr)
    q = quat_normalize(arr[:, 4:8])
    return Trajectory(t=arr[:, 0], p=arr[:, 1:4], q=q, name=name, meta={f"{name}_dropped": dropped})


def read_xyz_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray, int]:
    arr = _read_numeric(path, ncols=4)
    arr, dropped = _strictly_increasing(arr)
    return arr[:, 0], arr[:, 1:4], dropped


def _read_numeric(path: str | Path, ncols: int) -> np.ndarray:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    df = pd.read_csv(path, header=None)
    if df.shape[1] < ncols:
        raise ValueError(f"{path}: expected at least {ncols} columns, found {df.shape[1]}")
    arr = df.iloc[:, :ncols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    arr = arr[np.all(np.isfinite(arr), axis=1)]
    if len(arr) < 2:
        raise ValueError(f"{path}: fewer than 2 valid rows")
    return arr


def _strictly_increasing(arr: np.ndarray) -> tuple[np.ndarray, int]:
    """Sort by time and drop rows whose timestamp does not increase. Returns (rows, dropped count)."""
    arr = arr[np.argsort(arr[:, 0], kind="stable")]
    keep = np.concatenate([[True], np.diff(arr[:, 0]) > 0])
    return arr[keep], int((~keep).sum())


def _first_existing(*paths: Path) -> Path:
    for p in paths:
        if p.is_file():
            return p
    raise FileNotFoundError(" or ".join(str(p) for p in paths))

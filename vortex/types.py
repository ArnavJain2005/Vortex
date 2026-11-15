"""Plain data containers shared by loaders, estimators and metrics."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class ImuData:
    """Inertial samples in the body (IMU) frame, SI units.

    t:     (N,) seconds, strictly increasing
    gyro:  (N, 3) angular velocity, rad/s
    accel: (N, 3) specific force, m/s^2 (reads +g upwards when the device is at rest)
    """

    t: np.ndarray
    gyro: np.ndarray
    accel: np.ndarray

    def __post_init__(self) -> None:
        _check_series(self.t, {"gyro": self.gyro, "accel": self.accel}, width=3)


@dataclass
class Trajectory:
    """Timestamped 6-DoF poses.

    t: (N,) seconds, strictly increasing
    p: (N, 3) position, metres, world frame
    q: (N, 4) orientation quaternion (w, x, y, z), body-to-world
    """

    t: np.ndarray
    p: np.ndarray
    q: np.ndarray
    name: str = ""
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        _check_series(self.t, {"p": self.p}, width=3)
        _check_series(self.t, {"q": self.q}, width=4)

    def __len__(self) -> int:
        return len(self.t)

    def slice_time(self, t0: float, t1: float) -> "Trajectory":
        m = (self.t >= t0) & (self.t <= t1)
        return Trajectory(self.t[m], self.p[m], self.q[m], self.name, dict(self.meta))

    def path_length(self) -> float:
        if len(self.t) < 2:
            return 0.0
        return float(np.sum(np.linalg.norm(np.diff(self.p, axis=0), axis=1)))


@dataclass
class Sequence:
    """One recording: IMU, the device's own tracking pose stream, and ground truth."""

    name: str
    imu: ImuData
    pose: Trajectory  # e.g. ARKit / ARCore visual-inertial pose, the stream faults are applied to
    ground_truth: Trajectory
    meta: dict = field(default_factory=dict)


def _check_series(t: np.ndarray, cols: dict, width: int) -> None:
    t = np.asarray(t)
    if t.ndim != 1:
        raise ValueError("timestamps must be 1-D")
    if len(t) > 1 and not np.all(np.diff(t) > 0):
        raise ValueError("timestamps must be strictly increasing")
    for name, arr in cols.items():
        arr = np.asarray(arr)
        if arr.shape != (len(t), width):
            raise ValueError(f"{name} must have shape ({len(t)}, {width}), got {arr.shape}")
        if not np.all(np.isfinite(arr)):
            raise ValueError(f"{name} contains non-finite values")

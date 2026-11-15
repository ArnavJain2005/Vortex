"""Trajectory file output in TUM format, readable by evo (`evo_ape tum gt.txt est.txt -a`)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .types import Trajectory


def write_tum(traj: Trajectory, path: str | Path) -> None:
    """Write 'timestamp tx ty tz qx qy qz qw' lines (TUM order puts qw last)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    q_xyzw = traj.q[:, [1, 2, 3, 0]]
    np.savetxt(path, np.column_stack([traj.t, traj.p, q_xyzw]), fmt="%.9f")


def read_tum(path: str | Path, name: str = "") -> Trajectory:
    arr = np.loadtxt(path, ndmin=2)
    return Trajectory(t=arr[:, 0], p=arr[:, 1:4], q=arr[:, [7, 4, 5, 6]], name=name)

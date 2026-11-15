"""EuRoC MAV / TUM-VI loader (ASL layout): `mav0/imu0/data.csv` and, for scoring only, ground truth.

IMU file (the Track 3 input), header
    #timestamp [ns],w_RS_S_x [rad s^-1],w_RS_S_y [rad s^-1],w_RS_S_z [rad s^-1],
    a_RS_S_x [m s^-2],a_RS_S_y [m s^-2],a_RS_S_z [m s^-2]
Gyro in rad/s, body frame; accel is specific force in m/s^2 (includes gravity, +g up at rest).

Row definition (shared with check_output.py and main.py): a DATA ROW is any line that is not empty
or whitespace-only and does not start with '#'. Every data row is kept, in file order, even when its
values are NaN, empty, short, duplicated or out of order: the output needs exactly one pose per data
row. How the organisers count rows is not confirmed; blank lines are assumed not to be rows (pandas
read_csv skips them by default).

Ground truth is loaded for SCORING ONLY; no estimator may call load_ground_truth.
  EuRoC:  mav0/state_groundtruth_estimate0/data.csv   t, p(3), q(w,x,y,z), v(3), b_w(3), b_a(3)
  TUM-VI: mav0/mocap0/data.csv                         t, p(3), q(w,x,y,z)
Both: timestamps in ns, quaternion Hamilton (w, x, y, z), body-to-world.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..geometry import quat_normalize
from ..rowspec import BOM, is_data_line, seconds_text  # noqa: F401  (re-exported)
from ..types import ImuData, Trajectory

HEADER = ("#timestamp [ns],w_RS_S_x [rad s^-1],w_RS_S_y [rad s^-1],w_RS_S_z [rad s^-1],"
          "a_RS_S_x [m s^-2],a_RS_S_y [m s^-2],a_RS_S_z [m s^-2]")
GT_FOLDERS = ("state_groundtruth_estimate0", "mocap0")
NAN = float("nan")


@dataclass
class RawImu:
    """Every data row of an IMU file, in file order. NaN marks a missing or unparseable value.

    t_text: original timestamp field per row (stripped), so output timestamps can be exact
    t_ns:   int64 ns, -1 where the timestamp is not a plain integer
    gyro, accel: (N, 3) float64
    """

    t_text: list
    t_ns: np.ndarray
    gyro: np.ndarray
    accel: np.ndarray
    header: str = HEADER

    def __len__(self) -> int:
        return len(self.t_text)

    @property
    def valid(self) -> np.ndarray:
        """Rows with an integer timestamp and six finite values."""
        return (self.t_ns >= 0) & np.all(np.isfinite(self.gyro), axis=1) & np.all(np.isfinite(self.accel), axis=1)

    def seconds(self) -> np.ndarray:
        """Float seconds (NaN where the timestamp is bad). About 0.2 us resolution at EuRoC epochs."""
        return np.where(self.t_ns >= 0, self.t_ns / 1e9, np.nan)

    def to_imu_data(self) -> ImuData:
        """Clean files only (all rows valid, strictly increasing): raises ValueError otherwise."""
        if not np.all(self.valid):
            raise ValueError("%d invalid rows; to_imu_data needs a clean file" % int(np.sum(~self.valid)))
        return ImuData(t=self.t_ns / 1e9, gyro=self.gyro.copy(), accel=self.accel.copy())


def _float(s: str) -> float:
    try:
        return float(s)
    except ValueError:
        return NAN


def read_imu_csv(path: str | Path) -> RawImu:
    path = imu_path(path)
    t_text, t_ns, vals = [], [], []
    header = None
    with open(path, "rb") as f:
        for bline in f:
            if not is_data_line(bline):
                if header is None and bline.strip().lstrip(BOM).startswith(b"#"):
                    header = bline.strip().lstrip(BOM).decode("ascii", "replace")
                continue
            line = bline.decode("ascii", "replace")
            fields = line.strip().split(",")
            ts = fields[0].strip()
            t_text.append(ts)
            t_ns.append(int(ts) if seconds_text(ts) is not None else -1)
            row = [_float(x) for x in fields[1:7]]
            row += [NAN] * (6 - len(row))
            vals.append(row)
    v = np.array(vals, dtype=float).reshape(-1, 6)
    return RawImu(t_text=t_text, t_ns=np.array(t_ns, dtype=np.int64), gyro=v[:, :3].copy(),
                  accel=v[:, 3:].copy(), header=header or HEADER)


def _fmt(x: float, nan_text: str) -> str:
    return repr(float(x)) if math.isfinite(x) else (nan_text if x != x else repr(float(x)))


def write_imu_csv(raw: RawImu, path: str | Path, nan_text: str = "nan") -> None:
    """EuRoC format, '\\n' line ends, doubles with repr() (round-trips exactly)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    v = np.hstack([raw.gyro, raw.accel])
    with open(path, "w", encoding="ascii", newline="\n") as f:
        f.write(raw.header + "\n")
        for ts, row in zip(raw.t_text, v.tolist()):
            f.write(ts + "," + ",".join(_fmt(x, nan_text) for x in row) + "\n")


def _mav0(p: Path) -> Path:
    for c in (p / "mav0", p):
        if (c / "imu0").is_dir():
            return c
    raise FileNotFoundError("no mav0/imu0 under %s" % p)


def imu_path(p: str | Path) -> Path:
    """Accept the imu csv itself, a sequence folder, or its mav0 folder."""
    p = Path(p)
    if p.is_file():
        return p
    for c in (p / "mav0" / "imu0" / "data.csv", p / "imu0" / "data.csv", p / "data.csv"):
        if c.is_file():
            return c
    raise FileNotFoundError("no imu0/data.csv under %s" % p)


def load_ground_truth(seq: str | Path) -> Trajectory:
    """SCORING ONLY. Positions in m, quaternion (w, x, y, z) body-to-world, t in seconds."""
    mav0 = _mav0(Path(seq))
    for name in GT_FOLDERS:
        gt = mav0 / name / "data.csv"
        if gt.is_file():
            break
    else:
        raise FileNotFoundError("no ground truth (%s) under %s" % (", ".join(GT_FOLDERS), mav0))
    tr = read_ground_truth_csv(gt)
    tr.name = Path(seq).name
    return tr


def read_ground_truth_csv(gt: str | Path) -> Trajectory:
    """SCORING ONLY. EuRoC/TUM-VI ground-truth csv: t [ns], p(3), q(w, x, y, z), extra columns ignored."""
    t_ns, rows = [], []
    with open(gt, "r", encoding="ascii", errors="replace") as f:
        for line in f:
            if not is_data_line(line):
                continue
            fields = line.strip().split(",")
            t_ns.append(int(fields[0]))
            rows.append([float(x) for x in fields[1:8]])
    a = np.array(rows, dtype=float)
    t = np.array(t_ns, dtype=np.int64) / 1e9
    return Trajectory(t=t, p=a[:, 0:3], q=quat_normalize(a[:, 3:7]), name=Path(gt).parent.name,
                      meta={"source": str(gt), "t0_ns": int(t_ns[0])})

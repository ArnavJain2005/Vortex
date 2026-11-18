"""Small, deterministic EuRoC-format IMU inputs for independent CLI tests.

No dataset or estimator module is imported. ``gap_s`` removes physical rows;
``zero_tail_s`` retains timestamps while zeroing all six measurements.
"""

from __future__ import annotations

from pathlib import Path

T0_NS = 1_403_636_579_758_555_392
GRAVITY = 9.81
HEADER_GYRO = (
    "#timestamp [ns],w_RS_S_x [rad s^-1],w_RS_S_y [rad s^-1],"
    "w_RS_S_z [rad s^-1],a_RS_S_x [m s^-2],a_RS_S_y [m s^-2],"
    "a_RS_S_z [m s^-2]"
)
HEADER_ACCEL = (
    "#timestamp [ns],a_RS_S_x [m s^-2],a_RS_S_y [m s^-2],"
    "a_RS_S_z [m s^-2],w_RS_S_x [rad s^-1],w_RS_S_y [rad s^-1],"
    "w_RS_S_z [rad s^-1]"
)


def make_imu(
    path: Path,
    *,
    kind: str = "still",
    seconds: float = 12.0,
    hz: int = 200,
    order: str = "gyro_first",
    header: bool = True,
    crlf: bool = False,
    gap_s: tuple[float, float] | None = None,
    zero_tail_s: float = 0.0,
) -> list[int]:
    """Return the written nanosecond timestamps, excluding a physically missing gap.

    A level sensor at rest reads (0, 0, +g). Yaw begins after two seconds
    at 0.3 rad/s; straight-line acceleration begins then at 0.2 m/s².
    This is a format and gross-physics fixture, not a navigation benchmark.
    """
    if kind not in {"still", "yaw", "yaw_noisy", "straight"}:
        raise ValueError(kind)
    if order not in {"gyro_first", "accel_first"}:
        raise ValueError(order)
    if 1_000_000_000 % hz:
        raise ValueError("hz must divide one billion for exact timestamps")
    step_ns = 1_000_000_000 // hz
    count = round(seconds * hz)
    newline = "\r\n" if crlf else "\n"
    timestamps: list[int] = []
    with path.open("w", encoding="ascii", newline="") as output:
        if header:
            output.write((HEADER_GYRO if order == "gyro_first" else HEADER_ACCEL) + newline)
        for i in range(count):
            t_s = i / hz
            if gap_s is not None and gap_s[0] <= t_s < gap_s[1]:
                continue
            timestamp = T0_NS + i * step_ns
            timestamps.append(timestamp)
            gyro = (0.0, 0.0, 0.3 if kind in {"yaw", "yaw_noisy"} and t_s >= 2 else 0.0)
            accel = (0.2 if kind == "straight" and t_s >= 2 else 0.0, 0.0, GRAVITY)
            if kind == "yaw_noisy" and t_s >= 2:
                # Real sensors do not repeat an identical six-value tuple for
                # ten seconds. Tiny deterministic measurement variation keeps
                # a steady turn distinct from the organiser's stuck-row fault.
                gyro = (0.0, 0.0, 0.3 + (i % 5 - 2) * 0.0001)
                accel = (0.0, 0.0, GRAVITY + (i % 7 - 3) * 0.0001)
            if zero_tail_s and t_s >= seconds - zero_tail_s:
                gyro = accel = (0.0, 0.0, 0.0)
            values = (*gyro, *accel) if order == "gyro_first" else (*accel, *gyro)
            output.write(f"{timestamp}," + ",".join(f"{v:.9f}" for v in values) + newline)
    return timestamps

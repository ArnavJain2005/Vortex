"""Loader for our own phone recordings (Samsung Galaxy S24, Android), made with the Sensor Logger app.

App: Sensor Logger by Kelvin Tsz Hei Choi (Android: com.kelvin.sensorapp). Export a recording as
"Zipped CSV" and unzip it into a folder. Format reference:
https://github.com/tszheichoi/awesome-sensor-logger (UNITS.md, COORDINATES.md, CROSSPLATFORM.md).

What that reference states, and what this loader relies on:
- Each sensor is one CSV with a header row: `time` (UNIX epoch, nanoseconds, UTC), `seconds_elapsed`,
  then value columns. Columns are read by name, never by position.
- Android writes TotalAcceleration.csv (raw accelerometer, gravity included) and Accelerometer.csv
  (gravity removed). Units m/s^2. Android uses the "accelerating force" convention: flat on a table the
  reading is +z, i.e. specific force with +g up, which is our convention. We use TotalAcceleration.
- Gyroscope.csv: rad/s, same sign convention on iOS and Android.
- Magnetometer.csv: microtesla. Barometer.csv: `pressure` (hPa), `relativeAltitude` (m).
- Annotation.csv (optional): timestamped text notes, which we use to mark checkpoints on the floor.
- Metadata.csv: `platform` (android/ios), device name, `standardisation`.

iOS recordings are also accepted: Accelerometer + Gravity are summed and, unless "Standardise Units &
Frames" was on, negated to the Android convention.

Phone recordings have no motion-capture ground truth. They are used for the live demo and for
checkpoint tests (return to a marked start point, pass marked floor points), not for ATE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..types import ImuData


@dataclass
class Series:
    t: np.ndarray  # seconds, on the recording's common clock
    values: np.ndarray  # (N, k)
    columns: list[str]


@dataclass
class Annotation:
    t: float
    text: str


@dataclass
class PhoneRecording:
    name: str
    imu: ImuData
    magnetometer: Series | None = None
    barometer: Series | None = None
    annotations: list[Annotation] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def load_sensor_logger(folder: str | Path, rate: float = 200.0, calibrated: bool = True) -> PhoneRecording:
    """Load an unzipped Sensor Logger recording.

    Accelerometer and gyroscope run at different rates on the S24 (about 125 Hz and 500 Hz in Sensor
    Logger's published sampling table), so both are interpolated onto one uniform grid of `rate` Hz
    over the span both cover.
    """
    d = Path(folder)
    if not d.is_dir():
        raise FileNotFoundError(f"{d} not found. Unzip the Sensor Logger export into this folder.")

    meta = _read_metadata(d / "Metadata.csv")
    platform = str(meta.get("platform", "android")).lower()
    standardised = str(meta.get("standardisation", "false")).lower() == "true"

    suffix = "" if calibrated else "Uncalibrated"
    gyro_df = _read_sensor(_find(d, f"Gyroscope{suffix}.csv", "Gyroscope.csv"))

    total = d / "TotalAcceleration.csv"
    if total.is_file():
        acc_df = _read_sensor(total)
        acc_source = "TotalAcceleration"
        sign = 1.0
    else:
        # iOS: user acceleration + gravity. iOS uses the inertial-force convention unless standardised.
        user = _read_sensor(_find(d, "Accelerometer.csv"))
        grav = _read_sensor(_find(d, "Gravity.csv"))
        acc_df = _sum_on_left_times(user, grav)
        acc_source = "Accelerometer+Gravity"
        sign = -1.0 if (platform == "ios" and not standardised) else 1.0

    t0_ns = min(int(gyro_df["time"].iloc[0]), int(acc_df["time"].iloc[0]))
    tg, g = _xyz(gyro_df, t0_ns)
    ta, a = _xyz(acc_df, t0_ns)

    lo, hi = max(tg[0], ta[0]), min(tg[-1], ta[-1])
    if hi - lo < 1.0:
        raise ValueError("accelerometer and gyroscope overlap by less than 1 s")
    t = np.arange(lo, hi, 1.0 / rate)
    gyro = np.column_stack([np.interp(t, tg, g[:, i]) for i in range(3)])
    acc = sign * np.column_stack([np.interp(t, ta, a[:, i]) for i in range(3)])

    mag = _optional_series(d / f"Magnetometer{suffix}.csv", ["x", "y", "z"], t0_ns) or _optional_series(
        d / "Magnetometer.csv", ["x", "y", "z"], t0_ns
    )
    baro = _optional_series(d / "Barometer.csv", ["pressure", "relativeAltitude"], t0_ns)
    notes = _read_annotations(d / "Annotation.csv", t0_ns)

    meta.update(
        {
            "dataset": "phone",
            "recorder": "Sensor Logger",
            "accel_source": acc_source,
            "accel_sign_applied": sign,
            "resample_hz": rate,
            "raw_rate_hz": {"gyro": _median_rate(tg), "accel": _median_rate(ta)},
            "epoch_ns_at_t0": t0_ns,
            "calibrated": calibrated,
        }
    )
    return PhoneRecording(
        name=d.name,
        imu=ImuData(t=t, gyro=gyro, accel=acc),
        magnetometer=mag,
        barometer=baro,
        annotations=notes,
        meta=meta,
    )


def read_checkpoints(path: str | Path) -> dict[str, np.ndarray]:
    """Checkpoint positions measured on the floor: CSV with header `name,x,y,z` (metres).

    The annotation text typed in Sensor Logger at each checkpoint must match a `name` here.
    """
    df = pd.read_csv(path)
    missing = {"name", "x", "y", "z"} - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    return {str(r["name"]).strip(): np.array([r["x"], r["y"], r["z"]], dtype=float) for _, r in df.iterrows()}


def still_windows(imu: ImuData, window_s: float = 1.0, gyro_thresh: float = 0.05, acc_thresh: float = 0.3) -> list:
    """(start, end) spans where the phone is at rest: low rotation rate and |accel| close to g."""
    dt = float(np.median(np.diff(imu.t)))
    n = max(1, int(round(window_s / dt)))
    gyro_n = np.linalg.norm(imu.gyro, axis=1)
    acc_dev = np.abs(np.linalg.norm(imu.accel, axis=1) - 9.80665)
    still = (gyro_n < gyro_thresh) & (acc_dev < acc_thresh)
    spans, start = [], None
    for i, s in enumerate(still):
        if s and start is None:
            start = i
        elif not s and start is not None:
            if i - start >= n:
                spans.append((float(imu.t[start]), float(imu.t[i - 1])))
            start = None
    if start is not None and len(still) - start >= n:
        spans.append((float(imu.t[start]), float(imu.t[-1])))
    return spans


# ---------- helpers ----------

def _find(d: Path, *names: str) -> Path:
    for n in names:
        if (d / n).is_file():
            return d / n
    raise FileNotFoundError(f"none of {names} in {d}. Was the sensor enabled in Sensor Logger?")


def _read_sensor(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "time" not in df.columns:
        raise ValueError(f"{path}: no 'time' column; is this a Sensor Logger CSV?")
    df = df.dropna(subset=["time"]).sort_values("time", kind="stable")
    return df[df["time"].diff().fillna(1) > 0].reset_index(drop=True)


def _xyz(df: pd.DataFrame, t0_ns: int) -> tuple[np.ndarray, np.ndarray]:
    for c in ("x", "y", "z"):
        if c not in df.columns:
            raise ValueError(f"missing column {c!r}")
    t = (df["time"].to_numpy(dtype=np.int64) - t0_ns) / 1e9
    v = df[["x", "y", "z"]].to_numpy(dtype=float)
    ok = np.all(np.isfinite(v), axis=1)
    return t[ok], v[ok]


def _sum_on_left_times(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    out = a[["time"]].copy()
    tb = b["time"].to_numpy(dtype=float)
    for c in ("x", "y", "z"):
        out[c] = a[c].to_numpy(dtype=float) + np.interp(a["time"].to_numpy(dtype=float), tb, b[c].to_numpy(dtype=float))
    return out


def _optional_series(path: Path, cols: list[str], t0_ns: int) -> Series | None:
    if not path.is_file():
        return None
    df = _read_sensor(path)
    if not set(cols) <= set(df.columns):
        return None
    t = (df["time"].to_numpy(dtype=np.int64) - t0_ns) / 1e9
    return Series(t=t, values=df[cols].to_numpy(dtype=float), columns=cols)


def _read_annotations(path: Path, t0_ns: int) -> list[Annotation]:
    if not path.is_file():
        return []
    df = pd.read_csv(path)
    if "time" not in df.columns or "text" not in df.columns:
        return []
    return [
        Annotation(t=(int(r["time"]) - t0_ns) / 1e9, text=str(r["text"]).strip())
        for _, r in df.dropna(subset=["time"]).iterrows()
    ]


def _read_metadata(path: Path) -> dict:
    if not path.is_file():
        return {}
    df = pd.read_csv(path)
    if df.empty:
        return {}
    return {str(k): (v.item() if hasattr(v, "item") else v) for k, v in df.iloc[0].items()}


def _median_rate(t: np.ndarray) -> float:
    return float(1.0 / np.median(np.diff(t)))

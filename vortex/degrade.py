"""Seeded IMU degradation in the shape the Track 3 slides describe.

Timeline (seconds from the first row):
  [0, healthy_s)              untouched: the healthy opening the estimator calibrates on
  [healthy_s, failure_at)     white noise whose std rises linearly from *_noise_start to *_noise_end,
                              plus bias drift (random walk and/or linear rate),
                              plus `dropout_count` windows of `dropout_s` (rows NaN or missing)
  [failure_at, +blind_s)      total IMU failure (rows present: NaN, zero or stuck values)
  after failure_at + blind_s  cut (truncate_after_blind)

The organisers' own script and levels are NOT known (open question Q2). Every default here is a
placeholder chosen to be clearly worse than EuRoC's sensor; for scale, EuRoC's imu0/sensor.yaml lists
(as recalled, check against the downloaded file) gyro noise density 1.7e-4 rad/s/sqrt(Hz), gyro random
walk 1.9e-5 rad/s^2/sqrt(Hz), accel noise density 2.0e-3 m/s^2/sqrt(Hz), accel random walk
3.0e-3 m/s^3/sqrt(Hz). At 200 Hz the native per-sample noise is about 2.4e-3 rad/s and 0.028 m/s^2.

Same input + same config + same seed -> byte-identical output (numpy's default_rng; deterministic for
a given numpy version). The events JSON records every window, so score.py can split errors by phase.

CLI: python -m vortex.degrade IN (csv or sequence dir) OUT_DIR --seed N [--any-config-field VALUE]
     writes OUT_DIR/mav0/imu0/data.csv and OUT_DIR/degrade.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import numpy as np

from .data.euroc import RawImu, read_imu_csv, write_imu_csv

DROPOUT_MODES = ("nan", "missing")
FAILURE_MODES = ("nan", "zero", "stuck")


@dataclass
class DegradeConfig:
    healthy_s: float = 10.0            # untouched opening seconds (placeholder)
    gyro_noise_start: float = 0.0      # added white-noise std at healthy_s, rad/s
    gyro_noise_end: float = 0.05       # ... at failure_at, rad/s (~20x EuRoC native)
    accel_noise_start: float = 0.0     # m/s^2
    accel_noise_end: float = 0.5       # m/s^2 (~18x EuRoC native)
    gyro_bias_rw: float = 2e-4         # random walk, rad/s per sqrt(s)
    accel_bias_rw: float = 1e-2        # m/s^2 per sqrt(s)
    gyro_bias_rate: float = 0.0        # linear drift, rad/s per s
    accel_bias_rate: float = 0.0       # m/s^2 per s
    dropout_count: int = 3
    dropout_s: float = 2.0
    dropout_mode: str = "nan"          # "nan": rows kept with NaN values; "missing": rows removed
    min_gap_s: float = 5.0             # between dropouts, and from the last dropout to the failure
    failure: bool = True
    failure_at_s: float = -1.0         # < 0: failure_at_frac of the input duration
    failure_at_frac: float = 0.85
    failure_mode: str = "nan"
    blind_s: float = 5.0
    truncate_after_blind: bool = True
    duplicate_rows: int = 0            # rows repeated verbatim (robustness tests)
    swap_rows: int = 0                 # adjacent pairs swapped (out-of-order timestamps)


def degrade(clean: RawImu, cfg: DegradeConfig, seed: int) -> tuple[RawImu, dict]:
    if cfg.dropout_mode not in DROPOUT_MODES or cfg.failure_mode not in FAILURE_MODES:
        raise ValueError("bad dropout_mode or failure_mode")
    if len(clean) < 2 or not np.all(clean.valid) or not np.all(np.diff(clean.t_ns) > 0):
        raise ValueError("degrade needs a clean input: all rows valid, timestamps strictly increasing")
    rng = np.random.default_rng(seed)
    t0_ns = int(clean.t_ns[0])
    t = (clean.t_ns - t0_ns) / 1e9
    n = len(t)
    duration = float(t[-1])

    if cfg.failure:
        fail_at = cfg.failure_at_s if cfg.failure_at_s >= 0 else round(cfg.failure_at_frac * duration, 3)
        end = fail_at + cfg.blind_s if cfg.truncate_after_blind else duration
    else:
        fail_at = end = duration
    if fail_at <= cfg.healthy_s or fail_at > duration:
        raise ValueError("failure time %.3f s outside (healthy_s, duration]" % fail_at)

    # rising noise and bias drift, both zero in the healthy opening
    span = max(fail_at - cfg.healthy_s, 1e-9)
    frac = np.clip((t - cfg.healthy_s) / span, 0.0, 1.0)
    after = t >= cfg.healthy_s
    std = np.empty((n, 6))
    std[:, :3] = (cfg.gyro_noise_start + (cfg.gyro_noise_end - cfg.gyro_noise_start) * frac)[:, None]
    std[:, 3:] = (cfg.accel_noise_start + (cfg.accel_noise_end - cfg.accel_noise_start) * frac)[:, None]
    std[~after] = 0.0
    noise = rng.standard_normal((n, 6)) * std

    dt = np.diff(t, prepend=t[0])
    rw_sigma = np.array([cfg.gyro_bias_rw] * 3 + [cfg.accel_bias_rw] * 3)
    steps = rng.standard_normal((n, 6)) * np.sqrt(dt)[:, None] * rw_sigma
    steps[~after] = 0.0
    rate = np.array([cfg.gyro_bias_rate] * 3 + [cfg.accel_bias_rate] * 3)
    bias = np.cumsum(steps, axis=0) + np.clip(t - cfg.healthy_s, 0.0, None)[:, None] * rate

    v = np.hstack([clean.gyro, clean.accel]) + noise + bias

    # dropout windows: inside [healthy_s, fail_at - min_gap], at least min_gap apart
    drops = _place_dropouts(rng, cfg, fail_at)
    in_drop = np.zeros(n, dtype=bool)
    for s, e in drops:
        in_drop |= (t >= s) & (t < e)

    # failure
    failed = t >= fail_at if cfg.failure else np.zeros(n, dtype=bool)
    if failed.any():
        if cfg.failure_mode == "nan":
            v[failed] = np.nan
        elif cfg.failure_mode == "zero":
            v[failed] = 0.0
        else:  # stuck at the last value read before the failure
            v[failed] = v[np.argmax(failed) - 1]

    keep = t <= end + 1e-12
    if cfg.dropout_mode == "nan":
        v[in_drop] = np.nan
    else:
        keep &= ~in_drop
    rows_missing = int(np.sum(in_drop & (t <= end + 1e-12))) if cfg.dropout_mode == "missing" else 0

    idx = np.flatnonzero(keep)
    t_text = [clean.t_text[i] for i in idx]
    t_ns = clean.t_ns[idx].copy()
    v = v[idx]

    # robustness extras, applied to the final row order
    order, dup_at, swap_at = _shuffle_extras(rng, cfg, (t[idx] >= cfg.healthy_s) & (t[idx] < fail_at)
                                             & ~in_drop[idx])
    t_text = [t_text[i] for i in order]
    t_ns = t_ns[order]
    v = v[order]

    out = RawImu(t_text=t_text, t_ns=t_ns, gyro=v[:, :3].copy(), accel=v[:, 3:].copy(), header=clean.header)
    ns = lambda s: t0_ns + int(round(s * 1e9))  # noqa: E731
    events = {
        "seed": int(seed),
        "config": asdict(cfg),
        "t0_ns": t0_ns,
        "rows_in": int(n),
        "rows_out": len(out),
        "rows_dropped_missing": rows_missing,
        "healthy_end_s": float(cfg.healthy_s),
        "dropouts_s": [[float(s), float(e)] for s, e in drops],
        "dropouts_ns": [[ns(s), ns(e)] for s, e in drops],
        "failure_at_s": float(fail_at) if cfg.failure else None,
        "failure_at_ns": ns(fail_at) if cfg.failure else None,
        "end_s": float(min(end, duration)),
        "blind_s": float(cfg.blind_s) if cfg.failure else 0.0,
        "duplicated_rows": dup_at,
        "swapped_rows": swap_at,
        "note": "placeholder levels; the organisers' degradation script is unknown (Q2)",
    }
    return out, events


def _place_dropouts(rng, cfg: DegradeConfig, fail_at: float) -> list:
    k, d, gap = cfg.dropout_count, cfg.dropout_s, cfg.min_gap_s
    if k == 0:
        return []
    lo, hi = cfg.healthy_s, fail_at - gap - d   # latest allowed start
    if hi - lo < (k - 1) * (d + gap):
        raise ValueError("cannot fit %d dropouts of %.1f s between %.1f s and %.1f s" % (k, d, lo, fail_at))
    for _ in range(10000):
        starts = np.sort(rng.uniform(lo, hi, k))
        if k == 1 or np.all(np.diff(starts) >= d + gap):
            return [(round(float(s), 3), round(float(s), 3) + d) for s in starts]
    raise ValueError("could not place dropouts; loosen min_gap_s or dropout_count")


def _shuffle_extras(rng, cfg: DegradeConfig, eligible: np.ndarray):
    m = len(eligible)
    order = list(range(m))
    want = cfg.duplicate_rows + cfg.swap_rows
    if want == 0:
        return np.array(order), [], []
    cand = np.flatnonzero(eligible[:-1] & eligible[1:])
    for _ in range(1000):
        pick = np.sort(rng.choice(cand, size=want, replace=False))
        if want == 1 or np.all(np.diff(pick) >= 3):
            break
    else:
        raise ValueError("could not place duplicate/swap rows")
    is_dup = np.zeros(want, dtype=bool)
    is_dup[rng.choice(want, size=cfg.duplicate_rows, replace=False)] = True
    out, dups, swaps = [], [], []
    i = 0
    picks = dict(zip(pick.tolist(), is_dup.tolist()))
    while i < m:
        if i in picks and picks[i]:
            out += [i, i]
            dups.append(len(out) - 1)
            i += 1
        elif i in picks:
            out += [i + 1, i]
            swaps.append(len(out) - 2)
            i += 2
        else:
            out.append(i)
            i += 1
    return np.array(out), dups, swaps


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m vortex.degrade", description=__doc__.split("\n")[0])
    ap.add_argument("input", help="clean imu0/data.csv or a sequence folder")
    ap.add_argument("out_dir")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--nan-text", default="nan", help="how NaN is written: 'nan' (numpy) or '' (pandas)")
    for f in fields(DegradeConfig):
        flag = "--" + f.name.replace("_", "-")
        if f.type in ("bool", bool):
            ap.add_argument(flag, type=lambda s: s.lower() in ("1", "true", "yes"), default=f.default)
        else:
            ap.add_argument(flag, type=type(f.default), default=f.default)
    a = ap.parse_args(argv)
    cfg = DegradeConfig(**{f.name: getattr(a, f.name) for f in fields(DegradeConfig)})
    out, events = degrade(read_imu_csv(a.input), cfg, a.seed)
    out_dir = Path(a.out_dir)
    write_imu_csv(out, out_dir / "mav0" / "imu0" / "data.csv", nan_text=a.nan_text)
    events["input"] = str(a.input)
    events["nan_text"] = a.nan_text
    with open(out_dir / "degrade.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(events, f, indent=1, sort_keys=True)
        f.write("\n")
    print("wrote %s (%d rows) and degrade.json" % (out_dir / "mav0" / "imu0" / "data.csv", len(out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

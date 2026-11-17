"""Inspect extracted TUM-VI sequences under data/tumvi/ (rows, duration, IMU rate, gaps, GT coverage).

Usage:
  python tools/tumvi_inspect.py [--root data/tumvi] [--tar data/tumvi/dataset-room1_512_16.tar] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tarfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vortex.data import euroc  # noqa: E402


def inspect_sequence(seq_dir: str | Path) -> dict:
    """Compute IMU and mocap ground-truth statistics for one extracted TUM-VI sequence folder."""
    seq_dir = Path(seq_dir)
    raw = euroc.read_imu_csv(seq_dir)
    gt = euroc.load_ground_truth(seq_dir)
    n_imu = len(raw)
    n_valid = int(np.sum(raw.valid))
    t_ns = raw.t_ns
    t0_ns = int(t_ns[0])
    duration_s = float((t_ns[-1] - t0_ns) / 1e9) if n_imu >= 2 else 0.0

    dt_ns = np.diff(t_ns) if n_imu >= 2 else np.array([], dtype=np.int64)
    med_dt_ns = float(np.median(dt_ns)) if len(dt_ns) else 0.0
    med_dt_ms = med_dt_ns / 1e6
    rate_hz = (1e9 / med_dt_ns) if med_dt_ns > 0 else 0.0
    gap_thresh_ns = 1.5 * med_dt_ns if med_dt_ns > 0 else 0.0
    gap_mask = dt_ns > gap_thresh_ns if len(dt_ns) else np.zeros(0, dtype=bool)
    imu_gaps = int(np.sum(gap_mask))
    imu_missing_rows = (
        int(sum(max(1, int(round(float(d) / med_dt_ns)) - 1) for d in dt_ns[gap_mask]))
        if imu_gaps and med_dt_ns > 0 else 0
    )
    imu_nonmono = int(np.sum(dt_ns <= 0)) if len(dt_ns) else 0

    t0_s = t0_ns / 1e9
    gt_start_s = float(gt.t[0] - t0_s) if len(gt) else float("nan")
    gt_end_s = float(gt.t[-1] - t0_s) if len(gt) else float("nan")
    gt_span_s = float(gt.t[-1] - gt.t[0]) if len(gt) >= 2 else 0.0
    gt_dt = np.diff(gt.t) if len(gt) >= 2 else np.array([], dtype=float)
    gt_med_dt_s = float(np.median(gt_dt)) if len(gt_dt) else 0.0
    gt_hz = (1.0 / gt_med_dt_s) if gt_med_dt_s > 0 else 0.0
    gt_gap_mask = gt_dt > 0.05 if len(gt_dt) else np.zeros(0, dtype=bool)
    gt_gaps = int(np.sum(gt_gap_mask))
    gt_max_gap_s = float(np.max(gt_dt)) if len(gt_dt) else 0.0

    return {
        "sequence": seq_dir.name,
        "imu_rows": n_imu,
        "imu_valid_rows": n_valid,
        "duration_s": duration_s,
        "imu_rate_hz": rate_hz,
        "imu_med_dt_ms": med_dt_ms,
        "imu_min_dt_ms": float(np.min(dt_ns) / 1e6) if len(dt_ns) else 0.0,
        "imu_max_dt_ms": float(np.max(dt_ns) / 1e6) if len(dt_ns) else 0.0,
        "imu_gaps": imu_gaps,
        "imu_missing_rows": imu_missing_rows,
        "imu_nonmono": imu_nonmono,
        "gt_rows": len(gt),
        "gt_start_s": gt_start_s,
        "gt_end_s": gt_end_s,
        "gt_span_s": gt_span_s,
        "gt_coverage_pct": (100.0 * gt_span_s / duration_s) if duration_s > 0 else 0.0,
        "gt_rate_hz": gt_hz,
        "gt_gaps_gt50ms": gt_gaps,
        "gt_max_dt_s": gt_max_gap_s,
    }


def inspect_tar_sensors(tar_path: str | Path) -> dict[str, str]:
    """Read calibration YAML and verify mocap0 vs gt_imu alignment in-memory from a TUM-VI tar."""
    out = {}
    gt_rows = {}
    with tarfile.open(tar_path, "r") as tf:
        for m in tf.getmembers():
            if not m.isfile():
                continue
            name = m.name.lstrip("./")
            if name.endswith(("imu_config.yaml", "sensor.yaml")):
                f = tf.extractfile(m)
                if f is not None:
                    out[name] = f.read().decode("utf-8", errors="replace")
            elif name.endswith(("dso/gt_imu.csv", "mav0/mocap0/data.csv")):
                f = tf.extractfile(m)
                if f is not None:
                    gt_rows[name] = f.read().decode("utf-8", errors="replace").splitlines()[1:]
    if len(gt_rows) == 2:
        k = sorted(gt_rows)
        out["gt_imu_vs_mocap0_match"] = "%s == %s (%d rows): %s" % (
            k[0], k[1], len(gt_rows[k[0]]), gt_rows[k[0]] == gt_rows[k[1]])
    return out


def format_table(rows: list[dict]) -> str:
    """Format TUM-VI room inspection stats as a markdown table matching Step A's V1 table."""
    lines = [
        "| Sequence | IMU rows | Length | IMU rate | Time gaps | Ground-truth rows | Ground truth covers |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        rate = "%.1f Hz (dt %.3f ms)" % (r["imu_rate_hz"], r["imu_med_dt_ms"])
        if r["imu_gaps"] == 0 and r["imu_nonmono"] == 0 and r["imu_valid_rows"] == r["imu_rows"]:
            gaps = "none (max dt %.2f ms)" % r["imu_max_dt_ms"]
        else:
            parts = []
            if r["imu_gaps"]:
                parts.append("%d gaps (%d missing rows, max %.1f ms)" % (
                    r["imu_gaps"], r["imu_missing_rows"], r["imu_max_dt_ms"]))
            if r["imu_nonmono"]:
                parts.append("%d non-increasing" % r["imu_nonmono"])
            if r["imu_valid_rows"] != r["imu_rows"]:
                parts.append("%d invalid" % (r["imu_rows"] - r["imu_valid_rows"]))
            gaps = "; ".join(parts)
        gt_gap_note = ("no gaps >50 ms" if r["gt_gaps_gt50ms"] == 0
                       else "%d gaps >50 ms, max %.2f s" % (r["gt_gaps_gt50ms"], r["gt_max_dt_s"]))
        gt_cov = "%.2f..%.2f s (%.1f%%, %.0f Hz, %s)" % (
            r["gt_start_s"], r["gt_end_s"], r["gt_coverage_pct"], r["gt_rate_hz"], gt_gap_note)
        lines.append("| %s | %s | %.1f s | %s | %s | %s | %s |" % (
            r["sequence"], f"{r['imu_rows']:,}", r["duration_s"], rate, gaps, f"{r['gt_rows']:,}", gt_cov))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(ROOT / "data" / "tumvi"), help="TUM-VI root folder")
    ap.add_argument("--tar", help="Optional tar archive to print sensor.yaml files from")
    ap.add_argument("--json", help="Optional path to write JSON summary")
    a = ap.parse_args(argv)

    root = Path(a.root)
    seq_dirs = sorted(p for p in root.iterdir() if p.is_dir() and (p / "mav0" / "imu0" / "data.csv").is_file())
    rows = [inspect_sequence(p) for p in seq_dirs]
    print(format_table(rows))

    if a.tar:
        sensors = inspect_tar_sensors(a.tar)
        for name, text in sorted(sensors.items()):
            print("\n--- %s ---\n%s" % (name, text.strip()))

    if a.json:
        out_path = Path(a.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


"""Task G6 diagnostic probe: why stillness calibration never fires on TUM-VI (clean rooms 1 and 2 only).

Read-only on the estimator: imports pathfinder constants/functions and inspects ONLY clean
dataset-room1_512_16 and dataset-room2_512_16. Refuses V2_* and rooms 3..6 by default.

Usage:
  python tools/tumvi_still_probe.py [--root data/tumvi] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pathfinder as pf  # noqa: E402
from vortex.data import euroc  # noqa: E402

ALLOWED_DEFAULT = ("dataset-room1_512_16", "dataset-room2_512_16")
FORBIDDEN_PREFIXES = ("V2_", "dataset-room3", "dataset-room4", "dataset-room5", "dataset-room6")


def rule_specification() -> dict:
    """Return the exact still-detection rules and thresholds quoted from pathfinder.py."""
    return {
        "functions": {
            "pass1_calibrate": "pathfinder._calibrate(src) -> _best_run(n, s, still) -> _still_denoised(src, t0, n, s, ss)",
            "fallback_init": "pathfinder._init_window(src) -> pathfinder._initialise(win)",
            "online_zupt": "pathfinder._bin_still(n, s, ss) + pathfinder._bins_steady(na, sa, nb_, sb)",
        },
        "constants": {
            "CAL_HORIZON_S": pf.CAL_HORIZON_S,
            "BLOCK_S": pf.BLOCK_S,
            "BLOCK_MIN_ROWS": pf.BLOCK_MIN_ROWS,
            "MIN_STILL_S": pf.MIN_STILL_S,
            "TRIM_S": pf.TRIM_S,
            "PRE_MAX_ROWS": pf.PRE_MAX_ROWS,
            "CAL_NOISE_ON": pf.CAL_NOISE_ON,
            "INIT_S": pf.INIT_S,
            "INIT_MAX_ROWS": pf.INIT_MAX_ROWS,
            "STILL_GYRO_STD": pf.STILL_GYRO_STD,
            "STILL_ACC_STD": pf.STILL_ACC_STD,
            "STUCK_STD": pf.STUCK_STD,
            "ACC_NORM_MIN": pf.ACC_NORM_MIN,
            "ACC_NORM_MAX": pf.ACC_NORM_MAX,
            "STEADY_GYRO": pf.STEADY_GYRO,
            "STEADY_ACC": pf.STEADY_ACC,
            "BG_MAX": pf.BG_MAX,
            "BGCAP_ON": pf.BGCAP_ON,
            "G_DEFAULT": pf.G_DEFAULT,
            "MAX_DT": pf.MAX_DT,
        },
    }


def analyze_windows_1s(raw: euroc.RawImu, horizon_s: float = 60.0) -> list[dict]:
    """Compute per-1 s window statistics over [0, horizon_s) from t0."""
    t0_ns = int(raw.t_ns[0])
    t_rel = (raw.t_ns - t0_ns) / 1e9
    n_win = int(round(horizon_s))
    windows = []

    for k in range(n_win):
        m = (t_rel >= k) & (t_rel < k + 1.0) & raw.valid
        cnt = int(np.sum(m))
        if cnt < 2:
            continue
        g = raw.gyro[m]
        a = raw.accel[m]

        # Population std (ddof=0) matching pathfinder.py's var = ss/n - m*m
        g_std = np.std(g, axis=0, ddof=0)
        a_std = np.std(a, axis=0, ddof=0)
        g_mean = np.mean(g, axis=0)
        a_mean = np.mean(a, axis=0)

        g_std_max = float(np.max(g_std))
        a_std_max = float(np.max(a_std))
        g_mean_norm = float(np.linalg.norm(g_mean))
        a_mean_norm = float(np.linalg.norm(a_mean))

        a_row_norms = np.linalg.norm(a, axis=1)
        a_norm_mean = float(np.mean(a_row_norms))
        a_norm_std = float(np.std(a_row_norms, ddof=0))
        a_norm_minus_g = a_norm_mean - pf.G_DEFAULT
        a_mean_norm_minus_g = a_mean_norm - pf.G_DEFAULT

        pass_gyro_std = g_std_max < pf.STILL_GYRO_STD
        pass_acc_std = a_std_max < pf.STILL_ACC_STD
        pass_bg_cap = (not pf.BGCAP_ON) or (g_mean_norm <= pf.BG_MAX)
        pass_acc_norm = pf.ACC_NORM_MIN <= a_mean_norm <= pf.ACC_NORM_MAX
        pass_not_stuck = max(g_std_max, a_std_max) > pf.STUCK_STD
        passes_all = bool(pass_gyro_std and pass_acc_std and pass_bg_cap and pass_acc_norm and pass_not_stuck)

        windows.append({
            "window_idx": k,
            "t_start_s": float(k),
            "t_end_s": float(k + 1),
            "rows": cnt,
            "gyro_std_xyz": [float(x) for x in g_std],
            "gyro_std_max": g_std_max,
            "gyro_mean_xyz": [float(x) for x in g_mean],
            "gyro_mean_norm": g_mean_norm,
            "acc_std_xyz": [float(x) for x in a_std],
            "acc_std_max": a_std_max,
            "acc_mean_xyz": [float(x) for x in a_mean],
            "acc_mean_norm": a_mean_norm,
            "acc_norm_mean": a_norm_mean,
            "acc_norm_minus_g": a_norm_minus_g,
            "acc_mean_norm_minus_g": a_mean_norm_minus_g,
            "acc_norm_std": a_norm_std,
            "gyro_std_factor": g_std_max / pf.STILL_GYRO_STD,
            "acc_std_factor": a_std_max / pf.STILL_ACC_STD,
            "acc_norm_std_factor": a_norm_std / pf.STILL_ACC_STD,
            "bg_norm_factor": g_mean_norm / pf.BG_MAX,
            "passes_1s_rule": passes_all,
            "pass_flags": {
                "gyro_std": bool(pass_gyro_std),
                "acc_std": bool(pass_acc_std),
                "bg_cap": bool(pass_bg_cap),
                "acc_norm": bool(pass_acc_norm),
            },
        })
    return windows


def analyze_bins_025s(imu_path: Path, raw: euroc.RawImu) -> dict:
    """Exact replica of pathfinder._calibrate's 240 x 0.25 s bin analysis (strict and denoised)."""
    nb = int(pf.CAL_HORIZON_S / pf.BLOCK_S)
    bns = int(pf.BLOCK_S * 1e9)
    n = [0] * nb
    s = [0.0] * (6 * nb)
    ss = [0.0] * (6 * nb)
    t0 = int(raw.t_ns[0])
    t_end = t0 + nb * bns

    for t_ns, g_row, a_row, val in zip(raw.t_ns, raw.gyro, raw.accel, raw.valid):
        if not val:
            continue
        t = int(t_ns)
        if t >= t_end:
            break
        if t < t0:
            continue
        j = (t - t0) // bns
        n[j] += 1
        o = 6 * j
        v = (float(g_row[0]), float(g_row[1]), float(g_row[2]),
             float(a_row[0]), float(a_row[1]), float(a_row[2]))
        for i in range(6):
            x = v[i]
            s[o + i] += x
            ss[o + i] += x * x

    strict_still = [False] * nb
    bin_details = []
    for j in range(nb):
        if n[j] < pf.BLOCK_MIN_ROWS:
            bin_details.append({"bin": j, "rows": n[j], "strict_still": False})
            continue
        o = 6 * j
        sd = [0.0] * 6
        means = [0.0] * 6
        for i in range(6):
            m = s[o + i] / n[j]
            means[i] = m
            var = ss[o + i] / n[j] - m * m
            sd[i] = math.sqrt(var) if var > 0.0 else 0.0
        g_sd_max = max(sd[0], sd[1], sd[2])
        a_sd_max = max(sd[3], sd[4], sd[5])
        bg_norm = math.sqrt(means[0] ** 2 + means[1] ** 2 + means[2] ** 2)
        fn = math.sqrt(means[3] ** 2 + means[4] ** 2 + means[5] ** 2)
        ok_g = g_sd_max < pf.STILL_GYRO_STD
        ok_a = a_sd_max < pf.STILL_ACC_STD
        ok_stuck = max(sd) > pf.STUCK_STD
        ok_bg = (not pf.BGCAP_ON) or (bg_norm <= pf.BG_MAX)
        ok_fn = pf.ACC_NORM_MIN <= fn <= pf.ACC_NORM_MAX
        is_st = bool(ok_g and ok_a and ok_stuck and ok_bg and ok_fn)
        strict_still[j] = is_st
        bin_details.append({
            "bin": j,
            "t_start_s": j * pf.BLOCK_S,
            "t_end_s": (j + 1) * pf.BLOCK_S,
            "rows": n[j],
            "gyro_std_max": g_sd_max,
            "acc_std_max": a_sd_max,
            "bg_norm": bg_norm,
            "acc_mean_norm": fn,
            "strict_still": is_st,
            "ok_gyro_std": ok_g,
            "ok_acc_std": ok_a,
            "ok_bg": ok_bg,
            "ok_acc_norm": ok_fn,
        })

    strict_best_j, strict_best_len = pf._best_run(n, s, strict_still)
    denoised_still, w = pf._still_denoised(str(imu_path), t0, n, s, ss)
    den_best_j, den_best_len = pf._best_run(n, s, denoised_still, w)

    # Best 4-consecutive-bin (1.0 s) block in [0, 60] s by combined bottleneck ratio
    min_bins = int(round(pf.MIN_STILL_S / pf.BLOCK_S))
    best_4bin = None
    for j0 in range(0, nb - min_bins + 1):
        slice_bins = bin_details[j0:j0 + min_bins]
        if any(b.get("rows", 0) < pf.BLOCK_MIN_ROWS for b in slice_bins):
            continue
        worst_g = max(b["gyro_std_max"] for b in slice_bins)
        worst_a = max(b["acc_std_max"] for b in slice_bins)
        worst_bg = max(b["bg_norm"] for b in slice_bins)
        # Pairwise steady diffs across the 4 bins
        max_dg = 0.0
        max_da = 0.0
        for jj in range(j0 + 1, j0 + min_bins):
            oa, ob = 6 * (jj - 1), 6 * jj
            for i in range(3):
                max_dg = max(max_dg, abs(s[oa + i] / n[jj - 1] - s[ob + i] / n[jj]))
            for i in range(3, 6):
                max_da = max(max_da, abs(s[oa + i] / n[jj - 1] - s[ob + i] / n[jj]))
        bottleneck = max(
            worst_g / pf.STILL_GYRO_STD,
            worst_a / pf.STILL_ACC_STD,
            max_dg / pf.STEADY_GYRO,
            max_da / pf.STEADY_ACC,
        )
        cand = {
            "j0": j0,
            "t_start_s": j0 * pf.BLOCK_S,
            "t_end_s": (j0 + min_bins) * pf.BLOCK_S,
            "worst_bin_gyro_std_max": worst_g,
            "worst_bin_acc_std_max": worst_a,
            "worst_bin_bg_norm": worst_bg,
            "max_pair_d_gyro": max_dg,
            "max_pair_d_acc": max_da,
            "factor_gyro_std": worst_g / pf.STILL_GYRO_STD,
            "factor_acc_std": worst_a / pf.STILL_ACC_STD,
            "factor_steady_gyro": max_dg / pf.STEADY_GYRO,
            "factor_steady_acc": max_da / pf.STEADY_ACC,
            "factor_bg_max": worst_bg / pf.BG_MAX,
            "bottleneck_factor": bottleneck,
        }
        if best_4bin is None or cand["bottleneck_factor"] < best_4bin["bottleneck_factor"]:
            best_4bin = cand

    return {
        "total_bins_in_60s": nb,
        "strict_still_bins_count": int(sum(strict_still)),
        "strict_still_bin_indices": [j for j, flag in enumerate(strict_still) if flag],
        "strict_best_run_bins": int(strict_best_len),
        "strict_best_run_s": float(strict_best_len * pf.BLOCK_S),
        "strict_best_run_start_s": float(strict_best_j * pf.BLOCK_S),
        "denoised_still_bins_count": int(sum(denoised_still)),
        "denoised_still_bin_indices": [j for j, flag in enumerate(denoised_still) if flag],
        "denoised_best_run_bins": int(den_best_len),
        "denoised_best_run_s": float(den_best_len * pf.BLOCK_S),
        "denoised_best_run_start_s": float(den_best_j * pf.BLOCK_S),
        "gate_pass_counts_240": {
            "ok_gyro_std": sum(1 for b in bin_details if b.get("ok_gyro_std")),
            "ok_acc_std": sum(1 for b in bin_details if b.get("ok_acc_std")),
            "ok_bg": sum(1 for b in bin_details if b.get("ok_bg")),
            "ok_acc_norm": sum(1 for b in bin_details if b.get("ok_acc_norm")),
        },
        "best_4bin_1s_block": best_4bin,
    }


def check_units_and_conventions(imu_path: Path, raw: euroc.RawImu) -> dict:
    """Verify units and conventions assumed by pathfinder.py against actual TUM-VI data."""
    fe_lay = pf._fe_detect(str(imu_path))
    dt_ns = np.diff(raw.t_ns)
    med_dt_s = float(np.median(dt_ns) / 1e9)
    rate_hz = 1.0 / med_dt_s if med_dt_s > 0 else 0.0
    a_norms = np.linalg.norm(raw.accel, axis=1)
    g_norms = np.linalg.norm(raw.gyro, axis=1)
    first_1s = (raw.t_ns - raw.t_ns[0]) < 1_000_000_000
    a0_mean = np.mean(raw.accel[first_1s], axis=0)
    g0_mean = np.mean(raw.gyro[first_1s], axis=0)

    return {
        "header": raw.header,
        "frontend_detect": fe_lay,
        "timestamp_unit": fe_lay["ts_unit"],
        "median_dt_ms": med_dt_s * 1e3,
        "sample_rate_hz": rate_hz,
        "rows_per_025s_bin": rate_hz * pf.BLOCK_S,
        "accel_unit_detected": fe_lay["accel_unit"],
        "accel_norm_median_m_s2": float(np.median(a_norms)),
        "accel_norm_p05_p95_m_s2": [float(np.percentile(a_norms, 5)), float(np.percentile(a_norms, 95))],
        "gyro_norm_median_rad_s": float(np.median(g_norms)),
        "gyro_norm_p95_rad_s": float(np.percentile(g_norms, 95)),
        "gyro_suspect_deg_s": bool(fe_lay["gyro_suspect"]),
        "opening_1s_accel_mean_xyz": [float(x) for x in a0_mean],
        "opening_1s_gyro_mean_xyz": [float(x) for x in g0_mean],
        "gravity_sign_z_positive": bool(a0_mean[2] > 8.0),
    }


def inspect_first_seconds_with_mocap(seq_dir: Path, raw: euroc.RawImu, seconds: int = 5) -> list[dict]:
    """Inspect opening seconds (0..seconds) in 0.5 s slices, including mocap GT speed for diagnosis."""
    gt = euroc.load_ground_truth(seq_dir)
    t0_s = raw.t_ns[0] / 1e9
    t_imu = raw.t_ns / 1e9 - t0_s
    t_gt = gt.t - t0_s
    dt_gt = np.diff(t_gt)
    dp_gt = np.diff(gt.p, axis=0)
    valid_dt = dt_gt > 1e-4
    v_gt = np.zeros(len(dt_gt))
    v_gt[valid_dt] = np.linalg.norm(dp_gt[valid_dt], axis=1) / dt_gt[valid_dt]
    t_v = t_gt[:-1]

    slices = []
    for k in range(seconds * 2):
        ta, tb = 0.5 * k, 0.5 * (k + 1)
        mi = (t_imu >= ta) & (t_imu < tb)
        mv = (t_v >= ta) & (t_v < tb) & valid_dt
        g_slice = raw.gyro[mi]
        a_slice = raw.accel[mi]
        g_std_max = float(np.max(np.std(g_slice, axis=0, ddof=0))) if len(g_slice) else 0.0
        a_std_max = float(np.max(np.std(a_slice, axis=0, ddof=0))) if len(a_slice) else 0.0
        g_norm_mean = float(np.mean(np.linalg.norm(g_slice, axis=1))) if len(g_slice) else 0.0
        gt_speed_mean = float(np.mean(v_gt[mv])) if np.any(mv) else float("nan")
        gt_speed_max = float(np.max(v_gt[mv])) if np.any(mv) else float("nan")
        slices.append({
            "t_window_s": [ta, tb],
            "gyro_std_max_rad_s": g_std_max,
            "gyro_rate_mean_rad_s": g_norm_mean,
            "acc_std_max_m_s2": a_std_max,
            "mocap_speed_mean_m_s": gt_speed_mean,
            "mocap_speed_max_m_s": gt_speed_max,
        })
    return slices


def probe_sequence(seq_dir: str | Path) -> dict:
    """Run the complete G6 stillness probe on one clean TUM-VI sequence folder."""
    seq_dir = Path(seq_dir)
    imu_path = euroc.imu_path(seq_dir)
    raw = euroc.read_imu_csv(imu_path)
    win_1s = analyze_windows_1s(raw, horizon_s=pf.CAL_HORIZON_S)
    bins_025 = analyze_bins_025s(imu_path, raw)
    units = check_units_and_conventions(imu_path, raw)

    has_gt = (seq_dir / "mav0" / "mocap0" / "data.csv").is_file() or (
        seq_dir / "mav0" / "state_groundtruth_estimate0" / "data.csv"
    ).is_file()
    opening = inspect_first_seconds_with_mocap(seq_dir, raw, seconds=5) if has_gt else []

    # Best 1 s window by max(gyro_std_factor, acc_std_factor)
    best_by_combined = min(win_1s, key=lambda w: max(w["gyro_std_factor"], w["acc_std_factor"]))
    best_by_gyro = min(win_1s, key=lambda w: w["gyro_std_max"])
    best_by_acc = min(win_1s, key=lambda w: w["acc_std_max"])

    return {
        "sequence": seq_dir.name,
        "units_and_conventions": units,
        "opening_5s_slices": opening,
        "bins_025s_summary": bins_025,
        "windows_1s_passing_count": sum(1 for w in win_1s if w["passes_1s_rule"]),
        "best_1s_window_combined": best_by_combined,
        "best_1s_window_by_gyro_std": best_by_gyro,
        "best_1s_window_by_acc_std": best_by_acc,
        "window_0_to_1s": win_1s[0] if win_1s else None,
        "windows_1s": win_1s,
    }


def format_report(probes: list[dict]) -> str:
    """Format a Markdown report with the summary tables andper-1s tables for rooms 1 and 2."""
    spec = rule_specification()["constants"]
    L = [
        "# G6 Probe: Why Stillness Calibration Never Fires on TUM-VI (`room1`, `room2`)",
        "",
        "## 1. Exact Still-Detection Rules Quoted from `pathfinder.py`",
        "",
        "- **Pass 1 Calibration (`_calibrate` -> `_best_run` -> `_still_denoised`):**",
        f"  - Search span: `CAL_HORIZON_S = {spec['CAL_HORIZON_S']} s` from `t0`, split into `240` non-overlapping bins of `BLOCK_S = {spec['BLOCK_S']} s` (`BLOCK_MIN_ROWS = {spec['BLOCK_MIN_ROWS']}`).",
        f"  - Per-bin thresholds: `max(std_gx, std_gy, std_gz) < STILL_GYRO_STD = {spec['STILL_GYRO_STD']} rad/s`; "
        f"`max(std_ax, std_ay, std_az) < STILL_ACC_STD = {spec['STILL_ACC_STD']} m/s^2`; "
        f"`max(std) > STUCK_STD = {spec['STUCK_STD']}`; "
        f"`||mean_gyro|| <= BG_MAX = {spec['BG_MAX']} rad/s` (`BGCAP_ON = {spec['BGCAP_ON']}`); "
        f"`ACC_NORM_MIN = {spec['ACC_NORM_MIN']} <= ||mean_acc|| <= ACC_NORM_MAX = {spec['ACC_NORM_MAX']} m/s^2`.",
        f"  - Contiguous run (`_best_run`): adjacent still bins must satisfy `|mean_a - mean_b| < STEADY_GYRO = {spec['STEADY_GYRO']} rad/s` (gyro) and `< STEADY_ACC = {spec['STEADY_ACC']} m/s^2` (accel); total run duration `best_len * BLOCK_S >= MIN_STILL_S = {spec['MIN_STILL_S']} s` (>= 4 consecutive `0.25 s` bins).",
        f"  - Denoised retry (`_still_denoised`, `CAL_NOISE_ON = {spec['CAL_NOISE_ON']}`): subtracts per-bin 2nd-difference white-noise variance `w = sum(d2) / nd / 6` from bin variance and widens steady tolerances by `+ 3 * sqrt(w_a/n_a + w_b/n_b)`.",
        f"- **Fallback 1 s init (`_init_window` + `_initialise`):** first `INIT_S = {spec['INIT_S']} s` (`[t0, t0 + 1.0 s]`), same `STILL_GYRO_STD = 0.02`, `STILL_ACC_STD = 0.1`, `BG_MAX = 0.15` thresholds.",
        "",
        "## 2. Best 1 s Windows & 0.25 s Bin Gate Summary (`0..60 s`)",
        "",
        "| Sequence | Window | t (s) | Gyro std (x, y, z) rad/s | Max gyro std (miss x0.02) | Accel std (x, y, z) m/s^2 | Max accel std (miss x0.10) | ||a||-9.81 m/s^2 | std(||a||) m/s^2 (miss x0.10) | ||mean_g|| rad/s (vs 0.15) | Passes? |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for p in probes:
        seq = p["sequence"]
        for label, w in (
            ("Opening 1 s [0..1s]", p["window_0_to_1s"]),
            ("Best 1 s (combined)", p["best_1s_window_combined"]),
            ("Best 1 s (gyro std)", p["best_1s_window_by_gyro_std"]),
            ("Best 1 s (acc std)", p["best_1s_window_by_acc_std"]),
        ):
            if not w:
                continue
            gs = w["gyro_std_xyz"]
            acs = w["acc_std_xyz"]
            L.append(
                f"| `{seq}` | {label} | {w['t_start_s']:.0f}..{w['t_end_s']:.0f} | "
                f"({gs[0]:.4f}, {gs[1]:.4f}, {gs[2]:.4f}) | "
                f"**{w['gyro_std_max']:.4f}** ({w['gyro_std_factor']:.2f}x) | "
                f"({acs[0]:.4f}, {acs[1]:.4f}, {acs[2]:.4f}) | "
                f"**{w['acc_std_max']:.4f}** ({w['acc_std_factor']:.2f}x) | "
                f"{w['acc_norm_minus_g']:+.4f} | "
                f"{w['acc_norm_std']:.4f} ({w['acc_norm_std_factor']:.2f}x) | "
                f"{w['gyro_mean_norm']:.4f} ({w['bg_norm_factor']:.2f}x) | "
                f"{'YES' if w['passes_1s_rule'] else 'NO'} |"
            )

    L += [
        "",
        "### 0.25 s Calibration Bins (`240` bins in `0..60 s`)",
        "",
        "| Sequence | Bins passing `gyro_std < 0.02` | Bins passing `acc_std < 0.10` | Bins passing `||bg|| <= 0.15` | Bins passing `8.8 <= ||a|| <= 10.8` | Strict still bins | Longest strict run (need 1.00 s) | Denoised still bins | Longest denoised run (need 1.00 s) | Best 4-bin (1.0 s) bottleneck miss factor |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for p in probes:
        b = p["bins_025s_summary"]
        gc = b["gate_pass_counts_240"]
        b4 = b["best_4bin_1s_block"]
        b4_txt = (
            f"{b4['t_start_s']:.2f}..{b4['t_end_s']:.2f}s: "
            f"gyro_std {b4['factor_gyro_std']:.2f}x, acc_std {b4['factor_acc_std']:.2f}x, "
            f"steady_g {b4['factor_steady_gyro']:.2f}x, steady_a {b4['factor_steady_acc']:.2f}x"
            if b4 else "-"
        )
        L.append(
            f"| `{p['sequence']}` | {gc['ok_gyro_std']}/240 | {gc['ok_acc_std']}/240 | "
            f"{gc['ok_bg']}/240 | {gc['ok_acc_norm']}/240 | "
            f"**{b['strict_still_bins_count']}/240** | **{b['strict_best_run_s']:.2f} s** ({b['strict_best_run_bins']} bins) | "
            f"**{b['denoised_still_bins_count']}/240** | **{b['denoised_best_run_s']:.2f} s** ({b['denoised_best_run_bins']} bins) | "
            f"{b4_txt} |"
        )

    L += [
        "",
        "## 3. Units & Conventions Check Against `pathfinder.py` Assumptions",
        "",
        "| Sequence | Frontend order (`canonical`) | Timestamp unit (`median dt`, rate) | Rows / 0.25 s bin (need >=5) | Accel unit (median ||a||, p05..p95 m/s^2) | Opening 1 s mean accel (x, y, z) m/s^2 | Gyro unit (`gyro_suspect`, median ||w|| rad/s) | Opening 1 s mean gyro (x, y, z) rad/s | Failed assumption |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for p in probes:
        u = p["units_and_conventions"]
        p05, p95 = u["accel_norm_p05_p95_m_s2"]
        a0 = u["opening_1s_accel_mean_xyz"]
        g0 = u["opening_1s_gyro_mean_xyz"]
        fe = u["frontend_detect"]
        L.append(
            f"| `{p['sequence']}` | `{fe['order']}` (`{fe['canonical']}`) | "
            f"`{u['timestamp_unit']}` (`{u['median_dt_ms']:.3f} ms`, `{u['sample_rate_hz']:.2f} Hz`) | "
            f"`{u['rows_per_025s_bin']:.1f}` | "
            f"`{u['accel_unit_detected']}` (`{u['accel_norm_median_m_s2']:.3f}`, `{p05:.2f}..{p95:.2f}`) | "
            f"`({a0[0]:+.3f}, {a0[1]:+.3f}, {a0[2]:+.3f})` | "
            f"`rad/s` (`suspect={u['gyro_suspect_deg_s']}`, `{u['gyro_norm_median_rad_s']:.3f}`) | "
            f"`({g0[0]:+.4f}, {g0[1]:+.4f}, {g0[2]:+.4f})` | "
            f"**None (all units/conventions match EuRoC; only the rigid-rest assumption fails)** |"
        )

    L += [
        "",
        "## 4. Opening 5 Seconds Profile (`0..5 s` in 0.5 s slices, with mocap GT speed)",
        "",
        "| Sequence | Window (s) | Max gyro std (rad/s) | Mean ||w|| (rad/s) | Max accel std (m/s^2) | Mocap GT mean speed (m/s) | Mocap GT max speed (m/s) |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in probes:
        for sl in p["opening_5s_slices"]:
            ta, tb = sl["t_window_s"]
            L.append(
                f"| `{p['sequence']}` | {ta:.1f}..{tb:.1f} | {sl['gyro_std_max_rad_s']:.4f} | "
                f"{sl['gyro_rate_mean_rad_s']:.4f} | {sl['acc_std_max_m_s2']:.4f} | "
                f"{sl['mocap_speed_mean_m_s']:.4f} | {sl['mocap_speed_max_m_s']:.4f} |"
            )

    for p in probes:
        L += [
            "",
            f"## 5. All 60 One-Second Windows (`0..60 s`) -- `{p['sequence']}`",
            "",
            "| t (s) | std_gx | std_gy | std_gz | max_std_g (x0.02) | max_std_a (x0.10) | ||a||-9.81 | std(||a||) | ||mean_g|| | Pass |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for w in p["windows_1s"]:
            gs = w["gyro_std_xyz"]
            L.append(
                f"| {w['t_start_s']:2.0f}..{w['t_end_s']:2.0f} | {gs[0]:.4f} | {gs[1]:.4f} | {gs[2]:.4f} | "
                f"{w['gyro_std_max']:.4f} ({w['gyro_std_factor']:.1f}x) | "
                f"{w['acc_std_max']:.4f} ({w['acc_std_factor']:.1f}x) | "
                f"{w['acc_norm_minus_g']:+.4f} | {w['acc_norm_std']:.4f} | "
                f"{w['gyro_mean_norm']:.4f} | {'PASS' if w['passes_1s_rule'] else 'FAIL'} |"
            )

    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(ROOT / "data" / "tumvi"), help="TUM-VI root folder")
    ap.add_argument("--seqs", default=",".join(ALLOWED_DEFAULT),
                    help="Comma-separated sequence names (default: room1 and room2 only)")
    ap.add_argument("--json", help="Optional path to write full JSON output")
    a = ap.parse_args(argv)

    root = Path(a.root)
    names = [s.strip() for s in a.seqs.split(",") if s.strip()]
    for n in names:
        if n.startswith(FORBIDDEN_PREFIXES):
            raise SystemExit(f"refused: {n} is held out or final test set; G6 probes only tuning rooms 1 and 2")

    probes = [probe_sequence(root / n) for n in names]
    print(format_report(probes))

    if a.json:
        out_p = Path(a.json)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps({"rule": rule_specification(), "probes": probes}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

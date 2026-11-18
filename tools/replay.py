"""Generate a single self-contained HTML trajectory replay page for Vortex (Track 3).

Usage:
  python tools/replay.py IMU.csv estimated_trajectory.txt [--gt SEQ_DIR] [--events degrade.json] [--floor] -o replay.html

No server, no CDN, no external fonts, no http references; inline SVG + vanilla JS; under 3 MB for MH_01.
All scored numbers in the header are computed on the full-resolution trajectories by vortex.scoring
(never reimplemented and never computed from downsampled drawing points) and labelled:
"local scoring, not the organisers' evaluator".
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vortex import check_output, scoring  # noqa: E402
from vortex.data import euroc  # noqa: E402

MAX_DRAW_POINTS = 2200
DEFAULT_GAMMA = 1.7
DEFAULT_FLOOR_SEV = 0.02
DEFAULT_MAX_LEVEL = 1.0


def _fmt_num(x: float | None, digits: int = 3) -> str:
    if x is None or not math.isfinite(float(x)):
        return "-"
    return f"{float(x):.{digits}f}"


def _gap_rmse_mean(res: dict | None) -> float | None:
    if not res or "phases" not in res:
        return None
    drops = [d for d in res["phases"].get("dropouts", []) if d.get("n")]
    if not drops:
        return None
    return float(sum(d["rmse"] for d in drops) / len(drops))


def _blind_rmse(res: dict | None) -> float | None:
    if not res or "phases" not in res:
        return None
    b = res["phases"].get("blind")
    if not b or not b.get("n"):
        return None
    return b.get("rmse")


def _infer_meta(imu_path: Path, gt_path: Path | None, events: dict | None) -> dict:
    """Infer sequence name, reading (a/b/clean), and seed from paths, events, and optional meta.json."""
    meta_file = None
    for cand in (
        imu_path.parent.parent.parent / "meta.json",
        imu_path.parent / "meta.json",
    ):
        if cand.is_file():
            try:
                meta_file = json.loads(cand.read_text(encoding="utf-8"))
                break
            except Exception:
                pass

    seq_name = None
    reading = None
    seed = None

    if events:
        reading = events.get("reading")
        seed = events.get("seed")
    if meta_file:
        seq_name = meta_file.get("source_sequence") or seq_name
        reading = reading or meta_file.get("reading")
        seed = seed if seed is not None else meta_file.get("seed")

    folder_name = imu_path.parent.parent.parent.name if imu_path.parent.name == "imu0" else imu_path.stem
    if "_s" in folder_name and reading is None:
        rest, s_part = folder_name.rsplit("_s", 1)
        if s_part.isdigit() and rest.endswith(("_a", "_b")):
            seq_name = seq_name or rest[:-2]
            reading = rest[-1]
            seed = int(s_part)

    if seq_name is None:
        if gt_path is not None:
            p = Path(gt_path)
            seq_name = p.name if p.is_dir() else p.parent.name
        else:
            seq_name = folder_name

    if reading is None:
        reading = "clean"
    return {
        "sequence": str(seq_name),
        "reading": str(reading),
        "seed": seed,
        "meta": meta_file,
    }


def _detect_imu_faults(raw: euroc.RawImu, t0_s: float, healthy_end_s: float,
                       failure_at_s: float | None, events: dict | None) -> dict:
    """Extract or detect dropout bursts, zero tail, stuck runs, and spikes for the fault timeline."""
    valid_t = raw.t_ns >= 0
    t_rel = np.where(valid_t, raw.t_ns / 1e9 - t0_s, np.nan)
    finite_t = t_rel[np.isfinite(t_rel)]
    duration_s = float(finite_t[-1]) if len(finite_t) else 0.0

    # 1. Missing-row bursts
    if events and "dropouts_s" in events:
        dropouts = [[float(a), float(b)] for a, b in events.get("dropouts_s", [])]
    else:
        dropouts = []
        if len(finite_t) >= 3:
            dt = np.diff(finite_t)
            med_dt = float(np.median(dt[dt > 0])) if np.any(dt > 0) else 0.005
            gap_idx = np.flatnonzero(dt >= max(5.0 * med_dt, 0.024))
            for idx in gap_idx:
                dropouts.append([float(finite_t[idx]), float(finite_t[idx + 1])])

    # 2. Blind / zero tail
    zero_mask = valid_t & np.all(raw.gyro == 0.0, axis=1) & np.all(raw.accel == 0.0, axis=1)
    if failure_at_s is None and len(zero_mask) > 10 and bool(zero_mask[-1]):
        k = len(zero_mask) - 1
        while k > 0 and bool(zero_mask[k - 1]):
            k -= 1
        if len(zero_mask) - k >= 10 and math.isfinite(t_rel[k]):
            failure_at_s = float(t_rel[k])

    active_end = failure_at_s if failure_at_s is not None else duration_s

    # 3. Stuck runs (exact repeat of gyro or accel triple for >= 2 consecutive rows in active window)
    if events and "stuck_s" in events:
        stuck_runs = [[float(a), float(b)] for a, b in events["stuck_s"]]
    else:
        stuck_runs = []
        if len(raw) >= 3:
            g_same = np.all(np.diff(raw.gyro, axis=0) == 0.0, axis=1)
            a_same = np.all(np.diff(raw.accel, axis=0) == 0.0, axis=1)
            rep = (g_same | a_same) & ~zero_mask[1:]
            i = 0
            n_rep = len(rep)
            while i < n_rep:
                if not rep[i]:
                    i += 1
                    continue
                j = i
                while j < n_rep and rep[j]:
                    j += 1
                ts_a = float(t_rel[i]) if math.isfinite(t_rel[i]) else 0.0
                ts_b = float(t_rel[j]) if math.isfinite(t_rel[j]) else ts_a
                if ts_a >= healthy_end_s and ts_b <= active_end + 1e-3 and (j - i) >= 2:
                    stuck_runs.append([round(ts_a, 4), round(ts_b, 4)])
                i = j
            if len(stuck_runs) > 160:
                step = max(1, len(stuck_runs) // 160)
                stuck_runs = stuck_runs[::step]

    # 4. Spikes (listed in events or high 2nd-difference outliers in active window)
    if events and "spikes_s" in events:
        spikes_s = [float(x) for x in events["spikes_s"]]
    else:
        spikes_s = []
        if len(raw) >= 10:
            v = np.hstack([raw.gyro, raw.accel])
            d2 = v[2:] - 2.0 * v[1:-1] + v[:-2]
            g_jump = np.linalg.norm(d2[:, :3], axis=1)
            a_jump = np.linalg.norm(d2[:, 3:], axis=1)
            t_mid = t_rel[1:-1]
            act = (
                np.isfinite(t_mid)
                & (t_mid >= healthy_end_s)
                & (t_mid < active_end - 0.02)
                & ~zero_mask[1:-1]
            )
            if np.any(act):
                score_jump = np.where(act, g_jump / 0.4 + a_jump / 2.5, 0.0)
                cand = np.flatnonzero(score_jump > 1.8)
                if len(cand) > 80:
                    top_order = np.argsort(score_jump[cand])[-80:]
                    cand = np.sort(cand[top_order])
                spikes_s = [round(float(t_mid[c]), 4) for c in cand]

    return {
        "healthy_end_s": float(healthy_end_s),
        "dropouts_s": dropouts,
        "failure_at_s": float(failure_at_s) if failure_at_s is not None else None,
        "end_s": float(events.get("end_s", duration_s)) if events else duration_s,
        "stuck_s": stuck_runs,
        "spikes_s": spikes_s,
    }


def _select_indices(t_rel: np.ndarray, max_points: int, dropouts_s: list, failure_at_s: float | None) -> np.ndarray:
    """Downsample indices for drawing while preserving start, end, dropout boundaries, and blind start."""
    n = len(t_rel)
    if n <= max_points:
        return np.arange(n, dtype=int)
    base = set(np.linspace(0, n - 1, max_points, dtype=int).tolist())
    base.add(0)
    base.add(n - 1)
    for a, b in dropouts_s:
        ia = int(np.clip(np.searchsorted(t_rel, a), 0, n - 1))
        ib = int(np.clip(np.searchsorted(t_rel, b), 0, n - 1))
        for k in (ia - 1, ia, ib, ib + 1):
            if 0 <= k < n:
                base.add(k)
    if failure_at_s is not None:
        ib = int(np.clip(np.searchsorted(t_rel, failure_at_s), 0, n - 1))
        for k in (ib - 1, ib, ib + 1):
            if 0 <= k < n:
                base.add(k)
    return np.array(sorted(base), dtype=int)


def _svg_polyline(xs: np.ndarray, ys: np.ndarray, x_map, y_map) -> str:
    if len(xs) == 0:
        return ""
    return " ".join(f"{x_map(float(x)):.1f},{y_map(float(y)):.1f}" for x, y in zip(xs, ys))


def build_replay(imu_path: str | Path, est_path: str | Path, gt_path: str | Path | None = None,
                 events_path: str | Path | None = None, show_floor: bool = False) -> tuple[str, dict]:
    """Compute local scores via vortex.scoring and build the self-contained HTML string and summary dict."""
    imu_path = Path(imu_path)
    est_path = Path(est_path)
    events = json.loads(Path(events_path).read_text(encoding="utf-8")) if events_path else None

    raw_imu = euroc.read_imu_csv(imu_path)
    est_traj, est_info = scoring.read_tum(est_path)
    chk = check_output.check(imu_path, est_path)

    t0_ns = int(events["t0_ns"]) if (events and "t0_ns" in events) else (
        int(raw_imu.t_ns[0]) if len(raw_imu) and raw_imu.t_ns[0] >= 0 else int(round(est_traj.t[0] * 1e9))
    )
    t0_s = t0_ns / 1e9

    info = _infer_meta(imu_path, Path(gt_path) if gt_path else None, events)
    meta_cfg = ((info.get("meta") or {}).get("config")) or {}
    gamma = float((info.get("meta") or {}).get("gamma", meta_cfg.get("gamma", DEFAULT_GAMMA)))
    max_level = float((info.get("meta") or {}).get("max_level", meta_cfg.get("max_level", DEFAULT_MAX_LEVEL)))
    sev_floor = float(meta_cfg.get("floor", DEFAULT_FLOOR_SEV))
    healthy_end_s = float(events.get("healthy_end_s", meta_cfg.get("protect_seconds", 2.0))) if events else 0.0
    failure_at_s = events.get("failure_at_s") if events else None

    faults = _detect_imu_faults(raw_imu, t0_s, healthy_end_s, failure_at_s, events)

    has_gt = gt_path is not None
    res_est = None
    res_floor = None
    floor_point = [0.0, 0.0, 0.0]

    if has_gt:
        ref_traj = scoring.read_ground_truth(gt_path)
        res_est = scoring.score(ref_traj, est_traj, align="se3", rpe_deltas=(200,), events=events)
        al_est = scoring.fit_alignment(ref_traj, est_traj, mode="se3")
        est_aligned = scoring.apply(est_traj, al_est)

        ref_s, est_s = scoring.associate(ref_traj, est_traj)
        est_s_al = scoring.apply(est_s, al_est)
        err_s = np.linalg.norm(est_s_al.p - ref_s.p, axis=1)
        t_err_rel = ref_s.t - t0_s

        # Never-moving floor scored by vortex.scoring.score the exact same way
        floor_traj = scoring.Traj(
            t=est_traj.t.copy(),
            p=np.zeros_like(est_traj.p),
            R=np.broadcast_to(np.eye(3), est_traj.R.shape).copy(),
        )
        res_floor = scoring.score(ref_traj, floor_traj, align="se3", rpe_deltas=(200,), events=events)
        al_floor = scoring.fit_alignment(ref_traj, floor_traj, mode="se3")
        floor_al = scoring.apply(floor_traj, al_floor)
        floor_point = [float(floor_al.p[0, 0]), float(floor_al.p[0, 1]), float(floor_al.p[0, 2])]
        floor_err_s = np.linalg.norm(floor_al.p[0] - ref_s.p, axis=1)
    else:
        ref_traj = None
        est_aligned = est_traj
        t_err_rel = np.array([], dtype=float)
        err_s = np.array([], dtype=float)
        floor_err_s = np.array([], dtype=float)

    est_t_rel = est_aligned.t - t0_s
    duration_s = float(max(
        faults["end_s"],
        float(est_t_rel[-1]) if len(est_t_rel) else 0.0,
        float((ref_traj.t[-1] - t0_s)) if (ref_traj is not None and len(ref_traj.t)) else 0.0,
        1e-3,
    ))

    # Downsample for drawing only (never for header metrics)
    idx_est = _select_indices(est_t_rel, MAX_DRAW_POINTS, faults["dropouts_s"], faults["failure_at_s"])
    draw_est_t = np.round(est_t_rel[idx_est], 4)
    draw_est_p = np.round(est_aligned.p[idx_est], 4)

    if ref_traj is not None and len(ref_traj.t):
        gt_t_rel = ref_traj.t - t0_s
        idx_gt = _select_indices(gt_t_rel, MAX_DRAW_POINTS, faults["dropouts_s"], faults["failure_at_s"])
        draw_gt_t = np.round(gt_t_rel[idx_gt], 4)
        draw_gt_p = np.round(ref_traj.p[idx_gt], 4)
        idx_err = _select_indices(t_err_rel, MAX_DRAW_POINTS, faults["dropouts_s"], faults["failure_at_s"])
        draw_err_t = np.round(t_err_rel[idx_err], 4)
        draw_err_v = np.round(err_s[idx_err], 4)
        draw_floor_err_v = np.round(floor_err_s[idx_err], 4)
    else:
        draw_gt_t = np.array([], dtype=float)
        draw_gt_p = np.zeros((0, 3), dtype=float)
        draw_err_t = np.array([], dtype=float)
        draw_err_v = np.array([], dtype=float)
        draw_floor_err_v = np.array([], dtype=float)

    metrics_summary = {
        "label": "local scoring, not the organisers' evaluator",
        "sequence": info["sequence"],
        "reading": info["reading"],
        "seed": info["seed"],
        "has_gt": has_gt,
        "show_floor": bool(show_floor or has_gt),
        "input_rows": int(chk["input_rows"]),
        "output_rows": int(chk["output_rows"]),
        "contract": "PASS" if chk["ok"] else "FAIL",
        "duration_s": duration_s,
        "estimator": {
            "ape_se3_rmse": res_est["ape"]["rmse"] if res_est else None,
            "rpe_1s_rmse": res_est["rpe"]["200"]["rmse"] if res_est else None,
            "gap_rmse": _gap_rmse_mean(res_est),
            "blind_rmse": _blind_rmse(res_est),
            "final_error": res_est["final_error"] if res_est else None,
        },
        "floor": {
            "ape_se3_rmse": res_floor["ape"]["rmse"] if res_floor else None,
            "rpe_1s_rmse": res_floor["rpe"]["200"]["rmse"] if res_floor else None,
            "gap_rmse": _gap_rmse_mean(res_floor),
            "blind_rmse": _blind_rmse(res_floor),
            "final_error": res_floor["final_error"] if res_floor else None,
            "point_xyz": floor_point,
        },
    }

    html_text = _render_html(
        metrics_summary,
        faults,
        draw_est_t,
        draw_est_p,
        draw_gt_t,
        draw_gt_p,
        draw_err_t,
        draw_err_v,
        draw_floor_err_v,
        sev_floor=sev_floor,
        max_level=max_level,
        gamma=gamma,
    )
    return html_text, metrics_summary


def _render_html(
    summary: dict,
    faults: dict,
    est_t: np.ndarray,
    est_p: np.ndarray,
    gt_t: np.ndarray,
    gt_p: np.ndarray,
    err_t: np.ndarray,
    err_v: np.ndarray,
    floor_err_v: np.ndarray,
    sev_floor: float,
    max_level: float,
    gamma: float,
) -> str:
    """Build one self-contained HTML5 document with inline SVG plots and interactive scrubber."""
    has_gt = summary["has_gt"] and len(gt_p) > 0
    dur = max(summary["duration_s"], 1.0)
    est_m = summary["estimator"]
    flo_m = summary["floor"]

    # ---- XY coordinate bounds ----
    all_x = [est_p[:, 0]] if len(est_p) else [np.array([0.0])]
    all_y = [est_p[:, 1]] if len(est_p) else [np.array([0.0])]
    if has_gt:
        all_x.append(gt_p[:, 0])
        all_y.append(gt_p[:, 1])
        all_x.append(np.array([flo_m["point_xyz"][0]]))
        all_y.append(np.array([flo_m["point_xyz"][1]]))
    cat_x = np.concatenate(all_x)
    cat_y = np.concatenate(all_y)
    xmin, xmax = float(np.min(cat_x)), float(np.max(cat_x))
    ymin, ymax = float(np.min(cat_y)), float(np.max(cat_y))
    span_x = max(xmax - xmin, 0.5)
    span_y = max(ymax - ymin, 0.5)
    span = max(span_x, span_y) * 1.12
    cx, cy = 0.5 * (xmin + xmax), 0.5 * (ymin + ymax)
    x0, x1 = cx - 0.5 * span, cx + 0.5 * span
    y0, y1 = cy - 0.5 * span, cy + 0.5 * span

    W_XY, H_XY, PAD_XY = 560, 520, 44
    plot_w_xy = W_XY - 2 * PAD_XY
    plot_h_xy = H_XY - 2 * PAD_XY
    map_xy_x = lambda x: PAD_XY + (x - x0) / (x1 - x0) * plot_w_xy  # noqa: E731
    map_xy_y = lambda y: H_XY - PAD_XY - (y - y0) / (y1 - y0) * plot_h_xy  # noqa: E731

    gt_xy_pts = _svg_polyline(gt_p[:, 0], gt_p[:, 1], map_xy_x, map_xy_y) if has_gt else ""
    est_xy_pts = _svg_polyline(est_p[:, 0], est_p[:, 1], map_xy_x, map_xy_y)

    # Highlighted dropout polylines on XY plot
    dropout_xy_polylines = []
    for a, b in faults["dropouts_s"]:
        m = (est_t >= a - 1e-4) & (est_t <= b + 1e-4)
        idx = np.flatnonzero(m)
        if len(idx) < 2 and len(est_t) >= 2:
            i0 = max(0, int(np.searchsorted(est_t, a)) - 1)
            i1 = min(len(est_t) - 1, int(np.searchsorted(est_t, b)))
            if i1 > i0:
                idx = np.arange(i0, i1 + 1)
        if len(idx) >= 2:
            pts = _svg_polyline(est_p[idx, 0], est_p[idx, 1], map_xy_x, map_xy_y)
            dropout_xy_polylines.append(
                f'<polyline class="xy-dropout" points="{pts}" data-window="{a:.2f}-{b:.2f}s"/>'
            )

    # Highlighted blind 5 s polyline on XY plot
    blind_xy_svg = ""
    if faults["failure_at_s"] is not None:
        m_blind = est_t >= (faults["failure_at_s"] - 1e-4)
        if np.count_nonzero(m_blind) >= 2:
            pts_b = _svg_polyline(est_p[m_blind, 0], est_p[m_blind, 1], map_xy_x, map_xy_y)
            blind_xy_svg = f'<polyline class="xy-blind" points="{pts_b}"/>'

    fx_px = map_xy_x(flo_m["point_xyz"][0])
    fy_px = map_xy_y(flo_m["point_xyz"][1])

    # ---- Height z(t) bounds ----
    all_z = [est_p[:, 2]] if len(est_p) else [np.array([0.0])]
    if has_gt:
        all_z.append(gt_p[:, 2])
        all_z.append(np.array([flo_m["point_xyz"][2]]))
    cat_z = np.concatenate(all_z)
    zmin, zmax = float(np.min(cat_z)), float(np.max(cat_z))
    zpad = max(0.1 * (zmax - zmin), 0.25)
    z0, z1 = zmin - zpad, zmax + zpad

    W_TS, H_Z = 680, 210
    PAD_L, PAD_R, PAD_T, PAD_B = 54, 20, 20, 28
    pw_ts = W_TS - PAD_L - PAD_R
    ph_z = H_Z - PAD_T - PAD_B
    map_t_x = lambda t: PAD_L + np.clip(t / dur, 0.0, 1.0) * pw_ts  # noqa: E731
    map_z_y = lambda z: PAD_T + ph_z - (z - z0) / (z1 - z0) * ph_z  # noqa: E731

    gt_z_pts = _svg_polyline(gt_t, gt_p[:, 2], map_t_x, map_z_y) if has_gt else ""
    est_z_pts = _svg_polyline(est_t, est_p[:, 2], map_t_x, map_z_y)
    fz_py = map_z_y(flo_m["point_xyz"][2])

    # ---- Position Error ||e(t)|| + Fault Timeline bounds ----
    H_ERR_TOTAL = 265
    ERR_TOP, ERR_H = 18, 138
    TL_TOP, TL_H = 178, 52
    emax = float(np.max(np.concatenate([err_v, floor_err_v]))) if (has_gt and len(err_v)) else 1.0
    e1 = max(emax * 1.08, 0.5)
    map_e_y = lambda e: ERR_TOP + ERR_H - np.clip(e / e1, 0.0, 1.0) * ERR_H  # noqa: E731

    err_pts = _svg_polyline(err_t, err_v, map_t_x, map_e_y) if (has_gt and len(err_t)) else ""
    floor_err_pts = _svg_polyline(err_t, floor_err_v, map_t_x, map_e_y) if (has_gt and len(err_t)) else ""

    # ---- Fault timeline & severity ramp SVG elements ----
    # Severity ramp shaded blocks (48 slices across [0, dur])
    ramp_rects = []
    n_slices = 48
    for k in range(n_slices):
        ta = (k / n_slices) * dur
        tb = ((k + 1) / n_slices) * dur
        t_norm = 0.5 * (ta + tb) / dur
        sev = sev_floor + (max_level - sev_floor) * (t_norm ** gamma)
        alpha = 0.10 + 0.55 * min(1.0, max(0.0, sev))
        xa = map_t_x(ta)
        xb = map_t_x(tb)
        ramp_rects.append(
            f'<rect x="{xa:.1f}" y="{TL_TOP}" width="{max(1.0, xb - xa + 0.4):.1f}" height="{TL_H}" '
            f'fill="rgba(249, 115, 22, {alpha:.3f})"/>'
        )
    # Severity ramp curve overlay inside the fault strip
    ramp_curve_t = np.linspace(0.0, dur, 60)
    ramp_curve_v = sev_floor + (max_level - sev_floor) * np.power(ramp_curve_t / dur, gamma)
    map_sev_y = lambda s: TL_TOP + TL_H - np.clip(s / max(max_level, 1.0), 0.0, 1.0) * (TL_H - 4) - 2  # noqa: E731
    ramp_curve_pts = _svg_polyline(ramp_curve_t, ramp_curve_v, map_t_x, map_sev_y)

    # Protected opening 2 s
    prot_svg = ""
    if faults["healthy_end_s"] > 0:
        xw = max(2.0, map_t_x(faults["healthy_end_s"]) - PAD_L)
        prot_svg = (
            f'<rect class="tl-protected" x="{PAD_L:.1f}" y="{TL_TOP}" width="{xw:.1f}" height="{TL_H}"/>'
        )

    # Dropout bands on Z, Error, and Fault Timeline
    z_drop_rects, err_drop_rects, tl_drop_rects = [], [], []
    for a, b in faults["dropouts_s"]:
        xa = map_t_x(a)
        xw = max(2.0, map_t_x(b) - xa)
        z_drop_rects.append(f'<rect class="band-dropout" x="{xa:.1f}" y="{PAD_T}" width="{xw:.1f}" height="{ph_z}"/>')
        err_drop_rects.append(f'<rect class="band-dropout" x="{xa:.1f}" y="{ERR_TOP}" width="{xw:.1f}" height="{ERR_H}"/>')
        tl_drop_rects.append(
            f'<rect class="tl-dropout" x="{xa:.1f}" y="{TL_TOP + 2}" width="{xw:.1f}" height="{TL_H - 4}"/>'
        )

    # Blind 5 s zero tail on Z, Error, and Fault Timeline
    z_blind_svg = err_blind_svg = tl_blind_svg = ""
    if faults["failure_at_s"] is not None:
        xb = map_t_x(faults["failure_at_s"])
        bw = max(2.0, (PAD_L + pw_ts) - xb)
        z_blind_svg = f'<rect class="band-blind" x="{xb:.1f}" y="{PAD_T}" width="{bw:.1f}" height="{ph_z}"/>'
        err_blind_svg = f'<rect class="band-blind" x="{xb:.1f}" y="{ERR_TOP}" width="{bw:.1f}" height="{ERR_H}"/>'
        tl_blind_svg = f'<rect class="tl-blind" x="{xb:.1f}" y="{TL_TOP}" width="{bw:.1f}" height="{TL_H}"/>'

    # Spikes & stuck runs on Fault Timeline
    spike_ticks = []
    for ts in faults["spikes_s"]:
        xs = map_t_x(ts)
        spike_ticks.append(
            f'<line class="tl-spike" x1="{xs:.1f}" y1="{TL_TOP + 3}" x2="{xs:.1f}" y2="{TL_TOP + TL_H * 0.48:.1f}"/>'
        )
    stuck_ticks = []
    for sa, sb in faults["stuck_s"]:
        xa = map_t_x(sa)
        xw = max(1.8, map_t_x(sb) - xa)
        stuck_ticks.append(
            f'<rect class="tl-stuck" x="{xa:.1f}" y="{TL_TOP + TL_H * 0.54:.1f}" width="{xw:.1f}" height="{TL_H * 0.38:.1f}"/>'
        )

    # Grid lines & axis ticks
    xy_grid = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        xv = x0 + frac * (x1 - x0)
        yv = y0 + frac * (y1 - y0)
        xp = map_xy_x(xv)
        yp = map_xy_y(yv)
        xy_grid.append(f'<line class="grid" x1="{xp:.1f}" y1="{PAD_XY}" x2="{xp:.1f}" y2="{H_XY - PAD_XY}"/>')
        xy_grid.append(f'<line class="grid" x1="{PAD_XY}" y1="{yp:.1f}" x2="{W_XY - PAD_XY}" y2="{yp:.1f}"/>')
        xy_grid.append(f'<text class="tick" x="{xp:.1f}" y="{H_XY - PAD_XY + 16}" text-anchor="middle">{xv:.1f}m</text>')
        xy_grid.append(f'<text class="tick" x="{PAD_XY - 6}" y="{yp + 4:.1f}" text-anchor="end">{yv:.1f}m</text>')

    z_grid = []
    for frac in (0.0, 0.5, 1.0):
        zv = z0 + frac * (z1 - z0)
        yp = map_z_y(zv)
        z_grid.append(f'<line class="grid" x1="{PAD_L}" y1="{yp:.1f}" x2="{PAD_L + pw_ts}" y2="{yp:.1f}"/>')
        z_grid.append(f'<text class="tick" x="{PAD_L - 6}" y="{yp + 4:.1f}" text-anchor="end">{zv:.2f}m</text>')
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        tv = frac * dur
        xp = map_t_x(tv)
        z_grid.append(f'<line class="grid" x1="{xp:.1f}" y1="{PAD_T}" x2="{xp:.1f}" y2="{PAD_T + ph_z}"/>')
        z_grid.append(f'<text class="tick" x="{xp:.1f}" y="{H_Z - 8}" text-anchor="middle">{tv:.1f}s</text>')

    err_grid = []
    for frac in (0.0, 0.5, 1.0):
        ev = frac * e1
        yp = map_e_y(ev)
        err_grid.append(f'<line class="grid" x1="{PAD_L}" y1="{yp:.1f}" x2="{PAD_L + pw_ts}" y2="{yp:.1f}"/>')
        err_grid.append(f'<text class="tick" x="{PAD_L - 6}" y="{yp + 4:.1f}" text-anchor="end">{ev:.2f}m</text>')
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        tv = frac * dur
        xp = map_t_x(tv)
        err_grid.append(f'<line class="grid" x1="{xp:.1f}" y1="{ERR_TOP}" x2="{xp:.1f}" y2="{ERR_TOP + ERR_H}"/>')
        err_grid.append(f'<text class="tick" x="{xp:.1f}" y="{H_ERR_TOTAL - 8}" text-anchor="middle">{tv:.1f}s</text>')

    # Start & end markers on XY
    start_est_x = map_xy_x(float(est_p[0, 0])) if len(est_p) else PAD_XY
    start_est_y = map_xy_y(float(est_p[0, 1])) if len(est_p) else PAD_XY
    end_est_x = map_xy_x(float(est_p[-1, 0])) if len(est_p) else PAD_XY
    end_est_y = map_xy_y(float(est_p[-1, 1])) if len(est_p) else PAD_XY

    # Data payload for client-side interactive scrubber
    js_payload = {
        "has_gt": has_gt,
        "duration_s": round(dur, 4),
        "bounds": {
            "xy": [x0, x1, y0, y1, PAD_XY, W_XY, H_XY],
            "z": [z0, z1, PAD_L, pw_ts, PAD_T, ph_z],
            "err": [0.0, e1, PAD_L, pw_ts, ERR_TOP, ERR_H, TL_TOP, TL_H],
        },
        "faults": {
            "healthy_end_s": faults["healthy_end_s"],
            "dropouts_s": faults["dropouts_s"],
            "failure_at_s": faults["failure_at_s"],
            "sev_floor": sev_floor,
            "max_level": max_level,
            "gamma": gamma,
        },
        "est": {
            "t": est_t.tolist(),
            "x": est_p[:, 0].tolist() if len(est_p) else [],
            "y": est_p[:, 1].tolist() if len(est_p) else [],
            "z": est_p[:, 2].tolist() if len(est_p) else [],
        },
        "gt": {
            "t": gt_t.tolist() if has_gt else [],
            "x": gt_p[:, 0].tolist() if has_gt else [],
            "y": gt_p[:, 1].tolist() if has_gt else [],
            "z": gt_p[:, 2].tolist() if has_gt else [],
        },
        "err": {
            "t": err_t.tolist() if has_gt else [],
            "v": err_v.tolist() if has_gt else [],
            "fv": floor_err_v.tolist() if has_gt else [],
        },
    }

    seq_esc = html.escape(str(summary["sequence"]))
    reading_esc = html.escape(str(summary["reading"]))
    seed_esc = "-" if summary["seed"] is None else html.escape(str(summary["seed"]))
    contract_esc = html.escape(summary["contract"])

    ape_est_str = _fmt_num(est_m["ape_se3_rmse"], 4)
    ape_flo_str = _fmt_num(flo_m["ape_se3_rmse"], 4)
    rpe_est_str = _fmt_num(est_m["rpe_1s_rmse"], 4)
    rpe_flo_str = _fmt_num(flo_m["rpe_1s_rmse"], 4)
    gap_est_str = _fmt_num(est_m["gap_rmse"], 4)
    gap_flo_str = _fmt_num(flo_m["gap_rmse"], 4)
    blind_est_str = _fmt_num(est_m["blind_rmse"], 4)
    blind_flo_str = _fmt_num(flo_m["blind_rmse"], 4)

    first_drop_s = faults["dropouts_s"][0][0] if faults["dropouts_s"] else 0.0
    blind_start_s = faults["failure_at_s"] if faults["failure_at_s"] is not None else max(0.0, dur - 5.0)

    floor_xy_svg = ""
    floor_z_svg = ""
    if summary["show_floor"] and has_gt:
        floor_xy_svg = (
            f'<g class="xy-floor" transform="translate({fx_px:.1f},{fy_px:.1f})">'
            f'<circle r="6" fill="none" stroke="var(--floor)" stroke-width="2"/>'
            f'<line x1="-8" y1="0" x2="8" y2="0" stroke="var(--floor)" stroke-width="1.8"/>'
            f'<line x1="0" y1="-8" x2="0" y2="8" stroke="var(--floor)" stroke-width="1.8"/>'
            f'</g>'
        )
        floor_z_svg = (
            f'<line class="z-floor" x1="{PAD_L}" y1="{fz_py:.1f}" x2="{PAD_L + pw_ts}" y2="{fz_py:.1f}"/>'
        )

    no_gt_banner = ""
    if not has_gt:
        no_gt_banner = (
            f'<text class="tick" x="{PAD_L + pw_ts / 2:.1f}" y="{ERR_TOP + ERR_H / 2:.1f}" '
            f'text-anchor="middle">Ground truth not provided (--gt omitted): path-only mode</text>'
        )

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Vortex Replay — {seq_esc} ({reading_esc}, seed {seed_esc})</title>
<style>
:root {{
  color-scheme: dark light;
  --bg: #0b101b;
  --panel: #131b2e;
  --border: #24324d;
  --text: #e2e8f0;
  --muted: #94a3b8;
  --gt: #22c55e;
  --est: #38bdf8;
  --floor: #a855f7;
  --dropout: #f59e0b;
  --blind: #ef4444;
  --spike: #fde047;
  --stuck: #c084fc;
  --grid: rgba(148, 163, 184, 0.16);
}}
@media (prefers-color-scheme: light) {{
  :root:not([data-theme="dark"]) {{
    --bg: #f8fafc;
    --panel: #ffffff;
    --border: #cbd5e1;
    --text: #0f172a;
    --muted: #475569;
    --gt: #15803d;
    --est: #0284c7;
    --floor: #7e22ce;
    --dropout: #d97706;
    --blind: #dc2626;
    --spike: #ca8a04;
    --stuck: #9333ea;
    --grid: rgba(71, 85, 105, 0.18);
  }}
}}
:root[data-theme="light"] {{
  --bg: #f8fafc;
  --panel: #ffffff;
  --border: #cbd5e1;
  --text: #0f172a;
  --muted: #475569;
  --gt: #15803d;
  --est: #0284c7;
  --floor: #7e22ce;
  --dropout: #d97706;
  --blind: #dc2626;
  --spike: #ca8a04;
  --stuck: #9333ea;
  --grid: rgba(71, 85, 105, 0.18);
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  padding: 14px 18px 22px;
  background: var(--bg);
  color: var(--text);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  line-height: 1.4;
}}
header {{
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 16px;
  margin-bottom: 12px;
}}
.title-block h1 {{
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
}}
.subtitle {{
  font-size: 0.82rem;
  color: var(--muted);
  margin-top: 2px;
}}
.badge-note {{
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 0.76rem;
  font-weight: 600;
  background: rgba(245, 158, 11, 0.16);
  color: var(--dropout);
  border: 1px solid var(--dropout);
  margin-left: 8px;
}}
.metrics-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
  flex: 1 1 560px;
}}
.metric-card {{
  background: rgba(148, 163, 184, 0.06);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 10px;
}}
.metric-card .k {{
  font-size: 0.73rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}}
.metric-card .v {{
  font-size: 0.96rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}}
.metric-card .sub {{
  font-size: 0.74rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}}
.scrubber-bar {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 12px;
}}
.scrubber-bar input[type="range"] {{
  flex: 1 1 280px;
  accent-color: var(--est);
  cursor: pointer;
}}
button {{
  background: rgba(56, 189, 248, 0.14);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 0.82rem;
  cursor: pointer;
}}
button:hover, button:focus-visible {{
  border-color: var(--est);
  outline: none;
}}
.readout {{
  font-size: 0.83rem;
  font-variant-numeric: tabular-nums;
  color: var(--text);
  min-width: 310px;
}}
.main-grid {{
  display: grid;
  grid-template-columns: minmax(340px, 560px) 1fr;
  gap: 12px;
  align-items: start;
}}
@media (max-width: 1024px) {{
  .main-grid {{ grid-template-columns: 1fr; }}
}}
.panel {{
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
}}
.panel-head {{
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  gap: 8px;
}}
.panel-title {{
  font-size: 0.9rem;
  font-weight: 600;
}}
.legend {{
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 0.76rem;
  color: var(--muted);
}}
.legend span {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
}}
.swatch {{
  width: 12px;
  height: 3px;
  display: inline-block;
  border-radius: 2px;
}}
svg {{
  width: 100%;
  height: auto;
  display: block;
  user-select: none;
}}
.grid {{ stroke: var(--grid); stroke-width: 1; }}
.tick {{ fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }}
.xy-gt, .z-gt {{ fill: none; stroke: var(--gt); stroke-width: 1.9; stroke-opacity: 0.88; }}
.xy-est, .z-est, .err-est {{ fill: none; stroke: var(--est); stroke-width: 2.1; }}
.xy-dropout {{ fill: none; stroke: var(--dropout); stroke-width: 3.4; stroke-linecap: round; }}
.xy-blind {{ fill: none; stroke: var(--blind); stroke-width: 3.8; stroke-linecap: round; }}
.z-floor, .err-floor {{ fill: none; stroke: var(--floor); stroke-width: 1.5; stroke-dasharray: 5 4; }}
.band-dropout {{ fill: var(--dropout); fill-opacity: 0.22; }}
.band-blind {{ fill: var(--blind); fill-opacity: 0.22; }}
.tl-protected {{ fill: var(--gt); fill-opacity: 0.35; stroke: var(--gt); stroke-width: 1; }}
.tl-dropout {{ fill: var(--dropout); fill-opacity: 0.85; }}
.tl-blind {{ fill: var(--blind); fill-opacity: 0.85; }}
.tl-spike {{ stroke: var(--spike); stroke-width: 1.4; }}
.tl-stuck {{ fill: var(--stuck); fill-opacity: 0.85; }}
.tl-ramp-curve {{ fill: none; stroke: var(--text); stroke-opacity: 0.55; stroke-width: 1.3; stroke-dasharray: 3 2; }}
.cursor-line {{ stroke: var(--text); stroke-width: 1.4; stroke-dasharray: 3 3; }}
</style>
</head>
<body>
<header>
  <div class="title-block">
    <h1>
      Vortex Trajectory Replay — <span id="hdr-seq">{seq_esc}</span>
      <span class="badge-note">local scoring, not the organisers' evaluator</span>
    </h1>
    <div class="subtitle">
      Reading: <strong id="hdr-reading">{reading_esc}</strong> ·
      Seed: <strong id="hdr-seed">{seed_esc}</strong> ·
      Rows: <strong>{summary["input_rows"]}</strong> ·
      Duration: <strong>{dur:.2f} s</strong> ·
      Contract: <strong>{contract_esc}</strong>
    </div>
  </div>
  <div class="metrics-grid" aria-label="Trajectory scores">
    <div class="metric-card">
      <div class="k">APE SE(3) RMSE (m)</div>
      <div class="v" id="val-ape-est">{ape_est_str}</div>
      <div class="sub">Floor: <span id="val-ape-floor">{ape_flo_str}</span></div>
    </div>
    <div class="metric-card">
      <div class="k">RPE 1 s RMSE (m)</div>
      <div class="v" id="val-rpe-est">{rpe_est_str}</div>
      <div class="sub">Floor: <span id="val-rpe-floor">{rpe_flo_str}</span></div>
    </div>
    <div class="metric-card">
      <div class="k">Gap RMSE (m)</div>
      <div class="v" id="val-gap-est">{gap_est_str}</div>
      <div class="sub">Floor: <span id="val-gap-floor">{gap_flo_str}</span> ({len(faults["dropouts_s"])} bursts)</div>
    </div>
    <div class="metric-card">
      <div class="k">Blind 5 s RMSE (m)</div>
      <div class="v" id="val-blind-est">{blind_est_str}</div>
      <div class="sub">Floor: <span id="val-blind-floor">{blind_flo_str}</span></div>
    </div>
  </div>
</header>

<section class="scrubber-bar" aria-label="Time scrubber controls">
  <button type="button" id="btn-play" aria-label="Play or pause replay">Play</button>
  <label for="time-slider" style="font-size:0.82rem;color:var(--muted);">Time</label>
  <input type="range" id="time-slider" min="0" max="{dur:.4f}" step="0.01" value="0"
         aria-label="Trajectory time scrubber in seconds"/>
  <button type="button" id="btn-start">Start (0s)</button>
  <button type="button" id="btn-drop">1st Dropout ({first_drop_s:.1f}s)</button>
  <button type="button" id="btn-blind">Blind 5 s ({blind_start_s:.1f}s)</button>
  <button type="button" id="btn-end">End ({dur:.1f}s)</button>
  <button type="button" id="btn-theme" aria-label="Toggle dark and light theme">Theme</button>
  <div class="readout" id="live-readout" aria-live="polite">
    t = 0.00 s · phase: healthy · est (0.00, 0.00, 0.00) m
  </div>
</section>

<main class="main-grid">
  <section class="panel" aria-label="Top-down XY trajectory">
    <div class="panel-head">
      <div class="panel-title">Top-Down XY Path (SE(3) Umeyama aligned)</div>
      <div class="legend">
        <span><i class="swatch" style="background:var(--gt)"></i>GT</span>
        <span><i class="swatch" style="background:var(--est)"></i>Vortex</span>
        <span><i class="swatch" style="background:var(--dropout);height:4px"></i>Dropout burst</span>
        <span><i class="swatch" style="background:var(--blind);height:4px"></i>Blind 5 s</span>
        <span><i class="swatch" style="background:var(--floor)"></i>Floor (still)</span>
      </div>
    </div>
    <svg id="svg-xy" viewBox="0 0 {W_XY} {H_XY}" role="img" aria-label="Top-down XY path plot">
      {"".join(xy_grid)}
      <rect x="{PAD_XY}" y="{PAD_XY}" width="{plot_w_xy}" height="{plot_h_xy}" fill="none" stroke="var(--border)"/>
      {f'<polyline class="xy-gt" points="{gt_xy_pts}"/>' if has_gt else ''}
      <polyline class="xy-est" points="{est_xy_pts}"/>
      {"".join(dropout_xy_polylines)}
      {blind_xy_svg}
      {floor_xy_svg}
      <circle cx="{start_est_x:.1f}" cy="{start_est_y:.1f}" r="4" fill="var(--gt)"/>
      <rect x="{end_est_x - 3.5:.1f}" y="{end_est_y - 3.5:.1f}" width="7" height="7" fill="var(--blind)"/>
      <line id="xy-err-vec" x1="0" y1="0" x2="0" y2="0" stroke="var(--blind)" stroke-width="1.4" stroke-dasharray="3 3" visibility="hidden"/>
      <circle id="xy-marker-gt" cx="{start_est_x:.1f}" cy="{start_est_y:.1f}" r="5" fill="var(--gt)" stroke="#fff" stroke-width="1.5" visibility="{'visible' if has_gt else 'hidden'}"/>
      <circle id="xy-marker-est" cx="{start_est_x:.1f}" cy="{start_est_y:.1f}" r="6" fill="var(--est)" stroke="#fff" stroke-width="1.8"/>
    </svg>
  </section>

  <div style="display:flex;flex-direction:column;gap:12px;">
    <section class="panel" aria-label="Height over time">
      <div class="panel-head">
        <div class="panel-title">Height z(t) Over Time</div>
        <div class="legend">
          <span><i class="swatch" style="background:var(--gt)"></i>GT z</span>
          <span><i class="swatch" style="background:var(--est)"></i>Vortex z</span>
          <span><i class="swatch" style="background:var(--floor)"></i>Floor z</span>
        </div>
      </div>
      <svg id="svg-z" viewBox="0 0 {W_TS} {H_Z}" role="img" aria-label="Height over time plot">
        {"".join(z_drop_rects)}
        {z_blind_svg}
        {"".join(z_grid)}
        <rect x="{PAD_L}" y="{PAD_T}" width="{pw_ts}" height="{ph_z}" fill="none" stroke="var(--border)"/>
        {floor_z_svg}
        {f'<polyline class="z-gt" points="{gt_z_pts}"/>' if has_gt else ''}
        <polyline class="z-est" points="{est_z_pts}"/>
        <line id="z-cursor" class="cursor-line" x1="{PAD_L}" y1="{PAD_T}" x2="{PAD_L}" y2="{PAD_T + ph_z}"/>
        <circle id="z-marker-gt" cx="{PAD_L}" cy="{PAD_T}" r="4" fill="var(--gt)" visibility="{'visible' if has_gt else 'hidden'}"/>
        <circle id="z-marker-est" cx="{PAD_L}" cy="{PAD_T}" r="4.5" fill="var(--est)"/>
      </svg>
    </section>

    <section class="panel" aria-label="Position error and fault timeline">
      <div class="panel-head">
        <div class="panel-title">Position Error ‖p_est(t) − p_gt(t)‖ &amp; Fault Timeline (Severity Ramp γ={gamma:.1f})</div>
        <div class="legend">
          <span><i class="swatch" style="background:var(--est)"></i>Vortex error</span>
          <span><i class="swatch" style="background:var(--floor)"></i>Floor error</span>
          <span><i class="swatch" style="background:var(--gt);height:6px"></i>Protected 2 s</span>
          <span><i class="swatch" style="background:var(--dropout);height:6px"></i>Missing-row burst</span>
          <span><i class="swatch" style="background:var(--spike);height:6px"></i>Spike</span>
          <span><i class="swatch" style="background:var(--stuck);height:6px"></i>Stuck run</span>
          <span><i class="swatch" style="background:var(--blind);height:6px"></i>Zero tail (blind 5 s)</span>
        </div>
      </div>
      <svg id="svg-err" viewBox="0 0 {W_TS} {H_ERR_TOTAL}" role="img" aria-label="Position error and fault timeline plot">
        {"".join(err_drop_rects)}
        {err_blind_svg}
        {"".join(err_grid)}
        <rect x="{PAD_L}" y="{ERR_TOP}" width="{pw_ts}" height="{ERR_H}" fill="none" stroke="var(--border)"/>
        {f'<polyline class="err-floor" points="{floor_err_pts}"/>' if (has_gt and summary["show_floor"]) else ''}
        {f'<polyline class="err-est" points="{err_pts}"/>' if has_gt else no_gt_banner}
        <text class="tick" x="{PAD_L - 6}" y="{TL_TOP + 15}" text-anchor="end">Faults</text>
        <text class="tick" x="{PAD_L - 6}" y="{TL_TOP + 42}" text-anchor="end">Ramp</text>
        {"".join(ramp_rects)}
        {prot_svg}
        {"".join(tl_drop_rects)}
        {"".join(spike_ticks)}
        {"".join(stuck_ticks)}
        {tl_blind_svg}
        <polyline class="tl-ramp-curve" points="{ramp_curve_pts}"/>
        <rect x="{PAD_L}" y="{TL_TOP}" width="{pw_ts}" height="{TL_H}" fill="none" stroke="var(--border)"/>
        <line id="err-cursor" class="cursor-line" x1="{PAD_L}" y1="{ERR_TOP}" x2="{PAD_L}" y2="{TL_TOP + TL_H}"/>
        <circle id="err-marker" cx="{PAD_L}" cy="{ERR_TOP + ERR_H}" r="4.5" fill="var(--est)" visibility="{'visible' if has_gt else 'hidden'}"/>
      </svg>
    </section>
  </div>
</main>

<script id="replay-metrics" type="application/json">{json.dumps(summary)}</script>
<script id="replay-data" type="application/json">{json.dumps(js_payload)}</script>
<script>
(function() {{
  const D = JSON.parse(document.getElementById("replay-data").textContent);
  const slider = document.getElementById("time-slider");
  const btnPlay = document.getElementById("btn-play");
  const readout = document.getElementById("live-readout");
  const xyEst = document.getElementById("xy-marker-est");
  const xyGt = document.getElementById("xy-marker-gt");
  const xyVec = document.getElementById("xy-err-vec");
  const zCursor = document.getElementById("z-cursor");
  const zEst = document.getElementById("z-marker-est");
  const zGt = document.getElementById("z-marker-gt");
  const errCursor = document.getElementById("err-cursor");
  const errMarker = document.getElementById("err-marker");

  function bisect(arr, t) {{
    let lo = 0, hi = arr.length - 1;
    if (hi <= 0) return 0;
    while (lo < hi) {{
      const mid = (lo + hi) >> 1;
      if (arr[mid] < t) lo = mid + 1;
      else hi = mid;
    }}
    if (lo > 0 && Math.abs(arr[lo - 1] - t) <= Math.abs(arr[lo] - t)) return lo - 1;
    return lo;
  }}

  function mapXY(x, y) {{
    const [x0, x1, y0, y1, pad, W, H] = D.bounds.xy;
    const px = pad + ((x - x0) / (x1 - x0)) * (W - 2 * pad);
    const py = H - pad - ((y - y0) / (y1 - y0)) * (H - 2 * pad);
    return [px, py];
  }}

  function mapT(t) {{
    const [, , padL, pw] = D.bounds.z;
    const c = Math.max(0, Math.min(1, t / Math.max(D.duration_s, 1e-3)));
    return padL + c * pw;
  }}

  function mapZ(z) {{
    const [z0, z1, , , padT, ph] = D.bounds.z;
    return padT + ph - ((z - z0) / (z1 - z0)) * ph;
  }}

  function mapErr(e) {{
    const [, e1, , , top, h] = D.bounds.err;
    const c = Math.max(0, Math.min(1, e / Math.max(e1, 1e-6)));
    return top + h - c * h;
  }}

  function phaseAt(t) {{
    const F = D.faults;
    if (F.failure_at_s !== null && t >= F.failure_at_s) return "blind 5 s (zero tail)";
    for (let i = 0; i < F.dropouts_s.length; i++) {{
      if (t >= F.dropouts_s[i][0] && t <= F.dropouts_s[i][1]) return "dropout burst #" + (i + 1);
    }}
    if (t <= F.healthy_end_s) return "protected opening";
    return "degraded stretch";
  }}

  function updateAt(t) {{
    t = Math.max(0, Math.min(D.duration_s, Number(t) || 0));
    slider.value = t.toFixed(3);
    const tx = mapT(t);
    zCursor.setAttribute("x1", tx.toFixed(1));
    zCursor.setAttribute("x2", tx.toFixed(1));
    errCursor.setAttribute("x1", tx.toFixed(1));
    errCursor.setAttribute("x2", tx.toFixed(1));

    let ex = 0, ey = 0, ez = 0;
    if (D.est.t.length > 0) {{
      const ie = bisect(D.est.t, t);
      ex = D.est.x[ie]; ey = D.est.y[ie]; ez = D.est.z[ie];
      const [px, py] = mapXY(ex, ey);
      xyEst.setAttribute("cx", px.toFixed(1));
      xyEst.setAttribute("cy", py.toFixed(1));
      zEst.setAttribute("cx", tx.toFixed(1));
      zEst.setAttribute("cy", mapZ(ez).toFixed(1));

      if (D.has_gt && D.gt.t.length > 0) {{
        const ig = bisect(D.gt.t, t);
        const gx = D.gt.x[ig], gy = D.gt.y[ig], gz = D.gt.z[ig];
        const [gpx, gpy] = mapXY(gx, gy);
        xyGt.setAttribute("cx", gpx.toFixed(1));
        xyGt.setAttribute("cy", gpy.toFixed(1));
        xyVec.setAttribute("x1", px.toFixed(1));
        xyVec.setAttribute("y1", py.toFixed(1));
        xyVec.setAttribute("x2", gpx.toFixed(1));
        xyVec.setAttribute("y2", gpy.toFixed(1));
        xyVec.setAttribute("visibility", "visible");
        zGt.setAttribute("cx", tx.toFixed(1));
        zGt.setAttribute("cy", mapZ(gz).toFixed(1));
      }}
    }}

    let errTxt = "";
    if (D.has_gt && D.err.t.length > 0) {{
      const ir = bisect(D.err.t, t);
      const ev = D.err.v[ir];
      errMarker.setAttribute("cx", tx.toFixed(1));
      errMarker.setAttribute("cy", mapErr(ev).toFixed(1));
      errTxt = " · ‖e‖ = " + ev.toFixed(3) + " m";
    }}

    const sev = D.faults.sev_floor + (D.faults.max_level - D.faults.sev_floor) * Math.pow(t / Math.max(D.duration_s, 1e-3), D.faults.gamma);
    readout.textContent =
      "t = " + t.toFixed(2) + " s · " + phaseAt(t) +
      " · sev = " + sev.toFixed(2) +
      " · est (" + ex.toFixed(2) + ", " + ey.toFixed(2) + ", " + ez.toFixed(2) + ") m" + errTxt;
  }}

  slider.addEventListener("input", () => updateAt(parseFloat(slider.value)));
  document.getElementById("btn-start").addEventListener("click", () => updateAt(0));
  document.getElementById("btn-drop").addEventListener("click", () => updateAt({first_drop_s:.4f}));
  document.getElementById("btn-blind").addEventListener("click", () => updateAt({blind_start_s:.4f}));
  document.getElementById("btn-end").addEventListener("click", () => updateAt(D.duration_s));

  let playing = false, lastTs = null;
  function tick(ts) {{
    if (!playing) return;
    if (lastTs !== null) {{
      const dt = (ts - lastTs) / 1000.0;
      let next = parseFloat(slider.value) + dt * 4.0;
      if (next >= D.duration_s) {{
        next = D.duration_s;
        playing = false;
        btnPlay.textContent = "Play";
      }}
      updateAt(next);
    }}
    lastTs = ts;
    if (playing) requestAnimationFrame(tick);
  }}
  btnPlay.addEventListener("click", () => {{
    playing = !playing;
    btnPlay.textContent = playing ? "Pause" : "Play";
    lastTs = null;
    if (playing) {{
      if (parseFloat(slider.value) >= D.duration_s - 0.05) updateAt(0);
      requestAnimationFrame(tick);
    }}
  }});

  document.getElementById("btn-theme").addEventListener("click", () => {{
    const cur = document.documentElement.getAttribute("data-theme");
    document.documentElement.setAttribute("data-theme", cur === "light" ? "dark" : "light");
  }});

  window.addEventListener("keydown", (ev) => {{
    if (ev.target && (ev.target.tagName === "INPUT" || ev.target.tagName === "BUTTON")) return;
    if (ev.key === "ArrowRight") {{
      ev.preventDefault();
      updateAt(parseFloat(slider.value) + (ev.shiftKey ? 2.0 : 0.25));
    }} else if (ev.key === "ArrowLeft") {{
      ev.preventDefault();
      updateAt(parseFloat(slider.value) - (ev.shiftKey ? 2.0 : 0.25));
    }} else if (ev.key === "Home") {{
      ev.preventDefault();
      updateAt(0);
    }} else if (ev.key === "End") {{
      ev.preventDefault();
      updateAt(D.duration_s);
    }} else if (ev.key === " ") {{
      ev.preventDefault();
      btnPlay.click();
    }}
  }});

  updateAt(0);
}})();
</script>
</body>
</html>
"""
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("imu", help="Input IMU.csv path")
    ap.add_argument("est", help="Estimated trajectory TUM .txt path")
    ap.add_argument("--gt", help="Ground truth sequence folder, CSV, or TUM .txt")
    ap.add_argument("--events", help="degrade.json path (phase windows)")
    ap.add_argument("--floor", action="store_true", help="Include the never-moving floor baseline")
    ap.add_argument("-o", "--out", required=True, help="Output self-contained HTML path")
    a = ap.parse_args(argv)

    html_text, summary = build_replay(a.imu, a.est, gt_path=a.gt, events_path=a.events, show_floor=a.floor)
    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_text, encoding="utf-8", newline="\n")
    print(
        f"wrote {out_path} ({out_path.stat().st_size} bytes) | seq={summary['sequence']} "
        f"reading={summary['reading']} seed={summary['seed']} APE={_fmt_num(summary['estimator']['ape_se3_rmse'], 4)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

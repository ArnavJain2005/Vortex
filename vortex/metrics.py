"""Trajectory error metrics.

Implemented here (not imported from evo, which is GPL-3) so the repo stays MIT. Trajectories can also
be exported in TUM format and checked with evo as an independent cross-check (see trajectory_io).

Definitions:
- ATE: after rigid alignment (rotation + translation, no scale), RMSE of position error at
  ground-truth timestamps. Alignment can use the whole run ("full", the common convention) or only an
  early window ("prefix"), which does not let alignment hide drift that appears later, or a transform
  supplied by the caller ("given"), e.g. one estimated once from the undegraded pose stream and then
  reused for every degraded run, so a fault can never be partly absorbed by alignment.
- RPE (translational): RMSE over time of the error in displacement across a fixed time step, computed
  in the aligned world frame. Simpler than evo's body-frame RPE, so values are not directly comparable.
- Final error and drift per metre: position error at the last common timestamp, divided by ground-truth
  path length.
"""

from __future__ import annotations

import numpy as np

from .types import Trajectory


def umeyama(src: np.ndarray, dst: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rigid R, t minimising ||dst - (R src + t)|| (Umeyama 1991, no scale)."""
    mu_s, mu_d = src.mean(axis=0), dst.mean(axis=0)
    cov = (dst - mu_d).T @ (src - mu_s) / len(src)
    U, _, Vt = np.linalg.svd(cov)
    S = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[2, 2] = -1.0
    R = U @ S @ Vt
    return R, mu_d - R @ mu_s


def associate(est: Trajectory, gt: Trajectory) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Estimated positions interpolated at the ground-truth timestamps both trajectories cover."""
    m = (gt.t >= est.t[0]) & (gt.t <= est.t[-1])
    t = gt.t[m]
    if len(t) < 3:
        raise ValueError("trajectories overlap in fewer than 3 ground-truth samples")
    p_est = np.column_stack([np.interp(t, est.t, est.p[:, i]) for i in range(3)])
    return t, p_est, gt.p[m]


def evaluate(
    est: Trajectory,
    gt: Trajectory,
    align: str = "full",
    prefix_s: float = 10.0,
    rpe_delta_s: float = 1.0,
    transform: tuple[np.ndarray, np.ndarray] | None = None,
) -> dict:
    """Score one estimated trajectory. align: "full", "prefix", "given" (needs transform) or "none"."""
    t, p_est, p_gt = associate(est, gt)

    if align == "none":
        R, tr = np.eye(3), np.zeros(3)
    elif align == "full":
        R, tr = umeyama(p_est, p_gt)
    elif align == "given":
        if transform is None:
            raise ValueError("align='given' needs transform=(R, t)")
        R, tr = np.asarray(transform[0], dtype=float), np.asarray(transform[1], dtype=float)
    elif align == "prefix":
        m = t <= t[0] + prefix_s
        if m.sum() < 3:
            raise ValueError("prefix window holds fewer than 3 samples")
        R, tr = umeyama(p_est[m], p_gt[m])
    else:
        raise ValueError("align must be 'full', 'prefix', 'given' or 'none'")

    p_al = p_est @ R.T + tr
    err = np.linalg.norm(p_al - p_gt, axis=1)
    path = float(np.sum(np.linalg.norm(np.diff(p_gt, axis=0), axis=1)))

    j = np.searchsorted(t, t + rpe_delta_s)
    ok = j < len(t)
    if ok.any():
        d_est = p_al[j[ok]] - p_al[ok]
        d_gt = p_gt[j[ok]] - p_gt[ok]
        rpe = float(np.sqrt(np.mean(np.sum((d_est - d_gt) ** 2, axis=1))))
    else:
        rpe = float("nan")

    final = float(err[-1])
    return {
        "name": est.name,
        "align": align,
        "n": int(len(t)),
        "duration_s": float(t[-1] - t[0]),
        "ate_rmse_m": float(np.sqrt(np.mean(err**2))),
        "ate_median_m": float(np.median(err)),
        "ate_max_m": float(err.max()),
        "rpe_rmse_m": rpe,
        "rpe_delta_s": rpe_delta_s,
        "final_error_m": final,
        "gt_path_length_m": path,
        "drift_per_m": final / path if path > 0 else float("nan"),
        "time_to_1m_s": _time_to_exceed(t, err, 1.0),
        "_t": t,
        "_err": err,
        "_p_aligned": p_al,
    }


def alignment_transform(est: Trajectory, gt: Trajectory) -> tuple[np.ndarray, np.ndarray]:
    """Rigid transform taking est's frame to gt's frame, fitted over their whole overlap."""
    _, p_est, p_gt = associate(est, gt)
    return umeyama(p_est, p_gt)


def _time_to_exceed(t: np.ndarray, err: np.ndarray, threshold: float) -> float | None:
    """Seconds from the start until error first exceeds threshold; None if it never does."""
    over = np.nonzero(err > threshold)[0]
    return float(t[over[0]] - t[0]) if len(over) else None


def public(result: dict) -> dict:
    """Drop the per-sample arrays (keys starting with '_') for JSON output."""
    return {k: v for k, v in result.items() if not k.startswith("_")}

"""Track 3 scoring, evo-style: ATE (APE, translation part) and RPE against ground truth, split by phase.

The organisers score with evo (ATE RMSE, RPE). This module re-implements the same definitions from their
published maths so the repo stays MIT (evo is GPL-3; none of its code is copied). `tools/crosscheck_evo.py`
compares the numbers against a pip-installed evo.

Definitions (matching evo's defaults as we understand them; the cross-check is the evidence):
  association  each pose of the SHORTER trajectory is matched to the nearest timestamp of the longer one,
               kept if |dt| <= max_diff (evo default 0.01 s)
  alignment    none | origin (first matched pose of est moved onto gt's, full SE3) |
               se3 (Umeyama, rotation + translation, evo -a) | sim3 (+ scale, evo -as) |
               given (a transform fitted once on the UNDEGRADED run, so it cannot absorb a fault);
               n_to_align: fit on the first n matched poses only (evo --n_to_align)
  APE          ||p_gt_i - p_est_i|| after alignment (evo pose_relation translation_part)
  RPE          translation part of inv(Q_i^-1 Q_j) (P_i^-1 P_j), Q = gt, P = est, pairs (i, i+delta) in
               matched frames; all_pairs=False uses non-overlapping consecutive pairs (evo default),
               delta=1 frame is evo's default
Phases (needs the degrade.json events; times relative to its t0_ns): healthy opening, each dropout
window, the degraded stretch, and the blind window after total failure. Per phase: RMSE, mean, max,
error at start and end, and growth = |error vector at end - error vector at start| (drift accumulated
inside the window, independent of error carried in).
Waypoint proxies: error at every `waypoint_every_s` seconds. PROXY ONLY: the organisers' waypoint
definition is unknown (open question Q3).

Estimate files that break the contract (duplicate or unsorted timestamps, non-finite rows) are sorted,
de-duplicated (first kept) and filtered before scoring, and the counts are reported.

CLI: python score.py --gt SEQ_DIR|GT.csv|GT_TUM.txt --est est.txt [--events degrade.json]
     [--imu IMU.csv] [--align se3] [--given-from clean_est.txt] [--n-to-align N] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .geometry import matrix_to_quat, quat_to_matrix

ALIGN_MODES = ("none", "origin", "se3", "sim3")


@dataclass
class Traj:
    """t: (N,) seconds, sorted; p: (N, 3) metres; R: (N, 3, 3) body-to-world rotations."""

    t: np.ndarray
    p: np.ndarray
    R: np.ndarray

    def take(self, idx) -> "Traj":
        return Traj(self.t[idx], self.p[idx], self.R[idx])


def matrices_to_quat_xyzw(R: np.ndarray) -> np.ndarray:
    q = np.array([matrix_to_quat(r) for r in R])   # (w, x, y, z)
    return q[:, [1, 2, 3, 0]]


def _clean(t, p, q_wxyz):
    info = {"rows": int(len(t))}
    ok = np.isfinite(t) & np.all(np.isfinite(p), axis=1) & np.all(np.isfinite(q_wxyz), axis=1)
    ok &= np.linalg.norm(q_wxyz, axis=1) > 0
    info["non_finite_dropped"] = int(np.sum(~ok))
    t, p, q_wxyz = t[ok], p[ok], q_wxyz[ok]
    order = np.argsort(t, kind="stable")
    info["was_unsorted"] = bool(np.any(order != np.arange(len(t))))
    t, p, q_wxyz = t[order], p[order], q_wxyz[order]
    keep = np.concatenate([[True], np.diff(t) > 0]) if len(t) else np.zeros(0, bool)
    info["duplicates_dropped"] = int(np.sum(~keep))
    return Traj(t[keep], p[keep], quat_to_matrix(q_wxyz[keep])), info


def read_tum(path) -> tuple[Traj, dict]:
    """TUM `t tx ty tz qx qy qz qw`; '#' lines ignored."""
    a = np.loadtxt(path, comments="#", ndmin=2)
    if a.shape[1] != 8:
        raise ValueError("%s: expected 8 columns, got %d" % (path, a.shape[1]))
    return _clean(a[:, 0], a[:, 1:4], a[:, [7, 4, 5, 6]])


def read_ground_truth(path) -> Traj:
    """A TUM .txt, an EuRoC/TUM-VI ground-truth csv, or a sequence folder. SCORING ONLY."""
    path = Path(path)
    if path.is_file() and path.suffix == ".txt":
        return read_tum(path)[0]
    from .data import euroc
    gt = euroc.load_ground_truth(path) if path.is_dir() else euroc.read_ground_truth_csv(path)
    return _clean(gt.t, gt.p, gt.q)[0]


# ---------------------------------------------------------------- association and alignment

def associate(ref: Traj, est: Traj, max_diff: float = 0.01) -> tuple[Traj, Traj]:
    est_longer = len(est.t) > len(ref.t)
    short, long_ = (ref, est) if est_longer else (est, ref)
    j = np.clip(np.searchsorted(long_.t, short.t), 1, len(long_.t) - 1)
    left_closer = np.abs(short.t - long_.t[j - 1]) <= np.abs(long_.t[j] - short.t)
    j = np.where(left_closer, j - 1, j)
    ok = np.abs(long_.t[j] - short.t) <= max_diff
    if ok.sum() < 3:
        raise ValueError("fewer than 3 poses matched within %.3f s" % max_diff)
    i = np.flatnonzero(ok)
    s, l = short.take(i), long_.take(j[ok])
    return (s, l) if est_longer else (l, s)


def _umeyama(x: np.ndarray, y: np.ndarray, with_scale: bool):
    """R, t, c minimising sum ||y_i - (c R x_i + t)||^2 (Umeyama 1991). x, y: (n, 3)."""
    mx, my = x.mean(axis=0), y.mean(axis=0)
    xc, yc = x - mx, y - my
    cov = yc.T @ xc / len(x)
    U, d, Vt = np.linalg.svd(cov)
    S = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[2, 2] = -1.0
    R = U @ S @ Vt
    c = float(np.trace(np.diag(d) @ S) / (np.sum(xc ** 2) / len(x))) if with_scale else 1.0
    return R, my - c * R @ mx, c


def _fit(ref_s: Traj, est_s: Traj, mode: str, n_to_align: int = -1) -> dict:
    n = len(ref_s.t) if n_to_align is None or n_to_align < 0 else min(n_to_align, len(ref_s.t))
    if mode == "none":
        R, t, c = np.eye(3), np.zeros(3), 1.0
    elif mode == "origin":
        R = ref_s.R[0] @ est_s.R[0].T
        t, c = ref_s.p[0] - R @ est_s.p[0], 1.0
    elif mode in ("se3", "sim3"):
        if n < 3:
            raise ValueError("n_to_align must be >= 3")
        R, t, c = _umeyama(est_s.p[:n], ref_s.p[:n], mode == "sim3")
    else:
        raise ValueError("align must be one of %s or 'given'" % (ALIGN_MODES,))
    return {"mode": mode, "R": R, "t": t, "scale": c, "n_to_align": int(n)}


def fit_alignment(ref: Traj, est: Traj, mode: str = "se3", n_to_align: int = -1, max_diff: float = 0.01) -> dict:
    """Fit once (e.g. on the undegraded run) and pass to score(..., align='given', given=...)."""
    r, e = associate(ref, est, max_diff)
    return _fit(r, e, mode, n_to_align)


def apply(tr: Traj, al: dict) -> Traj:
    R, t, c = np.asarray(al["R"]), np.asarray(al["t"]), al["scale"]
    return Traj(tr.t, c * tr.p @ R.T + t, R @ tr.R)


# ---------------------------------------------------------------- metrics

def stats(e: np.ndarray) -> dict:
    e = np.asarray(e, dtype=float)
    if len(e) == 0:
        return {"n": 0}
    return {"n": int(len(e)), "rmse": float(np.sqrt(np.mean(e ** 2))), "mean": float(np.mean(e)),
            "median": float(np.median(e)), "std": float(np.std(e)), "min": float(np.min(e)),
            "max": float(np.max(e)), "sse": float(np.sum(e ** 2))}


def rpe(ref_s: Traj, est_s: Traj, delta: int = 1, all_pairs: bool = False) -> np.ndarray:
    """Translation-part RPE on already-associated trajectories (delta in frames)."""
    n = len(ref_s.t)
    if all_pairs:
        i = np.arange(0, n - delta)
        j = i + delta
    else:
        ids = np.arange(0, n, delta)
        i, j = ids[:-1], ids[1:]

    def rel_t(tr):
        return np.einsum("nji,nj->ni", tr.R[i], tr.p[j] - tr.p[i])   # R_i^T (p_j - p_i)

    # ||translation of inv(Q_rel) P_rel|| = ||R_Qrel^T (t_Prel - t_Qrel)|| = ||t_Prel - t_Qrel||
    return np.linalg.norm(rel_t(est_s) - rel_t(ref_s), axis=1)


def _window(rel, err, vec, a, b, inclusive_end=False):
    m = (rel >= a) & ((rel <= b) if inclusive_end else (rel < b))
    out = {"window_s": [float(a), float(b)]}
    if not m.any():
        out["n"] = 0
        return out
    e, v = err[m], vec[m]
    out.update(stats(e))
    out.update({"start_error": float(e[0]), "end_error": float(e[-1]),
                "growth": float(np.linalg.norm(v[-1] - v[0]))})
    return out


def phase_report(ref_s: Traj, est_al: Traj, events: dict) -> dict:
    t0 = events["t0_ns"] / 1e9
    rel = ref_s.t - t0
    vec = est_al.p - ref_s.p
    err = np.linalg.norm(vec, axis=1)
    fail = events.get("failure_at_s")
    end = events.get("end_s", float(rel[-1]))
    out = {"healthy": _window(rel, err, vec, 0.0, events.get("healthy_end_s", 0.0)),
           "dropouts": [_window(rel, err, vec, s, e) for s, e in events.get("dropouts_s", [])]}
    if fail is not None:
        out["degraded"] = _window(rel, err, vec, events.get("healthy_end_s", 0.0), fail)
        out["blind"] = _window(rel, err, vec, fail, end, inclusive_end=True)
    return out


def waypoints_proxy(ref_s: Traj, est_al: Traj, t0: float, every_s: float, max_diff: float) -> dict:
    rel = ref_s.t - t0
    err = np.linalg.norm(est_al.p - ref_s.p, axis=1)
    k_max = int(np.floor((rel[-1]) / every_s + 1e-6))
    pts = []
    for k in range(0, k_max + 1):
        tw = k * every_s
        if tw < rel[0] - max_diff:
            continue
        i = int(np.argmin(np.abs(rel - tw)))
        if abs(rel[i] - tw) <= max_diff:
            pts.append({"t_rel_s": float(tw), "error": float(err[i])})
    e = np.array([p["error"] for p in pts])
    return {"note": "PROXY: organisers' waypoint definition unknown (Q3)", "every_s": every_s,
            "points": pts, **({k: v for k, v in stats(e).items() if k in ("n", "rmse", "mean", "max")})}


def score(ref: Traj, est: Traj, align: str = "se3", n_to_align: int = -1, given: dict | None = None,
          max_diff: float = 0.01, rpe_deltas=(1, 200), events: dict | None = None,
          waypoint_every_s: float = 10.0) -> dict:
    ref_s, est_s = associate(ref, est, max_diff)
    al = given if align == "given" else _fit(ref_s, est_s, align, n_to_align)
    if al is None:
        raise ValueError("align='given' needs given=fit_alignment(...)")
    est_al = apply(est_s, al)
    err = np.linalg.norm(est_al.p - ref_s.p, axis=1)
    out = {
        "n_matched": int(len(ref_s.t)),
        "n_ref": int(len(ref.t)),
        "n_est": int(len(est.t)),
        "alignment": {"mode": align if align != "given" else "given(%s)" % al["mode"],
                      "scale": float(al["scale"]), "R": np.asarray(al["R"]).tolist(),
                      "t": np.asarray(al["t"]).tolist(), "n_to_align": al.get("n_to_align")},
        "ape": stats(err),
        "rpe": {str(d): stats(rpe(ref_s, est_al, d)) for d in rpe_deltas},
        "final_error": float(err[-1]),
    }
    t0 = events["t0_ns"] / 1e9 if events else float(ref_s.t[0])
    out["waypoints_proxy"] = waypoints_proxy(ref_s, est_al, t0, waypoint_every_s, max_diff)
    if events:
        out["phases"] = phase_report(ref_s, est_al, events)
    return out


# ---------------------------------------------------------------- CLI

def _fmt(x):
    return "-" if x is None else "%.4f" % x


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python score.py", description="Track 3 scoring (evo-style ATE/RPE)")
    ap.add_argument("--gt", required=True, help="sequence folder, ground-truth csv, or TUM .txt")
    ap.add_argument("--est", required=True, help="estimated_trajectory.txt")
    ap.add_argument("--events", help="degrade.json (phase windows)")
    ap.add_argument("--imu", help="the IMU csv main.py read: also run the output contract checker")
    ap.add_argument("--align", default="se3", choices=list(ALIGN_MODES) + ["given"])
    ap.add_argument("--given-from", help="estimate on the UNDEGRADED run; with --align given")
    ap.add_argument("--given-mode", default="se3", choices=["origin", "se3", "sim3"])
    ap.add_argument("--n-to-align", type=int, default=-1)
    ap.add_argument("--max-diff", type=float, default=0.01)
    ap.add_argument("--waypoint-every", type=float, default=10.0)
    ap.add_argument("--json")
    a = ap.parse_args(argv)

    ref = read_ground_truth(a.gt)
    est, info = read_tum(a.est)
    events = json.loads(Path(a.events).read_text()) if a.events else None
    given = None
    if a.align == "given":
        if not a.given_from:
            ap.error("--align given needs --given-from")
        given = fit_alignment(ref, read_tum(a.given_from)[0], a.given_mode, a.n_to_align, a.max_diff)

    res = score(ref, est, a.align, a.n_to_align, given, a.max_diff, events=events,
                waypoint_every_s=a.waypoint_every)
    res["est_file"] = info
    res["ape_by_alignment"] = {m: score(ref, est, m, a.n_to_align, max_diff=a.max_diff, rpe_deltas=(1,))["ape"]
                               for m in ALIGN_MODES}
    if a.imu:
        from . import check_output
        c = check_output.check(a.imu, a.est)
        res["contract"] = {"ok": c["ok"], "input_rows": c["input_rows"], "output_rows": c["output_rows"],
                           "error_counts": c["error_counts"]}

    print("matched %d of %d est / %d gt poses; est file: %s" % (res["n_matched"], res["n_est"], res["n_ref"], info))
    print("ATE RMSE by alignment:  " + "  ".join("%s %s m" % (m, _fmt(s["rmse"]))
                                                for m, s in res["ape_by_alignment"].items()))
    print("ATE (%s): rmse %s  mean %s  max %s  final %s m"
          % (res["alignment"]["mode"], _fmt(res["ape"]["rmse"]), _fmt(res["ape"]["mean"]),
             _fmt(res["ape"]["max"]), _fmt(res["final_error"])))
    for d, s in res["rpe"].items():
        print("RPE delta %s frames: rmse %s m  (n %d)" % (d, _fmt(s.get("rmse")), s["n"]))
    w = res["waypoints_proxy"]
    print("waypoint proxy every %.0f s: rmse %s m over %d points (PROXY, Q3)" % (w["every_s"], _fmt(w.get("rmse")), w["n"]))
    for name, ph in (res.get("phases") or {}).items():
        for i, p in enumerate(ph if isinstance(ph, list) else [ph]):
            label = name if not isinstance(ph, list) else "%s[%d]" % (name, i)
            print("phase %-12s %5.1f-%5.1f s: rmse %s  end %s  growth %s m"
                  % (label, p["window_s"][0], p["window_s"][1], _fmt(p.get("rmse")),
                     _fmt(p.get("end_error")), _fmt(p.get("growth"))))
    if "contract" in res:
        print("output contract:", "PASS" if res["contract"]["ok"] else "FAIL %s" % res["contract"]["error_counts"])
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

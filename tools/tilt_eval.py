"""Step L2 diagnostic: roll/pitch (tilt) error against ground truth, by flight phase. OFFLINE (reads GT).

Tilt error of a row = angle between the world vertical seen in the body frame by the estimate and by the
ground truth (R^T e_z for each). It does not depend on yaw or on the world frames' yaw, so no alignment is
needed (both worlds are gravity-aligned: ours by calibration, EuRoC's Vicon / Leica frame by construction).

Phases from ground truth at each row: rest (speed < 0.05 m/s and |omega| < 0.05 rad/s), hover (speed
< 0.3 m/s), manoeuvre (the rest); plus `blind` (the official copies' last 5 s, from degrade.json) reported
apart and kept out of the three phases. Rows outside the ground-truth time span are skipped.

Usage:
  python tools/tilt_eval.py --tag NAME [--main main.py] [--set NAME=VALUE ...] [--seqs MH_01_easy_a_s1,...]
         [--clean MH_01_easy,...]
Writes Docs/tilt/<tag>.json and prints a table (mean over files of the per-file RMS tilt error, degrees).
Tuning sequences only (MH_01/02, TUM-VI room1/2) unless a pre-registered rule says otherwise; V2_* refused.
"""
import argparse
import json
import math
import os
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import eval_euroc  # noqa: E402

OUT = os.path.join(ROOT, "Docs", "tilt")
REST_V, REST_W, HOVER_V = 0.05, 0.05, 0.3
PHASES = ("rest", "hover", "manoeuvre", "blind", "all")


def zbody(q):
    """Rows of (w, x, y, z) body-to-world quaternions -> world z axis in body frame (third row of R)."""
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    return np.stack([2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)], axis=1)


def read_gt(seq_dir):
    path = os.path.join(seq_dir, "mav0", "state_groundtruth_estimate0", "data.csv")
    a = np.loadtxt(path, delimiter=",", comments="#")
    t = a[:, 0].astype(np.int64)
    return t, a[:, 4:8], a[:, 8:11]


def read_est(path):
    a = np.loadtxt(path)
    t = np.round(a[:, 0] * 1e9).astype(np.int64)
    q = np.stack([a[:, 7], a[:, 4], a[:, 5], a[:, 6]], axis=1)   # file: qx qy qz qw
    return t, q


def tilt_errors(gt_dir, est_path, blind=None):
    """Per-phase RMS tilt error (deg) and row count; blind = (t0_s, t1_s) in seconds or None."""
    tg, qg, vg = read_gt(gt_dir)
    te, qe = read_est(est_path)
    keep = (te >= tg[0]) & (te <= tg[-1])
    te, qe = te[keep], qe[keep]
    i = np.clip(np.searchsorted(tg, te), 1, len(tg) - 1)
    i -= (te - tg[i - 1]) < (tg[i] - te)
    zg, ze = zbody(qg[i]), zbody(qe)
    c = np.clip(np.sum(zg * ze, axis=1) / np.linalg.norm(zg, axis=1) / np.linalg.norm(ze, axis=1), -1, 1)
    err = np.degrees(np.arccos(c))
    speed = np.linalg.norm(vg[i], axis=1)
    dq = qg[np.minimum(i + 1, len(tg) - 1)] - qg[np.maximum(i - 1, 0)]
    dt = (tg[np.minimum(i + 1, len(tg) - 1)] - tg[np.maximum(i - 1, 0)]) * 1e-9
    omega = 2 * np.linalg.norm(dq, axis=1) / np.maximum(dt, 1e-9)
    inblind = np.zeros(len(te), bool)
    if blind is not None:
        inblind = (te * 1e-9 >= blind[0]) & (te * 1e-9 <= blind[1])
    masks = {"rest": (speed < REST_V) & (omega < REST_W) & ~inblind,
             "hover": (speed < HOVER_V) & ~((speed < REST_V) & (omega < REST_W)) & ~inblind,
             "manoeuvre": (speed >= HOVER_V) & ~inblind, "blind": inblind, "all": ~inblind}
    out = {}
    for k, m in masks.items():
        out[k] = {"n": int(m.sum()), "rms_deg": float(math.sqrt(np.mean(err[m] ** 2))) if m.any() else None}
    return out


def blind_window(seq_dir):
    """The blind window (absolute seconds) from degrade.json, or None (clean sequence)."""
    path = os.path.join(seq_dir, "degrade.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        ev = json.load(f)
    t0 = ev["t0_ns"] * 1e-9
    return (t0 + ev["failure_at_s"], t0 + ev["end_s"])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--main", default=os.path.join(ROOT, "main.py"))
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--seqs", default="")
    ap.add_argument("--clean", default="")
    args = ap.parse_args(argv)
    names = [s for s in args.seqs.split(",") if s]
    clean = [s for s in args.clean.split(",") if s]
    if any(n.startswith("V2_") for n in names + clean):
        sys.exit("V2_* is the final test set: refused")
    sets = [tuple(s.split("=", 1)) for s in args.set]
    res = []
    with tempfile.TemporaryDirectory() as tmp:
        main_path = eval_euroc.wrapper(os.path.abspath(args.main), sets, tmp) if sets else os.path.abspath(args.main)
        jobs = [(n, os.path.join(eval_euroc.OFFICIAL, n), eval_euroc.official_base(n)) for n in names]
        jobs += [(n, os.path.join(eval_euroc.DATA, n), (n, "clean", None)) for n in clean]
        for name, seq_dir, (base, reading, seed) in jobs:
            imu = os.path.join(seq_dir, "mav0", "imu0", "data.csv")
            est = os.path.join(tmp, name + ".txt")
            p, _ = eval_euroc.run_main(main_path, imu, est)
            if p.returncode != 0:
                res.append({"sequence": name, "error": p.stderr[-400:]})
                continue
            r = tilt_errors(os.path.join(eval_euroc.DATA, base), est, blind_window(seq_dir))
            res.append({"sequence": name, "base": base, "reading": reading, "seed": seed, "tilt": r})
            print(name, " ".join("%s %.2f" % (k, r[k]["rms_deg"]) for k in PHASES if r[k]["rms_deg"] is not None),
                  flush=True)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, args.tag + ".json"), "w", encoding="utf-8") as f:
        json.dump({"tag": args.tag, "main": os.path.relpath(args.main, ROOT), "set": args.set, "runs": res}, f,
                  indent=1)
    by = {}
    for r in res:
        if "tilt" in r:
            by.setdefault(r["reading"], []).append(r["tilt"])
    print("| reading | files | " + " | ".join(PHASES) + " |")
    for k, rs in sorted(by.items()):
        cells = []
        for ph in PHASES:
            xs = [x[ph]["rms_deg"] for x in rs if x[ph]["rms_deg"] is not None]
            cells.append("%.2f" % (sum(xs) / len(xs)) if xs else "-")
        print("| %s | %d | %s |" % (k, len(rs), " | ".join(cells)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

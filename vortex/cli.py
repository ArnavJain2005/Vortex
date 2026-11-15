"""Command line entry point.

    python -m vortex check --advio data/advio --seq 1
    python -m vortex baselines --advio data/advio --seq 1 [--blackout 60 5] [--out results]
    python -m vortex baselines --synthetic [--seed 0]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from . import baselines, metrics
from .data import advio, synthetic
from .trajectory_io import write_tum
from .types import Sequence


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vortex", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_source(p: argparse.ArgumentParser) -> None:
        g = p.add_mutually_exclusive_group(required=True)
        g.add_argument("--advio", type=Path, help="folder holding advio-NN/ sequence folders")
        g.add_argument("--synthetic", action="store_true", help="use the built-in synthetic sequence")
        p.add_argument("--seq", type=int, default=1, help="ADVIO sequence number (default 1)")
        p.add_argument("--pose-source", choices=["arkit", "arcore"], default="arkit")
        p.add_argument("--accel-sign", type=float, default=advio.ACCEL_SIGN, help="ADVIO accelerometer sign")
        p.add_argument("--seed", type=int, default=0, help="synthetic sequence seed")

    c = sub.add_parser("check", help="validate a sequence and test the accelerometer sign")
    add_source(c)

    b = sub.add_parser("baselines", help="score the naive baselines")
    add_source(b)
    b.add_argument(
        "--blackout",
        nargs=2,
        type=float,
        action="append",
        metavar=("START_S", "DURATION_S"),
        help="pose-stream outage, seconds from the start of the run (repeatable). "
        "Default: one 5 s outage starting 40%% of the way through.",
    )
    b.add_argument("--out", type=Path, default=Path("results"), help="output folder (default results/)")
    b.add_argument("--no-plot", action="store_true")

    args = ap.parse_args(argv)
    seq = _load(args)
    if args.cmd == "check":
        return _check(seq)
    return _baselines(seq, args)


def _load(args: argparse.Namespace) -> Sequence:
    if args.synthetic:
        # Phone-grade white noise: ADVIO's published iPhone noise densities (gyro 2.4e-3 rad/s/sqrt(Hz),
        # accel 4.8e-3 m/s^2/sqrt(Hz)) at the synthetic 200 Hz rate.
        rate = 200.0
        return synthetic.make_sequence(
            imu_rate=rate, gyro_noise=2.4e-3 * rate**0.5, accel_noise=4.8e-3 * rate**0.5, seed=args.seed
        )
    return advio.load_sequence(args.advio, args.seq, pose_source=args.pose_source, accel_sign=args.accel_sign)


def _rate(t: np.ndarray) -> float:
    return float(1.0 / np.median(np.diff(t)))


def _check(seq: Sequence) -> int:
    imu, pose, gt = seq.imu, seq.pose, seq.ground_truth
    print(f"sequence      {seq.name}")
    for label, t, n in [("imu", imu.t, len(imu.t)), ("pose", pose.t, len(pose)), ("ground_truth", gt.t, len(gt))]:
        print(f"{label:13s} {n:7d} samples  {t[0]:10.3f} .. {t[-1]:10.3f} s  ~{_rate(t):6.1f} Hz")
    print(f"gt path       {gt.path_length():.1f} m")
    acc_norm = np.linalg.norm(imu.accel, axis=1)
    print(f"|accel|       median {np.median(acc_norm):.3f} m/s^2 (expect about 9.8)")
    print(f"|gyro|        median {np.median(np.linalg.norm(imu.gyro, axis=1)):.3f} rad/s")
    if "dropped_non_increasing" in seq.meta:
        print(f"dropped rows  {seq.meta['dropped_non_increasing']}")
    sign = baselines.detect_accel_sign(seq)
    print(f"accel sign    median 2 s dead-reckoning error: {sign['median_end_error_m']}")
    if sign["better"] == "as_loaded":
        print("              OK: the loaded accelerometer sign fits ground truth better.")
    else:
        print("              WARNING: negated accelerometer fits better. Re-run with --accel-sign "
              f"{-seq.meta.get('accel_sign', 1.0):g} and report this.")
    return 0


def _baselines(seq: Sequence, args: argparse.Namespace) -> int:
    out = args.out / seq.name
    out.mkdir(parents=True, exist_ok=True)
    gt, pose = seq.ground_truth, seq.pose

    t0 = pose.t[0]
    duration = pose.t[-1] - t0
    windows = [[float(s), float(d)] for s, d in (args.blackout or [[round(0.4 * duration, 1), 5.0]])]
    windows_abs = [(t0 + s, d) for s, d in windows]
    available = baselines.mask_from_windows(pose.t, windows_abs)

    # The pose stream's frame differs from ground truth's; fit that transform once on the clean stream
    # and reuse it, so alignment cannot hide a fault.
    to_gt = metrics.alignment_transform(pose, gt)

    runs = {
        "pose_clean": (pose, "given"),
        "freeze_on_loss": (baselines.freeze_on_loss(pose, available), "given"),
        "dead_reckoning": (baselines.run_dead_reckoning(seq), "none"),
    }
    results = {}
    for name, (traj, align) in runs.items():
        traj.name = name
        r = metrics.evaluate(traj, gt, align=align, transform=to_gt if align == "given" else None)
        results[name] = r
        write_tum(traj, out / f"{name}.tum")
    write_tum(gt, out / "ground_truth.tum")

    summary = {
        "sequence": seq.name,
        "meta": {k: v for k, v in seq.meta.items() if k != "R_cam_imu"},
        "blackouts_s_from_start": [list(w) for w in windows],
        "results": {k: metrics.public(v) for k, v in results.items()},
    }
    (out / "baselines.json").write_text(json.dumps(summary, indent=2))

    print(f"{seq.name}: pose outage(s) (start, duration) {windows} s from run start; written to {out}")
    print("('first >1m' = seconds from run start until position error first exceeds 1 m)")
    print(f"{'run':16s} {'ATE rmse':>9s} {'final':>9s} {'drift/m':>8s} {'first >1m':>10s}")
    for name, r in results.items():
        t1 = "never" if r["time_to_1m_s"] is None else f"{r['time_to_1m_s']:.1f}s"
        print(f"{name:16s} {r['ate_rmse_m']:8.3f}m {r['final_error_m']:8.3f}m {r['drift_per_m']:8.3f} {t1:>10s}")

    if not args.no_plot:
        _plot(results, gt, windows_abs, out / "baselines.png", seq.name)
    return 0


def _plot(results: dict, gt, windows_abs, path: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))
    ax1.plot(gt.p[:, 0], gt.p[:, 1], "k-", lw=2, label="ground truth")
    for name, r in results.items():
        ax1.plot(r["_p_aligned"][:, 0], r["_p_aligned"][:, 1], lw=1, label=name)
    # Keep the view on the real path; dead reckoning usually leaves it within seconds.
    pad = 0.5 * np.ptp(gt.p[:, :2], axis=0).max() + 1.0
    ax1.set_xlim(gt.p[:, 0].min() - pad, gt.p[:, 0].max() + pad)
    ax1.set_ylim(gt.p[:, 1].min() - pad, gt.p[:, 1].max() + pad)
    ax1.set_aspect("equal")
    ax1.set_xlabel("x (m)")
    ax1.set_ylabel("y (m)")
    ax1.set_title(f"{title}: top view (ground-truth frame)")
    ax1.legend(fontsize=8)

    for name, r in results.items():
        ax2.semilogy(r["_t"] - gt.t[0], np.maximum(r["_err"], 1e-3), lw=1, label=name)
    for s, d in windows_abs:
        ax2.axvspan(s - gt.t[0], s + d - gt.t[0], color="red", alpha=0.15)
    ax2.set_xlabel("time (s)")
    ax2.set_ylabel("position error (m, log)")
    ax2.set_title("error over time (red: pose outage)")
    ax2.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())

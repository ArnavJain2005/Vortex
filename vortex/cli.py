"""Command line entry point.

    python -m vortex check --advio data/advio --seq 1
    python -m vortex baselines --advio data/advio --seq 1 [--blackout 60 5] [--out results]
    python -m vortex baselines --synthetic [--seed 0]
    python -m vortex check --phone data/phone/walk-01 [--checkpoints data/phone/checkpoints.csv]
    python -m vortex station [--source auto|phone|synthetic] [--seconds 60] [--save data/phone/live-01]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from . import baselines, metrics, stations
from .data import advio, phone, synthetic
from .trajectory_io import write_tum
from .types import Sequence


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vortex", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_source(p: argparse.ArgumentParser) -> None:
        g = p.add_mutually_exclusive_group(required=True)
        g.add_argument("--advio", type=Path, help="folder holding advio-NN/ sequence folders")
        g.add_argument("--synthetic", action="store_true", help="use the built-in synthetic sequence")
        g.add_argument("--phone", type=Path, help="unzipped Sensor Logger recording from the phone (S24)")
        p.add_argument("--seq", type=int, default=1, help="ADVIO sequence number (default 1)")
        p.add_argument("--pose-source", choices=["arkit", "arcore"], default="arkit")
        p.add_argument("--accel-sign", type=float, default=advio.ACCEL_SIGN, help="ADVIO accelerometer sign")
        p.add_argument("--seed", type=int, default=0, help="synthetic sequence seed")

    c = sub.add_parser("check", help="validate a sequence and test the accelerometer sign")
    add_source(c)
    c.add_argument("--checkpoints", type=Path, help="phone only: CSV of name,x,y,z floor checkpoints")

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

    st = sub.add_parser("station", help="run a live sensor station: the phone (S24) if connected, else synthetic")
    st.add_argument("--source", choices=["auto", "phone", "synthetic"], default="auto",
                    help="auto: wait for the phone, fall back to synthetic (default)")
    st.add_argument("--port", type=int, default=8000, help="HTTP port the phone pushes to (default 8000)")
    st.add_argument("--wait", type=float, default=30.0, help="seconds to wait for the phone (default 30)")
    st.add_argument("--seconds", type=float, default=0.0, help="stop after this long; 0 = until Ctrl+C")
    st.add_argument("--save", type=Path, help="save the stream in Sensor Logger layout to this folder")
    st.add_argument("--fast", action="store_true", help="synthetic only: do not pace in real time")

    args = ap.parse_args(argv)
    if args.cmd == "station":
        return _station(args)
    if args.phone is not None:
        if args.cmd != "check":
            ap.error("phone recordings have no ground-truth trajectory, so only 'check' works on them for now")
        return _check_phone(phone.load_sensor_logger(args.phone), args.checkpoints)
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


def _check_phone(rec: "phone.PhoneRecording", checkpoints_path: Path | None) -> int:
    imu, m = rec.imu, rec.meta
    print(f"recording     {rec.name}")
    print(f"device        {m.get('device name', m.get('deviceName', 'unknown'))}  platform {m.get('platform', '?')}")
    raw = m["raw_rate_hz"]
    print(f"imu           {len(imu.t)} samples over {imu.t[-1] - imu.t[0]:.1f} s, resampled to {m['resample_hz']:g} Hz "
          f"(raw gyro ~{raw['gyro']:.0f} Hz, accel ~{raw['accel']:.0f} Hz, from {m['accel_source']})")
    for label, s in [("magnetometer", rec.magnetometer), ("barometer", rec.barometer)]:
        if s is None:
            print(f"{label:13s} not recorded")
        else:
            print(f"{label:13s} {len(s.t)} samples  ~{_rate(s.t):.1f} Hz  columns {s.columns}")
    acc_norm = np.linalg.norm(imu.accel, axis=1)
    print(f"|accel|       median {np.median(acc_norm):.3f} m/s^2 (expect about 9.8)")
    spans = phone.still_windows(imu)
    if spans:
        s0, s1 = spans[0]
        sel = (imu.t >= s0) & (imu.t <= s1)
        bias = imu.gyro[sel].mean(axis=0)
        f_mean = imu.accel[sel].mean(axis=0)
        print(f"still         {len(spans)} still period(s); first {s0:.1f}-{s1:.1f} s")
        print(f"              gyro bias there {np.round(bias, 4)} rad/s; gravity reads {np.linalg.norm(f_mean):.3f} m/s^2")
    else:
        print("still         WARNING: no still period found. Hold the phone still for 3 s at the start and end.")
    print(f"annotations   {len(rec.annotations)}" + (": " + ", ".join(f"{a.text}@{a.t:.1f}s" for a in rec.annotations[:10])
                                                    if rec.annotations else ""))
    if checkpoints_path is not None:
        cps = phone.read_checkpoints(checkpoints_path)
        texts = {a.text for a in rec.annotations}
        missing = sorted(set(cps) - texts)
        unknown = sorted(texts - set(cps))
        print(f"checkpoints   {len(cps)} defined; matched {len(set(cps) & texts)}; "
              f"never annotated {missing or 'none'}; annotations with no checkpoint {unknown or 'none'}")
    ok = 9.3 < np.median(acc_norm) < 10.3 and bool(spans)
    print("              OK: recording looks usable." if ok else "              WARNING: see the lines above.")
    return 0


def _station(args: argparse.Namespace) -> int:
    station: stations.SensorStation | None = None
    if args.source in ("auto", "phone"):
        phone_st = stations.PhoneStation(port=args.port)
        phone_st.on_connect(lambda s: print(f"[station] phone connected: device {s.device}, session {s.session}"))
        phone_st.start()
        print(f"[station] phone station listening. In Sensor Logger: Settings > Data Streaming > HTTP Push,")
        print(f"          URL {phone_st.push_url()} , then start a recording. Phone and computer must share a network.")
        print(f"[station] waiting up to {args.wait:.0f} s for the phone...")
        if stations.wait_for_phone(phone_st, args.wait):
            station = phone_st
        else:
            phone_st.stop()
            if args.source == "phone":
                print("[station] no phone connected. Check the URL, the shared Wi-Fi, and 'Tap to Test Pushing'.")
                return 1
            print("[station] no phone connected; using the synthetic station.")
    if station is None:
        station = stations.SyntheticStation(duration=max(args.seconds, 60.0), realtime=not args.fast).start()
        print("[station] synthetic station running (walking sequence with exact ground truth).")

    samples: list[stations.ImuSample] = []
    was_connected = True
    t_start = time.monotonic()
    try:
        while True:
            time.sleep(0.05 if args.fast else 1.0)
            samples.extend(station.read())
            s = station.status()
            if s.source == "phone" and s.connected != was_connected:
                print("[station] phone reconnected" if s.connected else
                      f"[station] phone quiet for {station.quiet_after_s:g} s (disconnected or recording stopped)")
                was_connected = s.connected
            if samples and not args.fast:
                last = samples[-1]
                rate = f"{s.rate_hz:6.1f} Hz" if s.rate_hz else "   -   "
                print(f"[{s.source}] {'connected' if s.connected else 'quiet    '} {rate} samples {len(samples):7d}  "
                      f"|accel| {np.linalg.norm(last.accel):5.2f} m/s^2  |gyro| {np.linalg.norm(last.gyro):5.2f} rad/s")
            elapsed = time.monotonic() - t_start
            if (args.seconds and elapsed >= args.seconds) or (
                isinstance(station, stations.SyntheticStation) and station.finished and station._queue.empty()
            ):
                break
    except KeyboardInterrupt:
        print()
    finally:
        station.stop()
        samples.extend(station.read())

    s = station.status()
    print(f"[station] stopped: {len(samples)} samples from {s.source} ({s.device or 'no device'}); "
          f"sensors seen: {sorted(s.sensors_seen) or 'none'}")
    if args.save and len(samples) > 1:
        out = stations.save_as_sensor_logger(stations.samples_to_imu(samples), args.save, device=s.device or s.source)
        print(f"[station] saved to {out}. Check it with: python -m vortex check --phone {out}")
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

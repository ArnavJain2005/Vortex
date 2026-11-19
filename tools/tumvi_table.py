"""TUM-VI baseline table: shipped estimator against never-moving floor, clean and official seeds 1..3.

Patterned after tools/baseline_table.py (which belongs to Claude Code). Reads JSON results from
Docs/tumvi/ (written by tools/eval_euroc.py --root data/tumvi) and collects LAST + calibrated gyro
bias diagnostics vs BG_MAX = 0.15 rad/s; writes Docs/TUMVI_BASELINE.md. Never edit by hand.

    python tools/tumvi_table.py [--collect-calib]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
import pathfinder as pf  # noqa: E402
import tumvi_still_probe  # noqa: E402

TUMVI_DOCS = os.path.join(ROOT, "Docs", "tumvi")
TUMVI_DATA = os.path.join(ROOT, "data", "tumvi")
TUMVI_OFFICIAL = os.path.join(ROOT, "data", "official_tumvi")
TUNING_PREFIXES = ("dataset-room1", "dataset-room2")


def is_tuning(name: str) -> bool:
    return name.startswith(TUNING_PREFIXES)


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def fmt(x, d=2):
    return "-" if x is None else "%.*f" % (d, x)


def group(results, base, reading, seeds):
    return [r for r in results if "error" not in r and r["base"] == base
            and r["reading"] == reading and r["seed"] in seeds]


def _canonical_path(src: str, tmp_dir: str) -> str:
    """Replicate pathfinder.run's front-end rewrite (without mutating estimator settings) for _calibrate."""
    lines = None
    if pf.FRONT_ON:
        lay = pf._fe_detect(src)
        if not lay["canonical"]:
            lines = pf._fe_canonical_lines(src, lay)
    f = None
    if getattr(pf, "FF_STUCK6_ON", False) or getattr(pf, "FF_SPIKE_ON", False):  # fault pass: lab copy only since 18 Nov
        if lines is None:
            f = open(src, "rb")
            lines = f
        lines = pf._ff_filter_lines(lines)
    if lines is None:
        return src
    tmp_in = os.path.join(tmp_dir, "calib_in.csv")
    try:
        with open(tmp_in, "wb") as g:
            g.writelines(lines)
    finally:
        if f is not None:
            f.close()
    return tmp_in


def diagnose_imu(imu_path: str) -> dict:
    """Run pathfinder on one IMU CSV and inspect LAST, calibrated gyro bias, and BG_MAX gate."""
    with tempfile.TemporaryDirectory(prefix="vortex_tumvi_diag_") as tmp_dir:
        out_txt = os.path.join(tmp_dir, "est.txt")
        pf.run(imu_path, out_txt)
        last = dict(pf.LAST)
        canon = _canonical_path(imu_path, tmp_dir)
        cal = pf._calibrate(canon)
        uncapped_bg_norm = None
        if cal is not None:
            bg = [float(cal[5]), float(cal[6]), float(cal[7])]
            bg_norm = math.sqrt(sum(x * x for x in bg))
            cal_source = "still_run"
        else:
            init = pf._initialise(pf._init_window(canon))
            bg = [float(init[4]), float(init[5]), float(init[6])]
            bg_norm = math.sqrt(sum(x * x for x in bg))
            cal_source = "init_window_still" if init[8] else "fallback_zero"
            prev_cap = pf.BGCAP_ON
            pf.BGCAP_ON = False
            try:
                cal_uncapped = pf._calibrate(canon)
            finally:
                pf.BGCAP_ON = prev_cap
            if cal_uncapped is not None:
                ubg = cal_uncapped[5:8]
                uncapped_bg_norm = math.sqrt(sum(x * x for x in ubg))
        fe = last.get("frontend") or {}
        return {
            "calibrated": bool(last.get("calibrated")),
            "cal_source": cal_source,
            "pre_rows": int(last.get("pre_rows", 0)),
            "zupt_ticks": int(last.get("zupt_ticks", 0)),
            "bg": bg,
            "bg_norm_rad_s": bg_norm,
            "bg_max_rad_s": float(pf.BG_MAX),
            "exceeds_bg_max": bool(bg_norm > pf.BG_MAX),
            "uncapped_still_bg_norm_rad_s": uncapped_bg_norm,
            "frontend_order": fe.get("order"),
            "frontend_order_from": fe.get("order_from"),
            "frontend_canonical": fe.get("canonical"),
            "gyro_suspect": fe.get("gyro_suspect"),
        }


def collect_calib(clean_est: dict, off_est: dict, clean_root: str = TUMVI_DATA,
                  official_root: str = TUMVI_OFFICIAL) -> dict:
    """Collect LAST and gyro-bias diagnostics for every clean and official seed 1..3 run."""
    clean_diag = {}
    for r in clean_est["results"]:
        seq = r["sequence"]
        imu = os.path.join(clean_root, seq, "mav0", "imu0", "data.csv")
        if os.path.isfile(imu):
            clean_diag[seq] = diagnose_imu(imu)

    official_diag = {}
    for r in off_est["results"]:
        copy = r["sequence"]
        imu = os.path.join(official_root, copy, "mav0", "imu0", "data.csv")
        if os.path.isfile(imu):
            d = diagnose_imu(imu)
            d["base"] = r.get("base")
            d["reading"] = r.get("reading")
            d["seed"] = r.get("seed")
            official_diag[copy] = d

    return {
        "bg_max_rad_s": float(pf.BG_MAX),
        "bgcap_on": bool(pf.BGCAP_ON),
        "clean": clean_diag,
        "official": official_diag,
    }


def collect_still_probe(clean_root: str = TUMVI_DATA) -> dict:
    """Collect G6 stillness-calibration probe diagnostics on tuning rooms 1 and 2 present under clean_root."""
    probes = []
    for name in tumvi_still_probe.ALLOWED_DEFAULT:
        seq_dir = os.path.join(clean_root, name)
        imu = os.path.join(seq_dir, "mav0", "imu0", "data.csv")
        if os.path.isfile(imu):
            probes.append(tumvi_still_probe.probe_sequence(seq_dir))
    return {"rule": tumvi_still_probe.rule_specification(), "probes": probes}


def _format_still_probe_section(still_probe: dict) -> list[str]:
    probes = (still_probe or {}).get("probes") or []
    if not probes:
        return []
    spec = ((still_probe or {}).get("rule") or {}).get("constants") or tumvi_still_probe.rule_specification()["constants"]
    L = [
        "",
        "## Stillness calibration diagnosis on tuning rooms (`room1`, `room2`; `tools/tumvi_still_probe.py`)",
        "",
        "Hand-held finding: all units and conventions on TUM-VI match EuRoC (`gyro_first`, integer `ns` timestamps at "
        "`199.36 Hz`, accelerometer in `m/s^2`, gyro in `rad/s`), and mocap ground-truth speed during the opening `5 s` "
        "is only `0.011..0.050 m/s` (`0..4.5 s` before walking begins). Stillness calibration (`_calibrate` and fallback "
        "`_initialise`) nevertheless falls back to `fallback_zero` because the rig is hand-held rather than resting on a "
        "rigid surface: angular and linear hand micro-motion keeps per-axis `max(std_g)` (`>= 0.0381 rad/s` on `room1`, "
        "`>= 0.0847 rad/s` on `room2`; `1.91x..4.23x` above `STILL_GYRO_STD = %.2f rad/s`) and `max(std_a)` "
        "(`>= 0.1022 m/s^2` on `room1`, `>= 0.1482 m/s^2` on `room2`; `1.02x..1.48x` above `STILL_ACC_STD = %.2f m/s^2`) "
        "above the rigid-rest thresholds in every `1 s` window. The denoised retry (`_still_denoised`, `CAL_NOISE_ON = True`) "
        "subtracts only high-frequency second-difference white noise and leaves low-frequency hand sway intact "
        "(**1-5 Hz physiological tremor frequency band: not measured — no frequency spectrum was run**)."
        % (spec["STILL_GYRO_STD"], spec["STILL_ACC_STD"]),
        "",
        "### Best `1 s` windows and opening `1 s` window (`0..60 s`)",
        "",
        "| Sequence | Window | t (s) | Gyro std (x, y, z) rad/s | Max gyro std (vs 0.02) | Accel std (x, y, z) m/s^2 | Max accel std (vs 0.10) | ‖a‖-9.81 m/s^2 | std(‖a‖) m/s^2 | ‖mean_g‖ rad/s (vs 0.15) | Passes? |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for p in probes:
        seq = p["sequence"]
        for label, w in (
            ("Opening 1 s [0..1s]", p.get("window_0_to_1s")),
            ("Best 1 s (combined)", p.get("best_1s_window_combined")),
            ("Best 1 s (gyro std)", p.get("best_1s_window_by_gyro_std")),
            ("Best 1 s (acc std)", p.get("best_1s_window_by_acc_std")),
        ):
            if not w:
                continue
            gs = w["gyro_std_xyz"]
            acs = w["acc_std_xyz"]
            L.append(
                "| `%s` | %s | %.0f..%.0f | (%.4f, %.4f, %.4f) | **%.4f** (%.2fx) | (%.4f, %.4f, %.4f) | "
                "**%.4f** (%.2fx) | %+.4f | %.4f (%.2fx) | %.4f (%.2fx) | %s |"
                % (
                    seq,
                    label,
                    w["t_start_s"],
                    w["t_end_s"],
                    gs[0],
                    gs[1],
                    gs[2],
                    w["gyro_std_max"],
                    w["gyro_std_factor"],
                    acs[0],
                    acs[1],
                    acs[2],
                    w["acc_std_max"],
                    w["acc_std_factor"],
                    w["acc_norm_minus_g"],
                    w["acc_norm_std"],
                    w["acc_norm_std_factor"],
                    w["gyro_mean_norm"],
                    w["bg_norm_factor"],
                    "YES" if w["passes_1s_rule"] else "NO",
                )
            )

    L += [
        "",
        "### `0.25 s` calibration bins (`240` bins in `0..60 s`)",
        "",
        "| Sequence | Bins `gyro_std < 0.02` | Bins `acc_std < 0.10` | Bins `‖bg‖ <= 0.15` | Bins `8.8 <= ‖a‖ <= 10.8` | Strict still bins | Longest strict run (need 1.00 s) | Denoised still bins | Longest denoised run (need 1.00 s) | Best 4-bin (`1.0 s`) bottleneck miss factor |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for p in probes:
        b = p["bins_025s_summary"]
        gc = b["gate_pass_counts_240"]
        b4 = b.get("best_4bin_1s_block")
        b4_txt = (
            "%.2f..%.2fs: gyro_std %.2fx, acc_std %.2fx, steady_g %.2fx, steady_a %.2fx"
            % (
                b4["t_start_s"],
                b4["t_end_s"],
                b4["factor_gyro_std"],
                b4["factor_acc_std"],
                b4["factor_steady_gyro"],
                b4["factor_steady_acc"],
            )
            if b4
            else "-"
        )
        L.append(
            "| `%s` | %d/240 | %d/240 | %d/240 | %d/240 | **%d/240** | **%.2f s** (%d bins) | **%d/240** | **%.2f s** (%d bins) | %s |"
            % (
                p["sequence"],
                gc["ok_gyro_std"],
                gc["ok_acc_std"],
                gc["ok_bg"],
                gc["ok_acc_norm"],
                b["strict_still_bins_count"],
                b["strict_best_run_s"],
                b["strict_best_run_bins"],
                b["denoised_still_bins_count"],
                b["denoised_best_run_s"],
                b["denoised_best_run_bins"],
                b4_txt,
            )
        )

    L += [
        "",
        "### Units and conventions check against `pathfinder.py`",
        "",
        "| Sequence | Frontend order (`canonical`) | Timestamp unit (`median dt`, rate) | Rows / 0.25 s bin (need >=5) | Accel unit (median ‖a‖, p05..p95 m/s^2) | Opening 1 s mean accel (x, y, z) m/s^2 | Gyro unit (`gyro_suspect`, median ‖w‖ rad/s) | Opening 1 s mean gyro (x, y, z) rad/s |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for p in probes:
        u = p["units_and_conventions"]
        p05, p95 = u["accel_norm_p05_p95_m_s2"]
        a0 = u["opening_1s_accel_mean_xyz"]
        g0 = u["opening_1s_gyro_mean_xyz"]
        fe = u["frontend_detect"]
        L.append(
            "| `%s` | `%s` (`%s`) | `%s` (`%.3f ms`, `%.2f Hz`) | `%.1f` | `%s` (`%.3f`, `%.2f..%.2f`) | `(%.3f, %.3f, %.3f)` | `rad/s` (`suspect=%s`, `%.3f`) | `(%.4f, %.4f, %.4f)` |"
            % (
                p["sequence"],
                fe["order"],
                fe["canonical"],
                u["timestamp_unit"],
                u["median_dt_ms"],
                u["sample_rate_hz"],
                u["rows_per_025s_bin"],
                u["accel_unit_detected"],
                u["accel_norm_median_m_s2"],
                p05,
                p95,
                a0[0],
                a0[1],
                a0[2],
                u["gyro_suspect_deg_s"],
                u["gyro_norm_median_rad_s"],
                g0[0],
                g0[1],
                g0[2],
            )
        )

    if any(p.get("opening_5s_slices") for p in probes):
        L += [
            "",
            "### Opening `5 s` profile (`0..5 s` in `0.5 s` slices, with mocap GT speed)",
            "",
            "| Sequence | Window (s) | Max gyro std (rad/s) | Mean ‖w‖ (rad/s) | Max accel std (m/s^2) | Mocap GT mean speed (m/s) | Mocap GT max speed (m/s) |",
            "|---|---|---|---|---|---|---|",
        ]
        for p in probes:
            for sl in p.get("opening_5s_slices") or []:
                ta, tb = sl["t_window_s"]
                L.append(
                    "| `%s` | %.1f..%.1f | %.4f | %.4f | %.4f | %.4f | %.4f |"
                    % (
                        p["sequence"],
                        ta,
                        tb,
                        sl["gyro_std_max_rad_s"],
                        sl["gyro_rate_mean_rad_s"],
                        sl["acc_std_max_m_s2"],
                        sl["mocap_speed_mean_m_s"],
                        sl["mocap_speed_max_m_s"],
                    )
                )
    return L


def build(est: dict, flo: dict, ce: dict, cf: dict, calib: dict | None = None,
          still_probe: dict | None = None) -> str:
    """Build Docs/TUMVI_BASELINE.md from eval JSONs and calibration diagnostics."""
    bases = sorted({r["base"] for r in est["results"] if "base" in r})
    cleanE = {r["sequence"]: r for r in ce["results"] if "error" not in r}
    cleanF = {r["sequence"]: r for r in cf["results"] if "error" not in r}
    all_clean_seqs = sorted(set(cleanE) | set(cleanF))

    L = [
        "# TUM-VI baseline: shipped estimator against the never-moving floor "
        "(generated by `python tools/tumvi_table.py`; do not edit by hand)",
        "",
        "Estimator: `main.py` at %s (unchanged shipped settings). Floor: `tools/baseline_still.py` "
        "(one identity pose per row at the origin), scored the same way. APE = RMSE after SE3 Umeyama "
        "fitted on the run being scored. RPE 1 s = relative translation error over 200 frames. "
        "Gap = mean RMSE inside missing-row bursts (>= 5 rows). Blind = RMSE over the last 5 s "
        "(exact zeros). Official copies: the organisers' `degrade_imu.py` via `tools/official_degrade.py` "
        "(`--root data/tumvi`, seeds 1..3 evaluated here; seeds 1..3 and 7..15 exist on disk under `data/official_tumvi/`; "
        "seeds 7..9 are spent, seeds 10..15 are reserved for Claude Code's two judging rules, and seeds 16..18 are not generated and reserved for Claude Code). "
        "Tuning rooms: `room1`, `room2`; held out: `room3..room6` (`BG_MAX = %.2f rad/s`)."
        % (est.get("commit", "?"), pf.BG_MAX),
        "",
        "## Clean (undegraded) rooms: estimator / floor",
        "",
        "| Sequence | Set | Contract | APE SE3 m | RPE 1 s m | Wall s | LAST calibrated | Calibrated ‖bg‖ (rad/s) vs BG_MAX=0.15 |",
        "|---|---|---|---|---|---|---|---|",
    ]

    cal_clean = (calib or {}).get("clean", {})
    for s in all_clean_seqs:
        re_s = cleanE.get(s, {})
        rf_s = cleanF.get(s, {})
        cd = cal_clean.get(s, {})
        cal_txt = "-" if not cd else ("True (%s)" % cd["cal_source"] if cd["calibrated"] else "False (%s)" % cd["cal_source"])
        if not cd:
            bg_txt = "-"
        elif cd["uncapped_still_bg_norm_rad_s"] is not None:
            bg_txt = "%.4f (uncapped still %.4f > 0.15)" % (cd["bg_norm_rad_s"], cd["uncapped_still_bg_norm_rad_s"])
        else:
            bg_txt = "%.4f (%s)" % (cd["bg_norm_rad_s"], "> 0.15" if cd["exceeds_bg_max"] else "<= 0.15")
        L.append("| %s | %s | %s | %s / %s | %s / %s | %.2f / %.2f | %s | %s |" % (
            s,
            "tuning" if is_tuning(s) else "held out",
            re_s.get("contract", "ERROR"),
            fmt(re_s.get("ate_se3_rmse")), fmt(rf_s.get("ate_se3_rmse")),
            fmt(re_s.get("rpe200_rmse"), 3), fmt(rf_s.get("rpe200_rmse"), 3),
            re_s.get("wall_s", 0.0), rf_s.get("wall_s", 0.0),
            cal_txt,
            bg_txt,
        ))

    L += [
        "",
        "## Official-script copies (seeds 1..3): per room & reading, estimator / floor",
        "",
        "| Sequence | Set | Reading | Copies | Contract | APE SE3 m | RPE 1 s m | Gap RMSE m | Blind RMSE m | Blind growth m |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for b in bases:
        for reading in ("a", "b"):
            rs = group(est["results"], b, reading, (1, 2, 3))
            fs = group(flo["results"], b, reading, (1, 2, 3))
            if not rs:
                continue
            ok = sum(r["contract"] == "PASS" for r in rs)
            cells = [
                "%s / %s" % (fmt(mean([r[k] for r in rs]), d), fmt(mean([r[k] for r in fs]), d))
                for k, d in (("ape_se3_rmse", 2), ("rpe200_rmse", 3), ("gap_rmse_mean", 2),
                             ("blind_rmse", 2), ("blind_growth", 2))
            ]
            L.append("| %s | %s | %s | %d | %d/%d PASS | %s |" % (
                b, "tuning" if is_tuning(b) else "held out", reading, len(rs), ok, len(rs), " | ".join(cells)
            ))

    L += [
        "",
        "## Means by reading and set: estimator / floor (seeds 1..3)",
        "",
        "| Set | Reading | Seeds | Copies | APE SE3 m | RPE 1 s m | Gap RMSE m | Blind RMSE m | Blind growth m | Contract |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for setname, sel in (("held out", lambda b: not is_tuning(b)),
                         ("tuning", is_tuning),
                         ("all", lambda b: True)):
        for r_label, readings in (("a", ("a",)), ("b", ("b",)), ("a+b", ("a", "b"))):
            rs = [r for b in bases if sel(b) for rd in readings for r in group(est["results"], b, rd, (1, 2, 3))]
            fs = [r for b in bases if sel(b) for rd in readings for r in group(flo["results"], b, rd, (1, 2, 3))]
            if not rs:
                continue
            cells = [
                "%s / %s" % (fmt(mean([r[k] for r in rs]), d), fmt(mean([r[k] for r in fs]), d))
                for k, d in (("ape_se3_rmse", 2), ("rpe200_rmse", 3), ("gap_rmse_mean", 2),
                             ("blind_rmse", 2), ("blind_growth", 2))
            ]
            ok = sum(r["contract"] == "PASS" for r in rs)
            L.append("| %s | %s | 1..3 | %d | %s | %d/%d PASS |" % (
                setname, r_label, len(rs), " | ".join(cells), ok, len(rs)
            ))

    ce_ok = [r for r in ce["results"] if "error" not in r]
    L += [
        "",
        "## Clean (undegraded) means: estimator / floor",
        "",
        "| Set | Sequences | APE SE3 m | RPE 1 s m |",
        "|---|---|---|---|",
    ]
    for setname, sel in (("held out", lambda s: not is_tuning(s)),
                         ("tuning", is_tuning),
                         ("all", lambda s: True)):
        names = [r["sequence"] for r in ce_ok if sel(r["sequence"])]
        if not names:
            continue
        L.append("| %s | %d | %s / %s | %s / %s |" % (
            setname,
            len(names),
            fmt(mean([cleanE[n]["ate_se3_rmse"] for n in names])),
            fmt(mean([cleanF[n]["ate_se3_rmse"] for n in names if n in cleanF])),
            fmt(mean([cleanE[n]["rpe200_rmse"] for n in names]), 3),
            fmt(mean([cleanF[n]["rpe200_rmse"] for n in names if n in cleanF]), 3),
        ))

    if calib and calib.get("official"):
        L += [
            "",
            "## Calibration (`LAST`) and gyro bias vs `BG_MAX = %.2f rad/s` (official copies, seeds 1..3)" % pf.BG_MAX,
            "",
            "| Copy | Frontend order (from) | LAST calibrated | pre_rows | zupt_ticks | ‖bg‖ rad/s | vs BG_MAX (0.15) | Uncapped still ‖bg‖ |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for copy in sorted(calib["official"]):
            d = calib["official"][copy]
            uc = "-" if d["uncapped_still_bg_norm_rad_s"] is None else "%.4f" % d["uncapped_still_bg_norm_rad_s"]
            L.append("| %s | %s (%s) | %s (%s) | %d | %d | %.4f | %s | %s |" % (
                copy,
                d.get("frontend_order") or "-",
                d.get("frontend_order_from") or "-",
                d["calibrated"],
                d["cal_source"],
                d["pre_rows"],
                d["zupt_ticks"],
                d["bg_norm_rad_s"],
                "> 0.15" if d["exceeds_bg_max"] else "<= 0.15",
                uc,
            ))

    if still_probe:
        L += _format_still_probe_section(still_probe)

    errs = [r["sequence"] for t in (est, flo, ce, cf) for r in t["results"] if "error" in r]
    L += ["", "Runs with errors: %s" % (", ".join(errs) if errs else "none"), ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--est", default="tumvi-off")
    ap.add_argument("--floor", default="tumvi-floor-off")
    ap.add_argument("--clean", default="tumvi-clean")
    ap.add_argument("--floor-clean", default="tumvi-floor-clean")
    ap.add_argument("--calib", default="tumvi-calib")
    ap.add_argument("--still-probe", default="tumvi-still-probe")
    ap.add_argument("--docs-dir", default=TUMVI_DOCS)
    ap.add_argument("--tumvi-root", default=TUMVI_DATA)
    ap.add_argument("--official-root", default=TUMVI_OFFICIAL)
    ap.add_argument("--out", default=os.path.join(ROOT, "Docs", "TUMVI_BASELINE.md"))
    ap.add_argument("--collect-calib", action="store_true", help="Run pathfinder diagnostics and write calib JSON")
    ap.add_argument("--collect-still-probe", action="store_true", help="Run G6 stillness probe and write probe JSON")
    a = ap.parse_args(argv)

    est = load(os.path.join(a.docs_dir, a.est + ".json"))
    flo = load(os.path.join(a.docs_dir, a.floor + ".json"))
    ce = load(os.path.join(a.docs_dir, a.clean + ".json"))
    cf = load(os.path.join(a.docs_dir, a.floor_clean + ".json"))

    calib_path = os.path.join(a.docs_dir, a.calib + ".json")
    if a.collect_calib or not os.path.isfile(calib_path):
        calib = collect_calib(ce, est, clean_root=a.tumvi_root, official_root=a.official_root)
        os.makedirs(a.docs_dir, exist_ok=True)
        with open(calib_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(calib, fh, indent=1, sort_keys=True)
            fh.write("\n")
    else:
        calib = load(calib_path)

    probe_path = os.path.join(a.docs_dir, a.still_probe + ".json")
    if a.collect_still_probe or not os.path.isfile(probe_path):
        still_probe = collect_still_probe(clean_root=a.tumvi_root)
        if still_probe.get("probes"):
            os.makedirs(a.docs_dir, exist_ok=True)
            with open(probe_path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(still_probe, fh, indent=1, sort_keys=True)
                fh.write("\n")
    else:
        still_probe = load(probe_path)

    text = build(est, flo, ce, cf, calib, still_probe=still_probe)
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

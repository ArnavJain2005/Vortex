"""Q6 go/no-go for witness V3 (rotor drag). OFFLINE ANALYSIS ONLY: this tool reads ground truth.

Model (multirotor with thrust along one body axis): the specific force the IMU measures along the two
body axes perpendicular to thrust is mostly rotor drag,
    f_h = -k * v_h + c,
with v_h the body-frame velocity along the same axis and c whatever accelerometer bias is left.

What the tool does, per sequence:
  - IMU from mav0/imu0/data.csv (valid rows only); ground truth from state_groundtruth_estimate0
    (EuRoC: t, p, q(w,x,y,z), v (world), gyro bias, accel bias). Without velocity columns (TUM-VI
    mocap0) the velocity is differentiated from position.
  - Body velocity v_b = R^T v_w, interpolated to IMU times inside the ground-truth time span.
  - Thrust axis = the IMU axis with the largest mean |specific force|; the other two are "horizontal".
  - Optionally subtracts the ground-truth accelerometer bias estimate (default on).
  - Smooths both signals with a centred moving average (default 1 s) to remove rotor vibration.
  - Fits k and c by least squares on the first half, refits on the second half, reports R^2.
  - Writes Docs/drag/<seq>.json and Docs/drag/<seq>.svg (scatter + fit); --render writes Docs/DRAG.md.

PRE-REGISTERED DECISION RULE (fixed 16 Nov 2026, before any real EuRoC data was on disk):
  GO for V3 if, for BOTH horizontal body axes, with 1 s smoothing and ground-truth bias removed:
    (a) k fitted on the first half is > 0,
    (b) held-out R^2 on the second half >= 0.5, predicting with the first-half k and an offset c
        refitted on the second half (the filter tracks the accelerometer bias anyway; k must transfer),
    (c) k refitted on the second half is within 30 % of the first-half k.
  Otherwise NO-GO, and V3 stays switched off. One sequence passing is not enough to switch V3 on in
  the submission: that also needs a gain in score.py on sequences we did not tune on.

PRE-REGISTERED RULE v2 (fixed 16 Nov 2026, AFTER exploring MH_01..05, BEFORE any Vicon Room data was
on disk; the git history of this file is the record). Settings were chosen on MH only (exploratory
fits: one k = 0.1996 /s explains R^2 0.65..0.96 on every thrust-perpendicular axis of MH_01..05).
  Decision data: EuRoC Vicon Room 1, V1_01_easy, V1_02_medium, V1_03_difficult (same drone, other room,
  never used for tuning). Nothing may be tuned after seeing them; a change needs new held-out data
  (Vicon Room 2).
  Stage A, signal (this tool, `--rule v2`), per sequence:
    - airborne part: after the longest ground-truth rest (speed < 0.05 m/s for >= 5 s); the whole
      sequence if there is none. Ground-truth accelerometer bias removed, 1 s centred moving average.
    - axes: the two body directions perpendicular to u, the mean airborne specific-force direction:
      a = unit(u x e_z) (e_x if u is within 1e-3 of +-e_z), b = u x a.
    - per axis: R^2 of f against -K_FIXED v + c (c refitted per sequence: the filter tracks the bias)
      and the free-fit k.
    - the sequence passes if on BOTH axes R^2 >= 0.5 and |k_free - K_FIXED| <= 0.3 K_FIXED.
    GO if at least 2 of the 3 sequences pass; otherwise NO-GO and V3 is dropped.
  Stage B, estimator gain (tools/eval_euroc.py, only after a stage A GO): V3 is built and its
    parameters frozen on MH_01..05 only; it is switched on in main.py only if, on the three clean
    Vicon Room 1 sequences, mean APE SE3 AND mean RPE 1 s are each at least 10 % lower than V1 + V2
    alone at the same commit, and no sequence's APE is more than 10 % worse. Before the submission it
    must also be limited to multirotors (platform detection W4) or the risk stated.

Usage:
  python tools/drag_fit.py --rule v2 data/euroc/V1_01_easy [...]       # stage A; writes Docs/drag/v2_*.json
  python tools/drag_fit.py data/euroc/MH_01_easy [more sequences] [--win 1.0] [--no-bias] [--after-rest]
  --after-rest: EXPLORATORY, added 16 Nov 2026 AFTER seeing MH_01 (hand-carried start): fits only data
  after the longest ground-truth rest (speed < 0.05 m/s for >= 5 s). Never yields a GO/NO-GO decision.
  python tools/drag_fit.py --synthetic [--k 0.3]     # SYNTHETIC self-check, writes nothing to Docs
  python tools/drag_fit.py --render
Needs numpy. No plotting library: the SVG is written by hand.
"""
import glob
import json
import os
import sys
import tempfile
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from vortex.data import euroc  # noqa: E402
from vortex.geometry import matrix_to_quat, quat_normalize, quat_to_matrix  # noqa: E402
from vortex.rowspec import is_data_line  # noqa: E402

OUT_DIR = os.path.join(ROOT, "Docs", "drag")
RULE = {"smooth_s": 1.0, "min_r2_test": 0.5, "max_k_rel_change": 0.3}
RULE_V2 = {"smooth_s": 1.0, "k_fixed": 0.20, "min_r2": 0.5, "max_k_rel_dev": 0.3, "min_pass": 2,
           "rest_speed": 0.05, "rest_min_s": 5.0,
           "decision_sequences": ["V1_01_easy", "V1_02_medium", "V1_03_difficult"]}
REST_SPEED, REST_MIN_S = 0.05, 5.0   # exploratory --after-rest only
AXES = "xyz"


# ---------- loading ----------

def read_gt_full(path):
    """All numeric columns of a ground-truth csv: t (s), array (N, ncols-1)."""
    t_ns, rows = [], []
    with open(path, "r", encoding="ascii", errors="replace") as f:
        for line in f:
            if not is_data_line(line):
                continue
            fields = line.strip().split(",")
            t_ns.append(int(fields[0]))
            rows.append([float(x) for x in fields[1:]])
    width = min(len(r) for r in rows)
    return np.array(t_ns, dtype=np.int64) / 1e9, np.array([r[:width] for r in rows], dtype=float)


def gt_path(seq):
    for name in euroc.GT_FOLDERS:
        for c in (os.path.join(seq, "mav0", name, "data.csv"), os.path.join(seq, name, "data.csv")):
            if os.path.isfile(c):
                return c
    raise FileNotFoundError("no ground truth under %s" % seq)


def load(seq, use_bias=True, after_rest=False):
    raw = euroc.read_imu_csv(euroc.imu_path(seq))
    ok = raw.valid
    t_imu = raw.t_ns[ok] / 1e9
    acc = raw.accel[ok]
    t_gt, a = read_gt_full(gt_path(seq))
    p, q = a[:, 0:3], quat_normalize(a[:, 3:7])
    if a.shape[1] >= 10:
        v_w, vel_src = a[:, 7:10], "ground-truth velocity columns"
    else:
        v_w, vel_src = np.gradient(p, t_gt, axis=0), "differentiated ground-truth position"
    v_w_diff = np.gradient(p, t_gt, axis=0)
    ba = a[:, 13:16] if (use_bias and a.shape[1] >= 16) else None
    R = quat_to_matrix(q)
    v_b = np.einsum("nji,nj->ni", R, v_w)
    v_b_diff = np.einsum("nji,nj->ni", R, v_w_diff)
    inside = (t_imu >= t_gt[0]) & (t_imu <= t_gt[-1])
    rest_end = None
    if after_rest:                        # EXPLORATORY: keep only data after the longest GT rest
        rest_end = longest_rest_end(t_gt, v_w)
        inside &= t_imu >= rest_end
    t = t_imu[inside]
    f = acc[inside].copy()
    interp = lambda x: np.column_stack([np.interp(t, t_gt, x[:, i]) for i in range(3)])  # noqa: E731
    if ba is not None:
        f -= interp(ba)
    return {"t": t, "f": f, "v": interp(v_b), "v_diff": interp(v_b_diff), "acc_all": acc,
            "vel_src": vel_src, "bias_removed": ba is not None, "rows_imu": int(len(raw)),
            "rows_valid": int(ok.sum()), "after_rest": after_rest,
            "rest_end_s": None if rest_end is None else float(rest_end - t_gt[0])}


# ---------- fitting ----------

def smooth(x, n):
    """Centred moving average; drops n // 2 samples at each end."""
    if n <= 1:
        return x
    k = np.ones(n) / n
    y = np.convolve(x, k, mode="valid")
    return y


def fit(v, f):
    """f = -k v + c by least squares. Returns k, c, R^2."""
    X = np.column_stack([-v, np.ones_like(v)])
    (k, c), *_ = np.linalg.lstsq(X, f, rcond=None)
    return float(k), float(c), r2(f, -k * v + c)


def r2(y, yhat):
    ss = float(np.sum((y - np.mean(y)) ** 2))
    return 1.0 - float(np.sum((y - yhat) ** 2)) / ss if ss > 0 else float("nan")


def longest_rest_end(t, v_w, speed=REST_SPEED, min_s=REST_MIN_S):
    """End time of the longest interval with ground-truth speed below `speed` (at least min_s long).
    On EuRoC MH the drone is hand-carried, then set down, then flies; this marks rotors-on flight."""
    still = np.linalg.norm(v_w, axis=1) < speed
    best, best_len, start = t[0], 0.0, None
    for i, s_ in enumerate(still):
        if s_ and start is None:
            start = i
        if (not s_ or i == len(still) - 1) and start is not None:
            ln = t[i] - t[start]
            if ln > best_len:
                best, best_len = t[i], ln
            start = None
    return best if best_len >= min_s else t[0]


def analyse(d, win_s=RULE["smooth_s"]):
    t = d["t"]
    rate = (len(t) - 1) / (t[-1] - t[0])
    n = max(1, int(round(win_s * rate)))
    thrust = int(np.argmax(np.abs(np.mean(d["acc_all"], axis=0))))
    res = {"rows_imu": d["rows_imu"], "rows_valid": d["rows_valid"], "rows_used": int(len(t)),
           "overlap_s": float(t[-1] - t[0]), "imu_rate_hz": float(rate), "smooth_s": win_s,
           "smooth_rows": n, "velocity_source": d["vel_src"], "bias_removed": d["bias_removed"],
           "thrust_axis": AXES[thrust], "axes": {}}
    for i in [j for j in range(3) if j != thrust]:
        vs, fs = smooth(d["v"][:, i], n), smooth(d["f"][:, i], n)
        vd = smooth(d["v_diff"][:, i], n)
        h = len(vs) // 2
        k1, c1, r2_1 = fit(vs[:h], fs[:h])
        k2, c2, r2_2 = fit(vs[h:], fs[h:])
        c_test = float(np.mean(fs[h:] + k1 * vs[h:]))           # offset refitted, k from first half
        kf, cf, r2f = fit(vs, fs)
        kr, cr, r2r = fit(d["v"][:, i], d["f"][:, i])           # unsmoothed, for reference
        kd, _, r2d = fit(vd, fs)
        ax = {"k_first_half": k1, "c_first_half": c1, "r2_first_half": r2_1,
              "k_second_half": k2, "r2_second_half_refit": r2_2,
              "r2_test": r2(fs[h:], -k1 * vs[h:] + c_test),
              "r2_test_same_offset": r2(fs[h:], -k1 * vs[h:] + c1),
              "k_rel_change": abs(k2 - k1) / abs(k1) if k1 != 0 else float("inf"),
              "k_full": kf, "c_full": cf, "r2_full": r2f, "k_raw": kr, "r2_raw": r2r,
              "k_diff_velocity": kd, "r2_diff_velocity": r2d,
              "v_std": float(np.std(vs)), "f_std": float(np.std(fs))}
        checks = {"k_positive": k1 > 0, "r2_test_ok": ax["r2_test"] >= RULE["min_r2_test"],
                  "k_stable": ax["k_rel_change"] <= RULE["max_k_rel_change"]}
        ax["checks"] = checks
        ax["pass"] = all(checks.values())
        res["axes"][AXES[i]] = ax
        ax["_plot"] = (vs, fs)
    res["after_rest"], res["rest_end_s"] = d.get("after_rest", False), d.get("rest_end_s")
    rule_applies = win_s == RULE["smooth_s"] and d["bias_removed"] and not res["after_rest"]
    res["decision"] = ("GO" if all(a["pass"] for a in res["axes"].values()) else "NO-GO") \
        if rule_applies else ("n/a (EXPLORATORY post-hoc airborne-only fit, not the pre-registered rule)"
                              if res["after_rest"] else "n/a (settings differ from the pre-registered rule)")
    return res


def perp_axes(u):
    """Rule v2 axes: two unit vectors perpendicular to the specific-force direction u (body frame)."""
    u = np.asarray(u, float) / np.linalg.norm(u)
    a = np.cross(u, [0.0, 0.0, 1.0])
    if np.linalg.norm(a) < 1e-3:
        a = np.array([1.0, 0.0, 0.0]) - u[0] * u
    a /= np.linalg.norm(a)
    return a, np.cross(u, a)


def analyse_v2(d, rule=RULE_V2):
    """Stage A of rule v2 on load(seq, use_bias=True, after_rest=True)."""
    t = d["t"]
    rate = (len(t) - 1) / (t[-1] - t[0])
    n = max(1, int(round(rule["smooth_s"] * rate)))
    u = np.mean(d["f"], axis=0)
    u = u / np.linalg.norm(u)
    kf = rule["k_fixed"]
    res = {"rule": "v2", "rows_used": int(len(t)), "airborne_s": float(t[-1] - t[0]),
           "rest_end_s": d.get("rest_end_s"), "thrust_dir": [float(x) for x in u], "axes": {}}
    for name, e in zip(("a", "b"), perp_axes(u)):
        fs, vs = smooth(d["f"] @ e, n), smooth(d["v"] @ e, n)
        k_free, _, r2_free = fit(vs, fs)
        c = float(np.mean(fs + kf * vs))
        r2_fixed = r2(fs, -kf * vs + c)
        dev = abs(k_free - kf) / kf
        ok = {"r2_fixed_ok": r2_fixed >= rule["min_r2"], "k_close": dev <= rule["max_k_rel_dev"]}
        res["axes"][name] = {"dir": [float(x) for x in e], "k_free": k_free, "r2_free": r2_free,
                             "r2_fixed_k": r2_fixed, "k_rel_dev": dev, "checks": ok, "pass": all(ok.values()),
                             "_plot": (vs, fs)}
    res["pass"] = all(a["pass"] for a in res["axes"].values())
    return res


def decide_v2(results, rule=RULE_V2):
    """results: {sequence name: analyse_v2 output}. GO / NO-GO over the decision sequences only."""
    named = [results[s] for s in rule["decision_sequences"] if s in results]
    if len(named) < len(rule["decision_sequences"]):
        return "INCOMPLETE (needs %s)" % ", ".join(rule["decision_sequences"])
    return "GO" if sum(r["pass"] for r in named) >= rule["min_pass"] else "NO-GO"


# ---------- outputs ----------

def svg(res, title):
    W, H, pad = 420, 320, 46
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" font-family="sans-serif" '
             'font-size="11">' % (2 * W, H + 30),
             '<rect width="100%" height="100%" fill="white"/>',
             '<text x="8" y="16" font-size="13">%s</text>' % title]
    for j, (name, ax) in enumerate(res["axes"].items()):
        vs, fs = ax["_plot"]
        idx = np.linspace(0, len(vs) - 1, min(1500, len(vs))).astype(int)
        x0, y0 = j * W, 30
        vlo, vhi = np.percentile(vs, [0.5, 99.5])
        flo, fhi = np.percentile(fs, [0.5, 99.5])
        vlo, vhi = vlo - 0.05 * (vhi - vlo + 1e-9), vhi + 0.05 * (vhi - vlo + 1e-9)
        flo, fhi = flo - 0.05 * (fhi - flo + 1e-9), fhi + 0.05 * (fhi - flo + 1e-9)
        X = lambda v: x0 + pad + (v - vlo) / (vhi - vlo) * (W - 2 * pad)  # noqa: E731
        Y = lambda f: y0 + H - pad - (f - flo) / (fhi - flo) * (H - 2 * pad)  # noqa: E731
        parts.append('<rect x="%.1f" y="%.1f" width="%d" height="%d" fill="none" stroke="#999"/>'
                     % (x0 + pad, y0 + pad, W - 2 * pad, H - 2 * pad))
        for i in idx:
            if vlo <= vs[i] <= vhi and flo <= fs[i] <= fhi:
                parts.append('<circle cx="%.1f" cy="%.1f" r="1.2" fill="#3b6ea8" fill-opacity="0.35"/>'
                             % (X(vs[i]), Y(fs[i])))
        k, c = ax["k_full"], ax["c_full"]
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#c0392b" stroke-width="1.5"/>'
                     % (X(vlo), Y(np.clip(-k * vlo + c, flo, fhi)), X(vhi), Y(np.clip(-k * vhi + c, flo, fhi))))
        parts.append('<text x="%.1f" y="%.1f">body %s: k=%.3f 1/s, R2 test=%.2f, %s</text>'
                     % (x0 + pad, y0 + pad - 8, name, k, ax["r2_test"], "pass" if ax["pass"] else "fail"))
        parts.append('<text x="%.1f" y="%.1f">velocity [m/s] %.2f .. %.2f</text>'
                     % (x0 + pad, y0 + H - pad + 16, vlo, vhi))
        parts.append('<text x="%.1f" y="%.1f">specific force [m/s2] %.2f .. %.2f</text>'
                     % (x0 + pad, y0 + H - pad + 30, flo, fhi))
    parts.append("</svg>")
    return "\n".join(parts)


def save(res, seq_name, out_dir=OUT_DIR):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, seq_name + ".svg"), "w", encoding="utf-8", newline="\n") as f:
        f.write(svg(res, "%s: horizontal body specific force vs ground-truth body velocity (%.1f s smoothing)"
                    % (seq_name, res["smooth_s"])))
    clean = {k: v for k, v in res.items() if k != "axes"}
    clean["axes"] = {n: {k: v for k, v in a.items() if k != "_plot"} for n, a in res["axes"].items()}
    clean.update(sequence=seq_name, date=time.strftime("%Y-%m-%d"), rule=RULE)
    with open(os.path.join(out_dir, seq_name + ".json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(clean, f, indent=1, sort_keys=True)
        f.write("\n")
    return clean


def save_v2(res, seq_name, out_dir=OUT_DIR):
    os.makedirs(out_dir, exist_ok=True)
    clean = {k: v for k, v in res.items() if k != "axes"}
    clean["axes"] = {n: {k: v for k, v in a.items() if k != "_plot"} for n, a in res["axes"].items()}
    clean.update(sequence=seq_name, date=time.strftime("%Y-%m-%d"), rule_v2=RULE_V2,
                 role="DECISION" if seq_name in RULE_V2["decision_sequences"] else "tuning set (exploratory)")
    with open(os.path.join(out_dir, "v2_" + seq_name + ".json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(clean, f, indent=1, sort_keys=True)
        f.write("\n")
    plot = {"smooth_s": RULE_V2["smooth_s"], "axes": {n: {"k_full": RULE_V2["k_fixed"], "c_full": float(
        np.mean(a["_plot"][1] + RULE_V2["k_fixed"] * a["_plot"][0])), "r2_test": a["r2_fixed_k"],
        "pass": a["pass"], "_plot": a["_plot"]} for n, a in res["axes"].items()}}
    with open(os.path.join(out_dir, "v2_" + seq_name + ".svg"), "w", encoding="utf-8", newline="\n") as f:
        f.write(svg(plot, "%s (rule v2, %s): thrust-perpendicular specific force vs body velocity, line = fixed k"
                    % (seq_name, clean["role"])))
    return clean


def render_v2(out_dir=OUT_DIR):
    data = [json.load(open(p, encoding="utf-8")) for p in sorted(glob.glob(os.path.join(out_dir, "v2_*.json")))]
    r = RULE_V2
    L = ["## Rule v2 (pre-registered 16 Nov 2026 after exploring MH, before any Vicon Room data)", "",
         "Airborne part only (after the longest ground-truth rest), ground-truth accel bias removed, %.0f s "
         "smoothing, axes perpendicular to the mean airborne specific force. Per axis: R^2 with the FIXED "
         "k = %.2f /s (offset refitted) and the free-fit k. A sequence passes if both axes have R^2 >= %.1f "
         "and k within %.0f %% of %.2f. GO if at least %d of %s pass. Stage B (estimator gain on the same "
         "sequences, V3 frozen on MH) decides whether V3 is switched on; see `tools/drag_fit.py`."
         % (r["smooth_s"], r["k_fixed"], r["min_r2"], 100 * r["max_k_rel_dev"], r["k_fixed"], r["min_pass"],
            ", ".join(r["decision_sequences"])), "",
         "| Sequence | Role | Date | Airborne s | Axis | k free 1/s | R^2 fixed k | R^2 free | Axis result | Sequence |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for d in data:
        for name, a in d["axes"].items():
            L.append("| %s | %s | %s | %.0f | %s | %.4f | %.3f | %.3f | %s | %s |" % (
                d["sequence"], d["role"], d["date"], d["airborne_s"], name, a["k_free"], a["r2_fixed_k"],
                a["r2_free"], "pass" if a["pass"] else "fail (%s)" % ", ".join(k for k, v in a["checks"].items() if not v),
                "pass" if d["pass"] else "fail"))
    L += ["", "**Stage A decision: %s**" % decide_v2({d["sequence"]: d for d in data}), ""]
    return L


def render(out_dir=OUT_DIR, md_path=None):
    md_path = md_path or os.path.join(ROOT, "Docs", "DRAG.md")
    data = [json.load(open(p, encoding="utf-8")) for p in sorted(glob.glob(os.path.join(out_dir, "*.json")))
            if not os.path.basename(p).startswith("v2_")]
    L = ["# Rotor-drag go/no-go (Q6; generated by `python tools/drag_fit.py --render`; do not edit by hand)", "",
         "Model: horizontal body specific force f = -k v + c, v = ground-truth body velocity. "
         "OFFLINE analysis; the estimator never reads ground truth.", "",
         "Pre-registered rule (16 Nov 2026, before real data): with %.0f s smoothing and ground-truth accel bias "
         "removed, GO if for both horizontal axes k (first half) > 0, held-out R^2 on the second half >= %.1f "
         "(first-half k, offset refitted), and second-half k within %.0f %% of first-half k."
         % (RULE["smooth_s"], RULE["min_r2_test"], 100 * RULE["max_k_rel_change"]), "",
         "| Sequence | Date | Overlap s | Thrust axis | Axis | k first half 1/s | k second half | k full | "
         "R^2 test | R^2 full | R^2 raw | k (diff. velocity) | Axis result | Decision |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for d in data:
        for name, a in d["axes"].items():
            L.append("| %s | %s | %.0f | %s | %s | %.4f | %.4f | %.4f | %.3f | %.3f | %.3f | %.4f | %s | %s |" % (
                d["sequence"], d["date"], d["overlap_s"], d["thrust_axis"], name, a["k_first_half"],
                a["k_second_half"], a["k_full"], a["r2_test"], a["r2_full"], a["r2_raw"], a["k_diff_velocity"],
                "pass" if a["pass"] else "fail (%s)" % ", ".join(k for k, v in a["checks"].items() if not v),
                d["decision"]))
    L += ["", "Rows named `*_after_rest` are EXPLORATORY (option added 16 Nov 2026 after MH_01 showed a "
          "hand-carried start, then a ground rest, then flight): they fit only data after the longest "
          "ground-truth rest, so rotors are on. They never change the pre-registered decision; switching V3 "
          "on would need a new rule fixed in advance and tested on sequences not used here.", "",
          "Plots: `Docs/drag/<sequence>.svg`.", ""] + render_v2(out_dir)
    with open(md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))
    return md_path


# ---------- synthetic self-check ----------

def synth_sequence(folder, k=0.3, seconds=120.0, seed=0, bias=(0.0, 0.05, -0.08), vib=0.5):
    """SYNTHETIC EuRoC-layout sequence with known drag k. IMU x axis is the thrust axis (as on EuRoC)."""
    rng = np.random.default_rng(seed)
    t = np.arange(0, seconds, 0.005)
    w = 2 * np.pi / np.array([17.0, 11.0])
    v_w = np.column_stack([1.2 * np.cos(w[0] * t), 0.9 * np.sin(w[1] * t), 0.1 * np.sin(0.3 * t)])
    p = np.column_stack([1.2 / w[0] * np.sin(w[0] * t), -0.9 / w[1] * np.cos(w[1] * t), -np.cos(0.3 * t) / 3])
    yaw = 0.25 * t + 0.4 * np.sin(0.2 * t)
    R0 = np.array([[0.0, 1, 0], [0, 0, 1], [1, 0, 0]])           # body x -> world z (thrust up)
    cy, sy = np.cos(yaw), np.sin(yaw)
    Rz = np.zeros((len(t), 3, 3))
    Rz[:, 0, 0], Rz[:, 0, 1], Rz[:, 1, 0], Rz[:, 1, 1], Rz[:, 2, 2] = cy, -sy, sy, cy, 1
    R = Rz @ R0
    q = np.array([matrix_to_quat(r) for r in R])
    v_b = np.einsum("nji,nj->ni", R, v_w)
    f = np.column_stack([9.81 + 0 * t, -k * v_b[:, 1], -k * v_b[:, 2]]) + np.array(bias)
    f += rng.normal(0, vib, f.shape)
    g = rng.normal(0, 0.01, (len(t), 3))
    t_ns = 1403636579758555392 + np.arange(len(t), dtype=np.int64) * 5000000
    mav0 = os.path.join(folder, "mav0")
    os.makedirs(os.path.join(mav0, "imu0"), exist_ok=True)
    os.makedirs(os.path.join(mav0, "state_groundtruth_estimate0"), exist_ok=True)
    with open(os.path.join(mav0, "imu0", "data.csv"), "w", newline="\n") as fh:
        fh.write(euroc.HEADER + "\n")
        for i in range(len(t)):
            fh.write("%d,%s\n" % (t_ns[i], ",".join(repr(float(x)) for x in (*g[i], *f[i]))))
    sl = slice(400, len(t) - 400)                                  # ground truth starts later, ends earlier
    with open(os.path.join(mav0, "state_groundtruth_estimate0", "data.csv"), "w", newline="\n") as fh:
        fh.write("#timestamp,p_x,p_y,p_z,q_w,q_x,q_y,q_z,v_x,v_y,v_z,bw_x,bw_y,bw_z,ba_x,ba_y,ba_z\n")
        for i in range(len(t))[sl]:
            fh.write("%d,%s\n" % (t_ns[i] + 2500000, ",".join(
                "%.9f" % x for x in [*p[i], *q[i], *v_w[i], 0, 0, 0, *bias])))
    return folder


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--render" in argv:
        print("wrote", os.path.relpath(render(), ROOT))
        return 0
    get = lambda key, d: argv[argv.index(key) + 1] if key in argv else d  # noqa: E731
    win = float(get("--win", RULE["smooth_s"]))
    use_bias = "--no-bias" not in argv
    after_rest = "--after-rest" in argv
    if "--synthetic" in argv:
        k = float(get("--k", 0.3))
        seq = synth_sequence(tempfile.mkdtemp(prefix="vortex_drag_"), k=k)
        res = analyse(load(seq, use_bias), win)
        print("SYNTHETIC, true k = %.3f" % k)
        for n, a in res["axes"].items():
            print("  body %s: k first half %.4f, second half %.4f, R2 test %.3f -> %s"
                  % (n, a["k_first_half"], a["k_second_half"], a["r2_test"], "pass" if a["pass"] else "fail"))
        print("decision:", res["decision"])
        return 0
    flags_with_value = {"--win", "--rule"}
    if get("--rule", None) == "v2":
        seqs = [a for i, a in enumerate(argv) if not a.startswith("--") and argv[i - 1] not in flags_with_value]
        for seq in seqs:
            name = os.path.basename(os.path.normpath(seq))
            res = analyse_v2(load(seq, use_bias=True, after_rest=True))
            clean = save_v2(res, name)
            print("%s (%s): airborne %.0f s, thrust dir %s" % (name, clean["role"], res["airborne_s"],
                                                               np.round(res["thrust_dir"], 3)))
            for n, a in res["axes"].items():
                print("  axis %s: k free %.4f, R2 fixed k %.3f -> %s" % (n, a["k_free"], a["r2_fixed_k"],
                                                                        "pass" if a["pass"] else "fail"))
        print("wrote", os.path.relpath(render(), ROOT))
        return 0
    seqs = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in flags_with_value)]
    if not seqs:
        print(__doc__)
        return 2
    for seq in seqs:
        name = os.path.basename(os.path.normpath(seq))
        if win != RULE["smooth_s"] or not use_bias:
            name += "_win%g%s" % (win, "_nobias" if not use_bias else "")
        if after_rest:
            name += "_after_rest"
        res = save(analyse(load(seq, use_bias, after_rest), win), name)
        print("%s: thrust axis %s, overlap %.0f s, velocity from %s" % (
            name, res["thrust_axis"], res["overlap_s"], res["velocity_source"]))
        for n, a in res["axes"].items():
            print("  body %s: k first half %.4f, second half %.4f, full %.4f; R2 test %.3f, full %.3f, raw %.3f -> %s"
                  % (n, a["k_first_half"], a["k_second_half"], a["k_full"], a["r2_test"], a["r2_full"],
                     a["r2_raw"], "pass" if a["pass"] else "fail"))
        print("  decision:", res["decision"])
    print("wrote", os.path.relpath(render(), ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())

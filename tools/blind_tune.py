"""Step L3 tuning harness (TUNING DATA ONLY: MH_01/02 and TUM-VI room1/2 official copies, readings a, b, seeds
1-3; clean MH_01/02 and room1/2 for information). Docs/TRACK3_PLAN.md, Step L3.

Runs the shipped build once per file, then applies each blind-window candidate (B0-B3) to that output and scores
it as the organisers do (APE with SE3 fitted on the run; gap and blind windows from degrade.json). The blind start
is found from the IMU file with the estimator's own row test (blind_start()), so the harness sees what the built
switch will see. Writes Docs/blind/<tag>.json and Docs/blind/<tag>.md.

    python tools/blind_tune.py --tag stepL3-tune [--main main.py]
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
from vortex import scoring  # noqa: E402

OUT = os.path.join(ROOT, "Docs", "blind")
EUROC, TUMVI = os.path.join(ROOT, "data", "euroc"), os.path.join(ROOT, "data", "tumvi")
OFF_E, OFF_T = os.path.join(ROOT, "data", "official"), os.path.join(ROOT, "data", "official_tumvi")
SEEDS = (1, 2, 3)
STUCK_ROWS = 5            # pathfinder.STUCK_ROWS
MAX_SUMSQ = 1e8           # pathfinder.MAX_SUMSQ
BLIND_MIN_S = 1.0
BLIND_FALLBACK_S = 5.0
TICK = 0.25
W3 = 2.0                  # B3 fit window (s)


def files():
    out = []
    for b in ("MH_01_easy", "MH_02_easy"):
        out += [("%s_%s_s%d" % (b, r, s), b, OFF_E, EUROC, "mh-" + r) for r in "ab" for s in SEEDS]
    for b in ("dataset-room1_512_16", "dataset-room2_512_16"):
        out += [("%s_%s_s%d" % (b, r, s), b, OFF_T, TUMVI, "tv-" + r) for r in "ab" for s in SEEDS]
    out += [(b, b, EUROC, EUROC, "clean-mh") for b in ("MH_01_easy", "MH_02_easy")]
    out += [(b, b, TUMVI, TUMVI, "clean-tv") for b in ("dataset-room1_512_16", "dataset-room2_512_16")]
    return out


def candidates():
    c = [("B0", None)]
    c += [("B1 L=%g" % L, ("B1", L)) for L in (1.0, 2.0, 3.0)]
    c += [("B2 L=%g b=%g" % (L, b), ("B2", L, b)) for L in (1.0, 2.0, 3.0) for b in (0.25, 0.5, 0.75, 1.0)]
    c += [("B3 L=%g tau=%g" % (L, t), ("B3", L, t)) for L in (1.0, 2.0, 3.0) for t in (0.25, 0.5, 1.0)]
    return c


def blind_start(imu):
    """(t_b in s, how): the first timestamp of the trailing run of rows the estimator rejects (not finite or
    absurd, all-zero accelerometer, a triple repeated STUCK_ROWS times) if it spans >= BLIND_MIN_S; else the
    last BLIND_FALLBACK_S seconds."""
    ts, bad = [], []
    lg = la = None
    sg = sa = 0
    with open(imu, encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            p = line.strip().split(",")
            try:
                t = int(p[0])
            except ValueError:
                continue
            try:
                v = [float(x) for x in p[1:7]]
                ok = sum(x * x for x in v) < MAX_SUMSQ
            except (ValueError, IndexError):
                ok = False
            if ok:
                g, a = tuple(v[:3]), tuple(v[3:])
                if g == lg:
                    sg += 1
                else:
                    lg, sg = g, 1
                if a == la:
                    sa += 1
                else:
                    la, sa = a, 1
                if sg >= STUCK_ROWS or sa >= STUCK_ROWS or not (a[0] or a[1] or a[2]):
                    ok = False
            ts.append(t * 1e-9)
            bad.append(not ok)
    i = len(bad)
    while i > 0 and bad[i - 1]:
        i -= 1
    if i < len(bad) and ts[-1] - ts[i] >= BLIND_MIN_S:
        return ts[i], "dead run"
    return ts[-1] - BLIND_FALLBACK_S, "fallback"


def apply(cand, t, p, R, tb):
    """One candidate on the output (t: s, p: (N, 3), R: (N, 3, 3)); returns new (p, R)."""
    if cand is None:
        return p, R
    kind, L = cand[0], cand[1]
    ta = tb - L
    m = t >= ta
    if not m.any():
        return p, R
    i0 = int(np.argmax(m))
    ia = max(i0 - 1, 0)
    a = p[ia].copy()
    p2, R2 = p.copy(), R.copy()
    R2[m] = R[ia]
    if kind == "B1":
        p2[m] = a
    elif kind == "B2":
        beta = cand[2]
        c = p[:i0].mean(axis=0) if i0 else a
        w = beta * np.minimum(1.0, (t[m] - ta) / L)
        p2[m] = a + w[:, None] * (c - a)
    elif kind == "B3":
        tau = cand[2]
        s = ta - W3 + TICK * np.arange(int(round(W3 / TICK)))
        idx = np.searchsorted(t, s, side="right") - 1
        idx = np.clip(idx, 0, len(t) - 1)
        q = p[idx]
        k = int(round(1.0 / TICK))
        sl = (q[k:] - q[:-k]) / 1.0
        v = np.median(sl, axis=0) if len(sl) else np.zeros(3)
        dt = t[m] - ta
        p2[m] = a + v[None, :] * (tau * (1.0 - np.exp(-dt / tau)))[:, None]
    return p2, R2


def score_one(ref, t, p, R, events):
    e = scoring.Traj(t, p, R)
    if events is None:
        r = scoring.score(ref, e, align="se3", rpe_deltas=(200,))
        return {"ape": r["ape"]["rmse"]}
    r = scoring.score(ref, e, align="se3", rpe_deltas=(200,), events=events)
    ph = r["phases"]
    drops = [d for d in ph["dropouts"] if d.get("n")]
    bl = ph["blind"]
    return {"ape": r["ape"]["rmse"], "rpe": r["rpe"]["200"]["rmse"],
            "gap": sum(d["rmse"] for d in drops) / len(drops) if drops else None,
            "blind": bl["rmse"], "fail_err": bl["start_error"], "growth": bl["growth"]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--main", default=os.path.join(ROOT, "main.py"))
    args = ap.parse_args(argv)
    cands = candidates()
    res = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, base, droot, groot, grp in files():
            seq = os.path.join(droot, name)
            imu = os.path.join(seq, "mav0", "imu0", "data.csv")
            est = os.path.join(tmp, name + ".txt")
            pr, _ = eval_euroc.run_main(os.path.abspath(args.main), imu, est)
            assert pr.returncode == 0, pr.stderr[-400:]
            ev_path = os.path.join(seq, "degrade.json")
            events = json.load(open(ev_path, encoding="utf-8")) if os.path.exists(ev_path) else None
            ref = scoring.read_ground_truth(os.path.join(groot, base))
            e, _ = scoring.read_tum(est)
            tb, how = blind_start(imu)
            row = {"group": grp, "t_b_rel": tb - (events["t0_ns"] / 1e9 if events else e.t[0]), "how": how,
                   "failure_at_s": events.get("failure_at_s") if events else None, "scores": {}}
            for lab, c in cands:
                p2, R2 = apply(c, e.t, e.p, e.R, tb)
                row["scores"][lab] = score_one(ref, e.t, p2, R2, events)
            res[name] = row
            b0 = row["scores"]["B0"]
            print("%-28s %-8s t_b %.3f B0 APE %.3f blind %s" % (name, how, row["t_b_rel"], b0["ape"],
                                                               "%.3f" % b0["blind"] if "blind" in b0 else "-"),
                  flush=True)
    summ = summarise(res, cands)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, args.tag + ".json"), "w", encoding="utf-8") as f:
        json.dump({"tag": args.tag, "main": os.path.relpath(os.path.abspath(args.main), ROOT),
                   "criterion": "lowest mean blind RMSE over the 24 copies among candidates with mean APE not "
                                "worse than B0 by > 0.5 % and mean gap RMSE not worse by > 1 %",
                   "summary": summ, "runs": res}, f, indent=1)
    render(args.tag)
    return 0


def summarise(res, cands):
    deg = [r for r in res.values() if not r["group"].startswith("clean")]
    out = {}
    for lab, _ in cands:
        d = {}
        for k in ("ape", "rpe", "gap", "blind", "fail_err", "growth"):
            xs = [r["scores"][lab][k] for r in deg if r["scores"][lab].get(k) is not None]
            d[k] = sum(xs) / len(xs)
        for g in ("mh-a", "mh-b", "tv-a", "tv-b"):
            rs = [r for r in deg if r["group"] == g]
            d["blind_" + g] = sum(r["scores"][lab]["blind"] for r in rs) / len(rs)
            d["ape_" + g] = sum(r["scores"][lab]["ape"] for r in rs) / len(rs)
        cl = [r for r in res.values() if r["group"].startswith("clean")]
        d["clean_ape"] = sum(r["scores"][lab]["ape"] for r in cl) / len(cl)
        out[lab] = d
    b0 = out["B0"]
    ok = {lab: (d["ape"] <= b0["ape"] * 1.005 and d["gap"] <= b0["gap"] * 1.01) for lab, d in out.items()}
    best = min((lab for lab in out if ok[lab]), key=lambda lab: out[lab]["blind"])
    for lab in out:
        out[lab]["eligible"] = ok[lab]
    out["_chosen"] = best
    return out


def render(tag):
    with open(os.path.join(OUT, tag + ".json"), encoding="utf-8") as f:
        d = json.load(f)
    s = d["summary"]
    ch = s["_chosen"]
    lines = ["# Step L3 tuning: %s (generated by `python tools/blind_tune.py`; do not edit)" % tag, "",
             "Main: `%s`. 24 tuning copies: MH_01/02 and TUM-VI room1/2 x readings a, b x seeds 1-3; clean MH_01/02 and "
             "room1/2 (fallback: last 5 s) for information. Means over copies, metres; APE with SE3 fitted on the run. "
             "Criterion (committed before this run): %s. **Chosen: %s.**" % (d["main"], d["criterion"], ch), "",
             "| Candidate | eligible | blind RMSE | error at failure | blind growth | APE | gap RMSE | RPE 1 s | blind MH a / b | "
             "blind TV a / b | clean APE |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for lab, x in s.items():
        if lab.startswith("_"):
            continue
        lines.append("| %s%s | %s | %.3f | %.3f | %.3f | %.3f | %.3f | %.3f | %.3f / %.3f | %.3f / %.3f | %.4f |" % (
            "**%s**" % lab if lab == ch else lab, "", "yes" if x["eligible"] else "no", x["blind"], x["fail_err"],
            x["growth"], x["ape"], x["gap"], x["rpe"], x["blind_mh-a"], x["blind_mh-b"], x["blind_tv-a"],
            x["blind_tv-b"], x["clean_ape"]))
    hows = {}
    for r in d["runs"].values():
        hows.setdefault(r["how"], []).append(r["group"])
    lines += ["", "Blind start: " + "; ".join("%s on %d files (%s)" % (h, len(g), ", ".join(sorted(set(g))))
                                              for h, g in hows.items()) + "."]
    gaps = [abs(r["t_b_rel"] - r["failure_at_s"]) for r in d["runs"].values() if r["failure_at_s"] is not None]
    lines.append("Detected blind start against degrade.json `failure_at_s`: max |difference| %.4f s." % max(gaps))
    with open(os.path.join(OUT, tag + ".md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())

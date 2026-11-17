"""Step 8 study: error in the blind 5 s window against the forecaster and dead-sensor switches.

For each EuRoC sequence and each failure point (fraction of the duration), one seeded degraded copy is
made in memory (vortex.degrade defaults, failure mode nan / zero / stuck) and the reference estimator
(vortex/core/witness.py) runs on it with each switch setting. Errors use the SE3 alignment fitted on
the reference's clean run (align "given"). GROUND TRUTH IS USED FOR SCORING ONLY.

    python tools/blind_study.py --tag NAME data/euroc/MH_01_easy ... [--fracs ...] [--seed0 N]
    python tools/blind_study.py --render          # rebuilds Docs/BLIND.md from Docs/blind/*.json

Variants: mode nan -> forecaster off (constant velocity) and FC_TAU in --taus; modes zero and stuck ->
dead detection off (forecaster off), then on with the same forecaster variants.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import statistics as st
import subprocess
import sys
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from vortex import degrade as dg, scoring  # noqa: E402
from vortex.core import strapdown as sd, witness as wx  # noqa: E402
from vortex.data import euroc  # noqa: E402

OUT_DIR = os.path.join(ROOT, "Docs", "blind")
DOC = os.path.join(ROOT, "Docs", "BLIND.md")


def _traj(raw, out):
    o = np.array(out)
    return scoring._clean(raw.t_ns / 1e9, o[:, :3], o[:, 3:7])[0]


def _commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True).stdout.strip() or "?"
    except OSError:
        return "?"


def run(seqs, fracs, seed0, modes, taus):
    res = []
    for d in seqs:
        seq = os.path.basename(os.path.normpath(d))
        clean = euroc.read_imu_csv(os.path.join(d, "mav0", "imu0", "data.csv"))
        ref = scoring.read_ground_truth(d)
        al = scoring.fit_alignment(ref, _traj(clean, wx.estimate(sd.rows_from_raw(clean))), "se3")
        for i, fr in enumerate(fracs):
            seed = seed0 + i
            for mode in modes:
                raw, ev = dg.degrade(clean, dg.DegradeConfig(failure_at_frac=fr, failure_mode=mode), seed)
                rows = sd.rows_from_raw(raw)
                variants = [(False, tau) for tau in taus] if mode == "nan" else \
                    [(False, None)] + [(True, tau) for tau in taus]
                for dead, tau in variants:
                    saved = wx.FC_TAU
                    wx.FC_TAU = tau if tau is not None else saved
                    try:
                        out = wx.estimate(rows, dead=dead, fc=tau is not None)
                    finally:
                        wx.FC_TAU = saved
                    r = scoring.score(ref, _traj(raw, out), align="given", given=al, rpe_deltas=(200,),
                                      events=ev)
                    ph = r["phases"]
                    drops = [x["growth"] for x in ph["dropouts"] if x.get("n")]
                    b = ph["blind"]
                    res.append({"seq": seq, "frac": fr, "seed": seed, "mode": mode, "dead": dead,
                                "tau": tau, "blind_growth": b["growth"], "blind_rmse": b["rmse"],
                                "blind_start": b["start_error"], "ape": r["ape"]["rmse"],
                                "dropout_growth": sum(drops) / len(drops) if drops else None})
                    print("%s %.2f %s dead=%s tau=%s growth %.2f rmse %.2f" % (
                        seq, fr, mode, dead, tau, b["growth"], b["rmse"]), flush=True)
    return res


def _key(r):
    return (r["mode"], r["dead"], r["tau"])


def summary(res):
    """One row per (mode, dead, tau): means over sequences and failure points."""
    g = defaultdict(list)
    for r in res:
        g[_key(r)].append(r)
    order = sorted(g, key=lambda k: (k[0], k[1], -(k[2] if k[2] is not None else 1e9)))
    L = ["| Failure mode | Dead detection | Forecaster | Runs | Blind growth m | Blind RMSE m | APE m | "
         "Dropout growth m |", "|---|---|---|---|---|---|---|---|"]
    for k in order:
        rs = g[k]
        dgs = [r["dropout_growth"] for r in rs if r["dropout_growth"] is not None]
        L.append("| %s | %s | %s | %d | %.3f | %.3f | %.3f | %s |" % (
            k[0], "on" if k[1] else "off", "constant velocity" if k[2] is None else "tau %g s" % k[2],
            len(rs), st.mean(r["blind_growth"] for r in rs), st.mean(r["blind_rmse"] for r in rs),
            st.mean(r["ape"] for r in rs), "%.3f" % st.mean(dgs) if dgs else "-"))
    return L


def render():
    runs = []
    for name in sorted(os.listdir(OUT_DIR)) if os.path.isdir(OUT_DIR) else []:
        if name.endswith(".json"):
            with open(os.path.join(OUT_DIR, name), encoding="utf-8") as f:
                runs.append(json.load(f))
    L = ["# Blind 5 s window study (step 8)", "",
         "Generated by `python tools/blind_study.py --render` from `Docs/blind/*.json`; do not edit by hand.",
         "Each run: one seeded degraded copy (`vortex.degrade` defaults, placeholder levels) with the failure",
         "at the given fraction of the sequence, scored with the SE3 alignment of the clean run (align",
         "\"given\"). Reference estimator (`vortex/core/witness.py`). Ground truth is used for scoring only.",
         "Blind growth = norm of the change of the error vector over the 5 s window.", ""]
    for run in runs:
        L += ["## %s" % run["tag"], "",
              "Commit %s, %s. Sequences: %s. Failure points: %s. Seeds %d..%d (one per failure point)." % (
                  run["commit"], run["date"], ", ".join(run["seqs"]), ", ".join("%g" % f for f in run["fracs"]),
                  run["seed0"], run["seed0"] + len(run["fracs"]) - 1), ""]
        L += summary(run["results"]) + [""]
    with open(DOC, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))
    print("wrote", DOC)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("seqs", nargs="*")
    ap.add_argument("--tag")
    ap.add_argument("--fracs", default="0.5,0.6,0.7,0.8,0.9,0.95")
    ap.add_argument("--seed0", type=int, default=100)
    ap.add_argument("--modes", default="nan,zero,stuck")
    ap.add_argument("--taus", default="cv,16,8,4,2,1,0.5,0.001")
    ap.add_argument("--render", action="store_true")
    a = ap.parse_args(argv)
    if a.render:
        render()
        return 0
    if not a.tag or not a.seqs:
        ap.error("--tag and at least one sequence are needed")
    fracs = [float(x) for x in a.fracs.split(",")]
    taus = [None if x == "cv" else float(x) for x in a.taus.split(",")]
    res = run(a.seqs, fracs, a.seed0, a.modes.split(","), taus)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, a.tag + ".json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"tag": a.tag, "commit": _commit(), "date": datetime.date.today().isoformat(),
                   "seqs": [os.path.basename(os.path.normpath(s)) for s in a.seqs], "fracs": fracs,
                   "seed0": a.seed0, "results": res}, f, indent=1)
    render()
    return 0


if __name__ == "__main__":
    sys.exit(main())

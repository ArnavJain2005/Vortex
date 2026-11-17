"""Step E tuning grid (MH_01/02 only): the smoother with the V2 envelope settings, against the shipped
forward filter. OFFLINE (ground truth for SCORING only). Reference estimator (vortex/core/witness.py).

    python tools/smooth_grid.py        # writes Docs/smooth/stepE-grid.json

Clean MH_01/02: APE SE3, RPE 1 s, and the step 7a tuning score (mean of APE/floor + RPE1s/floor,
floor = never-moving trajectory, Docs/RESULTS.md floor-still). Degraded MH_01/02 x seeds 1..3 (the
existing data/degraded copies): APE with the alignment from the same setting's clean run, mean dropout
growth.
"""
import itertools
import json
import os
import statistics as st
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from smooth_eval import traj  # noqa: E402
from vortex import scoring  # noqa: E402
from vortex.core import strapdown as sd, witness as wx  # noqa: E402
from vortex.data import euroc  # noqa: E402

FLOOR = {"MH_01_easy": (4.31, 0.499), "MH_02_easy": (4.65, 0.537)}   # Docs/RESULTS.md floor-still (APE, RPE 1 s)


def main():
    data, copies = {}, {}
    for seq in FLOOR:
        d = os.path.join(ROOT, "data", "euroc", seq)
        raw = euroc.read_imu_csv(os.path.join(d, "mav0", "imu0", "data.csv"))
        data[seq] = (raw, scoring.read_ground_truth(d), sd.rows_from_raw(raw))
        for s in (1, 2, 3):
            dd = os.path.join(ROOT, "data", "degraded", "%s_s%d" % (seq, s))
            raw = euroc.read_imu_csv(os.path.join(dd, "mav0", "imu0", "data.csv"))
            with open(os.path.join(dd, "degrade.json"), encoding="utf-8") as f:
                copies[(seq, s)] = (raw, json.load(f), sd.rows_from_raw(raw))
    base = (wx.V2_SIGMA_H, wx.V2P_SIGMA_H, wx.V2P_TAU)
    grid = [(False, base)] + [(True, c) for c in itertools.product((1.0, 2.0), (2.0, 5.0, 10.0), (10.0, 30.0))]
    res = []
    for sm, (sh, ph, tau) in grid:
        wx.V2_SIGMA_H, wx.V2P_SIGMA_H, wx.V2P_TAU = sh, ph, tau
        apes, rpes, score, als = [], [], [], {}
        for seq, (raw, ref, rows) in data.items():
            tr = traj(raw.t_ns, wx.estimate(rows, smooth=sm))
            als[seq] = scoring.fit_alignment(ref, tr, "se3")
            r = scoring.score(ref, tr, align="se3", rpe_deltas=(200,))
            a, b = r["ape"]["rmse"], r["rpe"]["200"]["rmse"]
            apes.append(a)
            rpes.append(b)
            score.append(a / FLOOR[seq][0] + b / FLOOR[seq][1])
        da, dg = [], []
        for (seq, s), (raw, ev, rows) in copies.items():
            r = scoring.score(data[seq][1], traj(raw.t_ns, wx.estimate(rows, smooth=sm)), align="given",
                              given=als[seq], rpe_deltas=(200,), events=ev)
            da.append(r["ape"]["rmse"])
            dr = [x for x in r["phases"]["dropouts"] if x.get("n")]
            dg.append(st.mean(x["growth"] for x in dr))
        row = {"smooth": sm, "V2_SIGMA_H": sh, "V2P_SIGMA_H": ph, "V2P_TAU": tau, "clean_ape": st.mean(apes),
               "clean_rpe1s": st.mean(rpes), "score": st.mean(score), "deg_ape": st.mean(da),
               "deg_dropout_growth": st.mean(dg)}
        res.append(row)
        print("smooth %-5s V2_H %.0f V2P_H %4.1f tau %4.0f | clean APE %.3f RPE %.3f score %.3f | deg APE %.3f "
              "drop growth %.3f" % (sm, sh, ph, tau, row["clean_ape"], row["clean_rpe1s"], row["score"],
                                    row["deg_ape"], row["deg_dropout_growth"]), flush=True)
    wx.V2_SIGMA_H, wx.V2P_SIGMA_H, wx.V2P_TAU = base
    os.makedirs(os.path.join(ROOT, "Docs", "smooth"), exist_ok=True)
    with open(os.path.join(ROOT, "Docs", "smooth", "stepE-grid.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"tag": "stepE-grid", "date": time.strftime("%Y-%m-%d"), "cap": wx.SMOOTH_MAX_BLOCKS,
                   "results": res}, f, indent=1)
        f.write("\n")


if __name__ == "__main__":
    main()

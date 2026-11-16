"""Step 7b: ZUPT_DEN_ON off vs on with the reference estimator, on degraded copies made in memory.
Ground truth is used for SCORING and the false-ZUPT diagnosis only.

    python tools/zupt_eval.py MH_03_medium,MH_04_difficult,MH_05_difficult 19,20,21 10 out.json
    (sequences, seeds, healthy_s, output JSON; run from the repository root)
"""
import json, sys, statistics as st
import numpy as np
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from vortex import degrade as dg, scoring
from vortex.data import euroc
from vortex.core import witness as wx, strapdown as sd

def traj(t_ns, out):
    o = np.array(out); return scoring._clean(np.asarray(t_ns) / 1e9, o[:, :3], o[:, 3:7])[0]

def zupt_check(log, ref):
    ts = [L["t"] / 1e9 for L in log if L["zupt"]]
    bad = 0; worst = 0.0
    for tc in ts:
        i = np.searchsorted(ref.t, tc)
        if 5 <= i < len(ref.t) - 5:
            sp = np.linalg.norm((ref.p[i + 5] - ref.p[i - 5]) / (ref.t[i + 5] - ref.t[i - 5])); worst = max(worst, float(sp)); bad += int(sp > 0.1)
    return len(ts), bad, worst

seqs, seeds, healthy = sys.argv[1].split(","), [int(x) for x in sys.argv[2].split(",")], float(sys.argv[3])
res = []
for seq in seqs:
    d = "data/euroc/" + seq
    clean = euroc.read_imu_csv(d + "/mav0/imu0/data.csv"); ref = scoring.read_ground_truth(d)
    crows = sd.rows_from_raw(clean); als = {}
    for on in (False, True):
        log = []; out = wx.estimate(crows, zden=on, log=log); tr = traj(clean.t_ns, out)
        als[on] = scoring.fit_alignment(ref, tr, "se3")
        z = zupt_check(log, ref)
        res.append({"seq": seq, "seed": None, "on": on, "ape": scoring.score(ref, tr, align="given", given=als[on])["ape"]["rmse"], "zupts": z[0], "false": z[1], "worst": z[2]})
    for seed in seeds:
        raw, ev = dg.degrade(clean, dg.DegradeConfig(healthy_s=healthy), seed); rows = sd.rows_from_raw(raw)
        for on in (False, True):
            log = []; out = wx.estimate(rows, zden=on, log=log)
            r = scoring.score(ref, traj(raw.t_ns, out), align="given", given=als[on], events=ev); z = zupt_check(log, ref)
            res.append({"seq": seq, "seed": seed, "on": on, "ape": r["ape"]["rmse"], "blind_growth": r["phases"]["blind"]["growth"], "zupts": z[0], "false": z[1], "worst": z[2]})
for seq in seqs:
    for on in (False, True):
        c = [r for r in res if r["seq"] == seq and r["on"] == on and r["seed"] is None][0]
        rs = [r for r in res if r["seq"] == seq and r["on"] == on and r["seed"] is not None]
        print("%s %-3s clean APE %.4f zupts %d false %d | degraded mean APE %.3f max %.3f, mean zupts %.1f, false-ZUPT ticks %d (worst GT speed %.2f)" % (
            seq, "on" if on else "off", c["ape"], c["zupts"], c["false"], st.mean(r["ape"] for r in rs), max(r["ape"] for r in rs),
            st.mean(r["zupts"] for r in rs), sum(r["false"] for r in rs), max(r["worst"] for r in rs)))
json.dump(res, open(sys.argv[4], "w"), indent=1)

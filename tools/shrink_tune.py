"""Step L1 tuning (TUNING SET ONLY: MH_01/02 official copies, readings a and b, seeds 1-3, plus clean MH_01/02).

For each file: run pathfinder.py once (shipped settings, SHRINK_ON with alpha 1, so the output is unchanged
and the noise meter's sigma and class are recorded), then score the output with its positions scaled by
alpha about their centroid for every alpha on the grid (the same arithmetic as the switch, applied to the
6-decimal text), and the same for the positions reversed in time (the null floor). Scored as the organisers
score: SE3 Umeyama fitted on the run, APE; gap and blind RMSE from degrade.json.

Objective (fixed before the grid was run): per file, 30 APE/APE0 + 20 blind/blind0 + 10 gap/gap0, where
x0 is the same metric at alpha = 0 (= the never-moving floor), normalised by the weights present (clean files
have APE only), so the floor scores 60. Each class's alpha is the grid value with the lowest mean objective
over the files the meter puts in that class.

    python tools/shrink_tune.py [--out Docs/shrink/stepL1-tune.json]
"""
import json
import os
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from vortex import scoring  # noqa: E402

import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("pf_tune", os.path.join(ROOT, "tools", "pathfinder_lab.py"))  # SHRINK lives in the lab copy
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)

DATA = os.path.join(ROOT, "data", "euroc")
OFFICIAL = os.path.join(ROOT, "data", "official")
SEQS = ("MH_01_easy", "MH_02_easy")
GRID = (0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5)
W = {"ape": 30.0, "blind": 20.0, "gap": 10.0}


def files():
    for seq in SEQS:
        yield seq, os.path.join(DATA, seq, "mav0", "imu0", "data.csv"), None
        for rd in "ab":
            for s in (1, 2, 3):
                name = "%s_%s_s%d" % (seq, rd, s)
                d = os.path.join(OFFICIAL, name)
                with open(os.path.join(d, "degrade.json"), encoding="utf-8") as f:
                    ev = json.load(f)
                yield name, os.path.join(d, "mav0", "imu0", "data.csv"), ev


def metrics(ref, t, p, R, ev):
    e = scoring.Traj(t, p, R)
    r = scoring.score(ref, e, align="se3", rpe_deltas=(), events=ev)
    out = {"ape": r["ape"]["rmse"]}
    if ev:
        ph = r["phases"]
        drops = [d for d in ph["dropouts"] if d.get("n")]
        out["gap"] = sum(d["rmse"] for d in drops) / len(drops) if drops else None
        out["blind"] = ph["blind"].get("rmse")
    return out


def main(argv):
    out_path = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(ROOT, "Docs", "shrink",
                                                                                     "stepL1-tune.json")
    pf.SHRINK_ON = True
    pf.SHRINK_ALPHA_LO = pf.SHRINK_ALPHA_HI = 1.0
    tmp = tempfile.mkdtemp(prefix="vortex_shrink_")
    rows = []
    for name, imu, ev in files():
        base = name if ev is None else name.rsplit("_", 2)[0]
        ref = scoring.read_ground_truth(os.path.join(DATA, base))
        est = os.path.join(tmp, name + ".txt")
        pf.run(imu, est)
        sigma = pf.LAST["shrink"][0]
        cls = "lo" if sigma > pf.SHRINK_NOISE else "hi"
        a = np.loadtxt(est, ndmin=2)
        t, p = a[:, 0], a[:, 1:4]
        # same cleaning as scoring.read_tum (duplicate timestamps keep the first row)
        e0, _ = scoring.read_tum(est)
        keep = np.concatenate([[True], np.diff(t) > 0])
        t, p = t[keep], p[keep]
        assert np.array_equal(t, e0.t)
        c = p.mean(0)
        res = {"name": name, "sigma": sigma, "class": cls, "est": {}, "rev": {}}
        for alpha in GRID:
            q = c + alpha * (p - c)
            res["est"][str(alpha)] = metrics(ref, t, q, e0.R, ev)
            res["rev"][str(alpha)] = metrics(ref, t, q[::-1].copy(), e0.R, ev)
        rows.append(res)
        print("%-18s sigma %.4f class %s  APE a=0 %.3f a=1 %.3f" % (
            name, sigma, cls, res["est"]["0.0"]["ape"], res["est"]["1.0"]["ape"]))

    def objective(m, m0):
        num = den = 0.0
        for k, w in W.items():
            if m.get(k) is not None and m0.get(k):
                num += w * m[k] / m0[k]
                den += w
        return 60.0 * num / den

    summary = {}
    for cls in ("lo", "hi"):
        sub = [r for r in rows if r["class"] == cls]
        if not sub:
            continue
        tab = []
        for alpha in GRID:
            k = str(alpha)
            ob = np.mean([objective(r["est"][k], r["est"]["0.0"]) for r in sub])
            obr = np.mean([objective(r["rev"][k], r["est"]["0.0"]) for r in sub])
            mean = lambda key, which: float(np.mean([r[which][k][key] for r in sub if r[which][k].get(key) is not None]))  # noqa: E731,E501
            tab.append({"alpha": alpha, "objective": float(ob), "objective_rev": float(obr),
                        "ape": mean("ape", "est"), "ape_rev": mean("ape", "rev"),
                        "blind": mean("blind", "est") if any(r["est"][k].get("blind") is not None for r in sub) else None,
                        "gap": mean("gap", "est") if any(r["est"][k].get("gap") is not None for r in sub) else None})
        best = min(tab, key=lambda x: x["objective"])
        summary[cls] = {"files": [r["name"] for r in sub], "grid": tab, "best_alpha": best["alpha"]}
        print("\nclass %s (%d files: %s)" % (cls, len(sub), ", ".join(r["name"] for r in sub)))
        print("alpha  objective (floor 60)  reversed  | APE  APE reversed | blind  gap")
        for x in tab:
            print("%5.2f  %8.2f  %8.2f  | %.3f  %.3f | %s  %s %s" % (
                x["alpha"], x["objective"], x["objective_rev"], x["ape"], x["ape_rev"],
                "-" if x["blind"] is None else "%.3f" % x["blind"], "-" if x["gap"] is None else "%.3f" % x["gap"],
                "<- best" if x is best else ""))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"grid": GRID, "weights": W, "noise_threshold": pf.SHRINK_NOISE, "files": rows,
                   "summary": summary}, f, indent=1)
        f.write("\n")
    print("wrote", os.path.relpath(out_path, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

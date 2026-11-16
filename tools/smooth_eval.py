"""Step E: SMOOTH_ON off vs on with the reference estimator (vortex/core/witness.py). OFFLINE (reads GT
for SCORING only; the estimator never sees it).

    python tools/smooth_eval.py --tag NAME --seqs MH_01_easy,MH_02_easy [--copies MH_01_easy_s1,...] [--cap N]

Clean sequences come from data/euroc/<seq>, degraded copies from data/degraded/<copy> (made by
`python -m vortex.degrade`). Per setting (off, on): clean APE SE3 and RPE 1 s; degraded APE with the
SE3 alignment fitted on the SAME setting's clean run (align "given"), mean dropout growth, blind growth
and blind RMSE. --cap overrides SMOOTH_MAX_BLOCKS (storage study only). Writes Docs/smooth/<tag>.json.
"""
import json
import os
import statistics as st
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from vortex import scoring  # noqa: E402
from vortex.core import strapdown as sd, witness as wx  # noqa: E402
from vortex.data import euroc  # noqa: E402

OUT_DIR = os.path.join(ROOT, "Docs", "smooth")


def traj(t_ns, out):
    o = np.array(out)
    return scoring._clean(np.asarray(t_ns) / 1e9, o[:, :3], o[:, 3:7])[0]


def is_final(name):
    return name.startswith("V2_")


def main(argv):
    get = lambda k, d: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    tag = get("--tag", None)
    seqs = [s for s in get("--seqs", "").split(",") if s]
    copies = [s for s in get("--copies", "").split(",") if s]
    if not tag or not seqs:
        print(__doc__)
        return 2
    if any(is_final(n) for n in seqs + copies):
        print("refused: V2_* is the final test set")
        return 2
    if "--cap" in argv:
        wx.SMOOTH_MAX_BLOCKS = int(get("--cap", None))
    res = []
    als = {}
    for seq in seqs:
        d = os.path.join(ROOT, "data", "euroc", seq)
        raw = euroc.read_imu_csv(os.path.join(d, "mav0", "imu0", "data.csv"))
        ref = scoring.read_ground_truth(d)
        rows = sd.rows_from_raw(raw)
        for on in (False, True):
            t0 = time.perf_counter()
            out = wx.estimate(rows, smooth=on)
            wall = time.perf_counter() - t0
            tr = traj(raw.t_ns, out)
            als[(seq, on)] = scoring.fit_alignment(ref, tr, "se3")
            r = scoring.score(ref, tr, align="se3", rpe_deltas=(200,))
            res.append({"seq": seq, "copy": None, "on": on, "ape": r["ape"]["rmse"],
                        "rpe1s": r["rpe"]["200"]["rmse"], "wall_s": wall})
            print("%-20s %-3s APE %.4f RPE 1 s %.4f (%.1f s)" % (seq, "on" if on else "off", res[-1]["ape"],
                                                               res[-1]["rpe1s"], wall), flush=True)
    for cp in copies:
        base = cp.rsplit("_s", 1)[0]
        if (base, False) not in als:
            print("skip %s: clean %s not in --seqs" % (cp, base))
            continue
        d = os.path.join(ROOT, "data", "degraded", cp)
        raw = euroc.read_imu_csv(os.path.join(d, "mav0", "imu0", "data.csv"))
        with open(os.path.join(d, "degrade.json"), encoding="utf-8") as f:
            ev = json.load(f)
        ref = scoring.read_ground_truth(os.path.join(ROOT, "data", "euroc", base))
        rows = sd.rows_from_raw(raw)
        for on in (False, True):
            out = wx.estimate(rows, smooth=on)
            r = scoring.score(ref, traj(raw.t_ns, out), align="given", given=als[(base, on)],
                              rpe_deltas=(200,), events=ev)
            ph = r["phases"]
            drops = [x for x in ph["dropouts"] if x.get("n")]
            res.append({"seq": base, "copy": cp, "on": on, "ape": r["ape"]["rmse"],
                        "rpe1s": r["rpe"]["200"]["rmse"],
                        "dropout_growth": st.mean(x["growth"] for x in drops) if drops else None,
                        "dropout_rmse": st.mean(x["rmse"] for x in drops) if drops else None,
                        "blind_growth": ph["blind"].get("growth"), "blind_rmse": ph["blind"].get("rmse")})
            x = res[-1]
            print("%-20s %-3s APE %.4f RPE 1 s %.4f drop growth %s blind growth %s" % (
                cp, "on" if on else "off", x["ape"], x["rpe1s"],
                "-" if x["dropout_growth"] is None else "%.4f" % x["dropout_growth"],
                "-" if x["blind_growth"] is None else "%.4f" % x["blind_growth"]), flush=True)
    summary = {}
    for kind in ("clean", "degraded"):
        for on in (False, True):
            rs = [r for r in res if r["on"] == on and (r["copy"] is None) == (kind == "clean")]
            if not rs:
                continue
            m = {k: st.mean(r[k] for r in rs if r.get(k) is not None)
                 for k in ("ape", "rpe1s", "dropout_growth", "blind_growth", "blind_rmse")
                 if any(r.get(k) is not None for r in rs)}
            m["n"] = len(rs)
            summary["%s_%s" % (kind, "on" if on else "off")] = m
            print("MEAN %-8s %-3s n %2d  %s" % (kind, "on" if on else "off", len(rs),
                                               "  ".join("%s %.4f" % kv for kv in m.items() if kv[0] != "n")))
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, tag + ".json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"tag": tag, "date": time.strftime("%Y-%m-%d"), "cap": wx.SMOOTH_MAX_BLOCKS,
                   "seqs": seqs, "copies": copies, "summary": summary, "results": res}, f, indent=1)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Step 8b (W6): coverage of the per-row position sigma of the reference estimator.

For each sequence: the clean run and seeded degraded copies made in memory (vortex.degrade defaults,
`--healthy` seconds untouched). Each row's 3D position error (SE3 alignment of the clean run, align
"given") is compared with its sigma (witness.row_sigma). GROUND TRUTH IS USED FOR SCORING ONLY; the
estimator never sees it and never reads its own sigma.

    python tools/coverage.py --tag NAME --seqs MH_01_easy,MH_02_easy --seeds 100,101 [--healthy 10]
                             [--k68 K --k95 K]     # without k: fitted on this set (tuning)
    python tools/coverage.py --render             # rebuilds Docs/COVERAGE.md from Docs/coverage/*.json

Rows before the calibration anchor have no sigma (NaN) and are left out (counted).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from vortex import degrade as dg, scoring  # noqa: E402
from vortex.core import strapdown as sd, witness as wx  # noqa: E402
from vortex.data import euroc  # noqa: E402

OUT_DIR = os.path.join(ROOT, "Docs", "coverage")
DOC = os.path.join(ROOT, "Docs", "COVERAGE.md")
PHASES = ("clean", "healthy", "degraded", "dropout", "blind")


def _commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True).stdout.strip() or "?"
    except OSError:
        return "?"


def _rows_err_sig(raw, out, sig, ref, al):
    """Per matched row: (time s, 3D error m, sigma m)."""
    t = raw.t_ns / 1e9
    o = np.array(out)
    est, _ = scoring._clean(t, o[:, :3], o[:, 3:7])
    s_by_t = {}
    for ti, si in zip(t, sig):
        s_by_t.setdefault(float(ti), si)
    rs, es = scoring.associate(ref, est)
    e = np.linalg.norm(scoring.apply(es, al).p - rs.p, axis=1)
    s = np.array([s_by_t[float(x)] for x in es.t])
    return es.t, e, s


def _phase(trel, ev):
    if ev is None:
        return np.array(["clean"] * len(trel), dtype=object)
    ph = np.array(["degraded"] * len(trel), dtype=object)
    ph[trel < ev.get("healthy_end_s", 0.0)] = "healthy"
    for a, b in ev.get("dropouts_s", []):
        ph[(trel >= a) & (trel < b)] = "dropout"
    if ev.get("failure_at_s") is not None:
        ph[trel >= ev["failure_at_s"]] = "blind"
    return ph


def collect(seqs, seeds, healthy):
    """Pooled arrays: error, sigma, phase, run id."""
    E, S, PH, RUN = [], [], [], []
    no_sig = 0
    for seq in seqs:
        d = os.path.join(ROOT, "data", "euroc", seq)
        clean = euroc.read_imu_csv(os.path.join(d, "mav0", "imu0", "data.csv"))
        ref = scoring.read_ground_truth(d)
        crows = sd.rows_from_raw(clean)
        sig = []
        out = wx.estimate(crows, sig=sig)
        o = np.array(out)
        al = scoring.fit_alignment(ref, scoring._clean(clean.t_ns / 1e9, o[:, :3], o[:, 3:7])[0], "se3")
        runs = [(None, clean, out, sig)]
        for seed in seeds:
            raw, ev = dg.degrade(clean, dg.DegradeConfig(healthy_s=healthy), seed)
            sg = []
            runs.append((ev, raw, wx.estimate(sd.rows_from_raw(raw), sig=sg), sg))
        for ev, raw, out, sg in runs:
            t, e, s = _rows_err_sig(raw, out, sg, ref, al)
            ok = np.isfinite(s)
            no_sig += int((~ok).sum())
            t0 = (ev["t0_ns"] if ev else int(raw.t_ns[0])) / 1e9
            E.append(e[ok])
            S.append(s[ok])
            PH.append(_phase(t[ok] - t0, ev))
            RUN.append(np.array(["%s/%s" % (seq, "clean" if ev is None else ev["seed"])] * int(ok.sum()), dtype=object))
            print(seq, "clean" if ev is None else ev["seed"], "rows %d, median err %.2f m, median sigma %.2f m" % (
                ok.sum(), np.median(e[ok]), np.median(s[ok])), flush=True)
    return np.concatenate(E), np.concatenate(S), np.concatenate(PH), np.concatenate(RUN), no_sig


def _spearman(a, b):
    ra = np.argsort(np.argsort(a))
    rb = np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1]) if len(a) > 2 else float("nan")


def table(E, S, PH, k68, k95):
    r = E / np.maximum(S, 1e-9)
    rows = []
    for ph in ("all",) + PHASES:
        m = np.ones(len(E), bool) if ph == "all" else PH == ph
        if not m.any():
            continue
        rows.append({"phase": ph, "rows": int(m.sum()), "median_sigma": float(np.median(S[m])),
                     "median_err": float(np.median(E[m])), "cov68": float(np.mean(r[m] <= k68)),
                     "cov95": float(np.mean(r[m] <= k95)), "spearman": _spearman(S[m], E[m])})
    return rows


def render():
    runs = []
    for name in sorted(os.listdir(OUT_DIR)) if os.path.isdir(OUT_DIR) else []:
        if name.endswith(".json"):
            with open(os.path.join(OUT_DIR, name), encoding="utf-8") as f:
                runs.append(json.load(f))
    L = ["# Per-row confidence coverage (step 8b, W6)", "",
         "Generated by `python tools/coverage.py --render` from `Docs/coverage/*.json`; do not edit by hand.",
         "Sigma: `witness.row_sigma` (reference estimator), a 3D position standard deviation per row. Error:",
         "3D position error after the clean run's SE3 alignment. Bound = k x sigma, k fitted on the tuning",
         "set so that 68 % / 95 % of its rows fall inside. Ground truth is used for scoring only. Rows before",
         "the anchor have no sigma and are left out.", ""]
    for run in runs:
        L += ["## %s" % run["tag"], "",
              "Commit %s, %s. Sequences %s; clean + seeds %s (healthy %g s). k68 = %.3f, k95 = %.3f (%s). "
              "Rows without sigma: %d." % (run["commit"], run["date"], ", ".join(run["seqs"]),
                                          ",".join(str(x) for x in run["seeds"]), run["healthy"], run["k68"],
                                          run["k95"], "fitted here" if run["fitted"] else "from tuning",
                                          run["no_sigma"]), "",
              "| Phase | Rows | Median sigma m | Median error m | Inside k68 sigma | Inside k95 sigma | "
              "Spearman(sigma, error) |", "|---|---|---|---|---|---|---|"]
        for r in run["table"]:
            L.append("| %s | %d | %.2f | %.2f | %.1f %% | %.1f %% | %.2f |" % (
                r["phase"], r["rows"], r["median_sigma"], r["median_err"], 100 * r["cov68"], 100 * r["cov95"],
                r["spearman"]))
        L.append("")
    with open(DOC, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))
    print("wrote", DOC)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tag")
    ap.add_argument("--seqs")
    ap.add_argument("--seeds", default="")
    ap.add_argument("--healthy", type=float, default=10.0)
    ap.add_argument("--k68", type=float)
    ap.add_argument("--k95", type=float)
    ap.add_argument("--render", action="store_true")
    a = ap.parse_args(argv)
    if a.render:
        render()
        return 0
    if not a.tag or not a.seqs:
        ap.error("--tag and --seqs are needed")
    seeds = [int(x) for x in a.seeds.split(",") if x]
    E, S, PH, _, no_sig = collect(a.seqs.split(","), seeds, a.healthy)
    fitted = a.k68 is None or a.k95 is None
    r = E / np.maximum(S, 1e-9)
    k68 = float(np.percentile(r, 68)) if a.k68 is None else a.k68
    k95 = float(np.percentile(r, 95)) if a.k95 is None else a.k95
    res = {"tag": a.tag, "commit": _commit(), "date": datetime.date.today().isoformat(),
           "seqs": a.seqs.split(","), "seeds": seeds, "healthy": a.healthy, "k68": k68, "k95": k95,
           "fitted": fitted, "no_sigma": no_sig, "table": table(E, S, PH, k68, k95)}
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, a.tag + ".json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(res, f, indent=1)
    render()
    return 0


if __name__ == "__main__":
    sys.exit(main())

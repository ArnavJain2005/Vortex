"""Step 7 item 4 (V5 walking rhythm): feasibility on the TUM-VI TUNING rooms only. EXPLORATORY analysis tool:
it reads ground truth (mocap) to judge the signals; nothing here is an estimator input.

    python tools/v5_feasibility.py [--rooms dataset-room1_512_16,dataset-room2_512_16]   # Docs/tumvi/v5-feasibility.json

1. Rhythm: per 4 s window (hop 1 s) the dominant frequency of the vertical specific force (gravity direction
   from a 1 s mean of the accelerometer) in 0.8-3.5 Hz, the share of power in that peak, and its correlation
   with the ground-truth horizontal speed.
2. Direction, best case: the horizontal accelerometer rotated to the world with the GROUND-TRUTH attitude;
   principal axis per window (2 s and 4 s, half overlap; raw and band-passed 1.2-2.5 Hz) against the ground-
   truth direction of travel, |cos| over windows with mean speed >= 0.4 m/s. A random axis gives median 0.707.
3. Speed: the shipped pathfinder.py's horizontal speed against ground truth (clean and official copies s1).
Never reads V2_* or TUM-VI room5/room6 (the final sets) or held-out rooms by default.
"""
import importlib.util
import json
import os
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINAL = ("V2_", "dataset-room5", "dataset-room6")
CHANCE = 0.7071


def load(room):
    d = os.path.join(ROOT, "data", "tumvi", room, "mav0")
    imu = np.loadtxt(os.path.join(d, "imu0", "data.csv"), delimiter=",", comments="#")
    gt = np.loadtxt(os.path.join(d, "mocap0", "data.csv"), delimiter=",", comments="#")
    return imu, gt


def movmean(x, n):
    k = np.ones(n) / n
    if x.ndim == 1:
        return np.convolve(x, k, mode="same")
    return np.stack([np.convolve(x[:, i], k, mode="same") for i in range(x.shape[1])], 1)


def qrot(q, v):
    """q (w, x, y, z) body to world, v body vectors."""
    w, x, y, z = q.T
    r = np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], -1),
                  np.stack([2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)], -1),
                  np.stack([2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)], -1)], 1)
    return np.einsum("nij,nj->ni", r, v)


def gt_speed_at(gt, t_ns):
    tg = gt[:, 0] * 1e-9
    v = np.gradient(movmean(gt[:, 1:4], 25), tg, axis=0)
    idx = np.clip(np.searchsorted(gt[:, 0], t_ns), 0, len(gt) - 1)
    return v[idx], np.abs(gt[idx, 0] - t_ns) < 2e7, idx


def rhythm(imu, gt):
    a = imu[:, 4:7]
    g = movmean(a, 200)
    g /= np.linalg.norm(g, axis=1, keepdims=True)
    fz = np.sum(a * g, axis=1)
    fz = fz - movmean(fz, 200)
    v, ok, _ = gt_speed_at(gt, imu[:, 0])
    sh = np.linalg.norm(v[:, :2], axis=1)
    w = 800
    f = np.fft.rfftfreq(w, 0.005)
    band = (f > 0.8) & (f < 3.5)
    rows = []
    for i0 in range(0, len(a) - w, 200):
        sl = slice(i0, i0 + w)
        if not ok[sl].all():
            continue
        p = np.abs(np.fft.rfft(fz[sl] * np.hanning(w))) ** 2
        k = int(np.argmax(p * band))
        rows.append((f[k], p[k - 1:k + 2].sum() / p[(f > 0.3) & (f < 10)].sum(), fz[sl].std(), sh[sl].mean()))
    r = np.array(rows)
    return {"windows": len(r), "freq_median_hz": float(np.median(r[:, 0])),
            "peak_share_median": float(np.median(r[:, 1])),
            "share_gt_0p3": float((r[:, 1] > 0.3).mean()),
            "gt_speed_mean": float(r[:, 3].mean()),
            "corr_freq_speed": float(np.corrcoef(r[:, 0], r[:, 3])[0, 1]),
            "corr_share_speed": float(np.corrcoef(r[:, 1], r[:, 3])[0, 1]),
            "corr_fzstd_speed": float(np.corrcoef(r[:, 2], r[:, 3])[0, 1])}


def direction(imu, gt):
    v, ok, idx = gt_speed_at(gt, imu[:, 0])
    aw = qrot(gt[idx, 4:8], imu[:, 4:7])[:, :2]
    f = np.fft.rfftfreq(len(aw), 0.005)
    x = np.fft.rfft(aw - aw.mean(0), axis=0)
    x[(f < 1.2) | (f > 2.5)] = 0
    bp = np.fft.irfft(x, n=len(aw), axis=0)
    out = {}
    for name, sig in (("raw", aw), ("band_1p2_2p5hz", bp)):
        for w in (400, 800):
            cs = []
            for i0 in range(0, len(aw) - w, w // 2):
                sl = slice(i0, i0 + w)
                if not ok[sl].all():
                    continue
                vm = v[sl, :2].mean(0)
                s = float(np.linalg.norm(vm))
                if s < 0.4:
                    continue
                h = sig[sl] - sig[sl].mean(0)
                d = np.linalg.eigh(h.T @ h)[1][:, 1]
                cs.append(abs(float(d @ vm)) / s)
            c = np.array(cs)
            out["%s_%ds" % (name, w // 200)] = {"windows": len(c), "abs_cos_median": float(np.median(c)),
                                                 "share_abs_cos_gt_0p9": float((c > 0.9).mean())}
    return out


def speed(room, gt):
    spec = importlib.util.spec_from_file_location("pf_v5", os.path.join(ROOT, "pathfinder.py"))
    pf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pf)
    tmp = tempfile.mkdtemp(prefix="vortex_v5_")
    tg = gt[:, 0] * 1e-9
    sg = np.linalg.norm(np.gradient(movmean(gt[:, 1:3], 25), tg, axis=0), axis=1)[25:-25]
    res = {"gt_median": float(np.median(sg))}
    for copy in ("clean", "a_s1", "b_s1"):
        src = (os.path.join(ROOT, "data", "tumvi", room) if copy == "clean" else
               os.path.join(ROOT, "data", "official_tumvi", "%s_%s" % (room, copy)))
        src = os.path.join(src, "mav0", "imu0", "data.csv")
        if not os.path.isfile(src):
            continue
        dst = os.path.join(tmp, "est.txt")
        pf.run(src, dst)
        e = np.loadtxt(dst)
        e = e[np.unique(e[:, 0], return_index=True)[1]]       # official copies duplicate rows
        se = np.linalg.norm(np.gradient(movmean(e[:, 1:3], 50), e[:, 0], axis=0), axis=1)[50:-50]
        res[copy + "_median"] = float(np.median(se))
        os.remove(dst)
    return res


def main(argv):
    rooms = (argv[argv.index("--rooms") + 1].split(",") if "--rooms" in argv
             else ["dataset-room1_512_16", "dataset-room2_512_16"])
    assert not any(r.startswith(FINAL) for r in rooms), "final set"
    out = {"chance_abs_cos_median": CHANCE, "rooms": {}}
    for room in rooms:
        imu, gt = load(room)
        r = {"rhythm": rhythm(imu, gt), "direction_gt_attitude": direction(imu, gt), "speed": speed(room, gt)}
        out["rooms"][room] = r
        rh, sp = r["rhythm"], r["speed"]
        print("%s rhythm: peak %.2f Hz, share %.2f (%.0f %% of windows > 0.3); corr with GT speed: freq %+.2f, "
              "share %+.2f, bounce %+.2f" % (room, rh["freq_median_hz"], rh["peak_share_median"],
                                             100 * rh["share_gt_0p3"], rh["corr_freq_speed"],
                                             rh["corr_share_speed"], rh["corr_fzstd_speed"]))
        for k, d in r["direction_gt_attitude"].items():
            print("  direction %-20s n %3d  |cos| median %.2f (chance %.2f), > 0.9 in %.0f %%" % (
                k, d["windows"], d["abs_cos_median"], CHANCE, 100 * d["share_abs_cos_gt_0p9"]))
        print("  horizontal speed median: GT %.2f m/s; estimator %s" % (sp["gt_median"], ", ".join(
            "%s %.2f" % (k[:-7], v) for k, v in sp.items() if k != "gt_median")))
    with open(os.path.join(ROOT, "Docs", "tumvi", "v5-feasibility.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

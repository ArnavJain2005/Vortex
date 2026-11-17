"""Check the strapdown integrator on a real EuRoC sequence. OFFLINE ANALYSIS: reads ground truth.

Two set-ups, both starting at `--start` seconds after the first ground-truth row (choose a moment
when the vehicle rests; on MH_01 it sits on the ground from about 20 to 44 s):
  ORACLE   initial attitude, gyro bias and accel bias from ground truth (labelled oracle: no real
           system has these). Shows whether frames, signs and time base are right.
  OWN INIT vortex/core/strapdown.py's own initialisation on the first second from `--start`
           (no ground truth), compared after fitting yaw and origin (which the scorer aligns).
For each duration it prints the end position error and the ground-truth path length.

Usage: python tools/integrator_check.py data/euroc/MH_01_easy [--start 25] [--durations 10,30,60]
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from vortex.core import strapdown as sd  # noqa: E402
from vortex.data import euroc  # noqa: E402


def gt_full(seq):
    for name in euroc.GT_FOLDERS:
        p = os.path.join(seq, "mav0", name, "data.csv")
        if os.path.isfile(p):
            g = np.loadtxt(p, delimiter=",", comments="#")
            return g[:, 0] / 1e9, g[:, 1:]
    raise FileNotFoundError("no ground truth under %s" % seq)


def yaw_origin_error(P, Q):
    """|P - Q| after the best rotation about z applied to P (both start at the origin)."""
    H = P[:, :2].T @ Q[:, :2]
    U, _, Vt = np.linalg.svd(H)
    D = np.diag([1.0, np.sign(np.linalg.det(Vt.T @ U.T))])
    R = Vt.T @ D @ U.T
    P2 = P.copy()
    P2[:, :2] = P[:, :2] @ R.T
    return np.linalg.norm(P2 - Q, axis=1)


def check(seq, start, durations):
    rows = sd.rows_from_raw(euroc.read_imu_csv(euroc.imu_path(seq)))
    t_imu = np.array([np.nan if r[0] is None else r[0] for r in rows], dtype=float) / 1e9
    tg, a = gt_full(seq)
    res = []
    for dur in durations:
        t0 = tg[0] + start
        i0, i1 = int(np.searchsorted(t_imu, t0)), int(np.searchsorted(t_imu, t0 + dur))
        j0 = int(np.searchsorted(tg, t_imu[i0]))
        p0, q0 = a[j0, 0:3], a[j0, 3:7] / np.linalg.norm(a[j0, 3:7])
        bw, ba = a[j0, 10:13], a[j0, 13:16]
        te = t_imu[i0:i1]
        pg = np.column_stack([np.interp(te, tg, a[:, k]) for k in range(3)]) - p0
        seg = [(t, tuple(np.asarray(v) - np.r_[0, 0, 0, ba])) for t, v in rows[i0:i1]]
        oracle = np.array(sd.estimate(seg, init=sd.Init(tuple(q0), tuple(bw), 9.81, True, 0)))
        e_or = np.linalg.norm(oracle[:, :3] - pg, axis=1)
        own_init = sd.initialise(sd.init_window(rows[i0:i1]))
        own = np.array(sd.estimate(rows[i0:i1], init=own_init))
        e_own = yaw_origin_error(own[:, :3], pg)
        r = {"start_s": start, "duration_s": dur, "oracle_end_m": float(e_or[-1]),
             "own_end_m": float(e_own[-1]), "own_still": own_init.still, "own_bg": own_init.bg,
             "gt_bg": tuple(float(x) for x in bw), "gt_path_m": float(np.sum(np.linalg.norm(np.diff(pg, axis=0), axis=1)))}
        res.append(r)
        print("%s start %.0f s, %3.0f s: ORACLE end error %7.2f m | OWN INIT (still=%s) end error %7.2f m "
              "(yaw + origin fitted) | ground-truth path %5.1f m"
              % (os.path.basename(os.path.normpath(seq)), start, dur, r["oracle_end_m"], own_init.still,
                 r["own_end_m"], r["gt_path_m"]))
    print("  own gyro bias %s rad/s; ground-truth gyro bias %s" % (
        tuple(round(x, 4) for x in res[0]["own_bg"]), tuple(round(x, 4) for x in res[0]["gt_bg"])))
    return res


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    get = lambda k, d: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    seqs = [x for i, x in enumerate(argv) if not x.startswith("--") and (i == 0 or argv[i - 1] not in ("--start", "--durations"))]
    if not seqs:
        print(__doc__)
        return 2
    start = float(get("--start", 25.0))
    durs = [float(x) for x in get("--durations", "10,30,60").split(",")]
    for s in seqs:
        check(s, start, durs)
    return 0


if __name__ == "__main__":
    sys.exit(main())

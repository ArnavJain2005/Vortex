"""CC-3 exploration, 19 Nov 2026 (TUNING rooms only; EXPLORATORY, not shipped, no switch in pathfinder.py).
When the shipped stillness search finds no still run, calibrate from the quietest window of the opening
seconds instead of falling back to zero bias. Env CALP = "H,W,K,MODE":
H horizon s, W window s, K weight of mean |w| (rad/s) against std(|a|) (m/s^2), MODE both|dir|both-m|dir-m.
MODE both: gyro bias and gravity from the window; dir: gravity direction only (bias 0, G_DEFAULT); a trailing
"-m" keeps the moving-start covariance (still0 False) instead of the calibrated one.

    CALP=20,1,10,dir python tools/eval_euroc.py --tag cc3x-dir --official --root data/tumvi \
        --main tools/cc3_calprobe.py --seqs dataset-room1_512_16_a_s1,...   # Docs/tumvi/cc3x-*.json
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pathfinder as pf

H, W, K, MODE = os.environ.get("CALP", "20,1,10,both").split(",")
H, W, K = float(H), float(W), float(K)
_orig = pf._calibrate


def _quiet(src):
    bs = pf.BLOCK_S
    bns = int(bs * 1e9)
    nb = int(H / bs)
    n = [0] * nb
    s = [[0.0] * 6 for _ in range(nb)]
    an = [0.0] * nb
    an2 = [0.0] * nb
    wn = [0.0] * nb
    t0 = None
    with pf._open_rows(src) as f:
        for line in f:
            r = pf._parse(line)
            if r is None:
                continue
            t, v = r
            if t is None or not pf._valid(v):
                continue
            if t0 is None:
                t0 = t
            if t >= t0 + nb * bns:
                break
            if t < t0:
                continue
            j = (t - t0) // bns
            n[j] += 1
            for i in range(6):
                s[j][i] += v[i]
            a = math.sqrt(v[3] * v[3] + v[4] * v[4] + v[5] * v[5])
            an[j] += a
            an2[j] += a * a
            wn[j] += math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if t0 is None:
        return None
    k = max(1, round(W / bs))
    best = None
    for j0 in range(nb - k + 1):
        cnt = sum(n[j0:j0 + k])
        if cnt < k * pf.BLOCK_MIN_ROWS:
            continue
        ma = sum(an[j0:j0 + k]) / cnt
        va = sum(an2[j0:j0 + k]) / cnt - ma * ma
        mw = sum(wn[j0:j0 + k]) / cnt
        score = math.sqrt(max(va, 0.0)) + K * mw
        if best is None or score < best[0]:
            best = (score, j0, cnt)
    if best is None:
        return None
    _, j0, cnt = best
    m = [sum(s[j][i] for j in range(j0, j0 + k)) / cnt for i in range(6)]
    if m[0] ** 2 + m[1] ** 2 + m[2] ** 2 > pf.BG_MAX ** 2:
        m[0] = m[1] = m[2] = 0.0
    qw, qx, qy, qz, fn = pf._tilt(m[3], m[4], m[5])
    if not pf.ACC_NORM_MIN <= fn <= pf.ACC_NORM_MAX:
        return None
    t_mid = t0 + j0 * bns + (k * bns) // 2
    return t_mid, qw, qx, qy, qz, m[0], m[1], m[2], fn


def _cal(src):
    c = _orig(src)
    if c is not None:
        return c
    q = _quiet(src)
    if q is None:
        return None
    if MODE.startswith("dir"):
        USED[0] = True
        return q[:5] + (0.0, 0.0, 0.0, pf.G_DEFAULT)
    USED[0] = True
    return q


USED = [False]
_kfi = pf._kf_init


def _kf_init(still0, *a):
    if USED[0] and MODE.endswith("-m"):          # keep the moving-start covariance
        still0 = False
    return _kfi(still0, *a)


pf._calibrate = _cal
pf._kf_init = _kf_init
if __name__ == "__main__":
    sys.exit(pf.main(sys.argv))

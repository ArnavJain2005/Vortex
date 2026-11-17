"""Vortex, Samsung PRISM XR Hackathon 2026, Track 3: trajectory from a degraded IMU.

    python -S main.py <imu0/data.csv> <estimated_trajectory.txt>

This is the estimator; main.py is a stub that imports it so that Python can load its compiled
bytecode instead of compiling this source on every run (step 9a). `python -S pathfinder.py IN OUT`
gives the same output. Pure Python, standard library only, single thread, offline, deterministic. Standalone: it never
imports the `vortex` package. The readable reference implementation is vortex/core/witness.py (on
top of vortex/core/strapdown.py); tests/test_core_equivalence.py keeps the two in lockstep (same
rules, same arithmetic order).

Output: one line `timestamp tx ty tz qx qy qz qw` per input data row, same order. A data row is any
line that is not blank and does not start with '#' (vortex/rowspec.py states the same rule). The
timestamp is the input ns value with the decimal point moved 9 digits left, done on the text, so it
is exact. A row whose timestamp is not an integer repeats the previous row's timestamp.

STATUS (steps 7a + 6c + 8a + 6d + 6e): self-calibration on the longest still run in the first 60 s (gyro bias, g, tilt),
backward integration from mid-run over the rows before it (dead reckoning, no witnesses), then a
forward error-state Kalman filter (15 states, one covariance step per 0.25 s tick) with the
witnesses V1 stillness (ZUPT + gyro bias) and V2 flight envelope (speed and volume); dropouts and
gaps add covariance learned from the recent motion (GAP_ON); a noise meter (JAM_ON) is built but off;
dead sensors (stuck or all-zero rows) are treated as missing (DEAD_ON) and velocity decays toward 0 in gaps (FC_ON);
rows before the anchor keep the anchor's position, attitude from the backward pass (PRE_HOLD);
if no still run passes the strict test, calibration retries with the white noise removed (CAL_NOISE_ON);
fallback to the step 6a first-second initialisation. Rules: vortex/core/witness.py. Performance: Docs/BUDGET.md.

Passes: (1) calibration scan of the first 60 s; (2) rows before the anchor are stored (64 bytes per
row, at most PRE_MAX_ROWS) and integrated backward; (3) one streaming forward pass writes every row.
"""
import math
import os
import sys
from array import array

READ_BUF = 1 << 16   # 64 KB: 1 MB gave no speed-up and +0.9 MB RSS (Docs/FLOOR.md)
CHUNK = 256          # output lines per write(): 4096 cost +1.1 MB tracemalloc, no speed-up
FMT = b"%s.%s %.6f %.6f %.6f %.7f %.7f %.7f %.7f\n"
BOM = b"\xef\xbb\xbf"
NAN = float("nan")

# Estimator parameters: identical to vortex/core/strapdown.py (a test checks), sources noted there.
INIT_S = 1.0
INIT_MAX_ROWS = 2000
STILL_GYRO_STD = 0.02
STILL_ACC_STD = 0.1
G_DEFAULT = 9.81
MAX_DT = 0.1
MAX_JUMP_S = 30.0
MAX_SUMSQ = 1e8
CAL_HORIZON_S = 60.0
BLOCK_S = 0.25
BLOCK_MIN_ROWS = 5
MIN_STILL_S = 1.0
STUCK_STD = 1e-5
ACC_NORM_MIN = 8.8
ACC_NORM_MAX = 10.8
STEADY_GYRO = 0.005
STEADY_ACC = 0.05
TRIM_S = 0.5
PRE_MAX_ROWS = 15000
CAL_NOISE_ON = True
# step 7a filter and witnesses: identical to vortex/core/witness.py (a test checks), sources noted there
TICK_S = BLOCK_S
GYRO_NOISE = 1.7e-3
ACC_NOISE = 2.0e-2
GYRO_WALK = 1.9e-4
ACC_WALK = 3.0e-3
P0_VEL = 0.01
P0_TILT = 0.02
P0_YAW = 0.0
P0_BG = 2e-3
P0_BA = 0.2
P0_TILT_FALLBACK = 0.1
P0_BG_FALLBACK = 0.02
ZUPT_SIGMA = 0.02
ZARU_SIGMA_MIN = 5e-4
V2_SIGMA_H = 2.0
V2_SIGMA_V = 0.3
V2P_SIGMA_H = 5.0
V2P_SIGMA_V = 2.0
V2P_TAU = 10.0
LEARN_ON = False             # Step 4: envelope learned per file (vortex/core/witness.py learn_env)
LEARN_FRAC = 0.3
LEARN_ITERS = 2
LEARN_K = 1.0
LEARN_MIN = (0.1, 0.05, 0.3, 0.1)
LEARN_MAX = (4.0, 1.0, 10.0, 4.0)
V1_ON = True
V2_ON = True
V2P_ON = True
JAM_TAU = 2.0
GAP_H_TICKS = 8
GAP_TAU = 20.0
JAM_ON = False
GAP_ON = True
STUCK_ROWS = 5
DEAD_ON = True
FC_TAU = 0.5
FC_ON = True
PRE_HOLD = True
N = 15

LAST = {"pre_rows": 0, "calibrated": False, "zupt_ticks": 0, "ba": (0.0, 0.0, 0.0), "jam": (-1.0, -1.0),
        "tilt2": -1.0}  # for tests/benchmarks


def _slow_fields(p):
    """Bad, empty or short value fields (rare): each unparseable value becomes NaN."""
    v = [NAN] * 6
    for i in range(1, min(len(p), 7)):
        try:
            v[i - 1] = float(p[i])
        except ValueError:
            pass
    return v


def _init_window(src):
    """Values of the valid rows in [t0, t0 + INIT_S] (t0 = first valid row). Same row rules as run()."""
    t0 = None
    t_end = 0
    win = []
    with open(src, "rb", buffering=READ_BUF) as f:
        if f.peek(3)[:3] == BOM:
            f.read(3)
        for line in f:
            if line[0] < 48:
                line = line.strip()
                if not line or line[0] == 35:
                    continue
            p = line.split(b",")
            ts = p[0]
            if not ts.isdigit():
                ts = ts.strip()
                if not ts.isdigit():
                    continue
            try:
                v = [float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5]), float(p[6])]
            except (ValueError, IndexError):
                v = _slow_fields(p)
            if not (v[0] * v[0] + v[1] * v[1] + v[2] * v[2] + v[3] * v[3] + v[4] * v[4] + v[5] * v[5]
                    < MAX_SUMSQ):
                continue
            t = int(ts)
            if t0 is None:
                t0 = t
                t_end = t0 + int(INIT_S * 1e9)
            if t > t_end:
                break
            if t >= t0:
                win.append(v)
                if len(win) >= INIT_MAX_ROWS:
                    break
    return win


def _parse(line):
    """One file line -> None (not a data row) or (t_ns or None, six floats). Same rules as run()."""
    if line[0] < 48:
        line = line.strip()
        if not line or line[0] == 35:
            return None
    p = line.split(b",")
    ts = p[0]
    if not ts.isdigit():
        ts = ts.strip()
    try:
        v = [float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5]), float(p[6])]
    except (ValueError, IndexError):
        v = _slow_fields(p)
    return (int(ts) if ts.isdigit() else None), v


def _valid(v):
    return v[0] * v[0] + v[1] * v[1] + v[2] * v[2] + v[3] * v[3] + v[4] * v[4] + v[5] * v[5] < MAX_SUMSQ


def _open_rows(src):
    f = open(src, "rb", buffering=READ_BUF)
    if f.peek(3)[:3] == BOM:
        f.read(3)
    return f


def _tilt(fx, fy, fz):
    fn = math.sqrt(fx * fx + fy * fy + fz * fz)
    ux, uy, uz = fx / fn, fy / fn, fz / fn
    if 1.0 + uz < 1e-9:
        return 0.0, 1.0, 0.0, 0.0, fn
    w, x, y = 1.0 + uz, uy, -ux
    k = 1.0 / math.sqrt(w * w + x * x + y * y)
    return w * k, x * k, y * k, 0.0, fn


def _best_run(n, s, still, w=None):
    """Longest run of still, pairwise steady bins (strapdown._best_run); w: per-bin white-noise
    variances (6 per bin) widen the steady tolerances (step 6e)."""
    sqrt = math.sqrt
    nb = len(n)
    best_j, best_len, j0 = 0, 0, -1
    for j in range(nb + 1):
        st = j < nb and still[j]
        steady = True
        if st and j0 >= 0:
            oa, ob = 6 * (j - 1), 6 * j
            for i in range(6):
                tol = STEADY_GYRO if i < 3 else STEADY_ACC
                if w is not None:
                    tol += 3.0 * sqrt(w[oa + i] / n[j - 1] + w[ob + i] / n[j])
                d = s[oa + i] / n[j - 1] - s[ob + i] / n[j]
                if d >= tol or d <= -tol:
                    steady = False
                    break
        if st and j0 >= 0 and not steady:
            if j - j0 > best_len:
                best_j, best_len = j0, j - j0
            j0 = j
        elif st and j0 < 0:
            j0 = j
        if not st and j0 >= 0:
            if j - j0 > best_len:
                best_j, best_len = j0, j - j0
            j0 = -1
    return best_j, best_len


def _still_denoised(src, t0, n, s, ss):
    """Step 6e: a second scan of the calibration horizon (only when no strict still run exists) for the
    per-bin second differences. Returns (still flags with the white-noise variance removed, per-bin
    white-noise variances) (strapdown.noise_bins, bin_is_still_denoised, white_var)."""
    sqrt = math.sqrt
    nb = len(n)
    bns = int(BLOCK_S * 1e9)
    t_end = t0 + nb * bns
    max_dt_ns = MAX_DT * 1e9
    nd = [0] * nb
    d2 = [0.0] * (6 * nb)
    h1 = h2 = None
    jl = tl = -1
    with _open_rows(src) as f:
        for line in f:
            r = _parse(line)
            if r is None:
                continue
            t, v = r
            if t is None or not _valid(v) or t < t0:
                h1 = h2 = None
                continue
            if t >= t_end:
                break
            j = (t - t0) // bns
            if h1 is not None and (j != jl or not 0 < t - tl <= max_dt_ns):
                h1 = h2 = None
            if h2 is not None:
                nd[j] += 1
                o = 6 * j
                for i in range(6):
                    d = v[i] - 2.0 * h1[i] + h2[i]
                    d2[o + i] += d * d
            h2, h1, jl, tl = h1, v, j, t
    w = [0.0] * (6 * nb)
    for j in range(nb):
        if nd[j]:
            for i in range(6):
                w[6 * j + i] = d2[6 * j + i] / nd[j] / 6.0
    still = [False] * nb
    for j in range(nb):
        if n[j] < BLOCK_MIN_ROWS or nd[j] < BLOCK_MIN_ROWS - 2:
            continue
        o = 6 * j
        ex = [0.0] * 6
        raw = 0.0
        for i in range(6):
            m = s[o + i] / n[j]
            var = ss[o + i] / n[j] - m * m
            if var > raw:
                raw = var
            var -= d2[o + i] / nd[j] / 6.0
            ex[i] = sqrt(var) if var > 0.0 else 0.0
        if max(ex[0], ex[1], ex[2]) >= STILL_GYRO_STD or max(ex[3], ex[4], ex[5]) >= STILL_ACC_STD:
            continue
        if raw <= STUCK_STD * STUCK_STD:
            continue
        fx, fy, fz = s[o + 3] / n[j], s[o + 4] / n[j], s[o + 5] / n[j]
        fn = sqrt(fx * fx + fy * fy + fz * fz)
        still[j] = ACC_NORM_MIN <= fn <= ACC_NORM_MAX
    return still, w


def _calibrate(src):
    """Pass 1 (see vortex/core/strapdown.calibrate). Returns (t_anchor, qw, qx, qy, qz, bgx, bgy, bgz, g)
    or None when there is no usable still run."""
    sqrt = math.sqrt
    nb = int(CAL_HORIZON_S / BLOCK_S)
    bns = int(BLOCK_S * 1e9)
    n = [0] * nb
    s = [0.0] * (6 * nb)
    ss = [0.0] * (6 * nb)
    t0 = None
    t_end = 0
    with _open_rows(src) as f:
        for line in f:
            r = _parse(line)
            if r is None:
                continue
            t, v = r
            if t is None or not _valid(v):
                continue
            if t0 is None:
                t0 = t
                t_end = t0 + nb * bns
            if t >= t_end:
                break
            if t < t0:
                continue
            j = (t - t0) // bns
            n[j] += 1
            o = 6 * j
            for i in range(6):
                x = v[i]
                s[o + i] += x
                ss[o + i] += x * x
    if t0 is None:
        return None
    still = [False] * nb
    for j in range(nb):
        if n[j] < BLOCK_MIN_ROWS:
            continue
        o = 6 * j
        sd = [0.0] * 6
        for i in range(6):
            m = s[o + i] / n[j]
            var = ss[o + i] / n[j] - m * m
            sd[i] = sqrt(var) if var > 0.0 else 0.0
        if max(sd[0], sd[1], sd[2]) >= STILL_GYRO_STD or max(sd[3], sd[4], sd[5]) >= STILL_ACC_STD:
            continue
        if max(sd) <= STUCK_STD:
            continue
        fx, fy, fz = s[o + 3] / n[j], s[o + 4] / n[j], s[o + 5] / n[j]
        fn = sqrt(fx * fx + fy * fy + fz * fz)
        still[j] = ACC_NORM_MIN <= fn <= ACC_NORM_MAX
    best_j, best_len = _best_run(n, s, still)
    if CAL_NOISE_ON and best_len * BLOCK_S < MIN_STILL_S:
        best_j, best_len = _best_run(n, s, *_still_denoised(src, t0, n, s, ss))
    if best_len * BLOCK_S < MIN_STILL_S:
        return None
    trim = int(TRIM_S / BLOCK_S)
    c0, c1 = best_j, best_j + best_len
    if (best_len - 2 * trim) * BLOCK_S >= MIN_STILL_S:
        c0, c1 = c0 + trim, c1 - trim
    cnt = 0
    tot = [0.0] * 6
    for j in range(c0, c1):
        cnt += n[j]
        for i in range(6):
            tot[i] += s[6 * j + i]
    m = [tot[i] / cnt for i in range(6)]
    qw, qx, qy, qz, fn = _tilt(m[3], m[4], m[5])
    t_mid = t0 + best_j * bns + (best_len * bns) // 2
    return t_mid, qw, qx, qy, qz, m[0], m[1], m[2], fn


def _pre_segment(src, t_anchor, init):
    """Pass 2: poses of the rows before the anchor row, integrated backward from it (see
    vortex/core/strapdown.backward). t_anchor None: the anchor is the first valid row.
    Returns array('d') with 7 values per row (px, py, pz, qw, qx, qy, qz), or None if more than
    PRE_MAX_ROWS rows precede the anchor."""
    tt = array("q")
    buf = array("d")
    anchor = None
    with _open_rows(src) as f:
        for line in f:
            r = _parse(line)
            if r is None:
                continue
            t, v = r
            if t is not None and _valid(v) and (t_anchor is None or t >= t_anchor):
                anchor = (t, v)
                break
            if len(tt) >= PRE_MAX_ROWS:
                return None
            tt.append(-1 if t is None else t)
            buf.extend(v)
            buf.append(0.0)
    qw, qx, qy, qz, bgx, bgy, bgz, g = init
    m = len(tt)
    if anchor is None:                              # no valid row at all
        for i in range(m):
            buf[7 * i:7 * i + 7] = array("d", (0.0, 0.0, 0.0, qw, qx, qy, qz))
        return buf
    sqrt, cos, sin = math.sqrt, math.cos, math.sin
    px = py = pz = vx = vy = vz = 0.0
    t_next, (gx, gy, gz, ax, ay, az) = anchor
    ncx = gx - bgx; ncy = gy - bgy; ncz = gz - bgz
    ux = 2.0 * (qy * az - qz * ay); uy = 2.0 * (qz * ax - qx * az); uz = 2.0 * (qx * ay - qy * ax)
    nfx = ax + qw * ux + (qy * uz - qz * uy)
    nfy = ay + qw * uy + (qz * ux - qx * uz)
    nfz = az + qw * uz + (qx * uy - qy * ux)
    has_next = True
    for i in range(m - 1, -1, -1):
        t = tt[i]
        o = 7 * i
        if t >= 0:
            dt = (t_next - t) * 1e-9
            gx, gy, gz, ax, ay, az = buf[o], buf[o + 1], buf[o + 2], buf[o + 3], buf[o + 4], buf[o + 5]
            if gx * gx + gy * gy + gz * gz + ax * ax + ay * ay + az * az < MAX_SUMSQ:
                if 0 < dt <= MAX_JUMP_S:
                    if dt <= MAX_DT and has_next:
                        cx = gx - bgx; cy = gy - bgy; cz = gz - bgz
                        wx = -0.5 * (ncx + cx); wy = -0.5 * (ncy + cy); wz = -0.5 * (ncz + cz)
                        th2 = (wx * wx + wy * wy + wz * wz) * dt * dt
                        if th2 < 1e-8:
                            c = 1.0 - th2 / 8.0
                            k = 0.5 * dt * (1.0 - th2 / 24.0)
                        else:
                            th = sqrt(th2)
                            c = cos(0.5 * th)
                            k = sin(0.5 * th) * dt / th
                        kx = wx * k; ky = wy * k; kz = wz * k
                        nw = qw * c - qx * kx - qy * ky - qz * kz
                        nx = qw * kx + qx * c + qy * kz - qz * ky
                        ny = qw * ky - qx * kz + qy * c + qz * kx
                        nz = qw * kz + qx * ky - qy * kx + qz * c
                        inv = 1.0 / sqrt(nw * nw + nx * nx + ny * ny + nz * nz)
                        nw *= inv; nx *= inv; ny *= inv; nz *= inv
                        ux = 2.0 * (ny * az - nz * ay); uy = 2.0 * (nz * ax - nx * az); uz = 2.0 * (nx * ay - ny * ax)
                        fwx = ax + nw * ux + (ny * uz - nz * uy)
                        fwy = ay + nw * uy + (nz * ux - nx * uz)
                        fwz = az + nw * uz + (nx * uy - ny * ux)
                        awx = 0.5 * (nfx + fwx); awy = 0.5 * (nfy + fwy); awz = 0.5 * (nfz + fwz) - g
                        hdt2 = 0.5 * dt * dt
                        npx = px - vx * dt + awx * hdt2
                        npy = py - vy * dt + awy * hdt2
                        npz = pz - vz * dt + awz * hdt2
                        nvx = vx - awx * dt; nvy = vy - awy * dt; nvz = vz - awz * dt
                        chk = npx + npy + npz + nvx + nvy + nvz + nw
                        if chk - chk == 0:
                            qw = nw; qx = nx; qy = ny; qz = nz
                            px = npx; py = npy; pz = npz
                            vx = nvx; vy = nvy; vz = nvz
                            ncx = cx; ncy = cy; ncz = cz
                            nfx = fwx; nfy = fwy; nfz = fwz
                        else:
                            has_next = False
                    else:
                        px = px - vx * dt; py = py - vy * dt; pz = pz - vz * dt
                        ncx = gx - bgx; ncy = gy - bgy; ncz = gz - bgz
                        ux = 2.0 * (qy * az - qz * ay); uy = 2.0 * (qz * ax - qx * az); uz = 2.0 * (qx * ay - qy * ax)
                        nfx = ax + qw * ux + (qy * uz - qz * uy)
                        nfy = ay + qw * uy + (qz * ux - qx * uz)
                        nfz = az + qw * uz + (qx * uy - qy * ux)
                        has_next = True
                    t_next = t
            elif 0 < dt <= MAX_JUMP_S:
                px = px - vx * dt; py = py - vy * dt; pz = pz - vz * dt
                t_next = t
                has_next = False
        buf[o] = px; buf[o + 1] = py; buf[o + 2] = pz
        buf[o + 3] = qw; buf[o + 4] = qx; buf[o + 5] = qy; buf[o + 6] = qz
    return buf


def _initialise(win):
    """(qw, qx, qy, qz, bgx, bgy, bgz, g, still) from the init window (see vortex/core/strapdown.py)."""
    sqrt = math.sqrt
    n = len(win)
    if n == 0:
        return 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, G_DEFAULT, False
    mean = [0.0] * 6
    for v in win:
        for i in range(6):
            mean[i] += v[i]
    for i in range(6):
        mean[i] /= n
    var = [0.0] * 6
    for v in win:
        for i in range(6):
            d = v[i] - mean[i]
            var[i] += d * d
    std = [sqrt(var[i] / n) for i in range(6)]
    still = max(std[0], std[1], std[2]) < STILL_GYRO_STD and max(std[3], std[4], std[5]) < STILL_ACC_STD
    fx, fy, fz = mean[3], mean[4], mean[5]
    fn = sqrt(fx * fx + fy * fy + fz * fz)
    if fn < 1.0:
        return 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, G_DEFAULT, False
    ux, uy, uz = fx / fn, fy / fn, fz / fn
    if 1.0 + uz < 1e-9:
        qw, qx, qy, qz = 0.0, 1.0, 0.0, 0.0
    else:
        w, x, y = 1.0 + uz, uy, -ux
        k = 1.0 / sqrt(w * w + x * x + y * y)
        qw, qx, qy, qz = w * k, x * k, y * k, 0.0
    if still:
        return qw, qx, qy, qz, mean[0], mean[1], mean[2], fn, True
    return qw, qx, qy, qz, 0.0, 0.0, 0.0, G_DEFAULT, False


# ---- step 7a filter. Same arithmetic as vortex/core/witness.py and strapdown.py (bin_is_still,
# bins_steady, exp_step, qmul_normalised); called once per 0.25 s tick, never per row. ----

def _rot_matrix(qw, qx, qy, qz):
    w, x, y, z = qw, qx, qy, qz
    return (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - w * z), 2.0 * (x * z + w * y),
            2.0 * (x * y + w * z), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - w * x),
            2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x * x + y * y))


def _kf_init(still):
    tilt = P0_TILT if still else P0_TILT_FALLBACK
    bg = P0_BG if still else P0_BG_FALLBACK
    sig = (0.0, 0.0, 0.0, P0_VEL, P0_VEL, P0_VEL, tilt, tilt, P0_YAW, bg, bg, bg, P0_BA, P0_BA, P0_BA)
    P = [0.0] * (N * N)
    for i in range(N):
        P[i * N + i] = sig[i] * sig[i]
    return P


def _kf_propagate(P, r, fx, fy, fz, T, acc_d2=ACC_NOISE * ACC_NOISE, gyro_d2=GYRO_NOISE * GYRO_NOISE):
    A = [(0, 3, T), (1, 4, T), (2, 5, T),
         (3, 7, T * fz), (3, 8, -T * fy), (4, 6, -T * fz), (4, 8, T * fx), (5, 6, T * fy), (5, 7, -T * fx)]
    for i in range(3):
        for j in range(3):
            a = -T * r[3 * i + j]
            A.append((3 + i, 12 + j, a))
            A.append((6 + i, 9 + j, a))
    M = P[:]
    for i, j, a in A:
        oi, oj = i * N, j * N
        for c in range(N):
            M[oi + c] += a * P[oj + c]
    Pn = M[:]
    for i, j, a in A:
        for rr in range(0, N * N, N):
            Pn[rr + i] += a * M[rr + j]
    qv = acc_d2 * T
    qt = gyro_d2 * T
    qg = GYRO_WALK * GYRO_WALK * T
    qa = ACC_WALK * ACC_WALK * T
    for k in range(3):
        Pn[(3 + k) * (N + 1)] += qv
        Pn[(6 + k) * (N + 1)] += qt
        Pn[(9 + k) * (N + 1)] += qg
        Pn[(12 + k) * (N + 1)] += qa
    P[:] = Pn


def _gap_inflate(P, L, tilt2, dv2):
    s = L / (GAP_H_TICKS * TICK_S)
    s = s * s
    P[6 * N + 6] += 0.5 * tilt2 * s
    P[7 * N + 7] += 0.5 * tilt2 * s
    for k in range(3):
        a = dv2[k] * s
        P[(3 + k) * (N + 1)] += a
        P[k * (N + 1)] += a * L * L * 0.25
        P[k * N + 3 + k] += a * L * 0.5
        P[(3 + k) * N + k] += a * L * 0.5


def _kf_update(P, dx, k, z, var):
    S = P[k * N + k] + var
    if not S > 0.0:
        return
    inn = z - dx[k]
    row = P[k * N:(k + 1) * N]
    for i in range(N):
        Ki = P[i * N + k] / S
        if Ki != 0.0:
            dx[i] += Ki * inn
            oi = i * N
            for j in range(N):
                P[oi + j] -= Ki * row[j]


def _bin_still(n, s, ss):
    if n < BLOCK_MIN_ROWS:
        return False
    sd = [0.0] * 6
    for i in range(6):
        m = s[i] / n
        var = ss[i] / n - m * m
        sd[i] = math.sqrt(var) if var > 0.0 else 0.0
    if max(sd[0], sd[1], sd[2]) >= STILL_GYRO_STD or max(sd[3], sd[4], sd[5]) >= STILL_ACC_STD:
        return False
    if max(sd) <= STUCK_STD:
        return False
    fx, fy, fz = s[3] / n, s[4] / n, s[5] / n
    fn = math.sqrt(fx * fx + fy * fy + fz * fz)
    return ACC_NORM_MIN <= fn <= ACC_NORM_MAX


def _bins_steady(na, sa, nb_, sb):
    for i in range(6):
        tol = STEADY_GYRO if i < 3 else STEADY_ACC
        d = sa[i] / na - sb[i] / nb_
        if d >= tol or d <= -tol:
            return False
    return True


def _inject(qw, qx, qy, qz, px, py, pz, vx, vy, vz, bgx, bgy, bgz, bax, bay, baz, dx):
    """witness.inject: Exp(dth) q (global error), p, v, biases += dx. Non-finite dx is discarded."""
    chk = 0.0
    for e in dx:
        chk += e
    if chk - chk != 0.0:
        return qw, qx, qy, qz, px, py, pz, vx, vy, vz, bgx, bgy, bgz, bax, bay, baz
    ex, ey, ez = dx[6], dx[7], dx[8]
    th2 = (ex * ex + ey * ey + ez * ez) * 1.0 * 1.0
    if th2 < 1e-8:
        c = 1.0 - th2 / 8.0
        k = 0.5 * 1.0 * (1.0 - th2 / 24.0)
    else:
        th = math.sqrt(th2)
        c = math.cos(0.5 * th)
        k = math.sin(0.5 * th) * 1.0 / th
    kx, ky, kz = ex * k, ey * k, ez * k
    nw = c * qw - kx * qx - ky * qy - kz * qz
    nx = c * qx + kx * qw + ky * qz - kz * qy
    ny = c * qy - kx * qz + ky * qw + kz * qx
    nz = c * qz + kx * qy - ky * qx + kz * qw
    inv = 1.0 / math.sqrt(nw * nw + nx * nx + ny * ny + nz * nz)
    return (nw * inv, nx * inv, ny * inv, nz * inv, px + dx[0], py + dx[1], pz + dx[2],
            vx + dx[3], vy + dx[4], vz + dx[5], bgx + dx[9], bgy + dx[10], bgz + dx[11],
            bax + dx[12], bay + dx[13], baz + dx[14])


# ---- input front end (Step 2): copy of vortex/core/frontend.py, same rules (tests/test_frontend.py) ----
FRONT_ON = True              # no-op on canonical files (gyro first, integer ns, m/s^2)
FE_DETECT_ROWS = 4000         # 20 s at 200 Hz
FE_ORDER_MARGIN = 0.5         # accelerometer-likeness gap needed to trust the data over the header
FE_G_SCRIPT = 9.80665         # degrade_imu.py's G (g -> m/s^2)
FE_G_LO, FE_G_HI = 0.5, 2.0      # median norm range read as g (degrade_imu.py's rule)
FE_GYRO_SUSPECT = 3.0         # rad/s median norm: above this a deg/s gyro is suspected (flag only)
FE_CANON_HEADER = ("#timestamp [ns],w_RS_S_x [rad s^-1],w_RS_S_y [rad s^-1],w_RS_S_z [rad s^-1],"
                "a_RS_S_x [m s^-2],a_RS_S_y [m s^-2],a_RS_S_z [m s^-2]")
FE_SHIFT = {"s": 9, "ms": 6, "us": 3, "ns": 0}


def _fe_is_data(line):
    s = line.strip()
    return bool(s) and s[0] != 35


def _fe_num(x):
    try:
        return float(x)
    except ValueError:
        return float("nan")


def _fe_median(xs):
    """Median of a non-empty list (sorted in place)."""
    xs.sort()
    n = len(xs)
    h = n // 2
    return xs[h] if n % 2 else 0.5 * (xs[h - 1] + xs[h])


def _fe_quart(xs, f):
    """Value at fraction f of a SORTED list (nearest rank, floor)."""
    return xs[int(f * (len(xs) - 1))]


def _fe_likeness(norms):
    """(s, median) for one triple's norms; s = inf when there are fewer than 10."""
    if len(norms) < 10:
        return float("inf"), float("nan")
    m = _fe_median(norms)
    if not m > 0.0:
        return float("inf"), m
    r = (_fe_quart(norms, 0.75) - _fe_quart(norms, 0.25)) / m
    d = min(abs(math.log(m / FE_G_SCRIPT)), abs(math.log(m)))
    return d + r, m


def _fe_header_order(header):
    if header is None:
        return None
    toks = [t.strip().lower() for t in header.lstrip(b"\xef\xbb\xbf").lstrip(b"#").split(b",")]
    if len(toks) < 7:
        return None

    def kind(t):
        if t.startswith(b"w") or b"gyr" in t or b"rad" in t:
            return "g"
        if t.startswith(b"a") or b"acc" in t or b"m s^-2" in t or b"m/s" in t:
            return "a"
        return None
    k1, k4 = kind(toks[1]), kind(toks[4])
    if k1 == "g" and k4 == "a":
        return "gyro_first"
    if k1 == "a" and k4 == "g":
        return "accel_first"
    return None


def _fe_detect(path):
    """Layout of an IMU csv. Keys: order ('gyro_first' | 'accel_first'), order_from ('data' | 'header'
    | 'default'), header_order, ts_unit, ts_digits (all timestamps of the sampled rows are digits),
    accel_scale (1.0 or FE_G_SCRIPT), accel_unit, gyro_suspect, s1, s2 (likeness of columns 1-3 and 4-6),
    canonical (True: read the file as it is)."""
    header = None
    n1, n2, steps = [], [], []
    prev = None
    digits = True
    rows = 0
    with open(path, "rb") as f:
        if f.peek(3)[:3] == b"\xef\xbb\xbf":
            f.read(3)
        for line in f:
            if not _fe_is_data(line):
                if header is None and rows == 0 and line.strip()[:1] == b"#":
                    header = line.strip()
                continue
            rows += 1
            p = line.split(b",")
            ts = p[0].strip()
            if not ts.isdigit():
                digits = False
            t = _fe_num(ts)
            if t == t and prev is not None and t > prev:
                steps.append(t - prev)
            if t == t:
                prev = t
            v = [_fe_num(p[i]) if i < len(p) else float("nan") for i in range(1, 7)]
            a = v[0] * v[0] + v[1] * v[1] + v[2] * v[2]
            b = v[3] * v[3] + v[4] * v[4] + v[5] * v[5]
            if a == a and a < 1e30 and a > 0.0:
                n1.append(math.sqrt(a))
            if b == b and b < 1e30 and b > 0.0:
                n2.append(math.sqrt(b))
            if rows >= FE_DETECT_ROWS:
                break
    s1, m1 = _fe_likeness(n1)
    s2, m2 = _fe_likeness(n2)
    hdr = _fe_header_order(header)
    if s2 + FE_ORDER_MARGIN <= s1:
        order, src = "gyro_first", "data"
    elif s1 + FE_ORDER_MARGIN <= s2:
        order, src = "accel_first", "data"
    elif hdr is not None:
        order, src = hdr, "header"
    else:
        order, src = "gyro_first", "default"
    m_acc, m_gyr = (m2, m1) if order == "gyro_first" else (m1, m2)
    g_unit = m_acc == m_acc and FE_G_LO < m_acc < FE_G_HI
    if steps:
        dt = _fe_median(steps)
        unit = "s" if dt < 1.0 else "ms" if dt < 1e3 else "us" if dt < 1e6 else "ns"
    else:
        unit = "ns"
    lay = {"order": order, "order_from": src, "header_order": hdr, "ts_unit": unit, "ts_digits": digits,
           "accel_scale": FE_G_SCRIPT if g_unit else 1.0, "accel_unit": "g" if g_unit else "m/s^2",
           "gyro_suspect": m_gyr == m_gyr and m_gyr > FE_GYRO_SUSPECT, "s1": s1, "s2": s2}
    lay["canonical"] = order == "gyro_first" and unit == "ns" and digits and not g_unit
    return lay


def _fe_ns_text(ts, shift):
    """Timestamp text in `shift`-digit-smaller units -> integer nanosecond text, on the digits (exact).
    Digits beyond the nanosecond are dropped (truncated). Anything that is not plain decimal digits with
    at most one '.' is returned unchanged (the estimator then treats it as a bad timestamp)."""
    s = ts.strip()
    ip, dot, fp = s.partition(b".")
    if not ip:
        ip = b"0"
    if not ip.isdigit() or (fp and not fp.isdigit()):
        return s
    fp = (fp + b"0" * shift)[:shift]
    out = (ip + fp).lstrip(b"0")
    return out or b"0"


def _fe_canonical_lines(path, lay):
    """The file's data rows rewritten canonically (bytes lines, '\\n' ends): integer ns timestamp, gyro
    first, accelerometer in m/s^2. Same number and order of data rows; non-data lines dropped; a canonical
    header first. Fields that are not numbers stay as they are (reordered only)."""
    shift = FE_SHIFT[lay["ts_unit"]]
    acc_first = lay["order"] == "accel_first"
    k = lay["accel_scale"]
    yield FE_CANON_HEADER.encode() + b"\n"
    with open(path, "rb") as f:
        if f.peek(3)[:3] == b"\xef\xbb\xbf":
            f.read(3)
        for line in f:
            if not _fe_is_data(line):
                continue
            p = line.strip().split(b",")
            p += [b""] * (7 - len(p))
            ts = _fe_ns_text(p[0], shift)
            g, a = (p[4:7], p[1:4]) if acc_first else (p[1:4], p[4:7])
            if k != 1.0:
                a = [repr(_fe_num(x) * k).encode() for x in a]
            else:
                a = [x.strip() for x in a]
            yield b",".join([ts] + [x.strip() for x in g] + a) + b"\n"


# ---- fault front end (Step 3): copy of vortex/core/faults.py, same rules (tests/test_faults.py) ----
FF_STUCK6_ON = False
FF_SPIKE_ON = False
FF_SPIKE_ZHI = 100.0          # z needed on the triple that is far out (chosen on MH_01/02, 17 Nov)
FF_SPIKE_ZLO = 3.0            # z needed on the other triple (chosen on MH_01/02, 17 Nov)
FF_SPIKE_ALPHA = 0.01         # running mean weight after the warm-up (about 100 rows, 0.5 s at 200 Hz)
FF_SPIKE_WARM = 50            # tested rows before any row can be judged a spike
FF_SPIKE_CLIP = 10.0          # after the warm-up a row moves the running mean by at most this many times it
                           # (an undetected spike would otherwise raise the scale and hide the next ones)
FF_SPIKE_SPAN_NS = 50_000_000  # G..N span above which P is not judged (10 rows at 200 Hz)
FF_SPIKE_FLOOR_G2 = 0.005 ** 2  # rad^2/s^2: deviations below this are never spikes (noiseless input)
FF_SPIKE_FLOOR_A2 = 0.05 ** 2   # m^2/s^4
FF_MISSING = b"nan,nan,nan,nan,nan,nan,m"


def _ff_parse(line):
    """(t_ns or None, six floats or None, ts text) of a data line."""
    p = line.strip().split(b",")
    ts = p[0].strip()
    t = int(ts) if ts.isdigit() else None
    if len(p) < 7:
        return t, None, ts
    try:
        v = (float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5]), float(p[6]))
    except ValueError:
        return t, None, ts
    s = v[0] * v[0] + v[1] * v[1] + v[2] * v[2] + v[3] * v[3] + v[4] * v[4] + v[5] * v[5]
    if not s < 1e8:
        return t, None, ts
    return t, v, ts


def _ff_filter_lines(lines, stuck=None, spike=None, stats=None):
    """Yields the lines with stuck repeats and spikes rewritten as missing samples. Non-data lines are
    passed on at once; data rows keep their order and number. stats (dict, optional) gets counts."""
    stuck = FF_STUCK6_ON if stuck is None else stuck
    spike = FF_SPIKE_ON if spike is None else spike
    zhi, zlo = FF_SPIKE_ZHI, FF_SPIKE_ZLO
    st = {"stuck": 0, "spike": 0, "zero_mid": 0, "blind_rows": 0, "tested": 0}
    pend = None          # (t, v, ts, line): the row waiting for its next neighbour
    reps = []            # lines repeating pend exactly
    zeros = []           # buffered all-zero rows (lines, ts)
    gt = None            # last accepted row: time and values
    gv = None
    eg = ea = 0.0        # running mean squared deviations (gyro, accel)
    nw = 0

    def resolve(nt, nv):
        """Emit pend (spike-tested against gt..next) and its repeats."""
        nonlocal gt, gv, eg, ea, nw
        t, v, ts, line = pend
        flag = False
        if spike and gv is not None and nv is not None and t is not None and nt - gt <= FF_SPIKE_SPAN_NS:
            d0 = v[0] - 0.5 * (gv[0] + nv[0])
            d1 = v[1] - 0.5 * (gv[1] + nv[1])
            d2 = v[2] - 0.5 * (gv[2] + nv[2])
            dg = d0 * d0 + d1 * d1 + d2 * d2
            d0 = v[3] - 0.5 * (gv[3] + nv[3])
            d1 = v[4] - 0.5 * (gv[4] + nv[4])
            d2 = v[5] - 0.5 * (gv[5] + nv[5])
            da = d0 * d0 + d1 * d1 + d2 * d2
            if (nw >= FF_SPIKE_WARM and dg > FF_SPIKE_FLOOR_G2 and da > FF_SPIKE_FLOOR_A2
                    and ((dg > zhi * eg and da > zlo * ea) or (da > zhi * ea and dg > zlo * eg))):
                flag = True
                st["spike"] += 1
            else:
                nw += 1
                st["tested"] += 1
                if nw <= FF_SPIKE_WARM:
                    eg += (dg - eg) / nw
                    ea += (da - ea) / nw
                else:
                    eg += (min(dg, FF_SPIKE_CLIP * eg) - eg) * FF_SPIKE_ALPHA
                    ea += (min(da, FF_SPIKE_CLIP * ea) - ea) * FF_SPIKE_ALPHA
        out = [ts + b"," + FF_MISSING + b"\n" if flag else line]
        for rl, rts in reps:
            out.append(rts + b"," + FF_MISSING + b"\n")
            st["stuck"] += 1
        if not flag and t is not None:
            gt, gv = t, v
        return out

    for line in lines:
        s = line.strip()
        if not s or s[0] == 35:
            yield line
            continue
        if line[-1:] != b"\n":
            line = line + b"\n"
        t, v, ts = _ff_parse(line)
        if v is not None and t is not None and not (v[0] or v[1] or v[2] or v[3] or v[4] or v[5]):
            if pend is not None:
                yield from resolve(None, None)
                pend, reps = None, []
            zeros.append((line, ts))
            continue
        if zeros:                               # an all-zero run that is not at the end: a fault
            for zl, zts in zeros:
                if stuck:
                    yield zts + b"," + FF_MISSING + b"\n"
                    st["zero_mid"] += 1
                else:
                    yield zl
            zeros = []
        if v is None or t is None:              # invalid row: passed on as it is
            if pend is not None:
                yield from resolve(None, None)
                pend, reps = None, []
            yield line
            continue
        if stuck and pend is not None and v == pend[1]:
            reps.append((line, ts))
            continue
        if pend is not None:
            yield from resolve(t, v)
        pend, reps = (t, v, ts, line), []
    if pend is not None:
        yield from resolve(None, None)
    for zl, _ in zeros:                         # trailing all-zero run: the blind window, untouched
        yield zl
    st["blind_rows"] = len(zeros)
    if stats is not None:
        stats.update(st)


def _learn_env(acc, t0, t1):
    """Copy of witness.learn_env: acc holds 5 numbers per tick (t_ns, vh2, vv2, ph2, pv2)."""
    lim = t0 + LEARN_FRAC * (t1 - t0)
    n = 0
    s = [0.0, 0.0, 0.0, 0.0]
    for i in range(0, len(acc), 5):
        if acc[i] <= lim:
            n += 1
            s[0] += acc[i + 1]
            s[1] += acc[i + 2]
            s[2] += acc[i + 3]
            s[3] += acc[i + 4]
    if n == 0:
        return (V2_SIGMA_H, V2_SIGMA_V, V2P_SIGMA_H, V2P_SIGMA_V)
    out = []
    for k in range(4):
        x = LEARN_K * math.sqrt(s[k] / n)
        out.append(LEARN_MIN[k] if x < LEARN_MIN[k] else LEARN_MAX[k] if x > LEARN_MAX[k] else x)
    return tuple(out)


def _ts_span(src):
    """First and last integer timestamp (ns) of the data rows, in file order (None if none)."""
    t0 = t1 = None
    with _open_rows(src) as f:
        for line in f:
            if line[0] < 48:
                line = line.strip()
                if not line or line[0] == 35:
                    continue
            ts = line.split(b",", 1)[0]
            if not ts.isdigit():
                ts = ts.strip()
                if not ts.isdigit():
                    continue
            t1 = int(ts)
            if t0 is None:
                t0 = t1
    return t0, t1


def _run_learned(src, dst, write, integrate):
    """_run, with the envelope learned per file first when LEARN_ON (LEARN_ITERS passes)."""
    if not (LEARN_ON and integrate):
        return _run(src, dst, write, integrate)
    t0, t1 = _ts_span(src)
    env = None
    for _ in range(LEARN_ITERS):
        acc = array("d")
        _run(src, dst, False, True, env=env, collect=acc)
        env = _learn_env(acc, t0, t1) if t0 is not None else None
    LAST["env"] = env
    return _run(src, dst, write, integrate, env=env)


INTERP_ON = False            # Step 3: skip rows marked missing and integrate steps up to INTERP_MAX_S
INTERP_MAX_S = 0.3           # s; the script's bursts are 5-50 rows (<= 0.25 s at 200 Hz)


def run(src, dst, write=True, integrate=True):
    """Stream src -> dst. Returns the number of data rows. With FRONT_ON a file that is not canonical, and
    with FF_STUCK6_ON / FF_SPIKE_ON every file, is first rewritten (canonical, faults marked missing) next to
    dst (dst + '.vortex_in.csv', removed afterwards)."""
    LAST["frontend"] = None
    LAST["faults"] = None
    lines = None
    if FRONT_ON:
        lay = _fe_detect(src)
        LAST["frontend"] = lay
        if not lay["canonical"]:
            lines = _fe_canonical_lines(src, lay)
    f = None
    if FF_STUCK6_ON or FF_SPIKE_ON:
        if lines is None:
            f = open(src, "rb")
            lines = f
        st = {}
        LAST["faults"] = st
        lines = _ff_filter_lines(lines, stats=st)
    LAST["env"] = None
    if lines is None:
        return _run_learned(src, dst, write, integrate)
    tmp = dst + ".vortex_in.csv"
    try:
        with open(tmp, "wb") as g:
            g.writelines(lines)
    finally:
        if f is not None:
            f.close()
    try:
        return _run_learned(tmp, dst, write, integrate)
    finally:
        os.remove(tmp)


def _run(src, dst, write=True, integrate=True, env=None, collect=None):
    """Stream src -> dst. Returns the number of data rows.
    write=False: no output (benchmarks); integrate=False: identity poses (benchmarks)."""
    fl = float
    fmt = FMT
    slow = _slow_fields
    sqrt = math.sqrt
    cos = math.cos
    sin = math.sin
    exp = math.exp
    interp = INTERP_ON
    max_dt = INTERP_MAX_S if interp else MAX_DT
    e = env if env is not None else (V2_SIGMA_H, V2_SIGMA_V, V2P_SIGMA_H, V2P_SIGMA_V)
    s2vh, s2vv, s2ph, s2pv = e[0] * e[0], e[1] * e[1], e[2] * e[2], e[3] * e[3]
    max_jump = MAX_JUMP_S
    max_ss = MAX_SUMSQ
    n = 0
    gx = gy = gz = ax = ay = az = NAN
    px = py = pz = vx = vy = vz = 0.0
    pre = array("d")
    cal = None
    if integrate:
        cal = _calibrate(src)
        if cal is not None:
            pre = _pre_segment(src, cal[0], cal[1:])
            if pre is None:                 # too many rows before the anchor: fall back
                cal = None
                pre = array("d")
        if cal is not None:
            qw, qx, qy, qz, bgx, bgy, bgz, g = cal[1:]
            still0 = True
        else:                               # 6a: rows before the first valid row keep the initial pose
            qw, qx, qy, qz, bgx, bgy, bgz, g, still0 = _initialise(_init_window(src))
    else:
        qw, qx, qy, qz, bgx, bgy, bgz, g, still0 = 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, G_DEFAULT, False
    n_pre = len(pre) // 7
    LAST["pre_rows"] = n_pre
    LAST["calibrated"] = cal is not None
    # ---- filter state (witness.estimate) ----
    v1, v2, v2p = V1_ON, V2_ON, V2P_ON
    kf_update = _kf_update
    bax = bay = baz = 0.0
    P = _kf_init(still0)
    dx = [0.0] * N
    tick_ns = int(TICK_S * 1e9)
    tick_end = t_tick = 0
    r0 = _rot_matrix(qw, qx, qy, qz)
    fsx = fsy = fsz = 0.0
    fn = 0
    bn = 0
    bs0 = bs1 = bs2 = bs3 = bs4 = bs5 = 0.0
    bq0 = bq1 = bq2 = bq3 = bq4 = bq5 = 0.0
    pn, ps, pss, pstill = 0, None, None, False
    ccx = ccy = ccz = 0.0
    jam, gap_on = JAM_ON, GAP_ON
    hn = 0                                   # raw rows in the meter's history (0, 1, 2+)
    hgx = hgy = hgz = hax = hay = haz = 0.0  # last raw row
    kgx = kgy = kgz = kax = kay = kaz = 0.0  # the one before
    nd = 0
    dg = da = fdt = gap = 0.0
    jg = ja = -1.0
    ring = []
    tilt2 = -1.0
    dv2 = [0.0, 0.0, 0.0]
    dead, stuck = DEAD_ON, STUCK_ROWS
    sg = sa = 0                              # current run of identical gyro / accel triples
    sgx = sgy = sgz = sax = say = saz = NAN
    fc, tau = FC_ON, FC_TAU
    zupt_ticks = 0
    zs2, zm2 = ZUPT_SIGMA * ZUPT_SIGMA, ZARU_SIGMA_MIN * ZARU_SIGMA_MIN
    t = tl = 0
    have_t = False       # t_last set
    has_prev = False     # previous sample usable for the trapezoid
    pcx = pcy = pcz = pfx = pfy = pfz = 0.0
    tok = False
    sec = b"0"
    frac = b"000000000"
    out = []
    ap = out.append
    k = CHUNK
    with open(src, "rb", buffering=READ_BUF) as f, open(dst, "wb") as gfile:
        w = gfile.write
        if f.peek(3)[:3] == BOM:
            f.read(3)
        if n_pre:
            # rows before the anchor: poses from the backward pass (pass 2)
            for line in f:
                if line[0] < 48:
                    line = line.strip()
                    if not line or line[0] == 35:
                        continue
                ts = line.split(b",", 1)[0]
                if not ts.isdigit():
                    ts = ts.strip()
                if ts.isdigit():
                    if len(ts) > 9:
                        sec = ts[:-9]
                        frac = ts[-9:]
                    else:
                        sec = b"0"
                        frac = ts.rjust(9, b"0")
                o = 7 * n
                n += 1
                if write:
                    if PRE_HOLD:                    # step 6d: position held at the anchor's
                        ap(fmt % (sec, frac, 0.0, 0.0, 0.0, pre[o + 4], pre[o + 5], pre[o + 6], pre[o + 3]))
                    else:
                        ap(fmt % (sec, frac, pre[o], pre[o + 1], pre[o + 2], pre[o + 4], pre[o + 5], pre[o + 6],
                                  pre[o + 3]))
                    k -= 1
                    if not k:
                        w(b"".join(out))
                        out.clear()
                        k = CHUNK
                if n == n_pre:
                    break
        for line in f:
            if line[0] < 48:                    # '#', blank, leading whitespace: rare path
                line = line.strip()
                if not line or line[0] == 35:
                    continue
            p = line.split(b",")
            ts = p[0]
            if not ts.isdigit():
                ts = ts.strip()
            if ts.isdigit():
                tok = True
                if len(ts) > 9:
                    sec = ts[:-9]
                    frac = ts[-9:]
                else:
                    sec = b"0"
                    frac = ts.rjust(9, b"0")
            else:
                tok = False                     # keep the previous output timestamp
            try:
                gx = fl(p[1]); gy = fl(p[2]); gz = fl(p[3])
                ax = fl(p[4]); ay = fl(p[5]); az = fl(p[6])
            except (ValueError, IndexError):
                gx, gy, gz, ax, ay, az = slow(p)
            n += 1
            if integrate and tok:
                t = int(ts)
                ok = gx * gx + gy * gy + gz * gz + ax * ax + ay * ay + az * az < max_ss
                if ok and dead:
                    # ---- dead sensor: a triple repeating exactly, or an all-zero accelerometer ----
                    if gx == sgx and gy == sgy and gz == sgz:
                        sg += 1
                    else:
                        sgx = gx; sgy = gy; sgz = gz; sg = 1
                    if ax == sax and ay == say and az == saz:
                        sa += 1
                    else:
                        sax = ax; say = ay; saz = az; sa = 1
                    if sg >= stuck or sa >= stuck or not (ax or ay or az):
                        ok = False
                if ok:
                    if have_t:
                        dt = (t - tl) * 1e-9
                        if 0 < dt <= max_jump:
                            if t >= tick_end:
                                # ---- close the tick (every 0.25 s): propagate, witnesses, inject ----
                                T = (tl - t_tick) * 1e-9
                                r1 = _rot_matrix(qw, qx, qy, qz)
                                if T > 0.0:
                                    r = [0.5 * (r0[i] + r1[i]) for i in range(9)]
                                    if gap_on and gap > 0.0 and tilt2 >= 0.0:
                                        _gap_inflate(P, gap, tilt2, dv2)
                                    ad2 = ACC_NOISE * ACC_NOISE
                                    gd2 = GYRO_NOISE * GYRO_NOISE
                                    if jam:
                                        if nd >= BLOCK_MIN_ROWS and fn:
                                            ds = fdt / fn / (18.0 * nd)
                                            if jg < 0.0:
                                                jg, ja = dg * ds, da * ds
                                            else:
                                                b = T / JAM_TAU if T < JAM_TAU else 1.0
                                                jg += (dg * ds - jg) * b
                                                ja += (da * ds - ja) * b
                                        if jg > gd2:
                                            gd2 = jg
                                        if ja > ad2:
                                            ad2 = ja
                                    if fn:
                                        _kf_propagate(P, r, fsx / fn, fsy / fn, fsz / fn, T, ad2, gd2)
                                    else:
                                        _kf_propagate(P, r, 0.0, 0.0, g, T, ad2, gd2)
                                bs = [bs0, bs1, bs2, bs3, bs4, bs5]
                                bss = [bq0, bq1, bq2, bq3, bq4, bq5]
                                still = _bin_still(bn, bs, bss)
                                zupt = (v1 and still and pstill and _bins_steady(pn, ps, bn, bs))
                                if zupt:
                                    zupt_ticks += 1
                                    kf_update(P, dx, 3, -vx, zs2)
                                    kf_update(P, dx, 4, -vy, zs2)
                                    kf_update(P, dx, 5, -vz, zs2)
                                    bgl = (bgx, bgy, bgz)
                                    for i in range(3):
                                        m = bs[i] / bn
                                        var = (bss[i] / bn - m * m) / bn
                                        if var < zm2:
                                            var = zm2
                                        kf_update(P, dx, 9 + i, m - bgl[i], var)
                                elif v2:
                                    kf_update(P, dx, 3, -vx, s2vh)
                                    kf_update(P, dx, 4, -vy, s2vh)
                                    kf_update(P, dx, 5, -vz, s2vv)
                                if v2p and not zupt and T > 0.0:
                                    a = T / V2P_TAU if T < V2P_TAU else 1.0
                                    ccx += (px - ccx) * a
                                    ccy += (py - ccy) * a
                                    ccz += (pz - ccz) * a
                                    kf_update(P, dx, 0, ccx - px, s2ph)
                                    kf_update(P, dx, 1, ccy - py, s2ph)
                                    kf_update(P, dx, 2, ccz - pz, s2pv)
                                if zupt or v2 or v2p:
                                    (qw, qx, qy, qz, px, py, pz, vx, vy, vz, bgx, bgy, bgz, bax, bay,
                                     baz) = _inject(qw, qx, qy, qz, px, py, pz, vx, vy, vz, bgx, bgy, bgz,
                                                    bax, bay, baz, dx)
                                    dx = [0.0] * N
                                if collect is not None:
                                    d0 = px - ccx
                                    d1 = py - ccy
                                    d2 = pz - ccz
                                    collect.extend((tl, 0.5 * (vx * vx + P[48] + vy * vy + P[64]),
                                                    vz * vz + P[80], 0.5 * (d0 * d0 + P[0] + d1 * d1 + P[16]),
                                                    d2 * d2 + P[32]))
                                r0 = _rot_matrix(qw, qx, qy, qz)
                                if gap_on:
                                    if len(ring) == GAP_H_TICKS:
                                        oz, ov = ring.pop(0)
                                        e0 = r0[6] - oz[0]
                                        e1 = r0[7] - oz[1]
                                        e2 = r0[8] - oz[2]
                                        e2 = e0 * e0 + e1 * e1 + e2 * e2
                                        d0 = vx - ov[0]
                                        d1 = vy - ov[1]
                                        d2 = vz - ov[2]
                                        if tilt2 < 0.0:
                                            tilt2 = e2
                                            dv2 = [d0 * d0, d1 * d1, d2 * d2]
                                        else:
                                            b = TICK_S / GAP_TAU
                                            tilt2 += (e2 - tilt2) * b
                                            dv2[0] += (d0 * d0 - dv2[0]) * b
                                            dv2[1] += (d1 * d1 - dv2[1]) * b
                                            dv2[2] += (d2 * d2 - dv2[2]) * b
                                    ring.append(((r0[6], r0[7], r0[8]), (vx, vy, vz)))
                                tick_end += tick_ns * ((t - tick_end) // tick_ns + 1)
                                t_tick = tl
                                fsx = fsy = fsz = 0.0
                                fn = 0
                                nd = 0
                                dg = da = fdt = gap = 0.0
                                pn, ps, pss, pstill = bn, bs, bss, still
                                bn = 0
                                bs0 = bs1 = bs2 = bs3 = bs4 = bs5 = 0.0
                                bq0 = bq1 = bq2 = bq3 = bq4 = bq5 = 0.0
                            bn += 1
                            bs0 += gx; bs1 += gy; bs2 += gz; bs3 += ax; bs4 += ay; bs5 += az
                            bq0 += gx * gx; bq1 += gy * gy; bq2 += gz * gz
                            bq3 += ax * ax; bq4 += ay * ay; bq5 += az * az
                            if jam:
                                # ---- noise meter: second differences of the raw values ----
                                if dt <= max_dt and has_prev:
                                    if hn >= 2:
                                        d0 = gx - 2.0 * hgx + kgx
                                        d1 = gy - 2.0 * hgy + kgy
                                        d2 = gz - 2.0 * hgz + kgz
                                        dg += d0 * d0 + d1 * d1 + d2 * d2
                                        d0 = ax - 2.0 * hax + kax
                                        d1 = ay - 2.0 * hay + kay
                                        d2 = az - 2.0 * haz + kaz
                                        da += d0 * d0 + d1 * d1 + d2 * d2
                                        nd += 1
                                    kgx = hgx; kgy = hgy; kgz = hgz; kax = hax; kay = hay; kaz = haz
                                    hn += 1
                                else:
                                    hn = 1
                                hgx = gx; hgy = gy; hgz = gz; hax = ax; hay = ay; haz = az
                            ax = ax - bax; ay = ay - bay; az = az - baz
                            if dt <= max_dt and has_prev:
                                # ---- strapdown step (trapezoid), as strapdown._step ----
                                cx = gx - bgx; cy = gy - bgy; cz = gz - bgz
                                wx = 0.5 * (pcx + cx); wy = 0.5 * (pcy + cy); wz = 0.5 * (pcz + cz)
                                th2 = (wx * wx + wy * wy + wz * wz) * dt * dt
                                if th2 < 1e-8:
                                    c = 1.0 - th2 / 8.0
                                    s = 0.5 * dt * (1.0 - th2 / 24.0)
                                else:
                                    th = sqrt(th2)
                                    c = cos(0.5 * th)
                                    s = sin(0.5 * th) * dt / th
                                kx = wx * s; ky = wy * s; kz = wz * s
                                nw = qw * c - qx * kx - qy * ky - qz * kz
                                nx = qw * kx + qx * c + qy * kz - qz * ky
                                ny = qw * ky - qx * kz + qy * c + qz * kx
                                nz = qw * kz + qx * ky - qy * kx + qz * c
                                inv = 1.0 / sqrt(nw * nw + nx * nx + ny * ny + nz * nz)
                                nw *= inv; nx *= inv; ny *= inv; nz *= inv
                                ux = 2.0 * (ny * az - nz * ay)
                                uy = 2.0 * (nz * ax - nx * az)
                                uz = 2.0 * (nx * ay - ny * ax)
                                fwx = ax + nw * ux + (ny * uz - nz * uy)
                                fwy = ay + nw * uy + (nz * ux - nx * uz)
                                fwz = az + nw * uz + (nx * uy - ny * ux)
                                awx = 0.5 * (pfx + fwx)
                                awy = 0.5 * (pfy + fwy)
                                awz = 0.5 * (pfz + fwz) - g
                                hdt2 = 0.5 * dt * dt
                                npx = px + vx * dt + awx * hdt2
                                npy = py + vy * dt + awy * hdt2
                                npz = pz + vz * dt + awz * hdt2
                                nvx = vx + awx * dt; nvy = vy + awy * dt; nvz = vz + awz * dt
                                chk = npx + npy + npz + nvx + nvy + nvz + nw
                                if chk - chk == 0:
                                    qw = nw; qx = nx; qy = ny; qz = nz
                                    px = npx; py = npy; pz = npz
                                    vx = nvx; vy = nvy; vz = nvz
                                    pcx = cx; pcy = cy; pcz = cz
                                    pfx = fwx; pfy = fwy; pfz = fwz
                                    fsx += fwx; fsy += fwy; fsz += fwz
                                    fn += 1
                                    fdt += dt
                                else:
                                    has_prev = False
                            else:
                                # gap or no previous sample: coast, then take this sample
                                if fc:
                                    e = exp(-dt / tau)
                                    s = tau * (1.0 - e)
                                    px = px + vx * s; py = py + vy * s; pz = pz + vz * s
                                    vx = vx * e; vy = vy * e; vz = vz * e
                                else:
                                    px = px + vx * dt; py = py + vy * dt; pz = pz + vz * dt
                                gap += dt
                                pcx = gx - bgx; pcy = gy - bgy; pcz = gz - bgz
                                ux = 2.0 * (qy * az - qz * ay)
                                uy = 2.0 * (qz * ax - qx * az)
                                uz = 2.0 * (qx * ay - qy * ax)
                                pfx = ax + qw * ux + (qy * uz - qz * uy)
                                pfy = ay + qw * uy + (qz * ux - qx * uz)
                                pfz = az + qw * uz + (qx * uy - qy * ux)
                                has_prev = True
                            tl = t
                    else:
                        tl = t
                        have_t = True
                        tick_end = t + tick_ns
                        t_tick = t
                        bn += 1
                        bs0 += gx; bs1 += gy; bs2 += gz; bs3 += ax; bs4 += ay; bs5 += az
                        bq0 += gx * gx; bq1 += gy * gy; bq2 += gz * gz
                        bq3 += ax * ax; bq4 += ay * ay; bq5 += az * az
                        hn = 1
                        hgx = gx; hgy = gy; hgz = gz; hax = ax; hay = ay; haz = az
                        ax = ax - bax; ay = ay - bay; az = az - baz
                        pcx = gx - bgx; pcy = gy - bgy; pcz = gz - bgz
                        ux = 2.0 * (qy * az - qz * ay)
                        uy = 2.0 * (qz * ax - qx * az)
                        uz = 2.0 * (qx * ay - qy * ax)
                        pfx = ax + qw * ux + (qy * uz - qz * uy)
                        pfy = ay + qw * uy + (qz * ux - qx * uz)
                        pfz = az + qw * uz + (qx * uy - qy * ux)
                        has_prev = True
                elif have_t and not (interp and len(p) > 7 and p[7][:1] == b"m"):
                    dt = (t - tl) * 1e-9
                    if 0 < dt <= max_jump:
                        if fc:
                            e = exp(-dt / tau)
                            s = tau * (1.0 - e)
                            px = px + vx * s; py = py + vy * s; pz = pz + vz * s
                            vx = vx * e; vy = vy * e; vz = vz * e
                        else:
                            px = px + vx * dt; py = py + vy * dt; pz = pz + vz * dt
                        tl = t
                        has_prev = False
                        gap += dt
                        hn = 0
            if write:
                ap(fmt % (sec, frac, px, py, pz, qx, qy, qz, qw))
                k -= 1
                if not k:
                    w(b"".join(out))
                    out.clear()
                    k = CHUNK
        if out:
            w(b"".join(out))
    LAST["zupt_ticks"] = zupt_ticks
    LAST["ba"] = (bax, bay, baz)
    LAST["jam"] = (jg, ja)
    LAST["tilt2"] = tilt2
    return n


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: python main.py <imu.csv> <estimated_trajectory.txt>\n")
        return 2
    try:
        run(argv[1], argv[2])
    except OSError as e:
        sys.stderr.write("main.py: %s\n" % e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

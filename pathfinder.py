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
gaps add covariance learned from the recent motion (GAP_ON);
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
BG_MAX = 0.15
BGCAP_ON = True
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
V1_ON = True
V2_ON = True
V2P_ON = True
GAP_H_TICKS = 8
GAP_TAU = 20.0
GAP_ON = True
STUCK_ROWS = 5
DEAD_ON = True
FC_TAU = 0.5
FC_ON = True
PRE_HOLD = True
REFRESH_ON = True
P0V_ON = True
# Step L2 (witness.TILT_*): windowed gravity alignment + gyro noise meter; see vortex/core/witness.py
TILT_ON = True               # Step L2: ON by rule G2 (18 Nov 2026, seeds 16-18; rule G on seeds 10-12 had failed its null)
TILT_TAU = 4.0
TILT_G_LO = 0.05
TILT_G_HI = 0.10
TILT_MED_TICKS = 40
TILT_R_K = 1.0
TILT_DV = 2.0
TILT_WALK_K = 0.7
TILT_LAG = True
TILT_GATE_A = 0.5
BLIND_ON = True              # Step L3: ON since rule H' passed (Docs/results/stepHP-verdict.txt); blind window from a trusted state (witness.blind_apply)
BLIND_MIN_S = 1.0            # s: a trailing run of rejected rows at least this long is the blind window
BLIND_FALLBACK_S = 5.0       # s: otherwise the last 5 s by timestamp (organisers' FAQ A5)
BLIND_L = 3.0                # s, lookback before the blind start: the anchor
BLIND_BETA = 1.0             # pull from the anchor toward the centroid of the rows before it, ramped over BLIND_L
BLIND_DEAD_ONLY = True       # rule H': act only on a detected dead run (no BLIND_FALLBACK_S rows); ON since H' passed
SMOOTH_ON = True             # Step 6: ON (rule passed 18 Nov 2026); fixed-interval (RTS) smoother at the tick (vortex/core/witness.py smooth_*)
SMOOTH_MAX_BLOCKS = 1024     # stored blocks (fixed cap; a full store merges adjacent pairs): <= 1.05 MB of floats
PLATFORM_ON = True           # Step 7: ON (rule passed 18 Nov 2026); hand-held envelope (HH_*) when the file is hand-held (vortex/core/platform.py)
PLAT_WIN_NS = 1000000000     # ns, window of the detector statistic
PLAT_Q = 0.75                # quantile of the window statistics
PLAT_HF = 1.0                # (m/s^2)^2: below this the file is hand-held (rotor vibration is far above)
PLAT_MIN_TERMS = 100         # second differences a window needs to count
HH_V2_SIGMA_H = 0.5          # m/s, hand-held envelope (TUM-VI room1/2): speed h
HH_V2_SIGMA_V = 0.3          # m/s, speed v
HH_V2P_SIGMA_H = 1.0         # m, volume h
HH_V2P_SIGMA_V = 0.3         # m, volume v
HH_V2P_TAU = 30.0            # s, running-centre time constant
N = 15

LAST = {"pre_rows": 0, "calibrated": False, "zupt_ticks": 0, "ba": (0.0, 0.0, 0.0), "tilt2": -1.0}  # tests/benchmarks


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


def _plat_stat(src):
    """Step 7 detector statistic (vortex/core/platform.py hf_stat): per 1 s window the mean squared second
    difference of the accelerometer, PLAT_Q quantile over windows; None if no window counts. Same row
    rules as run(); an invalid or all-zero-accelerometer row, or a bad timestamp, ends the chain."""
    es = []
    t0 = None
    k_cur = None
    s = 0.0
    n = 0
    a1 = a2 = None
    with _open_rows(src) as f:
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
                    a1 = a2 = None
                    continue
            try:
                v = [float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5]), float(p[6])]
            except (ValueError, IndexError):
                v = _slow_fields(p)
            if not (v[0] * v[0] + v[1] * v[1] + v[2] * v[2] + v[3] * v[3] + v[4] * v[4] + v[5] * v[5]
                    < MAX_SUMSQ) or (v[3] == 0.0 and v[4] == 0.0 and v[5] == 0.0):
                a1 = a2 = None
                continue
            t = int(ts)
            if t0 is None:
                t0 = t
            k = (t - t0) // PLAT_WIN_NS
            if k != k_cur:
                if n >= PLAT_MIN_TERMS:
                    es.append(s / (3.0 * n))
                k_cur = k
                s = 0.0
                n = 0
                a1 = a2 = None
            x, y, z = v[3], v[4], v[5]
            if a2 is not None:
                d0 = x - 2.0 * a1[0] + a2[0]
                d1 = y - 2.0 * a1[1] + a2[1]
                d2 = z - 2.0 * a1[2] + a2[2]
                s += d0 * d0 + d1 * d1 + d2 * d2
                n += 1
            a2 = a1
            a1 = (x, y, z)
    if n >= PLAT_MIN_TERMS:
        es.append(s / (3.0 * n))
    if not es:
        return None
    es.sort()
    return es[int(PLAT_Q * (len(es) - 1))]


def _plat_hh(src):
    """True if PLATFORM_ON and the file is hand-held; LAST["platform"] gets the statistic."""
    LAST["platform"] = None
    if not PLATFORM_ON:
        return False
    st = _plat_stat(src)
    LAST["platform"] = st
    return st is not None and st < PLAT_HF


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
        if BGCAP_ON:
            mx, my, mz = s[o] / n[j], s[o + 1] / n[j], s[o + 2] / n[j]
            if not mx * mx + my * my + mz * mz <= BG_MAX * BG_MAX:
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
        if BGCAP_ON:
            mx, my, mz = s[o] / n[j], s[o + 1] / n[j], s[o + 2] / n[j]
            if not mx * mx + my * my + mz * mz <= BG_MAX * BG_MAX:
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
    if still and BGCAP_ON:
        still = mean[0] * mean[0] + mean[1] * mean[1] + mean[2] * mean[2] <= BG_MAX * BG_MAX
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


def _kf_init(still, hh=False):
    tilt = P0_TILT if still else P0_TILT_FALLBACK
    bg = P0_BG if still else P0_BG_FALLBACK
    sig = (0.0, 0.0, 0.0, P0_VEL, P0_VEL, P0_VEL, tilt, tilt, P0_YAW, bg, bg, bg, P0_BA, P0_BA, P0_BA)
    if P0V_ON and not still:
        sh, sv = (HH_V2_SIGMA_H, HH_V2_SIGMA_V) if hh else (V2_SIGMA_H, V2_SIGMA_V)
        sig = (0.0, 0.0, 0.0, sh, sh, sv) + sig[6:]
    P = [0.0] * (N * N)
    for i in range(N):
        P[i * N + i] = sig[i] * sig[i]
    return P


def _kf_propagate(P, r, fx, fy, fz, T, acc_d2=ACC_NOISE * ACC_NOISE, gyro_d2=GYRO_NOISE * GYRO_NOISE,
                  gyro_w2=GYRO_WALK * GYRO_WALK):
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
    qg = gyro_w2 * T
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


def _kf_update_row(P, dx, h, z, var):
    """witness.kf_update_row: z = sum h_k dx[k] + noise."""
    ph = [0.0] * N
    for i in range(N):
        oi = i * N
        a = 0.0
        for k, c in h:
            a += P[oi + k] * c
        ph[i] = a
    S = var
    hx = 0.0
    for k, c in h:
        S += c * ph[k]
        hx += c * dx[k]
    if not S > 0.0:
        return
    inn = z - hx
    for i in range(N):
        Ki = ph[i] / S
        if Ki != 0.0:
            dx[i] += Ki * inn
            oi = i * N
            for j in range(N):
                P[oi + j] -= Ki * ph[j]


def _tilt_weight(ring):
    """witness.tilt_weight."""
    s = sorted(ring)
    m = len(s)
    med = s[m // 2] if m % 2 else 0.5 * (s[m // 2 - 1] + s[m // 2])
    sg = math.sqrt(med)
    w = (sg - TILT_G_LO) / (TILT_G_HI - TILT_G_LO)
    return (0.0 if w < 0.0 else 1.0 if w > 1.0 else w), med


def _tilt_var(s2, g, w):
    """witness.tilt_var."""
    b = TILT_DV / (g * TILT_TAU)
    return TILT_R_K * (s2 / (g * g) * (TICK_S / TILT_TAU) + b * b) / w


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
    if BGCAP_ON:
        mx, my, mz = s[0] / n, s[1] / n, s[2] / n
        if not mx * mx + my * my + mz * mz <= BG_MAX * BG_MAX:
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


def _rotate(w, x, y, z, vx, vy, vz):
    """strapdown.rotate: R(q) v."""
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty),
            vy + w * ty + (z * tx - x * tz),
            vz + w * tz + (x * ty - y * tx))


def _refresh_prev(pcx, pcy, pcz, pfx, pfy, pfz, ow, ox, oy, oz, qw, qx, qy, qz, dx):
    """witness.refresh_prev (Step F): the cached previous sample after an injection from q_o to q."""
    bx, by, bz = _rotate(ow, -ox, -oy, -oz, pfx, pfy, pfz)
    return (pcx - dx[9], pcy - dx[10], pcz - dx[11]) + _rotate(qw, qx, qy, qz, bx - dx[12], by - dx[13],
                                                                 bz - dx[14])


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


def _phi_entries(r, fx, fy, fz, T):
    """Copy of witness.phi_entries: the non-zero entries (row, col, value) of A in Phi = I + A."""
    A = [(0, 3, T), (1, 4, T), (2, 5, T),
         (3, 7, T * fz), (3, 8, -T * fy), (4, 6, -T * fz), (4, 8, T * fx), (5, 6, T * fy), (5, 7, -T * fx)]
    for i in range(3):
        for j in range(3):
            a = -T * r[3 * i + j]
            A.append((3 + i, 12 + j, a))
            A.append((6 + i, 9 + j, a))
    return A


def _smooth_gain(Pp, A, Pm):
    """Copy of witness.smooth_gain: RTS gain C = Pp Phi^T Pm^-1 (row-major), None if Pm is not positive
    definite."""
    M = Pp[:]
    for i, j, a in A:
        oi, oj = i * N, j * N
        for c in range(N):
            M[oi + c] += a * Pp[oj + c]
    L = [0.0] * (N * N)
    for i in range(N):
        for j in range(i + 1):
            s = 0.5 * (Pm[i * N + j] + Pm[j * N + i])
            for k in range(j):
                s -= L[i * N + k] * L[j * N + k]
            if i == j:
                if not s > 0.0:
                    return None
                L[i * N + i] = math.sqrt(s)
            else:
                L[i * N + j] = s / L[j * N + j]
    C = [0.0] * (N * N)
    y = [0.0] * N
    for col in range(N):
        for i in range(N):
            s = M[i * N + col]
            for k in range(i):
                s -= L[i * N + k] * y[k]
            y[i] = s / L[i * N + i]
        for i in range(N - 1, -1, -1):
            s = y[i]
            for k in range(i + 1, N):
                s -= L[k * N + i] * y[k]
            y[i] = s / L[i * N + i]
        for i in range(N):
            C[col * N + i] = y[i]
    return C


def _smooth_merge(b1, b2):
    """Copy of witness.smooth_merge: compose two adjacent blocks (t, A, b, d), stored in single precision."""
    t1, A1, c1, d1 = b1
    A2, c2 = b2[1], b2[2]
    A = [0.0] * (N * N)
    c = list(c1)
    for i in range(N):
        oi = i * N
        for k in range(N):
            a = A1[oi + k]
            if a != 0.0:
                ok = k * N
                for j in range(N):
                    A[oi + j] += a * A2[ok + j]
                c[i] += a * c2[k]
    return (t1, array("f", A), array("f", c), d1)


def _smooth_push(blocks, blk, cap):
    """witness.smooth_push, merging in place (same blocks, no second list while merging)."""
    if len(blocks) == cap:
        m = 0
        for i in range(0, cap - 1, 2):
            blocks[m] = _smooth_merge(blocks[i], blocks[i + 1])
            m += 1
        if cap % 2:
            blocks[m] = blocks[cap - 1]
            m += 1
        del blocks[m:]
    blocks.append(blk)


SMOOTH_K = (0, 1, 2, 6, 7, 8)   # the error components a pose needs: position, attitude


def _smooth_segments(blocks, t_end, d_end):
    """witness.smooth_apply's backward recursion. Per block j: start / end time (ns) and, for the six
    components in SMOOTH_K, the smoothed error just after the start tick (relative to the forward posterior)
    and just before the end tick (relative to the forward prior): 12 doubles."""
    nb = len(blocks)
    st0 = array("q", [0]) * nb
    st1 = array("q", [0]) * nb
    ev = array("d", [0.0]) * (12 * nb)
    ep = list(d_end)
    t_next = t_end
    for jb in range(nb - 1, -1, -1):
        t0, A, b, d = blocks[jb]
        es = [b[i] + sum(A[i * N + k] * ep[k] for k in range(N)) for i in range(N)]
        st0[jb] = t0
        st1[jb] = t_next
        o = 12 * jb
        for m in range(6):
            i = SMOOTH_K[m]
            ev[o + m] = es[i] - d[i]
            ev[o + 6 + m] = ep[i]
        ep, t_next = es, t0
    return st0, st1, ev, t_end


def _fe_is_data(line):
    s = line.strip()
    return bool(s) and s[0] != 35


def _fe_num(x):
    try:
        return float(x)
    except ValueError:
        return float("nan")


def _fe_text_header(line):
    """A header written without '#' (e.g. `timestamp,w_x,...`): no comma field is a number. Only the first
    data-like line of a file can be one (vortex/rowspec.py is_text_header); it is not a row. A line with
    no letter at all (`,,,,,,`: every value missing) stays a row."""
    if line.upper() == line.lower():
        return False
    for x in line.lstrip(b"\xef\xbb\xbf").split(b","):
        try:
            float(x)
            return False
        except ValueError:
            pass
    return True


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
    text_hdr = False
    with open(path, "rb") as f:
        if f.peek(3)[:3] == b"\xef\xbb\xbf":
            f.read(3)
        for line in f:
            if not _fe_is_data(line):
                if header is None and rows == 0 and line.strip()[:1] == b"#":
                    header = line.strip()
                continue
            if rows == 0 and not text_hdr and _fe_text_header(line):
                text_hdr = True
                if header is None:
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
           "gyro_suspect": m_gyr == m_gyr and m_gyr > FE_GYRO_SUSPECT, "s1": s1, "s2": s2,
           "text_header": text_hdr}
    lay["canonical"] = order == "gyro_first" and unit == "ns" and digits and not g_unit and not text_hdr
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
    skip = lay.get("text_header", False)
    with open(path, "rb") as f:
        if f.peek(3)[:3] == b"\xef\xbb\xbf":
            f.read(3)
        for line in f:
            if not _fe_is_data(line):
                continue
            if skip:                                 # the header written without '#': not a row
                skip = False
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


def run(src, dst, write=True, integrate=True):
    """Stream src -> dst. Returns the number of data rows. With FRONT_ON a file that is not canonical is
    first rewritten canonically next to dst (dst + '.vortex_in.csv', removed afterwards)."""
    LAST["frontend"] = None
    if FRONT_ON:
        lay = _fe_detect(src)
        LAST["frontend"] = lay
        if not lay["canonical"]:
            tmp = dst + ".vortex_in.csv"
            with open(tmp, "wb") as g:
                g.writelines(_fe_canonical_lines(src, lay))
            try:
                return _run_smoothed(tmp, dst, write, integrate)
            finally:
                os.remove(tmp)
    return _run_smoothed(src, dst, write, integrate)


def _run_smoothed(src, dst, write, integrate):
    """_run with the smoother (SMOOTH_ON): one pass that stores the smoother's blocks, then the pass that
    writes, each row corrected by the smoothed error (Step 6)."""
    hh = _plat_hh(src) if integrate else False
    LAST["smooth_blocks"] = None
    LAST["blind_t"] = None
    corr = None
    tb = None
    if (SMOOTH_ON or BLIND_ON) and integrate and write:
        st = {}
        _run(src, dst, False, True, store=st, hh=hh)
        if SMOOTH_ON:
            LAST["smooth_blocks"] = len(st["blocks"])
            if st["blocks"]:
                corr = _smooth_segments(st["blocks"], st["t_end"], st["d_end"])
        if BLIND_ON:
            tb = LAST["blind_t"] = st.get("blind_t")
        st = None
    return _run(src, dst, write, integrate, corr=corr, hh=hh, blind=tb)


def _run(src, dst, write=True, integrate=True, store=None, corr=None, hh=False, blind=None):
    """Stream src -> dst. Returns the number of data rows.
    write=False: no output (benchmarks); integrate=False: identity poses (benchmarks). store: a dict that
    gets the smoother's blocks (Step 6); corr: _smooth_segments() output, applied to every written row.
    blind: Step L3 blind start (ns) from the store pass; the written rows from ta = blind - BLIND_L on are blended
    toward the centroid of the rows written before (witness.blind_apply)."""
    fl = float
    fmt = FMT
    slow = _slow_fields
    sqrt = math.sqrt
    cos = math.cos
    sin = math.sin
    exp = math.exp
    max_dt = MAX_DT
    if hh:
        s2vh, s2vv = HH_V2_SIGMA_H * HH_V2_SIGMA_H, HH_V2_SIGMA_V * HH_V2_SIGMA_V
        s2ph, s2pv = HH_V2P_SIGMA_H * HH_V2P_SIGMA_H, HH_V2P_SIGMA_V * HH_V2P_SIGMA_V
        vtau = HH_V2P_TAU
    else:
        s2vh, s2vv = V2_SIGMA_H * V2_SIGMA_H, V2_SIGMA_V * V2_SIGMA_V
        s2ph, s2pv = V2P_SIGMA_H * V2P_SIGMA_H, V2P_SIGMA_V * V2P_SIGMA_V
        vtau = V2P_TAU
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
    P = _kf_init(still0, hh)
    dx = [0.0] * N
    smooth = store is not None and SMOOTH_ON
    bt = store is not None and BLIND_ON      # Step L3, store pass: track the trailing run of rejected rows
    brun = False
    bt0 = btz = None
    bl = blind is not None                   # Step L3, write pass
    if bl:
        bta = blind - int(BLIND_L * 1e9)
        bsw = False                          # switched: from the first row reaching bta
        brt = None                           # time of the row (its own, or the last earlier timestamp)
        bsx = bsy = bsz = 0.0
        bk = 0
        blx = bly = blz = blqx = blqy = blqz = blqw = 0.0
        bcx = bcy = bcz = 0.0
    blocks = []                              # Step 6: (t, C, b, d) per stored block
    sPp = P[:]                               # posterior covariance at the last tick
    sd_prev = array("f", [0.0] * N)          # correction injected at the last tick
    st_prev = None                           # time of the last tick
    sC = None
    zero_c = [0.0] * (N * N)
    cr = corr is not None
    if cr:
        cs0, cs1, cev, c_end = corr
        cj = 0
        cn = len(cs0)
    tr = None                                # last row timestamp from the anchor on (smoother correction)
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
    gap_on = GAP_ON
    gap = 0.0
    ring = []
    tilt2 = -1.0
    dv2 = [0.0, 0.0, 0.0]
    dead, stuck = DEAD_ON, STUCK_ROWS
    sg = sa = 0                              # current run of identical gyro / accel triples
    sgx = sgy = sgz = sax = say = saz = NAN
    fc, tau = FC_ON, FC_TAU
    refresh = REFRESH_ON
    tilt = TILT_ON                           # Step L2 state (witness.estimate)
    tF = [0.0, 0.0, 0.0]
    tS = [0.0, 0.0]
    tV = [0.0, 0.0]
    tn = 0
    tfull = TILT_TAU / TICK_S
    tring = []
    tw = 0.0
    med = 0.0
    nd = 0                                   # gyro second differences this tick (meter)
    dg = fdt = 0.0
    m1 = m2 = False                          # last two raw gyro rows held (h1, h2)
    h1x = h1y = h1z = h2x = h2y = h2z = 0.0
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
                        if sec[0] == 48:            # leading zeros: str(ns // 10**9), as the contract says
                            sec = sec.lstrip(b"0") or b"0"
                        frac = ts[-9:]
                    else:
                        sec = b"0"
                        frac = ts.rjust(9, b"0")
                o = 7 * n
                n += 1
                if write:
                    if bl:
                        # ---- Step L3: same as the main rows below (rare: the blind start reaches the pre rows) ----
                        if ts.isdigit():
                            brt = int(ts)
                        if PRE_HOLD:
                            X = Y = Z = 0.0
                        else:
                            X = pre[o]; Y = pre[o + 1]; Z = pre[o + 2]
                        QX = pre[o + 4]; QY = pre[o + 5]; QZ = pre[o + 6]; QW = pre[o + 3]
                        if not bsw and brt is not None and brt >= bta:
                            bsw = True
                            if bk:
                                bcx = bsx / bk; bcy = bsy / bk; bcz = bsz / bk
                            else:
                                bl = False
                        if not bl:
                            pass
                        elif bsw:
                            bw = (brt - bta) * 1e-9 / BLIND_L
                            bw = BLIND_BETA * (1.0 if bw > 1.0 else (0.0 if bw < 0.0 else bw))
                            X = blx + bw * (bcx - blx); Y = bly + bw * (bcy - bly); Z = blz + bw * (bcz - blz)
                            QX = blqx; QY = blqy; QZ = blqz; QW = blqw
                        else:
                            bsx += X; bsy += Y; bsz += Z
                            bk += 1
                            blx = X; bly = Y; blz = Z; blqx = QX; blqy = QY; blqz = QZ; blqw = QW
                        ap(fmt % (sec, frac, X, Y, Z, QX, QY, QZ, QW))
                    elif PRE_HOLD:                  # step 6d: position held at the anchor's
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
                    if sec[0] == 48:                # leading zeros: str(ns // 10**9), as the contract says
                        sec = sec.lstrip(b"0") or b"0"
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
                if bt:
                    btz = t
                    if ok:
                        brun = False
                    elif not brun:
                        brun = True
                        bt0 = t
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
                                    gw2 = GYRO_WALK * GYRO_WALK
                                    if tilt and nd >= BLOCK_MIN_ROWS and fn:
                                        tring.append(dg / (18.0 * nd))
                                        if len(tring) > TILT_MED_TICKS:
                                            tring.pop(0)
                                        if len(tring) == TILT_MED_TICKS:
                                            tw, med = _tilt_weight(tring)
                                        if tw > 0.0:
                                            d2 = med * fdt / fn
                                            if d2 > gd2:
                                                gd2 += tw * (d2 - gd2)
                                            w2 = TILT_WALK_K * TILT_WALK_K * d2
                                            if w2 > gw2:
                                                gw2 += tw * (w2 - gw2)
                                    if fn:
                                        _kf_propagate(P, r, fsx / fn, fsy / fn, fsz / fn, T, ad2, gd2, gw2)
                                        if smooth:
                                            sA = _phi_entries(r, fsx / fn, fsy / fn, fsz / fn, T)
                                    else:
                                        _kf_propagate(P, r, 0.0, 0.0, g, T, ad2, gd2, gw2)
                                        if smooth:
                                            sA = _phi_entries(r, 0.0, 0.0, g, T)
                                elif smooth:
                                    sA = []
                                if smooth:
                                    sC = _smooth_gain(sPp, sA, P)
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
                                    a = T / vtau if T < vtau else 1.0
                                    ccx += (px - ccx) * a
                                    ccy += (py - ccy) * a
                                    ccz += (pz - ccz) * a
                                    kf_update(P, dx, 0, ccx - px, s2ph)
                                    kf_update(P, dx, 1, ccy - py, s2ph)
                                    kf_update(P, dx, 2, ccz - pz, s2pv)
                                tup = False
                                if tilt and fn and T > 0.0:
                                    tn += 1
                                    b = 1.0 / tn
                                    if b < T / TILT_TAU:
                                        b = T / TILT_TAU
                                    fm = fsx / fn - tF[0]
                                    tS[0] += (fm * fm - tS[0]) * b
                                    tV[0] += (vx - tV[0]) * b
                                    tF[0] += fm * b
                                    fm = fsy / fn - tF[1]
                                    tS[1] += (fm * fm - tS[1]) * b
                                    tV[1] += (vy - tV[1]) * b
                                    tF[1] += fm * b
                                    fm = fsz / fn - tF[2]
                                    tF[2] += fm * b
                                    ax_ = (vx - tV[0]) / TILT_TAU
                                    ay_ = (vy - tV[1]) / TILT_TAU
                                    if tw > 0.0 and tn >= tfull and ax_ * ax_ + ay_ * ay_ <= TILT_GATE_A * TILT_GATE_A:
                                        if TILT_LAG:
                                            hr = [(6, 1.0)] + [(9 + j, TILT_TAU * r1[j]) for j in range(3)]
                                            _kf_update_row(P, dx, hr, tF[1] / g, _tilt_var(tS[1], g, tw))
                                            hr = [(7, 1.0)] + [(9 + j, TILT_TAU * r1[3 + j]) for j in range(3)]
                                            _kf_update_row(P, dx, hr, -tF[0] / g, _tilt_var(tS[0], g, tw))
                                        else:
                                            kf_update(P, dx, 6, tF[1] / g, _tilt_var(tS[1], g, tw))
                                            kf_update(P, dx, 7, -tF[0] / g, _tilt_var(tS[0], g, tw))
                                        tup = True
                                sdx = None
                                if zupt or v2 or v2p or tup:
                                    sdx = dx
                                    ow, ox, oy, oz = qw, qx, qy, qz
                                    (qw, qx, qy, qz, px, py, pz, vx, vy, vz, bgx, bgy, bgz, bax, bay,
                                     baz) = _inject(qw, qx, qy, qz, px, py, pz, vx, vy, vz, bgx, bgy, bgz,
                                                    bax, bay, baz, dx)
                                    if refresh or tilt:
                                        chk = 0.0
                                        for e in dx:
                                            chk += e
                                        if chk - chk == 0.0:
                                            if tilt:            # Step L2: the window was built with the old attitude
                                                ex, ey, ez = dx[6], dx[7], dx[8]
                                                f0, f1, f2 = tF
                                                tF = [f0 + ey * f2 - ez * f1, f1 + ez * f0 - ex * f2,
                                                      f2 + ex * f1 - ey * f0]
                                                if TILT_LAG:
                                                    u0 = TILT_TAU * g * (r1[0] * dx[9] + r1[1] * dx[10]
                                                                         + r1[2] * dx[11])
                                                    u1 = TILT_TAU * g * (r1[3] * dx[9] + r1[4] * dx[10]
                                                                         + r1[5] * dx[11])
                                                    tF[0] += u1
                                                    tF[1] -= u0
                                            if refresh and has_prev:
                                                (pcx, pcy, pcz, pfx, pfy, pfz) = _refresh_prev(
                                                    pcx, pcy, pcz, pfx, pfy, pfz, ow, ox, oy, oz, qw, qx, qy, qz, dx)
                                    dx = [0.0] * N
                                if smooth:
                                    chk = 0.0
                                    if sdx is not None:
                                        for e in sdx:
                                            chk += e
                                    sd_new = array("f", sdx if sdx is not None and chk - chk == 0.0 else [0.0] * N)
                                    _smooth_push(blocks, (st_prev, array("f", sC if sC is not None else zero_c),
                                                          sd_prev, sd_prev), SMOOTH_MAX_BLOCKS)
                                    sd_prev, st_prev, sPp = sd_new, tl, P[:]
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
                                dg = fdt = 0.0
                                gap = 0.0
                                pn, ps, pss, pstill = bn, bs, bss, still
                                bn = 0
                                bs0 = bs1 = bs2 = bs3 = bs4 = bs5 = 0.0
                                bq0 = bq1 = bq2 = bq3 = bq4 = bq5 = 0.0
                            bn += 1
                            bs0 += gx; bs1 += gy; bs2 += gz; bs3 += ax; bs4 += ay; bs5 += az
                            bq0 += gx * gx; bq1 += gy * gy; bq2 += gz * gz
                            bq3 += ax * ax; bq4 += ay * ay; bq5 += az * az
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
                                    if tilt:
                                        fdt += dt
                                else:
                                    has_prev = False
                                if tilt:                    # gyro meter: second differences (witness.estimate)
                                    if m2:
                                        d0 = gx - 2.0 * h1x + h2x
                                        d1 = gy - 2.0 * h1y + h2y
                                        d2 = gz - 2.0 * h1z + h2z
                                        dg += d0 * d0 + d1 * d1 + d2 * d2
                                        nd += 1
                                    h2x = h1x; h2y = h1y; h2z = h1z; m2 = m1
                                    h1x = gx; h1y = gy; h1z = gz; m1 = True
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
                                if tilt:
                                    h1x = gx; h1y = gy; h1z = gz; m1 = True; m2 = False
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
                        st_prev = t
                        if tilt:
                            h1x = gx; h1y = gy; h1z = gz; m1 = True
                        bn += 1
                        bs0 += gx; bs1 += gy; bs2 += gz; bs3 += ax; bs4 += ay; bs5 += az
                        bq0 += gx * gx; bq1 += gy * gy; bq2 += gz * gz
                        bq3 += ax * ax; bq4 += ay * ay; bq5 += az * az
                        ax = ax - bax; ay = ay - bay; az = az - baz
                        pcx = gx - bgx; pcy = gy - bgy; pcz = gz - bgz
                        ux = 2.0 * (qy * az - qz * ay)
                        uy = 2.0 * (qz * ax - qx * az)
                        uz = 2.0 * (qx * ay - qy * ax)
                        pfx = ax + qw * ux + (qy * uz - qz * uy)
                        pfy = ay + qw * uy + (qz * ux - qx * uz)
                        pfz = az + qw * uz + (qx * uy - qy * ux)
                        has_prev = True
                elif have_t:
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
                        m1 = m2 = False
            if write:
                if cr:
                    if tok:
                        tr = t
                    if tr is not None and tr <= c_end:
                        # ---- Step 6: smoothed error, linear in time inside the bracketing block ----
                        while cj < cn - 1 and tr > cs1[cj]:
                            cj += 1
                        t0 = cs0[cj]
                        t1 = cs1[cj]
                        wt = 0.0 if t1 <= t0 or tr <= t0 else (tr - t0) / (t1 - t0)
                        o = 12 * cj
                        e0 = cev[o] + (cev[o + 6] - cev[o]) * wt
                        e1 = cev[o + 1] + (cev[o + 7] - cev[o + 1]) * wt
                        e2 = cev[o + 2] + (cev[o + 8] - cev[o + 2]) * wt
                        ex = cev[o + 3] + (cev[o + 9] - cev[o + 3]) * wt
                        ey = cev[o + 4] + (cev[o + 10] - cev[o + 4]) * wt
                        ez = cev[o + 5] + (cev[o + 11] - cev[o + 5]) * wt
                        th2 = (ex * ex + ey * ey + ez * ez) * 1.0 * 1.0
                        if th2 < 1e-8:
                            c = 1.0 - th2 / 8.0
                            s = 0.5 * 1.0 * (1.0 - th2 / 24.0)
                        else:
                            th = sqrt(th2)
                            c = cos(0.5 * th)
                            s = sin(0.5 * th) * 1.0 / th
                        kx = ex * s; ky = ey * s; kz = ez * s
                        nw = c * qw - kx * qx - ky * qy - kz * qz
                        nx = c * qx + kx * qw + ky * qz - kz * qy
                        ny = c * qy - kx * qz + ky * qw + kz * qx
                        nz = c * qz + kx * qy - ky * qx + kz * qw
                        inv = 1.0 / sqrt(nw * nw + nx * nx + ny * ny + nz * nz)
                        X = px + e0; Y = py + e1; Z = pz + e2
                        QX = nx * inv; QY = ny * inv; QZ = nz * inv; QW = nw * inv
                    else:
                        X = px; Y = py; Z = pz; QX = qx; QY = qy; QZ = qz; QW = qw
                else:
                    X = px; Y = py; Z = pz; QX = qx; QY = qy; QZ = qz; QW = qw
                if bl:
                    # ---- Step L3 (witness.blind_apply): centroid and anchor of the rows before bta, then blend ----
                    if tok:
                        brt = t
                    if not bsw and brt is not None and brt >= bta:
                        bsw = True
                        if bk:
                            bcx = bsx / bk; bcy = bsy / bk; bcz = bsz / bk
                        else:
                            bl = False
                    if not bl:
                        pass
                    elif bsw:
                        bw = (brt - bta) * 1e-9 / BLIND_L
                        bw = BLIND_BETA * (1.0 if bw > 1.0 else (0.0 if bw < 0.0 else bw))
                        X = blx + bw * (bcx - blx); Y = bly + bw * (bcy - bly); Z = blz + bw * (bcz - blz)
                        QX = blqx; QY = blqy; QZ = blqz; QW = blqw
                    else:
                        bsx += X; bsy += Y; bsz += Z
                        bk += 1
                        blx = X; bly = Y; blz = Z; blqx = QX; blqy = QY; blqz = QZ; blqw = QW
                ap(fmt % (sec, frac, X, Y, Z, QX, QY, QZ, QW))
                k -= 1
                if not k:
                    w(b"".join(out))
                    out.clear()
                    k = CHUNK
        if out:
            w(b"".join(out))
    if bt and btz is not None:
        bdet = brun and btz - bt0 >= int(BLIND_MIN_S * 1e9)
        store["blind_t"] = (bt0 if bdet else None if BLIND_DEAD_ONLY
                            else btz - int(BLIND_FALLBACK_S * 1e9))
    if smooth:
        store["blocks"] = blocks
        store["t_end"] = st_prev
        store["d_end"] = sd_prev
    LAST["zupt_ticks"] = zupt_ticks
    LAST["ba"] = (bax, bay, baz)
    LAST["tilt2"] = tilt2
    return n


_usage_text = """usage: python main.py [IN [OUT]]   or   python main.py --input IN --output OUT   (-i IN -o OUT)
  IN   the IMU csv, or a sequence folder (searched for imu0/data.csv, mav0/imu0/data.csv, data.csv,
       then a single *.csv). No IN: the current folder is searched the same way.
  OUT  the trajectory file, or a folder (estimated_trajectory.txt inside it).
       No OUT: estimated_trajectory.txt in the current folder.
"""
_out_name = "estimated_trajectory.txt"
_search_paths = (("imu0", "data.csv"), ("mav0", "imu0", "data.csv"), ("data.csv",))


class _Usage(Exception):
    pass


def _find_input(folder):
    """The IMU csv of a folder: imu0/data.csv, mav0/imu0/data.csv, data.csv, else its only *.csv."""
    for parts in _search_paths:
        p = os.path.join(folder, *parts)
        if os.path.isfile(p):
            return p
    csvs = [n for n in os.listdir(folder) if n.lower().endswith(".csv") and not n.endswith(".vortex_in.csv")
            and os.path.isfile(os.path.join(folder, n))]
    if len(csvs) == 1:
        return os.path.join(folder, csvs[0])
    raise _Usage("no IMU csv found in %s (looked for %s, or a single *.csv; found %d *.csv)"
                 % (os.path.abspath(folder), ", ".join("/".join(s) for s in _search_paths), len(csvs)))


def _paths(argv):
    """(src, dst) from the command line; raises _Usage. argv[0] is the script name."""
    src = dst = None
    pos = []
    a = list(argv[1:])
    while a:
        x = a.pop(0)
        for flags, key in ((("-i", "--input"), "i"), (("-o", "--output"), "o")):
            hit = None
            if x in flags:
                if not a:
                    raise _Usage("%s needs a value" % x)
                hit = a.pop(0)
            elif x.startswith(flags[1] + "="):
                hit = x[len(flags[1]) + 1:]
            if hit is not None:
                if key == "i":
                    src = hit
                else:
                    dst = hit
                break
        else:
            if x in ("-h", "--help"):
                raise _Usage("")
            if x.startswith("-") and len(x) > 1:
                raise _Usage("unknown option %s" % x)
            pos.append(x)
    if src is None and pos:
        src = pos.pop(0)
    if dst is None and pos:
        dst = pos.pop(0)
    if pos:
        raise _Usage("too many arguments: %s" % " ".join(pos))
    if src is None:
        src = _find_input(os.getcwd())
    elif os.path.isdir(src):
        src = _find_input(src)
    if dst is None:
        dst = _out_name
    elif os.path.isdir(dst):
        dst = os.path.join(dst, _out_name)
    return src, dst


def _fallback(src, dst):
    """A constant pose (origin, identity) for every data row, same timestamps rule as _run. Returns rows."""
    n = 0
    sec, frac = b"0", b"000000000"
    first = True
    with open(src, "rb", buffering=READ_BUF) as f, open(dst, "wb") as g:
        if f.peek(3)[:3] == BOM:
            f.read(3)
        for line in f:
            if not _fe_is_data(line):
                continue
            if first:
                first = False
                if _fe_text_header(line):
                    continue
            ts = line.split(b",", 1)[0].strip()
            if ts.isdigit():
                t = int(ts)
                sec = str(t // 1000000000).encode()
                frac = b"%09d" % (t % 1000000000)
            g.write(b"%s.%s 0.000000 0.000000 0.000000 0.0000000 0.0000000 0.0000000 1.0000000\n" % (sec, frac))
            n += 1
    return n


def main(argv):
    """Never fails on a readable input: if the estimator raises, every row gets a constant pose (exit 0).
    Exit 2: bad arguments or no input found; 1: the input cannot be read or the output not written."""
    try:
        src, dst = _paths(argv)
    except _Usage as e:
        if str(e):
            sys.stderr.write("main.py: %s\n" % e)
        sys.stderr.write(_usage_text)
        return 0 if not str(e) else 2
    LAST["fallback"] = None
    try:
        run(src, dst)
        return 0
    except KeyboardInterrupt:
        raise
    except BaseException as e:      # noqa: BLE001 (any failure of the estimator: fall back, never fail)
        LAST["fallback"] = "%s: %s" % (type(e).__name__, e)
        tb = e.__traceback__                 # where it failed: the innermost frame (file, line)
        while tb is not None and tb.tb_next is not None:
            tb = tb.tb_next
        if tb is not None:
            LAST["fallback"] += " (%s line %d)" % (tb.tb_frame.f_code.co_filename, tb.tb_lineno)
        sys.stderr.write("main.py: the estimator failed (%s); writing a constant pose for every row\n"
                         % LAST["fallback"])
    try:
        rows = _fallback(src, dst)
    except Exception as e:          # noqa: BLE001
        sys.stderr.write("main.py: %s\n" % e)
        return 1
    sys.stderr.write("main.py: wrote %d constant poses to %s\n" % (rows, dst))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

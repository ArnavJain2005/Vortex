"""Vortex, Samsung PRISM XR Hackathon 2026, Track 3: trajectory from a degraded IMU.

    python -S main.py <imu0/data.csv> <estimated_trajectory.txt>

Pure Python, standard library only, single thread, offline, deterministic. Standalone: it never
imports the `vortex` package. The readable reference implementation is vortex/core/witness.py (on
top of vortex/core/strapdown.py); tests/test_core_equivalence.py keeps the two in lockstep (same
rules, same arithmetic order).

Output: one line `timestamp tx ty tz qx qy qz qw` per input data row, same order. A data row is any
line that is not blank and does not start with '#' (vortex/rowspec.py states the same rule). The
timestamp is the input ns value with the decimal point moved 9 digits left, done on the text, so it
is exact. A row whose timestamp is not an integer repeats the previous row's timestamp.

STATUS (step 7a): self-calibration on the longest still run in the first 60 s (gyro bias, g, tilt),
backward integration from mid-run over the rows before it (dead reckoning, no witnesses), then a
forward error-state Kalman filter (15 states, one covariance step per 0.25 s tick) with the
witnesses V1 stillness (ZUPT + gyro bias) and V2 flight envelope (speed and volume); fallback to the
step 6a first-second initialisation. Rules: vortex/core/witness.py. Performance: Docs/BUDGET.md.

Passes: (1) calibration scan of the first 60 s; (2) rows before the anchor are stored (64 bytes per
row, at most PRE_MAX_ROWS) and integrated backward; (3) one streaming forward pass writes every row.
"""
import math
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
N = 15

LAST = {"pre_rows": 0, "calibrated": False, "zupt_ticks": 0, "ba": (0.0, 0.0, 0.0)}  # for tests/benchmarks


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
    best_j, best_len, j0 = 0, 0, -1
    for j in range(nb + 1):
        st = j < nb and still[j]
        steady = True
        if st and j0 >= 0:
            oa, ob = 6 * (j - 1), 6 * j
            for i in range(6):
                tol = STEADY_GYRO if i < 3 else STEADY_ACC
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


def _kf_propagate(P, r, fx, fy, fz, T):
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
    qv = ACC_NOISE * ACC_NOISE * T
    qt = GYRO_NOISE * GYRO_NOISE * T
    qg = GYRO_WALK * GYRO_WALK * T
    qa = ACC_WALK * ACC_WALK * T
    for k in range(3):
        Pn[(3 + k) * (N + 1)] += qv
        Pn[(6 + k) * (N + 1)] += qt
        Pn[(9 + k) * (N + 1)] += qg
        Pn[(12 + k) * (N + 1)] += qa
    P[:] = Pn


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


def run(src, dst, write=True, integrate=True):
    """Stream src -> dst. Returns the number of data rows.
    write=False: no output (benchmarks); integrate=False: identity poses (benchmarks)."""
    fl = float
    fmt = FMT
    slow = _slow_fields
    sqrt = math.sqrt
    cos = math.cos
    sin = math.sin
    max_dt = MAX_DT
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
                if gx * gx + gy * gy + gz * gz + ax * ax + ay * ay + az * az < max_ss:
                    if have_t:
                        dt = (t - tl) * 1e-9
                        if 0 < dt <= max_jump:
                            if t >= tick_end:
                                # ---- close the tick (every 0.25 s): propagate, witnesses, inject ----
                                T = (tl - t_tick) * 1e-9
                                r1 = _rot_matrix(qw, qx, qy, qz)
                                if T > 0.0:
                                    r = [0.5 * (r0[i] + r1[i]) for i in range(9)]
                                    if fn:
                                        _kf_propagate(P, r, fsx / fn, fsy / fn, fsz / fn, T)
                                    else:
                                        _kf_propagate(P, r, 0.0, 0.0, g, T)
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
                                    kf_update(P, dx, 3, -vx, V2_SIGMA_H * V2_SIGMA_H)
                                    kf_update(P, dx, 4, -vy, V2_SIGMA_H * V2_SIGMA_H)
                                    kf_update(P, dx, 5, -vz, V2_SIGMA_V * V2_SIGMA_V)
                                if v2p and not zupt and T > 0.0:
                                    a = T / V2P_TAU if T < V2P_TAU else 1.0
                                    ccx += (px - ccx) * a
                                    ccy += (py - ccy) * a
                                    ccz += (pz - ccz) * a
                                    kf_update(P, dx, 0, ccx - px, V2P_SIGMA_H * V2P_SIGMA_H)
                                    kf_update(P, dx, 1, ccy - py, V2P_SIGMA_H * V2P_SIGMA_H)
                                    kf_update(P, dx, 2, ccz - pz, V2P_SIGMA_V * V2P_SIGMA_V)
                                if zupt or v2 or v2p:
                                    (qw, qx, qy, qz, px, py, pz, vx, vy, vz, bgx, bgy, bgz, bax, bay,
                                     baz) = _inject(qw, qx, qy, qz, px, py, pz, vx, vy, vz, bgx, bgy, bgz,
                                                    bax, bay, baz, dx)
                                    dx = [0.0] * N
                                tick_end += tick_ns * ((t - tick_end) // tick_ns + 1)
                                t_tick = tl
                                r0 = _rot_matrix(qw, qx, qy, qz)
                                fsx = fsy = fsz = 0.0
                                fn = 0
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
                                else:
                                    has_prev = False
                            else:
                                # gap or no previous sample: constant velocity, then take this sample
                                px = px + vx * dt; py = py + vy * dt; pz = pz + vz * dt
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
                        px = px + vx * dt; py = py + vy * dt; pz = pz + vz * dt
                        tl = t
                        has_prev = False
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

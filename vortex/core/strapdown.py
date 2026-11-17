"""Reference estimator, steps 6a and 6b: initialisation, self-calibration on a still run, and
strapdown integration. Plain Python floats, no numpy, so pathfinder.py (the optimised twin) can match it
to rounding.

Conventions: quaternion (w, x, y, z), Hamilton, body-to-world. World frame: z up, gravity
(0, 0, -g); yaw and origin are arbitrary (zero at the first valid row), because the scorer aligns
the trajectory. Gyro in rad/s (body), accel is specific force in m/s^2 (+g up at rest).

Self-calibration (step 6b, W2). EuRoC MH sequences start hand-carried, so the first second is
not still; the vehicle rests on the ground later (MH_01: about 20 to 44 s by ground truth).
  - Scan the valid rows with t in [t0, t0 + CAL_HORIZON_S) in BLOCK_S time bins. A bin is still if
    it has >= BLOCK_MIN_ROWS rows, per-axis std below STILL_GYRO_STD and STILL_ACC_STD, some channel
    std above STUCK_STD (a stuck or frozen sensor is not "still") and |mean specific force| in
    [ACC_NORM_MIN, ACC_NORM_MAX].
  - Take the longest run of consecutive still bins (earliest on ties), at least MIN_STILL_S long, in
    which neighbouring bins are also steady: mean gyro within STEADY_GYRO and mean specific force
    within STEADY_ACC per axis (a slow, smooth rotation has a low std but a non-zero mean).
    From its core (TRIM_S cut from each end when the run is at least MIN_STILL_S + 2 TRIM_S long,
    because the ends may still creep): gyro bias = mean gyro, g = |mean specific force|, roll and
    pitch from the mean specific force (yaw 0). Velocity 0 at the anchor.
  - Anchor = the first valid row, in file order, with t >= the MIDDLE of the run (where v = 0 is
    most certain; the run's ends may still creep). Rows before the anchor are
    integrated BACKWARD in time from the anchor (same rules mirrored), rows from the anchor onward
    forward. If no still run exists, or more than PRE_MAX_ROWS rows precede the anchor, fall back to
    the 6a initialisation below with the anchor at the first valid row.

Fallback initialisation (step 6a; gravity alignment is unknown, so it is estimated):
  The init window is every valid row whose timestamp lies in [t0, t0 + INIT_S], t0 being the first
  valid row's timestamp (at most INIT_MAX_ROWS rows). A valid row has an integer timestamp and six
  finite values of sane size (sum of squares below MAX_SUMSQ).
  - Roll and pitch: the minimal rotation taking the window's mean specific force onto world +z.
  - If the window is still (per-axis std below STILL_GYRO_STD and STILL_ACC_STD): gyro bias = mean
    gyro, g = |mean specific force|. Otherwise gyro bias = 0 and g = G_DEFAULT.
  - Velocity 0, position 0.

Integration, per row, in file order (every row still gets a pose):
  - Valid row, dt = t - t_last in (0, MAX_DT], previous sample available: attitude by the exponential
    map of the mean bias-corrected rate of the two samples (trapezoid); world acceleration = mean of
    R f at the two samples, minus gravity; p += v dt + a dt^2 / 2, v += a dt.
  - Valid row after a gap (dt > MAX_DT) or after invalid rows: p += v dt (constant velocity), attitude
    held; this row becomes the previous sample. PLACEHOLDER until the dropout step.
  - Invalid values (NaN, inf, missing) with a usable timestamp: p += v dt, attitude held.
  - dt <= 0 (duplicate, out of order), dt > MAX_JUMP_S (corrupt timestamp) or no integer timestamp:
    the row is ignored for estimation; its pose repeats the current state.
  - If an update would produce a non-finite state it is discarded (cannot happen with finite input
    of sane size; this is the never-NaN guarantee).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Named parameters. Source: placeholders chosen from the EuRoC ADIS16448 noise densities in
# sensor.yaml (gyro 1.7e-4 rad/s/sqrt(Hz), accel 2.0e-3 m/s^2/sqrt(Hz); about 1.7e-3 rad/s and
# 0.02 m/s^2 per sample at 200 Hz), with a 10x and 5x margin. To be checked on real MH_01.
INIT_S = 1.0
INIT_MAX_ROWS = 2000
STILL_GYRO_STD = 0.02      # rad/s, per axis
STILL_ACC_STD = 0.1        # m/s^2, per axis
G_DEFAULT = 9.81           # m/s^2, used only when the init window is not still
MAX_DT = 0.1               # s; a longer step is a gap (EuRoC is 200 Hz, 5 ms)
MAX_JUMP_S = 30.0          # s; a longer forward jump is treated as a corrupt timestamp
CAL_HORIZON_S = 60.0       # s scanned for a still run (6b)
BLOCK_S = 0.25             # s per stillness bin
BLOCK_MIN_ROWS = 5
MIN_STILL_S = 1.0          # shortest usable still run
STUCK_STD = 1e-5           # all six channel stds at or below this: frozen sensor, not still (above the
                           # ~1e-7 rounding floor of the sum-of-squares std; real noise ~2e-3 rad/s)
ACC_NORM_MIN = 8.8         # m/s^2, plausible gravity for a still bin
ACC_NORM_MAX = 10.8
STEADY_GYRO = 0.005        # rad/s, bin-to-bin change of mean gyro inside a run (~20x bin-mean noise)
STEADY_ACC = 0.05          # m/s^2, bin-to-bin change of mean specific force (~17x)
TRIM_S = 0.5               # s cut from each end of a long still run before averaging
PRE_MAX_ROWS = 15000       # rows stored for the backward pass (memory cap: 64 bytes per row in pathfinder.py)
CAL_NOISE_ON = True        # step 6e (rule passed 16 Nov): if no strict still run, retry with the white noise removed (see calibrate)
# Step F (rule in Docs/TRACK3_PLAN.md, Step F; passed, ships on). A steady rotation has low variance and
# steady bin means, so the still tests alone take it for rest and its rate for gyro bias (a constant 0.3 rad/s
# yaw at the start was erased completely). With BGCAP_ON a bin or init window whose mean gyro norm exceeds
# BG_MAX is not still: in bin_is_still (calibration and V1), bin_is_still_denoised (6e, 7b) and initialise.
BG_MAX = 0.15              # rad/s: 1.8x the largest calibrated |bg| on MH_01/02 (clean and official copies a/b s1-3: 0.080-0.083); TUM-VI not checked
BGCAP_ON = True               # Step F: ships on (held-out rule passed, 17 Nov 2026)
# 6b thresholds measured afterwards on clean MH_01..05 (0.25 s bins, longest still run in 60 s):
# in-run gyro std max 0.003..0.017 rad/s, accel std max 0.061..0.094 m/s^2.
MAX_SUMSQ = 1e8            # a row whose six values' sum of squares reaches this is invalid (values of
                           # order 1e4; the ADIS16448 range is about 17 rad/s and 180 m/s^2)


@dataclass
class Init:
    q: tuple            # (w, x, y, z)
    bg: tuple           # gyro bias, rad/s
    g: float            # gravity magnitude, m/s^2
    still: bool
    rows: int


@dataclass
class Calib:
    init: Init
    anchor: int                # index in rows where forward integration starts (mid-run; len(rows) if none)
    run_s: tuple | None        # (start, end) of the still run, s after the first valid row; None = fallback


def is_valid(vals) -> bool:
    """One compare rejects NaN (comparison false), +-inf and absurd magnitudes (overflow to inf)."""
    g0, g1, g2, a0, a1, a2 = vals
    return g0 * g0 + g1 * g1 + g2 * g2 + a0 * a0 + a1 * a1 + a2 * a2 < MAX_SUMSQ


def init_window(rows):
    """rows: iterable of (t_ns or None, (gx, gy, gz, ax, ay, az)). Returns the init window values."""
    t0 = None
    win = []
    for t, vals in rows:
        if t is None or not is_valid(vals):
            continue
        if t0 is None:
            t0 = t
        if t > t0 + int(INIT_S * 1e9):
            break
        if t >= t0:
            win.append(vals)
            if len(win) >= INIT_MAX_ROWS:
                break
    return win


def initialise(win) -> Init:
    n = len(win)
    if n == 0:
        return Init((1.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0), G_DEFAULT, False, 0)
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
    std = [math.sqrt(var[i] / n) for i in range(6)]
    still = max(std[0], std[1], std[2]) < STILL_GYRO_STD and max(std[3], std[4], std[5]) < STILL_ACC_STD
    if still and BGCAP_ON:
        still = mean[0] * mean[0] + mean[1] * mean[1] + mean[2] * mean[2] <= BG_MAX * BG_MAX
    fx, fy, fz = mean[3], mean[4], mean[5]
    fn = math.sqrt(fx * fx + fy * fy + fz * fz)
    if fn < 1.0:                               # no usable gravity reading
        return Init((1.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0), G_DEFAULT, False, n)
    ux, uy, uz = fx / fn, fy / fn, fz / fn
    # minimal rotation u -> +z: q = (1 + u.z, u x z) normalised; u x z = (uy, -ux, 0)
    if 1.0 + uz < 1e-9:
        q = (0.0, 1.0, 0.0, 0.0)               # upside down: 180 deg about x
    else:
        w, x, y = 1.0 + uz, uy, -ux
        k = 1.0 / math.sqrt(w * w + x * x + y * y)
        q = (w * k, x * k, y * k, 0.0)
    if still:
        return Init(q, (mean[0], mean[1], mean[2]), fn, True, n)
    return Init(q, (0.0, 0.0, 0.0), G_DEFAULT, False, n)


def _tilt(fx, fy, fz):
    """Minimal rotation taking specific force f onto world +z (same arithmetic as initialise)."""
    fn = math.sqrt(fx * fx + fy * fy + fz * fz)
    ux, uy, uz = fx / fn, fy / fn, fz / fn
    if 1.0 + uz < 1e-9:
        return (0.0, 1.0, 0.0, 0.0), fn
    w, x, y = 1.0 + uz, uy, -ux
    k = 1.0 / math.sqrt(w * w + x * x + y * y)
    return (w * k, x * k, y * k, 0.0), fn


def still_bins(rows):
    """(t0, list of per-bin (n, sums[6], sumsq[6])) over the calibration horizon."""
    t0 = None
    nb = int(CAL_HORIZON_S / BLOCK_S)
    bns = int(BLOCK_S * 1e9)
    n = [0] * nb
    s = [[0.0] * 6 for _ in range(nb)]
    ss = [[0.0] * 6 for _ in range(nb)]
    for t, vals in rows:
        if t is None or not is_valid(vals):
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
        sj, ssj = s[j], ss[j]
        for i in range(6):
            x = vals[i]
            sj[i] += x
            ssj[i] += x * x
    return t0, n, s, ss


def bin_is_still(n, s, ss):
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
    if BGCAP_ON and not gyro_plausible(n, s):
        return False
    fx, fy, fz = s[3] / n, s[4] / n, s[5] / n
    fn = math.sqrt(fx * fx + fy * fy + fz * fz)
    return ACC_NORM_MIN <= fn <= ACC_NORM_MAX


def gyro_plausible(n, s):
    """Step F: the bin's mean gyro is small enough to be a bias (norm <= BG_MAX)."""
    gx, gy, gz = s[0] / n, s[1] / n, s[2] / n
    return gx * gx + gy * gy + gz * gz <= BG_MAX * BG_MAX


def bins_steady(na, sa, nb_, sb):
    for i in range(6):
        tol = STEADY_GYRO if i < 3 else STEADY_ACC
        d = sa[i] / na - sb[i] / nb_
        if d >= tol or d <= -tol:
            return False
    return True


def noise_bins(rows, t0):
    """Per bin over the calibration horizon: (count, per-channel sums of squared second differences
    x[k] - 2 x[k-1] + x[k-2]) of consecutive accepted rows of the same bin (step 6e). Accepted = the
    rows still_bins counts; any other row, a step outside (0, MAX_DT] or a new bin restarts the history."""
    nb = int(CAL_HORIZON_S / BLOCK_S)
    bns = int(BLOCK_S * 1e9)
    nd = [0] * nb
    d2 = [[0.0] * 6 for _ in range(nb)]
    if t0 is None:
        return nd, d2
    t_end = t0 + nb * bns
    h1 = h2 = None
    jl = tl = -1
    for t, vals in rows:
        if t is None or not is_valid(vals) or t < t0:
            h1 = h2 = None
            continue
        if t >= t_end:
            break
        j = (t - t0) // bns
        if h1 is not None and (j != jl or not 0 < t - tl <= MAX_DT * 1e9):
            h1 = h2 = None
        if h2 is not None:
            nd[j] += 1
            dj = d2[j]
            for i in range(6):
                d = vals[i] - 2.0 * h1[i] + h2[i]
                dj[i] += d * d
        h2, h1, jl, tl = h1, vals, j, t
    return nd, d2


def bin_is_still_denoised(n, s, ss, nd, d2):
    """bin_is_still with each channel's white-noise variance (second-difference variance / 6) removed
    before the std thresholds (step 6e). The stuck and |f| tests are unchanged."""
    if n < BLOCK_MIN_ROWS or nd < BLOCK_MIN_ROWS - 2:
        return False
    ex = [0.0] * 6
    raw = 0.0
    for i in range(6):
        m = s[i] / n
        var = ss[i] / n - m * m
        if var > raw:
            raw = var
        var -= d2[i] / nd / 6.0
        ex[i] = math.sqrt(var) if var > 0.0 else 0.0
    if max(ex[0], ex[1], ex[2]) >= STILL_GYRO_STD or max(ex[3], ex[4], ex[5]) >= STILL_ACC_STD:
        return False
    if raw <= STUCK_STD * STUCK_STD:
        return False
    if BGCAP_ON and not gyro_plausible(n, s):
        return False
    fx, fy, fz = s[3] / n, s[4] / n, s[5] / n
    fn = math.sqrt(fx * fx + fy * fy + fz * fz)
    return ACC_NORM_MIN <= fn <= ACC_NORM_MAX


def white_var(nd, d2):
    """Per-channel white-noise variance of one bin from its second differences (variance 6 sigma^2)."""
    return [d2[i] / nd / 6.0 for i in range(6)] if nd else [0.0] * 6


def bins_steady_denoised(na, sa, wa, nb_, sb, wb):
    """bins_steady with each tolerance widened by 3 standard deviations of the difference of the two
    bin means under white noise of variance wa, wb (step 6e)."""
    for i in range(6):
        tol = (STEADY_GYRO if i < 3 else STEADY_ACC) + 3.0 * math.sqrt(wa[i] / na + wb[i] / nb_)
        d = sa[i] / na - sb[i] / nb_
        if d >= tol or d <= -tol:
            return False
    return True


def _best_run(n, s, still, w=None):
    """Longest run of still, pairwise steady bins (earliest on ties): (first bin, length). w: per-bin
    white-noise variances (step 6e) for bins_steady_denoised, else bins_steady."""
    best_j, best_len, j0 = 0, 0, -1
    nb = len(n)
    for j in range(nb + 1):
        st = j < nb and still[j]
        if st and j0 >= 0 and not (bins_steady(n[j - 1], s[j - 1], n[j], s[j]) if w is None else
                                   bins_steady_denoised(n[j - 1], s[j - 1], w[j - 1], n[j], s[j], w[j])):
            if j - j0 > best_len:                       # close the run before this bin, start anew
                best_j, best_len = j0, j - j0
            j0 = j
        elif st and j0 < 0:
            j0 = j
        if not st and j0 >= 0:
            if j - j0 > best_len:
                best_j, best_len = j0, j - j0
            j0 = -1
    return best_j, best_len


def calibrate(rows) -> Calib:
    t0, n, s, ss = still_bins(rows)
    best_j, best_len = _best_run(n, s, [bin_is_still(n[j], s[j], ss[j]) for j in range(len(n))])
    if CAL_NOISE_ON and t0 is not None and best_len * BLOCK_S < MIN_STILL_S:
        nd, d2 = noise_bins(rows, t0)
        best_j, best_len = _best_run(n, s, [bin_is_still_denoised(n[j], s[j], ss[j], nd[j], d2[j])
                                            for j in range(len(n))], [white_var(nd[j], d2[j]) for j in range(len(n))])
    first_valid = next((i for i, (t, v) in enumerate(rows) if t is not None and is_valid(v)), len(rows))
    if t0 is None or best_len * BLOCK_S < MIN_STILL_S:
        return Calib(initialise(init_window(rows)), first_valid, None)
    trim = int(TRIM_S / BLOCK_S)
    c0, c1 = best_j, best_j + best_len
    if (best_len - 2 * trim) * BLOCK_S >= MIN_STILL_S:
        c0, c1 = c0 + trim, c1 - trim
    cnt = 0
    tot = [0.0] * 6
    for j in range(c0, c1):
        cnt += n[j]
        for i in range(6):
            tot[i] += s[j][i]
    m = [tot[i] / cnt for i in range(6)]
    q, fn = _tilt(m[3], m[4], m[5])
    t_mid = t0 + best_j * int(BLOCK_S * 1e9) + (best_len * int(BLOCK_S * 1e9)) // 2
    anchor = next(i for i, (t, v) in enumerate(rows) if t is not None and is_valid(v) and t >= t_mid)
    if anchor > PRE_MAX_ROWS:
        return Calib(initialise(init_window(rows)), first_valid, None)
    return Calib(Init(q, (m[0], m[1], m[2]), fn, True, cnt), anchor,
                 (best_j * BLOCK_S, (best_j + best_len) * BLOCK_S))


def rotate(q, vx, vy, vz):
    """R(q) v, v' = v + w t + u x t with t = 2 u x v."""
    w, x, y, z = q
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty),
            vy + w * ty + (z * tx - x * tz),
            vz + w * tz + (x * ty - y * tx))


def exp_step(wx, wy, wz, dt):
    """Quaternion of the rotation (wx, wy, wz) * dt."""
    th2 = (wx * wx + wy * wy + wz * wz) * dt * dt
    if th2 < 1e-8:
        c = 1.0 - th2 / 8.0
        k = 0.5 * dt * (1.0 - th2 / 24.0)
    else:
        th = math.sqrt(th2)
        c = math.cos(0.5 * th)
        k = math.sin(0.5 * th) * dt / th
    return c, wx * k, wy * k, wz * k


def qmul_normalised(q, d):
    w, x, y, z = q
    c, kx, ky, kz = d
    nw = w * c - x * kx - y * ky - z * kz
    nx = w * kx + x * c + y * kz - z * ky
    ny = w * ky - x * kz + y * c + z * kx
    nz = w * kz + x * ky - y * kx + z * c
    inv = 1.0 / math.sqrt(nw * nw + nx * nx + ny * ny + nz * nz)
    return nw * inv, nx * inv, ny * inv, nz * inv


def estimate(rows, init: Init | None = None):
    """rows: list of (t_ns or None, six floats), one per data row. Returns one
    (px, py, pz, qw, qx, qy, qz) per row. With `init` given (tests, oracle tools) the still-run
    calibration is skipped and integration starts at the first valid row, as in step 6a."""
    if init is None:
        cal = calibrate(rows)
        init, anchor = cal.init, cal.anchor
    else:
        anchor = next((i for i, (t, v) in enumerate(rows) if t is not None and is_valid(v)), len(rows))
    out = backward(rows, anchor, init)
    q = init.q
    bgx, bgy, bgz = init.bg
    g = init.g
    p = [0.0, 0.0, 0.0]
    v = [0.0, 0.0, 0.0]
    t_last = None
    prev = None               # (bias-corrected gyro, world specific force) of the previous sample
    for t, vals in rows[anchor:]:
        if t is not None:
            if is_valid(vals):
                if t_last is None:
                    t_last = t
                    prev = _sample(q, vals, bgx, bgy, bgz)
                else:
                    dt = (t - t_last) * 1e-9
                    if 0 < dt <= MAX_JUMP_S:
                        if dt <= MAX_DT and prev is not None:
                            q, p, v, prev = _step(q, p, v, prev, vals, bgx, bgy, bgz, g, dt)
                        else:
                            np_ = [p[0] + v[0] * dt, p[1] + v[1] * dt, p[2] + v[2] * dt]
                            p = np_
                            prev = _sample(q, vals, bgx, bgy, bgz)
                        t_last = t
            elif t_last is not None:
                dt = (t - t_last) * 1e-9
                if 0 < dt <= MAX_JUMP_S:
                    p = [p[0] + v[0] * dt, p[1] + v[1] * dt, p[2] + v[2] * dt]
                    t_last = t
                    prev = None
        out.append((p[0], p[1], p[2], q[0], q[1], q[2], q[3]))
    return out


def backward(rows, anchor, init):
    """Poses of rows[:anchor], integrating backward in time from the anchor row (state: init.q,
    p = v = 0). Mirrors the forward rules; an ignored row repeats the pose of the row after it."""
    out = [None] * anchor
    q = init.q
    if anchor >= len(rows):                     # no valid row at all
        return [(0.0, 0.0, 0.0) + tuple(q)] * anchor
    bgx, bgy, bgz = init.bg
    g = init.g
    p = [0.0, 0.0, 0.0]
    v = [0.0, 0.0, 0.0]
    t_next = rows[anchor][0]
    nxt = _sample(q, rows[anchor][1], bgx, bgy, bgz)
    for i in range(anchor - 1, -1, -1):
        t, vals = rows[i]
        if t is not None:
            dt = (t_next - t) * 1e-9
            if is_valid(vals):
                if 0 < dt <= MAX_JUMP_S:
                    if dt <= MAX_DT and nxt is not None:
                        q, p, v, nxt = _step_back(q, p, v, nxt, vals, bgx, bgy, bgz, g, dt)
                    else:
                        p = [p[0] - v[0] * dt, p[1] - v[1] * dt, p[2] - v[2] * dt]
                        nxt = _sample(q, vals, bgx, bgy, bgz)
                    t_next = t
            elif 0 < dt <= MAX_JUMP_S:
                p = [p[0] - v[0] * dt, p[1] - v[1] * dt, p[2] - v[2] * dt]
                t_next = t
                nxt = None
        out[i] = (p[0], p[1], p[2], q[0], q[1], q[2], q[3])
    return out


def _step_back(q, p, v, nxt, vals, bgx, bgy, bgz, g, dt):
    """Inverse of _step: from the later state to the state at this row's time."""
    gx, gy, gz, ax, ay, az = vals
    cx, cy, cz = gx - bgx, gy - bgy, gz - bgz
    wx, wy, wz = -0.5 * (nxt[0] + cx), -0.5 * (nxt[1] + cy), -0.5 * (nxt[2] + cz)
    nq = qmul_normalised(q, exp_step(wx, wy, wz, dt))
    fwx, fwy, fwz = rotate(nq, ax, ay, az)
    awx = 0.5 * (nxt[3] + fwx)
    awy = 0.5 * (nxt[4] + fwy)
    awz = 0.5 * (nxt[5] + fwz) - g
    hdt2 = 0.5 * dt * dt
    np_ = [p[0] - v[0] * dt + awx * hdt2, p[1] - v[1] * dt + awy * hdt2, p[2] - v[2] * dt + awz * hdt2]
    nv = [v[0] - awx * dt, v[1] - awy * dt, v[2] - awz * dt]
    chk = np_[0] + np_[1] + np_[2] + nv[0] + nv[1] + nv[2] + nq[0]
    if chk - chk != 0:
        return q, p, v, None
    return nq, np_, nv, (cx, cy, cz, fwx, fwy, fwz)


def _sample(q, vals, bgx, bgy, bgz):
    gx, gy, gz, ax, ay, az = vals
    return (gx - bgx, gy - bgy, gz - bgz) + rotate(q, ax, ay, az)


def _step(q, p, v, prev, vals, bgx, bgy, bgz, g, dt):
    gx, gy, gz, ax, ay, az = vals
    cx, cy, cz = gx - bgx, gy - bgy, gz - bgz
    wx, wy, wz = 0.5 * (prev[0] + cx), 0.5 * (prev[1] + cy), 0.5 * (prev[2] + cz)
    nq = qmul_normalised(q, exp_step(wx, wy, wz, dt))
    fwx, fwy, fwz = rotate(nq, ax, ay, az)
    awx = 0.5 * (prev[3] + fwx)
    awy = 0.5 * (prev[4] + fwy)
    awz = 0.5 * (prev[5] + fwz) - g
    hdt2 = 0.5 * dt * dt
    np_ = [p[0] + v[0] * dt + awx * hdt2, p[1] + v[1] * dt + awy * hdt2, p[2] + v[2] * dt + awz * hdt2]
    nv = [v[0] + awx * dt, v[1] + awy * dt, v[2] + awz * dt]
    chk = np_[0] + np_[1] + np_[2] + nv[0] + nv[1] + nv[2] + nq[0]
    if chk - chk != 0:                         # non-finite: discard this update
        return q, p, v, None
    return nq, np_, nv, (cx, cy, cz, fwx, fwy, fwz)


def rows_from_raw(raw):
    """vortex.data.euroc.RawImu -> rows for estimate() (t_ns -1 means no integer timestamp)."""
    rows = []
    for i in range(len(raw)):
        t = int(raw.t_ns[i])
        vals = tuple(float(x) for x in raw.gyro[i]) + tuple(float(x) for x in raw.accel[i])
        rows.append((None if t < 0 else t, vals))
    return rows


def estimate_file(path):
    from ..data import euroc
    return estimate(rows_from_raw(euroc.read_imu_csv(path)))

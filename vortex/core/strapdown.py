"""Reference estimator, step 6a: initialisation and strapdown integration. Plain Python floats, no
numpy, so main.py (the optimised twin) can match it to rounding.

Conventions: quaternion (w, x, y, z), Hamilton, body-to-world. World frame: z up, gravity
(0, 0, -g); yaw and origin are arbitrary (zero at the first valid row), because the scorer aligns
the trajectory. Gyro in rad/s (body), accel is specific force in m/s^2 (+g up at rest).

Initialisation (gravity alignment is unknown, so it is estimated):
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
MAX_SUMSQ = 1e8            # a row whose six values' sum of squares reaches this is invalid (values of
                           # order 1e4; the ADIS16448 range is about 17 rad/s and 180 m/s^2)


@dataclass
class Init:
    q: tuple            # (w, x, y, z)
    bg: tuple           # gyro bias, rad/s
    g: float            # gravity magnitude, m/s^2
    still: bool
    rows: int


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
    (px, py, pz, qw, qx, qy, qz) per row."""
    if init is None:
        init = initialise(init_window(rows))
    q = init.q
    bgx, bgy, bgz = init.bg
    g = init.g
    p = [0.0, 0.0, 0.0]
    v = [0.0, 0.0, 0.0]
    t_last = None
    prev = None               # (bias-corrected gyro, world specific force) of the previous sample
    out = []
    for t, vals in rows:
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

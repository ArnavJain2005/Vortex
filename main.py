"""Vortex, Samsung PRISM XR Hackathon 2026, Track 3: trajectory from a degraded IMU.

    python -S main.py <imu0/data.csv> <estimated_trajectory.txt>

Pure Python, standard library only, single thread, offline, deterministic. Standalone: it never
imports the `vortex` package. The readable reference implementation is vortex/core/strapdown.py;
tests/test_core_equivalence.py keeps the two in lockstep (same rules, same arithmetic order).

Output: one line `timestamp tx ty tz qx qy qz qw` per input data row, same order. A data row is any
line that is not blank and does not start with '#' (vortex/rowspec.py states the same rule). The
timestamp is the input ns value with the decimal point moved 9 digits left, done on the text, so it
is exact. A row whose timestamp is not an integer repeats the previous row's timestamp.

STATUS (step 6a): initialisation (gravity direction, gyro bias and g from the first second) and
strapdown integration (trapezoid). No witnesses yet, so position drifts like dead reckoning. Rules
for gaps, invalid rows and bad timestamps: see vortex/core/strapdown.py. Performance: Docs/BUDGET.md.
"""
import math
import sys

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


def _initialise(win):
    """(qw, qx, qy, qz, bgx, bgy, bgz, g) from the init window (see vortex/core/strapdown.py)."""
    sqrt = math.sqrt
    n = len(win)
    if n == 0:
        return 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, G_DEFAULT
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
        return 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, G_DEFAULT
    ux, uy, uz = fx / fn, fy / fn, fz / fn
    if 1.0 + uz < 1e-9:
        qw, qx, qy, qz = 0.0, 1.0, 0.0, 0.0
    else:
        w, x, y = 1.0 + uz, uy, -ux
        k = 1.0 / sqrt(w * w + x * x + y * y)
        qw, qx, qy, qz = w * k, x * k, y * k, 0.0
    if still:
        return qw, qx, qy, qz, mean[0], mean[1], mean[2], fn
    return qw, qx, qy, qz, 0.0, 0.0, 0.0, G_DEFAULT


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
    if integrate:
        qw, qx, qy, qz, bgx, bgy, bgz, g = _initialise(_init_window(src))
    else:
        qw, qx, qy, qz, bgx, bgy, bgz, g = 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, G_DEFAULT
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

"""Step L1 (18 Nov 2026): trust-scaled shrinkage of the output positions about their own centroid.

Reference; pathfinder.py copies it bit-identically (`_sh_*`). Plain Python floats, no numpy.

Why. The organisers score APE after an SE(3) Umeyama fit on the run itself. For an output
p_out = c + alpha (p - c), with c the centroid of the estimate (one fixed point per file), the fitted
rotation does not depend on alpha (it maximises tr(R^T alpha C)), and

    APE^2(alpha) = sig_g^2 + alpha^2 sig_p^2 - 2 alpha ||C||_*

with sig_g, sig_p the RMS spread of truth and estimate about their centroids and ||C||_* the nuclear norm
(Umeyama's determinant sign) of their cross-covariance. alpha = 0 is exactly the never-moving floor,
alpha = 1 the estimate as it is; the curve is convex, so the best alpha beats both. Ground truth is never
read: alpha is a constant per noise class, chosen on the tuning set.

Noise class. The script's severity ramps to its maximum at the end of the file. The meter is the gyro's
per-sample white-noise standard deviation from second differences, x[k] - 2 x[k-1] + x[k-2] (variance
6 sigma^2 for white noise; smooth motion nearly cancels), measured in BIN_S bins over the WIN_S seconds
that end BLIND_S seconds before the last timestamp (the last 5 s are invalid by the FAQ), as the median of
the bins (spikes do not move a median). sigma > SHRINK_NOISE is the high-noise class.
Physics, not tuned: clean EuRoC flight reads about 0.04 rad/s (rotor vibration, Step 6c); the script's
gyro white noise at full severity is 0.015 rad/s (reading b) and 0.20 rad/s (reading a, where the gyro
columns get the accelerometer settings); SHRINK_NOISE = 0.10 sits between.

A row is valid for the meter when it has an integer timestamp, six finite values and a non-zero
accelerometer triple. Second differences need three consecutive valid rows with 0 < dt <= MAX_DT and the
two steps within 25 % of each other (missing rows would put motion into the difference).
"""
import math

SHRINK_ON = False
SHRINK_NOISE = 0.10          # rad/s per sample: class threshold (physics, see above; not tuned)
SHRINK_WIN_S = 20.0          # s: meter window length
SHRINK_BLIND_S = 5.0         # s: the window ends this long before the last timestamp (FAQ: last 5 s invalid)
SHRINK_BIN_S = 0.25          # s: meter bin (the filter tick)
SHRINK_BIN_MIN = 5           # second differences needed in a bin
SHRINK_MAX_DT = 0.1          # s: as strapdown.MAX_DT
SHRINK_ALPHA_LO = 0.10       # high-noise class: lowest tuning objective, MH_01/02 a (tools/shrink_tune.py)
SHRINK_ALPHA_HI = 0.20       # low-noise class: lowest tuning objective, MH_01/02 b + clean (flat: 59.85 vs 61.76 at 1.0)

LAST = [None]                # (sigma, alpha) of the last file


def gyro_noise(rows):
    """Median per-bin gyro white-noise sigma (rad/s per sample) in the meter window; -1.0 if no bin.
    rows: (t_ns or None, (gx, gy, gz, ax, ay, az)) in file order."""
    bin_ns = int(SHRINK_BIN_S * 1e9)
    max_dt = int(SHRINK_MAX_DT * 1e9)
    t0 = None
    t_last = None
    h1 = h2 = None               # (t, gx, gy, gz) of the last two valid rows
    bins = []
    cur = -1
    s = 0.0
    c = 0
    for t, v in rows:
        if t is None:
            continue
        t_last = t
        gx, gy, gz, ax, ay, az = v
        ok = (gx - gx == 0.0 and gy - gy == 0.0 and gz - gz == 0.0 and ax - ax == 0.0 and ay - ay == 0.0
              and az - az == 0.0 and (ax != 0.0 or ay != 0.0 or az != 0.0))
        if not ok:
            h1 = h2 = None
            continue
        if t0 is None:
            t0 = t
        if h1 is not None and 0 < t - h1[0] <= max_dt:
            if h2 is not None:
                d1 = h1[0] - h2[0]
                d2 = t - h1[0]
                if 4 * abs(d2 - d1) <= d1:
                    e0 = gx - 2.0 * h1[1] + h2[1]
                    e1 = gy - 2.0 * h1[2] + h2[2]
                    e2 = gz - 2.0 * h1[3] + h2[3]
                    b = (t - t0) // bin_ns
                    if b != cur:
                        if c >= SHRINK_BIN_MIN:
                            bins.append((cur, s / c))
                        cur = b
                        s = 0.0
                        c = 0
                    s += e0 * e0 + e1 * e1 + e2 * e2
                    c += 1
            h2 = h1
        else:
            h2 = None
        h1 = (t, gx, gy, gz)
    if c >= SHRINK_BIN_MIN:
        bins.append((cur, s / c))
    if t0 is None:
        return -1.0
    hi = t_last - int(SHRINK_BLIND_S * 1e9)
    lo = hi - int(SHRINK_WIN_S * 1e9)
    sel = sorted(m for b, m in bins if t0 + b * bin_ns >= lo and t0 + (b + 1) * bin_ns <= hi)
    if not sel:
        return -1.0
    k = len(sel) // 2
    med = sel[k] if len(sel) % 2 else 0.5 * (sel[k - 1] + sel[k])
    return math.sqrt(med / 18.0)


def choose_alpha(sigma):
    return SHRINK_ALPHA_LO if sigma > SHRINK_NOISE else SHRINK_ALPHA_HI


def apply(out, alpha):
    """out: (px, py, pz, qw, qx, qy, qz) per row; positions scaled by alpha about their centroid."""
    if alpha == 1.0 or not out:
        return out
    sx = sy = sz = 0.0
    for r in out:
        sx += r[0]
        sy += r[1]
        sz += r[2]
    n = len(out)
    cx = sx / n
    cy = sy / n
    cz = sz / n
    return [(cx + alpha * (r[0] - cx), cy + alpha * (r[1] - cy), cz + alpha * (r[2] - cz)) + tuple(r[3:])
            for r in out]


def shrink(rows, out):
    """The L1 output for estimate() rows/out when SHRINK_ON; records (sigma, alpha) in LAST."""
    LAST[0] = None
    if not SHRINK_ON:
        return out
    sigma = gyro_noise(rows)
    alpha = choose_alpha(sigma)
    LAST[0] = (sigma, alpha)
    return apply(out, alpha)

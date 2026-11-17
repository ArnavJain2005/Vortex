"""Input front end (Step 2, 17 Nov 2026): which columns are the accelerometer, the timestamp unit and the
accelerometer unit, decided from the data. Reference for pathfinder.py's `_frontend` (same rules, same
arithmetic; tests/test_frontend.py keeps them in lockstep). Standard library only.

Why: the organisers' degrade_imu.py treats columns 2-4 as accelerometer and 5-7 as gyro, while EuRoC
files are gyro first; their script also accepts timestamps in s, ms, us or ns and acceleration in m/s^2
or g. We do not know which layout the evaluation file has.

Rules (decided on the first DETECT_ROWS data rows; a data row is any line that is not blank and does
not start with '#', as everywhere else):
- Accelerometer triple: for each triple, n = median norm and r = (p75 - p25) / n over rows whose
  triple is finite and not exactly zero. Accelerometer-likeness s = d + r, d = min(|ln(n / G)|,
  |ln(n / 1)|): gravity makes the accelerometer norm sit near 9.81 m/s^2 (or 1 g) and vary little,
  the gyro norm is small and varies a lot. The triple with the lower s is the accelerometer if the
  other's s is higher by at least ORDER_MARGIN; otherwise the header decides (names starting with
  w / containing gyr or rad vs a / acc), and failing that the EuRoC order (gyro first).
- Timestamp unit from the median positive step (same thresholds as degrade_imu.py): < 1 -> s,
  < 1e3 -> ms, < 1e6 -> us, else ns. Output is always seconds: timestamps are converted to integer
  nanoseconds on the TEXT (decimal point moved), so integer inputs stay exact.
- Accelerometer unit: median accelerometer norm in (0.5, 2.0) -> g, scaled by G = 9.80665 (the
  script's constant); else m/s^2.
- Gyro in deg/s cannot be told apart safely from a fast rad/s motion: it is only flagged
  (`gyro_suspect` when the median gyro norm exceeds GYRO_SUSPECT rad/s), never converted.

If the file is already canonical (gyro first, integer ns, m/s^2) nothing changes: the estimator reads
it as before, so every earlier result on EuRoC files is unchanged.
"""
from __future__ import annotations

import math

DETECT_ROWS = 4000         # 20 s at 200 Hz
ORDER_MARGIN = 0.5         # accelerometer-likeness gap needed to trust the data over the header
G_SCRIPT = 9.80665         # degrade_imu.py's G (g -> m/s^2)
G_LO, G_HI = 0.5, 2.0      # median norm range read as g (degrade_imu.py's rule)
GYRO_SUSPECT = 3.0         # rad/s median norm: above this a deg/s gyro is suspected (flag only)
CANON_HEADER = ("#timestamp [ns],w_RS_S_x [rad s^-1],w_RS_S_y [rad s^-1],w_RS_S_z [rad s^-1],"
                "a_RS_S_x [m s^-2],a_RS_S_y [m s^-2],a_RS_S_z [m s^-2]")
SHIFT = {"s": 9, "ms": 6, "us": 3, "ns": 0}


def is_data(line: bytes) -> bool:
    s = line.strip()
    return bool(s) and s[0] != 35


def _num(x: bytes) -> float:
    try:
        return float(x)
    except ValueError:
        return float("nan")


def _median(xs):
    """Median of a non-empty list (sorted in place)."""
    xs.sort()
    n = len(xs)
    h = n // 2
    return xs[h] if n % 2 else 0.5 * (xs[h - 1] + xs[h])


def _quart(xs, f):
    """Value at fraction f of a SORTED list (nearest rank, floor)."""
    return xs[int(f * (len(xs) - 1))]


def _likeness(norms):
    """(s, median) for one triple's norms; s = inf when there are fewer than 10."""
    if len(norms) < 10:
        return float("inf"), float("nan")
    m = _median(norms)
    if not m > 0.0:
        return float("inf"), m
    r = (_quart(norms, 0.75) - _quart(norms, 0.25)) / m
    d = min(abs(math.log(m / G_SCRIPT)), abs(math.log(m)))
    return d + r, m


def _header_order(header: bytes | None):
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


def detect(path) -> dict:
    """Layout of an IMU csv. Keys: order ('gyro_first' | 'accel_first'), order_from ('data' | 'header'
    | 'default'), header_order, ts_unit, ts_digits (all timestamps of the sampled rows are digits),
    accel_scale (1.0 or G_SCRIPT), accel_unit, gyro_suspect, s1, s2 (likeness of columns 1-3 and 4-6),
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
            if not is_data(line):
                if header is None and rows == 0 and line.strip()[:1] == b"#":
                    header = line.strip()
                continue
            rows += 1
            p = line.split(b",")
            ts = p[0].strip()
            if not ts.isdigit():
                digits = False
            t = _num(ts)
            if t == t and prev is not None and t > prev:
                steps.append(t - prev)
            if t == t:
                prev = t
            v = [_num(p[i]) if i < len(p) else float("nan") for i in range(1, 7)]
            a = v[0] * v[0] + v[1] * v[1] + v[2] * v[2]
            b = v[3] * v[3] + v[4] * v[4] + v[5] * v[5]
            if a == a and a < 1e30 and a > 0.0:
                n1.append(math.sqrt(a))
            if b == b and b < 1e30 and b > 0.0:
                n2.append(math.sqrt(b))
            if rows >= DETECT_ROWS:
                break
    s1, m1 = _likeness(n1)
    s2, m2 = _likeness(n2)
    hdr = _header_order(header)
    if s2 + ORDER_MARGIN <= s1:
        order, src = "gyro_first", "data"
    elif s1 + ORDER_MARGIN <= s2:
        order, src = "accel_first", "data"
    elif hdr is not None:
        order, src = hdr, "header"
    else:
        order, src = "gyro_first", "default"
    m_acc, m_gyr = (m2, m1) if order == "gyro_first" else (m1, m2)
    g_unit = m_acc == m_acc and G_LO < m_acc < G_HI
    if steps:
        dt = _median(steps)
        unit = "s" if dt < 1.0 else "ms" if dt < 1e3 else "us" if dt < 1e6 else "ns"
    else:
        unit = "ns"
    lay = {"order": order, "order_from": src, "header_order": hdr, "ts_unit": unit, "ts_digits": digits,
           "accel_scale": G_SCRIPT if g_unit else 1.0, "accel_unit": "g" if g_unit else "m/s^2",
           "gyro_suspect": m_gyr == m_gyr and m_gyr > GYRO_SUSPECT, "s1": s1, "s2": s2}
    lay["canonical"] = order == "gyro_first" and unit == "ns" and digits and not g_unit
    return lay


def ns_text(ts: bytes, shift: int) -> bytes:
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


def canonical_lines(path, lay):
    """The file's data rows rewritten canonically (bytes lines, '\\n' ends): integer ns timestamp, gyro
    first, accelerometer in m/s^2. Same number and order of data rows; non-data lines dropped; a canonical
    header first. Fields that are not numbers stay as they are (reordered only)."""
    shift = SHIFT[lay["ts_unit"]]
    acc_first = lay["order"] == "accel_first"
    k = lay["accel_scale"]
    yield CANON_HEADER.encode() + b"\n"
    with open(path, "rb") as f:
        if f.peek(3)[:3] == b"\xef\xbb\xbf":
            f.read(3)
        for line in f:
            if not is_data(line):
                continue
            p = line.strip().split(b",")
            p += [b""] * (7 - len(p))
            ts = ns_text(p[0], shift)
            g, a = (p[4:7], p[1:4]) if acc_first else (p[1:4], p[4:7])
            if k != 1.0:
                a = [repr(_num(x) * k).encode() for x in a]
            else:
                a = [x.strip() for x in a]
            yield b",".join([ts] + [x.strip() for x in g] + a) + b"\n"

"""Vortex, Samsung PRISM XR Hackathon 2026, Track 3: trajectory from a degraded IMU.

    python -S main.py <imu0/data.csv> <estimated_trajectory.txt>

Pure Python, standard library only, single thread, offline, deterministic. Standalone: it never
imports the `vortex` package (the readable reference implementation lives in vortex/core/).

Output: one line `timestamp tx ty tz qx qy qz qw` per input data row, same order. A data row is any
line that is not blank and does not start with '#' (vortex/rowspec.py states the same rule). The
timestamp is the input ns value with the decimal point moved 9 digits left, done on the text, so it
is exact. A row whose timestamp is not an integer repeats the previous row's timestamp.

STATUS (step 3 skeleton): parsing and output are final; every pose is the identity. The estimator
replaces the identity in later steps. Performance notes and measurements: Docs/BUDGET.md.
"""
import sys

READ_BUF = 1 << 16   # 64 KB: 1 MB gave no speed-up and +0.9 MB RSS (Docs/FLOOR.md)
CHUNK = 256          # output lines per write(): 4096 cost +1.1 MB tracemalloc, no speed-up
FMT = b"%s.%s %.6f %.6f %.6f %.7f %.7f %.7f %.7f\n"
BOM = b"\xef\xbb\xbf"
NAN = float("nan")


def _slow_fields(p):
    """Bad, empty or short value fields (rare): each unparseable value becomes NaN."""
    v = [NAN] * 6
    for i in range(1, min(len(p), 7)):
        try:
            v[i - 1] = float(p[i])
        except ValueError:
            pass
    return v


def run(src, dst, write=True):
    """Stream src -> dst. Returns the number of data rows. write=False parses only (benchmarks)."""
    fl = float
    fmt = FMT
    slow = _slow_fields
    n = 0
    gx = gy = gz = ax = ay = az = NAN
    tx = ty = tz = 0.0
    qx = qy = qz = 0.0
    qw = 1.0
    sec = b"0"
    frac = b"000000000"
    out = []
    ap = out.append
    k = CHUNK
    with open(src, "rb", buffering=READ_BUF) as f, open(dst, "wb") as g:
        w = g.write
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
                if len(ts) > 9:
                    sec = ts[:-9]
                    frac = ts[-9:]
                else:
                    sec = b"0"
                    frac = ts.rjust(9, b"0")
            # else: not an integer timestamp, keep the previous one
            try:
                gx = fl(p[1]); gy = fl(p[2]); gz = fl(p[3])
                ax = fl(p[4]); ay = fl(p[5]); az = fl(p[6])
            except (ValueError, IndexError):
                gx, gy, gz, ax, ay, az = slow(p)
            n += 1
            if write:
                ap(fmt % (sec, frac, tx, ty, tz, qx, qy, qz, qw))
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

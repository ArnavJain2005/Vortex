"""Floor-measurement worker: runs ONE I/O variant and prints its in-process timing as one JSON line.

Stdlib only, and only `sys` and `time` are imported (plus tracemalloc with --trace), so the
process's RSS is close to what a minimal main.py would pay. The harness (measure_floor.py)
launches this script and measures the whole process from outside.

Usage: python floor_worker.py MODE IN.csv OUT.txt [--buf BYTES] [--chunk LINES] [--trace]

Modes
  noop          start, exit (interpreter + this script's compile)
  read          iterate lines in binary
  parse_bytes   binary lines -> split(b',') -> 6 float() + timestamp slices
  parse_str     text lines   -> split(',')  -> 6 float() + timestamp slices
  pw_bytes_id   parse_bytes + write identity poses, bytes %-format, binary file
  pw_str_id     parse_str   + write identity poses, str %-format, text file
  pw_bytes_real as pw_bytes_id, but position = parsed accel and a non-trivial unit quaternion,
                so %.6f / %.7f format real-looking numbers instead of 0.0
  pw_str_real   same for str

Every mode keeps every data row; a short row reuses the previous values (as main.py will).
"""
import sys
from time import perf_counter, process_time

FMT_B = b"%s.%s %.6f %.6f %.6f %.7f %.7f %.7f %.7f\n"
FMT_S = "%s.%s %.6f %.6f %.6f %.7f %.7f %.7f %.7f\n"
CHUNK = 4096   # output lines per write(); override with --chunk N


def m_noop(src, dst, buf, real):
    return 0


def m_read(src, dst, buf, real):
    n = 0
    with open(src, "rb", buffering=buf) as f:
        for line in f:
            n += 1
    return n


def m_parse_bytes(src, dst, buf, real):
    fl = float
    n = 0
    gx = gy = gz = ax = ay = az = 0.0
    with open(src, "rb", buffering=buf) as f:
        for line in f:
            if line[0] == 35:          # b'#'
                continue
            p = line.split(b",")
            ts = p[0]
            if len(ts) < 10:
                ts = ts.rjust(10, b"0")
            sec = ts[:-9]
            frac = ts[-9:]
            if len(p) == 7:
                gx = fl(p[1]); gy = fl(p[2]); gz = fl(p[3])
                ax = fl(p[4]); ay = fl(p[5]); az = fl(p[6])
            n += 1
    return n


def m_parse_str(src, dst, buf, real):
    fl = float
    n = 0
    gx = gy = gz = ax = ay = az = 0.0
    with open(src, "r", buffering=buf, encoding="ascii") as f:
        for line in f:
            if line[0] == "#":
                continue
            p = line.split(",")
            ts = p[0]
            if len(ts) < 10:
                ts = ts.rjust(10, "0")
            sec = ts[:-9]
            frac = ts[-9:]
            if len(p) == 7:
                gx = fl(p[1]); gy = fl(p[2]); gz = fl(p[3])
                ax = fl(p[4]); ay = fl(p[5]); az = fl(p[6])
            n += 1
    return n


def m_pw_bytes(src, dst, buf, real):
    fl = float
    fmt = FMT_B
    n = 0
    gx = gy = gz = ax = ay = az = 0.0
    tx = ty = tz = 0.0
    if real:
        qx, qy, qz, qw = 0.1234567, -0.2345678, 0.3456789, 0.8995023
    else:
        qx, qy, qz, qw = 0.0, 0.0, 0.0, 1.0
    out = []
    ap = out.append
    k = CHUNK
    with open(src, "rb", buffering=buf) as f, open(dst, "wb") as g:
        w = g.write
        for line in f:
            if line[0] == 35:
                continue
            p = line.split(b",")
            ts = p[0]
            if len(ts) < 10:
                ts = ts.rjust(10, b"0")
            if len(p) == 7:
                gx = fl(p[1]); gy = fl(p[2]); gz = fl(p[3])
                ax = fl(p[4]); ay = fl(p[5]); az = fl(p[6])
            if real:
                tx = ax; ty = ay; tz = az
            ap(fmt % (ts[:-9], ts[-9:], tx, ty, tz, qx, qy, qz, qw))
            n += 1
            k -= 1
            if not k:
                w(b"".join(out))
                out.clear()
                k = CHUNK
        if out:
            w(b"".join(out))
    return n


def m_pw_str(src, dst, buf, real):
    fl = float
    fmt = FMT_S
    n = 0
    gx = gy = gz = ax = ay = az = 0.0
    tx = ty = tz = 0.0
    if real:
        qx, qy, qz, qw = 0.1234567, -0.2345678, 0.3456789, 0.8995023
    else:
        qx, qy, qz, qw = 0.0, 0.0, 0.0, 1.0
    out = []
    ap = out.append
    k = CHUNK
    with open(src, "r", buffering=buf, encoding="ascii") as f, \
            open(dst, "w", encoding="ascii", newline="\n") as g:
        w = g.write
        for line in f:
            if line[0] == "#":
                continue
            p = line.split(",")
            ts = p[0]
            if len(ts) < 10:
                ts = ts.rjust(10, "0")
            if len(p) == 7:
                gx = fl(p[1]); gy = fl(p[2]); gz = fl(p[3])
                ax = fl(p[4]); ay = fl(p[5]); az = fl(p[6])
            if real:
                tx = ax; ty = ay; tz = az
            ap(fmt % (ts[:-9], ts[-9:], tx, ty, tz, qx, qy, qz, qw))
            n += 1
            k -= 1
            if not k:
                w("".join(out))
                out.clear()
                k = CHUNK
        if out:
            w("".join(out))
    return n


MODES = {
    "noop": (m_noop, False),
    "read": (m_read, False),
    "parse_bytes": (m_parse_bytes, False),
    "parse_str": (m_parse_str, False),
    "pw_bytes_id": (m_pw_bytes, False),
    "pw_str_id": (m_pw_str, False),
    "pw_bytes_real": (m_pw_bytes, True),
    "pw_str_real": (m_pw_str, True),
}


def main():
    a = sys.argv
    mode, src, dst = a[1], a[2], a[3]
    buf = int(a[a.index("--buf") + 1]) if "--buf" in a else 1 << 16
    trace = "--trace" in a
    if "--chunk" in a:
        global CHUNK
        CHUNK = int(a[a.index("--chunk") + 1])
    if trace:
        import tracemalloc
        tracemalloc.start()
    fn, real = MODES[mode]
    t0 = perf_counter()
    c0 = process_time()
    rows = fn(src, dst, buf, real)
    t1 = perf_counter()
    c1 = process_time()
    peak = tracemalloc.get_traced_memory()[1] if trace else -1
    sys.stdout.write('{"rows": %d, "loop_wall_s": %.6f, "loop_cpu_s": %.6f, "tracemalloc_peak": %d}\n'
                     % (rows, t1 - t0, c1 - c0, peak))


if __name__ == "__main__":
    main()

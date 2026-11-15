"""Micro-benchmarks behind main.py's per-row parsing choices. Stdlib only.

Each variant parses the same SYNTHETIC EuRoC-format file in-process; reports median us per row.
  base         split + 6 float(), no guards (crashes on empty fields: not usable, the floor)
  try          + try/except around the 6 float() calls (zero-cost when nothing raises, 3.11+)
  len_check    + `len(p) == 7 and all fields non-empty` check instead of try (does NOT catch garbage)
  strip_all    + line.strip() on every row before splitting
  first_byte   + `line[0] < 48` test, strip only then (blank, '#', whitespace start)
  isdigit      + timestamp ts.isdigit() check
  main_like    first_byte + isdigit + try + timestamp slices (what main.py does)

Usage: python -S tools/bench_choices.py [--rows 36000] [--repeat 7]
"""
import os
import sys
import tempfile
from time import perf_counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synth_euroc  # noqa: E402


def v_base(path):
    fl = float
    with open(path, "rb", buffering=65536) as f:
        next(f)
        for line in f:
            p = line.split(b",")
            gx = fl(p[1]); gy = fl(p[2]); gz = fl(p[3]); ax = fl(p[4]); ay = fl(p[5]); az = fl(p[6])


def v_try(path):
    fl = float
    with open(path, "rb", buffering=65536) as f:
        next(f)
        for line in f:
            p = line.split(b",")
            try:
                gx = fl(p[1]); gy = fl(p[2]); gz = fl(p[3]); ax = fl(p[4]); ay = fl(p[5]); az = fl(p[6])
            except (ValueError, IndexError):
                pass


def v_len_check(path):
    fl = float
    with open(path, "rb", buffering=65536) as f:
        next(f)
        for line in f:
            p = line.split(b",")
            if len(p) == 7 and p[1] and p[2] and p[3] and p[4] and p[5] and p[6]:
                gx = fl(p[1]); gy = fl(p[2]); gz = fl(p[3]); ax = fl(p[4]); ay = fl(p[5]); az = fl(p[6])


def v_strip_all(path):
    fl = float
    with open(path, "rb", buffering=65536) as f:
        next(f)
        for line in f:
            line = line.strip()
            if not line or line[0] == 35:
                continue
            p = line.split(b",")
            gx = fl(p[1]); gy = fl(p[2]); gz = fl(p[3]); ax = fl(p[4]); ay = fl(p[5]); az = fl(p[6])


def v_first_byte(path):
    fl = float
    with open(path, "rb", buffering=65536) as f:
        next(f)
        for line in f:
            if line[0] < 48:
                line = line.strip()
                if not line or line[0] == 35:
                    continue
            p = line.split(b",")
            gx = fl(p[1]); gy = fl(p[2]); gz = fl(p[3]); ax = fl(p[4]); ay = fl(p[5]); az = fl(p[6])


def v_isdigit(path):
    fl = float
    with open(path, "rb", buffering=65536) as f:
        next(f)
        for line in f:
            p = line.split(b",")
            ts = p[0]
            if ts.isdigit():
                pass
            gx = fl(p[1]); gy = fl(p[2]); gz = fl(p[3]); ax = fl(p[4]); ay = fl(p[5]); az = fl(p[6])


def v_main_like(path):
    fl = float
    sec = b"0"
    frac = b"000000000"
    with open(path, "rb", buffering=65536) as f:
        for line in f:
            if line[0] < 48:
                line = line.strip()
                if not line or line[0] == 35:
                    continue
            p = line.split(b",")
            ts = p[0]
            if ts.isdigit() and len(ts) > 9:
                sec = ts[:-9]
                frac = ts[-9:]
            try:
                gx = fl(p[1]); gy = fl(p[2]); gz = fl(p[3]); ax = fl(p[4]); ay = fl(p[5]); az = fl(p[6])
            except (ValueError, IndexError):
                pass


VARIANTS = [("base", v_base), ("try", v_try), ("len_check", v_len_check), ("strip_all", v_strip_all),
            ("first_byte", v_first_byte), ("isdigit", v_isdigit), ("main_like", v_main_like)]


def main(argv):
    rows = int(argv[argv.index("--rows") + 1]) if "--rows" in argv else 36000
    rep = int(argv[argv.index("--repeat") + 1]) if "--repeat" in argv else 7
    path = os.path.join(tempfile.gettempdir(), "vortex_synth_%d.csv" % rows)
    if not os.path.exists(path):
        synth_euroc.write(path, rows=rows, seed=0)
    print("Python %s, %d rows (SYNTHETIC), median of %d" % (sys.version.split()[0], rows, rep))
    base = None
    for name, fn in VARIANTS:
        ts = []
        for _ in range(rep):
            t0 = perf_counter()
            fn(path)
            ts.append(perf_counter() - t0)
        us = sorted(ts)[rep // 2] / rows * 1e6
        base = us if base is None else base
        print("  %-11s %6.3f us/row  (%+6.3f vs base)" % (name, us, us - base))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

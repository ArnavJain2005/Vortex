"""Write a SYNTHETIC EuRoC-format IMU file (imu0/data.csv layout) for I/O benchmarks.

Stdlib only. Uses nothing but random.random() and + and *, so the same seed gives a byte-identical
file on every platform and Python version (no libm calls whose last bit could differ).
The numbers are not physically meaningful; only the text format matters here: 19-digit ns
timestamps at 200 Hz and doubles printed with repr() (about 17 significant digits, like EuRoC's
own files, e.g. -0.099134701513277898).

Usage: python tools/synth_euroc.py OUT.csv [--rows 36000] [--seed 0] [--decimals N] [--crlf]
"""
import random
import sys

HEADER = ("#timestamp [ns],w_RS_S_x [rad s^-1],w_RS_S_y [rad s^-1],w_RS_S_z [rad s^-1],"
          "a_RS_S_x [m s^-2],a_RS_S_y [m s^-2],a_RS_S_z [m s^-2]")
T0_NS = 1403636579758555392   # an EuRoC-like start time (19 digits)
DT_NS = 5000000               # 200 Hz


def write(path, rows=36000, seed=0, decimals=None, crlf=False):
    rng = random.Random(seed)
    nl = "\r\n" if crlf else "\n"
    fmt = repr if decimals is None else (lambda x, d=decimals: "%.*f" % (d, x))
    t = T0_NS
    with open(path, "w", encoding="ascii", newline="") as f:
        f.write(HEADER + nl)
        for i in range(rows):
            r = rng.random
            # triangle-wave motion plus uniform noise: arithmetic only, so bit-exact everywhere
            ph = (i % 400) / 200.0 - 1.0
            gx = 0.3 * ph + 0.05 * (r() - 0.5)
            gy = -0.2 * ph + 0.05 * (r() - 0.5)
            gz = 0.1 * ph + 0.05 * (r() - 0.5)
            ax = 9.3 + 0.8 * ph + 0.3 * (r() - 0.5)
            ay = -0.4 + 0.5 * ph + 0.3 * (r() - 0.5)
            az = -2.4 - 0.3 * ph + 0.3 * (r() - 0.5)
            f.write("%d,%s,%s,%s,%s,%s,%s%s" % (t, fmt(gx), fmt(gy), fmt(gz),
                                                 fmt(ax), fmt(ay), fmt(az), nl))
            t += DT_NS + int((r() - 0.5) * 512)   # small jitter, as in real logs
    return path


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    rows = int(argv[argv.index("--rows") + 1]) if "--rows" in argv else 36000
    seed = int(argv[argv.index("--seed") + 1]) if "--seed" in argv else 0
    dec = int(argv[argv.index("--decimals") + 1]) if "--decimals" in argv else None
    write(argv[1], rows, seed, dec, "--crlf" in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

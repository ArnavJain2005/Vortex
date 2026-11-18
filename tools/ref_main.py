"""The REFERENCE estimator (vortex/core) as a main.py-like script, for tuning a switch before it is copied
into pathfinder.py:  python tools/ref_main.py IMU.csv estimated_trajectory.txt

Every upper-case constant of vortex.core.witness and vortex.core.strapdown is mirrored here, so
`tools/eval_euroc.py --main tools/ref_main.py --set TILT_ON=True` works: main() copies the (possibly
overridden) values back into those modules before running. Output format as pathfinder.py. Not shipped.
"""
import os
import site
import sys

site.main()   # run with python -S by tools/eval_euroc.py; the reference package imports numpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vortex.core import strapdown as _sd  # noqa: E402
from vortex.core import witness as _wx  # noqa: E402

_NAMES = {}
for _mod in (_sd, _wx):
    for _k, _v in vars(_mod).items():
        if _k.isupper() and not callable(_v):
            globals()[_k] = _v
            _NAMES.setdefault(_k, []).append(_mod)


def main(argv):
    g = globals()
    for k, mods in _NAMES.items():
        for m in mods:
            setattr(m, k, g[k])
    rows = _wx.estimate_file(argv[1])
    ts = []
    with open(argv[1], "rb") as f:
        for line in f:
            s = line.strip()
            if s and s[0] != 35:
                ts.append(s.split(b",", 1)[0].strip())
    with open(argv[2], "wb") as f:
        for t, o in zip(ts, rows):
            sec, frac = (t[:-9], t[-9:]) if len(t) > 9 else (b"0", t.rjust(9, b"0"))
            f.write(b"%s.%s %.6f %.6f %.6f %.7f %.7f %.7f %.7f\n" % (sec, frac, o[0], o[1], o[2], o[4], o[5], o[6],
                                                                      o[3]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

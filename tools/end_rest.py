"""Step 6 check: does a flight end with a ground rest before the blind window (the zeroed last 5 s)?

For each file the shipped reference estimator runs with its tick log; we report the last tick the V1
stillness test (ZUPT) fired before the blind window, the length of that still run, and the gap from its end
to the blind window. Ground-truth speed over the same span is printed beside it as a DIAGNOSTIC only (the
estimator never sees it). V2_* (final test set) is refused.

    python tools/end_rest.py [--official] [--seqs A,B,...]      # writes Docs/END_REST.md with --write
"""
import csv
import json
import math
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from vortex.core import strapdown as sd  # noqa: E402
from vortex.core import witness as wx  # noqa: E402
from vortex.data import euroc  # noqa: E402

EUROC = os.path.join(ROOT, "data", "euroc")
OFFICIAL = os.path.join(ROOT, "data", "official")


def rows_of(path):
    lines = wx.prepare_lines(path)
    if lines is None:
        return sd.rows_from_raw(euroc.read_imu_csv(path))
    fd, tmp = tempfile.mkstemp(suffix=".csv")
    try:
        with os.fdopen(fd, "wb") as f:
            for line in lines:
                f.write(line)
        return sd.rows_from_raw(euroc.read_imu_csv(tmp))
    finally:
        os.remove(tmp)


def gt_speed(base):
    """(t_ns, speed m/s) from the ground truth's velocity columns. DIAGNOSTIC ONLY."""
    p = os.path.join(EUROC, base, "mav0", "state_groundtruth_estimate0", "data.csv")
    out = []
    with open(p, newline="") as f:
        for r in csv.reader(f):
            if not r or r[0].startswith("#"):
                continue
            out.append((int(r[0]), math.sqrt(sum(float(x) ** 2 for x in r[8:11]))))
    return out


def check(path, base, blind_ns):
    rows = rows_of(path)
    log = []
    wx.estimate(rows, log=log)
    ts = [t for t, _ in rows if t is not None]
    t0, t_end = ts[0], ts[-1]
    blind = t_end - blind_ns if blind_ns else t_end      # start of the blind window (clean: the file end)
    still = [(d["t"], d["zupt"]) for d in log if d["t"] <= blind]
    last = None
    for t, z in reversed(still):
        if z:
            last = t
            break
    run = 0.0
    if last is not None:
        first = last
        for t, z in reversed([s for s in still if s[0] <= last]):
            if not z:
                break
            first = t
        run = (last - first) * 1e-9 + wx.TICK_S
    gt = [(t, s) for t, s in gt_speed(base) if blind - 3e9 <= t <= blind]
    return {"file": os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(path)))), "base": base, "len_s": (t_end - t0) * 1e-9,
            "last_still_before_blind_s": None if last is None else (blind - last) * 1e-9,
            "still_run_s": run,
            "gt_speed_last3s_max": max(s for _, s in gt) if gt else None,
            "gt_speed_last3s_mean": sum(s for _, s in gt) / len(gt) if gt else None}


def main(argv):
    get = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    out = []
    if "--official" in argv:
        names = get("--seqs").split(",") if get("--seqs") else sorted(os.listdir(OFFICIAL))
        for n in names:
            if n.startswith("V2_"):
                continue
            meta = json.load(open(os.path.join(OFFICIAL, n, "degrade.json")))
            path = os.path.join(OFFICIAL, n, "mav0", "imu0", "data.csv")
            base = n.rsplit("_", 2)[0]                      # <seq>_<a|b>_s<seed>
            out.append(check(path, base, int(round(5e9))) | {"failure_at_s": meta.get("failure_at_s")})
    else:
        names = get("--seqs").split(",") if get("--seqs") else sorted(
            s for s in os.listdir(EUROC) if not s.startswith("V2_"))
        for n in names:
            assert not n.startswith("V2_"), "V2_* is the final test set"
            out.append(check(os.path.join(EUROC, n, "mav0", "imu0", "data.csv"), n, 0))
    for r in out:
        print("%-24s len %6.1f s | last still before blind: %s | still run %5.2f s | GT speed last 3 s mean %s max %s" % (
            r["file"], r["len_s"],
            "none" if r["last_still_before_blind_s"] is None else "%6.1f s" % r["last_still_before_blind_s"],
            r["still_run_s"], "%.3f" % r["gt_speed_last3s_mean"] if r["gt_speed_last3s_mean"] is not None else "-",
            "%.3f" % r["gt_speed_last3s_max"] if r["gt_speed_last3s_max"] is not None else "-"))
    if get("--json"):
        with open(get("--json"), "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

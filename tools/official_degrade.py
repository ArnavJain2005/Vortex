"""Degraded copies made with the ORGANISERS' degrade_imu.py (Track 3 student package), without editing it.

The script is organiser-provided and needs pandas; it is not committed (decision pending). Put it at
tools/official/degrade_imu.py (git-ignored). This wrapper imports it and calls its degrade() with a
chosen seed, max-level and gamma (the script's own CLI fixes the seed at 42).

Two column readings, because the script treats columns 2-4 as accelerometer and 5-7 as gyro while
EuRoC files are gyro first, and we do not know what the organisers feed in:
  a  the raw EuRoC file fed straight in (the gyro columns get the accelerometer-sized faults);
  b  columns reordered to accel first, degraded, written accel first (header names reordered too).

    python tools/official_degrade.py data/euroc/MH_01_easy --reading a --seed 1
    python tools/official_degrade.py --all [--seeds 1,2,3,42] [--readings a,b] [--seqs MH_01_easy,...]
    python tools/official_degrade.py --all --seqs V2_01_easy,V2_02_medium,V2_03_difficult --readings a,b --seeds 42 --final

Output: data/official/<sequence>_<reading>_s<seed>/
    mav0/imu0/data.csv   the degraded file, exactly as the script writes it (pandas to_csv)
    meta.json            the script's own statistics (what its --meta writes) + reading and source
    degrade.json         phase windows for vortex.scoring (healthy = the 2 s protected opening,
                         missing-row bursts of >= BURST_MIN rows, failure = the last 5 s)
Ground truth is not copied: scoring reads data/euroc/<sequence>. V2_* requires explicit --final.
OFFLINE tool (numpy, pandas); never imported by main.py.
"""
import argparse
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "tools", "official", "degrade_imu.py")
DATA = os.path.join(ROOT, "data", "euroc")
OUT = os.path.join(ROOT, "data", "official")
FINAL_PREFIX = "V2_"
BURST_MIN = 5          # rows: the script's burst length starts at 5; single drops are not scored as gaps


def load_script(path=SCRIPT):
    if not os.path.exists(path):
        raise SystemExit("missing %s: copy the organisers' degrade_imu.py there (git-ignored)" % path)
    spec = importlib.util.spec_from_file_location("degrade_imu_official", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def reorder_accel_first(df):
    """EuRoC gyro-first frame -> accel first (timestamp, a_x, a_y, a_z, w_x, w_y, w_z), names kept."""
    c = list(df.columns)
    return df[[c[0]] + c[4:7] + c[1:4]]


def missing_runs(t_in, t_out):
    """Index runs [i, j) of input rows whose timestamp does not appear in the output."""
    kept = set(t_out)
    runs, i, n = [], 0, len(t_in)
    while i < n:
        if t_in[i] in kept:
            i += 1
            continue
        j = i
        while j < n and t_in[j] not in kept:
            j += 1
        runs.append((i, j))
        i = j
    return runs


def guard_final(seq, final=False):
    if seq.startswith(FINAL_PREFIX) and not final:
        raise SystemExit("refused: %s is the final test set; pass --final only when told to run the final table" % seq)


def make_copy(seq_dir, reading, seed, out_root=OUT, max_level=None, gamma=None, mod=None, final=False):
    seq = os.path.basename(os.path.normpath(seq_dir))
    guard_final(seq, final)
    import pandas as pd
    if reading not in ("a", "b"):
        raise SystemExit("reading must be a or b")
    mod = mod or load_script()
    src = os.path.join(seq_dir, "mav0", "imu0", "data.csv")
    header = mod.detect_header(src)
    df = pd.read_csv(src, header=header)
    if df.shape[1] != 7:
        raise SystemExit("expected 7 columns, got %d" % df.shape[1])
    if header is None:
        df.columns = ["timestamp", "ax", "ay", "az", "gx", "gy", "gz"]
    if reading == "b":
        df = reorder_accel_first(df)
    cfg = dict(mod.CONFIG)
    if max_level is not None:
        cfg["max_level"] = max_level
    if gamma is not None:
        cfg["gamma"] = gamma
    out, stats = mod.degrade(df, cfg, seed)
    name = "%s_%s_s%d" % (seq, reading, seed)
    dst_dir = os.path.join(out_root, name)
    imu_dir = os.path.join(dst_dir, "mav0", "imu0")
    os.makedirs(imu_dir, exist_ok=True)
    out.to_csv(os.path.join(imu_dir, "data.csv"), index=False, header=header is not None)

    t_in = [int(x) for x in df[df.columns[0]].to_numpy()]
    t_out = [int(x) for x in out[out.columns[0]].to_numpy()]
    scale = {"s": 1e9, "ms": 1e6, "us": 1e3, "ns": 1.0}[stats["timestamp_unit"]]
    t0 = t_in[0]
    rel = lambda t: (t - t0) * scale / 1e9  # noqa: E731
    runs = missing_runs(t_in, t_out)
    bursts = [(i, j) for i, j in runs if j - i >= BURST_MIN]
    T = rel(t_in[-1])
    fail = T - cfg["failure_seconds"] if T > cfg["failure_seconds"] + cfg["protect_seconds"] else None
    # a burst window runs from the last kept row before it to the first kept row after it
    drops = [[rel(t_in[i - 1]) if i > 0 else rel(t_in[i]), rel(t_in[j]) if j < len(t_in) else T]
             for i, j in bursts]
    events = {"source": "official degrade_imu.py via tools/official_degrade.py", "seed": seed,
              "reading": reading, "t0_ns": int(t0 * scale), "healthy_end_s": cfg["protect_seconds"],
              "dropouts_s": drops, "dropout_rows": [j - i for i, j in bursts],
              "single_missing_rows": sum(j - i for i, j in runs if j - i < BURST_MIN),
              "failure_at_s": fail, "end_s": T, "blind_s": cfg["failure_seconds"] if fail is not None else 0.0}
    meta = dict(stats)
    meta.update({"reading": reading, "source_sequence": seq,
                 "columns_in": list(df.columns), "max_level": cfg["max_level"], "gamma": cfg["gamma"]})
    with open(os.path.join(dst_dir, "meta.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")
    with open(os.path.join(dst_dir, "degrade.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(events, f, indent=1)
        f.write("\n")
    return name, meta, events


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("seq", nargs="?", help="a clean sequence folder (data/euroc/<seq>)")
    ap.add_argument("--all", action="store_true", help="every sequence under --root except V2_*")
    ap.add_argument("--root", default=DATA, help="clean sequence root directory (default: data/euroc)")
    ap.add_argument("--seqs", help="comma list of sequence names under --root (with --all)")
    ap.add_argument("--reading", default=None, help="a or b (single copy)")
    ap.add_argument("--readings", default="a,b")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--seeds", default="1,2,3,42")
    ap.add_argument("--max-level", type=float, default=None)
    ap.add_argument("--gamma", type=float, default=None)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--final", action="store_true", help="explicitly allow the sealed V2 final test set")
    a = ap.parse_args(argv)
    if a.all:
        if a.final and not a.seqs:
            ap.error("--final with --all requires explicit --seqs")
        names = a.seqs.split(",") if a.seqs else sorted(
            n for n in os.listdir(a.root) if os.path.isdir(os.path.join(a.root, n))
        )
        for n in names:
            guard_final(n, a.final)
        seq_dirs = [os.path.join(a.root, n) for n in names if a.final or not n.startswith(FINAL_PREFIX)]
        readings = a.readings.split(",")
        seeds = [int(s) for s in a.seeds.split(",")]
    else:
        if not a.seq:
            ap.error("give a sequence folder or --all")
        guard_final(os.path.basename(os.path.normpath(a.seq)), a.final)
        seq_dir = a.seq if os.path.exists(a.seq) or not os.path.exists(os.path.join(a.root, a.seq)) else os.path.join(a.root, a.seq)
        seq_dirs = [seq_dir]
        readings = [a.reading or "a"]
        seeds = [a.seed if a.seed is not None else 42]
    mod = load_script()
    for d in seq_dirs:
        for r in readings:
            for s in seeds:
                name, m, e = make_copy(d, r, s, a.out, a.max_level, a.gamma, mod, final=a.final)
                print("%-26s rows %d -> %d  spikes %d  stuck %d  dropped %d (%d bursts)  dup %d  zeros %d  "
                      "ts %s  accel %s" % (name, m["rows_in"], m["rows_out"], m["spikes"], m["stuck_samples"],
                                           m["dropped_total"], m["dropped_burst_gaps"], m["duplicated_rows"],
                                           m["failure_frames"], m["timestamp_unit"], m["accel_unit"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

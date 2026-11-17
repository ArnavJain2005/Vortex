"""Fault front end (Step 3, 17 Nov 2026): stuck rows and spikes become missing samples. Reference for
pathfinder.py's `_ff_*` copy (same rules, same arithmetic; tests/test_faults.py keeps them in lockstep).
Standard library only. Works on canonical lines (frontend.py: integer ns, gyro first, m/s^2).

Why: the organisers' degrade_imu.py adds spikes on all six axes at once (up to 9 m/s^2 and 1.5 rad/s),
stuck runs of 2-10 identical rows (which can repeat a spike), duplicated rows, missing rows and bursts,
and exact zeros for the last 5 s; values are rounded to 6 decimals, so repeats and zeros are exact.
Before Step 3 the estimator integrated spikes and the first rows of a stuck run as if they were real.

Pieces (each its own switch, default off; decision rules in Docs/TRACK3_PLAN.md, Step 3):
- STUCK6_ON: a data row whose six values equal the previous data row's exactly is a missing sample
  (from the second row of the run on; a duplicated row is the same case). Clean EuRoC has no such
  repeat (checked on MH_01..05, V1_01..03).
- SPIKE_ON: joint outlier test. Row P is compared with the last accepted row G before it and the next
  row N that is not a repeat of P: dev = P - (G + N) / 2, separately for the gyro and accelerometer
  triples; z = squared deviation / its running mean over accepted rows (about 1 for ordinary rows). P is
  a spike when one triple is far out (max z > SPIKE_ZHI) AND the other is out too (min z > SPIKE_ZLO),
  both above a small absolute floor. (A glitch hits the whole sample; rotor vibration can hide one
  triple's part, which is why the second level is lower.) Not judged (accepted) when G and N are more than
  SPIKE_SPAN_S apart, or during the first SPIKE_WARM tested rows (the running means are built there;
  the script protects the first 2 s).
- Blind window: the trailing run of rows whose six values are all exactly 0 is left untouched (so the
  dead-sensor rule coasts through it, as before). An all-zero run that is NOT at the end of the file is
  a fault: with STUCK6_ON its rows are missing samples. Exact, no threshold.
A missing sample is written as `ts,nan,nan,nan,nan,nan,nan,m`: invalid everywhere (calibration and the
backward pass ignore it as before); with INTERP_ON (witness.py / pathfinder.py) the forward pass skips it
and integrates across with the real timestamp step instead of coasting.
"""
from __future__ import annotations

STUCK6_ON = False
SPIKE_ON = False
SPIKE_ZHI = 100.0          # z needed on the triple that is far out (chosen on MH_01/02, 17 Nov)
SPIKE_ZLO = 3.0            # z needed on the other triple (chosen on MH_01/02, 17 Nov)
SPIKE_ALPHA = 0.01         # running mean weight after the warm-up (about 100 rows, 0.5 s at 200 Hz)
SPIKE_WARM = 50            # tested rows before any row can be judged a spike
SPIKE_CLIP = 10.0          # after the warm-up a row moves the running mean by at most this many times it
                           # (an undetected spike would otherwise raise the scale and hide the next ones)
SPIKE_SPAN_NS = 50_000_000  # G..N span above which P is not judged (10 rows at 200 Hz)
SPIKE_FLOOR_G2 = 0.005 ** 2  # rad^2/s^2: deviations below this are never spikes (noiseless input)
SPIKE_FLOOR_A2 = 0.05 ** 2   # m^2/s^4
MISSING = b"nan,nan,nan,nan,nan,nan,m"


def _parse(line):
    """(t_ns or None, six floats or None, ts text) of a data line."""
    p = line.strip().split(b",")
    ts = p[0].strip()
    t = int(ts) if ts.isdigit() else None
    if len(p) < 7:
        return t, None, ts
    try:
        v = (float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5]), float(p[6]))
    except ValueError:
        return t, None, ts
    s = v[0] * v[0] + v[1] * v[1] + v[2] * v[2] + v[3] * v[3] + v[4] * v[4] + v[5] * v[5]
    if not s < 1e8:
        return t, None, ts
    return t, v, ts


def filter_lines(lines, stuck=None, spike=None, stats=None):
    """Yields the lines with stuck repeats and spikes rewritten as missing samples. Non-data lines are
    passed on at once; data rows keep their order and number. stats (dict, optional) gets counts."""
    stuck = STUCK6_ON if stuck is None else stuck
    spike = SPIKE_ON if spike is None else spike
    zhi, zlo = SPIKE_ZHI, SPIKE_ZLO
    st = {"stuck": 0, "spike": 0, "zero_mid": 0, "blind_rows": 0, "tested": 0}
    pend = None          # (t, v, ts, line): the row waiting for its next neighbour
    reps = []            # lines repeating pend exactly
    zeros = []           # buffered all-zero rows (lines, ts)
    gt = None            # last accepted row: time and values
    gv = None
    eg = ea = 0.0        # running mean squared deviations (gyro, accel)
    nw = 0

    def resolve(nt, nv):
        """Emit pend (spike-tested against gt..next) and its repeats."""
        nonlocal gt, gv, eg, ea, nw
        t, v, ts, line = pend
        flag = False
        if spike and gv is not None and nv is not None and t is not None and nt - gt <= SPIKE_SPAN_NS:
            d0 = v[0] - 0.5 * (gv[0] + nv[0])
            d1 = v[1] - 0.5 * (gv[1] + nv[1])
            d2 = v[2] - 0.5 * (gv[2] + nv[2])
            dg = d0 * d0 + d1 * d1 + d2 * d2
            d0 = v[3] - 0.5 * (gv[3] + nv[3])
            d1 = v[4] - 0.5 * (gv[4] + nv[4])
            d2 = v[5] - 0.5 * (gv[5] + nv[5])
            da = d0 * d0 + d1 * d1 + d2 * d2
            if (nw >= SPIKE_WARM and dg > SPIKE_FLOOR_G2 and da > SPIKE_FLOOR_A2
                    and ((dg > zhi * eg and da > zlo * ea) or (da > zhi * ea and dg > zlo * eg))):
                flag = True
                st["spike"] += 1
            else:
                nw += 1
                st["tested"] += 1
                if nw <= SPIKE_WARM:
                    eg += (dg - eg) / nw
                    ea += (da - ea) / nw
                else:
                    eg += (min(dg, SPIKE_CLIP * eg) - eg) * SPIKE_ALPHA
                    ea += (min(da, SPIKE_CLIP * ea) - ea) * SPIKE_ALPHA
        out = [ts + b"," + MISSING + b"\n" if flag else line]
        for rl, rts in reps:
            out.append(rts + b"," + MISSING + b"\n")
            st["stuck"] += 1
        if not flag and t is not None:
            gt, gv = t, v
        return out

    for line in lines:
        s = line.strip()
        if not s or s[0] == 35:
            yield line
            continue
        if line[-1:] != b"\n":
            line = line + b"\n"
        t, v, ts = _parse(line)
        if v is not None and t is not None and not (v[0] or v[1] or v[2] or v[3] or v[4] or v[5]):
            if pend is not None:
                yield from resolve(None, None)
                pend, reps = None, []
            zeros.append((line, ts))
            continue
        if zeros:                               # an all-zero run that is not at the end: a fault
            for zl, zts in zeros:
                if stuck:
                    yield zts + b"," + MISSING + b"\n"
                    st["zero_mid"] += 1
                else:
                    yield zl
            zeros = []
        if v is None or t is None:              # invalid row: passed on as it is
            if pend is not None:
                yield from resolve(None, None)
                pend, reps = None, []
            yield line
            continue
        if stuck and pend is not None and v == pend[1]:
            reps.append((line, ts))
            continue
        if pend is not None:
            yield from resolve(t, v)
        pend, reps = (t, v, ts, line), []
    if pend is not None:
        yield from resolve(None, None)
    for zl, _ in zeros:                         # trailing all-zero run: the blind window, untouched
        yield zl
    st["blind_rows"] = len(zeros)
    if stats is not None:
        stats.update(st)

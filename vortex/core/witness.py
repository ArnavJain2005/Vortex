"""Reference estimator, steps 7a + 6c + 8a: error-state Kalman filter with the core velocity witnesses
V1 (stillness) and V2 (flight envelope), a noise meter and dropout covariance. Plain Python floats, no numpy; main.py copies the filter
functions verbatim so the two stay bit-identical.

Built on step 6b (vortex/core/strapdown.py): same self-calibration, same backward pass before the
anchor, same per-row strapdown rules, except that the accelerometer bias estimate is subtracted from
the specific force. With both witnesses off nothing is ever corrected, the bias estimate stays zero
and the output equals strapdown.estimate exactly.

Filter (forward only, from the anchor). Error state, 15 values:
  dp (0..2), dv (3..5) world frame; dth (6..8) world-frame attitude error, q_true = Exp(dth) q;
  dbg (9..11) gyro bias, dba (12..14) accelerometer bias, body frame.
Continuous model: dp' = dv; dv' = -[f_w]x dth - R dba; dth' = -R dbg; biases random walks; white
gyro and accel noise. The covariance is propagated once per tick (TICK_S, the 6b stillness bin) with
Phi = I + A T, using the mean world specific force over the tick and the mean of R at the tick's two
ends. Measurements are direct (one state each), applied as scalar updates at the end of a tick, then
injected into the nominal state and the error reset to zero.

Ticks are TICK_S time bins counted from the anchor's timestamp. A tick closes when an accepted valid
row (first row, or 0 < dt <= MAX_JUMP_S) arrives at or after the bin's end, before that row is
integrated. Accepted valid rows feed the bin's raw statistics (count, sums, sums of squares).

V1 stillness: the bin is still by the 6b test (strapdown.bin_is_still) and so is the previous bin,
and the two are steady (strapdown.bins_steady). Then v = 0 (ZUPT, ZUPT_SIGMA per axis) and gyro bias =
the bin's mean gyro (ZARU, sigma = the bin-mean standard error, at least ZARU_SIGMA_MIN).
V2 flight envelope, on every tick where V1 did not fire; two parts, each behind its own switch:
  speed (V2_ON): each world velocity axis is pulled toward 0, sigma V2_SIGMA_H (x, y), V2_SIGMA_V (z):
    an indoor flight or walk has zero-mean velocity of a typical size;
  volume (V2P_ON): position is pulled toward a running centre c (c += (p - c) T / V2P_TAU), sigma
    V2P_SIGMA_H, V2P_SIGMA_V: it stays in a room-sized volume. Assumes a bounded volume (true for
    EuRoC and the TUM-VI room sequences; wrong for long corridor or outdoor walks).
Envelope values are FIXED, chosen on clean MH_01/02 only (rule: lowest mean of APE/floor + RPE1s/floor
after the anchor, floor = a never-moving trajectory); MH_03..05 are held out. Learning them in the
healthy phase is still to do.

Step 6c, two switches; with both off the output equals step 7a exactly.
Noise meter (JAM_ON): on rows integrated by a normal step, the second difference of each raw channel
(x[k] - 2 x[k-1] + x[k-2]) has variance 6 sigma^2 for white noise of per-sample std sigma, and smooth
motion nearly cancels in it. Per tick: sigma^2 per sensor (mean over its 3 axes), turned into a noise
density (sigma^2 times the mean sample interval) and smoothed with time constant JAM_TAU. The filter's
white-noise densities become max(datasheet value, measured). In flight this measures rotor vibration
as well as added noise (MH clean flight: about 0.04 rad/s and 1 m/s^2 per sample).
Dropout covariance (GAP_ON): time a tick spends without integrated IMU data (invalid rows, or a step
longer than MAX_DT) is a gap; position coasts on velocity and attitude is held (unchanged rules). The
error that leaves is learned from the filter's own recent motion: over a horizon of GAP_H_TICKS ticks
(2 s) the squared change of the gravity direction in the body frame (tilt) and of each velocity axis,
smoothed with time constant GAP_TAU. A gap of length L adds (L / horizon)^2 times these to the tilt
and velocity variances (constant-acceleration model for position: + var L^2 / 4, cross term var L / 2),
so the witnesses can pull the state back after the gap. Yaw is not inflated (nothing observes it).

Step 8a, two switches; with both off the output equals step 6c exactly.
Dead sensor (DEAD_ON): a row whose gyro or accelerometer triple has repeated exactly for STUCK_ROWS rows
in a row (stuck), or whose accelerometer triple is exactly (0, 0, 0), is treated as an invalid row.
Forecaster (FC_ON): while coasting without IMU data, velocity decays toward 0 with time constant FC_TAU
(coast()); off = constant velocity. Applies to every gap, so to dropouts and to the blind window.

Step 6d (PRE_HOLD): the rows before the anchor keep the anchor's position (0, 0, 0); their attitude still
comes from the backward gyro integration. Backward dead reckoning without witnesses was worse than
standing still on clean MH_01/02 and could reach hundreds of metres when a dropout fell before the anchor.
"""

from __future__ import annotations

import math

from . import strapdown as sd

# Named parameters. Noise densities: EuRoC sensor.yaml (ADIS16448) with margins, see each line.
TICK_S = sd.BLOCK_S          # s, filter tick = stillness bin
GYRO_NOISE = 1.7e-3          # rad/s/sqrt(Hz): 10x sensor.yaml 1.6968e-4
ACC_NOISE = 2.0e-2           # m/s^2/sqrt(Hz): 10x sensor.yaml 2.0e-3 (rotor vibration)
GYRO_WALK = 1.9e-4           # rad/s^2/sqrt(Hz): 10x sensor.yaml 1.9393e-5
ACC_WALK = 3.0e-3            # m/s^3/sqrt(Hz): 1x sensor.yaml 3.0e-3
P0_VEL = 0.01                # m/s at the anchor (mid still run)
P0_TILT = 0.02               # rad, roll and pitch after calibration (accel bias / g)
P0_YAW = 0.0                 # yaw is defined as 0 at the anchor
P0_BG = 2e-3                 # rad/s after calibration (MH_01..05: within 1.5e-3 of ground truth)
P0_BA = 0.2                  # m/s^2, accelerometer bias before any witness
P0_TILT_FALLBACK = 0.1       # rad, 6a fallback (first second may be moving)
P0_BG_FALLBACK = 0.02        # rad/s, 6a fallback
ZUPT_SIGMA = 0.02            # m/s
ZARU_SIGMA_MIN = 5e-4        # rad/s
# V2 envelope, chosen on clean MH_01/02 (16 Nov; grid V2_SIGMA_H 0.5/1/2, V2P_SIGMA_H 2/5/10,
# V2P_TAU 10/30, ACC_WALK 3e-3/3e-2; the landscape is flat, 1.92 to 1.97 against 2.0 for standing still)
V2_SIGMA_H = 2.0             # m/s, horizontal speed envelope
V2_SIGMA_V = 0.3             # m/s, vertical (not tuned; MH ground-truth vertical speed rms 0.18..0.28)
V2P_SIGMA_H = 5.0            # m, volume envelope around the running centre
V2P_SIGMA_V = 2.0            # m (not tuned)
V2P_TAU = 10.0               # s, time constant of the running centre (EMA of own position)
V1_ON = True
V2_ON = True
V2P_ON = True
# step 6c (placeholders, not tuned)
JAM_TAU = 2.0                # s, smoothing of the measured noise density
GAP_H_TICKS = 8              # ticks (2 s, the slides' dropout length): horizon of the learned motion
GAP_TAU = 20.0               # s, smoothing of the learned motion statistics
JAM_ON = False               # rule v2 (16 Nov): fails with GAP_ON on; see Docs/TRACK3_PLAN.md step 6c
GAP_ON = True
# step 8a (decided by the pre-registered rule, Docs/TRACK3_PLAN.md step 8a)
STUCK_ROWS = 5               # rows: a sensor triple repeating exactly this often in a row is dead (clean MH_01..05: longest run 2)
DEAD_ON = True               # step 8a rule (16 Nov): passes on held-out MH_03..05; dead-sensor detection
FC_TAU = 0.5                 # s, velocity decay while coasting: lowest mean blind growth on MH_01/02 (Docs/BLIND.md step8-tune)
FC_ON = True                 # step 8a rule (16 Nov): passes; velocity decays toward 0 while coasting (off = constant velocity)
# step 6d (decided by the pre-registered rule, Docs/TRACK3_PLAN.md step 6d)
PRE_HOLD = False             # rows before the anchor keep the anchor position (attitude still from the backward pass)
N = 15


def rot_matrix(q):
    """Row-major body-to-world rotation matrix of q = (w, x, y, z)."""
    w, x, y, z = q
    return (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - w * z), 2.0 * (x * z + w * y),
            2.0 * (x * y + w * z), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - w * x),
            2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x * x + y * y))


def kf_init(still):
    """Initial covariance, flat row-major N x N."""
    tilt = P0_TILT if still else P0_TILT_FALLBACK
    bg = P0_BG if still else P0_BG_FALLBACK
    sig = (0.0, 0.0, 0.0, P0_VEL, P0_VEL, P0_VEL, tilt, tilt, P0_YAW, bg, bg, bg, P0_BA, P0_BA, P0_BA)
    P = [0.0] * (N * N)
    for i in range(N):
        P[i * N + i] = sig[i] * sig[i]
    return P


def kf_propagate(P, r, fx, fy, fz, T, acc_d2=ACC_NOISE * ACC_NOISE, gyro_d2=GYRO_NOISE * GYRO_NOISE):
    """P <- Phi P Phi^T + Q for a tick of T seconds. r: row-major R (body to world), f: mean world
    specific force; acc_d2, gyro_d2: white-noise densities squared. Phi = I + A; A's non-zero
    entries are listed as (row, col, value)."""
    A = [(0, 3, T), (1, 4, T), (2, 5, T),
         (3, 7, T * fz), (3, 8, -T * fy), (4, 6, -T * fz), (4, 8, T * fx), (5, 6, T * fy), (5, 7, -T * fx)]
    for i in range(3):
        for j in range(3):
            a = -T * r[3 * i + j]
            A.append((3 + i, 12 + j, a))
            A.append((6 + i, 9 + j, a))
    M = P[:]                                   # M = Phi P
    for i, j, a in A:
        oi, oj = i * N, j * N
        for c in range(N):
            M[oi + c] += a * P[oj + c]
    Pn = M[:]                                  # Pn = M Phi^T
    for i, j, a in A:
        for rr in range(0, N * N, N):
            Pn[rr + i] += a * M[rr + j]
    qv = acc_d2 * T
    qt = gyro_d2 * T
    qg = GYRO_WALK * GYRO_WALK * T
    qa = ACC_WALK * ACC_WALK * T
    for k in range(3):
        Pn[(3 + k) * (N + 1)] += qv
        Pn[(6 + k) * (N + 1)] += qt
        Pn[(9 + k) * (N + 1)] += qg
        Pn[(12 + k) * (N + 1)] += qa
    P[:] = Pn


def kf_update(P, dx, k, z, var):
    """Scalar measurement of error-state element k: z = dx[k] + noise (variance var)."""
    S = P[k * N + k] + var
    if not S > 0.0:
        return
    inn = z - dx[k]
    row = P[k * N:(k + 1) * N]
    for i in range(N):
        Ki = P[i * N + k] / S
        if Ki != 0.0:
            dx[i] += Ki * inn
            oi = i * N
            for j in range(N):
                P[oi + j] -= Ki * row[j]


def gap_inflate(P, L, tilt2, dv2):
    """Covariance added by a gap of L seconds without IMU data. tilt2: learned squared tilt change
    over the horizon; dv2: learned squared velocity change per world axis over the horizon."""
    s = L / (GAP_H_TICKS * TICK_S)
    s = s * s
    P[6 * N + 6] += 0.5 * tilt2 * s
    P[7 * N + 7] += 0.5 * tilt2 * s
    for k in range(3):
        a = dv2[k] * s
        P[(3 + k) * (N + 1)] += a
        P[k * (N + 1)] += a * L * L * 0.25
        P[k * N + 3 + k] += a * L * 0.5
        P[(3 + k) * N + k] += a * L * 0.5


def inject(q, p, v, bg, ba, dx):
    """Apply the error estimate to the nominal state; returns (q, p, v, bg, ba). A non-finite
    correction is discarded (never-NaN guarantee)."""
    chk = 0.0
    for e in dx:
        chk += e
    if chk - chk != 0.0:
        return q, p, v, bg, ba
    nq = sd.qmul_normalised(sd.exp_step(dx[6], dx[7], dx[8], 1.0), q)
    return (nq,[p[0] + dx[0], p[1] + dx[1], p[2] + dx[2]], [v[0] + dx[3], v[1] + dx[4], v[2] + dx[5]],
            (bg[0] + dx[9], bg[1] + dx[10], bg[2] + dx[11]), (ba[0] + dx[12], ba[1] + dx[13], ba[2] + dx[14]))


def coast(p, v, dt, tau):
    """Coast dt seconds without IMU data. tau None: constant velocity. Otherwise velocity decays toward 0
    with time constant tau (the mean of an Ornstein-Uhlenbeck velocity) and position integrates it."""
    if tau is None:
        return [p[0] + v[0] * dt, p[1] + v[1] * dt, p[2] + v[2] * dt], v
    e = math.exp(-dt / tau)
    s = tau * (1.0 - e)
    return [p[0] + v[0] * s, p[1] + v[1] * s, p[2] + v[2] * s], [v[0] * e, v[1] * e, v[2] * e]


def estimate(rows, v1=None, v2=None, v2p=None, log=None, jam=None, gap_on=None, dead=None, fc=None,
             pre_hold=None):
    """rows: list of (t_ns or None, six floats). Returns one (px, py, pz, qw, qx, qy, qz) per row.
    v1, v2, v2p, jam, gap_on, dead, fc, pre_hold: switches (default the module's *_ON). log: optional list, gets
    one dict per tick."""
    v1 = V1_ON if v1 is None else v1
    v2 = V2_ON if v2 is None else v2
    v2p = V2P_ON if v2p is None else v2p
    jam = JAM_ON if jam is None else jam
    gap_on = GAP_ON if gap_on is None else gap_on
    dead = DEAD_ON if dead is None else dead
    tau = (FC_TAU if (FC_ON if fc is None else fc) else None)
    c = [0.0, 0.0, 0.0]                 # running centre of the volume envelope
    cal = sd.calibrate(rows)
    init, anchor = cal.init, cal.anchor
    out = sd.backward(rows, anchor, init)
    if PRE_HOLD if pre_hold is None else pre_hold:
        out = [(0.0, 0.0, 0.0) + o[3:] for o in out]
    q = init.q
    bg = init.bg
    ba = (0.0, 0.0, 0.0)
    g = init.g
    p = [0.0, 0.0, 0.0]
    v = [0.0, 0.0, 0.0]
    P = kf_init(init.still)
    dx = [0.0] * N
    tick_ns = int(TICK_S * 1e9)
    t_last = None
    prev = None
    tick_end = None
    t_tick = None                       # timestamp of the state at the last tick close
    r0 = rot_matrix(q)                  # R at the start of the tick
    fs = [0.0, 0.0, 0.0]                # sum of world specific force over integrated steps
    fn = 0
    bn, bs, bss = 0, [0.0] * 6, [0.0] * 6
    pn, ps, pss, pstill = 0, None, None, False
    h1 = h2 = None                      # last two raw rows of an unbroken run (noise meter)
    nd, dg, da, fdt = 0, 0.0, 0.0, 0.0  # second differences this tick; integrated time this tick
    jg = ja = -1.0                      # smoothed measured densities^2 (< 0: none yet)
    gap = 0.0                           # seconds of this tick without integrated IMU data
    ring = []                           # (gravity direction in body, velocity) at the last ticks
    tilt2 = -1.0                        # learned squared changes over the horizon (< 0: none yet)
    dv2 = [0.0, 0.0, 0.0]
    sg = sa = 0                         # length of the current run of identical gyro / accel triples
    lg = la = None
    for t, vals in rows[anchor:]:
        if t is not None:
            ok = sd.is_valid(vals)
            if ok and dead:
                if vals[:3] == lg:
                    sg += 1
                else:
                    lg, sg = vals[:3], 1
                if vals[3:] == la:
                    sa += 1
                else:
                    la, sa = vals[3:], 1
                if sg >= STUCK_ROWS or sa >= STUCK_ROWS or not (vals[3] or vals[4] or vals[5]):
                    ok = False
            if ok:
                dt = None if t_last is None else (t - t_last) * 1e-9
                if dt is None or 0 < dt <= sd.MAX_JUMP_S:
                    if tick_end is None:
                        tick_end = t + tick_ns
                        t_tick = t
                    elif t >= tick_end:
                        # ---- close the tick: propagate, witnesses, inject ----
                        T = (t_last - t_tick) * 1e-9
                        r1 = rot_matrix(q)
                        if T > 0.0:
                            r = [0.5 * (r0[i] + r1[i]) for i in range(9)]
                            if gap_on and gap > 0.0 and tilt2 >= 0.0:
                                gap_inflate(P, gap, tilt2, dv2)
                            ad2 = ACC_NOISE * ACC_NOISE
                            gd2 = GYRO_NOISE * GYRO_NOISE
                            if jam:
                                if nd >= sd.BLOCK_MIN_ROWS and fn:
                                    ds = fdt / fn / (18.0 * nd)
                                    if jg < 0.0:
                                        jg, ja = dg * ds, da * ds
                                    else:
                                        b = T / JAM_TAU if T < JAM_TAU else 1.0
                                        jg += (dg * ds - jg) * b
                                        ja += (da * ds - ja) * b
                                if jg > gd2:
                                    gd2 = jg
                                if ja > ad2:
                                    ad2 = ja
                            if fn:
                                kf_propagate(P, r, fs[0] / fn, fs[1] / fn, fs[2] / fn, T, ad2, gd2)
                            else:
                                kf_propagate(P, r, 0.0, 0.0, g, T, ad2, gd2)
                        still = sd.bin_is_still(bn, bs, bss)
                        zupt = (v1 and still and pstill and sd.bins_steady(pn, ps, bn, bs))
                        if zupt:
                            for k in range(3):
                                kf_update(P, dx, 3 + k, -v[k], ZUPT_SIGMA * ZUPT_SIGMA)
                            for k in range(3):
                                m = bs[k] / bn
                                var = (bss[k] / bn - m * m) / bn
                                if var < ZARU_SIGMA_MIN * ZARU_SIGMA_MIN:
                                    var = ZARU_SIGMA_MIN * ZARU_SIGMA_MIN
                                kf_update(P, dx, 9 + k, m - bg[k], var)
                        elif v2:
                            kf_update(P, dx, 3, -v[0], V2_SIGMA_H * V2_SIGMA_H)
                            kf_update(P, dx, 4, -v[1], V2_SIGMA_H * V2_SIGMA_H)
                            kf_update(P, dx, 5, -v[2], V2_SIGMA_V * V2_SIGMA_V)
                        if v2p and not zupt and T > 0.0:
                            a = T / V2P_TAU if T < V2P_TAU else 1.0
                            for k in range(3):
                                c[k] += (p[k] - c[k]) * a
                            kf_update(P, dx, 0, c[0] - p[0], V2P_SIGMA_H * V2P_SIGMA_H)
                            kf_update(P, dx, 1, c[1] - p[1], V2P_SIGMA_H * V2P_SIGMA_H)
                            kf_update(P, dx, 2, c[2] - p[2], V2P_SIGMA_V * V2P_SIGMA_V)
                        if zupt or v2 or v2p:
                            q, p, v, bg, ba = inject(q, p, v, bg, ba, dx)
                            dx = [0.0] * N
                        r0 = rot_matrix(q)
                        if gap_on:
                            zb = (r0[6], r0[7], r0[8])
                            if len(ring) == GAP_H_TICKS:
                                oz, ov = ring.pop(0)
                                e = [zb[k] - oz[k] for k in range(3)]
                                e2 = e[0] * e[0] + e[1] * e[1] + e[2] * e[2]
                                d = [v[k] - ov[k] for k in range(3)]
                                if tilt2 < 0.0:
                                    tilt2 = e2
                                    dv2 = [d[k] * d[k] for k in range(3)]
                                else:
                                    b = TICK_S / GAP_TAU
                                    tilt2 += (e2 - tilt2) * b
                                    for k in range(3):
                                        dv2[k] += (d[k] * d[k] - dv2[k]) * b
                            ring.append((zb, (v[0], v[1], v[2])))
                        if log is not None:
                            log.append({"t": t_last, "zupt": zupt, "ba": ba, "bg": bg, "v": tuple(v),
                                        "jg": jg, "ja": ja, "gap": gap, "tilt2": tilt2, "dv2": tuple(dv2),
                                        "pv": P[3 * N + 3], "ptilt": P[6 * N + 6]})
                        tick_end += tick_ns * ((t - tick_end) // tick_ns + 1)
                        t_tick = t_last
                        fs = [0.0, 0.0, 0.0]
                        fn = 0
                        nd, dg, da, fdt, gap = 0, 0.0, 0.0, 0.0, 0.0
                        pn, ps, pss, pstill = bn, bs, bss, still
                        bn, bs, bss = 0, [0.0] * 6, [0.0] * 6
                    bn += 1
                    for i in range(6):
                        bs[i] += vals[i]
                        bss[i] += vals[i] * vals[i]
                    vc = (vals[0], vals[1], vals[2], vals[3] - ba[0], vals[4] - ba[1], vals[5] - ba[2])
                    if dt is None:
                        prev = sd._sample(q, vc, bg[0], bg[1], bg[2])
                        h1 = vals
                    elif dt <= sd.MAX_DT and prev is not None:
                        q, p, v, prev = sd._step(q, p, v, prev, vc, bg[0], bg[1], bg[2], g, dt)
                        if prev is not None:
                            fs[0] += prev[3]
                            fs[1] += prev[4]
                            fs[2] += prev[5]
                            fn += 1
                            fdt += dt
                        if h2 is not None:
                            d0 = vals[0] - 2.0 * h1[0] + h2[0]
                            d1 = vals[1] - 2.0 * h1[1] + h2[1]
                            d2 = vals[2] - 2.0 * h1[2] + h2[2]
                            dg += d0 * d0 + d1 * d1 + d2 * d2
                            d0 = vals[3] - 2.0 * h1[3] + h2[3]
                            d1 = vals[4] - 2.0 * h1[4] + h2[4]
                            d2 = vals[5] - 2.0 * h1[5] + h2[5]
                            da += d0 * d0 + d1 * d1 + d2 * d2
                            nd += 1
                        h2 = h1
                        h1 = vals
                    else:
                        p, v = coast(p, v, dt, tau)
                        prev = sd._sample(q, vc, bg[0], bg[1], bg[2])
                        gap += dt
                        h1, h2 = vals, None
                    t_last = t
            elif t_last is not None:
                dt = (t - t_last) * 1e-9
                if 0 < dt <= sd.MAX_JUMP_S:
                    p, v = coast(p, v, dt, tau)
                    t_last = t
                    prev = None
                    gap += dt
                    h1 = h2 = None
        out.append((p[0], p[1], p[2], q[0], q[1], q[2], q[3]))
    return out


def estimate_file(path):
    from ..data import euroc
    return estimate(sd.rows_from_raw(euroc.read_imu_csv(path)))

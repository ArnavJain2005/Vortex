"""Reference estimator, steps 7a + 6c + 8a: error-state Kalman filter with the core velocity witnesses
V1 (stillness) and V2 (flight envelope), a noise meter and dropout covariance. Plain Python floats, no numpy; pathfinder.py copies the filter
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

Step 7b (ZUPT_DEN_ON): V1 also fires when ZUPT_DEN_BINS ticks in a row pass the calibration's denoised
still test and are pairwise steady under the denoised tolerance (strapdown.bin_is_still_denoised,
bins_steady_denoised), with the tick's per-channel second differences (rows integrated by a normal step).
The strict V1 condition is unchanged.

Step 6d (PRE_HOLD): the rows before the anchor keep the anchor's position (0, 0, 0); their attitude still
comes from the backward gyro integration. Backward dead reckoning without witnesses was worse than
standing still on clean MH_01/02 and could reach hundreds of metres when a dropout fell before the anchor.

Step E / Step 6 (SMOOTH_ON, ON since 18 Nov 2026, also in pathfinder.py): fixed-interval Rauch-Tung-Striebel smoother at the filter tick.
At each tick close the gain C = P+ Phi^T (P-)^-1 (previous posterior, this prior) and the correction
injected at the previous tick are stored as a block (t, C, b, d) in single precision; a full store
(SMOOTH_MAX_BLOCKS) merges adjacent blocks pairwise by composing their affine maps e'_start = A e'_end + b,
so memory never grows. After the forward pass, the backward recursion gives the smoothed error at every
stored tick, and each row from the anchor on is corrected linearly in time between its two bracketing
ticks. Rows before the anchor and after the last tick (the blind window) are unchanged. Works on
SYNTHETIC data (second rest carried back: 12.2 -> 0.8 m). On the clean tuning runs MH_01/02 it raised
APE (Docs/TRACK3_PLAN.md step E), but on the official degraded copies it passed the Step 6 rule committed
before the held-out run (held-out APE -7.8 %, gap RMSE -10.7 %, clean APE -2.7 %), so it ships on.
"""

from __future__ import annotations

import math
from array import array

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
# Step 4 (reference first; rule in Docs/TRACK3_PLAN.md, Step 4): envelope learned per file (LEARN_ON). Pass 1
# runs with the fixed values above and records per tick, after the updates, v^2 + P_vv and (p - c)^2 + P_pp
# (c = the running centre), horizontal (mean of x, y) and vertical. Over the ticks in the first LEARN_FRAC
# of the file's time span the learned sigma is sqrt(mean): one EM step for the prior's variance, using the
# filter's own posterior. Times LEARN_K (the prior is applied every 0.25 s tick as if the ticks were
# independent; speed and position are correlated over seconds, so the per-tick sigma must be wider than the
# spread), then clamped to [LEARN_MIN, LEARN_MAX]; LEARN_ITERS such steps, then the final pass.
LEARN_ON = False
LEARN_FRAC = 0.3
LEARN_ITERS = 2
LEARN_K = 1.0
LEARN_MIN = (0.1, 0.05, 0.3, 0.1)   # speed h, v (m/s); volume h, v (m): wide, not tuned
LEARN_MAX = (4.0, 1.0, 10.0, 4.0)


def learn_env(acc, t0, t1):
    """acc: flat list, 5 per tick (t_ns, vh2, vv2, ph2, pv2). Returns (sigma speed h, v, volume h, v)."""
    lim = t0 + LEARN_FRAC * (t1 - t0)
    n = 0
    s = [0.0, 0.0, 0.0, 0.0]
    for i in range(0, len(acc), 5):
        if acc[i] <= lim:
            n += 1
            s[0] += acc[i + 1]
            s[1] += acc[i + 2]
            s[2] += acc[i + 3]
            s[3] += acc[i + 4]
    if n == 0:
        return (V2_SIGMA_H, V2_SIGMA_V, V2P_SIGMA_H, V2P_SIGMA_V)
    out = []
    for k in range(4):
        x = LEARN_K * math.sqrt(s[k] / n)
        out.append(LEARN_MIN[k] if x < LEARN_MIN[k] else LEARN_MAX[k] if x > LEARN_MAX[k] else x)
    return tuple(out)
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
# step 7b (decided by the pre-registered rule, Docs/TRACK3_PLAN.md step 7b)
ZUPT_DEN_BINS = 4            # ticks (1 s = MIN_STILL_S): MH_01/02 study, false denoised-still runs in flight were 2 ticks
ZUPT_DEN_ON = False          # V1 also fires after ZUPT_DEN_BINS denoised-still, steady ticks in a row
PRE_HOLD = True              # rule passed 16 Nov; rows before the anchor keep the anchor position (attitude still from the backward pass)
# step E (reference only until its pre-registered rule passes, Docs/TRACK3_PLAN.md step E)
SMOOTH_ON = True             # Step 6: ON (pre-registered rule passed on held-out copies, 18 Nov 2026); RTS smoother at the filter tick; non-causal (offline)
SMOOTH_MAX_BLOCKS = 1024     # blocks stored (fixed cap): 256 s at one tick per block; longer files merge
                             # adjacent blocks pairwise. Single precision: 4 x (225 + 15 + 15) bytes + 8 per block
# Step F (rule in Docs/TRACK3_PLAN.md, Step F; judged 17 Nov 2026 on held-out seeds 4-6): REFRESH, P0V and
# strapdown.BGCAP_ON passed and ship on; RESET failed (reading a mean APE +1.8 %) and ships off.
RESET_ON = False            # OFF (failed the rule). After each injection: covariance reset P <- G P G^T (kf_reset)
REFRESH_ON = True            # after each injection: the cached previous sample re-expressed with the corrected
                             # attitude and biases (refresh_prev)
P0V_ON = True                 # no still run (fallback init): initial velocity sigma = the V2 envelope, not P0_VEL
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
    if P0V_ON and not still:      # Step F: nothing says the sensor was at rest; the envelope is all we know
        sig = (0.0, 0.0, 0.0, V2_SIGMA_H, V2_SIGMA_H, V2_SIGMA_V) + sig[6:]
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


def kf_reset(P, ex, ey, ez):
    """Step F: covariance reset after injecting the attitude error (ex, ey, ez). With the global error
    q_true = Exp(dth) q and q+ = Exp(dth_hat) q, the new error is dth+ = Log(Exp(dth) Exp(-dth_hat)),
    whose Jacobian at dth = dth_hat is G = I + [dth_hat / 2]x to first order (Sola 2017, "Quaternion
    kinematics for the error-state Kalman filter", ESKF reset, global angular error). P <- G P G^T; G is
    the identity outside the attitude block, so only rows and columns 6..8 change."""
    hx, hy, hz = 0.5 * ex, 0.5 * ey, 0.5 * ez
    o6, o7, o8 = 6 * N, 7 * N, 8 * N
    for c in range(N):                         # rows: G P
        a, b, d = P[o6 + c], P[o7 + c], P[o8 + c]
        P[o6 + c] = a - hz * b + hy * d
        P[o7 + c] = b + hz * a - hx * d
        P[o8 + c] = d - hy * a + hx * b
    for rr in range(0, N * N, N):              # columns: (G P) G^T
        a, b, d = P[rr + 6], P[rr + 7], P[rr + 8]
        P[rr + 6] = a - hz * b + hy * d
        P[rr + 7] = b + hz * a - hx * d
        P[rr + 8] = d - hy * a + hx * b


def refresh_prev(prev, qo, qn, dx):
    """Step F: the cached previous sample (bias-corrected gyro, world specific force; see strapdown._sample)
    re-expressed after an injection from attitude qo to qn and biases + dx[9..14], so the next trapezoid
    step does not mix the old and the corrected state. Body force = R(qo)^T f_w, minus the accel bias
    change, rotated by R(qn)."""
    bx, by, bz = sd.rotate((qo[0], -qo[1], -qo[2], -qo[3]), prev[3], prev[4], prev[5])
    return (prev[0] - dx[9], prev[1] - dx[10], prev[2] - dx[11]) + sd.rotate(qn, bx - dx[12], by - dx[13], bz - dx[14])


def coast(p, v, dt, tau):
    """Coast dt seconds without IMU data. tau None: constant velocity. Otherwise velocity decays toward 0
    with time constant tau (the mean of an Ornstein-Uhlenbeck velocity) and position integrates it."""
    if tau is None:
        return [p[0] + v[0] * dt, p[1] + v[1] * dt, p[2] + v[2] * dt], v
    e = math.exp(-dt / tau)
    s = tau * (1.0 - e)
    return [p[0] + v[0] * s, p[1] + v[1] * s, p[2] + v[2] * s], [v[0] * e, v[1] * e, v[2] * e]


def _pos_cov(P):
    """Sums over the 3 axes of the position variance, position-velocity covariance and velocity variance."""
    return (P[0] + P[N + 1] + P[2 * N + 2], P[3] + P[N + 4] + P[2 * N + 5],
            P[3 * N + 3] + P[4 * N + 4] + P[5 * N + 5])


def row_sigma(cov, d, gap, tilt2, dv2):
    """Step 8b (W6): 3D position sigma of one row. The last tick's position covariance, carried d seconds
    on its velocity covariance (pp + 2 pv d + vv d^2), plus, while the IMU is missing for `gap` seconds
    since that tick, the dropout model's velocity change (gap_inflate: sum dv2 (gap / horizon)^2 gap^2 / 4).
    An error bar for reporting only: the estimator never reads it."""
    pp, pv, vv = cov
    v = pp + 2.0 * pv * d + vv * d * d
    if gap > 0.0 and tilt2 >= 0.0:
        h = GAP_H_TICKS * TICK_S
        v += (dv2[0] + dv2[1] + dv2[2]) * (gap / h) ** 2 * gap * gap * 0.25
    return math.sqrt(v) if v > 0.0 else 0.0


def phi_entries(r, fx, fy, fz, T):
    """The non-zero entries (row, col, value) of A in Phi = I + A, built exactly as in kf_propagate."""
    A = [(0, 3, T), (1, 4, T), (2, 5, T),
         (3, 7, T * fz), (3, 8, -T * fy), (4, 6, -T * fz), (4, 8, T * fx), (5, 6, T * fy), (5, 7, -T * fx)]
    for i in range(3):
        for j in range(3):
            a = -T * r[3 * i + j]
            A.append((3 + i, 12 + j, a))
            A.append((6 + i, 9 + j, a))
    return A


def smooth_gain(Pp, A, Pm):
    """Step E: RTS gain C = Pp Phi^T Pm^-1 (row-major N x N). Pp: posterior covariance at the previous
    tick (before any gap inflation); A: Phi's entries (empty: Phi = I); Pm: prior covariance at this tick
    (after gap inflation and propagation). Solved through the Cholesky factor of the symmetrised Pm.
    Returns None when Pm is not positive definite (the caller then stores C = 0: no smoothing across)."""
    M = Pp[:]                                  # M = Phi Pp; C^T = Pm^-1 M since Pp is symmetric
    for i, j, a in A:
        oi, oj = i * N, j * N
        for c in range(N):
            M[oi + c] += a * Pp[oj + c]
    L = [0.0] * (N * N)
    for i in range(N):
        for j in range(i + 1):
            s = 0.5 * (Pm[i * N + j] + Pm[j * N + i])
            for k in range(j):
                s -= L[i * N + k] * L[j * N + k]
            if i == j:
                if not s > 0.0:
                    return None
                L[i * N + i] = math.sqrt(s)
            else:
                L[i * N + j] = s / L[j * N + j]
    C = [0.0] * (N * N)
    y = [0.0] * N
    for col in range(N):
        for i in range(N):
            s = M[i * N + col]
            for k in range(i):
                s -= L[i * N + k] * y[k]
            y[i] = s / L[i * N + i]
        for i in range(N - 1, -1, -1):
            s = y[i]
            for k in range(i + 1, N):
                s -= L[k * N + i] * y[k]
            y[i] = s / L[i * N + i]
        for i in range(N):
            C[col * N + i] = y[i]
    return C


def _f32(xs):
    """Round to single precision (the smoother's storage)."""
    return list(array("f", xs))


def smooth_merge(b1, b2):
    """Compose two adjacent blocks (t, A, b, d): e'_start = A e'_end + b, with e' the smoothed error
    relative to the forward prior at a tick, d the forward correction injected at the block's first tick."""
    t1, A1, c1, d1 = b1
    _, A2, c2, _ = b2
    A = [0.0] * (N * N)
    c = c1[:]
    for i in range(N):
        oi = i * N
        for k in range(N):
            a = A1[oi + k]
            if a != 0.0:
                ok = k * N
                for j in range(N):
                    A[oi + j] += a * A2[ok + j]
                c[i] += a * c2[k]
    return (t1, _f32(A), _f32(c), d1)


def smooth_push(blocks, blk, cap):
    """Append a block; when the store is full, merge adjacent pairs (memory never grows past cap)."""
    if len(blocks) == cap:
        merged = [smooth_merge(blocks[i], blocks[i + 1]) for i in range(0, cap - 1, 2)]
        if cap % 2:
            merged.append(blocks[-1])
        blocks[:] = merged
    blocks.append(blk)


def smooth_apply(out, rows, anchor, blocks, t_end, d_end):
    """Backward RTS recursion over the stored blocks, then the correction of every row from the anchor on:
    linear in time between the smoothed error just after the bracketing earlier tick (relative to the
    forward posterior) and just before the later tick (relative to the forward prior). Rows after the last
    tick (the blind window) are unchanged: there the smoothed state equals the filtered one."""
    if not blocks:
        return out
    seg = []
    ep = list(d_end)                            # e'_N = d_N: the final smoothed state is the filtered one
    t_next = t_end
    for t0, A, b, d in reversed(blocks):
        es = [b[i] + sum(A[i * N + k] * ep[k] for k in range(N)) for i in range(N)]
        seg.append((t0, [es[i] - d[i] for i in range(N)], t_next, ep))
        ep, t_next = es, t0
    seg.reverse()
    j = 0
    tr = None
    for idx in range(anchor, len(rows)):
        t = rows[idx][0]
        if t is not None:
            tr = t
        if tr is None or tr > t_end:
            continue
        while j < len(seg) - 1 and tr > seg[j][2]:
            j += 1
        t0, e0, t1, e1 = seg[j]
        w = 0.0 if t1 <= t0 or tr <= t0 else (tr - t0) / (t1 - t0)
        e = [e0[i] + (e1[i] - e0[i]) * w for i in range(N)]
        o = out[idx]
        q = sd.qmul_normalised(sd.exp_step(e[6], e[7], e[8], 1.0), o[3:7])
        out[idx] = (o[0] + e[0], o[1] + e[1], o[2] + e[2]) + tuple(q)
    return out


def estimate(rows, v1=None, v2=None, v2p=None, log=None, jam=None, gap_on=None, dead=None, fc=None,
             pre_hold=None, zden=None, sig=None, smooth=None, env=None, collect=None):
    """rows: list of (t_ns or None, six floats). Returns one (px, py, pz, qw, qx, qy, qz) per row.
    v1, v2, v2p, jam, gap_on, dead, fc, pre_hold, zden: switches (default the module's *_ON). log: optional list, gets
    one dict per tick. sig: optional list, gets one per-row position sigma (m, 3D) per row (step 8b,
    W6; NaN before the anchor), see row_sigma()."""
    v1 = V1_ON if v1 is None else v1
    v2 = V2_ON if v2 is None else v2
    v2p = V2P_ON if v2p is None else v2p
    jam = JAM_ON if jam is None else jam
    gap_on = GAP_ON if gap_on is None else gap_on
    dead = DEAD_ON if dead is None else dead
    zden = ZUPT_DEN_ON if zden is None else zden
    tau = (FC_TAU if (FC_ON if fc is None else fc) else None)
    smooth = SMOOTH_ON if smooth is None else smooth
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
    cov = _pos_cov(P)                   # (pp, pv, vv) after the last tick (W6)
    blocks = []                         # step E: (t, C, b, d) per stored block
    sPp = P[:]                          # posterior covariance at the last tick
    sd_prev = _f32([0.0] * N)           # correction injected at the last tick
    st_prev = None                      # time of the last tick
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
    wd = [0.0] * 6                      # ... per channel (step 7b)
    zr = 0                              # denoised-still, steady ticks in a row (step 7b)
    pwv = None
    jg = ja = -1.0                      # smoothed measured densities^2 (< 0: none yet)
    gap = 0.0                           # seconds of this tick without integrated IMU data
    ring = []                           # (gravity direction in body, velocity) at the last ticks
    tilt2 = -1.0                        # learned squared changes over the horizon (< 0: none yet)
    dv2 = [0.0, 0.0, 0.0]
    sg = sa = 0                         # length of the current run of identical gyro / accel triples
    lg = la = None
    interp = INTERP_ON
    max_dt = INTERP_MAX_S if interp else sd.MAX_DT
    e = env if env is not None else (V2_SIGMA_H, V2_SIGMA_V, V2P_SIGMA_H, V2P_SIGMA_V)
    s2vh, s2vv, s2ph, s2pv = e[0] * e[0], e[1] * e[1], e[2] * e[2], e[3] * e[3]
    reset, refresh = RESET_ON, REFRESH_ON
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
                        st_prev = t
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
                                if smooth:
                                    sA = phi_entries(r, fs[0] / fn, fs[1] / fn, fs[2] / fn, T)
                            else:
                                kf_propagate(P, r, 0.0, 0.0, g, T, ad2, gd2)
                                if smooth:
                                    sA = phi_entries(r, 0.0, 0.0, g, T)
                        elif smooth:
                            sA = []
                        if smooth:
                            sC = smooth_gain(sPp, sA, P)
                        still = sd.bin_is_still(bn, bs, bss)
                        if zden:
                            dst = sd.bin_is_still_denoised(bn, bs, bss, nd, wd)
                            wv = sd.white_var(nd, wd)
                            if dst and zr > 0 and sd.bins_steady_denoised(pn, ps, pwv, bn, bs, wv):
                                zr += 1
                            elif dst:
                                zr = 1
                            else:
                                zr = 0
                            pwv = wv
                        zupt = v1 and ((still and pstill and sd.bins_steady(pn, ps, bn, bs)) or zr >= ZUPT_DEN_BINS)
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
                            kf_update(P, dx, 3, -v[0], s2vh)
                            kf_update(P, dx, 4, -v[1], s2vh)
                            kf_update(P, dx, 5, -v[2], s2vv)
                        if v2p and not zupt and T > 0.0:
                            a = T / V2P_TAU if T < V2P_TAU else 1.0
                            for k in range(3):
                                c[k] += (p[k] - c[k]) * a
                            kf_update(P, dx, 0, c[0] - p[0], s2ph)
                            kf_update(P, dx, 1, c[1] - p[1], s2ph)
                            kf_update(P, dx, 2, c[2] - p[2], s2pv)
                        sdx = None
                        if zupt or v2 or v2p:
                            sdx = dx
                            qo = q
                            q, p, v, bg, ba = inject(q, p, v, bg, ba, dx)
                            if reset or refresh:
                                chk = 0.0
                                for e in dx:
                                    chk += e
                                if chk - chk == 0.0:        # inject applied it (a non-finite dx is discarded)
                                    if reset:
                                        kf_reset(P, dx[6], dx[7], dx[8])
                                    if refresh and prev is not None:
                                        prev = refresh_prev(prev, qo, q, dx)
                            dx = [0.0] * N
                        if collect is not None:
                            d0 = p[0] - c[0]
                            d1 = p[1] - c[1]
                            d2 = p[2] - c[2]
                            collect.extend((float(t_last), 0.5 * (v[0] * v[0] + P[48] + v[1] * v[1] + P[64]),
                                            v[2] * v[2] + P[80], 0.5 * (d0 * d0 + P[0] + d1 * d1 + P[16]),
                                            d2 * d2 + P[32]))
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
                        cov = _pos_cov(P)
                        if smooth:
                            chk = 0.0
                            if sdx is not None:
                                for e in sdx:
                                    chk += e
                            sd_new = _f32(sdx if sdx is not None and chk - chk == 0.0 else [0.0] * N)
                            smooth_push(blocks, (st_prev, _f32(sC if sC is not None else [0.0] * (N * N)),
                                                 sd_prev, sd_prev), SMOOTH_MAX_BLOCKS)
                            sd_prev, st_prev, sPp = sd_new, t_last, P[:]
                        if log is not None:
                            log.append({"t": t_last, "zupt": zupt, "ba": ba, "bg": bg, "v": tuple(v),
                                        "jg": jg, "ja": ja, "gap": gap, "tilt2": tilt2, "dv2": tuple(dv2),
                                        "pv": P[3 * N + 3], "ptilt": P[6 * N + 6], "zr": zr})
                        tick_end += tick_ns * ((t - tick_end) // tick_ns + 1)
                        t_tick = t_last
                        fs = [0.0, 0.0, 0.0]
                        fn = 0
                        nd, dg, da, fdt, gap = 0, 0.0, 0.0, 0.0, 0.0
                        wd = [0.0] * 6
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
                    elif dt <= max_dt and prev is not None:
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
                            if zden:
                                wd[0] += d0 * d0
                                wd[1] += d1 * d1
                                wd[2] += d2 * d2
                            d0 = vals[3] - 2.0 * h1[3] + h2[3]
                            d1 = vals[4] - 2.0 * h1[4] + h2[4]
                            d2 = vals[5] - 2.0 * h1[5] + h2[5]
                            da += d0 * d0 + d1 * d1 + d2 * d2
                            if zden:
                                wd[3] += d0 * d0
                                wd[4] += d1 * d1
                                wd[5] += d2 * d2
                            nd += 1
                        h2 = h1
                        h1 = vals
                    else:
                        p, v = coast(p, v, dt, tau)
                        prev = sd._sample(q, vc, bg[0], bg[1], bg[2])
                        gap += dt
                        h1, h2 = vals, None
                    t_last = t
            elif t_last is not None and not (interp and type(vals) is MissingRow):
                dt = (t - t_last) * 1e-9
                if 0 < dt <= sd.MAX_JUMP_S:
                    p, v = coast(p, v, dt, tau)
                    t_last = t
                    prev = None
                    gap += dt
                    h1 = h2 = None
        if sig is not None:
            tr = t if t is not None else t_last
            d = 0.0 if t_tick is None or tr is None else (tr - t_tick) * 1e-9
            sig.append(row_sigma(cov, d, gap, tilt2, dv2))
        out.append((p[0], p[1], p[2], q[0], q[1], q[2], q[3]))
    if sig is not None:
        sig[0:0] = [float("nan")] * anchor
    if smooth:
        smooth_apply(out, rows, anchor, blocks, st_prev, sd_prev)
    return out


FRONT_ON = True              # Step 2 (17 Nov): input front end (vortex/core/frontend.py); no-op on canonical files
# Step 3 (reference first; decision rules in Docs/TRACK3_PLAN.md, Step 3). STUCK6_ON / SPIKE_ON live in
# faults.py. INTERP_ON: rows the fault pass marked missing are skipped (no coasting; the next good row
# integrates across with the real timestamp step, i.e. the trapezoid between the good neighbours), and a
# step up to INTERP_MAX_S (missing rows and bursts: the script's bursts are 5-50 rows, <= 0.25 s at
# 200 Hz) is integrated instead of coasted. Longer steps coast as before.
INTERP_ON = False
INTERP_MAX_S = 0.3


class MissingRow(tuple):
    """Six NaNs for a row the fault pass marked missing (invalid everywhere; skipped with INTERP_ON)."""


def prepare_lines(path):
    """The file's lines after the input front end (FRONT_ON) and the fault pass (faults.STUCK6_ON /
    SPIKE_ON), or None when neither changes anything (the file is read as it is)."""
    from . import faults, frontend
    lines = None
    if FRONT_ON:
        lay = frontend.detect(path)
        if not lay["canonical"]:
            lines = frontend.canonical_lines(path, lay)
    if faults.STUCK6_ON or faults.SPIKE_ON:
        if lines is None:
            lines = open(path, "rb")
        lines = faults.filter_lines(lines)
    return lines


def estimate_file(path):
    """The estimator on an IMU csv, after prepare_lines(); rows marked missing become MissingRow. With
    shrink.SHRINK_ON the positions are then scaled about their centroid (Step L1)."""
    import os
    import tempfile
    from ..data import euroc
    from . import shrink
    lines = prepare_lines(path)
    if lines is None:
        rows = sd.rows_from_raw(euroc.read_imu_csv(path))
        return shrink.shrink(rows, estimate_learned(rows))
    fd, tmp = tempfile.mkstemp(suffix=".csv")
    miss = []
    try:
        with os.fdopen(fd, "wb") as f:
            for line in lines:
                s = line.strip()
                if s and s[0] != 35:
                    miss.append(s.endswith(b",m"))
                f.write(line)
        rows = sd.rows_from_raw(euroc.read_imu_csv(tmp))
    finally:
        if hasattr(lines, "close"):
            lines.close()
        os.remove(tmp)
    rows = [(t, MissingRow(v)) if m else (t, v) for (t, v), m in zip(rows, miss)]
    return shrink.shrink(rows, estimate_learned(rows))


def estimate_learned(rows):
    """estimate(), with the envelope learned per file first when LEARN_ON (LEARN_ITERS passes)."""
    if not LEARN_ON:
        return estimate(rows)
    ts = [t for t, _ in rows if t is not None]
    env = None
    for _ in range(LEARN_ITERS):
        acc = []
        estimate(rows, env=env, collect=acc)
        env = learn_env(acc, ts[0], ts[-1]) if ts else None
    LAST_ENV[0] = env
    return estimate(rows, env=env)


LAST_ENV = [None]

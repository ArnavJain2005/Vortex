# Method: shipped IMU-only estimator

This describes `main.py` and the shipped `pathfinder.py` at `d1fc504` (18 November
2026). The input is a degraded IMU CSV; the output has one timestamped 6-DoF pose
per nonblank, noncomment input row. Hidden ground truth and waypoints are never
inputs. The official script's two possible column readings are evaluated
separately because the organisers' input order is unresolved (`Docs/TRACK3_PLAN.md`,
“Open questions”, Q9). This is a description of the implementation, not a claim
that its trajectory beats a stationary estimate.

## Input, state and initialisation

`pathfinder.py` `run`, `_fe_detect`, `_fe_canonical_lines`: the front end samples up
to `FE_DETECT_ROWS` rows to infer gyro/accelerometer column order, timestamp units
and whether acceleration is in g. Header order breaks ambiguous data ties; an
ambiguous file without a useful header defaults to gyro first. Noncanonical
input is rewritten to a temporary canonical file beside the requested output;
the temporary file is removed after processing. The subsequent pass uses integer
nanosecond timestamps and writes seconds with nine exact fractional digits.
Sensor values are finite checked in the estimator. A bad timestamp repeats the
previous output timestamp. The order detector is a heuristic, not a per-row
label or a correction for faults already applied to the wrong columns.

`pathfinder.py` `_calibrate`, `_best_run`, `_still_denoised`, `_initialise`:
the first 60 seconds are grouped into 0.25-second bins. A bin needs at least
five valid samples, small gyro and acceleration variation, nonzero variation
to exclude a stuck sensor, acceleration magnitude in [8.8, 10.8] m/s², and
mean gyro magnitude at most 0.15 rad/s. Adjacent bins must also agree in their
means. The longest run of at least one second is selected, with half a second
trimmed from each end if sufficient data remain. A second pass subtracts an
estimate of white-noise variance from the stillness test only if the strict
scan found no run. Mean gyro gives the initial gyro bias; mean specific force
gives the gravity magnitude and the tilt quaternion. Yaw is unobservable from
gravity and starts at zero. The anchor is the middle of the detected run.
If no run qualifies, `_initialise` uses up to the first second: it sets gyro
bias from that window only if the fallback stillness check passes, otherwise
the bias is zero and gravity is 9.81 m/s². Fallback tilt comes from mean
acceleration when usable. The larger fallback velocity covariance is set by
`_kf_init` when there is no still anchor.

The nominal state is position **p**, velocity **v**, unit body-to-world
quaternion **q**, gyro bias **b_g**, and accelerometer bias **b_a**. `pathfinder.py`
`_kf_init`, `_kf_propagate`, `_kf_update`, `_inject` carry the 15-component error
state `δx = [δp, δv, δθ, δb_g, δb_a]` and its 15×15 covariance **P**. A covariance
propagation runs at roughly 0.25-second ticks, with `P ← F P Fᵀ + Q` in
`_kf_propagate`. Scalar Kalman updates and the left-multiplied attitude
correction `q ← Exp(δθ) ⊗ q` occur in `_kf_update` and `_inject`.
`_refresh_prev` re-expresses the cached previous sample after a correction.

`pathfinder.py` `_run` integrates consecutive usable samples using the mean
bias-corrected angular rate, normalises the quaternion, rotates specific force
into the world frame and subtracts gravity. With the trapezoidal world-frame
acceleration **a** over time step Δt, it uses
`p ← p + v Δt + a Δt²/2` and `v ← v + a Δt` (`_run`, “strapdown step”).
`_pre_segment` integrates backwards from a later still anchor to obtain
pre-anchor attitude. With `PRE_HOLD`, their output positions remain at the
anchor rather than claiming measured displacement before calibration.

## Velocity and position witnesses

Each residual below is a *pseudo-measurement* formed from IMU-derived state;
none is an external observation of position. `pathfinder.py` `_bin_still`,
`_bins_steady`, `_run` (tick close): V1 needs two consecutive still and mutually
steady bins. Its zero-velocity observation is `z_v = 0`, residual `−v`, with
per-axis standard deviation `ZUPT_SIGMA = 0.02 m/s`. It also observes that the
mean gyro in the bin is bias when still: residual `mean(ω_m) − b_g`, with
variance at least `ZARU_SIGMA_MIN² = (0.0005 rad/s)²` and otherwise the
sample-mean variance. V1 is skipped when stillness is not established.

`pathfinder.py` `_run` (tick close), `_kf_update`: V2 acts when V1 has not
issued a zero-velocity update. Its speed prior is `z_v = 0`, residual `−v`,
with horizontal standard deviation `V2_SIGMA_H = 2 m/s` and vertical
`V2_SIGMA_V = 0.3 m/s`. These values restrain drift; the residual cannot
distinguish genuine motion from a velocity error.

`pathfinder.py` `_run` (tick close), `_kf_update`: V2P maintains a running
centre `c ← c + (p − c) min(Δt / V2P_TAU, 1)`, with `V2P_TAU = 10 s`.
When V1 has not fired, its position observation is `z_p = c`, residual
`c − p`, with horizontal standard deviation `V2P_SIGMA_H = 5 m` and
vertical `V2P_SIGMA_V = 2 m`. The centre comes from the estimate itself;
it is a volume prior rather than an independent position measurement.

## Missing and dead IMU samples

`pathfinder.py` `_run` detects a nonfinite/extreme reading, an all-zero
accelerometer, or five consecutive identical gyro *or* acceleration triples.
It treats these samples as missing, while retaining their timestamp and
writing one output pose. Physical missing-row bursts appear as timestamp
jumps. If a time step exceeds `MAX_DT = 0.1 s`, the estimator does not
integrate a trapezoid across it. `_gap_inflate` adds covariance from recent
tilt and velocity changes when a gap ends; it does not supply a motion
measurement. Nonpositive or larger-than-30-second jumps are not integrated.

For a positive gap or invalid sample of duration Δt at most 30 s, the blind
forecaster in `pathfinder.py` `_run` uses a 0.5-second decay constant:
`v_new = v_old exp(−Δt/0.5)` and
`p_new = p_old + 0.5 [1 − exp(−Δt/0.5)] v_old`.
During the final invalid-value blind window, timestamps are still present;
no extra rows are appended. The forecast tends to stop rather than extend
the last velocity indefinitely. This is a prior, not recovered motion.

## Offline correction of earlier poses

`pathfinder.py` `_run_smoothed`, `_run`, `_smooth_gain`, `_smooth_push`,
`_smooth_merge`, `_smooth_segments`: `SMOOTH_ON` is now true. A first forward
pass stores, at filter ticks, the fixed-interval Rauch–Tung–Striebel gain
`C_k = P_k⁺ Φ_kᵀ (P_{k+1}⁻)⁻¹` and affine error corrections. Backward recursion
applies future filter corrections to earlier tick errors. A second forward
pass writes one pose per original row, interpolating the six relevant
corrections (position and attitude) between stored ticks. The cap is 1,024
blocks: when full, `_smooth_merge` composes neighbouring blocks so storage
stays bounded, including on long files. The final blind state has no future
observation and remains its filtered state (`Docs/TRACK3_PLAN.md`, “Step 6”).

The Step E tuning-only smoother trial was rejected before a held-out rule
existed. The later Step 6 rule was registered and judged on official-script
copies; it passed and was ported to the shipped `pathfinder.py` (`Docs/TRACK3_PLAN.md`,
“Step E” and “Step 6”). This is an offline refinement of the same IMU evidence,
not an additional position measurement.

## Scoring and limits

The organisers align an output to hidden ground truth with rigid SE(3)
Umeyama fitting before computing translational APE (`Docs/TRACK3_PLAN.md`,
“Organisers' FAQ”). This can align a never-moving output to the truth's
centroid. It is therefore essential to report that floor beside the estimate,
under identical timestamp association and alignment. `Docs/RESULTS.md`
`step6-H46` and `Docs/TRACK3_PLAN.md` “Step 6” record the shipped held-out
EuRoC comparison; `Docs/TUMVI_BASELINE.md` “Means by reading and set” records
the TUM-VI baseline **before** the shipped smoother (`Docs/NUMBERS.md`, “Sets”).

The code has no direct in-flight velocity measurement; V2 and V2P constrain
the trajectory without proving its shape. The TUM-VI baseline records
`fallback_zero` on all six clean rooms and all 24 official copies
(`Docs/TUMVI_BASELINE.md`, “Calibration”), so the intended still-run bias
calibration did not fire there. This is a measured coverage limit.

### Code and plan disagreements

- `Docs/TRACK3_PLAN.md`, “Direction”, describes a jamming meter setting trust
  and a per-flight learned envelope as part of the original approach. The
  shipped `pathfinder.py` has fixed V2/V2P noise and no `JAM_ON` or `LEARN_ON`;
  the rejected implementations are in `tools/pathfinder_lab.py` (“Lean
  pathfinder” in the plan).
- `Docs/TRACK3_PLAN.md`, “Step L1”, says shrinkage was copied into
  `pathfinder.py`. The later lean step removed it from that shipped file;
  it remains off in the lab and reference copies.
- `Docs/TRACK3_PLAN.md`, “Step 7b”, anticipates a TUM-VI revisit of denoised
  V1 and says TUM-VI was not downloaded. The later
  `Docs/TUMVI_BASELINE.md` reports rooms 1–6, but it does not report a new
  denoised-V1 experiment. The shipped V1 remains the strict stillness test.
- `Docs/TRACK3_PLAN.md`, “Step E”, calls `SMOOTH_ON` off, reflecting its earlier
  tuning trial. The later “Step 6” and `pathfinder.py` now put it on; the
  Step 6 outcome supersedes the Step E status.


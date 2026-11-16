# Track 3 plan: Path Finder (trajectory estimation under sensor degradation)

Running record of what is done, verified, blocked and unknown. Dates are IST. Update this file in the
same commit as the work it describes. The full PRD, day-by-day plan and risk table live in the team doc
"Vortex: Track 3 PRD, Plan of Action and Checklist".

Status vocabulary: **Done (verified)** = run with the stated result; **Done (unverified)** = written but
not run on its real input; **Blocked**; **Not started**.

## Direction (revised 15 Nov 2026, evening)

The official Track 3 slides define the task: estimate a 6-DoF trajectory from a **degraded IMU only**
(EuRoC MAV and TUM-VI, EuRoC `imu0/data.csv` format, gravity alignment unknown), write
`estimated_trajectory.txt` (`timestamp tx ty tz qx qy qz qw`, seconds, exactly one pose per IMU row),
survive rising noise, bias drift and 2 s dropouts, and dead-reckon 5 s after total IMU failure. Budget:
peak RAM <= 8 MB, <= 20 ms compute per second of IMU, single thread, offline. Scoring: efficiency 40
(memory 20, runtime 20), trajectory 60 (waypoints 30, blind 5 s 20, dropouts 10), via evo against hidden
ground truth.

This replaces the earlier S24/ADVIO pose-fusion direction. The S24 and the live stations become jury
demo material only.

**Approach: velocity witnesses.** No pretrained network. Vortex gathers independent, drift-free hints
about velocity from the IMU's own physics, calibrates them in the healthy opening seconds, and a jamming
meter sets the trust of each:

| Witness | Applies to | Plan |
|---|---|---|
| V1 Stillness (zero-velocity updates) | Both datasets | Core. **On** (step 7a, 16 Nov). On EuRoC MH it fires only during the starting ground rest (3 to 25 ticks), so it adds nothing in flight there; it matters for walking (TUM-VI) and landings |
| V2 Flight envelope learned in the healthy phase | Both datasets | Core. **On** (step 7a, 16 Nov): speed envelope + volume envelope (running centre), fixed values chosen on MH_01/02; learning them in the healthy phase is still to do. Bounds drift from km to metres, but only to the level of a trajectory that never moves (see step 7a) |
| V3 Rotor drag (horizontal specific force proportional to body velocity) | Multirotor (EuRoC) | **Off.** Rule v1: NO-GO on MH_01 (16 Nov; the hand-carried start). **Rule v2 pre-registered** 16 Nov (commit c1b594c, `tools/drag_fit.py`): airborne part only, thrust-perpendicular axes, fixed k = 0.20 /s. Decision on Vicon Room 1 (not yet downloaded): stage A = signal on 2 of 3 sequences, stage B = V3 on only if mean APE and RPE 1 s improve >= 10 % over V1 + V2 there. MH_01..05 (tuning set) pass stage A with R^2 0.65..0.96 |
| V4 Turn physics (speed = lateral accel / turn rate, steady turns) | Steady turns | Switchable |
| V5 Walking rhythm | Hand-held (TUM-VI) | Switchable |
| V6 Tilt and acceleration link | Multirotor | Feeds the blind 5 s forecaster |
| V7 Rotor-vibration speed cue | Multirotor | Experiment only |

No witness is load-bearing: V1 + V2 alone must bound drift. Every switchable feature stays on only if
`score.py` shows a gain on sequences we did not tune on.

Deadline **22 Nov 2026, 11:59 PM** per the timeline slide; two other slides say 18 Nov (asked the
organisers, see Q1). Full-time work starts **20 Nov**.

## Steps

| # | Goal | Status | Exit criterion |
|---|---|---|---|
| 1 | Repo restructure, Python package; old ESP32/Unity code deleted (in git history before 15 Nov) | **Done (verified)** 15 Nov | `pytest` green |
| 2 | Shared pieces: quaternion maths, data types, metrics (ATE/RPE, alignment), TUM writer, synthetic data, still-period detection, dead-reckoning baseline | **Done (verified on synthetic data)** 15 Nov: 32 tests | Reused by steps 3 to 9 |
| 2c | Live sensor stations: S24 via Sensor Logger HTTP push, synthetic fallback | **Done (unverified with the real phone)** 15 Nov | Demo material only |
| 2e | Efficiency floor: interpreter RSS and start-up, parse and parse + write cost per row (`tools/measure_floor.py`, `Docs/FLOOR.md`) | **Done (verified on SYNTHETIC input)** 15 Nov: Windows 3.13/3.14, WSL2 Linux 3.12 | Numbers reported before step 3 |
| 3 | EuRoC/TUM-VI `imu0/data.csv` loader keeping every row; output checker; `main.py` skeleton (one pose per row) | Loader (`vortex/data/euroc.py`), row rules (`vortex/rowspec.py`) and checker (`vortex/check_output.py`): **Done (verified on synthetic files)** 16 Nov. `main.py` skeleton (final I/O path, identity poses): **Done (verified on synthetic files)** 16 Nov; not yet run on MH_01 | `main.py` on MH_01 passes the checker |
| 4 | Seeded degradation script: rising noise, bias drift, 2 s dropouts, failure + 5 s | **Done (verified on synthetic files)** 16 Nov: `vortex/degrade.py`; NaN or missing dropout rows, NaN/zero/stuck failure, optional duplicate and swapped rows; levels are placeholders until Q2 | Same seed gives identical files (checked) |
| 5 | `benchmark.py` (tracemalloc and process RSS, ms per s of IMU) and `score.py` (ATE/RPE split by dropout and blind windows, coverage) | `benchmark.py` + `Docs/BUDGET.md` + tracemalloc pytest gate: **Done (verified on synthetic input)** 16 Nov. `score.py` (`vortex/scoring.py`): evo-style ATE/RPE, alignments none/origin/se3/sim3/given, phase split, waypoint proxies: **Done (verified against evo on synthetic data)** 16 Nov; not yet run on MH_01 | Both run on MH_01 |
| 6 | Filter core: initialisation and self-calibration (W2), front end and jamming meter (W3), dropout bridging | 6a init + strapdown integrator: **Done (verified on SYNTHETIC data and MH_01)** 16 Nov. 6b self-calibration on the longest still run in the first 60 s + backward pass before it: **Done (verified on SYNTHETIC data and MH_01..05)** 16 Nov; reference and `main.py` bit-identical. 6c dropout covariance (`GAP_ON`, **on**) and noise meter (`JAM_ON`, **off** by rule v2): **Done (verified on SYNTHETIC data and seeded degraded MH copies)** 16 Nov; reference and `main.py` bit-identical. Degraded held-out mean APE 8.48 -> 6.69 m (seeds 4..6); clean unchanged. 6d rows before the anchor hold its position (`PRE_HOLD`, **on** by a pre-registered no-harm rule): **Done (verified on SYNTHETIC data and MH_01..05 clean and degraded)** 16 Nov; clean mean APE 5.29 -> 4.84 m (MH_02 5.98 -> 3.85, a tuning sequence). Failure detection: step 8a | Beats dead reckoning on degraded MH_01 |
| 7 | Velocity witnesses (W1): V1, V2 core; V3 after go/no-go; V4, V5 switchable; platform detection (W4) | 7a error-state filter + V1 + V2: **Done (verified on SYNTHETIC data and MH_01..05)** 16 Nov; reference and `main.py` bit-identical. Result: drift bounded (APE 249..1,288 m -> 3.5..6.6 m) but **not better than a never-moving trajectory** (mean APE 5.29 vs 5.25 m). V3: rule v2 pre-registered 16 Nov (commit c1b594c), waiting for Vicon Room 1. V4, V5, W4: Not started | Ablation table, each witness on and off, on held-out sequences |
| 8 | Blind 5 s forecaster (W5), dead-sensor detection, per-row confidence (W6) | 8a dead-sensor detection (`DEAD_ON`, **on**) and velocity-decay forecaster (`FC_ON`, **on**, FC_TAU 0.5 s chosen on MH_01/02): **Done (verified on SYNTHETIC data and seeded degraded MH copies)** 16 Nov; both pass the pre-registered rule on held-out MH_03..05; reference and `main.py` bit-identical. Held-out blind growth -49.5 % (study A); zero failures 27.0 -> 4.4 m. W6: Not started | Blind error below constant velocity; coverage table |
| 9 | Efficiency pass (C core if whole-process RAM counts); submission bundle, Dockerfile, deck, video | Not started | Valid `team_name.zip` by 21 Nov 6 PM; submitted 3 h before cutoff |

## Open questions (Q1 to Q5 are in the email drafted for prism@samsung.com on 15 Nov)

| Q | Question | Owner |
|---|---|---|
| Q1 | Final deadline: 18 Nov or 22 Nov; Google Form link | Arnav |
| Q2 | Track 3 student package: degradation script, sample data, evaluator | Arnav |
| Q3 | Are waypoint positions or times given as input? | Arnav |
| Q4 | Is 8 MB peak RAM measured for the whole process or the algorithm only? Is `main.cpp` accepted? **Now urgent:** a bare `python -S -c pass` already peaks at 8.4 MB RSS (WSL2 Linux, 3.12) and 9.5 to 9.7 MB (Windows 3.13/3.14), so CPython cannot meet 8 MB whole-process RSS; a C++ parse + write floor peaks at 4.3 MB (Windows). See `Docs/FLOOR.md`. Step 6a: compiling the larger `main.py` source adds about 1.1 MB peak RSS (11.8 vs 10.7 MB compile-only, Win 3.14); a 3-line stub importing a cached `.pyc` peaks at 10.3 MB, but a `.pyc` only works on the matching Python version (decide in step 9). Step 6b: compile-only is now 13.07 MB vs a bare 9.80 MB (+3.3 MB, Win 3.14); the run itself from a cached `.pyc` peaks at 11.92 MB on MH_01. Splitting the source into separately compiled modules may also lower the compile peak (not measured). Step 7a: compile-only 14.91 MB vs 13.15 MB for 6b and 9.80 MB bare (Win 3.14); the MH_01 run from a cached `.pyc` peaks at 12.05 MB (6b: 11.92), from source at 15.43 MB. The filter itself costs about 0.1 MB; compiling costs about 3.4 MB | Arnav |
| Q5 | Demo video length: 2 to 3, 3, or 5 minutes? | Arnav |
| Q6 | Is the rotor-drag signal visible in EuRoC's IMU (offline fit on clean MH_01)? **Answered 16 Nov: NO-GO under the pre-registered rule** (whole sequence; the hand-carried start breaks it). Exploratory in-flight fit: visible, k 0.14 to 0.25 /s. See `Docs/DRAG.md`. **Rule v2** pre-registered 16 Nov (commit c1b594c): decided on Vicon Room 1 | Arnav + Claude, before 20 Nov |

## Results so far (15 Nov 2026, branch `track3/python-pipeline`)

| Item | Result | Where |
|---|---|---|
| `pytest` | 32 passed | Linux sandbox, Python 3.13, numpy 2.5 |
| Dead reckoning, noiseless synthetic, 20 s, exact gravity, 5 ms velocity window | final error 1.2 cm | same; shows the integrator is consistent |
| EuRoC / TUM-VI download from the sandbox | Blocked (hosts refused by the network allowlist) | Arnav downloads on Windows |

## Efficiency floor (15 Nov 2026, branch `track3/imu-core`; SYNTHETIC 36,000-row EuRoC-format file; full tables in `Docs/FLOOR.md`)

| Item | Result | Where |
|---|---|---|
| Bare interpreter peak RSS, `python -S -c pass` | 8.46 MB (Linux 3.12), 9.50 MB (Win 3.13), 9.74 MB (Win 3.14) | i7-14650HX laptop; Linux = WSL2 Ubuntu 24.04 |
| Start-up wall, `python -S -c pass` | 6 ms (Linux), 23 ms (Windows) | same |
| What `-S` saves vs plain `python` | Linux 6.6 ms, 1.4 MB; Win 3.13 3 ms, 0.8 MB; Win 3.14 42 ms, 3.7 MB (depends on installed site-packages) | same |
| Parse + write poses, loop only (bytes I/O) | 2.5 to 2.7 us per row (budget 100) | same |
| Parse + write poses, whole process | 0.55 ms (Linux) to 0.68 ms (Windows) per IMU-second (budget 20) | same |
| Whole-process peak RSS, parse + write, 256-line output chunks | 9.30 MB (Linux), 10.73 MB (Win 3.13), 11.04 MB (Win 3.14) | same |
| tracemalloc peak, parse + write, 256-line output chunks | 146 to 270 KB | same |
| C++ floor (MinGW -O2 -static, stdio fprintf), parse + write | 4.33 MB RSS, 8 us per row (fprintf is the cost; slower than the Python loop) | Windows only; no g++ in WSL |

## Data tools (16 Nov 2026, branch `track3/step2-data`)

| Item | Result | Where |
|---|---|---|
| `pytest` | 86 passed (32 earlier + 54 new) | Windows, Python 3.14.7, numpy 2.5.3 |
| Degrade synthetic 36,000 rows, seed 1, both dropout modes, 2 duplicates, 2 swaps; identity poses via `tools/floor_worker.py`; `check_output` | PASS: 31,602 rows (NaN mode) and 30,402 rows (missing mode); same seed gives identical bytes | Windows; checker run on Python 3.13 without numpy |
| Empty-field NaN (`--nan-text ""`, what pandas writes) | Crashes the floor worker's parser (`float(b'')`): `main.py` must handle empty fields | same |

## main.py skeleton (16 Nov 2026, branch `track3/step3-main`, commit a997d68; SYNTHETIC 36,000 rows; full ledger in `Docs/BUDGET.md`)

| Item | Result | Where |
|---|---|---|
| `pytest` | 100 passed (86 earlier + 3 BOM cases + 11 main.py) | Windows, Python 3.14.7 |
| `python -S main.py`, whole process | 2.12 us/row, 0.42 ms per IMU-s (Linux 3.12); 3.24 and 2.93 us/row (Win 3.13, 3.14) | i7-14650HX |
| Peak RSS, whole process | 8.96 MB (Linux), 10.19 MB (Win 3.13), 10.57 MB (Win 3.14) | same |
| tracemalloc peak | 144 to 268 KB; flat from 3 to 15 min of input (pytest gate) | same |
| `python main.py` without `-S` | +0.4 to +1.1 us/row, +0.8 to +3.6 MB RSS | same |
| Parse-guard choices (`tools/bench_choices.py`) | all guards together cost at most ~0.35 us/row, inside run-to-run noise | Win 3.13/3.14, Linux 3.12 |

## score.py (16 Nov 2026, branch `track3/step4-score`)

| Item | Result | Where |
|---|---|---|
| `pytest` | 116 passed (100 earlier + 16 scoring) | Windows, Python 3.14.7 |
| Cross-check against pip-installed evo (separate venv), 8 cases: APE none, -a, -as, --align_origin, --n_to_align; RPE delta 1 and 200 frames with -a and -as | Worst difference 4.2e-7 m, inside evo's 6-digit print rounding (`Docs/EVO_CROSSCHECK.md`) | SYNTHETIC pair, seed 0; Windows |

Which alignment the organisers use with evo is still unknown; `score.py` reports ATE under all four.

## Estimator step 6a: init + strapdown integrator (16 Nov 2026, branch `track3/step6-integrator`, commit a4f25e3; SYNTHETIC)

| Item | Result | Where |
|---|---|---|
| `pytest` | 131 passed (116 earlier + 8 strapdown + 7 equivalence); 136 with the step 5 branch merged in (+5 drag tool) | Windows, Python 3.14.7 |
| `main.py` vs reference, every row | max difference exactly 0 (position and quaternion) on the messy file, 36,000 random rows, degraded files and physical motion | Windows 3.14 |
| Noiseless SYNTHETIC motion, 30 s, true initial attitude | position error 6.3 mm, attitude error 4.2e-6 rad | reference |
| `python -S main.py`, whole process (36,000 rows) | 5.07 us/row (Linux 3.12), 5.67 (Win 3.13), 7.05 (Win 3.14); before: 2.12, 3.24, 2.93. In-process loop 3.5 to 5.4 us/row. The machine also measured about 20 % slower on the unchanged parse stage this run | i7-14650HX |
| Peak RSS, whole process | 10.14 MB (Linux), 11.29 (Win 3.13), 11.66 (Win 3.14); before: 8.96, 10.19, 10.57. Cause: compiling the bigger source (see Q4), not the run | same |
| tracemalloc peak | 159 to 283 KB | same |

## First real data: EuRoC Machine Hall (16 Nov 2026, branch `track3/step5-mh01`)

Downloaded by Arnav from the ETH Research Collection (`machine_hall.zip`, 12.7 GB, all five MH sequences with bags). Only `imu0` and `state_groundtruth_estimate0` were extracted to `data/euroc/MH_0x_*/mav0/` (git-ignored). Rows: MH_01 36,820 IMU and 36,382 ground truth; MH_02 30,400 and 29,993; MH_03 27,008 and 26,302; MH_04 20,320 and 19,753; MH_05 22,721 and 22,212.

| Item | Result | Where |
|---|---|---|
| Drag go/no-go on MH_01, pre-registered rule (`tools/drag_fit.py`, rule committed in a1a8f65 before the data) | **NO-GO**: first-half k = -0.09 (y), -0.11 (z); held-out R^2 -0.71, -0.66. V3 stays off | `Docs/DRAG.md`, `Docs/drag/MH_01_easy.svg` |
| Same rule on MH_02 to MH_05 (extra evidence) | NO-GO on all four; body y passes on MH_03 only | same |
| Why: ground truth shows MH sequences start **hand-carried** (MH_01: 0.8 m/s at t = 0), then a ground rest (MH_01: about 20 to 44 s), then flight. Carried motion has no rotor drag | Rest ends at 43.6, 37.7, 17.0, 18.9, 19.5 s (MH_01 to 05) | `--after-rest` output |
| EXPLORATORY (post hoc): fit only after the longest ground rest | k = 0.18 to 0.25 /s (y), 0.14 to 0.24 /s (z) on all five; in-flight R^2 0.69 to 0.96 (y), 0.38 to 0.61 (z); raw unsmoothed R^2 at most 0.15, so drag needs about 1 s of averaging | `Docs/DRAG.md` rows `*_after_rest` |
| Body z sits at about -3.3 m/s^2 in flight: the IMU x axis is about 20 deg off the thrust axis, so thrust changes leak into z | A future V3 should use axes perpendicular to the measured thrust direction | `Docs/drag/MH_05_difficult_after_rest.svg` |
| **Consequence for initialisation**: the "first second is still" assumption of step 6a does not hold on EuRoC MH | Init must find stillness anywhere in the healthy phase, or work while moving (step 6b) | ground truth |

## Step 6a on real MH_01 (16 Nov 2026, branch `track3/step6-integrator`)

| Item | Result | Where |
|---|---|---|
| `main.py` on MH_01 + `vortex/check_output.py` | PASS: 36,820 rows in, 36,820 out; 0.39 s wall | Windows, Python 3.14 |
| `benchmark.py --input` MH_01 | 6.36 us/row, 1.27 ms per IMU-s (an earlier run: 5.30, 1.06), peak RSS 11.66 MB, tracemalloc 283 KB, gate PASS | `Docs/BUDGET.md` row `windows-py314-mh01` |
| Init on MH_01's first second | Not still (accel std up to 1.3 m/s^2): falls back to gyro bias 0, g = 9.81 | as designed; see the hand-carried start above |
| `score.py` on that output (pure dead reckoning, uncorrected gyro bias of 0.079 rad/s about z) | ATE se3 51,304 m, final 118 km; sim3 4.2 m. Expected without bias estimation or witnesses; this is the floor step 6b and 7 must beat | scratch run, not committed |
| `tools/integrator_check.py` MH_01, start 25 s (ground rest) | OWN INIT from that rest window: gyro bias (-0.0034, 0.0210, 0.0797) vs ground truth (-0.0032, 0.0213, 0.0785) rad/s; end error 0.25 m after 10 s, 6.6 m after 30 s, 121 m after 60 s (yaw + origin fitted). ORACLE (ground-truth attitude and biases): 2.1, 51, 293 m | Windows 3.14 |
| Same, MH_02, start 28 s | own gyro bias within 1.5e-3 rad/s of ground truth; 0.18 m after 5 s, 1.1 m after 10 s | same |
| Conclusion | Frames, signs and time base are right on real data (a frame error would give about 500 m in 10 s). Drift over a minute comes from the uncorrected accelerometer bias (0.137 m/s^2 on y) and is what the witnesses must bound | |

## Step 6b: self-calibration on a still run (16 Nov 2026, branch `track3/step6b-calibration`, commit 6862f9d)

| Item | Result | Where |
|---|---|---|
| `pytest` | 144 passed (136 + 5 reference + 2 equivalence + 1 memory) | Windows, Python 3.14.7 |
| Still run found (0.25 s bins, first 60 s), MH_01..05 | 24.25-29.75, 26.5-29.75, 10.75-12.75, 12.5-14.5, 0-3 s; gyro bias within 1.5e-3 rad/s of ground truth on all five | reference |
| `main.py` vs reference on MH_01..05 | max difference exactly 0; 300 to 5,625 rows go through the backward pass | Windows 3.14 |
| SYNTHETIC move-rest-move (32 s, tiny noise) | position error below 2 cm before and after the anchor; with 10x larger noise the oracle itself ends 2.8 cm off | `tests/test_strapdown.py` |
| Clean MH_01..05, 6a -> 6b (`tools/eval_euroc.py`, `Docs/RESULTS.md`) | APE SE3: 51,304 -> 1,288; 34,198 -> 941; 18,193 -> 677; 17,687 -> 249; 594 -> 508 m. Final error 118 km -> 3.9 km on MH_01. Still pure dead reckoning: the accelerometer bias is uncorrected until V1/V2 | Windows 3.14 |
| `python -S main.py`, whole process | 6.11 us/row Win 3.14, 5.45 Win 3.13, 6.20 Linux 3.12; MH_01 6.31 us/row, 1.26 ms per IMU-s. Gate PASS on all | `Docs/BUDGET.md` |
| Memory | tracemalloc 579 KB on MH_01, 943 KB with 11,500 stored rows (worst realistic case; test gate < 4 MB). Peak RSS 13.38 MB (Win 3.14), 12.97 (Win 3.13), 11.48 (Linux), 13.71 (MH_01): the rise is compile memory, see Q4 | same |

## Step 7a: error-state filter, V1 stillness, V2 flight envelope (16 Nov 2026, branch `track3/step7-v1v2`, commit 290c894)

Reference `vortex/core/witness.py`, copied into `main.py` (bit-identical: max difference exactly 0 on MH_01..05 and on every synthetic test file). 15-state error-state Kalman filter on top of the 6b strapdown; the covariance is stepped once per 0.25 s tick (the 6b stillness bin). V1: ZUPT + gyro-bias update on two consecutive steady still bins. V2: speed envelope (velocity pulled to 0, sigma 2 m/s horizontal, 0.3 vertical) and volume envelope (position pulled to its own 10 s running centre, sigma 5 m horizontal, 2 m vertical). The rows before the anchor are still backward dead reckoning, unfiltered.

Tuning was done on MH_01/02 only; MH_03..05 were run once with the chosen values. Rule: lowest mean of APE/floor + RPE1s/floor after the anchor, floor = a never-moving trajectory. The landscape was flat (1.92 to 1.97 against 2.0 for the floor).

| Item | Result | Where |
|---|---|---|
| `pytest` | 155 passed (144 + 9 witness + 2 equivalence) | Windows, Python 3.14.7 |
| SYNTHETIC second rest after unseen bias steps (0.1 m/s^2, 0.01 rad/s) | V1 on: 0.8 m error at the end (12 m when the rest begins), gyro bias found within 1e-3; V1 off: 69 m and growing | `tests/test_witness.py` |
| SYNTHETIC 108 s of motion with an unseen 0.084 m/s^2 accel bias | dead reckoning > 50 m; V2 speed < 10 m; V2 speed + volume < 5 m; bias recovered within 50 % | same |
| Floor: never-moving trajectory (`tools/baseline_still.py`) | APE 4.31, 4.65, 3.58, 6.82, 6.88 m (mean 5.25); RPE 1 s 0.50, 0.54, 1.19, 1.13, 1.03 (mean 0.878) | `Docs/RESULTS.md` |
| 6b -> 7a, clean MH_01..05 (MH_03..05 held out) | APE SE3 1,288 -> 3.99; 941 -> 5.97; 677 -> 3.53; 249 -> 6.41; 508 -> 6.55 m (mean 5.29). RPE 1 s mean 26.8 -> 0.936 | same |
| Ablation (mean over MH_01..05, APE m / RPE 1 s m) | V1 only 717 / 26.3 (no in-flight rests on MH); V1 + V2 speed 5.30 / 0.959; V1 + V2 volume 5.27 / 0.980; V2 without V1 5.27 / 0.934; both 5.29 / 0.936 | same |
| **Verdict** | V2 is what bounds the drift; V1 adds nothing on MH flights. Neither beats standing still: in flight the velocity carries a slowly drifting offset of 0.1 to 0.4 m/s (accelerometer error with rotors on, not seen at rest), and a zero-mean prior can only remove it by also flattening the real motion. A witness that measures velocity in flight is needed (V3 drag) | `vortex/core/witness.py` docstring |
| Accelerometer bias found by the filter (end of run) vs ground truth | y 0.110, 0.108, 0.137, 0.096, 0.085 vs 0.126..0.144; x and z poor (z -0.16 vs 0.06 on MH_04) | Windows 3.14 |
| Before vs after the anchor (MH_02, analysis only) | before (hand-carried, unfiltered): APE 11.0 m, RPE 1.84 m; after: 4.04 m, 0.75 m. The smoother step should cover the part before the anchor | scratch analysis |
| `python -S main.py`, whole process | 8.90 us/row Win 3.14, 8.53 Win 3.13, 7.52 Linux 3.12 (6b: 6.11, 5.45, 6.20); MH_01 8.69 us/row, 1.74 ms per IMU-s. Gate PASS on all | `Docs/BUDGET.md` |
| Memory | tracemalloc 288 KB synthetic, 585 KB MH_01. Peak RSS 14.80 MB (Win 3.14), 14.34 (Win 3.13), 12.78 (Linux), 15.36 (MH_01): compile memory, see Q4 | same |

## Drag rule v2 for V3 (16 Nov 2026, branch `track3/v3-rule-v2`, rule commit c1b594c)

Rule v1 failed on MH because every MH sequence starts hand-carried (no rotor drag). Exploration on MH_01..05 (all already used) chose the v2 settings; the rule was committed before any Vicon Room data was on disk (`data/euroc` held MH_01..05 only).

| Item | Result | Where |
|---|---|---|
| Exploratory: body y/z axes vs axes perpendicular to the mean airborne specific force | second axis R^2 0.38..0.61 -> 0.65..0.90 (the IMU sits about 20 deg off the thrust axis, so body z mixes in thrust) | scratch analysis |
| Exploratory: one pooled k for all five | k = 0.1996 /s; R^2 with that fixed k 0.65..0.96 on every axis | same |
| Rule v2 on MH_01..05 (TUNING SET, not evidence) | all five pass: R^2 fixed k 0.65..0.96, free k 0.177..0.223 (within 12 % of 0.20) | `Docs/DRAG.md`, `Docs/drag/v2_*.json` |
| Stage A decision (Vicon Room 1) | **Not run: data not downloaded** | needs Arnav |
| `pytest` | 161 passed (155 + 6 rule v2) | Windows, Python 3.14.7 |


## Step 6c: noise meter and dropout covariance (16 Nov 2026, branch `track3/step6c-jamming`)

Degraded copies: `python -m vortex.degrade data/euroc/<seq> data/degraded/<seq>_s<seed> --seed <seed>`,
seeds 1..3, default (placeholder) levels, MH_01..05: 15 copies (git-ignored). Scoring:
`python tools/eval_euroc.py --tag NAME --degraded` (alignment fitted once on the same main's clean run).

**Decision rule, committed before any on/off comparison.** Two switches, `JAM_ON` (noise meter sets the
filter's white-noise densities) and `GAP_ON` (dropout covariance). Their constants (JAM_TAU 2 s,
GAP_H_TICKS 8, GAP_TAU 20 s) are placeholders and are NOT tuned. A switch stays on only if, on the
held-out copies MH_03..05 x seeds 1..3: (a) mean APE (given alignment) is not worse than with it off,
(b) its target improves by at least 5 %: GAP_ON mean dropout growth, JAM_ON mean APE; and (c) on clean
MH_01..05 the mean APE and mean RPE 1 s are each within +5 % of step 7a. Each switch is judged with the
other one on and off; both readings are reported. MH_01/02 copies are reported but do not decide.
Caveat: the dropout-covariance idea came from diagnosing the step 7a baseline on MH_03_medium_s1 (a
held-out copy: velocity ran away to 10 m/s after the third dropout); no constant was set from it.

**Rule v1 outcome** (16 Nov; reference filter via a scratch runner, step 7a reproduced exactly with both
switches off; held-out = MH_03..05 x seeds 1..3, means):

| Reading | APE m | Dropout growth m | Blind 5 s growth m |
|---|---|---|---|
| both off (= step 7a) | 8.869 | 3.471 | 22.004 |
| JAM only | 7.659 | 2.818 | 14.127 |
| GAP only | 6.852 | 3.303 | 13.478 |
| both on | 6.661 | 2.789 | 9.821 |

GAP_ON fails (b) in both readings: dropout growth -4.8 % (JAM off) and -1.0 % (JAM on), short of 5 %,
although APE improves 23 % / 13 % and blind growth 39 % / 30 %. JAM_ON passes with GAP off (APE -13.6 %)
and fails (b) with GAP on (-2.8 %); rule v1 did not say how to combine the readings. Clean MH_01..05:
JAM_ON 5.375 m APE (+1.6 %), 0.941 m RPE 1 s (+0.5 %): passes (c); GAP_ON cannot change a run without
gaps (tested). **Under rule v1 both switches stay off.**

**Rule v2 (replication), committed before seeds 4..6 exist.** v1's target for GAP was the wrong one: the
dropout covariance acts after the window (the witnesses pull the tilt back), while dropout growth is
measured inside it. New copies MH_03..05 x seeds 4..6 (noise and dropout realisations never run), same
constants, no tuning. Each switch is judged with the other on; if one fails, the other is re-judged with
it off. A switch ships on only if on those 9 copies (a) mean APE is not worse, (b) mean APE or mean blind
5 s growth improves by at least 5 %, and (c) the clean condition of v1 holds. Otherwise it ships off.
This is a second look chosen after seeing v1: weaker evidence than a first pre-registered test.

**Rule v2 outcome** (16 Nov, `main.py` at f8dfe4f with `--set`; MH_03..05 x seeds 4..6, 9 copies, means;
`Docs/RESULTS.md` tags `step6c-rep-*`):

| Reading | APE m | RPE 1 s m | Dropout growth m | Blind 5 s growth m |
|---|---|---|---|---|
| both off (= step 7a) | 8.481 | 1.212 | 3.907 | 8.597 |
| JAM only | 7.399 | 1.173 | 3.338 | 6.146 |
| GAP only | 6.687 | 1.170 | 3.195 | 6.771 |
| both on | 6.479 | 1.165 | 2.789 | 6.788 |

- GAP_ON with JAM on: APE -12.4 %: passes (blind growth +10.4 % in this reading).
- JAM_ON with GAP on: APE -3.1 %, blind growth +0.3 %: **fails** (b).
- GAP_ON re-judged with JAM off: APE -21.2 %, blind growth -21.2 %: **passes**.
- **Shipped: GAP_ON = True, JAM_ON = False.** Clean MH_01..05 with the shipped settings (tag `step6c`)
  is identical to step 7a (largest difference 0.0): no gaps in the clean files.
- `main.py` reproduces the reference runs exactly on seeds 1..3 (all four readings, same means to 3
  decimals as the scratch reference runner).

| Item | Result | Where |
|---|---|---|
| Seeds 1..3, all 15 copies, shipped (GAP only) vs step 7a | MH_01/02: APE 6.12 -> 5.58 m, blind growth 6.00 -> 5.50 m; MH_03..05: APE 8.87 -> 6.85 m, blind growth 22.0 -> 13.5 m | `Docs/RESULTS.md` `step6c-deg-*` |
| Why GAP helps | after a 2 s dropout the held attitude is typically 2..9 deg off in tilt (clean MH, IMU-only study); on MH_03_s1 step 7a's velocity then ran away to 10 m/s. The added covariance lets V2 pull tilt and velocity back | scratch study, not in the repo |
| Noise meter reading on clean MH flight | rotor vibration dominates: about 0.04 rad/s and 1 m/s^2 per sample, above the placeholder added noise (0.05 rad/s, 0.5 m/s^2 at the end); the meter cannot tell them apart | same |
| `pytest` | 170 passed (161 + 5 step 6c reference + 4 equivalence readings) | Windows, Python 3.14.7 |
| Budget, `python -S main.py` (commit bd35767) | 8.38 us/row, 15.07 MB peak RSS, 289 KB tracemalloc (Win 3.14); 8.48, 14.50 MB (Win 3.13); 7.82, 13.05 MB (Linux 3.12); MH_01 8.21 us/row, 15.58 MB; degraded MH_01_s1 8.59 us/row, 15.62 MB. Step 7a: 8.90, 14.80; 8.53, 14.34; 7.52, 12.78; MH_01 8.69, 15.36. Gate PASS on all | `Docs/BUDGET.md` |

Not checked: TUM-VI (no data); the organisers' degradation levels (Q2); "missing"-mode dropouts and
stuck/zero failures on real data (synthetic tests only); the blind 5 s window still coasts at constant
velocity (step 8).


## Step 8a: dead-sensor detection and blind forecaster (16 Nov 2026, branch `track3/step8-blind`)

**What happens now in the blind 5 s window.** After the IMU fails, every row is invalid (NaN), so no
tick closes, no witness acts, attitude is held and position coasts at the last velocity. Zero and stuck
failures are worse: their rows are valid numbers, so they are integrated (zero specific force; a frozen
rate and force).

**Two switches** (`vortex/core/witness.py`, mirrored in `main.py`):
- `DEAD_ON`: a row is dead (treated as invalid) when its gyro or its accelerometer triple has repeated
  exactly for STUCK_ROWS = 5 rows in a row, or its accelerometer triple is exactly (0, 0, 0). Clean
  MH_01..05: longest exact repeat is 2 rows, no zero triple (checked). The first 4 rows of a stuck run are
  still integrated (held values, 20 ms at 200 Hz).
- `FC_ON`: while coasting without IMU data (invalid rows, or a step longer than MAX_DT), velocity
  decays toward 0 with time constant FC_TAU and position integrates it: the mean forecast of an
  Ornstein-Uhlenbeck velocity, i.e. the V2 speed envelope's prior. Off = constant velocity. This applies
  to every gap, dropouts included.

**Tuning (MH_01/02 only;** `python tools/blind_study.py --tag step8-tune data/euroc/MH_01_easy
data/euroc/MH_02_easy`, 6 failure points x 3 modes x seeds 100..105, `Docs/BLIND.md`). Means over 12
runs:

| Setting | Blind growth m | Blind RMSE m |
|---|---|---|
| constant velocity (now) | 5.509 | 6.903 |
| FC_TAU 2 s | 2.980 | 6.625 |
| FC_TAU 1 s | 2.530 | 6.475 |
| **FC_TAU 0.5 s (chosen: lowest growth)** | **2.434** | 6.298 |
| hold position (0.001 s) | 2.486 | 6.016 |
| zero failure, DEAD off / on | 28.066 / 5.509 | 14.848 / 6.903 |
| stuck failure, DEAD off / on | 13.777 / 5.519 | 9.447 / 6.917 |

The filter's velocity at the failure is worth about nothing: holding position is as good as any decay.
Oracle checks with ground truth (analysis only, scratch script): even the TRUE velocity at the failure
cuts the 5 s forecast error only from 1.8..5.3 m (hold) to 1.5..4.0 m; pulling toward the running
centre is worse than holding on 4 of 5 sequences. Most blind error is the error already present at the
failure (blind RMSE 6.0..6.9 m against growth 2.4..5.5 m).

**Decision rule, committed before any held-out run** (held-out data does not exist yet):
- (A) `tools/blind_study.py --tag step8-heldout --seed0 200 --taus cv,0.5` on MH_03..05: 6 failure
  points x modes nan/zero/stuck, seeds 200..205.
- (B) new copies `python -m vortex.degrade data/euroc/<seq> data/degraded/<seq>_s<seed> --seed <seed>
  --failure_mode <mode>`, MH_03..05 x seed 7 (nan), 8 (zero), 9 (stuck), scored with `main.py`
  (`tools/eval_euroc.py --degraded --seqs ...`, `--set` per reading).
- `DEAD_ON` ships on only if (1) clean MH_01..05 output is unchanged (largest difference 0), (2) on (A)'s
  zero and stuck runs mean blind growth falls by at least 30 % (forecaster off in both), and (3) on (B)'s
  seed 8 and 9 copies mean APE is not worse.
- `FC_ON` (FC_TAU 0.5 s, judged with DEAD on) ships on only if (1) clean MH_01..05 output is unchanged,
  (2) on all of (A) mean blind growth falls by at least 10 % and mean blind RMSE is not worse, and (3) on
  all 9 copies of (B) mean APE is at most +1 % and mean dropout growth at most +5 %.
- Otherwise the switch ships off. No constant changes after this commit.

**Found on the way, not fixed here (step 6b issue).** In one tuning run (MH_02, failure at 0.9, seed
104) APE was 134.6 m: a dropout at 23..25 s fell before the calibration anchor (28.1 s), and the
backward pass (dead reckoning, no witnesses) reached 757 m error in the first 10 s. The blind window was
normal. Any dropout or heavy noise before the anchor can do this; MH_01/02 anchors are at 27-28 s, inside
the degraded part when healthy_s is 10 s.

**Outcome** (16 Nov; rule committed at ce94cef, before the held-out data existed).

(A) `Docs/BLIND.md` `step8-heldout`: MH_03..05 x 6 failure points x 3 modes, seeds 200..205, reference
estimator, means:

| Setting | Runs | Blind growth m | Blind RMSE m | APE m |
|---|---|---|---|---|
| nan failure, constant velocity (step 6c) | 18 | 8.638 | 8.391 | 6.526 |
| nan failure, FC on | 18 | 4.367 | 7.141 | 6.385 |
| zero failure, DEAD off / on / on + FC | 18 | 27.015 / 8.638 / 4.367 | 14.851 / 8.391 / 7.141 | 7.220 / 6.526 / 6.385 |
| stuck failure, DEAD off / on / on + FC | 18 | 9.356 / 8.652 / 4.371 | 7.927 / 8.356 / 7.128 | 6.512 / 6.525 / 6.384 |

(B) `main.py` on the new copies MH_03..05 x seeds 7 (nan), 8 (zero), 9 (stuck); `Docs/RESULTS.md`
tags `step8-B-off` (= step 6c), `step8-B-dead`, `step8-B-both`. Means:

| Reading | Copies | APE m | Dropout growth m | Blind growth m | Blind RMSE m |
|---|---|---|---|---|---|
| step 6c (both off) | 9 | 6.975 | 2.657 | 15.886 | 8.663 |
| DEAD on | 9 | 6.709 | 2.657 | 5.616 | 3.793 |
| DEAD + FC on | 9 | 6.761 | 2.060 | 5.228 | 3.389 |

Judgement:
- `DEAD_ON` (1) clean output byte-identical (largest difference 0.0); (2) (A) zero + stuck blind growth
  18.185 -> 8.645 m, -52.5 % (>= 30 %); (3) (B) seeds 8 + 9 mean APE 7.526 -> 7.127 m, -5.3 %. **Passes:
  ships on.**
- `FC_ON` (1) clean byte-identical; (2) (A) all 54 runs blind growth 8.643 -> 4.368 m (-49.5 %), blind
  RMSE 8.380 -> 7.137 m (-14.8 %); (3) (B) mean APE 6.709 -> 6.761 m (+0.78 %, limit +1 %), dropout
  growth 2.657 -> 2.060 m (-22.4 %). **Passes: ships on.** Close on APE; on (B) blind growth falls only
  6.9 %, and on two stuck copies it rose (MH_04_s9 4.74 -> 5.87 m, MH_05_s9 2.68 -> 5.38 m).
- With constant velocity, DEAD raised blind RMSE on stuck failures in (A) (7.93 -> 8.36 m); with FC also
  on it is 7.13 m.

Shipped settings (`main.py`, tags `step8` clean and `step8-deg`, all 33 copies, contract PASS on all)
against step 6c `main.py` on the same copies (`step6c-deg-gap`, `step6c-rep-gap`, `step8-B-off`):

| Copies | APE m | Dropout growth m | Blind growth m | Blind RMSE m |
|---|---|---|---|---|
| MH_01/02 x seeds 1..3 (tuning) | 5.578 -> 5.507 | 1.652 -> 0.926 | 5.502 -> 2.356 | 5.212 -> 4.103 |
| MH_03..05 x seeds 1..3 | 6.852 -> 6.320 | 3.303 -> 2.369 | 13.478 -> 5.916 | 11.383 -> 6.572 |
| MH_03..05 x seeds 4..6 | 6.687 -> 6.516 | 3.195 -> 2.281 | 6.771 -> 5.311 | 7.404 -> 5.455 |
| MH_03..05 x seeds 7..9 (nan/zero/stuck) | 6.975 -> 6.761 | 2.657 -> 2.060 | 15.886 -> 5.228 | 8.663 -> 3.389 |
| Clean MH_01..05 | identical to step 6c (largest difference 0.0) | | | |

| Item | Result | Where |
|---|---|---|
| `pytest` | 181 passed (170 + 6 step 8a reference + 5 equivalence) | Windows, Python 3.14.7 |
| Budget, `python -S main.py` (commit 02e2e5d) | 9.78 us/row, 15.20 MB peak RSS, 289 KB tracemalloc (Win 3.14); 8.63, 14.74 MB (Win 3.13); 7.30, 13.13 MB (Linux 3.12); MH_01 8.98, 15.70 MB; degraded MH_01_s1 8.85, 15.68 MB. Step 6c (bd35767): 8.38, 15.07; 8.48, 14.50; 7.82, 13.05; 8.21, 15.58; 8.59, 15.62. Within the +-15 % rerun spread except Win 3.14 (+17 %); gate PASS on all | `Docs/BUDGET.md` |

Seeds 1..6 were seen during step 6c (not during the step 8a tuning); seeds 7..9 and 200..205 were made
after the rule.

Not checked: TUM-VI (no data); the organisers' failure format (Q2): a failure that writes plausible
noise, a slowly freezing sensor or a stuck value that changes in the last bit would not be caught;
STUCK_ROWS assumes about 200 Hz; per-row confidence (W6) and a coverage table are not started; the
backward-pass blow-up above is not fixed.


## Step 6d: rows before the anchor (16 Nov 2026, branch `track3/step6d-backward`)

**Problem.** Rows before the calibration anchor (mid still run, 27-28 s into MH_01/02) get poses from
a backward strapdown pass: dead reckoning with no witnesses. Found in step 8a: one degraded MH_02 copy
reached 757 m error there (APE 134.6 m) after a dropout before the anchor.

**Switch** `PRE_HOLD` (`vortex/core/witness.py`, mirrored in `main.py`): rows before the anchor keep the
anchor's position (0, 0, 0); their attitude still comes from the backward gyro integration. Off = the
step 6b backward pass.

**Tuning (MH_01/02 only;** scratch study, reference estimator, alignment from each variant's own clean
run; ground truth for scoring only). Clean, and 20 degraded copies per sequence (default levels, seeds
100..119):

| | Backward pass (now) | Backward to the first gap, then hold | Hold position |
|---|---|---|---|
| Clean MH_01 APE / pre-anchor RMSE m | 3.986 / 4.38 | same | 3.911 / 4.19 |
| Clean MH_02 APE / pre-anchor RMSE m | 5.975 / 10.98 | same | 3.846 / 4.25 |
| Degraded MH_01, mean APE (max) m | 5.881 (16.33) | 5.032 (8.06) | 4.236 (5.52) |
| Degraded MH_01, mean pre-anchor RMSE m | 10.29 | 7.54 | 4.19 |

Backward dead reckoning is worse than standing still even on clean data (the step 7a lesson again); the
added noise from 10 s on makes it worse. Degraded MH_02: the calibration fell back to the step 6a
first-second initialisation in 19 of 20 copies (the added noise starts before its still run and breaks
the still test), so there is no backward segment and nothing changes; see "Found" below.

**Decision rule, committed before any held-out run with the switch.** Held-out: clean MH_03..05 and new
copies MH_03..05 x seeds 10..12 (default levels; made after this commit). `PRE_HOLD` ships on only if
(a) clean MH_03..05 mean APE (SE3) is not worse, (b) on the 9 new copies mean APE (given alignment, from
each setting's own clean run) is not worse, and (c) no single held-out run's APE is worse by more than
10 %. Otherwise it ships off. Caveat: MH_03..05 anchors are early (11.8, 13.5 and 1.5 s), so the
held-out test has little to act on; this is a no-harm test there, the gain is measured on MH_01/02.

**Found, not fixed.** When the added noise starts before the still run (healthy_s 10 s, MH_02 still run
at about 20-36 s), the still test fails and calibration falls back to the first second: gyro bias and
tilt are then not calibrated. The organisers' healthy length is unknown (Q2).

**Outcome** (16 Nov; rule committed at c2b76cc, `main.py` with `--set PRE_HOLD=...`; `Docs/RESULTS.md`
tags `step6d-H-*`):

| Held-out check | Off | On | Rule |
|---|---|---|---|
| (a) clean MH_03..05 mean APE (SE3) m | 5.4958 | 5.4849 | not worse: passes |
| (b) MH_03..05 x seeds 10..12 mean APE (given) m | 6.2924 | 6.2798 | not worse: passes |
| (c) worst single held-out run | | +1.0 % (MH_03_s10) | <= +10 %: passes |

**Shipped: PRE_HOLD = True.** As expected, the held-out effect is small (early anchors). Shipped
settings against step 8a (`main.py`, tags `step6d` and `step6d-deg`, 42 copies, contract PASS on all):

| Set | Step 8a | Step 6d |
|---|---|---|
| Clean MH_01 / MH_02 APE m | 3.986 / 5.975 | 3.911 / 3.846 |
| Clean MH_01 / MH_02 RPE 1 s m | 0.506 / 0.973 | 0.480 / 0.591 |
| Clean MH_03 / 04 / 05 APE m | 3.529 / 6.412 / 6.546 | 3.530 / 6.378 / 6.546 |
| Clean MH_01..05 mean APE m (never-moving floor 5.25) | 5.290 | **4.842** |
| Degraded MH_01/02 x seeds 1..3, mean APE (max) m | 5.507 (6.33) | 5.146 (6.03) |
| Degraded MH_03..05 x seeds 1..9, mean APE (max) m | 6.532 (10.03) | 6.538 (10.05) |
| Degraded MH_03..05 x seeds 10..12, mean APE m | 6.292 | 6.280 |

The clean mean is below the never-moving floor for the first time, but almost all of the gain is MH_02,
a tuning sequence; on MH_03..05 the change is within +-0.6 %.

| Item | Result | Where |
|---|---|---|
| `pytest` | 183 passed (181 + 1 reference + 1 equivalence reading; the two step 6b identity tests now pass pre_hold off) | Windows, Python 3.14.7 |
| Budget, `python -S main.py` (commit 0f61fda) | 10.23 us/row, 15.17 MB peak RSS (Win 3.14, rerun; first run 11.71); 9.14, 14.75 MB (Win 3.13); 8.20, 13.12 MB (Linux 3.12); MH_01 9.25, 15.68 MB; degraded MH_01_s1 9.23, 15.70 MB. The synthetic input has no rows before the anchor, so the change cannot act there: the spread is machine noise. Gate PASS on all | `Docs/BUDGET.md` |

Not checked: TUM-VI (no data); whether the organisers score attitude (only the position is held); the
calibration fallback on degraded MH_02 ("Found" above) is not fixed.


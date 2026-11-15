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
| V1 Stillness (zero-velocity updates) | Both datasets | Core |
| V2 Flight envelope learned in the healthy phase | Both datasets | Core |
| V3 Rotor drag (horizontal specific force proportional to body velocity) | Multirotor (EuRoC) | **Off: NO-GO** on MH_01 (16 Nov, pre-registered rule). Exploratory: k about 0.2 /s in flight on all five MH sequences; revisit only with a new rule fixed in advance |
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
| 6 | Filter core: initialisation and self-calibration (W2), front end and jamming meter (W3), dropout bridging | 6a init + strapdown integrator: **Done (verified on SYNTHETIC data and MH_01)** 16 Nov. 6b self-calibration on the longest still run in the first 60 s + backward pass before it: **Done (verified on SYNTHETIC data and MH_01..05)** 16 Nov; reference and `main.py` bit-identical. Jamming meter, dropout bridging: Not started (after V1 + V2, per the work order) | Beats dead reckoning on degraded MH_01 |
| 7 | Velocity witnesses (W1): V1, V2 core; V3 after go/no-go; V4, V5 switchable; platform detection (W4) | Not started | Ablation table, each witness on and off, on held-out sequences |
| 8 | Blind 5 s forecaster (W5) and per-row confidence (W6) | Not started | Blind error below constant velocity; coverage table |
| 9 | Efficiency pass (C core if whole-process RAM counts); submission bundle, Dockerfile, deck, video | Not started | Valid `team_name.zip` by 21 Nov 6 PM; submitted 3 h before cutoff |

## Open questions (Q1 to Q5 are in the email drafted for prism@samsung.com on 15 Nov)

| Q | Question | Owner |
|---|---|---|
| Q1 | Final deadline: 18 Nov or 22 Nov; Google Form link | Arnav |
| Q2 | Track 3 student package: degradation script, sample data, evaluator | Arnav |
| Q3 | Are waypoint positions or times given as input? | Arnav |
| Q4 | Is 8 MB peak RAM measured for the whole process or the algorithm only? Is `main.cpp` accepted? **Now urgent:** a bare `python -S -c pass` already peaks at 8.4 MB RSS (WSL2 Linux, 3.12) and 9.5 to 9.7 MB (Windows 3.13/3.14), so CPython cannot meet 8 MB whole-process RSS; a C++ parse + write floor peaks at 4.3 MB (Windows). See `Docs/FLOOR.md`. Step 6a: compiling the larger `main.py` source adds about 1.1 MB peak RSS (11.8 vs 10.7 MB compile-only, Win 3.14); a 3-line stub importing a cached `.pyc` peaks at 10.3 MB, but a `.pyc` only works on the matching Python version (decide in step 9). Step 6b: compile-only is now 13.07 MB vs a bare 9.80 MB (+3.3 MB, Win 3.14); the run itself from a cached `.pyc` peaks at 11.92 MB on MH_01. Splitting the source into separately compiled modules may also lower the compile peak (not measured) | Arnav |
| Q5 | Demo video length: 2 to 3, 3, or 5 minutes? | Arnav |
| Q6 | Is the rotor-drag signal visible in EuRoC's IMU (offline fit on clean MH_01)? **Answered 16 Nov: NO-GO under the pre-registered rule** (whole sequence; the hand-carried start breaks it). Exploratory in-flight fit: visible, k 0.14 to 0.25 /s. See `Docs/DRAG.md` | Arnav + Claude, before 20 Nov |

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

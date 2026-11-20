# Track 3 plan: Path Finder (trajectory estimation under sensor degradation)

Running record of what is done, verified, blocked and unknown. Dates are IST. Update this file in the
same commit as the work it describes. The PRD, day-by-day plan, work split and risk table live in
`Docs/PRD.md` (v2, 18 Nov 2026; supersedes the 15 Nov team doc).

Status vocabulary: **Done (verified)** = run with the stated result; **Done (unverified)** = written but
not run on its real input; **Blocked**; **Not started**.

## Organisers' FAQ (17 Nov 2026): what is settled

Source: `Track3_FAQ_Responses.txt` and the student package's `degrade_imu.py` (both from the organisers;
kept outside the repository). Where they conflict with older text in this file, they win.

| Topic | Answer | Consequence for Vortex |
|---|---|---|
| Language | Python only; `main.cpp` is not accepted; `main.py` is the only entry point | C core (step 9b) becomes a recorded experiment: kept with tests and results, removed from the bundle and the PR gates (Step 1, 17 Nov) |
| 8 MB limit | Measured at algorithm / heap level, not process RSS | Memory gate is now the tracemalloc peak (design target 4 MB, limit 8 MB); RSS reported only |
| Processing order | Offline: whole file in memory allowed (within 8 MB); non-causal / batch smoothing allowed | A forward-backward smoother is in scope (Step 6) |
| Alignment | SE(3) Umeyama, then ATE (evo) | Primary metric: APE with SE(3) fitted on the run being scored, beside the never-moving floor scored the same way |
| Waypoints | Hidden; used only for scoring | Never an input |
| Blind 5 s | Timestamps present, sensor values invalid; exactly one pose per row, never append | `degrade_imu.py` writes exact zeros for the last 5 s |
| Dropouts | Physically missing rows (timestamp jumps) | |
| Test data | Any EuRoC MAV or TUM-VI sequence, degraded with `degrade_imu.py` | All earlier degraded results used our own `vortex/degrade.py`, which does not match: they are history, not evidence |
| Deadline | 22 Nov 2026 (11:59 PM IST) | Freeze a checked zip by Fri 20 Nov, 9 PM |
| Demo video | 2 to 3 minutes, strict maximum 3 | |

What `degrade_imu.py` does (read 17 Nov): columns 2-4 are treated as accelerometer and 5-7 as gyro
(EuRoC files are gyro first; what the organisers feed in is unknown, so both readings are tested); white
noise, bias random walk and scale-factor random walk on all six axes; spikes on all six axes at once (up
to 9 m/s^2 and 1.5 rad/s); stuck runs of 2-10 identical rows; single missing rows (up to 6 %) and missing
bursts of 5-50 rows; duplicated rows anywhere (same timestamp twice); exact zeros for the last 5 s;
values rounded to 6 decimals. Severity ramps from 0.02 at the start to 1.0 at the end (gamma 1.7); only
the first 2 s are protected. The seed is fixed at 42 inside the script.

## Direction (revised 15 Nov 2026, evening; budget, language and alignment superseded by the FAQ above)

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
| V3 Rotor drag (horizontal specific force proportional to body velocity) | Multirotor (EuRoC) | **Off.** Rule v1: NO-GO on MH_01 (16 Nov; the hand-carried start). **Rule v2 pre-registered** 16 Nov (commit c1b594c, `tools/drag_fit.py`): airborne part only, thrust-perpendicular axes, fixed k = 0.20 /s. Decision on Vicon Room 1: **stage A NO-GO (17 Nov; 1 of 3 sequences pass), so V3 is dropped**: stage A = signal on 2 of 3 sequences, stage B = V3 on only if mean APE and RPE 1 s improve >= 10 % over V1 + V2 there. MH_01..05 (tuning set) pass stage A with R^2 0.65..0.96 |
| V4 Turn physics (speed = lateral accel / turn rate, steady turns) | Steady turns | Switchable |
| V5 Walking rhythm | Hand-held (TUM-VI) | Switchable |
| V6 Tilt and acceleration link | Multirotor | Feeds the blind 5 s forecaster |
| V7 Rotor-vibration speed cue | Multirotor | Experiment only |

No witness is load-bearing: V1 + V2 alone must bound drift. Every switchable feature stays on only if
`score.py` shows a gain on sequences we did not tune on.

Deadline **22 Nov 2026, 11:59 PM IST**, confirmed by the FAQ (Q1 closed). Full-time work starts **20 Nov**.

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
| 6 | Filter core: initialisation and self-calibration (W2), front end and jamming meter (W3), dropout bridging | 6a init + strapdown integrator: **Done (verified on SYNTHETIC data and MH_01)** 16 Nov. 6b self-calibration on the longest still run in the first 60 s + backward pass before it: **Done (verified on SYNTHETIC data and MH_01..05)** 16 Nov; reference and `main.py` bit-identical. 6c dropout covariance (`GAP_ON`, **on**) and noise meter (`JAM_ON`, **off** by rule v2): **Done (verified on SYNTHETIC data and seeded degraded MH copies)** 16 Nov; reference and `main.py` bit-identical. Degraded held-out mean APE 8.48 -> 6.69 m (seeds 4..6); clean unchanged. 6d rows before the anchor hold its position (`PRE_HOLD`, **on** by a pre-registered no-harm rule): **Done (verified on SYNTHETIC data and MH_01..05 clean and degraded)** 16 Nov; clean mean APE 5.29 -> 4.84 m (MH_02 5.98 -> 3.85, a tuning sequence). 6e denoised still test when the strict one finds no run (`CAL_NOISE_ON`, **on** by a pre-registered rule): **Done (verified on SYNTHETIC data and MH_01..05 clean and degraded)** 16 Nov; degraded MH_02 fallbacks 19/20 -> 0/20 (tuning), clean unchanged. Failure detection: step 8a | Beats dead reckoning on degraded MH_01 |
| 7 | Velocity witnesses (W1): V1, V2 core; V3 after go/no-go; V4, V5 switchable; platform detection (W4) | 7a error-state filter + V1 + V2: **Done (verified on SYNTHETIC data and MH_01..05)** 16 Nov; reference and `main.py` bit-identical. Result: drift bounded (APE 249..1,288 m -> 3.5..6.6 m) but **not better than a never-moving trajectory** (mean APE 5.29 vs 5.25 m). V3: rule v2 pre-registered 16 Nov (commit c1b594c), waiting for Vicon Room 1. 7b denoised V1 (`ZUPT_DEN_ON`): built in the reference, **off** (pre-registered rule failed on held-out MH_03..05: APE +0.2 %, needed -2 %) 16 Nov; not in `main.py`. V4, V5, W4: Not started | Ablation table, each witness on and off, on held-out sequences |
| 8 | Blind 5 s forecaster (W5), dead-sensor detection, per-row confidence (W6) | 8a dead-sensor detection (`DEAD_ON`, **on**) and velocity-decay forecaster (`FC_ON`, **on**, FC_TAU 0.5 s chosen on MH_01/02): **Done (verified on SYNTHETIC data and seeded degraded MH copies)** 16 Nov; both pass the pre-registered rule on held-out MH_03..05; reference and `main.py` bit-identical. Held-out blind growth -49.5 % (study A); zero failures 27.0 -> 4.4 m. 8b W6 per-row sigma from the filter covariance: built in the reference (`witness.row_sigma`, `tools/coverage.py`, `Docs/COVERAGE.md`) 16 Nov; **not informative** on MH_01/02 (rank correlation with the error -0.07), so no confidence is claimed; not in `main.py` | Blind error below constant velocity; coverage table |
| 9 | Efficiency pass (C core if whole-process RAM counts); submission bundle, Dockerfile, deck, video | 9a `main.py` is a stub importing `pathfinder.py`, and the bundle ships its bytecode: **Done (verified on MH_01..05 clean and degraded, Win 3.13/3.14, WSL2 3.12)** 16 Nov; outputs byte-identical, peak RSS -3.5 to -3.8 MB (MH_01: 11.95 MB Win 3.14, 10.27 MB Linux 3.12), still above 8 MB. Bundle builder `tools/make_bundle.py`, README, Dockerfile: zip verified on all three Pythons; Docker image built and its output identical on all 65 inputs. 9b C core `main.cpp` (Q4 unanswered, so the strict reading is assumed): **Done (verified on MH_01..05 clean and degraded, Windows and WSL2 Linux)** 16 Nov; peak RSS 2.7 MB Linux / 4.8 MB Windows on MH_01, bit-identical to `pathfinder.py` on Linux; bundle in the PRD layout. C-core Dockerfile not built yet. Deck, video: Not started | Valid `team_name.zip` by 21 Nov 6 PM; submitted 3 h before cutoff |
| R1 | FAQ re-plan, Step 1: C core retired from the submission; memory gate moved from RSS to the heap (tracemalloc) | **Done (verified)** 17 Nov: gate PASS on Win 3.14 synthetic + MH_01 and Win 3.13 synthetic; bundle verified on 3.13/3.14; Python Docker image built, MH_01 output identical | Python-only zip verified |
| R2 | Official-script harness (both column readings), input front end, new baseline | **Done (verified)** 17 Nov: 64 copies (8 sequences x readings a, b x seeds 1, 2, 3, 42), front end correct on all 72 files; baseline in `Docs/STEP2_BASELINE.md` | Table shown to Arnav before Step 3 |
| R3 | Fault front end: stuck rows, spikes, bridging of missing samples (three switches), blind-window protection | **Done (verified): all three switches OFF** by the pre-registered rule (17 Nov, rule at 99bf25b); shipped output unchanged | Each switch judged on 36 held-out copies |
| R4 | Envelope (V2 speed and volume sigmas) learned per flight instead of fixed values chosen on Machine Hall (`LEARN_ON`) | **Done (verified): OFF** by the pre-registered rule (17 Nov, rule at c1769cb): held-out APE 3.739 m vs floor 3.748 (passes), clean +6.7 % (fails); shipped output unchanged | Held-out mean APE <= never-moving floor; clean no worse |
| R5 | Rotor drag (V3): drag rule v2 stages A and B as pre-registered (c1b594c) on V1_01..03; build V3 only if stage A passes | **Done (verified): NO-GO, V3 not built.** Stage A re-run 17 Nov reproduces the Step B result exactly (1 of 3 sequences pass, 2 needed); stage B not reached | Stage A on 2 of 3 Vicon Room 1 sequences |
| R6 | Batch forward-backward smoother at the 0.25 s tick (`SMOOTH_ON`, Step E code in the reference) | **Done (verified): ON** by the pre-registered rule (18 Nov, rule at 8da205d): held-out APE -7.8 %, gap RMSE -10.7 %, clean -2.7 %; ported to `pathfinder.py`, bit-identical (max difference 0.0 on real files) | Held-out APE and gap RMSE improve >= 2 %; clean not worse |
| R7 | TUM-VI: loader check and baseline; platform detector (multirotor / hand-held) from the accelerometer spectrum; hand-held envelope (`PLATFORM_ON`); V5 walking rhythm (time-boxed) | **Done (verified): ON** by the pre-registered rule (18 Nov, rule at 4064b3f): detector right on all 328 non-final files (multirotor >= 5.38, hand-held <= 0.160, threshold 1.0); held-out room3/4 seeds 7-9 APE 1.994 -> 1.127 m (-43.5 %; floor 1.164), gap -38.2 %, both rooms, clean -3.4 %; EuRoC byte-identical. V1 hand-held: not changed. V5 (19 Nov): stopped at feasibility on room1/2, **off, not built** (direction from the acceleration axis at chance even with ground-truth attitude) | Detector right everywhere; held-out APE -10 %, gap -5 %, both rooms; clean not worse > 5 % |
| F | Filter fixes from the 16-17 Nov reviews: gyro-bias cap on every still test (`BGCAP_ON`), covariance reset after injection (`RESET_ON`), refresh of the cached previous sample (`REFRESH_ON`), fallback velocity uncertainty (`P0V_ON`); four switches | **Done** (17 Nov): BGCAP, P0V, REFRESH pass and ship on; RESET fails (reading a APE +1.8 %) and ships off. Held-out mean APE 4.972 -> 4.962 m; floor 3.745 m | Each switch judged on 36 fresh held-out copies (seeds 4-6) by the no-harm rule |
| L1 | Positions scaled about their centroid, alpha per gyro-noise class (`SHRINK_ON`); null floor = the estimate reversed in time (`eval_euroc.py --reverse`) | **Done (verified): OFF** by the pre-registered rule (18 Nov, rule at d56c875): both arms improve the mean objective (reading a -49.5 %, reading b -23.9 %) but fail sequence consistency (4 and 3 of 6); LO also loses to its reversed output. Shipped output unchanged | Each arm judged on 36 fresh held-out copies (seeds 7-9) |
| Lean | Switched-off experiments moved from `pathfinder.py` to `tools/pathfinder_lab.py` (not shipped) to cut compile memory | **Done (verified)** 18 Nov: output byte-identical on all 144 real inputs; no-bytecode heap 6,055 -> 4,935 KB (3.14), 6,431 -> 6,309 KB (3.13); gate PASS | `tests/test_lab.py`; gates PASS |
| PRD v2 | PRD v2 (18 Nov) in the repo (`Docs/PRD.md`): levers L1 shrinkage, L2 slow gravity alignment, L3 blind window, L4 hardening, L5 TUM-VI; paired, sequence-level judging (rules G and H); work split Claude Code / Antigravity / ChatGPT. Fallback zip frozen | **Done (verified)** 18 Nov (K0): `dist/vortex_v0.9.zip` from `main` da14417, eval input `data/official/MH_03_medium_b_s1` (placeholder), 26,106 rows, 3.19 ms per IMU-s, heap 1,013 KB; `verify` PASS on Win 3.13 and 3.14; SHA-256 0e558440a397ef4b78426cc471ac8d3fd17f8c658b28a6cd40aeb5a3ba555d6b | Zip verified; never deleted |
| NUMBERS (K6, early) | `tools/make_numbers.py` -> `Docs/NUMBERS.md` + `Docs/numbers/numbers.json`: every number the deck, script and README may quote, as `key | value | source tag | date`, generated from committed result, TUM-VI, budget and pytest files. Keys are stable (ChatGPT's `[[N:key]]`); when the shipped build changes, `SOURCES` in the script points at the new tags | **Done (verified)** 18 Nov: headline keys reproduce the Step F verdict to the digit (held-out 4.962 vs floor 3.745 m; reading a 6.181, b 3.744; gap 5.036; blind 6.992). Budget from a fresh lean run (`lean-win-py314-mh01-b-s1`) | `tests/test_numbers.py` (3); `--check` in the suite |
| L2 | Slow gravity alignment over a 4 s window with a lag model, weighted by a gyro noise meter (`TILT_ON`) | **Done (verified): ON** by rule G2 (18 Nov, rule at 3e2646e, seeds 16-18, base with the Step 6 smoother): all 13 checks pass, held-out APE 4.922 -> 3.575 m (floor 3.746), DiD null 1.347 vs 1.187 m. Rule G (seeds 10-12) had failed its level null; G2 was **written after seeing that: weaker evidence, same 6 flights** | Rule G2 on 36 fresh held-out copies + TUM-VI room3/4 |

## Open questions (Q1 to Q5 are in the email drafted for prism@samsung.com on 15 Nov)

| Q | Question | Owner |
|---|---|---|
| Q1 | Final deadline: 18 Nov or 22 Nov; Google Form link. **Closed (FAQ, 17 Nov): 22 Nov 2026**; the form link comes in the announcements channel | Arnav |
| Q2 | Track 3 student package: degradation script, sample data, evaluator. **Mostly answered 17 Nov**: `degrade_imu.py` received; sample data = any EuRoC/TUM-VI sequence; the evaluator is evo with SE(3) alignment (not shipped) | Arnav |
| Q3 | Are waypoint positions or times given as input? **Closed (FAQ): no**, hidden, scoring only | Arnav |
| Q4 | Is 8 MB peak RAM measured for the whole process or the algorithm only? Is `main.cpp` accepted? **Closed (FAQ, 17 Nov): algorithm / heap level, not process RSS; Python only, `main.cpp` not accepted.** The history (RSS floor 8.4 to 9.7 MB, bytecode stub, C core at 2.7 / 4.8 MB) is in steps 2e, 9a and 9b below | Arnav |
| Q5 | Demo video length: 2 to 3, 3, or 5 minutes? **Closed (FAQ): 2 to 3 minutes, strict maximum 3** | Arnav |
| Q6 | Is the rotor-drag signal visible in EuRoC's IMU (offline fit on clean MH_01)? **Answered 16 Nov: NO-GO under the pre-registered rule** (whole sequence; the hand-carried start breaks it). Exploratory in-flight fit: visible, k 0.14 to 0.25 /s. See `Docs/DRAG.md`. **Rule v2** pre-registered 16 Nov (commit c1b594c): **NO-GO on Vicon Room 1, 17 Nov** (only V1_02 passes; second axis fails on V1_01 and V1_03). Closed | Arnav + Claude, before 20 Nov |
| Q7 | May future samples refine earlier poses (smoothing)? **Closed (FAQ): yes**, offline batch / non-causal processing is allowed within 8 MB | - |
| Q8 | Which alignment does evo use? **Closed (FAQ): SE(3) Umeyama**, then ATE | - |
| Q9 | Column order fed to `degrade_imu.py`: raw EuRoC (gyro first; the script then puts accelerometer-sized faults on the gyro) or reordered accel first? **Open**; both readings are built and tested (Step 2) | Arnav |

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

Which alignment the organisers use with evo was unknown here; the FAQ (17 Nov) settles it: SE(3) Umeyama.

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


## Step 6e: calibration when the noise starts before the still run (16 Nov 2026, branch `track3/step6e-calib`)

**Problem** (found in step 6d). The still test uses fixed per-bin std thresholds (STILL_GYRO_STD 0.02
rad/s, STILL_ACC_STD 0.1 m/s^2). MH_02's only still run is short (26.5..29.75 s); with the added noise
starting at 10 s its bins exceed the accelerometer threshold, no run is found and calibration falls back
to the first second (19 of 20 degraded tuning copies): gyro bias and tilt are then not calibrated.

**Switch** `CAL_NOISE_ON` (`vortex/core/strapdown.py`, mirrored in `main.py`). Only when the strict test
finds no run of MIN_STILL_S: the calibration horizon is scanned again for each bin's second
differences x[k] - 2 x[k-1] + x[k-2] (variance 6 sigma^2 for white noise; smooth motion nearly cancels).
The still test is repeated with each channel's white-noise variance removed before the same std
thresholds, and the steady test's tolerances are widened by 3 standard deviations of the difference of
two bin means under that noise. Stuck and |f| tests are unchanged. No new tuned constant. When the strict
test finds a run nothing changes, so clean MH_01..05 output cannot change; `main.py` pays for the second
scan only in the fallback case. Risk: rotor vibration is not white (its second differences are larger),
so a steady hover could pass the denoised test; it is used only where the alternative is the first-second
fallback.

**Tuning (MH_01/02 only;** scratch study, reference estimator, 20 degraded copies per sequence, seeds
100..119, alignment from the clean run, ground truth for scoring only):

| | Off | On |
|---|---|---|
| MH_02 fallbacks | 19 / 20 | 0 / 20 |
| MH_02 mean APE (max) m | 6.250 (8.527) | 4.570 (5.969) |
| MH_01 mean APE m (strict test always finds a run) | 4.236 | 4.236 |
| Clean MH_01 / MH_02 APE m | 3.911 / 3.846 | identical |

Every MH_02 copy that fell back improved; the run found was the true rest (ground-truth 90th-percentile
speed 0.003..0.004 m/s). A first version without the widened steady test found the same runs on MH_02
but broke a synthetic noisy rest into 1 s pieces (test), so the widening was added before any held-out run.

**Decision rule, committed before the held-out copies exist.** Held-out: MH_03..05 x seeds 13..15
(default levels) and x seeds 16..18 with `--healthy-s 2` (noise from 2 s, so it covers their early still
runs too), 18 copies, scored with `main.py`. `CAL_NOISE_ON` ships on only if (a) clean MH_01..05 output is
byte-identical, (b) mean APE over the 18 copies is not worse, and (c) no single copy's APE is worse by
more than 10 %. Reported as well: how many copies fell back with it off, and the ground-truth speed in
the runs it chose (diagnostic only).

**Outcome** (16 Nov; rule committed at f68ee61; `main.py` with `--set CAL_NOISE_ON=...`; tags
`step6e-H-off`, `step6e-H-on`):

| Held-out check | Result | Rule |
|---|---|---|
| (a) clean MH_01..05 output, on vs off | byte-identical | passes |
| (b) 18 new copies, mean APE (given) | 6.3677 -> 6.3421 m | not worse: passes |
| (c) worst single copy | +0.0 % (no copy worse) | <= +10 %: passes |
| Copies that fell back with it off | 3: MH_03_s13, MH_03_s16, MH_04_s18 | diagnostic |
| Recovered | MH_04_s18: run 12.5..14.5 s, ground-truth speed 0.003 m/s, APE 7.209 -> 6.749 m | diagnostic |
| Not recovered | MH_03_s13, s16: a 2 s dropout covers MH_03's whole 2 s still run; falling back is right | diagnostic |

**Shipped: CAL_NOISE_ON = True.** All 60 degraded copies with `main.py` (tag `step6e-deg`, contract PASS on
all) against step 6d: only four runs change, all better: MH_02_s1 5.682 -> 3.982 m, s2 6.034 -> 4.221 m,
s3 5.300 -> 4.083 m (tuning sequence; these copies also fell back before), MH_04_s18 7.209 -> 6.749 m.
MH_01/02 mean APE 5.146 -> 4.358 m; MH_03..05 (54 copies) 6.438 -> 6.430 m. Clean (tag `step6e`):
identical to step 6d (largest difference 0.0).

| Item | Result | Where |
|---|---|---|
| `pytest` | 188 passed (183 + 3 reference + 2 equivalence readings) | Windows, Python 3.14.7 |
| Budget, `python -S main.py` (commit f40d3ea) | 10.28 us/row, 15.44 MB peak RSS (Win 3.14); 10.42, 15.05 MB (Win 3.13); 9.44, 13.33 MB (Linux 3.12); MH_01 9.70, 15.95 MB; degraded MH_01_s1 9.23, 15.94 MB. The synthetic input has no still run, so it now pays for the second 60 s scan: about +1.2 us/row and +65 KB tracemalloc (Linux 8.20 -> 9.44, Win 3.13 9.14 -> 10.42). Peak RSS +0.2..0.3 MB on MH_01 even without the scan (larger source). Gate PASS on all | `Docs/BUDGET.md` |

Not checked: TUM-VI (no data); a hover with rotor vibration passing the denoised test (no such case
occurred: every recovered run was a true rest by ground truth); V1 stillness (ZUPT) in the filter still
uses the strict test, so with heavy noise it fires less (matters for walking, TUM-VI).


## Step 7b: denoised stillness witness (V1) (16 Nov 2026, branch `track3/step7b-zupt`)

**Problem.** V1 (ZUPT + gyro bias) fires only when two ticks pass the strict still test. With added
noise above STILL_ACC_STD the rests are not seen: degraded MH_01 (healthy 10 s) keeps about 10 of its 25
clean ZUPT ticks, degraded MH_02 about 0 of 6.

**Switch** `ZUPT_DEN_ON` (reference only, `vortex/core/witness.py`; not in `main.py`). V1 also fires when
ZUPT_DEN_BINS = 4 ticks in a row (1 s, = MIN_STILL_S) pass step 6e's denoised still test and are pairwise
steady under the denoised tolerance. The strict condition is unchanged.

**Hazard found first** (MH_01/02 only, ground truth for diagnosis): removing the white-noise variance
also removes rotor vibration, the signature that tells steady flight from rest. Single pairs of ticks
passed the denoised test in flight at 0.55..0.79 m/s (4 runs over 2 x 20 degraded copies), all exactly 2
ticks long; true rests gave runs of 2 to 12+ ticks. Hence the run length of 4.

**Tuning (MH_01/02;** reference estimator, alignment from each setting's clean run):

| Set | Off | On |
|---|---|---|
| Clean MH_01 / MH_02 APE m | 3.9106 / 3.8459 | 3.9106 / 3.8988 (+1.4 %) |
| Degraded, healthy 10 s, seeds 100..119: MH_01 / MH_02 mean APE m | 4.236 / 4.570 | 4.225 / 4.413 |
| Degraded, healthy 2 s, seeds 120..129: MH_01 / MH_02 mean APE m | 4.220 / 4.607 | 4.145 / 4.618 |
| False ZUPT ticks (ground-truth speed > 0.1 m/s), all 60 copies | 0 | 0 |

The effect on MH is small and mixed (-3.4 % .. +1.4 %): on these drone sequences V1 only matters at the
ground rest. It would matter for standing periods in walking data (TUM-VI, not downloaded).

**Decision rule, committed before any held-out run.** A gain is required, because the switch costs
per-row work in `main.py`'s hot loop and carries the in-flight hazard. Held-out: clean MH_03..05 and,
generated in memory after this commit, MH_03..05 x seeds 19..21 (healthy 10 s) and x seeds 22..24
(healthy 2 s), 18 copies, reference estimator. `ZUPT_DEN_ON` is ported to `main.py` and ships on only if
(a) mean APE over the 18 copies improves by at least 2 %, (b) clean MH_03..05 mean APE is not worse, and
(c) no ZUPT tick falls where ground-truth speed exceeds 0.1 m/s. Otherwise it stays off, in the reference
only, until TUM-VI data exists.

**Outcome** (16 Nov; rule committed at 1ac2f45; reference estimator, `python tools/zupt_eval.py
MH_03_medium,MH_04_difficult,MH_05_difficult 19,20,21 10 OUT` and `... 22,23,24 2 OUT`; 18 held-out copies):

| Check | Off | On | Rule |
|---|---|---|---|
| (a) mean APE, 18 copies (healthy 10 s and 2 s) | 6.482 m | 6.496 m (+0.2 %) | >= 2 % better: **fails** |
| (b) clean MH_03..05 mean APE | 5.485 m | 5.466 m | not worse: passes |
| (c) ZUPT ticks at ground-truth speed > 0.1 m/s | 0 | 0 | none: passes |

**ZUPT_DEN_ON stays off and is not ported to `main.py`.** On these drone sequences V1 matters only at the
ground rest, and recovering those ticks under noise does not move APE. Revisit with TUM-VI (walking, with
standing periods). `main.py` and every shipped result are unchanged by this step.


## Step 8b: per-row confidence (W6) (16 Nov 2026, branch `track3/step8b-confidence`)

**What it is.** The output format has no confidence column, so W6 is an error bar for reporting and the
jury demo only, never read by the estimator. `witness.row_sigma`: the 3D position sigma of each row, from
the last tick's position covariance carried forward on its velocity covariance (pp + 2 pv d + vv d^2),
plus, while the IMU is missing, the dropout model's velocity change (as in `gap_inflate`). Rows before
the anchor have none. `estimate(sig=[])` collects it; `tools/coverage.py` scores it against ground truth
(scoring only) and writes `Docs/COVERAGE.md`.

**Result on the tuning set** (`python tools/coverage.py --tag step8b-tune --seqs MH_01_easy,MH_02_easy
--seeds 100,101,102,103,104,105`; clean + 6 degraded copies each, 344,494 rows):

| Phase | Median sigma m | Median error m | Spearman(sigma, error) |
|---|---|---|---|
| all | 2.08 | 3.56 | -0.07 |
| clean | 2.05 | 3.38 | -0.02 |
| degraded | 2.08 | 3.60 | -0.09 |
| dropout | 2.48 | 3.26 | -0.15 |
| blind | 3.52 | 3.69 | -0.34 |

The sigma is nearly constant (the volume envelope V2P holds the position covariance near its 5 m / 2 m
sigmas) and does not rank the rows by error; it even falls as the error rises inside the blind window.
The k that puts 68 % / 95 % of the rows inside k x sigma is 2.18 / 9.02: a heavy tail, which a constant
bound describes as well. **Decision: no calibrated per-row confidence is claimed.** The tool stays for
the record and for a later attempt; no held-out run was spent, since the tuning result already rules it
out. What dominates the error is the trajectory's offset from the never-moving level (step 7a), which
nothing in the IMU-only filter observes.


## Step 9a: compile memory (16 Nov 2026, branch `track3/step9-bundle`)

**Problem.** `python -S main.py` compiles its own ~1,000-line source on every run. Measured before
any change (scratch probe, `tools/measure_floor.run_measured`, MH_01, 7 runs, median peak RSS):

| | Win 3.14 | Win 3.13 |
|---|---|---|
| `python -S -c "import math, array"` (floor) | 10.72 MB | 10.44 MB |
| compile `main.py` only | 15.55 MB | 15.27 MB |
| import the same code from a cached `.pyc` only | 10.91 MB | 10.57 MB |
| run `main.py` from source | 16.00 MB | 15.64 MB |
| run a 3-line stub importing the same code from a `.pyc` | 12.05 MB | 11.23 MB |

Compiling costs about 4.8 MB; loading the compiled code costs 0.2 MB. A script given on the command
line is always compiled from source, but an imported module is loaded from `__pycache__` when a
matching `.pyc` is there.

**Change.** The estimator moves unchanged to `pathfinder.py`; `main.py` becomes a stub (imports `sys`
only) that puts its own folder on `sys.path`, imports `pathfinder` and calls `pathfinder.main`. The
bundle ships hash-checked `.pyc` files (valid whatever the file times after unzipping) for each Python
we can build them with; without a matching one, Python compiles the source as before.

**Rule (written before the change).** Ship the stub only if all hold:
1. Output byte-identical to the current `main.py` on clean MH_01..05 and every `data/degraded` copy.
2. Peak RSS of the MH_01 run with a matching `.pyc` at least 2 MB lower than from source, on Win
   3.14, Win 3.13 and WSL2 Linux 3.12.
3. Without a matching `.pyc` (cold, `-X pycache_prefix` on an empty folder), peak RSS at most 0.5 MB
   above the current `main.py`.
4. `benchmark.py --gate` passes on all three.

This does not reach 8 MB: the interpreter with `math` and `array` alone peaks at 9.3 to 10.7 MB
(`Docs/FLOOR.md`). Whether a C core is needed still depends on Q4.

**Outcome: all four hold, the stub ships** (commit fd89e4a).
1. Outputs: sha256 of all 65 outputs (clean MH_01..05 + 60 degraded copies, Win 3.14) identical for
   the old `main.py`, the stub and `pathfinder.py` run directly.
2. and 3. MH_01, 7 runs, median peak RSS, run from the staged bundle (`dist/stage`, bytecode built
   by `tools/make_bundle.py stage`):

| | Win 3.14 | Win 3.13 | WSL2 Linux 3.12 |
|---|---|---|---|
| before: `pathfinder.py` compiled from source | 15.76 MB | 15.63 MB | 13.79 MB |
| stub, matching bytecode | **11.95 MB** (-3.81) | **11.83 MB** (-3.80) | **10.27 MB** (-3.52) |
| stub, no cached bytecode | 15.75 MB (-0.01) | 15.28 MB (-0.36) | 13.94 MB (+0.15) |

4. `benchmark.py --runs 15 --gate` at fd89e4a: PASS on Win 3.14, Win 3.13, WSL2 3.12 (synthetic),
   Win 3.14 MH_01 and degraded MH_01_s1 (`Docs/BUDGET.md`). Timing is unchanged within noise: 21
   interleaved runs on MH_01 (Win 3.14) gave 9.44 us/row for the stub, 9.70 from source.

| Run (`python -S`, peak RSS) | Stub, bytecode | Stub, no cached bytecode | `pathfinder.py` from source |
|---|---|---|---|
| Win 3.14, synthetic | 11.46 MB | 15.85 MB | 15.42 MB |
| Win 3.13, synthetic | 11.04 MB | 15.33 MB | 15.06 MB |
| WSL2 3.12, synthetic | 10.07 MB | 13.07 MB | 13.36 MB |
| Win 3.14, MH_01 | 11.80 MB | 15.79 MB | 15.87 MB |
| Win 3.14, degraded MH_01_s1 | 12.00 MB | 15.77 MB | 15.98 MB |

**Found on the way.** The Windows shell these runs used sets `PYTHONDONTWRITEBYTECODE=1` (not checked
whether Arnav's own terminals do), so Python there never writes a cache: a stub alone would gain
nothing on a second run. An evaluator's machine could be set up the same way. That is why the bundle ships
the `.pyc` files (reading them is unaffected by that variable) and `benchmark.py` writes them
explicitly. Under `-I` the variable is ignored, which is why the tests did not show it.

**Bundle.** `tools/make_bundle.py stage` (once per Python), `zip --name NAME`, `verify`. The zip
(`NAME/`: `main.py`, `pathfinder.py`, `__pycache__/pathfinder.cpython-312/313/314.pyc`, `README.md`,
`Dockerfile`, `LICENSE`, `MANIFEST.txt`) passed `verify` on Win 3.14, Win 3.13 and WSL2 3.12: output
identical to `pathfinder.py`, checker PASS, estimator loaded from the shipped bytecode on the first
run. The Dockerfile (`python:3.12.7-slim-bookworm`, bytecode compiled at build time) was built from
`dist/stage` with Docker Desktop 29.6.2 (image 45 MB) and run on all 65 inputs (clean MH_01..05 + 60
degraded copies, input mounted read-only): every output's sha256 equals the pre-change baseline, and
`python -v` in the container shows `pathfinder` loaded from `/app/__pycache__/pathfinder.cpython-312.pyc`.
Peak RSS inside the container was not measured (the WSL2 3.12 numbers above are the same Python
version on Linux).


## Step 9b: C core under 8 MB (16 Nov 2026, branch `track3/step9b-ccore`)

**Why.** Q4 got no answer, so we assume the strict reading: 8 MB of whole-process peak RSS. CPython
cannot meet it (bare interpreter 8.4 to 9.7 MB, `Docs/FLOOR.md`). The PRD (slide 17) allows `main.py`
or `main.cpp`, and fixes the rules for a C core: C-style C++, standard library only, no heap allocation
after start-up, double precision, `-O2`, no `-ffast-math`, equivalence-tested against the Python. The
C++ parse + write floor is 4.3 MB (Windows).

**Change.** `main.cpp`: a line-by-line port of `pathfinder.py` with the shipped switch settings (the
switches that are off are not ported; a test checks that the Python settings match what the port
implements). Same passes, same row rules, same arithmetic order. `main.py` stays as the Python
submission and the fallback.

**Rule (written before the port).** `main.cpp` becomes the recommended entry point only if all hold:
1. On clean MH_01..05 and every `data/degraded` copy, the full-precision outputs of `main.cpp` and
   `pathfinder.py` agree within the equivalence criterion (position < 1e-6 m, quaternion < 1e-7 on
   every row), and every output passes `vortex.check_output`; the messy-input and degraded synthetic
   cases of `tests/test_main.py` give identical submission-format bytes.
2. Peak RSS <= 8 MB on Windows and on Linux, on MH_01, on the degraded MH_01_s1 copy and on a 15 min
   SYNTHETIC file (memory must not grow with length).
3. Process time per row not above `python -S main.py`'s on the same machine.
Known, accepted differences (inputs EuRoC/TUM-VI never contain): timestamps above 9.2e18 ns are copied
to the output but not integrated; lines longer than 64 KB are cut at 64 KB.

**Outcome: all three hold; `main.cpp` is the recommended entry point** (commit ba79c15).
1. Equivalence, full precision, all 65 inputs (clean MH_01..05 + 60 degraded copies):
   - Linux (WSL2 Ubuntu 24.04, g++ 13.3, Python 3.12.3): **bit-identical**, max difference 0.
   - Windows (MinGW g++ 13.2 UCRT `-static`, Python 3.14.7): max 6.1e-13 m position, 1.2e-14
     quaternion (the two C maths libraries differ in the last bit of sin/cos); output files
     byte-identical on all 65.
   - `tests/test_ccore.py` (18 tests, Windows): every synthetic scenario of the equivalence tests,
     identical submission bytes; the number routines against Python's own `float()` and `%`-formatting
     on 30,074 fields and 30,018 doubles (0 mismatches, also on Linux).
2. Peak RSS, median of 9 runs:

| Input | Linux C core | Linux `python -S main.py` | Windows C core | Windows `python -S main.py` |
|---|---|---|---|---|
| MH_01 | **2.71 MB** | 10.26 MB | **4.75 MB** | 11.88 MB |
| degraded MH_01_s1 | **2.74 MB** | 10.26 MB | **4.75 MB** | 11.92 MB |
| SYNTHETIC 15 min (180,000 rows) | **2.38 MB** | 10.07 MB | **4.44 MB** | 11.46 MB |

3. Time: 1.1 to 1.6 us per row on Windows (Python 8.3 to 11.0), 1.1 to 5.1 on Linux reading from
   the slow `/mnt/c` mount (Python 7.2 to 13.9).

`benchmark.py --runs 15 --gate --cbin` at ba79c15 (gate now also requires the C core within 8 MB, within
50 us per row and byte-identical to `python -S main.py`): PASS on all six (`Docs/BUDGET.md`):

| Run | C core us/row | C core peak RSS | Same bytes as main.py | `python -S main.py` peak RSS |
|---|---|---|---|---|
| Win 3.14, synthetic | 1.66 | 4.44 MB | yes | 11.46 MB |
| Win 3.13, synthetic | 1.55 | 4.45 MB | yes | 11.07 MB |
| WSL2 3.12, synthetic | 1.21 | 2.38 MB | yes | 10.07 MB |
| Win 3.14, MH_01 | 1.28 | 4.75 MB | yes | 11.80 MB |
| Win 3.14, degraded MH_01_s1 | 1.32 | 4.75 MB | yes | 12.00 MB |
| WSL2 3.12, MH_01 (input on `/mnt/c`) | 3.98 | 2.70 MB | yes | 10.23 MB |

**What it took.** The first port ran at about 10 us per row on Windows: the Windows C library's
`strtod` and `printf` cost about 5 and 4 us per row. `main.cpp` now parses and formats numbers itself
with 128-bit integer arithmetic, rounding correctly (to nearest, ties to even, on the exact value) as
Python does, and hands anything outside that range back to the C library. Without a 128-bit integer
type (MSVC) it always uses the C library.

**Bundle (PRD layout).** `tools/make_bundle.py`: `stage` (per Python), `eval IMU.csv --cbin PATH`
(writes `estimated_trajectory.txt` and `metadata.json`: runtime, peak RSS, machine), `zip`, `verify`
(also builds `src/main.cpp` with g++ and requires the same bytes). Verified on Win 3.14, Win 3.13 and
WSL2 3.12. The evaluation files in it are MH_01 placeholders until the organisers' input exists.
Dockerfiles (repository root and `bundle/`) build the C core in a g++ stage and run it; not built
yet (needs the Debian g++ packages downloaded inside the build).



## Step A: new data, baselines first (17 Nov 2026, branch `track3/stepA-baselines`; no estimator change)

**Data on disk** (A.1, checked 17 Nov): EuRoC MH_01..05 and **V1_01..03** (Vicon Room 1, extracted 17 Nov
from `vicon_room1.zip`: `mav0/imu0` and `mav0/state_groundtruth_estimate0` only). **Missing: V2_01..03
(Vicon Room 2) and TUM-VI room1..4.** A.2 (TUM-VI loader) and the TUM-VI half of A.3 and A.4 are blocked.

| Sequence | IMU rows | Length | IMU rate | Ground-truth rows | Ground truth covers |
|---|---|---|---|---|---|
| V1_01_easy | 29,120 | 145.6 s | 200 Hz (dt 5.000 ms, no gaps) | 28,712 | 1.04..144.60 s |
| V1_02_medium | 17,100 | 85.5 s | 200 Hz | 16,702 | 1.00..84.50 s |
| V1_03_difficult | 21,500 | 107.5 s | 200 Hz | 20,932 | 1.83..106.49 s |

Same IMU header and units as MH (`#timestamp [ns]`, gyro rad/s, accel m/s^2), same ground-truth layout.

**Tooling.** `tools/eval_euroc.py`: `--cbin PATH` runs the C core instead of `python -S main.py`; clean runs
now also record APE under the `none` and `origin` alignments (new table in `Docs/RESULTS.md`); **V2_\* is
skipped by default and refused when named unless `--final` is given** (final test set). Tests:
`tests/test_eval_euroc.py`.

**Degraded copies** (existing seeds scheme, default placeholder levels, made 17 Nov): V1_01..03 x seeds
1..3 (NaN failure) and seeds 7 (NaN), 8 (`--failure-mode zero`), 9 (`--failure-mode stuck`): 18 copies.

**Baseline: shipped estimator (main.py at ea4258c = main.cpp), unchanged.** Tags `stepA-v1-py`,
`stepA-v1-c`, `stepA-v1-floor`, `stepA-v1-deg-*`. Every later step is judged against these numbers.

Clean V1, APE RMSE m under each alignment / RPE 1 s m:

| Sequence | Estimator none / origin / SE3 / Sim3 | RPE 1 s | Never-moving floor none / origin / SE3 | Floor RPE 1 s |
|---|---|---|---|---|
| V1_01_easy | 2.82 / 2.38 / 1.77 / 1.77 | 0.409 | 2.38 / 2.70 / 1.85 | 0.439 |
| V1_02_medium | 3.55 / 2.95 / 1.77 / 1.71 | 0.669 | 2.60 / 2.16 / 1.78 | 0.964 |
| V1_03_difficult | 2.93 / 2.28 / 1.55 / 1.51 | 0.469 | 2.50 / 2.21 / 1.57 | 0.716 |
| **Mean** | 3.10 / 2.53 / **1.70** / 1.66 | **0.516** | 2.49 / 2.36 / **1.73** | **0.706** |

Degraded V1 (APE with the alignment fitted on the same main's clean run), means:

| Copies | Estimator APE / RPE 1 s / dropout growth / blind growth / blind RMSE m | Floor APE / RPE 1 s / dropout growth / blind growth / blind RMSE m |
|---|---|---|
| seeds 1..3 (9) | 2.924 / 0.638 / 1.107 / 1.259 / 3.758 | 1.759 / 0.717 / 1.098 / 1.203 / 1.327 |
| seeds 7..9, nan/zero/stuck (9) | 3.160 / 0.638 / 1.141 / 1.480 / 4.430 | 1.759 / 0.717 / 1.082 / 1.203 / 1.327 |
| all 18 | **3.042** / 0.638 / 1.124 / 1.369 / 4.094 (worst APE 6.77, V1_03_s9) | **1.759** / 0.717 / 1.090 / 1.203 / 1.327 |

**Reading.** Vicon Room 1 is a small volume (the floor's SE3 APE is only 1.6..1.9 m, against 4.3..6.9 m on
MH). Clean, the estimator is level with standing still on APE (1.70 vs 1.73 m) and better on RPE 1 s
(0.52 vs 0.71 m). Degraded, it is clearly **worse than the floor** (APE 3.04 vs 1.76 m; blind RMSE 4.09 vs
1.33 m): the error already present when the IMU fails, not the 5 s growth, dominates (as on MH in step
8a). Under the `none` and `origin` alignments the estimator is worse than the floor on all three
sequences. This is the gap Step B has to close.

**Output contract and equivalence.** `python -S main.py` and the C core (MinGW g++ 13.2, `-static`) give
byte-identical output on all 86 inputs (MH_01..05 + V1_01..03 clean, 78 degraded copies), and every C
output passes `vortex.check_output` (scratch script, 17 Nov).

| Item | Result | Where |
|---|---|---|
| `pytest` | 227 passed (224 + 3 eval selection/runner) | Windows, Python 3.14.7 |
| `benchmark.py --runs 15 --gate --allow-rss --cbin` | PASS on all five runs. C core: Win 3.14 synthetic 1.51 us/row, 4.45 MiB; V1_01 1.81 us/row, 4.45 MiB; degraded V1_02_s9 2.18 us/row, 4.45 MiB; WSL2 synthetic 1.43 us/row, 2.40 MiB; WSL2 V1_01 14.72 us/row (input read through the slow `/mnt/c` mount), 2.40 MiB. Output identical to main.py on all five. `python -S main.py` peaks at 10.1..11.5 MiB (above 8 MB, as known; hence `--allow-rss`) | `Docs/BUDGET.md` |

Not checked: TUM-VI (not downloaded), so the loader check, long-file memory on TUM-VI and the
hand-held baseline are open; the Linux C core equivalence on the V1 inputs (only the benchmark's two
Linux runs compared bytes); peak RSS on a TUM-VI-length file (the 15 min synthetic check of step 9b
stands).


## Step B: rotor drag (V3), stage A of rule v2 (17 Nov 2026, branch `track3/stepB-drag`)

Run once, as pre-registered (rule commit c1b594c; `tools/drag_fit.py` and its imports unchanged since):
`python tools/drag_fit.py --rule v2 data/euroc/V1_01_easy data/euroc/V1_02_medium data/euroc/V1_03_difficult`.
Each axis passes if R^2 with the fixed k = 0.20 /s is >= 0.5 and the free k is within 30 % of 0.20.

| Sequence | Airborne s | Axis a: k free / R^2 fixed k | Axis b: k free / R^2 fixed k | Sequence |
|---|---|---|---|---|
| V1_01_easy | 144 | 0.224 / 0.542 pass | 0.083 / -0.049 **fail** | fail |
| V1_02_medium | 84 | 0.201 / 0.668 pass | 0.175 / 0.784 pass | pass |
| V1_03_difficult | 100 | 0.194 / 0.630 pass | 0.138 / 0.432 **fail** | fail |

**Stage A: NO-GO** (1 of 3 sequences pass; the rule needs 2). Under the rule V3 is dropped: it is not
built, so B.2..B.5 (filter V3, tuning, stage B, no-harm check, ablation) are not run. Axis a (the
in-plane axis) holds on all three, with k 0.19 to 0.22 /s; axis b (the second thrust-perpendicular
axis) does not carry the fixed-k relation on V1_01 or V1_03. Nothing was explored or tuned after the
run; any rule v3 would need held-out data never seen (Vicon Room 2 is reserved as the final test set).
Per-sequence fits and plots: `Docs/DRAG.md`, `Docs/drag/v2_V1_0*.{json,svg}`.

No estimator, `main.py` or `main.cpp` change: output and budget are those of step A (`Docs/BUDGET.md`
`stepA-*`).


## Step 1 (FAQ re-plan): Python only, heap-level memory gate (17 Nov 2026, branch `track3/step1-faq`)

**Why.** The organisers' FAQ (17 Nov, section "Organisers' FAQ" at the top) rejects `main.cpp` and
measures the 8 MB at algorithm / heap level. No estimator change in this step: `pathfinder.py` and the
reference are untouched, so every accuracy number stays as it was.

**Changes.**
- `tools/make_bundle.py`: the zip carries `src/main.py`, `src/pathfinder.py`, bytecode, `README.md`,
  `Dockerfile`, `LICENSE`, `MANIFEST.txt` and the evaluation files; `main.cpp` is no longer shipped
  (a stage or zip that still holds it is refused); `eval` measures `python -S src/main.py` only and
  writes the whole-run heap peak to `metadata.json` (RSS kept, labelled as the record only).
- `Dockerfile`, `bundle/Dockerfile`: Python only (`python:3.12.7-slim-bookworm`, bytecode compiled at
  build time, entry `python -S /app/main.py`). The C-core Dockerfile is kept as `Dockerfile.ccore`.
- `benchmark.py --gate`: memory is gated on the heap. Two tracemalloc readings, the larger gated at the
  4 MB design target: `pathfinder.run` in-process, and the whole `python -S main.py` run in a fresh
  interpreter with tracing started before `main.py` (import from the shipped bytecode included). A
  third reading, the whole run with no cached bytecode, is held to the 8 MB limit only. Peak RSS is
  still measured and shown, not gated. `--cbin` still times the C core for the record; it is not gated.
- `main.cpp`, `tests/test_ccore.py`, `tests/ccore_selftest.cpp` and every C-core result stay in the
  repository as a recorded experiment.

**Found.** Compiling `pathfinder.py` happens on the traced heap: without matching bytecode the whole-run
heap peak is 4.40 MB (Win 3.14) and 6.31 MB (Win 3.13), against 0.76 to 1.19 MB from the shipped
bytecode. Under 8 MB either way, but close on 3.13. If the evaluator's Python has no matching `.pyc`
and traces from start-up, this is the number it sees. Splitting the estimator into smaller modules
should lower the compile peak (not measured).

| Run (`python -S benchmark.py --runs 15 --gate`) | us per row | ms per IMU-s | Heap KB in-process / whole run / no bytecode | Peak RSS MiB (not gated) | Gate |
|---|---|---|---|---|---|
| Win 3.14, SYNTHETIC 36,000 rows | 13.47 | 2.69 | 289 / 763 / 4,400 | 11.52 | PASS |
| Win 3.14, MH_01 | 11.69 | 2.34 | 587 / 1,061 / 4,400 | 11.86 | PASS |
| Win 3.13, SYNTHETIC 36,000 rows | 9.40 | 1.88 | 234 / 1,190 / 6,310 | 11.10 | PASS |

The 3.14 runs ran beside the full pytest suite, so their timing is pessimistic.

| Item | Result | Where |
|---|---|---|
| `pytest` | 230 passed (227 + 3 net new gate tests; `test_ccore.py` included, g++ on PATH) | Windows, Python 3.14.7 |
| Bundle | `stage` on 3.14 and 3.13, `eval` on MH_01 (heap 1,080,825 bytes, checker PASS), `zip`, `verify` PASS on 3.14 and 3.13 (output identical to `pathfinder.py`, estimator loaded from the shipped bytecode) | `dist/` (git-ignored) |
| Docker | Python image built from the stage (Docker 29.6.2); its MH_01 output is byte-identical to the staged `estimated_trajectory.txt` | Windows |

Not checked: WSL2 Linux 3.12 (no stage, benchmark or verify run there this step, so the zip carries
bytecode for 3.13 and 3.14 only); the Docker image on the degraded copies; how exactly the organisers
start tracemalloc (we assume before `main.py` runs, the stricter reading).


## Step 2: official-script harness, input front end, new baseline (17 Nov 2026, branch `track3/step2-official`)

**Harness.** `tools/official_degrade.py` imports the organisers' `degrade_imu.py` from the git-ignored
`tools/official/` (not committed: decision pending) and calls its `degrade()` with a chosen seed,
max-level and gamma, without editing it. Its output for seed 42, reading a, MH_01 is byte-identical to
the script's own CLI. Each copy `data/official/<seq>_<a|b>_s<seed>/` holds the degraded csv, `meta.json`
(the script's statistics, what `--meta` writes) and `degrade.json` (phase windows for scoring:
protected 2 s, missing-row bursts of >= 5 rows, last 5 s). Reading a = raw EuRoC (gyro first) fed in;
reading b = reordered accelerometer first, left accelerometer first. 64 copies: MH_01..05, V1_01..03 x
a, b x seeds 1, 2, 3, 42. Example (MH_01, seed 42): 36,820 -> 35,629 rows, 38 spikes, 525 stuck
samples, 1,240 dropped (26 bursts), 49 duplicated rows, 1,001 zero rows.

**Input front end** (`vortex/core/frontend.py`, copied into `pathfinder.py`; `FRONT_ON = True`). From
the first 4,000 data rows: the accelerometer triple is the one whose median norm is nearest 9.81 m/s^2
or 1 g and varies least (likeness gap needed 0.5; else the header names decide; else EuRoC order);
timestamp unit from the median step (s / ms / us / ns, the script's thresholds); accelerometer in g
when its median norm is in (0.5, 2.0). A non-canonical file is rewritten canonically next to the output
(integer ns on the text, gyro first, m/s^2) and removed afterwards; a canonical EuRoC file is read as
before, so clean outputs are byte-identical to Step 1 (checked on MH_01).
- Correct, from the data alone, on all 8 clean files and all 64 copies (likeness gap >= 2.3; the
  header agrees on every file), and on the most degraded 20 s of every copy (128 checks, gap >= 0.75).
- **Cannot be detected:** gyro in deg/s versus a fast rad/s motion. A median gyro norm above 3 rad/s
  is flagged (`gyro_suspect`), never converted. Also not handled: a header line without '#' still
  counts as a data row (row rule unchanged); sub-nanosecond timestamp digits are truncated.

**Baseline** (shipped estimator at 5699f6e, unchanged apart from the front end; `Docs/STEP2_BASELINE.md`,
`Docs/RESULTS.md` tags `step2-*`). APE SE3 fitted on the run being scored; floor scored the same way.
Held-out sequences (MH_03..05, V1_01..03), estimator / floor:

| Input | Copies | APE m | RPE 1 s m | Gap RMSE m | Blind RMSE m |
|---|---|---|---|---|---|
| Clean | 6 | 3.59 / 3.75 | 0.791 / 0.912 | - | - |
| Reading a, seeds 1..3 | 18 | **6.31 / 3.75** | 1.016 / 0.938 | 6.24 / 3.35 | 10.67 / 2.51 |
| Reading a, seed 42 | 6 | 7.31 / 3.75 | 1.046 / 0.944 | 6.09 / 3.72 | 14.06 / 2.51 |
| Reading b, seeds 1..3 | 18 | **3.86 / 3.75** | 0.840 / 0.938 | 3.50 / 3.35 | 3.49 / 2.51 |
| Reading b, seed 42 | 6 | 3.82 / 3.75 | 0.841 / 0.944 | 3.91 / 3.72 | 2.86 / 2.51 |

Reading. Under reading b the estimator is level with standing still on APE (+3 %) and better on RPE
1 s, but worse in the gaps and in the blind 5 s. Under reading a (the gyro columns carry the
accelerometer-sized noise, bias walk and spikes up to about 9 rad/s) it is far worse than the floor on
every sequence: the attitude is lost. The blind 5 s error is dominated by the error already present at
the failure (blind growth 0.6 m reading b, 1.4 m reading a, held out). Contract PASS on all 128
official-copy runs and 16 clean runs.

| Item | Result | Where |
|---|---|---|
| `pytest` | Full suite: 244 passed, 1 failed (`test_imports_are_stdlib_allowlist`: `os` now imported to remove the temporary copy; allow-list updated); `tests/test_main.py` rerun: 14 passed. Net: 245 (230 + 15 front end) | Windows, Python 3.14.7 |
| Reference vs `pathfinder.py`, full precision | max difference 0 on MH_01_easy_b_s1, V1_02_medium_a_s42, MH_03_medium_b_s42 (real official copies) and the synthetic front-end cases | Windows 3.14 |
| Budget, `python -S benchmark.py --runs 15 --gate` | PASS on all three. Heap in-process / whole run / no bytecode: synthetic 506 / 995 / 4,886 KB; MH_01_easy_b_s1 587 / 1,081 / 4,886 KB; MH_01_easy_a_s1 587 / 1,081 / 4,886 KB. Time 40.6, 38.1, 31.6 us/row: the laptop ran about 3x slower than in Step 1 throughout this session; on the same file in the same minute, Step 1 and Step 2 `pathfinder.run` took 1.33 s and 1.35 s (+1.5 %) | `Docs/BUDGET.md` `step2-*` |

The front end adds about 216 KB to the in-process heap peak (the 4,000-row detection sample) and, for
a non-canonical file, one extra pass that writes the canonical copy to disk.

Not checked: TUM-VI (not downloaded); what the organisers actually feed the script (Q9); the
`degrade_imu.py` licence and whether to commit it (Arnav); timing on a quiet machine (rerun the
benchmark); the cost of the conversion pass in isolation.


## Step 3: fault front end (17 Nov 2026, branch `track3/step3-faults`)

**What the faults do to the shipped estimator** (Step 2 state): spikes and the first 4 rows of a stuck
run are integrated as real data; a dead or NaN row makes the filter coast (velocity decays, attitude held)
and also drops the next good row's integration step; steps longer than 0.1 s (most missing-row bursts:
5-50 rows) coast instead of being bridged; duplicated rows (step 0) are skipped.

**Pieces** (each a switch, default off; reference `vortex/core/faults.py` + `witness.INTERP_ON`, copied
into `pathfinder.py` bit-identically, `tests/test_faults.py`):
- `STUCK6_ON`: a row whose six values equal the previous row's exactly is a missing sample (stuck runs,
  duplicated rows). Clean EuRoC has none (MH_01..05, V1_01..03 checked), so clean output cannot change.
- `SPIKE_ON`: joint outlier test against the last accepted row and the next distinct row; one triple far
  out (z > SPIKE_ZHI = 100) and the other out (z > SPIKE_ZLO = 3), z = squared deviation over its clipped
  running mean. Chosen on MH_01/02.
- `INTERP_ON`: rows marked missing are skipped (no coasting) and steps up to INTERP_MAX_S = 0.3 s (the
  script's longest burst is 50 rows = 0.25 s; not tuned) are integrated with the trapezoid between the good
  neighbours instead of coasted.
- Blind window: the trailing all-zero run is never marked; it is detected exactly (no threshold). Checked
  on all 64 copies: it equals the script's failure frames plus duplicates, and no all-zero row occurs
  anywhere else. It has no switch: it only stops `STUCK6_ON` from touching the blind rows.
- Calibration under faults (diagnostic, switches off): on every reading-a copy the anchor is the clean
  file's still run (within 0.9 s); V1_01 and V1_02 have no still run even clean (first-second fallback).

**Tuning (MH_01/02 x readings a, b x seeds 1..3, 12 copies; `Docs/RESULTS.md` tags `step3-tune-*`), mean
APE SE3 m, reading a / reading b:** off 12.282 / 3.973; INTERP 13.349 / 3.949; STUCK 11.642 / 3.982;
STUCK + INTERP 14.253 / 3.949; SPIKE (100/3) 12.300 / 3.977; all three with spike thresholds 30/3
14.273 / 4.016, 100/3 14.367 / 3.963, 100/2 14.277 / 3.963. Spike detection against the script's own
spike rows (rerun with zero spike magnitude, MH_01/02 only): at 100/3 about 40 % of the spikes are found,
with about two false marks per true one (rotor vibration is heavy-tailed); clean MH_01/02 get 71 / 28 marks.

**Decision rule, committed before any held-out run of these switches.** Held-out set H: MH_03..05,
V1_01..03 x readings a, b x seeds 1, 2, 3 (36 copies; the seed-42 copies are reported, never decide).
Clean set C: MH_01..05, V1_01..03. Switches are judged in the order STUCK6, SPIKE, INTERP, each with the
earlier ones at their decided state. A switch ships on only if all hold:
1. mean APE (SE3 on the run) over H improves by at least 1 %;
2. in each reading separately, mean APE over its 18 copies is not worse by more than 1 %;
3. mean gap RMSE and mean blind RMSE over H are each not worse by more than 2 %;
4. mean APE over C is not worse by more than 0.5 %;
5. output contract PASS on every run.
Otherwise it ships off and is recorded as a measured experiment. No constant changes after this commit.

**Outcome** (17 Nov; `python tools/judge_step3.py`, tags `step3-H-*` (36 held-out copies) and `step3-C-*`
(8 clean sequences), `main.py` with `--set`; contract PASS on all 88 runs of each comparison):

| Switch (judged with the earlier ones off) | Mean APE H | Reading a | Reading b | Gap RMSE | Blind RMSE | Clean APE | Verdict |
|---|---|---|---|---|---|---|---|
| STUCK6 | 5.086 -> 5.075 (-0.20 %) | 6.311 -> 6.190 (-1.92 %) | 3.861 -> 3.961 (**+2.60 %**) | -1.46 % | +1.41 % | +0.000 % | **off** (fails 1 and 2) |
| SPIKE (100/3) | 5.086 -> 5.088 (+0.05 %) | +0.08 % | -0.00 % | -0.06 % | +0.52 % | +0.053 % | **off** (fails 1) |
| INTERP (0.3 s) | 5.086 -> 5.412 (+6.42 %) | 6.311 -> 7.027 (**+11.34 %**) | 3.861 -> 3.798 (-1.62 %) | +5.07 % | +15.26 % | +0.000 % | **off** (fails 1, 2, 3) |

**Reading.** None of the three pieces earns its place on the held-out copies. The two column readings
pull in opposite directions: under reading b (sane gyro) bridging gaps helps a little (-1.6 %), under
reading a (accelerometer-sized faults on the gyro) every extra gyro integration step hurts and coasting
with the attitude held is better; removing stuck rows helps reading a and hurts reading b. Spike removal
does nothing measurable: at 100/3 it finds about 40 % of the spikes, and the remaining ones plus the
gyro noise dominate. The error is not in the isolated faults but in the attitude under the noise and bias
walk the script adds (reading a), and in the never-moving-level offset (both readings).

Shipped: `STUCK6_ON = SPIKE_ON = INTERP_ON = False` (reference and `pathfinder.py`); the code stays as a
recorded experiment. Not retried on the same held-out copies: any reading-aware variant (for example
bridging only when the gyro noise level is low) would need a new rule and copies never seen (new seeds).

| Item | Result | Where |
|---|---|---|
| `pytest` | 256 passed (245 + 11 `tests/test_faults.py`) | Windows, Python 3.14.7 |
| Reference vs `pathfinder.py` with switches on | max difference within the equivalence criterion on a SYNTHETIC degraded file (spikes, stuck runs, a 40-row burst, duplicates, zero tail) for four switch combinations; the fault pass emits identical lines | `tests/test_faults.py` |
| Budget, `python -S benchmark.py --runs 15 --gate` (shipped settings, switches off) | PASS: synthetic 10.48 us/row, heap 506 / 1,005 / 5,278 KB (in-process / whole run / no bytecode); MH_01_easy_b_s1 10.24 us/row, 588 / 1,092 / 5,278 KB. No-bytecode heap on Win 3.13 (MH_01): 6,310 KB | `Docs/BUDGET.md` `step3-*` |

The no-bytecode compile peak on 3.14 rose from 4.89 MB (Step 2) to 5.28 MB: the switched-off fault code is
compiled too. Still under 8 MB; if it grows further, moving switched-off experiments out of
`pathfinder.py` (they live in the reference anyway) is the cheapest fix.

Not checked: TUM-VI (not downloaded); the seed-42 copies with the switches on (the switches ship off, so
the Step 2 seed-42 numbers stand); a reading-aware variant (would need a new rule and new seeds).

## Step 4: envelope learned per flight (17 Nov 2026, branch `track3/step4-envelope`)

**Why.** The V2 envelope sigmas (speed 2.0 / 0.3 m/s, volume 5.0 / 2.0 m around a 10 s running centre) were
chosen on Machine Hall. Under the official script's reading a they are far too loose to hold the drift
(Step 2: held-out reading a APE 6.31 m against a floor of 3.75 m).

**Piece** (`LEARN_ON`, default off; reference `vortex/core/witness.py` `learn_env` / `estimate_learned`,
copied into `pathfinder.py` `_learn_env` / `_run_learned` bit-identically; `tests/test_witness.py`): pass 1
runs with the fixed values and records per tick, after the updates, v^2 + P_vv and (p - c)^2 + P_pp
(horizontal = mean of x, y; vertical). Over the ticks in the first LEARN_FRAC of the file's time span the
sigma is LEARN_K x sqrt(mean) (one EM step for the prior's variance with the filter's own posterior),
clamped to [LEARN_MIN, LEARN_MAX] = [(0.1, 0.05, 0.3, 0.1), (4.0, 1.0, 10.0, 4.0)] (wide, not tuned).
LEARN_ITERS such steps, then the final pass that writes. Ground truth is never read. Cost: LEARN_ITERS + 1
passes over the rows.

**Tuning (MH_01/02 x readings a, b x seeds 1..3, 12 copies, and clean MH_01/02; tags `step4-tune-*`,
`step4-abl-*`).** Mean APE SE3 m; never-moving floor on the same 12 copies 4.491; today (fixed values)
8.128 (a 12.282, b 3.973), clean 3.878.

| Setting | APE all | Reading a | Reading b | Gap RMSE | Blind RMSE | Clean APE |
|---|---|---|---|---|---|---|
| fixed (today) | 8.128 | 12.282 | 3.973 | 8.793 | 17.650 | 3.878 |
| FRAC 0.3, 1 iter | 4.479 | 4.529 | 4.430 | 3.937 | 5.413 | 4.426 |
| **FRAC 0.3, 2 iters** | **4.391** | 4.318 | 4.464 | 3.680 | 4.772 | 4.456 |
| FRAC 0.5, 1 iter | 5.383 | 6.421 | 4.345 | 5.307 | 8.690 | 4.344 |
| FRAC 0.5, 2 iters | 4.651 | 4.889 | 4.412 | 4.260 | 5.957 | 4.412 |
| FRAC 1.0, 1 iter | 9.990 | 15.668 | 4.313 | 10.846 | 20.166 | 4.313 |
| FRAC 1.0, 2 iters | 11.947 | 19.500 | 4.394 | 13.072 | 25.483 | 4.395 |
| FRAC 0.3, 2 iters, K 1.5 | 4.449 | 4.454 | 4.443 | 3.833 | 5.240 | 4.439 |
| FRAC 0.3, 2 iters, K 2 | 4.785 | 5.153 | 4.417 | 4.373 | 6.433 | 4.416 |
| FRAC 0.3, 2 iters, K 3 | 6.328 | 8.302 | 4.354 | 6.422 | 10.566 | 4.355 |
| FRAC 0.5, 2 iters, K 1.5 | 5.962 | 7.573 | 4.350 | 6.042 | 10.083 | 4.352 |
| FRAC 0.5, 2 iters, K 2 | 8.111 | 11.942 | 4.279 | 8.665 | 15.498 | 4.278 |
| FRAC 0.5, 2 iters, K 3 | 12.828 | 21.528 | 4.129 | 14.353 | 28.379 | 4.107 |
| FRAC 0.3, 2 iters, speed only (volume fixed) | 4.379 | 4.312 | 4.447 | 3.659 | 4.799 | 4.440 |
| FRAC 0.3, 2 iters, volume only (speed fixed) | 4.527 | 4.700 | 4.355 | 4.017 | 5.723 | 4.355 |
| FRAC 0.3, 2 iters, horizontal only | 4.358 | 4.316 | 4.400 | 3.650 | 4.895 | 4.412 |

Learned values on clean MH_01 (FRAC 0.5, 1 iter): speed 0.51 / 0.16 m/s, volume 1.19 / 0.32 m, close to the
ground truth's own spread (speed RMS 0.35 / 0.20 m/s, distance from the 10 s centre 1.42 / 0.40 m; read for
this diagnostic only, never by the estimator). On reading-a copies the learned values are larger (drift
inflates them; a second iteration shrinks them).

**Choice (on tuning only):** FRAC 0.3, 2 iterations, K 1.0, all four sigmas learned: the lowest APE among the
full-learning settings and within 1 % of the best restricted variant, so the simpler one. It is the only
setting judged on held-out data. **Every learned setting makes clean MH_01/02 worse (3.878 -> 4.11..4.46 m,
+6 to +15 %)**, including speed-only and volume-only: any envelope tighter than today's costs clean APE. So
condition 2 below is expected to fail; the held-out run is made once anyway, as the rule's decision.

**Decision rule, committed before any held-out run of `LEARN_ON`.** Held-out set H: MH_03..05, V1_01..03 x
readings a, b x seeds 1, 2, 3 (36 copies; seed 42 reported, never decides). Clean set C: MH_01..05,
V1_01..03. `LEARN_ON` (FRAC 0.3, ITERS 2, K 1.0) ships on only if all hold:
1. mean APE (SE3 on the run) over H is no worse than the never-moving floor's on the same 36 copies
   (tag `step2-floor-off`);
2. mean APE over C is not worse than today's (`step3-C-off`) by more than 0.5 %;
3. output contract PASS on every run.
Reported, not deciding: the change against today's fixed envelope on H (`step3-H-off`) per reading, gap,
blind and RPE 1 s. `python tools/judge_step4.py --h-on step4-H-learn --floor step2-floor-off --h-off
step3-H-off --c-off step3-C-off --c-on step4-C-learn`. No constant changes after this commit.

**Outcome** (17 Nov; `python tools/judge_step4.py ...` as above; tags `step4-H-learn` (36 held-out copies),
`step4-C-learn` (8 clean), `step4-R42-learn` (12 seed-42 copies, reported only); contract PASS on all runs):

| Condition | Value | Result |
|---|---|---|
| 1 mean APE over H <= never-moving floor | floor 3.748, learned 3.739 m (-0.25 %) | pass |
| 2 clean mean APE not worse by > 0.5 % | 3.663 -> 3.908 m (+6.68 %) | **FAIL** |
| 3 contract PASS on every run | 44 runs | pass |

**Verdict: `LEARN_ON` ships OFF.**

Reported only, today's fixed envelope -> learned, mean over H (floor in brackets): APE 5.086 -> 3.739 m
(3.748); reading a 6.311 -> 3.764 (3.748); reading b 3.861 -> 3.713 (3.748); gap RMSE 4.871 -> 3.361
(3.351); blind RMSE 7.076 -> 2.874 (2.509); RPE 1 s 0.928 -> 0.950 (0.938). Seed 42 (12 copies): reading a
7.310 -> 3.729 (3.747), reading b 3.822 -> 3.718 (3.747); blind reading a 14.061 -> 2.511 (2.508).

Clean APE per sequence, fixed / learned / floor (m): MH_01 3.911 / 4.286 / 4.308; MH_02 3.846 / 4.626 /
4.646; MH_03 3.530 / 3.524 / 3.580; MH_04 6.378 / 6.775 / 6.822; MH_05 6.546 / 6.841 / 6.879; V1_01 1.774 /
1.806 / 1.853; V1_02 1.773 / 1.805 / 1.778; V1_03 1.548 / 1.601 / 1.574.

**Reading.** The learned envelope does not find a better motion model; it collapses the estimate towards
the never-moving trajectory. On every clean sequence the learned APE lands within 2 % of the floor's, and
on H it ties the floor (-0.25 %) while RPE 1 s gets worse. On degraded copies that is a large gain over
today (-26 %, reading a -40 %, blind -59 %), because today's estimate is worse than standing still there;
on clean files it throws away the motion the fixed envelope keeps. The cause: the posterior spread of a
filter whose only position information is the envelope itself is small, so each EM step tightens the prior
further. Scaling the sigmas up (K) gives the motion back on clean files only by giving the drift back on
reading a (tuning table). The real problem the step exposes: under reading a, the estimator is worse than
not moving at all; that is a front-end/attitude problem (Steps 3, 5, 6), not an envelope problem.

Shipped: `LEARN_ON = False` (reference and `pathfinder.py`; FRAC 0.3, ITERS 2, K 1.0 kept as the recorded
settings). Not retried on the same held-out copies.

| Item | Result | Where |
|---|---|---|
| `pytest` | 259 passed (256 + 3 Step 4 tests in `tests/test_witness.py`); 264 after merging main (Step E smoother tests), 18 Nov | Windows, Python 3.14.7 |
| Reference vs `pathfinder.py` with `LEARN_ON` | within the equivalence criterion on a SYNTHETIC file for (ITERS 1, K 1.0) and (ITERS 2, K 1.5); learned sigmas identical | `tests/test_witness.py` |
| Budget, `python -S benchmark.py --runs 15 --gate` (shipped settings, switch off) | PASS: synthetic 12.04 us/row, heap 505 / 1,012 / 5,471 KB (in-process / whole run / no bytecode); MH_01_easy_b_s1 11.19 us/row, 588 / 1,099 / 5,471 KB | `Docs/BUDGET.md` `step4-*` |
| Cost with `LEARN_ON` (not shipped; in-process `run()`, best of 3, MH_01_easy_b_s1) | 25.7 us/row (off: 11.5), heap peak 613 KB (off: 588) | scratch script, not committed |

The no-bytecode compile peak rose again, 5.28 -> 5.47 MB (switched-off Step 4 code). Still under 8 MB. If
Step 5 or 6 adds more, the switched-off experiments (fault pass, learned envelope) move out of
`pathfinder.py`; they stay in the reference.

Not checked: TUM-VI (not downloaded); a gated variant (learn only when the file looks like reading a)
would need a new rule and new seeds; LEARN_ON timing through `python -S main.py` (only in-process).

Merge note (18 Nov): Step 4 was judged on the estimator before Step F (`BGCAP_ON`, `P0V_ON`, `REFRESH_ON`
now ship on, merged into `main` the same day). The verdict stands for that estimator; it was not re-run on
the Step F estimator (that would be a second look at the same held-out copies). `LEARN_ON` stays off.


## Step E: forward-backward smoother (17 Nov 2026, branch `track3/stepE-smoother`; time-boxed, one session)

Started before Step C because C is blocked (no TUM-VI) and V3 was dropped (so Step D does not apply).

**What was built** (`vortex/core/witness.py`, switch `SMOOTH_ON`, **off**; reference only, not in
`pathfinder.py` or `main.cpp`). A fixed-interval Rauch-Tung-Striebel smoother at the 0.25 s filter tick:
- at each tick close, the gain C = P+ Phi^T (P-)^-1 (Cholesky solve) and the correction injected at the
  previous tick are stored as one block, in single precision: 4 x (225 + 15 + 15) + 8 = **1,028 bytes per
  block**;
- fixed cap `SMOOTH_MAX_BLOCKS` = 1024 blocks (**1,052,672 bytes worst case**, any file length): up to 256 s at
  one tick per block; a full store merges adjacent blocks pairwise (exact composition of their affine maps),
  so a 15 min file ends with blocks of 4 ticks (1 s) and memory never grows;
- after the forward pass the backward recursion gives the smoothed error at every stored tick; each row
  from the anchor on is corrected linearly in time between its two bracketing ticks (dropouts are
  bracketed on both sides). Rows before the anchor and after the last tick (the blind window) are
  unchanged: the file ends in sensor failure, so the last smoothed state is the filtered one.

The byte counts above are computed from the layout, not measured: the smoother was not ported to
`main.cpp`, so its RSS on the longest file was not measured.

**Checks (SYNTHETIC, `tests/test_witness.py`, 5 new tests).** RTS gain equals dense numpy; default output
unchanged; second-rest profile with V1 only: max error over the second motion 12.2 -> 0.8 m (all witnesses
on: 2.7 -> 0.36 m), rows before the anchor and the last row unchanged; with a cap of 16 blocks the store
never exceeds 16 and the output stays finite; block merge composes exactly (to single precision).

**Tuning set, MH_01/02 only** (`python tools/smooth_eval.py --tag stepE-tune ...`,
`python tools/smooth_grid.py`; `Docs/smooth/`):

| Setting | Clean APE m | Clean RPE 1 s m | Degraded APE m (6 copies) | Dropout growth m |
|---|---|---|---|---|
| forward only (shipped) | **3.878** | 0.536 | **4.358** | **0.894** |
| smoother, shipped envelope | 4.387 | 0.330 | 4.655 | 1.129 |
| smoother, best of 12 envelope settings by clean APE (V2_H 2, V2P_H 2, tau 10) | 4.292 | 0.384 | 4.468 | 1.006 |
| smoother, range over all 12 settings | 4.29..4.52 | 0.29..0.38 | 4.47..4.90 | 1.01..1.39 |

Blind growth 2.447 -> 2.383 m (shipped envelope; the blind window itself is unchanged, the difference is
where it starts from).

**Why it fails.** The smoother is right where the model is right (synthetic), but on MH the filter has no
in-flight velocity measurement: V2 is a zero-mean prior and V2P a pull toward its own running centre. The
forward estimate is collapsed toward the room centre (position std 0.5..0.8 m against 2.3..3.3 m in ground
truth, MH_01/02, analysis only) and jittery (path length 1.7x ground truth). Smoothing removes the jitter
(path 0.7x, RPE 1 s -38 %) but the motion it restores does not have the true shape, so APE and dropout
growth rise. Smoothing cannot add information the filter does not have.

**Decision: SMOOTH_ON stays off, without a held-out run.** The user's rule needs held-out mean APE and
dropout growth to improve; both get worse on the tuning set in every setting tried, so (as in step 8b) no
held-out data was spent and no rule was registered. The switch and tests stay in the reference for a later
attempt (for example once an in-flight witness exists). `pathfinder.py`, `main.py`, `main.cpp` and every
shipped result are unchanged.

| Item | Result | Where |
|---|---|---|
| `pytest` | 232 passed (227 + 5 smoother) | Windows, Python 3.14.7 |
| Budget | not rerun: `pathfinder.py`, `main.py` and `main.cpp` unchanged (step A numbers stand) | `Docs/BUDGET.md` `stepA-*` |

Not checked: RSS of a C port (not ported); TUM-VI (no data); whether the organisers allow non-causal
processing (open).

### Step E, second look: official-script copies (17 Nov 2026, branch `track3/stepE2-smoother-official`)

After Step 2 (official harness, `data/official/`), the smoother was rerun on the TUNING copies only:
MH_01/02 x readings a, b x seeds 1..3 (12 copies; seed 42 is report-only and not used), read through the
input front end as `main.py` reads them, scored as the organisers score (SE3 fitted on the run itself).
`python tools/smooth_eval.py --tag stepE2-tune-official --official ...` (`Docs/smooth/stepE2-tune-official.json`).

| Reading | Smoother | APE m | RPE 1 s m | Gap RMSE m | Gap growth m | Blind RMSE m | Blind growth m |
|---|---|---|---|---|---|---|---|
| b (accelerometer first) | off | **3.973** | 0.558 | **3.754** | 0.026 | 7.537 | 0.634 |
| b | on | 4.341 | 0.399 | 3.863 | 0.022 | 7.350 | 0.559 |
| a (raw EuRoC fed in) | off | 12.283 | 1.204 | 13.832 | 0.146 | 27.763 | 3.181 |
| a | on | 10.734 | 1.343 | 11.193 | 0.058 | 29.110 | 3.195 |

Never-moving floor on MH_01/02 (SE3 on the run): 4.31 / 4.65 m APE.

**Reading.** Under reading b (and on clean data) the smoother raises APE (+9 %) and gap RMSE (+3 %),
for the same reason as above. Under reading a it lowers APE 13 % and gap RMSE 19 %, but there the forward
estimate is already about 3x worse than standing still (attitude lost to the gyro-sized faults): the
smoother repairs part of a broken estimate rather than improving a working one, and the fault front end
(O2) is meant to remove that failure first. The official gaps are short (5..50 rows), so bracketing them
gives little (gap growth is already 0.02..0.15 m).

**Decision: SMOOTH_ON stays off; no held-out run.** Revisit after O2 (spike / stuck rejection) and an
in-flight witness, with a rule written before any held-out copy is run. Nothing shipped changes.

`pytest`: 250 passed (245 after Step 2 + 5 smoother), Windows, Python 3.14.7. Budget not rerun: `pathfinder.py` and
`main.py` unchanged.



## Step F: filter fixes from the reviews (17 Nov 2026, branch `track3/stepF-bias-reset`)

**Why.** Two external reviews (16 and 17 Nov) found four defects in the shipped filter, all confirmed in the
code and present in both `pathfinder.py` and the reference:
- The still tests bound the spread of the gyro, not its mean. A steady rotation is low-variance and steady,
  so it is taken for rest and its rate for gyro bias. SYNTHETIC check: 8 s of 0.3 rad/s yaw from the first
  row, calibrated as rest with a 0.300 rad/s z bias; the final yaw was 0.005 deg against a true 137 deg.
  Only a bias prior can tell the two apart (the IMU readings are identical), so this is damage limitation:
  a rotation slower than the cap still passes.
- No covariance reset after the attitude correction is injected (`P <- G P G^T`).
- The cached previous sample (bias-corrected gyro, world specific force) keeps the pre-injection attitude
  and biases for the next trapezoid step.
- With no still run (first-second fallback) the initial velocity sigma is still 0.01 m/s.

**Pieces** (each a switch, default off; reference `vortex/core/strapdown.py` + `witness.py`, copied into
`pathfinder.py`; `tests/test_stepF.py`, 23 tests):
- `BGCAP_ON`: a bin or init window whose mean gyro norm exceeds `BG_MAX = 0.15` rad/s is not still, in every
  still test: strict calibration and V1 (`bin_is_still`), the denoised calibration and V1 (`bin_is_still_denoised`)
  and the first-second fallback (`initialise`). `BG_MAX` is 1.8x the largest calibrated |bg| on MH_01/02 (clean and
  the 12 official copies: 0.080 to 0.083 rad/s); not tuned on anything else; TUM-VI not checked.
- `RESET_ON`: `kf_reset`, G = I + [dth/2]x on the attitude block (global attitude error; Sola 2017, ESKF reset).
  Checked against a finite-difference Jacobian of dth+ = Log(Exp(dth) Exp(-dth_hat)): second-order agreement,
  and the opposite sign is visibly wrong.
- `REFRESH_ON`: `refresh_prev`, the cached sample re-expressed with the corrected attitude and biases; equals a
  fresh `_sample` with the corrected state to 1e-12.
- `P0V_ON`: with no still run, the initial velocity sigma is the V2 envelope (2.0, 2.0, 0.3 m/s).
- The smoother (Step E, reference only, off) does not apply the reset to its stored covariances; if it is ever
  switched on together with `RESET_ON` that needs adding.

**Tuning set (MH_01/02 x readings a, b x seeds 1-3, 12 copies; clean MH_01/02), mean APE SE3 m, reading a /
reading b; gap and blind RMSE m; tags `stepF-tune-*`:** off 12.282 / 3.973, gap 8.793, blind 17.650, clean 3.8782;
BGCAP identical to off (every MH calibration is under the cap); P0V identical (MH always calibrates); REFRESH
12.282 / 3.973, identical gap and blind, clean 3.8783; RESET 12.272 / 3.974, gap 8.913 (+1.4 %), blind 18.299
(+3.7 %), clean 3.8787; RESET + REFRESH as RESET. Nothing was tuned on these runs: `BG_MAX` and the P0V sigmas
are set from the calibrated MH bias and the envelope, not from accuracy.

**Decision rule, committed before any held-out run of these switches** (`tools/judge_stepF.py`). Held-out set
H: MH_03..05, V1_01..03 x readings a, b x seeds **4, 5, 6** (36 copies made with the organisers' script for this
step; the seed 1-3 copies already decided Step 3). Clean set C: MH_01..05, V1_01..03. Judged in the order
BGCAP, P0V, REFRESH, RESET, each with the earlier ones at their decided state. These fix demonstrated defects
and add no new hint, so the rule is no-harm. A switch ships on only if all hold:
1. mean APE (SE3 on the run) over H is not worse by more than 0.5 %;
2. in each reading separately, mean APE over its 18 copies is not worse by more than 1 %;
3. mean gap RMSE and mean blind RMSE over H are each not worse by more than 2 %;
4. mean APE over C is not worse by more than 0.5 %;
5. output contract PASS on every run;
6. BGCAP only: the SYNTHETIC steady-rotation test in `tests/test_stepF.py` passes.
Otherwise it ships off and is recorded as a measured experiment. No constant changes after this commit.
Expected from the tuning set (a prediction, not part of the rule): BGCAP and P0V change little or nothing on
EuRoC (their targets, moving starts, are rare there); RESET may fail condition 3 on the blind RMSE.

**Outcome (17 Nov 2026; rule commit cba34e3, judged with `tools/judge_stepF.py`).** Held-out H = 36 copies
(MH_03..05, V1_01..03 x a, b x seeds 4-6), clean C = MH_01..05, V1_01..03. Mean APE SE3 m over H (reading a /
reading b), gap RMSE, blind RMSE; clean mean APE; tags `stepF-H-*`, `stepF-C-*`:

| state | H APE | a | b | gap | blind | C APE | verdict |
|---|---|---|---|---|---|---|---|
| never-moving floor (`stepF-H-floor`) | 3.745 | 3.745 | 3.745 | 3.626 | 2.504 | - | - |
| all off (`stepF-H-off`) | 4.972 | 6.193 | 3.752 | 5.011 | 6.964 | 3.6633 | - |
| + BGCAP (`stepF-H-bgcap`) | 4.972 | 6.193 | 3.752 | 5.011 | 6.964 | 3.6633 | on (no run changed; condition 6: 23/23 tests pass) |
| + P0V (`stepF-H-p0v`) | 4.962 | 6.181 | 3.744 | 5.036 | 6.992 | 3.6548 | on (changed only V1_01 and V1_02, which start moving) |
| + REFRESH (`stepF-H-p0v-refresh`) | 4.962 | 6.181 | 3.744 | 5.036 | 6.992 | 3.6548 | on (changes below 0.01 %) |
| + RESET (`stepF-H-reset`) | 5.020 | 6.293 | 3.746 | 5.095 | 7.004 | 3.6543 | **off**: conditions 1 (+1.15 %) and 2 on reading a (+1.81 %) fail |

`stepF-H-refresh` / `stepF-C-refresh` (REFRESH without P0V) were run in parallel in case P0V failed; unused.
Shipped: `BGCAP_ON`, `P0V_ON`, `REFRESH_ON` on; `RESET_ON` off (kept, tested, recorded as a measured
experiment: the textbook reset is correct to second order but costs accuracy on reading a; not investigated
further). The prediction held for BGCAP and RESET (RESET failed, though on APE rather than condition 3); P0V
was not "identical": V1_01 and V1_02 have no still run in their first 60 s on the official copies.

**Plain reading.** Step F moves the held-out mean APE by -0.2 %. The estimator is still worse than the
never-moving floor on H (4.962 against 3.745 m); on reading b it is level with it (3.744 against 3.745), on
reading a it is far worse (6.181), driven by V1_01 a (8.5 m against 1.9) and MH_03..05 a. The blind 5 s is
worse than the floor in both readings (6.99 against 2.50 m). These are the problems to work on next; Step F
does not address them.

Gates (Windows, Python 3.14): `pytest` 284 passed (g++ on PATH, so `test_ccore.py` ran); `benchmark.py --gate` PASS on the synthetic file (`stepF-win-py314`: heap
1012.6 KB with the shipped bytecode, 13.05 us/row) and on MH_01_easy_b_s1 (`stepF-win-py314-mh01-b-s1`: heap
1100.0 KB, 11.43 us/row); checker PASS on all 36 + 36 + 8 runs of every tag.
`tests/test_ccore.py` now compares the frozen C core (`main.cpp`, never extended) with a private copy of
`pathfinder.py` whose Step F switches are set back off; without that its 11 pose tests fail, as expected.
The no-cached-bytecode reading (compiling `pathfinder.py` while traced) rose from 5278 KB (Step 3) to 5512 KB
with the added code: under the 8 MB limit it is held to, and above the 4 MB design target, as before.


## Step 5: rotor drag (V3) (17 Nov 2026, branch `track3/step5-v3`)

Brief: run drag rule v2 stages A and B exactly as pre-registered (commit c1b594c) on V1_01..03, rule not
edited; build V3 in the filter only if stage A passes.

`tools/drag_fit.py` and every module it imports (`vortex/data/euroc.py`, `vortex/geometry.py`,
`vortex/rowspec.py`) are unchanged since c1b594c (`git diff c1b594c HEAD` on those files is empty). Re-run:
`python tools/drag_fit.py --rule v2 data/euroc/V1_01_easy data/euroc/V1_02_medium data/euroc/V1_03_difficult`.
Output identical to the Step B run (`Docs/drag/v2_V1_0*.json` equal key by key; regenerated files differ
only in line endings, so the committed ones were kept):

| Sequence | Airborne s | Axis a: k free / R^2 fixed k | Axis b: k free / R^2 fixed k | Sequence |
|---|---|---|---|---|
| V1_01_easy | 144 | 0.224 / 0.542 pass | 0.083 / -0.049 **fail** | fail |
| V1_02_medium | 84 | 0.201 / 0.668 pass | 0.175 / 0.784 pass | pass |
| V1_03_difficult | 100 | 0.194 / 0.630 pass | 0.138 / 0.432 **fail** | fail |

**Stage A: NO-GO** (1 of 3; the rule needs 2). **Stage B is not run:** by the rule it compares V3 on
against V1 + V2 in `main.py`, and V3 is not built after a stage A failure. So the V3 filter work (airborne
detector, online thrust axis, k = 0.20 /s, sequential gated updates, accelerometer-bias states, SYNTHETIC
bias step/walk check), the no-harm check on official copies and the ablation (V1+V2 / +V3 / V3 without the
volume envelope) are not built or run. The ablation reduces to V1 + V2, the shipped estimator (Steps 2-4).

No estimator, `pathfinder.py` or `main.py` change: output and budget are those of Step 4
(`Docs/BUDGET.md` `step4-*`; `Docs/RESULTS.md` unchanged). `pytest tests/test_drag_fit.py`: 11 passed;
the full suite was not re-run (no code changed since Step 4: 259 passed; 287 after merging main with Steps E and F, 18 Nov).

Not done, and why: a rule v3 (for example axis a only, which holds on all three with k 0.19..0.22 /s) would
be chosen after seeing V1_01..03, so it would need decision data never seen; the only unseen EuRoC
sequences are V2_01..03, the final test set. Not proposed.

## Step 6: batch forward-backward smoother (18 Nov 2026, branch `track3/step6-smoother`)

Brief: fixed-interval smoothing at the 0.25 s tick, rows re-integrated between smoothed ticks, storage
capped (bytes per tick, worst case on a 15 min file), check whether flights end with a ground rest before
the zeroed 5 s (an end anchor for the backward pass); on only if held-out mean APE and gap error improve
by a stated margin and clean runs are not worse.

**Starting point.** The RTS smoother of Step E (`witness.SMOOTH_ON`, reference only) with the shipped
estimator after Step F. Step F does not change the MH_01/02 tuning copies (APE identical to 4 decimals with
its switches off or on), so the Step E second-look numbers still describe the current estimator; rerun to
confirm (`python tools/smooth_eval.py --tag step6-tune-official-postF --official <12 MH_01/02 copies>`,
`--tag step6-tune-clean-postF --seqs MH_01_easy,MH_02_easy`): clean 3.878 -> 4.387 m (+13 %); reading b
3.973 -> 4.340 (+9 %); reading a 12.283 -> 10.734 (-13 %); gap RMSE a 13.83 -> 11.19, b 3.75 -> 3.86.

**End anchor: none.** `python tools/end_rest.py` (clean) and `python tools/end_rest.py --official --seqs
<seed-1 copies>`: the estimator's own V1 stillness test, run over the file. On every MH_01..05 and
V1_01..03 file (clean and both readings) the last still tick before the blind window is the opening rest,
80 to 146 s earlier (V1_01: no still tick at all, even clean). Ground truth at the start of the blind window
(DIAGNOSTIC only, never read by the estimator): mean speed over the 3 s before it 0.17 to 0.98 m/s on every
file. The flights end in motion, so the backward pass has no end anchor: its only information is the V2
envelope prior, as in the forward pass.

**Rows between ticks.** Not built as re-integration. Scoring only the rows that close a tick (where the
smoothed state is exact and any between-tick treatment, linear or re-integrated, gives the same pose):
clean MH_01 3.782 -> 4.057 m, MH_02 3.604 -> 4.197 m (smoother off -> on; EXPLORATORY, tuning set, scratch
script). The loss is at the ticks themselves, so no between-tick treatment can remove it. For scale: a
re-integration differs from the linear correction by at most about (g x tilt error + accel-bias error) x
T^2 / 2 = (9.8 x 0.05 + 0.1) x 0.25^2 / 2 = 0.02 m within a tick, against a 0.3 to 0.6 m APE loss.

**Storage** (Step E layout, computed, not measured): 1,028 bytes per stored block (15 x 15 gain + two
15-vectors in single precision + time), at most `SMOOTH_MAX_BLOCKS` = 1024 blocks = 1,052,672 bytes for any
file length; a 15 min file (3,600 ticks) ends with blocks of 4 ticks (1 s). Only the reference has it
(Python lists, so its own footprint is larger); written before the rule; ported after it passed (see Port).

**Decision rule, committed before any held-out run of the smoother.** Setting: the Step E smoother as it
is (shipped envelope, cap 1024, linear correction between ticks), reference estimator, both from
`tools/smooth_eval.py` (off and on in the same harness). Held-out set H: MH_03..05, V1_01..03 x readings a,
b x seeds 1, 2, 3 (36 copies; seed 42 reported only). Clean set C: MH_01..05, V1_01..03. `SMOOTH_ON` passes
only if all hold:
1. mean APE (SE3 on the run) over H improves by at least 2 %;
2. mean gap RMSE over H improves by at least 2 %;
3. mean APE over C is not worse by more than 0.5 %.
Reported, not deciding: per reading, RPE 1 s, blind RMSE, the never-moving floor (`step2-floor-off`) on the
same copies, seed 42. If it passed it would be ported to `pathfinder.py` (bit-identical, budget gate) before
shipping. Expected from tuning: condition 3 fails. `python tools/judge_step6.py --h step6-H --c step6-C
--floor step2-floor-off --r42 step6-R42`. No constant changes after this commit.

**Outcome** (18 Nov; `python tools/judge_step6.py --h step6-H --c step6-C --floor step2-floor-off --r42
step6-R42`; `Docs/smooth/step6-{H,C,R42}.json`):

| Condition | Value | Result |
|---|---|---|
| 1 mean APE over H improves >= 2 % | 5.071 -> 4.677 m (-7.78 %) | pass |
| 2 mean gap RMSE over H improves >= 2 % | 4.849 -> 4.329 m (-10.73 %) | pass |
| 3 clean mean APE not worse by > 0.5 % | 3.655 -> 3.555 m (-2.73 %) | pass |

**Verdict: `SMOOTH_ON` ships ON** (reference and `pathfinder.py`).

Reported only, off -> on (never-moving floor on the same copies): APE reading a 6.289 -> 5.757 m (3.748),
reading b 3.853 -> 3.597 m (3.748); RPE 1 s 0.929 -> 0.715 m (0.938); blind RMSE 7.115 -> 7.458 m (+4.8 %;
2.509); gap RMSE a 6.193 -> 5.491, b 3.506 -> 3.167 (3.351). Seed 42: reading a 7.332 -> 6.574, reading b
3.808 -> 3.555 m.

Per sequence, clean APE off -> on (m): MH_01 3.911 -> 4.232 (+8 %), MH_02 3.846 -> 4.541 (+18 %), MH_03 3.530
-> 2.710 (-23 %), MH_04 6.378 -> 6.265, MH_05 6.547 -> 6.557, V1_01 1.761 -> 1.886 (+7 %), V1_02 1.718 -> 1.028
(-40 %), V1_03 1.548 -> 1.222 (-21 %). Held-out copies, mean of seeds 1..3, reading a / b: MH_03 -16 / -20 %,
MH_04 +6 / -1 %, MH_05 -5 / +0.3 %, V1_01 -13 / +5 %, V1_02 -23 / -24 %, V1_03 -15 / -15 %.

**Reading.** The tuning set (MH_01/02) was the worst case: both get worse, and the held-out set is better on
the whole. The smoother is a clear gain on MH_03, V1_02, V1_03 and on reading a; it costs on MH_01/02, V1_01
(clean and reading b) and the blind window (+4.8 %: the smoothed state the blind forecast starts from is
unchanged, but the trajectory before it moves, so the SE3 fit moves). Held-out reading b is now below
the never-moving floor (3.597 against 3.748 m; Step 2: 3.86, above it); reading a (5.757) is still above it. Tuning results did not predict this; the rule, not the tuning, decides.

**Port** (`pathfinder.py`: `_phi_entries`, `_smooth_gain`, `_smooth_merge`, `_smooth_push` (merging in place),
`_smooth_segments`; `_run(..., store, corr)`; `_run_learned` runs a storing pass, then the writing pass with
the correction): pass 1 stores the blocks exactly as the reference (single precision, same arithmetic, the
built-in `sum()` in the backward recursion as in the reference, since 3.12 compensated), pass 2 recomputes
the forward pass and corrects each row as it is written (only the six components a pose needs are
interpolated). Memory is the block store (capped) plus 12 doubles and 2 times per block for the segments; it
never grows with the file. Full-precision check against `witness.estimate_file` (smoother on): max
difference 0.0 in position and attitude on MH_01_easy_b_s1, MH_02_easy_a_s2 and clean MH_01_easy.
`tests/test_smoother_port.py`: 5 tests (caps 1024, 16 and 15 so the merge runs, odd and even; with the
learned envelope; the switch changes the output; the last row keeps the filtered pose).

**Cost** (`python -S`, in-process `run()`, Windows 3.14):

| File | Off: us/row, heap | On: us/row, heap | Blocks at the end |
|---|---|---|---|
| SYNTHETIC 15 min (180,000 rows, `tools/synth_euroc.py --rows 180000`) | 9.25, 505 KB | 32.6, 1,479 KB | 527 (merged twice) |
| MH_01_easy_b_s1 (35,697 rows) | 9.36, 592 KB | 21.9, 1,232 KB | 608 |

Bytes per stored block: 255 single-precision floats (1,020 bytes of data) + the time; with Python's array
and tuple headers about 1.3 KB; worst case 1024 blocks, about 1.35 MB, reached on any file longer than 256 s.
Measured peak on the 15 min file: 1.48 MB in-process (the 4 MB target holds).

Heap peak against flight length (SYNTHETIC, `tools/synth_euroc.py`, in-process `run()`, tracemalloc,
scratch script): 3 / 6 / 9 / 15 min = 1,118 / 1,453 / 1,479 / 1,479 KB with the smoother (719 / 927 / 623 /
527 blocks at the end); 508 / 506 / 506 / 506 KB without it. The store grows until it first fills (1024
ticks, 256 s) and is flat after that.

**Gates** (18 Nov, Windows 3.14, `python -S benchmark.py --runs 9 --gate`, `Docs/budget/step6-win-py314*.json`):
PASS on both inputs. `python -S main.py`: 35.54 us/row SYNTHETIC 180 s (Step 4 merge: 12.62), 30.19 us/row
MH_01_easy_b_s1; heap peak in-process 1,060.0 / 1,232.3 KB, whole run 1,654.3 / 1,818.2 KB (4 MB target
holds). **Whole run with no cached bytecode: 7,337.7 KB** (Step 4 merge: 5,730.7 KB): compiling the longer
`pathfinder.py` costs 1.6 MB more. Under the 8 MB hard limit with 0.8 MB to spare, over the 4 MB target; the
bundle carries cached bytecode (Step 9a), so the shipped run is the 1.8 MB figure. To watch in Step 9.

**Shipped `main.py` scored** (`python tools/eval_euroc.py --tag step6-shipped-clean --main main.py`, `--tag
step6-shipped-official --main main.py --official`; `Docs/RESULTS.md`): on the same 36 held-out copies APE
4.677 m, gap RMSE 4.329, RPE 1 s 0.715, blind RMSE 7.458, reading a 5.757, b 3.597; clean mean 3.555 m:
the reference numbers of the judged run, to the digit.

**Tests changed by shipping it on.** Contracts that are about the filter alone now set the smoother off
(it is a post-pass; with zero corrections it still renormalises each quaternion, a last-bit change):
`test_witness.py` and `test_core_equivalence.py::test_witnesses_off_equals_step_6b` (witnesses off =
plain strapdown); `test_ccore.py` (the C core is frozen before Step F; `SMOOTH_ON` joins the Step F switches
set off in its private copy). `test_main.py::test_memory_gate_bounded_and_flat`: was 15 min at most 64 KB
above 3 min; now 15 min at most 64 KB above 9 min with the smoother (in the suite: 1,515 vs 1,590 KB), and
15 min at most 64 KB above 3 min with it off.
`test_witness.py::test_smooth_default_is_on_and_the_switch_works` replaces the off-by-default test.
Full suite (Windows 3.14): 291 passed, 1 failed (the memory test, then two-sided); after making it
one-sided as before, that test alone: 1 passed (18.5 min, four 3 to 15 min runs under tracemalloc). 292 tests.

**Merged with main** (Step L1 shrinkage, OFF; G1 TUM-VI data): `pathfinder.py` and `witness.py` merged without
conflict (the shrink is a post-pass after the smoothed write). L1 was judged with the smoother off and ships
off, so it was not re-judged. After the merge: the smoother, shrink, TUM-VI, witness, core-equivalence and
main tests: 101 passed (memory test deselected, it was unchanged by the merge); gate PASS
(`Docs/budget/step6m-win-py314.json`; no cached bytecode 7,665.6 KB, the full pre-lean file).

**Merged with the lean pathfinder** (#57: switched-off experiments moved to `tools/pathfinder_lab.py`). The
smoother is ported into both: the lab is this branch's full `pathfinder.py` plus the lab header; the lean
`pathfinder.py` gets the same smoother code, with `_run_smoothed` (store pass, then the writing pass) in
place of `_run_learned` (LEARN is lab-only). `tests/test_smoother_port.py` now checks both against the
reference (caps 1024, 16, 15) and the learned envelope on the lab (8 tests). Lean `pathfinder.py` and the lab
write byte-identical output on MH_01_easy_b_s1, MH_04_difficult_a_s2, V1_03_difficult_b_s3 and clean
MH_03_medium (scratch script); the lab is the pre-merge Step 6 file, so the numbers above stand.
After this merge: **pytest 329 passed** (full suite, Windows 3.14: main's 321 + the 8 smoother port tests).
Gate PASS (`Docs/budget/step6-lean-win-py314*.json`): `python -S main.py` 35.79 us/row SYNTHETIC, 32.01
MH_01_easy_b_s1 (other sessions' tests were running at the same time); heap in-process 1,059.8 / 1,231.8 KB,
whole run 1,632.3 / 1,795.9 KB; **no cached bytecode 5,579.7 KB** (lean without the smoother: 4,934.5; the
smoother's code costs about 645 KB of compile memory). Under the 8 MB limit by 2.5 MB; still over the 4 MB
target when compiled from source.

**Shipped build on the seeds spent by earlier steps** (REPORTED ONLY, not a second judgement: seeds 4-6 were
Step F's held-out copies, 7-9 Step L1's; `eval_euroc --main main.py --official`, tags `step6-H46`,
`step6-H79`; previous shipped-build runs `stepF-H-p0v-refresh`, `stepL1-H-off`; floors on the same copies):

| Copies | APE before -> Step 6 (floor) | reading a | reading b | gap RMSE | blind RMSE |
|---|---|---|---|---|---|
| seeds 4-6 (36) | 4.962 -> 4.648 (3.745) | 6.181 -> 5.782 | 3.744 -> 3.515 | 5.036 -> 4.582 | 6.992 -> 7.559 |
| seeds 7-9 (36) | 4.736 -> 4.516 (3.748) | 5.653 -> 5.445 | 3.820 -> 3.588 | 4.611 -> 4.465 | 6.116 -> 6.574 |

The same pattern as the judged seeds 1-3: APE and gap better, reading b below the floor, reading a above it,
blind worse (+7 to +8 %). `tools/make_numbers.py` SOURCES now point at these runs, `step6-shipped-clean` and
the `step6-lean-win-*` budgets; the TUM-VI sources are Antigravity's G1 runs of the build before the smoother
(labelled so in `Docs/NUMBERS.md`, not re-run here). `SMOOTH_ON` joins `SHIPPED_ON`.

**Merged with main at 77b3641** (PRD v2, NUMBERS.md, the final-set gate, the failure map; no estimator
change): `python tools/make_numbers.py --pytest`: **335 passed** (Windows 3.14). The first such run had 1
failed, 334 passed; it ran while `Docs/NUMBERS.md` was still the one generated from the old SOURCES, and the
recorded summary does not name the test; the NUMBERS, lab, port and final-gate tests then passed (21), and
the full re-run passed. Most likely `test_numbers` against the stale file (not proven).


## Step L1: trust-scaled shrinkage about the centroid (18 Nov 2026, branch `track3/stepL1-shrink`)

**Why.** The organisers fit SE(3) Umeyama on each run. For p_out = c + alpha (p - c), c the centroid of
the estimate (one fixed point per file), the fitted rotation does not depend on alpha, and
APE^2(alpha) = sig_g^2 + alpha^2 sig_p^2 - 2 alpha ||C||_* (sig_g, sig_p the RMS spread of truth and
estimate about their centroids; ||C||_* the nuclear norm, with Umeyama's determinant sign, of their
cross-covariance). alpha = 0 is exactly the never-moving floor, alpha = 1 today's output; the curve is
convex, so the best alpha beats both. **Caveat found in the 18 Nov review:** the fitted rotation also makes
pure noise correlate with the truth (on MH_01/02 tuning copies rho 0.35 / 0.50 for readings a / b against
0.45 / 0.43 for the same estimate reversed in time), so "below the floor after shrinking" is not by itself
evidence of information. Hence a second floor: the estimator's own output with its positions reversed in
time (`tools/eval_euroc.py --reverse`): same spread and smoothness, no information about the flight.

**Piece** (`SHRINK_ON`, default off; reference `vortex/core/shrink.py`, hooked into
`witness.estimate_file`; copied into `pathfinder.py` `_sh_noise` / `_sh_apply` / `_shrink`;
`tests/test_shrink.py`, 23 tests). After the forward pass has written the output, the noise meter reads the
input once more: gyro white-noise sigma per sample from second differences, median of 0.25 s bins over the
20 s that end 5 s before the last timestamp. sigma > `SHRINK_NOISE` = 0.10 rad/s is the high-noise class
(physics, not tuned: clean EuRoC flight reads about 0.04 rad/s, the script's gyro noise at full severity
is 0.015 on reading b and 0.20 on reading a). The output is then rewritten once with the positions scaled
by `SHRINK_ALPHA_LO` (high-noise class) or `SHRINK_ALPHA_HI` (low-noise class) about their centroid;
timestamps and attitude unchanged. alpha = 1 leaves the file byte-identical. Memory: no rows are stored
(two passes over the output file); cost about one extra read of the input and one read + write of the output.

**Tuning (MH_01/02 only;** `python tools/shrink_tune.py`, `Docs/shrink/stepL1-tune.json`). Objective, fixed
before the grid ran: per file 30 APE/APE_f + 20 blind/blind_f + 10 gap/gap_f, x_f the never-moving floor
on the same file, normalised by the weights present (clean files: APE only); the floor scores 60. Meter: the
6 reading-a copies read 0.168..0.178 rad/s (high-noise class), the 6 reading-b copies and clean MH_01/02
0.038..0.042 (low-noise class).

| Class | alpha | Objective (floor 60) | Reversed null | APE m | APE reversed m | Blind RMSE m | Gap RMSE m |
|---|---|---|---|---|---|---|---|
| high noise (6 copies, reading a) | 1.0 (today) | 225.44 | 140.23 | 12.282 | 11.788 | 27.763 | 13.832 |
| high noise | 0 (= floor) | 60.00 | 60.00 | 4.491 | 4.491 | 5.291 | 3.852 |
| high noise | **0.10 (chosen)** | **54.39** | 58.24 | **4.270** | 4.034 | **4.466** | **3.471** |
| low noise (6 copies reading b + 2 clean) | 1.0 (today) | 61.76 | 60.54 | 3.949 | 4.113 | 7.536 | 3.754 |
| low noise | 0 (= floor) | 60.00 | 60.00 | 4.487 | 4.487 | 5.291 | 3.852 |
| low noise | **0.20 (chosen)** | **59.85** | 59.75 | 4.349 | 4.379 | 5.677 | 3.787 |
| low noise | 1.75 (best APE alone) | 66.78 | 64.09 | 3.845 | 4.146 | 9.540 | 3.973 |

Reading. On reading a, alpha 0.10 cuts the objective 76 % against today and 9 % against the floor, and
beats the reversed null (58.24); on APE alone the reversed null is better (4.03 against 4.27 m): the gain over
the null is in the blind window and the gaps. On the low-noise class the landscape is flat (59.85 to 61.76
over alpha 0..1) and the reversed null is level with the estimate: the estimate carries little the scoring
can see beyond its spread. APE alone would want alpha about 1.75 (the estimate is too tight), the blind
window wants 0: one constant cannot serve both (a time-varying alpha is the follow-up, not this step).
End-to-end check (tag `stepL1-tune-on`, `main.py` with `--set SHRINK_ON=True`, the 12 tuning copies): mean
APE 4.270 (a) and 4.350 (b), the same as the tuning script.

**Decision rule, committed before the held-out copies exist** (`tools/judge_stepL1.py`). Held-out H7:
MH_03..05, V1_01..03 x readings a, b x seeds **7, 8, 9** (36 new copies, made with the organisers' script
after this commit). Clean C: MH_01..05, V1_01..03. Tags: `stepL1-H-floor` (never-moving), `stepL1-H-off`,
`stepL1-H-lo` (SHRINK_ON, alpha_lo 0.10, alpha_hi 1.0), `stepL1-H-lo-rev` (same, reversed), then
`stepL1-H-hi` / `stepL1-H-hi-rev` (alpha_hi 0.20, alpha_lo at arm LO's decided value), and `stepL1-C-off`,
`-lo`, `-hi`. Objective per copy as in tuning (the floor run on the same copy). Constants are not changed
after this commit.
- **Arm LO** ships on only if all hold: (1) mean objective over the 18 reading-a copies improves by at least
  2 % against off; (2) at least 5 of the 6 sequences improve (mean over their three seeds); (3) it beats its
  own reversed output on that mean (information beyond what the alignment can fit); (4) the 18 reading-b
  copies are not worse by more than 0.5 %; (5) clean mean APE is not worse by more than 0.5 %; (6) contract
  PASS on every run.
- **Arm HI** (judged against arm LO's decided state): the same conditions on the 18 reading-b copies, (4)
  on the reading-a copies; (5) clean mean APE is reported, not a gate (the organisers score degraded files
  only, and shrinking a clean file costs APE by construction).
- An arm that fails ships with its alpha at 1.0; `SHRINK_ON` ships on if either arm passes.
- Expected from tuning (a prediction, not part of the rule): arm LO passes; arm HI fails condition 3
  (59.85 against 59.75 reversed on tuning).

**Outcome (18 Nov 2026; rule commit d56c875, copies made after it; `python tools/judge_stepL1.py ...`).**
Tags `stepL1-H-*` (36 copies), `stepL1-C-*` (8 clean). Mean objective (floor 60), and reported means:

| Arm | Condition | Result | |
|---|---|---|---|
| LO (alpha_lo 0.10) | 1 reading a objective >= 2 % better | 143.17 -> 72.35 (-49.5 %) | pass |
| | 2 >= 5 of 6 sequences improve | 4 of 6 | **FAIL** |
| | 3 beats its reversed output | 72.35 vs 69.75 | **FAIL** |
| | 4 reading b not worse / 5 clean / 6 contract | +0.00 % / +0.00 % / PASS | pass |
| | reported, reading a: APE / blind / gap m | off 5.653 / 8.972 / 5.829; on 3.821 / 2.793 / 3.375; reversed 3.764 / 3.005 / 3.378; floor 3.748 / 2.505 / 3.256 | |
| HI (alpha_hi 0.20, LO off) | 1 reading b objective >= 2 % better | 77.08 -> 58.66 (-23.9 %) | pass |
| | 2 >= 5 of 6 sequences improve | 3 of 6 | **FAIL** |
| | 3 beats its reversed output | 58.66 vs 60.30 | pass |
| | 4 reading a not worse / 6 contract | -10.9 % / PASS | pass |
| | 5 clean mean APE (reported) | 3.6548 -> 3.8493 m (+5.3 %) | - |
| | reported, reading b: APE / blind / gap m | off 3.820 / 3.259 / 3.394; on 3.684 / 2.436 / 3.165; reversed 3.670 / 2.600 / 3.249; floor 3.748 / 2.505 / 3.256 | |

**Shipped: `SHRINK_ON = False`** (both arms fail; alphas kept at their tuned values in the code, unused).
Shipped output is byte-identical to Step F.

Per sequence, mean objective over seeds 7-9 (floor 60):

| Sequence | Reading | off | LO (0.10) | LO reversed | HI (0.20) | HI reversed |
|---|---|---|---|---|---|---|
| MH_03_medium | a | 138.1 | 59.7 | 61.5 | 138.1 | 123.3 |
| MH_04_difficult | a | 115.3 | 56.4 | 61.0 | 115.3 | 93.0 |
| MH_05_difficult | a | 133.7 | 54.9 | 59.3 | 133.7 | 81.5 |
| V1_01_easy | a | 261.2 | 52.4 | 57.5 | 261.2 | 175.3 |
| V1_02_medium | a | 109.5 | 109.5 | 85.0 | 63.0 | 60.9 |
| V1_03_difficult | a | 101.2 | 101.2 | 94.2 | 54.1 | 62.2 |
| MH_03_medium | b | 55.7 | 55.7 | 58.9 | 58.5 | 59.3 |
| MH_04_difficult | b | 57.6 | 57.6 | 62.6 | 58.4 | 60.2 |
| MH_05_difficult | b | 65.4 | 65.4 | 61.2 | 60.0 | 60.0 |
| V1_01_easy | b | 52.5 | 52.5 | 60.0 | 53.7 | 59.1 |
| V1_02_medium | b | 123.3 | 123.3 | 85.5 | 63.7 | 60.4 |
| V1_03_difficult | b | 108.0 | 108.0 | 99.8 | 57.6 | 62.8 |

**Reading (measured, after the verdict; nothing below changes it).**
- Where a file is shrunk with its class's alpha it lands at or below the floor (52.4..63.7), and the four
  high-noise copies beat their reversed output. The rule fails on consistency across sequences, not on the
  mean.
- **The classifier is the weak point.** The organisers' script guesses the accelerometer unit from the
  median norm of the columns it treats as the accelerometer. On reading a those are the gyro: on V1_02 and
  V1_03 it took them for g and scaled the noise down about 9.8x (copy log `accel g`), so their gyro noise
  reads 0.043 and 0.076 rad/s, in the low-noise class. Reading a is not one noise regime.
- The low-noise class mixes files already better than the floor (MH_03..05 b, V1_01 b: 52.5..65.4, which
  alpha 0.20 moves toward 60) with files much worse than it (V1_02 b 123.3, V1_03 b 108.0, V1_02/03 a). What
  separates them is not gyro noise; a trigger would have to detect a broken estimate. No such GT-free test
  exists in the code yet.
- Not done: a second rule with a different trigger. The only sequences never used are V2_01..03 (final test
  set) and TUM-VI (not downloaded); new seeds of the same six sequences are not new evidence (18 Nov review,
  item 6). Arnav decides.

| Item | Result | Where |
|---|---|---|
| `pytest` | 310 passed (287 + 23 in `tests/test_shrink.py`; g++ on PATH, so `test_ccore.py` ran) | Windows, Python 3.14.7 |
| Reference vs `pathfinder.py` with `SHRINK_ON` | identical to full precision on 12 SYNTHETIC cases (3 files x 4 alpha/threshold settings); meter values exactly equal | `tests/test_shrink.py` |
| Budget, `python -S benchmark.py --runs 15 --gate` (shipped: switch off) | PASS on all three. Heap in-process / whole run / no bytecode: Win 3.14 synthetic 506 / 1,030 / 6,055 KB; Win 3.14 MH_01_easy_b_s1 588 / 1,117 / 6,055 KB; Win 3.13 synthetic 393 / 1,396 / 6,431 KB. Time 15.8, 14.9, 15.5 us/row (3.2, 2.9, 3.1 ms per IMU-s) | `Docs/BUDGET.md` `stepL1-*` |

**Compile heap.** The no-bytecode reading rose 5,512 -> 6,055 KB (3.14) for code that ships off; 3.13 reads
6,431 KB, about 1.4 MB under the 8 MB limit (7,812 KiB if MB means 10^6 bytes). Every switched-off experiment
in `pathfinder.py` (fault pass, learned envelope, INTERP, RESET, now SHRINK) costs compile memory on an
evaluator without our bytecode. Moving them out of `pathfinder.py` (kept in the reference) is the next
efficiency step; not done here.

Not checked: TUM-VI (not downloaded); Linux/WSL timing; how the organisers start tracemalloc (we assume
before `main.py` runs). The reversed-null floor is one realisation per copy.


## Lean pathfinder: switched-off experiments moved to a lab copy (18 Nov 2026, branch `track3/step-lean-pathfinder`)

**Why.** An evaluator without our bytecode compiles `pathfinder.py` while tracemalloc runs, and the
switched-off experiments were compiled with it: the no-bytecode heap reading had grown to 6,055 KB (3.14) and
6,431 KB (3.13) by Step L1 (18 Nov review, item 7).

**Change.** No estimator change.
- `tools/pathfinder_lab.py` (new, not shipped): the full estimator as of dc162ac, with every experiment and its
  switch (fault pass `FF_*`, learned envelope `LEARN_*`, `INTERP_*`, noise meter `JAM_*`, covariance reset
  `RESET_ON` / `_kf_reset`, shrinkage `SHRINK_*`), all off. Re-run an experiment with
  `tools/eval_euroc.py --main tools/pathfinder_lab.py --set NAME=VALUE`.
- `pathfinder.py`: those pieces removed (1,640 -> 1,214 lines). The shipped switches stay (`GAP_ON`, `DEAD_ON`,
  `FC_ON`, `PRE_HOLD`, `CAL_NOISE_ON`, `BGCAP_ON`, `REFRESH_ON`, `P0V_ON`, `FRONT_ON`, V1/V2). The
  reference (`vortex/core`) is unchanged and still holds every experiment.
- Tests of the experiments now run against the lab copy (`test_faults`, `test_shrink`, `test_stepF`, the
  LEARN test in `test_witness`, the JAM test in `test_core_equivalence`, and `test_ccore`, whose frozen C core
  still declares the JAM constants). New `tests/test_lab.py` (7): the experiments are off in the lab and absent
  from `pathfinder.py`; every shared constant is equal; lab with everything off writes byte-identical output on
  five SYNTHETIC files (messy, degraded, move-rest-move, accelerometer-first, empty).

| Item | Result | Where |
|---|---|---|
| `pathfinder.py` vs lab copy (all off), every real input on disk | **byte-identical on all 144** (8 clean EuRoC + 136 official copies; V2 excluded) | scratch script, Windows 3.14 |
| `pytest` | 317 passed (310 + 7 `test_lab.py`; g++ on PATH); 321 after merging `main` with #54 (4 TUM-VI tests) | Windows, Python 3.14.7 |
| Compile peak, `compile()` of the source in-process | 5,640 -> 4,536 KB | Windows 3.14 |
| Budget, `python -S benchmark.py --runs 15 --gate` | PASS on all three. Heap in-process / whole run / no bytecode: Win 3.14 synthetic 506 / 997 / **4,935** KB (Step L1: 6,055); Win 3.14 MH_01_easy_b_s1 587 / 1,084 / **4,935** KB; Win 3.13 synthetic 393 / 1,368 / **6,309** KB (Step L1: 6,431). Time 12.9, 13.2, 13.1 us/row | `Docs/BUDGET.md` `lean-*` |

**Reading.** On 3.14 the no-bytecode reading falls 1.1 MB, back under the 4 MB design target only with the
shipped bytecode (as before) and 3.2 MB under the 8 MB limit without it. On 3.13 it falls only 122 KB: the
3.13 peak has stayed near 6.3 MB since Step 1 (6,310 KB then, with a smaller file), so it does not track the
source size. Not investigated; the largest single function (`_run`, about 600 lines) is a candidate. The time
change (about -15 %) is inside this laptop's run-to-run spread and is not claimed.

Not checked: Linux / WSL; the Docker image (unchanged Dockerfile; `pathfinder.py` content changed, output
identical); what dominates the 3.13 compile peak.

## Step 7: TUM-VI (18 Nov 2026, branch `track3/step7-tumvi`, stacked on Step 6)

Brief: (1) loader check, baseline and floor on room1/room2 in both readings; (2) platform detection
(multirotor or hand-held) from the accelerometer spectrum, right on every sequence on disk and stable at full
severity, V3 forced off on hand-held data; (3) hand-held settings for V1 and the learned envelope, judged on
room3/room4; (4) V5 walking rhythm, time-boxed to one session, rule first, off if no pass.

Data split for this step. Tuning: room1, room2 (clean, official copies seeds 1-3). Held out: room3, room4,
**official copies seeds 7-9** (generated by G1 and not used by anyone; seeds 10-12 and 13-15 belong to rules G and
H of PRD v2) and clean room3/room4. G1 already ran the build before Step 6 on room3/room4 seeds 1-3 and on clean
room3..6 (baseline only, nothing tuned on them). Rooms 5 and 6 and Vicon Room 2 are not read in this step
(the final table runs "any untouched TUM-VI rooms").

**1. Loader check** (`data/tumvi/dataset-room1_512_16`, `room2`): EuRoC export, header `w_RS_S_* [rad s^-1],
a_RS_S_* [m s^-2]`, rad/s and m/s^2; 200 Hz (median step 5.016 ms, range 4.995 to 5.037 ms); 141 s and 144 s;
ground truth in `mav0/mocap0/data.csv` (confirmed). The rooms never start still: in the first 5 s |gyro| is
0.06 to 0.22 rad/s (hand tremor), then walking. The still test never fires (calibration falls back, 0 ZUPT
ticks), so V1 does nothing on TUM-VI and the gyro bias starts at 0.

Baseline (`main.py` with Step 6, `python tools/eval_euroc.py --root data/tumvi [--official]`, tags
`step7-tune-clean`, `step7-tune`; floor `tumvi-floor-*` from G1):

| room1/room2 | APE SE3 m | gap RMSE m | RPE 1 s m | blind RMSE m |
|---|---|---|---|---|
| official seeds 1-3, 12 copies: estimator / floor | 1.927 / 1.110 (a 1.909, b 1.945) | 1.671 / 1.063 | 1.009 / 1.438 | 3.988 / 0.677 |
| clean: estimator / floor | 0.866, 0.934 / 1.00, 1.22 | - | 0.293, 0.919 | - |

On degraded hand-held data the shipped (drone) settings lose to standing still.

**2. Platform detector** (`vortex/core/platform.py`, ported as `_plat_stat` / `_plat_hh`): per 1 s window the
mean squared second difference of the accelerometer, (m/s^2)^2 (rotor vibration is near Nyquist; walking is at
1 to 3 Hz, where the second difference is almost zero); the 0.75 quantile over the windows of the whole file
(EuRoC flights start with the drone carried by hand, so the opening looks hand-held); hand-held below
`PLAT_HF` = 1.0. Tuning files (EXPLORATORY): MH_01/02 flight windows 5 to 6, MH_01 file statistic 6.48;
TUM-VI room1 clean 0.0024, at most about 0.18 in the last 30 s of reading b. V3 is not built (Step 5), so
"V3 off on hand-held" holds trivially.

**3. Hand-held settings.** When `PLATFORM_ON` and the file is hand-held, the V2 speed and V2P volume envelope
use `HH_*` (also for the initial velocity sigma when there is no still run, P0V). Sweep on room1/room2 (12
official copies + 2 clean, `--set`, tags `step7-grid-*`, EXPLORATORY): degraded mean APE base 1.927; speed h
0.5: 1.017; volume h 0.5 / 1 / 2: 1.015 / 1.205 / 1.525; volume v 0.3: 1.948; speed v 0.1: 2.740; tau 3 / 30:
3.534 / 1.417; second round around the best: 0.87 to 0.97 for every neighbour; chosen **speed h 0.5 m/s,
speed v 0.3 (unchanged), volume h 1.0 m, volume v 0.3 m, tau 30 s**: degraded 0.871 (room1 0.603 vs floor
1.002, room2 1.139 vs 1.218), gap 0.877, blind 0.953, clean 0.407 / 1.094. The learned envelope
(`LEARN_ON`, lab): 0.931 alone, 0.927 on top of the chosen values: not taken (worse, and lab-only).
V1: not changed. The still test never fires on these rooms; the only looser variant (`ZUPT_DEN_ON`, failed
in step 7b) exists in the reference only; a hand-held quasi-static ZUPT was not built in this step.

**Decision rule, committed before the detector is run outside the tuning files and before any run on room3/
room4 seeds 7-9.** `PLATFORM_ON` with the values above (frozen) ships on only if all hold:
- A. Detector: right on every file on disk outside the final sets: clean MH_01..05, V1_01..03, room1..room4,
  and every official copy of them on disk (`data/official`, `data/official_tumvi`, both readings, all seeds):
  multirotor for EuRoC, hand-held for TUM-VI. Reported: smallest EuRoC and largest TUM-VI statistic.
- B. Held out (room3, room4; official copies seeds 7-9, readings a and b: 12 copies; `main.py` off and on):
  1. mean APE improves by at least 10 %; 2. mean gap RMSE improves by at least 5 %; 3. paired: each room's
  mean APE (its 6 copies) improves; 4. clean room3/room4 mean APE not worse by more than 5 %.
- C. EuRoC unchanged: follows from A (multirotor takes the unchanged path; `tests/test_platform.py` checks
  byte identity on SYNTHETIC files); also checked byte-identical on real EuRoC copies.
Reported, not deciding: per reading, RPE 1 s, blind RMSE, the never-moving floor on the same copies.
`python tools/judge_step7.py`. No constant changes after this commit.

**Outcome** (18 Nov; `python tools/platform_check.py`, then `python tools/judge_step7.py`; `Docs/tumvi/step7-*.json`):

| Condition | Value | Result |
|---|---|---|
| A detector right on every non-final file | 328 files, 0 wrong; smallest multirotor 5.376, largest hand-held 0.160 (threshold 1.0) | pass |
| B1 held-out mean APE improves >= 10 % | 1.994 -> 1.127 m (-43.5 %) | pass |
| B2 held-out mean gap RMSE improves >= 5 % | 1.800 -> 1.113 m (-38.2 %) | pass |
| B3 each room improves | room3 2.275 -> 1.228, room4 1.713 -> 1.027 | pass |
| B4 clean room3/4 not worse by > 5 % | 1.044 -> 1.008 m (-3.4 %) | pass |
| C EuRoC byte-identical with the switch | 6 of 6 copies; the detector statistic inside `main.py` equals the check's on all 6 | pass |

**Verdict: `PLATFORM_ON` ships ON** (reference, `pathfinder.py`, lab).

**Part A needed a fix to the check tool, said plainly.** The first run of `tools/platform_check.py` gave 86 wrong
files, all EuRoC reading-b copies, smallest "multirotor" 0.009: the tool called the detector on the raw file,
and reading b has the accelerometer first, so it measured the gyro columns. `main.py` runs the input front end
first (`run()` -> canonical rewrite -> `_run_smoothed` -> detector), so the estimator was not affected: the
same run showed MH_01 reading-b copies byte-identical with the switch on, which needs a multirotor call. The
tool now goes through the front end exactly as `run()` does and records the statistic `main.py` computes
itself on the identity copies (equal on 6 of 6). No constant or estimator code changed between the rule
commit and the verdict. The first run's output is kept outside the repository (scratch), not in `Docs/`.
Also: 280 files on the first run, 328 on the second (official copies added on disk meanwhile by another session).

Reported only (off -> on; never-moving floor on the same 12 copies): APE reading a 2.029 -> 1.126 m (1.164),
reading b 1.959 -> 1.129 (1.164); RPE 1 s 1.050 -> 1.024 (1.265); blind RMSE 4.687 -> 1.277 (0.739); gap RMSE
1.800 -> 1.113 (1.076). Clean: room3 0.702 -> 1.085 m (**+55 %**), room4 1.385 -> 0.930 (-33 %).

**Reading.** On degraded hand-held data the shipped drone envelope lost to standing still by 70 %; the hand-held
envelope brings it to a tie with the floor (1.127 against 1.164 m), not a clear win. The blind 5 s is still
worse than standing still (1.28 against 0.74 m): Step 8. Clean room3 gets much worse; room4 better. The
shipped build on room1..4 seeds 1-3 (reporting, `step7-shipped-tumvi`): tuning rooms 0.871 m (floor 1.110),
held-out rooms 1.109 m (floor 1.164; build before Step 6: 2.599).

**Cost and gates** (Windows, i7-14650HX, 9 runs each, `python -S benchmark.py --gate`; `Docs/budget/step7-*.json`;
all GATE PASS, output check PASS): heap peak / whole run / whole run without cached bytecode (KB), `python -S main.py`
us/row:
- synthetic (hand-held path), Python 3.14: 1,060 / 1,639 / 5,803; 37.2 us/row (Step 6 lean: 1,060 / 1,632 / 5,580; 35.6)
- MH_01_easy_b_s1 (multirotor path), 3.14: 1,232 / 1,802 / 5,802; 31.0 us/row
- dataset-room1_512_16_b_s1 (hand-held path), 3.14: 861 / 1,427 / 5,802; 43.9 us/row (the slowest; under 50)
- synthetic, Python 3.13: 940 / 2,252 / 6,309; 35.2 us/row
The detector adds one pass over the file: synthetic +1.6 us/row against Step 6 (not separated from run-to-run noise); no-cache heap +223 KB (larger module).

V1 hand-held: not changed (see above).

**After merging main (19 Nov, L2 `TILT_ON` shipped meanwhile; reporting only, nothing decided).** Step 7 was judged
without `TILT_ON` and rule G2 without `PLATFORM_ON`; the combined build (tags `step7m-*`) was run on the same copies:
- TUM-VI: equal to Step 7 alone on every metric to the third decimal (rooms 1-4 seeds 1-3: tuning 0.871 m, held-out
  rooms 1.109 m; room3/4 seeds 7-9: APE 1.127, gap 1.113, blind 1.277 m; clean 0.879 m). L2 does not move the
  hand-held path.
- EuRoC held-out, seeds 4-6: APE 4.648 (Step 6) -> 3.480 m (floor 3.745), gap 4.582 -> 3.513 (3.626), blind 7.559 ->
  3.017 (2.504); seeds 7-9: APE 4.516 -> 3.566 (3.748), gap 4.465 -> 3.289 (3.256), blind 6.574 -> 3.110 (2.505).
  Clean MH/V1: 3.555 -> 3.570 m (floor 3.930). Seeds 4-9 were spent before L2 (reporting only).
- Cost (all GATE PASS; heap peak / whole run / whole run without cached bytecode, KB; us/row): MH_01 b s1
  1,234 / 1,816 / **7,188**; 28.6. room1 b s1 863 / 1,440 / 7,188; 33.4. Synthetic 3.14 1,062 / 1,652 / 7,188; 35.8.
  Synthetic 3.13 942 / 2,264 / **7,551**; 31.0.
- **The no-bytecode heap rose about 1.4 MB (5,802 -> 7,188 KB), 0.9 MB of it from a parser threshold, not from the algorithm.** Compiling
  `pathfinder.py` from source peaks at 5,876 KB for main, 5,428 KB for Step 7 alone, 6,748 KB merged (Python 3.14).
  The merged file has 16,490 parser tokens, main 15,747; CPython's parser grows its token array by doubling, and
  padding main's file with filler lines moves the compile peak from 5,820 to 6,743 KB exactly between 16,367 and
  16,387 tokens. The next doubling is at 32,768 tokens; below that, growth is about linear. Headroom to the 8 MB
  hard limit on Python 3.13 is now about 0.45 MB. The gated algorithm heap (about 1.2 MB) is unaffected. Not
  fixed here: getting back under 16,384 tokens needs about 110 fewer tokens with no margin, or a second module.

**4. V5 walking rhythm (19 Nov, time-boxed to one session): stopped at feasibility on the tuning rooms; OFF, not
built.** No held-out data and no seed was used; no rule was registered, because nothing reached a candidate
setting. `python tools/v5_feasibility.py` (room1/room2 clean; reads mocap ground truth to judge the signals, an
analysis tool, never an estimator input; `Docs/tumvi/v5-feasibility.json`):
- Rhythm: present. A clear vertical-force peak in 87 % (room1) and 89 % (room2) of 4 s windows, at 1.00 and 1.75 Hz.
  It says "walking", not "how fast": correlation with ground-truth speed is weak (step rate -0.12 / +0.17, bounce
  +0.37 / +0.19), because the walker keeps an almost constant pace (mean about 1 m/s).
- Direction (the plan's method: principal axis of the horizontal acceleration). Tested in the best case, with the
  ground-truth attitude, against the ground-truth direction of travel (windows with mean speed >= 0.4 m/s; a
  random axis gives median |cos| 0.71). Room1: 0.70 to 0.79 for 2 s and 4 s windows, raw or band-passed at the step
  frequency: chance. Room2: 0.88 (2 s) and 0.99 (4 s, 19 windows of straight walking) raw, but 0.69 / 0.70 band-
  passed: the axis comes from the walk's own speed changes on straight legs, not from the gait, and the windows
  were picked with the ground-truth speed. With the filter's own attitude and the official noise it can only be
  worse.
- Speed (shipped build): room1 0.82 to 0.83 m/s against ground truth 0.96 (close); room2 0.24 to 0.29 against 1.07
  (far too slow). So room2 has speed error a walking witness could remove, but only with a usable direction.
Reading: a V5 velocity witness needs a direction, and the specified one carries none on room1 and only a selected
subset on room2. Building the filter update, the port and a held-out rule on top would spend the time-box (and a
seed set) on a feature that cannot pass. A speed-magnitude-only variant (along the filter's own velocity) was not
built: on room2 the filter's direction is as unreliable as its speed.



## Step L2: slow gravity alignment with a gyro noise meter (18-19 Nov 2026, branch `track3/stepL2-tilt`)

**Why.** Under reading a the organisers' script puts accelerometer-sized faults on the gyro columns (white
0.20 rad/s per sample, bias walk 0.010 rad/s/sqrt(s), spikes up to 6 rad/s, all times the severity ramp) and
gyro-sized faults on the accelerometer, so attitude from the gyro is lost while the accelerometer stays nearly
clean. Measured on the tuning copies (`tools/tilt_eval.py`, roll/pitch error against ground truth, MH_01/02 x
seeds 1-3): 9.4 deg RMS under reading a, 1.2 deg under reading b, 0.9 deg clean.

**Piece** (`TILT_ON`, default off; reference `vortex/core/witness.py`, copied into `pathfinder.py`;
`tests/test_tilt.py`, 15 tests). Not the instantaneous accelerometer tilt (on a multirotor the accelerometer
reads thrust along body z plus drag): over a window the vehicle's mean acceleration is near zero, so the mean
world-frame specific force (body specific force rotated by the current attitude estimate) must point along +z.
- Window: an exponential average over the 0.25 s ticks with time constant `TILT_TAU`; O(1) memory (3 + 2 + 2
  floats). After every injected correction the stored mean is rotated by the attitude correction and, with
  `TILT_LAG`, shifted for the gyro-bias correction, so nothing is measured twice.
- Measurement: F_hat = F_true - dth x F_true, so dth_x = F_y / g, dth_y = -F_x / g (world-frame error,
  q_true = Exp(dth) q; sign checked against exact rotations in the tests). `TILT_LAG`: an exponential mean of an
  error ramping at -R dbg lags by tau, so the row is dth + tau R dbg (the gyro-bias states become directly
  observable). Two sequential scalar updates per tick, variance `TILT_R_K` x (window spread / g^2 x tick / tau
  + (`TILT_DV` / (g tau))^2) / w.
- Gate: no update while the filter's own window-mean horizontal acceleration exceeds `TILT_GATE_A` = 0.5 m/s^2.
- Gyro meter: per-sample white-noise sigma from second differences of the raw gyro, median over the last
  `TILT_MED_TICKS` = 40 ticks (spikes do not count), weight 0 until the ring is full. Weight w rises from 0 at
  `TILT_G_LO` = 0.05 rad/s to 1 at `TILT_G_HI` = 0.10 (clean EuRoC flight reads about 0.04, reading a at full
  severity 0.17-0.20; Step L1 meter). With w = 0 the output is unchanged to the bit (test). With w > 0 the gyro
  white-noise density rises toward the measured one and the gyro bias-walk density toward `TILT_WALK_K` = 0.7
  times it (the script's own walk / white ratio for those faults).
- Deviation from the brief, said plainly: the brief asked for a window of 10-20 s and a meter against "its
  calibration floor". Tuning chose 4 s (below), and the meter uses absolute thresholds, because the calibration
  rest reads far below the rotor vibration in flight, so a ratio to it would mark every clean flight as jammed.

**Synthetic checks** (`tests/test_tilt.py`). Sign conventions against exact rotations; window rotation to
second order; spike robustness of the meter; clean gyro: output identical with the switch on; steady 15 deg
banked circle with a drag-like pitch offset (instantaneous accelerometer tilt wrong by about 15 deg), weight
forced to 1: tilt error stays within the stated bias (2.9 deg at 4 s) plus 1 deg (measured max 2.8 deg); jammed
gyro + clean accelerometer: tilt RMS below 0.75 x off and below 4.5 deg; reference and `pathfinder.py` agree to
full precision on 6 cases (jammed, clean forced, degraded forced x `TILT_LAG` on/off), each with the update
actually firing.

**Tuning (MH_01/02 only;** `python tools/tilt_tune.py`, tables in `Docs/tilt/stepL2-*.md`, generated). Probe 1
(`stepL2-probe1`) ran an earlier meter (weight allowed from the first tick) without the lag model; probes 2 and 3
and the final pass run the committed code. Means over 6 copies per reading, reading a:

| Setting | APE m | RPE 1 s m | Gap RMSE m | Blind RMSE m | Tilt RMS deg |
|---|---|---|---|---|---|
| off (shipped) | 12.282 | 1.204 | 13.832 | 27.763 | 9.42 |
| no lag model, R_K 0.1, tau 12 s (probe 1) / 6 / 4 s (probe 2) | 14.880 / 6.761 / 5.076 | 1.681 / 1.052 / 0.838 | 16.54 / 6.80 / 5.19 | 25.72 / 8.83 / 7.25 | 5.62 / 4.01 / 3.39 |
| lag model, R_K 0.1, tau 12 / 6 / 4 / 3 / 2 s (probes 2-3) | 4.544 / 3.890 / 3.690 / 3.593 / 3.560 | 0.713 / 0.623 / 0.579 / 0.560 / 0.551 | 4.47 / 3.75 / 3.50 / 3.39 / 3.39 | 6.21 / 6.41 / 6.78 / 6.59 / 6.56 | 5.41 / 4.30 / 3.61 / 3.12 / 2.68 |
| **chosen: lag, tau 4 s, R_K 1, walk 0.7, meter 0.05 / 0.10** | **3.687** | **0.583** | **3.505** | **6.726** | **3.46** |
| same, output reversed in time (null) | 4.666 | 0.582 | 4.236 | 7.210 | - |
| never-moving floor (Step E2, MH_01/02) | 4.491 | - | 3.852 | 5.291 | - |

Other settings at tau 4 s: R_K 0.1 3.690, walk ratio 0.35 / 1.4 3.877 / 3.613, meter 0.07 / 0.12 5.041 m.
Reading b, clean MH_01/02 and the TUM-VI tuning rooms (room1/2 x a, b x seeds 1-3) are **identical** with the
switch on in every setting (the meter keeps the weight at 0): reading b 3.973, clean 3.878, TUM-VI a / b
2.001 / 2.054 m. Tau 4 s rather than the best 2 s: below 4 s the acceleration gate blocks every update in the
synthetic banked circle, so 2-3 s acts only where the flight is gentle; 4 s is within 4 % of the best.

**Reading (tuning only, not evidence).** On reading a the estimate goes from about 3x worse than standing still
to below it (3.69 against 4.49 m), and below its own reversed output (4.67), with RPE 1 s halved and tilt
error from 9.4 to 3.5 deg: the attitude, and with it some of the motion, is recovered, not just the spread
fitted. The blind 5 s is still worse than the floor (6.73 against 5.29 m): that is L3's job. TUM-VI: the
estimator is worse than its floor there with or without L2 (2.0 against 1.1 m; Antigravity's baseline), and L2
does not touch it.

**Also changed.** `tools/pathfinder_lab.py` carries L2 too (its meter is the JAM meter's second-difference sums,
now accumulated when JAM or TILT is on), so the lab stays a superset of `pathfinder.py`; with TILT_ON it writes the
same bytes as `pathfinder.py` (test). New tools: `tools/ref_main.py` (the reference as a main script, for tuning
with `--set`), `tools/tilt_eval.py`, `tools/tilt_tune.py`, `tools/judge_stepG.py` (+ `tests/test_judge_stepG.py`,
10 tests on synthetic tables).

| Item | Result | Where |
|---|---|---|
| Shipped output (TILT_ON off) vs the lean `main` (ed147f0) | **byte-identical on all 246** real non-V2 inputs (8 clean EuRoC, 136 official EuRoC copies, 6 TUM-VI rooms, 96 official TUM-VI copies) | scratch script, Windows 3.14 |
| `pytest` | 348 passed (321 on the lean branch + 17 `tests/test_tilt.py` + 10 `tests/test_judge_stepG.py`; g++ on PATH) | Windows, Python 3.14.7 |
| Budget, `python -S benchmark.py --runs 15 --gate` (shipped: TILT_ON off) | PASS on both. Heap in-process / whole run / no bytecode: synthetic 506 / 1,008 / 5,362 KB; MH_01_easy_b_s1 587 / 1,095 / 5,362 KB. Time 15.3 and 11.5 us/row (3.06 and 2.23 ms per IMU-s) | `Docs/BUDGET.md` `stepL2-*` |
| Cost of TILT_ON | about +1 us/row on MH_01_easy_a_s1 (10.0 / 13.0 off, 11.5 / 12.6 on, two runs each: inside this laptop's spread). Rule G condition 9 runs the gate with TILT_ON | scratch timing, Windows 3.14 |

**Compile heap.** The no-bytecode reading rose 4,935 -> 5,362 KB (3.14) with the L2 code, which ships off
until rule G decides. Under the 8 MB limit; above the 4 MB design target, as before Lean. If L2 fails rule G it
moves to the lab (L4), and the reading falls back.

Not checked: Win 3.13 and Linux gates; TUM-VI attitude error (the ground-truth reader is EuRoC-only, so TUM-VI is
APE only); whether the gate (`TILT_GATE_A`) ever blocks an update on the real tuning flights (not logged).

**Decision rule G, committed before the held-out copies exist** (`tools/judge_stepG.py`; constants frozen in
this commit; no constant changes after it). Held-out H: MH_03..05, V1_01..03 x readings a, b x seeds **10, 11,
12** (36 copies, made with the organisers' script after this commit). These are 6 flights, not 36: seeds and
readings re-use the same trajectories, so the sequence-level condition pools each sequence's 6 copies. TUM-VI
block T: room3, room4 x a, b x seeds 10-12 (12 copies Antigravity made on 18 Nov; never run by Claude Code).
Clean C: MH_01..05, V1_01..03; clean TUM-VI CT: room1..4. Tags `stepG-H-floor`, `stepG-H-off`, `stepG-H-on`,
`stepG-H-on-rev` (on, positions reversed in time), `stepG-C-off/-on`, `stepG-T-off/-on`, `stepG-CT-off/-on`.
`TILT_ON` ships on only if all hold:
1. mean APE (SE3 fitted on the run) over H improves by at least 2 %;
2. the paired gain is positive on at least 4 of the 6 sequences (mean over each sequence's 6 copies);
3. in each reading separately, mean APE over its 18 copies is not worse by more than 1 %;
4. mean gap RMSE and mean blind RMSE over H are each not worse by more than 2 %;
5. clean mean APE is not worse by more than 0.5 % (C, and separately CT);
6. TUM-VI block T: mean APE not worse by more than 1 %;
7. mean APE over H with TILT_ON beats the same output reversed in time (Step L1 null floor);
8. output contract PASS on every run;
9. `python -S benchmark.py --runs 15 --gate` PASS with TILT_ON = True.
Reported beside the verdict: the never-moving floor, RPE 1 s, each sequence's paired effect and the
sequence-level spread. A gain is called "better aligned APE" unless RPE 1 s improves too.
Expected from tuning (a prediction, not part of the rule): reading b and clean unchanged (the meter keeps the
weight at 0 there); reading a improves on MH_03..05 and V1_01; V1_02 a and V1_03 a may not move, because the
organisers' script scaled their gyro noise down (Step L1: meter 0.043 and 0.076 rad/s), so condition 2 is the
risk.

**Outcome (18 Nov 2026, late evening; rule commit 5fd288c; the seed 10-12 copies were made after it;
`python tools/judge_stepG.py ... --gate PASS`, output kept in `Docs/results/stepG-verdict.txt`).** Tags
`stepG-H-*` (36 copies), `stepG-C-*` (8 clean), `Docs/tumvi/stepG-T-*` (12 TUM-VI copies), `stepG-CT-*` (4 clean
rooms). Gate with TILT_ON (condition 9, a scratch copy with `TILT_ON = True`): PASS on synthetic (heap 1,004 KB,
12.1 us/row) and MH_01_easy_a_s1 (1,094 KB, 9.3 us/row); no-bytecode 5,357 KB.

| Condition | Result | |
|---|---|---|
| 1 H mean APE improves >= 2 % | 4.935 -> 3.743 m (-24.15 %) | pass |
| 2 paired gain > 0 on >= 4 of 6 sequences | 5 of 6 (V1_02 unchanged: +0.0 %) | pass |
| 3 reading a / b not worse by > 1 % | -36.86 % / -4.88 % | pass |
| 4 gap / blind RMSE not worse by > 2 % | -29.61 % / -52.67 % | pass |
| 5 clean EuRoC / clean TUM-VI | -0.464 % / +0.000 % | pass |
| 6 TUM-VI block (room3/4) | 2.545 -> 2.545 m (+0.00 %) | pass |
| 7 beats its own reversed output | **3.743 vs 3.735 m** | **FAIL** |
| 8 contract PASS | 156 runs | pass |
| 9 benchmark gate with TILT_ON | PASS | pass |

**Shipped: `TILT_ON = False`.** Shipped output is byte-identical to the lean `main`. Seeds 10-12 are spent.

**Base, said plainly (added 18 Nov after the G2 run, at Arnav's request; nothing in rule G changes).** Rule G
was judged on 5fd288c, before the Step 6 smoother; the verdict applies to that build. 5fd288c sits on ed147f0
(the lean re-land); `SMOOTH_ON` does not exist in it, and #58 reached `main` (d1fc504) after the rule G runs.
Every `stepG-*` tag records commit 5fd288c. That build no longer exists on `main`.

Per sequence and reading, mean over seeds 10-12 (APE m; blind RMSE m):

| Sequence | Reading | off | on | on reversed | floor | blind on | blind floor |
|---|---|---|---|---|---|---|---|
| MH_03_medium | a | 8.208 | 3.969 | 3.684 | 3.583 | 3.188 | 3.085 |
| MH_03_medium | b | 3.518 | 3.518 | 3.340 | 3.583 | 2.997 | 3.085 |
| MH_04_difficult | a | 7.761 | 6.299 | 6.621 | 6.814 | 4.404 | 3.851 |
| MH_04_difficult | b | 6.533 | 6.533 | 6.564 | 6.814 | 3.774 | 3.851 |
| MH_05_difficult | a | 10.346 | 6.499 | 6.693 | 6.868 | 4.189 | 4.061 |
| MH_05_difficult | b | 6.546 | 6.546 | 6.604 | 6.868 | 4.419 | 4.061 |
| V1_01_easy | a | 4.738 | 2.071 | 2.107 | 1.854 | 1.426 | 1.724 |
| V1_01_easy | b | 1.874 | 1.874 | 1.740 | 1.854 | 1.868 | 1.724 |
| V1_02_medium | a | 2.108 | 2.108 | 2.030 | 1.779 | 2.656 | 1.043 |
| V1_02_medium | b | 2.261 | 2.261 | 2.126 | 1.779 | 3.743 | 1.043 |
| V1_03_difficult | a | 2.529 | 1.589 | 1.647 | 1.580 | 1.548 | 1.269 |
| V1_03_difficult | b | 2.798 | 1.650 | 1.666 | 1.580 | 2.029 | 1.269 |

Sequence-level paired gain: mean +24.8 %, sd 16.8 % (n = 6). Means by reading, on / reversed / floor: a 3.756 /
3.797 / 3.746; b 3.730 / 3.673 / 3.746. RPE 1 s over H 0.931 -> 0.869.

**Reading (measured, after the verdict; nothing below changes it).**
- L2 removes the reading-a failure: reading a goes from 5.95 m to 3.76 m, level with standing still (3.75), and
  the blind 5 s over H from 6.38 to 3.02 m (floor 2.50). It does not get below the floor on held-out data, unlike
  on tuning (3.69 against 4.49). The tuning gain below the floor did not carry over.
- Condition 7 fails on the pooled mean. On reading a, where L2 acts, it beats its reversed output (3.756 against
  3.797); on reading b the estimate, mostly unchanged by L2, already loses to its reversed output (3.730 against
  3.673). The null says the shipped estimator's motion on reading b carries no more than what the alignment can
  fit, which is the Step L1 finding again. The rule pooled both readings, as written.
- As predicted, V1_02 did not move (meter below 0.05 rad/s on both readings). Not predicted: V1_03 b moved
  (2.798 -> 1.650 m): its gyro meter reads above 0.05 on reading b too (aggressive flight vibration plus the
  script's noise), so L2 acted there and helped.
- Called "better aligned APE", not motion recovered: the rule did not pass, and APE ends at the floor.
- Not done: any revised rule. Seeds 16-18 are the only reserve (one re-judge of one revised variant with a new
  rule). Rule H (L3) was planned on seeds 13-15. Arnav decides.

### Rule G2 (Step L2 re-judge, seeds 16-18): **written after seeing rule G's result; weaker evidence; same 6 flights**

Arnav's decision (18 Nov, late evening): one re-judge of L2 on the last reserve, with a revised null, committed
before the seed 16-18 copies exist. `TILT_*` constants are unchanged since rule G (5fd288c); nothing was tuned
after rule G. `tools/judge_stepG2.py` (+ `tests/test_judge_stepG2.py`, 7 tests on synthetic tables).

**Base changed, said plainly.** Since rule G, `main` shipped the Step 6 smoother ON (#58, judged on seeds 1-3).
Rule G judged L2 without it. G2 judges L2 on the base that ships: this branch with `main` merged
(`SMOOTH_ON = True`). After the merge, reference = `pathfinder.py` with TILT_ON + smoother on 6 synthetic cases,
the lab = `pathfinder.py` with TILT_ON, and the shipped output (TILT_ON off) is checked byte-identical to `main` (result recorded with the outcome).

**Base by hash (stated 18 Nov after the G2 run, at Arnav's request; it names the build the paragraph above
already described and changes no condition).** Rule G2 judges 3e2646e: the merge of `main` at d1fc504 (Step 6
smoother ON) into Step L2, with every `TILT_*` constant as at 5fd288c; TILT_ON set per run with `--set`. Every
`stepG2-*` tag records commit 3e2646e. Rule G2 is not changed after this point, whatever the re-measurement
below shows.

Held-out H: MH_03..05, V1_01..03 x readings a, b x seeds **16, 17, 18** (36 copies, made after this commit).
TUM-VI block T: room3, room4 x a, b x seeds 16-18 (12 copies, made by Claude Code after this commit; Antigravity
had made seeds 1-3 and 7-15 only). Clean C: MH_01..05, V1_01..03; clean TUM-VI CT: room1..4. Tags `stepG2-H-floor`,
`stepG2-H-off`, `stepG2-H-on`, `stepG2-H-off-rev`, `stepG2-H-on-rev`, `stepG2-C-off/-on`, `stepG2-T-off/-on`,
`stepG2-CT-off/-on`. `TILT_ON` ships on only if all hold:
- Conditions 1-6, 8, 9: identical to rule G, same thresholds (H APE >= 2 % better; >= 4 of 6 sequences; each
  reading not worse by > 1 %; gap and blind not worse by > 2 %; clean EuRoC and clean TUM-VI not worse by
  > 0.5 %; TUM-VI block not worse by > 1 %; contract PASS on every run; benchmark gate PASS with TILT_ON).
- **7 (replaced): difference-in-differences null.** The gain mean_H(APE off - APE on) must exceed the same gain
  on both outputs reversed in time, mean_H(APE off-reversed - APE on-reversed). It asks whether L2's gain needs
  the right time order, which is what the null is for; rule G's form compared levels, and failed on reading b
  copies that L2 mostly does not touch.
- **10 (new): no reading-b sequence worse by more than 2 %** (mean of its 3 seeds, on against off). V1_03 b fired
  unexpectedly under rule G, so the switch must not hurt where it fires on reading b.
If G2 fails, `TILT_ON` stays off for good and the reserve is spent. L3 (rule H, seeds 13-15) is judged only
after G2 is decided, on whichever base ships; if G2 passes, rule H names `TILT_ON = True` as its base.
Prediction (not part of the rule): conditions 1-4 pass as under rule G (the smoother may shrink the margins);
condition 7 is the open question.

**Outcome of rule G2 (18 Nov 2026, late evening; rule commit 3e2646e; the 48 seed 16-18 copies were made after
it; `python tools/judge_stepG2.py ...`, output in `Docs/results/stepG2-verdict.txt`).** Base: `main` with the
smoother ON, merged into this branch; with TILT_ON off the merged branch is byte-identical to `main` on all 282
real non-V2 inputs on disk at the time. Gate with TILT_ON (condition 9): PASS on synthetic (heap 1,641 KB with
bytecode, 6,027 KB without; 30.5 us/row) and MH_01_easy_a_s1 (1,805 KB; 28.0 us/row), both measured while another
evaluation was running, so the times are pessimistic.

| Condition | Result | |
|---|---|---|
| 1 H mean APE improves >= 2 % | 4.922 -> 3.575 m (-27.36 %) | pass |
| 2 paired gain > 0 on >= 4 of 6 sequences | 5 of 6 (V1_02 unchanged) | pass |
| 3 reading a / b not worse by > 1 % | -42.18 % / -0.83 % | pass |
| 4 gap / blind RMSE not worse by > 2 % | -28.83 % / -57.48 % | pass |
| 5 clean EuRoC / clean TUM-VI | +0.422 % / +0.000 % | pass (EuRoC close to its 0.5 % limit) |
| 6 TUM-VI block (room3/4) | 2.136 -> 2.136 m (+0.00 %) | pass |
| 7 gain exceeds the gain on reversed outputs | 1.347 vs 1.187 m | pass |
| 8 contract PASS | 192 runs | pass |
| 9 benchmark gate with TILT_ON | PASS | pass |
| 10 no reading-b sequence worse by > 2 % | worst +0.00 % (V1_03 b improves 1.574 -> 1.398) | pass |

**Shipped: `TILT_ON = True`** (reference, `pathfinder.py`, lab copy). Seeds 16-18 are spent; no seed reserve is
left for L2.

Means by reading over seeds 16-18 (APE m; blind and gap RMSE m):

| Reading | off | on | on reversed | off reversed | floor | blind on / floor | gap on / floor |
|---|---|---|---|---|---|---|---|
| a | 6.315 | 3.651 | 3.881 | 6.217 | 3.746 | 3.100 / 2.506 | 3.591 / 3.453 |
| b | 3.528 | 3.499 | 3.802 | 3.840 | 3.746 | 3.213 / 2.506 | 3.364 / 3.453 |
| both | 4.922 | 3.575 | 3.841 | - | 3.746 | 3.156 / 2.506 | 3.478 / 3.453 |

**Reading (measured, after the verdict; nothing below changes it).**
- On these seeds, and with the smoother, the estimate is below the never-moving floor on both readings
  (3.651 and 3.499 against 3.746) and below its own reversed output on both (rule G's level null would also have
  passed here: 3.575 against 3.841). Under rule G (seeds 10-12, no smoother) the same L2 ended level with the
  floor. Seeds and the smoother both changed between the two judgements, so the difference cannot be assigned
  to either; the seeds re-use the same 6 flights.
- Weaker evidence, said plainly: G2's condition 7 was chosen after rule G's result was known. The other
  conditions are rule G's, unchanged, and they passed on copies made after G2 was committed.
- The blind 5 s is still worse than the floor (3.16 against 2.51 m): L3's job. Gap RMSE is level with it.
- Clean EuRoC moved +0.42 %, all of it from one flight: clean V1_03_difficult 1.222 -> 1.342 m (+9.8 %); the
  other 7 clean sequences are identical (meter at weight 0). On the aggressive V1_03 flight the gyro meter rises
  above 0.05 rad/s without any added fault, so L2 acts on a sound gyro there and costs 0.12 m. Inside the 0.5 %
  mean limit, but a known cost: an organiser test on a V1_03-like clean flight would see it.
- Rule H (L3, seeds 13-15) must name `TILT_ON = True` (and `SMOOTH_ON = True`) as its base.

### Re-measurement of rule G's null on the smoother-on base (informational; NOT a re-judge)

Asked by Arnav (18 Nov, late evening), written and committed before it runs, after rule G2 was committed
(3e2646e) and judged. Rule G's verdict stands as recorded (OFF, judged on 5fd288c, verdict 6ba6f6e) whatever
this shows; the ship decision is rule G2 alone, and G2 is not changed after this.

- Build: this branch at the commit that carries this text (smoother ON; code identical to 3e2646e except the
  shipped default `TILT_ON = True`). Every run sets TILT_ON explicitly with `--set`; no constant changes.
- Data: the same 36 seed 10-12 copies rule G used (MH_03..05, V1_01..03 x a, b x seeds 10-12), the same
  `--reverse` comparison. Tags `stepGR-H-off`, `stepGR-H-on`, `stepGR-H-on-rev` (rule G's level null: on
  against on reversed) and `stepGR-H-off-rev` (so G2's difference-in-differences form can be read off too).
  The floor is the never-moving baseline and does not depend on the build: `stepG-H-floor` is reused.
- Report (`python tools/remeasure_stepG.py`, output kept in `Docs/results/stepGR-report.txt`): means of off, on,
  on reversed, off reversed, floor, overall and by reading; per-sequence paired effects; both null forms.
- Not re-run on seeds 10-12: clean EuRoC, TUM-VI room3/4 and clean rooms, and the gate (measured on the
  smoother-on base under G2).

**Result of the re-measurement (18 Nov 2026, late evening; build a7f932b, the commit that pre-registered it;
every tag records it; 144 runs, contract PASS on all; report in `Docs/results/stepGR-report.txt`).
Informational: rule G's verdict (OFF, 5fd288c) stands as recorded; the decision is G2's.**

| Seed 10-12 copies | off | on | on reversed | off reversed | floor |
|---|---|---|---|---|---|
| reading a | 5.502 | 3.647 | 3.840 | 5.327 | 3.746 |
| reading b | 3.674 | 3.520 | 3.791 | 3.925 | 3.746 |
| both (H) | 4.588 | 3.584 | 3.815 | 4.626 | 3.746 |

- Rule G's level null, re-measured on the smoother-on base: on 3.584 against on reversed 3.815 m, so on is
  below (under rule G, on 5fd288c without the smoother: 3.743 against 3.735, a fail). G2's gain form:
  1.004 against 0.811 m, gain larger.
- Same copies as rule G, so the change from 5fd288c to this build is the base (the Step 6 smoother merged in),
  not the seeds. Both the off and on estimates moved: off 4.935 -> 4.588, on 3.743 -> 3.584 m.
- Per sequence, paired effect off - on (m): MH_03 +2.002, MH_04 +0.635, MH_05 +1.573, V1_01 +0.962, V1_02
  0.000, V1_03 +0.854 (V1_03 b 2.517 -> 1.593). RPE 1 s 0.746 -> 0.590; gap 4.460 -> 3.447; blind 7.077 ->
  3.381 m (floor 2.506).
- It agrees with the G2 decision (ship ON) and changes nothing. Not re-run on seeds 10-12: clean EuRoC, TUM-VI
  and the gate. The floor tag `stepG-H-floor` (5fd288c) is reused; the never-moving baseline does not depend on
  the estimator build.

## Freeze build: one self-contained `src/main.py` (19 Nov 2026, branch `track3/freeze-build`)

Arnav's freeze-build requirements (19 Nov; ledger `Docs/SUBMISSION_RULES.md` A1, B1-B7): one generated
`src/main.py`, standard library only, no bytecode, no C, no ctypes; every invocation form; never fail
(constant pose per row, exit 0); exact `s.nnnnnnnnn` timestamps; input variants that do not change the
output; `metadata.json` with commit, flags, input, rows, `cal_source`, heap and time; Python 3.10-3.14.

Without bytecode Python compiles the whole file inside the traced run. The PLAIN layout (pathfinder.py
with docstrings, comments and the OFF side of every switch removed; 16,483 parser tokens, still above
CPython's 16,384-token step) peaks at 7,514 KB (Win 3.14) and 7,963 KB (Win 3.13) over the whole run
on MH_03_medium_a_s1, against the 8,192 KB limit. Main before this branch was already at 7,188 / 7,551 KB
from source (Docs/NUMBERS.md at 86711a9; Step 7 crossed the token step).

### Bundle rule K (CHUNKED layout; not the loop's TUM-VI rule K of CC-3): committed BEFORE any measurement of the CHUNKED bundle

Disclosure: one exploratory reading was taken before this rule: compiling the PLAIN file one top-level
statement at a time inside a tracemalloc window (not the CHUNKED bundle, not a whole run) peaked at
2,687 KB (3.14) / 2,593 KB (3.13), against 6,857 / 6,656 KB for compiling it whole.

CHUNKED: a short loader (sys and builtins only), then pathfinder.py VERBATIM in one raw string; at run
time each chunk of neighbouring top-level statements (up to N lines; N = 40, 120, 400 tried, the lowest
peak kept) is compiled and executed in one namespace, line numbers kept, then `main(sys.argv)` runs. The
loader's own fallback covers a failure of the exec loop. No estimator function is refactored or split.

CHUNKED ships only if ALL hold, else PLAIN ships:
- (a) output byte-identical to PLAIN and to the repo build on every official and clean copy on disk
  (V2_* excluded), on Win 3.14 and WSL2 3.12;
- (b) every B1/B2/B4/B5 test PLAIN passes also passes on CHUNKED;
- (c) whole-run from-source heap peak at least 1.5 MB lower than PLAIN on MH_01_easy_b_s1 AND on the
  longest official copy, on every Python measured (Win 3.14, Win 3.13, WSL2 3.12);
- (d) us per row not worse than PLAIN by more than 5 % on the same inputs.
The shipped layout must be <= 7 MB whole-run from source on every Python measured, or Arnav decides.
Time box: 90 minutes after PLAIN passes; if exceeded, PLAIN ships and CHUNKED is marked PARKED.

### Bundle rule K outcome (20 Nov 2026; d49cf06 plus two measurement-tool fixes, pathfinder.py unchanged)

`tools/bundle_layouts.py measure` / `identity` (Docs/bundle/*.json) and `benchmark.py --bundle` (tags
`bundle-{plain,chunked}-{win-py314,win-py313,wsl-py312}-mh01-b-s1`). Python 3.10 and 3.11 are not installed
on this machine, so they were not measured.

Whole-run heap peak from source (tracing started before the bundle is compiled; KB). It is the same on all four
inputs, because compiling dominates:

| Python | PLAIN | CHUNKED (N=120) | difference | `-X tracemalloc=1`, PLAIN / CHUNKED | largest chunk compile | estimator only, MH_01_easy_b_s1 |
|---|---|---|---|---|---|---|
| Win 3.14.7 | 7,512 | 3,186 | -4,326 | 10,239 / 7,033 | 2,599 (`_run`) | 1,283 |
| Win 3.13.5 | 7,954 | 3,876 | -4,078 | 9,876 / 5,798 | 2,516 (`_run`) | 1,159 |
| WSL2 3.12.3 | 7,713 | 3,555 | -4,158 | 9,682 / 5,525 | 2,434 (`_run`) | 1,157 |

`-X tracemalloc=1` traces from interpreter start-up, so it also counts start-up allocations. Under it, CHUNKED
on 3.14 is 7,033 KB, just above 7,000 KB and below 7 MiB (7,168 KB). Chunk size: N = 40 / 120 / 400 gave
3,193 / 3,186 / (timed out at 600 s) KB on 3.14, 3,884 / 3,876 / 3,887 on 3.13, and 3,564 / 3,555 / 3,566 on
3.12; outputs identical on 3.13 and 3.12 (the 3.14 scan stopped before comparing) (Docs/bundle/chunk-lines-scan.txt). N = 120 kept.

us per row, `python -S main.py`. Median of 11 runs, PLAIN and CHUNKED interleaved; CHUNKED's change against
PLAIN:

| Python | MH_01_easy_b_s1 | MH_01_easy_a_s1 | MH_01_easy_a_s3 (longest) | room1_512_16_b_s1 | benchmark tag (5 runs) |
|---|---|---|---|---|---|
| Win 3.14 | 73.8 / 73.1 (-0.8 %) | 139.7 / 141.8 (+1.5 %) | 23.6 / 23.9 (+1.2 %) | 29.1 / 29.4 (+1.0 %) | 141.4 / 139.9 (-1.1 %) |
| Win 3.13 | 22.0 / 21.7 (-1.1 %) | 20.4 / 20.6 (+1.1 %) | 20.7 / 21.0 (+1.6 %) | 155.9 / 157.7 (+1.1 %) | 131.8 / 127.6 (-3.2 %) |
| WSL2 3.12 | 58.1 / 52.3 (-10.0 %) | 39.0 / 33.7 (-13.8 %) | 30.6 / 38.0 (**+24.3 %**) | 30.5 / 30.0 (-1.4 %) | 36.1 / 36.4 (+0.7 %) |

The machine was shared with other sessions, so absolute times swing from 20 to 158 us/row between inputs. That
swing is load, not the bundle; the interleaved pairs are the comparison.

- (a) **PASS.** 412 of 412 copies on disk (official 280, official_tumvi 120, euroc 8, tumvi 4) are byte-identical
  across the repo build, PLAIN and CHUNKED, on Win 3.14 and on WSL2 3.12. V2_* and TUM-VI rooms 5-6 were
  excluded (final test data).
- (b) Both layouts pass the test_freeze / test_bundle_layout runs on this branch (counts in the PR).
- (c) **PASS.** CHUNKED is 4.1-4.3 MB lower on MH_01_easy_b_s1 and on MH_01_easy_a_s3, on every Python measured.
- (d) **FAIL on 1 of 12 cells, read literally.** WSL2 3.12 MH_01_easy_a_s3 is +24.3 %. The other 11 cells are
  between -13.8 % and +1.6 %, and the three benchmark tags between -3.2 % and +0.7 %. The run-time code is the
  same estimator; CHUNKED only adds 15 module-level `exec` calls (one per chunk) and keeps the switch `if`s that PLAIN
  folds away. So that cell looks like load, but the rule does not allow re-running until it passes.
- Time box: exceeded (the build, tests and measurements took well over 90 minutes).
- **Result by the letter: PLAIN ships and CHUNKED is PARKED. But PLAIN is 7.5-8.0 MB from source, above the
  7 MB ceiling, so the layout goes to Arnav.** CHUNKED is 3.2-3.9 MB from source.
- **Decision (Arnav, 21 Nov 2026): ship CHUNKED.** `tools/make_bundle.py` now builds CHUNKED by default (N = 120);
  PLAIN stays buildable with `--layout plain`. Dockerfile, zip, verify and bundle/README.md use the shipped file.

### Gate on the L2 build with TILT_ON shipped (19 Nov 2026; carried over after #61 merged)

Measured on `track3/stepL2-tilt` after #61 was merged, so they arrive here in a follow-up PR. Build: TILT_ON and
SMOOTH_ON on, before Step 7 (PLATFORM_ON) reached `main`. Tags `Docs/budget/stepL2on-*`; the older
`stepL2-win-py314*` tags (5fd288c, TILT_ON off) are kept as they were. 15 runs each, `python -S benchmark.py
--gate`: **PASS on all seven.**

| Python | Input | commit | heap, estimator | whole run, bytecode / none | `python -S main.py` |
|---|---|---|---|---|---|
| Windows 3.14.7 | synthetic | 405109e | 1,062 KB | 1,646 / 6,031 KB | 37.3 us/row |
| Windows 3.14.7 | MH_01_easy_b_s1 | 405109e | 1,234 KB | 1,809 / 6,032 KB | 27.3 us/row |
| Windows 3.14.7 | MH_01_easy_a_s1 (L2 acts) | 405109e | 1,234 KB | 1,810 / 6,032 KB | 27.1 us/row |
| Windows 3.13.5 | synthetic | 6084ec2 | 942 KB | 2,258 / 6,349 KB | 31.2 us/row |
| Windows 3.13.5 | MH_01_easy_a_s1 | 6084ec2 | 1,114 KB | 2,424 / 6,349 KB | 24.7 us/row |
| WSL2 Ubuntu 3.12.3 | synthetic | 6084ec2 * | 938 KB | 2,013 / 6,078 KB | 25.4 us/row |
| WSL2 Ubuntu 3.12.3 | MH_01_easy_a_s1 | 6084ec2 * | 1,110 KB | 2,178 / 6,078 KB | 32.1 us/row |

\* The WSL2 records carry `commit: null` (git inside WSL could not read the Windows checkout); they were run on
6084ec2. All inside the 4 MB heap target and 50 us/row with bytecode; without bytecode, under 8 MB and above
4 MB. 405109e and 6084ec2 differ only in documents. Not carried over: the branch's NUMBERS.md refresh, which #63
superseded (NUMBERS.md now comes from the Step 7 + L2 build).

## CC-4: reading-a gap diagnosis and K8 (19 Nov 2026, loop task CC-4; analysis only, no code change)

**Gap RMSE, reading a, seeds 7-9 (reporting only; `Docs/results/step7m-H79.json` against
`stepL1-H-floor.json`).** Reading a's mean gap RMSE is 3.373 m against b's 3.204 m and the floor's 3.256 m.
Per copy it ranges from -34.7 % (V1_02 a s7) to +54.2 % (V1_01 a s7) against the floor.
- The smoother bridges the bursts. The error grows by 0.015 m on average across a burst (max 0.047 m) on
  reading a, and by 0.014 m (max 0.059 m) on b (`gap_growth_mean`). A burst that was bridged from one end only
  would grow by metres over a burst of a second or more.
- So gap RMSE is the estimate's position error at the moments the bursts fall, not an error made inside them.
  Reading a loses where its whole track is off at those times: V1_01 a +54/+17/+31 %, MH_03 a s8/s9 +14/+12 %.
  The paired difference against the floor correlates only weakly with the APE difference (r = 0.24 on a,
  0.34 on b), because a few bursts sample a few moments of the track.
- No plain bug, so no fix. Any gain here comes from lowering the track error (APE), which other steps already
  target.

**K8, the independent test F1 (exact constant yaw rate treated as stuck).** The behaviour is kept, and the
test stays `xfail(strict=True)` with its reason (ChatGPT's file, unchanged).
- The stuck detector fires on `STUCK_ROWS = 5` identical gyro triplets.
- In the clean data we hold (MH_01..05, V1_01..03, TUM-VI room1..4; 312,179 rows; V2 and room5/6 not read),
  the longest run of exactly repeated gyro triplets is 2 rows, and no run reaches 5.
- A real IMU at 6-decimal resolution does not repeat a triplet five times unless it is stuck. Stuck runs are one
  of the organisers' faults, so the detector is right for real input. Only a synthetic noiseless signal trips
  it, and the noisy variant of the same test passes.

## CC-3: TUM-VI hand-held calibration (19 Nov 2026, loop task CC-3): PARKED at tuning; rule K not written, seeds 19-21 unspent

**Problem.** On every TUM-VI file the stillness search finds no still run, because the rooms start hand-held.
Calibration then falls back: gravity direction comes from the mean of the first 1 s, and gyro bias is 0
(`Docs/TUMVI_BASELINE.md`, G6).

**Probe** (`tools/cc3_calprobe.py`, exploratory, outside `pathfinder.py`). It runs only when the shipped search
returns nothing. It takes the quietest window of the opening H s, scored as std(|a|) + K * mean |w| over W s.
From that window it calibrates either the gyro bias and gravity (`both`) or the gravity direction only (`dir`:
bias 0, `G_DEFAULT`), and anchors the run there as a found still run would. `-m` keeps the moving-start
covariance. The grid was run on the tuning rooms only: room1/2 x readings a, b x seeds 1-3, 12 copies. No
criterion was written beforehand: this is exploration, and no held-out copy was touched. Results are in
`Docs/tumvi/cc3x-*.json`, contract PASS on all 180 runs.

| Variant (H s, W s, K) | mean APE m | room1 | room2 | gap m | blind m |
|---|---|---|---|---|---|
| shipped (fallback: bias 0) | 0.871 | 0.603 | 1.139 | 0.877 | 0.953 |
| `both` 20, 1, 10 (also H 10/60, K 100) | 0.910 | 0.612 | 1.208 | 0.914 | 1.083 |
| `both` 20, 2, 10 | 0.887 | 0.582 | 1.191 | 0.891 | 1.002 |
| `both` 20, 1, 0 (accelerometer only) | 1.013 | 0.754 | 1.273 | 0.997 | 0.960 |
| `both-m` 20, 1, 10 | 0.966 | 0.664 | 1.267 | 0.971 | 1.120 |
| `dir` 20, 1, 10 (also H 5/60; W 2: 0.857; W 4: 0.856; K 0: 0.859) | 0.857 | 0.586 | 1.127 | 0.865 | 0.925 |
| `dir-m` 20, 1, 10 | 0.905 | 0.627 | 1.183 | 0.914 | 1.007 |
| never-moving floor | 1.110 | | | 1.063 | 0.677 |

- A gyro bias taken from a hand-held window makes the result worse. The window mean is mostly the hand's own
  rotation, not bias, and the filter's bias state does better starting from 0.
- Gravity direction alone is the best variant: -1.6 % mean APE, both rooms and both readings better, gap
  -1.4 %, blind -2.9 %. The gain disappears with the moving-start covariance (`dir-m` 0.905). So most of it
  comes from anchoring with the calibrated (still-start) covariance, not from a better direction. That is a
  covariance effect we cannot justify physically for a hand-held start.
- **Decision: parked; rule K is not written and TUM-VI seeds 19-21 stay unspent.** Rule K needs at least a 2 %
  gain on held-out copies. The best tuning gain is 1.6 % and rests on a covariance effect, so a pass is
  unlikely, and a fail would spend seeds for nothing. No switch was added to `pathfinder.py`, so the shipped
  build is unchanged. A later session can take this up with a better-founded calibration, and seeds 19-21
  remain free for it.

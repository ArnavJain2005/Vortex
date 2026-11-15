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
| V3 Rotor drag (horizontal specific force proportional to body velocity) | Multirotor (EuRoC) | Switchable, after offline go/no-go |
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
| 3 | EuRoC/TUM-VI `imu0/data.csv` loader keeping every row; output checker; `main.py` skeleton (one pose per row) | Loader (`vortex/data/euroc.py`), row rules (`vortex/rowspec.py`) and checker (`vortex/check_output.py`): **Done (verified on synthetic files)** 16 Nov. `main.py`: Not started | `main.py` on MH_01 passes the checker |
| 4 | Seeded degradation script: rising noise, bias drift, 2 s dropouts, failure + 5 s | **Done (verified on synthetic files)** 16 Nov: `vortex/degrade.py`; NaN or missing dropout rows, NaN/zero/stuck failure, optional duplicate and swapped rows; levels are placeholders until Q2 | Same seed gives identical files (checked) |
| 5 | `benchmark.py` (tracemalloc and process RSS, ms per s of IMU) and `score.py` (ATE/RPE split by dropout and blind windows, coverage) | Not started | Both run on MH_01 |
| 6 | Filter core: initialisation and self-calibration (W2), front end and jamming meter (W3), dropout bridging | Not started | Beats dead reckoning on degraded MH_01 |
| 7 | Velocity witnesses (W1): V1, V2 core; V3 after go/no-go; V4, V5 switchable; platform detection (W4) | Not started | Ablation table, each witness on and off, on held-out sequences |
| 8 | Blind 5 s forecaster (W5) and per-row confidence (W6) | Not started | Blind error below constant velocity; coverage table |
| 9 | Efficiency pass (C core if whole-process RAM counts); submission bundle, Dockerfile, deck, video | Not started | Valid `team_name.zip` by 21 Nov 6 PM; submitted 3 h before cutoff |

## Open questions (Q1 to Q5 are in the email drafted for prism@samsung.com on 15 Nov)

| Q | Question | Owner |
|---|---|---|
| Q1 | Final deadline: 18 Nov or 22 Nov; Google Form link | Arnav |
| Q2 | Track 3 student package: degradation script, sample data, evaluator | Arnav |
| Q3 | Are waypoint positions or times given as input? | Arnav |
| Q4 | Is 8 MB peak RAM measured for the whole process or the algorithm only? Is `main.cpp` accepted? **Now urgent:** a bare `python -S -c pass` already peaks at 8.4 MB RSS (WSL2 Linux, 3.12) and 9.5 to 9.7 MB (Windows 3.13/3.14), so CPython cannot meet 8 MB whole-process RSS; a C++ parse + write floor peaks at 4.3 MB (Windows). See `Docs/FLOOR.md` | Arnav |
| Q5 | Demo video length: 2 to 3, 3, or 5 minutes? | Arnav |
| Q6 | Is the rotor-drag signal visible in EuRoC's IMU (offline fit on clean MH_01)? | Arnav + Claude, before 20 Nov |

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

No result on EuRoC or TUM-VI exists yet.

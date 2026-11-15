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
| 3 | Python reference: EuRoC/TUM-VI `imu0/data.csv` loader keeping every row; output checker; `main.py` skeleton (one pose per row) | Not started | `main.py` on MH_01 passes the checker |
| 3b | C core skeleton `main.cpp` (C-style C++, standard library only): streams the CSV, writes identity poses byte-identical to `main.py` | Not started | Equivalence test passes; benchmarked |
| 4 | Seeded degradation script: rising noise, bias drift, 2 s dropouts, failure + 5 s | Not started | Same seed gives identical files |
| 5 | `benchmark.py` (process RSS and tracemalloc, ms per s of IMU, Python and C) and `score.py` (evo-style ATE/RPE with and without alignment; waypoint proxies, dropout and blind windows; coverage) | Not started | Both run on MH_01 |
| 6 | Filter core: initialisation and self-calibration (W2), jamming meter and failure detection (W3), dropout handling | Not started | Beats dead reckoning on degraded MH_01 |
| 6b | **Two-pass offline smoothing**: forward snapshots (store capped from the row count), backward pass, fusion; behind a switch pending Q7 | Not started | Gain over forward-only filter on held-out sequences |
| 7 | Velocity witnesses (W1): V1, V2 core; V3 after go/no-go; V4, V5 switchable; V7 experiment; platform detection (W4) | Not started | Ablation table, each witness on and off, on held-out sequences |
| 8 | Self-testing forecaster for the blind 5 s (W5) and per-row confidence (W6) | Not started | Blind error below constant velocity; coverage table |
| 9 | Port the frozen algorithm to `main.cpp`; equivalence test; Python v0.1 kept as fallback; submission bundle, Dockerfile, deck, video | Not started | Valid `team_name.zip` by 21 Nov 6 PM; submitted 3 h before cutoff |

**Scoring strategy (15 Nov):** C core from day one for the 40 efficiency points; two-pass smoothing for
waypoints (30) and dropouts (10); exact failure detection and a self-testing forecaster for the blind 5 s
(20). A valid Python submission exists by 20 Nov night as fallback. Details: the team PRD doc.

## Open questions (Q1 to Q5, Q7, Q8 go in the email to prism@samsung.com)

| Q | Question | Owner |
|---|---|---|
| Q1 | Final deadline: 18 Nov or 22 Nov; Google Form link | Arnav |
| Q2 | Track 3 student package: degradation script, sample data, evaluator | Arnav |
| Q3 | Are waypoint positions or times given as input? | Arnav |
| Q4 | Is 8 MB peak RAM measured for the whole process or the algorithm only? Is `main.cpp` accepted? | Arnav |
| Q5 | Demo video length: 2 to 3, 3, or 5 minutes? | Arnav |
| Q6 | Is the rotor-drag signal visible in EuRoC's IMU (offline fit on clean MH_01)? | Arnav + Claude, before 20 Nov |
| Q7 | May the solution read the whole file before writing (offline, non-causal smoothing)? | Arnav (email) |
| Q8 | Does the evo evaluation align our trajectory to ground truth before scoring (SE(3) or Sim(3))? | Arnav (email) |

## Results so far (15 Nov 2026, branch `track3/python-pipeline`)

| Item | Result | Where |
|---|---|---|
| `pytest` | 32 passed | Linux sandbox, Python 3.13, numpy 2.5 |
| Dead reckoning, noiseless synthetic, 20 s, exact gravity, 5 ms velocity window | final error 1.2 cm | same; shows the integrator is consistent |
| EuRoC / TUM-VI download from the sandbox | Blocked (hosts refused by the network allowlist) | Arnav downloads on Windows |

No result on EuRoC or TUM-VI exists yet.

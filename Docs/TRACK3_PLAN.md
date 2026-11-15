# Track 3 plan: Path Finder (trajectory estimation under sensor degradation)

Running record of what is done, verified, blocked and unknown. Dates are IST. Update this file in the
same commit as the work it describes.

Status vocabulary: **Done (verified)** = run with the stated result; **Done (unverified)** = written but
not run on its real input; **Blocked**; **Not started**.

## Direction (decided 15 Nov 2026)

The ESP32 sensor station is gone, so hardware is out. Vortex is a Python pipeline on recorded phone data
(ADVIO), with the pitch "trustworthy confidence": a trajectory that survives sensor faults and an error
bound that is shown to hold under them. Deadline **22 Nov 2026**; full-time work starts **20 Nov**.

## Steps

| # | Goal | Status | Exit criterion |
|---|---|---|---|
| 1 | Repo restructure, Python package, old code to `legacy/` | **Done (verified)** 15 Nov | `pytest` green |
| 2 | ADVIO loader + dead-reckoning and freeze-on-loss baselines + metrics | **Done (unverified on real data)** 15 Nov: 18 tests pass on synthetic data and synthetic files in ADVIO's layout | `vortex check` prints OK on a real sequence; baselines scored on 2 sequences |
| 3 | Error-state Kalman filter (IMU predict, ARKit pose update), unit-tested | Not started | Beats both baselines through a 5 s blackout on synthetic data |
| 4 | Seeded fault injector: blackout, IMU noise burst, gyro bias, packet delay; 3 severities | Not started | Same seed gives identical runs |
| 5 | Trust layer: per-sensor health, innovation gating, covariance inflation | Not started | Lower error than plain filter under faults |
| 6 | Calibrated error bound (conformal), coverage plot | Not started | Stated coverage matches measured coverage per fault |
| 7 | Sweep and generated results tables | Not started | One command regenerates every number |
| 8 | Visualizer: truth / naive / Vortex, uncertainty tube, fault buttons | Not started | Runs in a browser from recorded data |
| 9 | Submission: README for judges, diagram, video, borrowed-work list | Not started | Submitted 3 h before cutoff |

Schedule: before 20 Nov, steps 1 to 4 on synthetic data. 20 Nov: steps 2 to 4 on real data. 21 Nov:
steps 5 to 8, feature freeze at night. 22 Nov: step 9.

## Open questions

| Q | Question | Owner |
|---|---|---|
| Q1 | Submission format and cutoff time on 22 Nov (repo, video, deck, report?) | Arnav |
| Q2 | Samsung rules on prior code, open data and IP | Arnav |
| Q3 | Does `vortex check` print OK on ADVIO sequence 1, and what accel sign? | Arnav, after download |

## Step 1-2 results (15 Nov 2026, branch `track3/python-pipeline`)

| Item | Result | Where |
|---|---|---|
| `pytest` | 18 passed | Linux sandbox, Python 3.13, numpy 2.5 |
| Dead reckoning, noiseless synthetic, 20 s, exact gravity, 5 ms velocity window | final error 1.2 cm | same; shows the integrator is consistent |
| `vortex baselines --synthetic` (phone-grade noise, 5 s blackout at 12 s) | freeze-on-loss ATE 0.40 m, max 1.6 m at the end of the outage; dead reckoning passes 1 m error at 4.9 s | same; synthetic, not a device claim |
| ADVIO download from the sandbox | Blocked (Zenodo refused by the network allowlist) | Arnav downloads on Windows |

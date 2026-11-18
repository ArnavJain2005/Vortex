<div align="center">

<img src="assets/vortex-title.gif" alt="Vortex — Path Finder. An animated IMU trajectory passes through a degraded segment and continues into five seconds of blind prediction." width="100%">

<br>

<a href="https://research.samsung.com/"><img src="assets/samsung-research-card.svg" alt="Samsung Research (R&amp;D), on a white card for visibility in dark mode" width="220"></a>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
<a href="https://www.samsungprism.com/"><img src="assets/samsung-prism.png" alt="Samsung PRISM" width="125"></a>

<p><strong>Samsung PRISM XR Hackathon Challenge 2026 · Track 3: Path Finder</strong></p>
<p>IMU-only, 6-DoF trajectory estimation under sensor degradation.</p>

[Challenge](#the-challenge) · [Architecture](#architecture) · [Measured results](#measured-results) · [Run](#run-vortex) · [Research notes](#research-notes)

</div>

---

> **Official-script held-out result:** Vortex is level with a never-moving trajectory under reading **b** (3.744 vs 3.745 m mean SE(3) APE) and worse under reading **a** (6.181 vs 3.745 m). Across both column readings: **4.962 vs 3.745 m**. It has not demonstrated useful motion recovery. [Recorded results](Docs/RESULTS.md) · [decision log](Docs/TRACK3_PLAN.md).

## The challenge

An aircraft must navigate without GPS or cameras while its IMU becomes less reliable: noise and bias grow, readings disappear for up to two seconds, and the sensor eventually fails. The task is to reconstruct a **6-DoF pose for every input IMU row**, including the five seconds after failure, from a EuRoC-format `imu0/data.csv` alone. The evaluator uses EuRoC MAV and TUM-VI sequences with hidden ground truth.

| Input → output | Operating limits | Evaluation |
|---|---|---|
| Gyroscope + accelerometer → `timestamp tx ty tz qx qy qz qw`; one pose per input row, in order, never appended | Python only; offline (batch smoothing allowed), one thread; **8 MB peak at heap level** and **20 ms compute per second of IMU** | SE(3)-aligned ATE (evo) against hidden ground truth: 60 points for trajectory (waypoints 30, blind prediction 20, dropouts 10); 40 for efficiency (memory 20, runtime 20) |

The organisers' FAQ (17 Nov 2026) settled the open points: Python only (`main.py`; `main.cpp` is not accepted), the 8 MB limit is measured at algorithm / heap level rather than process RSS, non-causal smoothing is allowed, scoring uses SE(3) Umeyama alignment, dropouts are physically missing rows, and test data is any EuRoC or TUM-VI sequence degraded with their `degrade_imu.py`.

Small attitude and bias errors grow rapidly under inertial integration. Vortex uses two IMU-only velocity witnesses: **V1 stillness** and **V2 flight envelope**. V2 pulls velocity towards zero and position towards a running centre of the estimate; it bounds drift but is a prior, **not an independent motion measurement**. No camera, GPS, barometer, ground truth or pretrained model enters the estimator.

## Architecture

**Shipped Python path:**

```mermaid
flowchart TD
    A["IMU CSV"] --> B["Input front end"]
    B --> C["Stillness calibration"]
    C --> D["Pre-anchor attitude + held position"]
    C --> E["Strapdown + 15-state V1/V2 filter"]
    E --> F["Gap and blind forecast"]
    D --> G["One pose per input row"]
    F --> G
```

`main.py` launches the standard-library estimator in [`pathfinder.py`](pathfinder.py). The **input front end** detects IMU column order, timestamp scale and acceleration units from the file, canonicalising non-standard input beside the output. It handled the eight clean sequences and 64 official-script copies in the [Step 2 record](Docs/TRACK3_PLAN.md); degrees/second versus fast radians/second motion cannot be resolved automatically. The estimator calibrates gravity, tilt and gyro bias on a still interval, holds pre-anchor position, and then runs a 15-state error-state Kalman filter. Missing rows increase uncertainty; exact zero/stuck failures and invalid samples trigger a 0.5 s velocity-decay forecast. Step F adds a gyro-bias cap, fallback velocity uncertainty and cached-sample refresh.

| IMU-only cue | Role | Shipped state |
|---|---|---|
| V1 · Stillness | Zero-velocity and gyro-bias updates | **On**; little in-flight rest on MH |
| V2 · Flight envelope | Speed and running-centre position priors | **On**; bounds drift but can flatten real motion |
| V3 · Rotor drag | Proposed in-flight velocity cue | **Not built**; both registered signal rules returned NO-GO |
| Turn physics, walking rhythm, tilt response | Conditional research ideas | Not shipped |

The [reference filter](vortex/core/witness.py) retains rejected experiments. Presence in source does not mean a feature is enabled.

### Switches

Every `*_ON` assignment in the shipped `pathfinder.py` at `33b841e`:

| Switch | State | Reason and record |
|---|---|---|
| `FRONT_ON` | **On** | Input format detection; [Step 2](Docs/TRACK3_PLAN.md). |
| `CAL_NOISE_ON` | **On** | Noise-tolerant still calibration fallback; [Step 6e](Docs/TRACK3_PLAN.md). |
| `BGCAP_ON` | **On** | Caps false stillness during steady rotation; [Step F](Docs/TRACK3_PLAN.md). |
| `P0V_ON` | **On** | Wider initial velocity uncertainty without an anchor; [Step F](Docs/TRACK3_PLAN.md). |
| `REFRESH_ON` | **On** | Refreshes cached sample after correction; [Step F](Docs/TRACK3_PLAN.md). |
| `V1_ON` | **On** | Stillness witness; [Step 7a](Docs/TRACK3_PLAN.md). |
| `V2_ON` | **On** | Speed prior; [Step 7a](Docs/TRACK3_PLAN.md). |
| `V2P_ON` | **On** | Running-centre position prior; [Step 7a](Docs/TRACK3_PLAN.md). |
| `GAP_ON` | **On** | Dropout covariance; [Step 6c](Docs/TRACK3_PLAN.md). |
| `DEAD_ON` | **On** | Exact zero/stuck failure detection; [Step 8a](Docs/TRACK3_PLAN.md). |
| `FC_ON` | **On** | Velocity decay during gaps and blind phase; [Step 8a](Docs/TRACK3_PLAN.md). |
| `JAM_ON` | **Off** | Noise meter failed its rule; [Step 6c](Docs/TRACK3_PLAN.md). |
| `RESET_ON` | **Off** | Covariance reset worsened held-out APE; [Step F](Docs/TRACK3_PLAN.md). |
| `LEARN_ON` | **Off** | Per-flight envelope tied the degraded floor but raised clean APE 6.68%; [Step 4](Docs/TRACK3_PLAN.md). |
| `FF_STUCK6_ON` | **Off** | Stuck-row rejection failed held-out checks; [Step 3](Docs/TRACK3_PLAN.md). |
| `FF_SPIKE_ON` | **Off** | Spike rejection did not improve held-out APE; [Step 3](Docs/TRACK3_PLAN.md). |
| `INTERP_ON` | **Off** | Interpolation worsened aggregate and reading-a scores; [Step 3](Docs/TRACK3_PLAN.md). |
| `SHRINK_ON` | **Off** | Both shrinkage arms failed registered conditions; [Step L1](Docs/TRACK3_PLAN.md). |

A forward-backward smoother and denoised V1 remain **off in the reference only**. An experimental per-row sigma did not rank error and is not submitted as calibrated confidence ([coverage study](Docs/COVERAGE.md)).

## Measured results

**Primary scoreboard — organisers' degradation script, held-out MH_03–05 and V1_01–03, readings a and b, seeds 4–6 (36 copies).** APE is the mean per-copy translational RMSE after SE(3) alignment fitted on each run. Reading **a** feeds raw gyro-first EuRoC columns to the script; reading **b** feeds accelerometer columns first. The actual evaluator order (Q9) remains unknown. [Step F](Docs/TRACK3_PLAN.md) · [generated results](Docs/RESULTS.md).

| Held-out input | Vortex APE ↓ | Never-moving APE ↓ | Blind 5 s RMSE: Vortex / floor ↓ |
|---|---:|---:|---:|
| Reading a · 18 copies | **6.181 m** | **3.745 m** | 11.148 / 2.504 m |
| Reading b · 18 copies | **3.744 m** | **3.745 m** | 2.836 / 2.504 m |
| **Both · 36 copies** | **4.962 m** | **3.745 m** | **6.992 / 2.504 m** |

**Vortex does not beat standing still on the official degradation.** Reading b is effectively tied on APE; reading a and blind windows are worse. The input front end recognises the order, but it cannot undo accelerometer-sized faults applied to gyro columns under reading a. Ground truth is used only for scoring.

Clean-data history illustrates the limitation: across five clean MH sequences the estimator recorded **4.84 m** mean SE(3) APE versus **5.25 m** for never-moving, with much of the margin on MH_02, a tuning sequence. V2 is a prior rather than a measurement of velocity. Results from the project's own placeholder fault injector are historical workflow evidence and **not a proxy for the organisers' script**. [Clean results](Docs/RESULTS.md) · [Step 6d](Docs/TRACK3_PLAN.md).

**A negative control:** Step L1 trust-scaled shrinkage reduced the reading-a objective from **143.17 to 72.35**, but improved only **four of six** sequences where five were required. Its time-reversed output scored **69.75**, better than 72.35. Shrinking an estimate can improve SE(3)-aligned scores without demonstrating motion information. **`SHRINK_ON` remains off.** [Step L1](Docs/TRACK3_PLAN.md).

| Other recorded check | Outcome |
|---|---|
| Automated tests | **310 passed**, Windows/Python 3.14.7, 18 Nov; recorded, not rerun for this documentation change ([Step L1](Docs/TRACK3_PLAN.md)) |
| Latest official-copy budget | **2.89 ms per IMU-second**; **1,117 KB** traced whole-run heap with matching bytecode, **6,055 KB** without, Windows/Python 3.14.7 ([Step L1 row](Docs/BUDGET.md)) |
| V3 rotor drag | Revised rule passed only one of three Vicon Room 1 sequences; V3 **not built** ([Step 5](Docs/TRACK3_PLAN.md)) |
| Per-row confidence | Reference sigma did not rank error on MH_01/02 tuning data: Spearman **−0.07** over 344,494 scored rows; no calibrated confidence claimed ([coverage](Docs/COVERAGE.md)) |
| Submission bundle | Python-only launcher, estimator, version-matched bytecode, Dockerfile and manifest ([guide](bundle/README.md)) |

The recorded 20 ms/IMU-second and 8 MB **heap** gates pass on the measured machine. Whole-process RSS includes the interpreter and is not the organisers' memory metric. Without matching bytecode, compilation raises the traced heap; the latest 3.13 no-cache reading is **6,431 KB**, still under 8 MB ([budget](Docs/BUDGET.md)). TUM-VI and untouched Vicon Room 2 have not been evaluated. L2 slow gravity alignment, L3 blind-window start state and submission hardening remain planned ([plan](Docs/TRACK3_PLAN.md)).

## Run Vortex

Python 3.12 is sufficient for the submission entry point; `main.py` and `pathfinder.py` use the standard library. Analysis and tests need the dependencies in `pyproject.toml`. Run these commands from the repository root.

```bash
python -m pip install -e '.[dev]'
pytest

# Synthetic format and output-contract check, not a navigation benchmark.
python tools/synth_euroc.py imu.csv --rows 36000 --seed 0
python -S main.py imu.csv estimated_trajectory.txt
python -m vortex.check_output imu.csv estimated_trajectory.txt
```

The checker should report `PASS: 36000 input rows, 36000 output rows`. `python -S` skips site-package initialisation for the standard-library launcher; it does **not** provide a matching cached bytecode file. A source-only checkout still runs but incurs a higher compilation heap peak.

For the [submission bundle](bundle/README.md), run `python tools/make_bundle.py stage` under each target Python version, then `python tools/make_bundle.py zip --name NAME` and `python tools/make_bundle.py verify dist/NAME.zip`. Replace `NAME` with the submission name when known. Verification runs under the current interpreter. The bundle includes a [Dockerfile](bundle/Dockerfile).

EuRoC data and ground truth are **not shipped**. With a locally downloaded sequence under `data/euroc/` ([data setup](Docs/DATA.md)):

```bash
python -S main.py data/euroc/MH_01_easy/mav0/imu0/data.csv estimated_trajectory.txt
python -m vortex.check_output data/euroc/MH_01_easy/mav0/imu0/data.csv estimated_trajectory.txt
python score.py --gt data/euroc/MH_01_easy --est estimated_trajectory.txt
```

The clean-data evaluator also requires local sequences and ground truth; its tag writes JSON and rebuilds `Docs/RESULTS.md`:

```bash
python tools/eval_euroc.py --tag local-clean --seqs MH_01_easy,MH_02_easy,MH_03_medium,MH_04_difficult,MH_05_difficult
```

This is a **project-placeholder fault model**, useful for a workflow check but not interchangeable with the organisers' `degrade_imu.py`:

```bash
python -m vortex.degrade data/euroc/MH_01_easy data/degraded/MH_01_easy_s1 --seed 1
python tools/eval_euroc.py --tag local-placeholder --degraded --seqs MH_01_easy_s1
```

The official script and FAQ files are not committed. The [official baseline](Docs/STEP2_BASELINE.md), [generated results](Docs/RESULTS.md) and [plan](Docs/TRACK3_PLAN.md) record both column readings; reproducing their official-copy scores requires that local script and data.

## Research notes

- [Track 3 plan](Docs/TRACK3_PLAN.md) — registered decisions, open Q9 and next steps.
- [Official-script baseline](Docs/STEP2_BASELINE.md) — original held-out floor comparison.
- [Generated results](Docs/RESULTS.md) — clean and seeded degraded EuRoC metrics, stationary floor, and ablations.
- [Blind-window study](Docs/BLIND.md) — dead-sensor detection and five-second forecast comparisons.
- [Confidence coverage](Docs/COVERAGE.md) — why the experimental per-row sigma is not reported as calibrated confidence.
- [Submission bundle](bundle/README.md) — launcher, bytecode, manifest, Docker, and verification.
- [Budget ledger](Docs/BUDGET.md) and [efficiency floor](Docs/FLOOR.md) — synthetic and real timing, heap and process memory, and interpreter cost.
- [Rotor-drag study](Docs/DRAG.md) — pre-registered NO-GO result and explicitly labeled exploratory fits.
- [Scorer cross-check](Docs/EVO_CROSSCHECK.md) — evo comparison on synthetic trajectories.
- [Data instructions](Docs/DATA.md) and [third-party notices](THIRD_PARTY.md) — datasets stay outside the repository.

**Current solo entrant:** Arnav Jain · **Submission name:** `[TEAM_NAME]` · **College:** `[COLLEGE_NAME]`. Samsung Research and Samsung PRISM marks identify the challenge context; Vortex is Arnav's current solo entry.

<sub>Project code: [MIT](LICENSE). Brand marks are Samsung's; [Research mark](https://cdn.codeground.org/nsr/images/layout/logo-sr.png) and [PRISM mark](https://www.samsungprism.com/assets/images/prism_logo.png) are reproduced from their official sites.</sub>

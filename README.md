<div align="center">

<img src="assets/vortex-title.gif" alt="Vortex: IMU-only pose estimation. A schematic trajectory grows from gyro and accelerometer readings through a missing-row gap into five seconds of blind forecasting." width="100%">

<br>

<a href="https://research.samsung.com/"><img src="assets/samsung-research-card.svg" alt="Samsung Research (R&amp;D), on a white card for visibility in dark mode" width="200"></a>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
<a href="https://www.samsungprism.com/"><img src="assets/samsung-prism.png" alt="Samsung PRISM" width="115"></a>

<h3>Samsung PRISM XR Hackathon Challenge 2026 · Track 3: Path Finder</h3>

<p><b>A drone's motion sensor is getting noisier, losing readings, and is about to die.<br>
Vortex rebuilds its full 6-DoF flight path from that sensor alone.</b></p>

<img src="https://img.shields.io/badge/Python-3.12%20%7C%203.13%20%7C%203.14-0a0e2e?style=for-the-badge&logo=python&logoColor=5ec8f2" alt="Python 3.12, 3.13, 3.14">
<img src="https://img.shields.io/badge/dependencies-standard%20library%20only-0a0e2e?style=for-the-badge&labelColor=0a0e2e&color=5ec8f2" alt="Standard library only">
<img src="https://img.shields.io/badge/tests-521%20passed-0a0e2e?style=for-the-badge&labelColor=0a0e2e&color=7ee0b5" alt="521 tests passed">
<img src="https://img.shields.io/badge/licence-MIT-0a0e2e?style=for-the-badge&labelColor=0a0e2e&color=c38bf5" alt="MIT licence">

<br><br>

<a href="https://www.youtube.com/watch?v=bPd4NMj70VY"><img src="assets/vortex-film-poster.jpg" alt="Watch the Vortex film (1 minute): Pip, a little drone whose flight log is about to fall apart. Click to play." width="88%"></a>

<sub>▶ <a href="https://www.youtube.com/watch?v=bPd4NMj70VY"><b>Watch the 60-second film on YouTube</b></a> &nbsp;·&nbsp; <a href="assets/vortex-film.mp4">MP4 download (21 MB)</a></sub>

<br><br>

[**The problem**](#-the-problem) · [**How it works**](#-how-vortex-works) · [**Results**](#-results) · [**Budget**](#-inside-the-budget) · [**Run it**](#-run-it-in-60-seconds) · [**Deep dive**](#-deep-dive)

</div>

---

## ✦ Vortex in 30 seconds

<table>
<tr>
<td width="33%" valign="top">

### 🛰️ The problem
No GPS, no camera: only a gyroscope and an accelerometer. Then the IMU degrades. Noise and bias grow, readings vanish for up to 2 s, and in the last 5 s the sensor is dead. A pose is still needed for **every single row**.

</td>
<td width="33%" valign="top">

### 🧭 What Vortex does
A 15-state error-state Kalman filter with an offline smoother, held in check by **velocity witnesses**: hints about motion from the IMU's own physics. It tracks how far it can trust the sensor, and when the sensor dies it falls back to the last pose it trusted.

</td>
<td width="33%" valign="top">

### 📏 What we measured
On **36 held-out EuRoC flights** degraded with the organisers' own script, Vortex is **8.1% lower** in trajectory error and **40.2% lower** in local-motion error than a trajectory that never moves. It uses **6.60 ms** of compute per IMU-second (limit 20 ms) and **3.5 MB** of heap (limit 8 MB).

</td>
</tr>
</table>

> [!NOTE]
> **Held-out headline, shipped v1.0 build.** On 36 EuRoC copies (six flights × two column readings × seeds 4–6), Vortex records **3.440 m** mean SE(3)-aligned APE against **3.745 m** for a never-moving trajectory. In the blind five seconds it **ties** that floor (**2.494 vs 2.504 m**). These are results on held-out copies, not a guarantee on hidden data. Every number on this page comes from the generated ledger [`Docs/NUMBERS.md`](Docs/NUMBERS.md).

---

## 🛰️ The problem

A flying platform has to keep track of itself with **no GPS and no camera**, using an IMU that gets steadily worse:

| Phase of the flight | What the sensor does | What Vortex has to do |
|:---|:---|:---|
| 🟢 **Healthy** | Clean gyro + accelerometer | Calibrate gravity, tilt and gyro bias; start tracking |
| 🟡 **Degrading** | Noise, bias and scale drift grow; spikes, stuck runs, duplicated rows | Keep integrating without letting small errors explode |
| 🟠 **Dropouts** | Rows physically **missing** for up to 2 s | Carry the pose across the hole, with growing uncertainty |
| 🔴 **Blind 5 s** | Timestamps continue, values are dead (exact zeros) | Still output a pose for every row |

<details>
<summary><b>The exact rules we follow</b> (from the organisers' slides and FAQ, 17 Nov 2026)</summary>

<br>

| Input → output | Operating limits | Evaluation |
|---|---|---|
| EuRoC-format `imu0/data.csv` (gyro + accelerometer) → `timestamp tx ty tz qx qy qz qw`, one pose per input row, in order, never appended | Python only; offline (batch smoothing allowed); one thread; **8 MB peak at heap level**; **20 ms compute per second of IMU** | SE(3)-aligned ATE (evo) against hidden ground truth: 60 points for trajectory (waypoints 30, blind prediction 20, dropouts 10); 40 for efficiency (memory 20, runtime 20) |

The FAQ settled the open points: Python only (`main.py`; `main.cpp` is not accepted); the 8 MB limit is measured at algorithm / heap level, not process RSS; non-causal smoothing is allowed; scoring uses SE(3) Umeyama alignment; dropouts are physically missing rows; and test data is any EuRoC or TUM-VI sequence degraded with the organisers' `degrade_imu.py`. Our reading of every silent point is in [`Docs/SUBMISSION_RULES.md`](Docs/SUBMISSION_RULES.md).

</details>

**Why it's hard:** inertial navigation integrates acceleration twice, so a tiny tilt or bias error turns into metres of drift within seconds. Vortex gets no outside help to correct it. **No camera, GPS, barometer, ground truth or pretrained model enters the estimator.**

---

## 🧭 How Vortex works

```mermaid
flowchart LR
    A[("Degraded<br/>IMU CSV")]:::io --> B["Input front end<br/><sub>column order · units · timestamps</sub>"]
    B --> C["Stillness &amp; platform<br/>detection"]
    C --> E["Strapdown +<br/>15-state filter<br/><sub>V1 / V2 witnesses</sub>"]:::core
    E --> I["Slow gravity<br/>alignment"]
    E --> F["Gap forecast"]
    I --> H["Offline smoother"]:::core
    E --> H
    H --> J["Blind window from<br/>the last trusted state"]
    C --> D["Pre-anchor attitude<br/>+ held position"]
    D --> G[("One pose<br/>per input row")]:::io
    F --> G
    J --> G
    classDef io fill:#0a0e2e,stroke:#5ec8f2,color:#f3f5ff,stroke-width:2px
    classDef core fill:#121a45,stroke:#c38bf5,color:#f3f5ff,stroke-width:2px
```

1. **Read anything.** The front end detects IMU column order, timestamp scale and acceleration units from the file itself. It tolerates CRLF, missing headers, blank lines and extra columns.
2. **Calibrate while healthy.** Gravity, tilt and gyro bias come from a still interval, with a fallback if there isn't one. A whole-file accelerometer statistic decides whether this is a **drone** or a **hand-held** recording.
3. **Track with velocity witnesses.** A 15-state error-state Kalman filter runs on top of strapdown integration. Cues from the IMU's own physics keep velocity bounded (table below).
4. **Treat a gap as a gap.** Missing rows increase uncertainty instead of being invented. Exact zero or stuck failures trigger a 0.5 s velocity-decay forecast.
5. **Smooth with hindsight.** The task is offline, so a forward-backward smoother revises earlier poses using later samples. When gyro noise rises, windowed gravity alignment steps in.
6. **Know when to stop believing.** If the file ends in ≥ 1 s of dead rows, every pose from 3 s before that run keeps the **attitude of the last trusted pose**, and its position is gently pulled toward the trajectory's centroid. This is a trust policy, not a forecast of the motion.

| IMU-only cue | What it tells the filter | Shipped |
|:---|:---|:---:|
| **V1 · Stillness** | "I'm not moving": zero-velocity and gyro-bias updates | ✅ On |
| **V2 · Flight / hand-held envelope** | Speed and running-centre priors chosen per platform. Bounds drift, but is a *prior*, not a motion measurement | ✅ On |
| **Slow gravity alignment** | Windowed tilt correction when the gyro gets noisy | ✅ On |
| **V3 · Rotor drag** | Proposed in-flight velocity cue | ❌ Not built: both registered rules returned NO-GO |
| Turn physics, walking rhythm | Conditional research ideas | ➖ Not shipped |

> [!TIP]
> **Every feature had to earn its place.** Each one is a switch, off by default. Its pass/fail rule was committed *before* it was compared on held-out data, and it ships only if it passes. Eight ideas were measured and left out. One (shrinkage) improved the headline number but failed its time-reversed control, so it stays off. The full record is in the [Track 3 plan](Docs/TRACK3_PLAN.md).

---

## 📊 Results

<div align="center">
<img src="assets/readme-results.svg" alt="Vortex versus a never-moving trajectory. EuRoC held-out full APE 3.440 vs 3.745 m (8.1% lower); 1 s RPE 0.562 vs 0.941 m (40.2% lower); dropout gaps 3.478 vs 3.626 m (4.1% lower); blind 5 s 2.494 vs 2.504 m (tie); 8 clean EuRoC flights 3.570 vs 3.930 m (9.2% lower); TUM-VI held-out rooms 1.083 vs 1.164 m (7.0% lower)." width="100%">
</div>

**What the comparison is.** Each run is compared with the **never-moving trajectory** on the *same input*, after the same per-run SE(3) alignment. That floor is deliberately simple. It is **not** a comparison with other teams, with visual-inertial methods, or with the hidden leaderboard. [Scoring method](Docs/METHOD.md) · [source values and run tags](Docs/NUMBERS.md).

<table>
<tr>
<td width="50%" valign="top">

#### ✅ Where Vortex is stronger
- **5 of 6** held-out EuRoC flights beat the floor on full-trajectory error, in each column reading
- **7 of 8** clean EuRoC flights, and **4 of 4** measured TUM-VI rooms
- Local motion (1 s RPE) is **40–50% lower** on EuRoC
- Replicated on independent degradation seeds 7–9: **3.481 vs 3.748 m**
- Every copy passes the output contract: **36/36** (seeds 4–6), **36/36** (7–9), **36/36** (22–24) and **24/24** TUM-VI

</td>
<td width="50%" valign="top">

#### ⚠️ Where it is weaker
- The **blind five seconds only tie** the floor (2.494 vs 2.504 m): Vortex holds steady, it does not predict the motion
- Gap error on seeds 7–9 is **1.3% higher** than the floor (3.298 vs 3.256 m)
- **V1_01** is worse than the floor in both readings (2.245 and 2.049 vs 1.854 m)
- The blind-window and gravity-alignment rules were revised after their first rules failed, so that evidence is **weaker**

</td>
</tr>
</table>

<details>
<summary><b>📋 Full results tables</b> (every set, every metric)</summary>

<br>

| Test set · metric ↓ | Vortex | Never-moving floor | Relative error |
|---|---:|---:|---:|
| EuRoC held-out, seeds 4–6 · full APE (36 copies) | **3.440 m** | 3.745 m | **8.1% lower** |
| EuRoC held-out, seeds 4–6 · 1 s RPE | **0.562 m** | 0.941 m | **40.2% lower** |
| EuRoC held-out, seeds 4–6 · gap-window RMSE | **3.478 m** | 3.626 m | **4.1% lower** |
| EuRoC held-out, seeds 4–6 · blind 5 s RMSE | **2.494 m** | 2.504 m | 0.4% lower (a tie) |
| EuRoC held-out, seeds 7–9 · full APE (36 further copies) | **3.481 m** | 3.748 m | **7.1% lower** |
| EuRoC held-out, seeds 7–9 · 1 s RPE | **0.563 m** | 0.943 m | **40.2% lower** |
| EuRoC clean · full APE (8 sequences) | **3.570 m** | 3.930 m | **9.2% lower** |
| EuRoC clean · 1 s RPE | **0.407 m** | 0.813 m | **49.9% lower** |
| TUM-VI held-out rooms 3–4 · full APE (12 copies) | **1.083 m** | 1.164 m | **7.0% lower** |
| TUM-VI held-out rooms 3–4 · 1 s RPE | **1.012 m** | 1.260 m | **19.7% lower** |
| TUM-VI rooms 1–4 · full APE (24 copies) | **0.969 m** | 1.137 m | **14.8% lower** |
| TUM-VI rooms 1–4 · gap-window RMSE | **0.988 m** | 1.078 m | **8.3% lower** |
| TUM-VI rooms 1–4 · blind 5 s RMSE | **0.699 m** | 0.709 m | 1.4% lower (a tie) |
| TUM-VI rooms 1–4, clean · full APE (4 sequences) | **0.879 m** | 1.137 m | **22.6% lower** |

**By column reading (EuRoC held-out, seeds 4–6).** Reading **a** feeds raw gyro-first EuRoC columns to the organisers' script; reading **b** feeds accelerometer columns first. The evaluator's actual order (Q9) is unknown, so both are reported.

| Metric ↓ | Vortex a / floor | Vortex b / floor | a vs floor | b vs floor |
|---|---:|---:|---:|---:|
| Full APE | 3.506 / 3.745 m | 3.373 / 3.745 m | 6.4% lower | 9.9% lower |
| 1 s RPE | 0.606 / 0.941 m | 0.519 / 0.941 m | 35.5% lower | 44.9% lower |
| Gap-window RMSE | 3.593 / 3.626 m | 3.363 / 3.626 m | 0.9% lower | 7.3% lower |
| Blind 5 s RMSE | 2.490 / 2.504 m | 2.498 / 2.504 m | 0.6% lower | 0.2% lower |

**Per flight (full APE, seeds 4–6).**

| EuRoC sequence | Reading a: Vortex / floor | Reading b: Vortex / floor | Outcome |
|---|---:|---:|:---:|
| MH_03_medium | 3.310 / 3.579 m | 2.875 / 3.579 m | ✅ both better |
| MH_04_difficult | 6.258 / 6.813 m | 6.186 / 6.813 m | ✅ both better |
| MH_05_difficult | 6.621 / 6.865 m | 6.564 / 6.865 m | ✅ both better |
| V1_01_easy | 2.245 / 1.854 m | 2.049 / 1.854 m | ❌ both worse |
| V1_02_medium | 1.223 / 1.778 m | 1.196 / 1.778 m | ✅ both better |
| V1_03_difficult | 1.381 / 1.581 m | 1.370 / 1.581 m | ✅ both better |

**Coverage.** Seeds 7–9 beat the floor on **5/6** flights with both readings pooled (**4/6** in reading a, **5/6** in reading b). These seeds reuse the same six flights, so they show replication across degradations, not six new trajectories. On TUM-VI, rooms 1–2 were used for tuning and rooms 3–4 are held out. The platform detector picks the hand-held envelope there, and stillness calibration did not fire on any of the four clean rooms or 24 official copies. Ground truth is used only for scoring.

**Rule H' set (seeds 22–24), weaker evidence.** The blind window was first judged by rule H on seeds 13–15. It failed one condition: its fixed 5 s fallback made clean TUM-VI 1.13% worse. Rule H' judges the dead-run-only variant that ships. It was written after that failure and judged on seeds 22–24. On those 36 EuRoC copies: APE **3.554 vs 3.750 m** (5.2% lower), blind **2.501 vs 2.508 m**, gap **3.472 vs 3.414 m** (1.7% higher), **4/6** flights better (3/6 in reading a). On 12 TUM-VI room 3–4 copies: APE **1.077 vs 1.163 m**, blind **0.734 vs 0.740 m**.

**A negative control.** Step L1 shrinkage improved its aggregate objective, but it failed the registered sequence check, and its *time-reversed* output scored better. Shrinking an estimate can improve SE(3)-aligned scores without carrying any motion information, so shrinkage stays off. Step L2 gravity alignment first failed rule G's reversed-time null. Its revised rule G2, written after that outcome, passed on later copies and ships. That is weaker evidence than an unchanged first rule.

[Verified figures](Docs/NUMBERS.md) · [generated results](Docs/RESULTS.md) · [decision log](Docs/TRACK3_PLAN.md) · [negative results](Docs/NEGATIVE_RESULTS.md)

</details>

---

## ⚡ Inside the budget

<div align="center">
<img src="assets/readme-budget.svg" alt="Compute 6.60 ms per IMU-second in Linux Docker against a 20 ms limit (5.82 ms on Windows, Python 3.14.7). Peak heap 3,476 KB against 8,192 KB (4,158 KB on Python 3.13.5). Single thread, standard library only, 521 automated tests passing." width="100%">
</div>

<details>
<summary><b>📋 Budget details</b></summary>

<br>

Every figure is for the shipped `src/main.py`, compiled from source (no bytecode ships), on the zip's evaluation input `MH_03_medium_b_s1` (reading b, 26,106 rows). Heap values are tracemalloc peaks for the whole run, started before the file is compiled. [Budget record](Docs/BUDGET.md) · [Docker benchmark](Docs/DOCKER_BENCH.md) · [clean-machine check](Docs/CLEAN_MACHINE.md).

| Parameter | Measured | Limit | Headroom |
|---|---:|---:|---|
| Wall time per IMU second, Linux Docker (`python:3.12.7-slim-bookworm`, 15-run median) | **6.60 ms** | 20 ms | 67% below; 6.56–7.67 ms over seven inputs |
| Wall time per IMU second, Windows 11, Python 3.14.7 | **5.82 ms** | 20 ms | 71% below |
| Time per row, Windows 11, Python 3.14.7 | **30.1 µs** | 100 µs | 70% below |
| Whole-run heap from source, Python 3.14.7 | **3,476 KB** | 8,192 KB | 4,716 KB below |
| Whole-run heap from source, Python 3.13.5 | **4,158 KB** | 8,192 KB | 4,034 KB below; above our own 4 MB design target |
| Automated tests, Windows 11, Python 3.14.7, 22 Nov | **521 passed** | — | 0 failed, 2 skipped, 1 expected failure |

On 3.13.5 the heap is above our own 4 MB design target, so `benchmark.py --gate` reports that target as missed there. The challenge's 8 MB limit holds on every measured Python. Whole-process RSS includes the interpreter and is not the organisers' memory metric.

</details>

---

## 🚀 Run it in 60 seconds

The submission is **one self-contained file**, `src/main.py`: pure Python 3, standard library only, single thread, offline and deterministic. It never crashes on a readable input.

```bash
python -S src/main.py                              # finds imu0/data.csv (or data.csv) here, writes estimated_trajectory.txt
python -S src/main.py IN                           # IN: the csv, or a sequence folder
python -S src/main.py IN OUT                       # OUT: the trajectory file, or a folder
python -S src/main.py --input IN --output OUT      # also -i IN -o OUT
```

**With Docker:**

```bash
docker build -t vortex .
docker run --rm -v "<folder with the csv>:/data" -w /data vortex
```

**From this repository** (no dataset needed: a synthetic file checks the format and the output contract, not navigation accuracy):

```bash
python -m pip install -e '.[dev]' && pytest
python tools/synth_euroc.py imu.csv --rows 36000 --seed 0
python -S main.py imu.csv estimated_trajectory.txt
python -m vortex.check_output imu.csv estimated_trajectory.txt     # → PASS: 36000 input rows, 36000 output rows
```

<details>
<summary><b>📦 The submission file, failure behaviour and Docker</b></summary>

<br>

`src/main.py` is **generated** from [`pathfinder.py`](pathfinder.py) by [`tools/make_bundle.py`](tools/make_bundle.py) and never edited by hand. It holds `pathfinder.py` verbatim as source text under a short loader that compiles it one function at a time. Compiling the whole 1,870-line file in one go costs the Python parser about 7 MB of heap, whereas chunked compiling keeps the whole run at 3,476 KB (Python 3.14.7) to 4,158 KB (3.13.5). Error messages keep `pathfinder.py`'s line numbers. The output is byte-identical to the repository's `python -S main.py` (checked on 412 official copies when the layout was chosen, and on 12 again for v1.0), and identical on CPython 3.12, 3.13 and 3.14.

Every invocation works with or without `-S`, under `-I`, and from any working directory. A folder (or the current folder, with no `IN`) is searched for `imu0/data.csv`, `mav0/imu0/data.csv`, `data.csv`, then a single `*.csv`. The output has one line `timestamp tx ty tz qx qy qz qw` per input data row, in input order. Timestamps are the input nanoseconds with the decimal point moved by integer arithmetic, so they are exact.

**Never crashes on a readable input.** If the estimator raises any exception (`MemoryError` included), `main.py` writes a note on stderr, writes a constant pose (origin, identity attitude) for every input row with the exact timestamps, and exits 0. If the estimator cannot even be loaded, the loader does the same. Otherwise the exit codes are 2 for wrong arguments or no input found, and 1 if the input cannot be read or the output cannot be written.

**Docker.** The repository [`Dockerfile`](Dockerfile) builds the same single file from `pathfinder.py` in a first stage and runs only that file (`python -S /app/main.py` on `python:3.12.7-slim-bookworm`). The zip carries its own [Dockerfile](bundle/Dockerfile) that copies the shipped `src/main.py`. On 22 Nov the image's `/app/main.py` was byte-identical to the zip's `src/main.py`, and both `docker run` forms reproduced the zip's `estimated_trajectory.txt` byte for byte.

```bash
docker run --rm -v "<folder with the csv>:/data" vortex /data/data.csv /data/estimated_trajectory.txt
```

**v1.0 bundle.** Tag `v1.0`, `dist/vortex_v1.0.zip`, sha256 `e251c4010248caf5103bbf2923122146bba64ae7e2b225069a89672ffbd4447c`. It passed `verify` on Windows/Python 3.14.7 and 3.13.5 and on WSL2/Python 3.12.3. No evaluation input had been released, so its `estimated_trajectory.txt` is our output for the official degraded copy `MH_03_medium_b_s1` (26,106 rows). The bundle README and `metadata.json` name the input and the commit. [Bundle guide](bundle/README.md).

</details>

<details>
<summary><b>🛠️ Build the bundle, score real data, reproduce the results</b></summary>

<br>

`main.py` (a stub that runs `pathfinder.py`) and `pathfinder.py` use the standard library only; the analysis tools and tests need the dependencies in `pyproject.toml`. Run everything from the repository root. The repository's `main.py` compiles `pathfinder.py` in one go, so it uses more heap than the chunked submission file; the budget figures are for the submission file.

**Build and verify the submission zip** (pass absolute paths to `--dir`):

```bash
python tools/make_bundle.py stage --dir "$PWD/dist/stage"
python tools/make_bundle.py same --dir "$PWD/dist/stage"                   # byte-identity against `python -S main.py`
python tools/make_bundle.py eval IMU.csv --dir "$PWD/dist/stage"           # estimated_trajectory.txt + metadata.json
python tools/make_bundle.py zip --name Vortex --dir "$PWD/dist/stage" --out "$PWD/dist"
python tools/make_bundle.py verify "$PWD/dist/Vortex.zip"
```

**Score a real EuRoC sequence.** Data and ground truth are not shipped; see [data setup](Docs/DATA.md).

```bash
python -S main.py data/euroc/MH_01_easy/mav0/imu0/data.csv estimated_trajectory.txt
python -m vortex.check_output data/euroc/MH_01_easy/mav0/imu0/data.csv estimated_trajectory.txt
python score.py --gt data/euroc/MH_01_easy --est estimated_trajectory.txt
python tools/eval_euroc.py --tag local-clean --seqs MH_01_easy,MH_02_easy,MH_03_medium   # rebuilds Docs/RESULTS.md
```

`python -m vortex.degrade` is the project's own **placeholder** fault model. It is useful as a workflow check but is not interchangeable with the organisers' `degrade_imu.py`, which is not committed. Reproducing the official-copy scores needs that script and the data locally.

**Regenerate this README's charts** from `Docs/NUMBERS.md`:

```bash
python tools/readme_figures.py           # assets/readme-results.svg, assets/readme-budget.svg
python tools/readme_figures.py --check   # fails if they are out of date
```

</details>

---

## 🔬 Deep dive

<details>
<summary><b>🎛️ Every switch in the shipped estimator</b></summary>

<br>

Every `*_ON` assignment in the shipped [`pathfinder.py`](pathfinder.py) is **on**. Rejected alternatives live in the reference or lab copy, not in this list.

| Switch | What it does | Record |
|---|---|---|
| `FRONT_ON` | Input format detection | [Step 2](Docs/TRACK3_PLAN.md) |
| `CAL_NOISE_ON` | Noise-tolerant still-calibration fallback | [Step 6e](Docs/TRACK3_PLAN.md) |
| `BGCAP_ON` | Caps false stillness during steady rotation | [Step F](Docs/TRACK3_PLAN.md) |
| `P0V_ON` | Wider initial velocity uncertainty without an anchor | [Step F](Docs/TRACK3_PLAN.md) |
| `REFRESH_ON` | Refreshes the cached sample after a correction | [Step F](Docs/TRACK3_PLAN.md) |
| `SMOOTH_ON` | Offline forward-backward smoother; passed its registered held-out rule | [Step 6](Docs/TRACK3_PLAN.md) |
| `PLATFORM_ON` | Hand-held vs multirotor detection; selects the envelope | [Step 7](Docs/TRACK3_PLAN.md) |
| `TILT_ON` | Noisy-gyro gravity alignment; passed revised rule G2 after G failed (weaker evidence) | [Step L2](Docs/TRACK3_PLAN.md) |
| `TILT_LAG` | Lag model of that gravity alignment; part of the build judged by G2 | [Step L2](Docs/TRACK3_PLAN.md) |
| `BLIND_ON` | Blind window from a trusted state; passed rule H' after H failed (weaker evidence) | [Step L3](Docs/TRACK3_PLAN.md) |
| `BLIND_DEAD_ONLY` | Acts only on a detected trailing dead run, never on a fixed last 5 s | [Step L3](Docs/TRACK3_PLAN.md) |
| `V1_ON` | Stillness witness | [Step 7a](Docs/TRACK3_PLAN.md) |
| `V2_ON` | Speed prior | [Step 7a](Docs/TRACK3_PLAN.md) |
| `V2P_ON` | Running-centre position prior | [Step 7a](Docs/TRACK3_PLAN.md) |
| `GAP_ON` | Dropout covariance | [Step 6c](Docs/TRACK3_PLAN.md) |
| `DEAD_ON` | Exact zero / stuck failure detection | [Step 8a](Docs/TRACK3_PLAN.md) |
| `FC_ON` | Velocity decay during gaps and the blind phase | [Step 8a](Docs/TRACK3_PLAN.md) |

**Measured and left out:** stuck/spike rejection and interpolation (Step 3), learned envelope (Step 4), rotor drag V3 (Step 5, NO-GO), noise-meter gating (Step 6c), denoised V1 (Step 7b), covariance reset (Step F), shrinkage (Step L1), and the blind window's fixed 5 s fallback (Step L3, rule H). An experimental per-row sigma did not rank error, so it is not submitted as calibrated confidence ([coverage study](Docs/COVERAGE.md)). The [reference filter](vortex/core/witness.py) keeps the rejected experiments; being present in source does not mean a feature is enabled.

</details>

<details>
<summary><b>🗺️ Repository map</b></summary>

<br>

| Path | What's there |
|---|---|
| [`pathfinder.py`](pathfinder.py) | The estimator: standard library only, the source of the shipped `src/main.py` |
| [`main.py`](main.py) | Repository entry point (a stub that runs `pathfinder.py`) |
| [`bundle/`](bundle/README.md) | README and Dockerfile that ship inside the submission zip |
| [`vortex/`](vortex) | Reference filter (`core/`), metrics, scoring, output checker, placeholder degrader |
| [`tools/`](tools) | Bundle builder, evaluators, judging scripts for each registered rule, benchmarks, chart generator |
| [`tests/`](tests) | pytest suite (521 passed on 22 Nov) |
| [`Docs/`](Docs) | Plan, generated numbers and results, budget, method, studies |
| [`score.py`](score.py), [`benchmark.py`](benchmark.py) | SE(3)-aligned scorer; runtime and heap gate |
| `main.cpp`, `Dockerfile.ccore` | A recorded C-core experiment: kept with its tests, never shipped |

</details>

<details>
<summary><b>📚 Research notes</b></summary>

<br>

- [Project deck](Docs/deck/ManipalInstituteofTechnology_Vortex.pdf) ([PowerPoint](Docs/deck/ManipalInstituteofTechnology_Vortex.pptx))
- [Track 3 plan](Docs/TRACK3_PLAN.md): registered decisions, open Q9 and next steps
- [Verified figures](Docs/NUMBERS.md): every quotable number, with source tags
- [Generated results](Docs/RESULTS.md): clean and degraded EuRoC metrics, stationary floor, ablations
- [Method](Docs/METHOD.md): test-set composition and metric definitions
- [Negative results](Docs/NEGATIVE_RESULTS.md): what we tried that didn't work
- [Official-script baseline](Docs/STEP2_BASELINE.md) and [TUM-VI baseline](Docs/TUMVI_BASELINE.md)
- [Blind-window study](Docs/BLIND.md): dead-sensor detection and forecast comparisons (before Step L3)
- [Confidence coverage](Docs/COVERAGE.md): why the per-row sigma isn't reported as calibrated
- [Rotor-drag study](Docs/DRAG.md): pre-registered NO-GO, with exploratory fits labelled as such
- [Budget ledger](Docs/BUDGET.md), [efficiency floor](Docs/FLOOR.md), [Docker benchmark](Docs/DOCKER_BENCH.md), [clean-machine check](Docs/CLEAN_MACHINE.md)
- [Scorer cross-check](Docs/EVO_CROSSCHECK.md): our scorer against evo on synthetic trajectories
- [Submission rules](Docs/SUBMISSION_RULES.md), [data instructions](Docs/DATA.md) and [third-party notices](THIRD_PARTY.md)

</details>

---

<div align="center">

**Built by Arnav Jain** · Manipal Institute of Technology · Submission name `VORTEX` (solo entry)

<sub>Code: [MIT](LICENSE). The film is original to this project. Samsung Research and Samsung PRISM marks identify the challenge context and are Samsung's; the [Research mark](https://cdn.codeground.org/nsr/images/layout/logo-sr.png) and [PRISM mark](https://www.samsungprism.com/assets/images/prism_logo.png) are reproduced from their official sites.</sub>

</div>

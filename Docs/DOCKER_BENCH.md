# Linux Docker Runtime, Heap, and `cProfile` Ledger (`AG-1` / `AG-4`)

Measured inside Linux Docker (`python:3.12.7-slim-bookworm`, built from `bundle/Dockerfile` at `main` commit `5ba1c4b`; estimator code identical to `550ba68` / `86711a9` with `SMOOTH_ON = True`, `PLATFORM_ON = True`, `TILT_ON = True`).

All input CSVs were copied directly onto the container's local Linux filesystem (`/tmp/inputs/*.csv`) via `docker cp` before running `python -S benchmark.py --runs 15 --gate --input <file>`, eliminating Windows-to-Linux bind-mount (`9P`) I/O and per-run `docker run` container creation overhead.

---

## 1. Headline Findings (`AG-1`)

- **In-process compute only (`pathfinder.run`, median of 15 runs):** **`29.39..35.53 µs/row`** (**`5.70..7.02 ms per IMU-second`**).
- **Whole process (`python -S main.py`, startup included, median of 15 runs):**
  - With cached bytecode: **`30.20..37.40 µs/row`** (**`5.88..7.22 ms per IMU-second`**).
  - From source (`-B -X pycache_prefix=...`, no cached bytecode, per Ledger A1/B7): **`30.89..38.86 µs/row`** (**`5.99..7.50 ms per IMU-second`**).
- **Why G4-dry measured `17.8..18.6 ms/IMU-s`:** Linux Docker compute + process startup on container-local storage is **`5.88..7.50 ms/IMU-s`**, matching native WSL2 (`~6.4 ms/IMU-s`). The ~`11 ms/IMU-s` difference in G4-dry came entirely from outer `docker run --rm -v <win_path>:/data` container lifecycle and Windows bind-mount I/O.
- **CC-1b gate check (`compute > 12 ms/IMU-s`):** Worst-case compute across all tested files is **`7.02 ms/IMU-s`** (`<= 12 ms/IMU-s` threshold and `<= 15 ms/IMU-s` target). **CC-1b is not needed / not blocked.**

---

## 2. 15-Run Linux Docker Benchmark Table (`commit = 5ba1c4b`, `python:3.12.7-slim-bookworm`)

Compute `ms/IMU-s` is calculated from the in-process full stage (`stages[-1]["us_per_row"] * rows / 1000 / imu_seconds`). Whole-process readings are the 15-run medians from `benchmark.py`.

| Tag | Input file | Rows (`imu_s`) | Compute only (µs/row) | Compute only (ms/IMU-s) | Whole process `-S` cached (µs/row) | Whole process `-S` cached (ms/IMU-s) | Whole process `-S` no-cache (µs/row) | Whole process `-S` no-cache (ms/IMU-s) | Heap in-proc / whole-run / no-cache (KB) | Peak RSS median (MiB) | Gate |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `ag1-mh01-b-s1` (run 1) | `MH_01_easy_b_s1` | 35,697 (`184.10s`) | 30.62 | 5.94 | 32.42 | 6.29 | 31.94 | 6.19 | 1110.0 / 5910.5 / 7367.2 | 10.88 | FAIL (1st-run 5910 KB > 4 MB) |
| `ag1-mh01-b-s1-r2` (steady) | `MH_01_easy_b_s1` | 35,697 (`184.10s`) | 29.39 | 5.70 | 30.73 | 5.96 | 30.89 | 5.99 | 1110.1 / 2219.1 / 7367.2 | 10.82 | PASS |
| `ag1-mh03-a-s1` | `MH_03_medium_a_s1` | 26,106 (`135.04s`) | 31.70 | 6.13 | 32.20 | 6.23 | 31.95 | 6.18 | 783.1 / 1882.7 / 7367.5 | 10.71 | PASS |
| `ag1-mh03-b-s1` | `MH_03_medium_b_s1` | 26,106 (`135.04s`) | 31.45 | 6.08 | 32.99 | 6.38 | 31.84 | 6.16 | 783.3 / 1882.7 / 7367.2 | 10.77 | PASS |
| `ag1-room3-a-s1` | `dataset-room3_512_16_a_s1` | 27,206 (`141.06s`) | 35.53 | 6.85 | 33.72 | 6.51 | 35.41 | 6.84 | 739.1 / 1842.5 / 7367.5 | 10.72 | PASS |
| `ag1-room3-b-s1` | `dataset-room3_512_16_b_s1` | 27,206 (`141.06s`) | 34.99 | 6.75 | 37.40 | 7.22 | 38.86 | 7.50 | 739.5 / 1842.9 / 7367.5 | 10.73 | PASS |
| `ag1-mh01-b-s3-longest-off` | `MH_01_easy_b_s3` (longest official) | 35,864 (`184.10s`) | 32.24 | 6.28 | 30.20 | 5.88 | 33.30 | 6.49 | 1110.0 / 2218.9 / 7367.2 | 10.84 | PASS |
| `ag1-mh01-clean-longest` | `MH_01_easy` clean (longest overall) | 36,820 (`184.10s`) | 35.11 | 7.02 | 31.68 | 6.34 | 33.64 | 6.73 | 1132.4 / 2242.6 / 7367.3 | 11.00 | PASS |

### Stage Breakdown (`in-process`, median `µs/row`, 15 runs, `commit = 5ba1c4b`)

| Tag | Stage 1: parse | Stage 2: parse + write | Stage 3: parse + init + strapdown | Stage 4: full `main.py` (with smoother + write) |
|---|---:|---:|---:|---:|
| `ag1-mh01-b-s1-r2` | 3.42 | 4.49 | 11.74 | 29.39 |
| `ag1-mh03-a-s1` | 1.59 | 2.41 | 11.39 | 31.70 |
| `ag1-mh03-b-s1` | 3.75 | 4.17 | 13.09 | 31.45 |
| `ag1-room3-a-s1` | 1.31 | 2.16 | 12.92 | 35.53 |
| `ag1-room3-b-s1` | 3.86 | 4.84 | 14.84 | 34.99 |
| `ag1-mh01-b-s3-longest-off` | 3.58 | 4.58 | 12.97 | 32.24 |
| `ag1-mh01-clean-longest` | 2.37 | 3.35 | 12.88 | 35.11 |

*(Note: reading `b` is accelerometer-first and therefore runs `_fe_canonical_lines` in Stage 1, adding ~`2.0..2.5 µs/row` over canonical reading `a`.)*

---

## 3. `cProfile` Top 15 Functions by Cumulative Time (`commit = 5ba1c4b`, Linux Docker Python 3.12.7)

### A. Longest overall file: `data/euroc/MH_01_easy` clean (`36,820` rows, `184.10 s`, canonical gyro-first)

Total profiled time: `1.537 s` (`1,367,605` function calls).

| Rank | `ncalls` | `tottime` (s) | `cumtime` (s) | Function (`pathfinder.py` / built-in) | Role |
|---:|---:|---:|---:|---|---|
| 1 | 1 | 0.000 | 1.537 | `pathfinder.py:1073(run)` | Top-level entry point |
| 2 | 1 | 0.000 | 1.501 | `pathfinder.py:1091(_run_smoothed)` | Two-pass forward + RTS smoother wrapper |
| 3 | 2 | 0.572 | 1.345 | `pathfinder.py:1107(_run)` | Forward strapdown + filter pass (called twice: store + write) |
| 4 | 628 | 0.226 | 0.227 | `pathfinder.py:816(_smooth_gain)` | 15x15 Cholesky + RTS smoother gain `C_k` at 0.25 s ticks |
| 5 | 7,536 | 0.128 | 0.128 | `pathfinder.py:661(_kf_update)` | Scalar Kalman measurement updates (V1/V2/V2P) |
| 6 | 1 | 0.000 | 0.124 | `pathfinder.py:262(_plat_hh)` | Step 7 platform detector wrapper |
| 7 | 1 | 0.108 | 0.124 | `pathfinder.py:203(_plat_stat)` | Step 7 platform detector file scan |
| 8 | 2 | 0.039 | 0.121 | `pathfinder.py:381(_calibrate)` | First-60 s stillness calibration scan |
| 9 | 34,808 | 0.087 | 0.108 | `pathfinder.py:175(_parse)` | CSV line parser in calibration/pre-anchor passes |
| 10 | 2 | 0.046 | 0.095 | `pathfinder.py:458(_pre_segment)` | Backward pre-anchor strapdown integration |
| 11 | 1,256 | 0.084 | 0.087 | `pathfinder.py:618(_kf_propagate)` | 15x15 covariance propagation (`F P F^T + Q`) |
| 12 | 149,265 | 0.057 | 0.057 | `{method 'split' of 'bytes' objects}` | Byte-line comma splitting |
| 13 | 1 | 0.017 | 0.036 | `pathfinder.py:971(_fe_detect)` | Front-end column order and unit detection (first 4,000 rows) |
| 14 | 1 | 0.005 | 0.032 | `pathfinder.py:889(_smooth_segments)` | Backward RTS recursion over stored tick blocks |
| 15 | 257,708 | 0.030 | 0.030 | `{method 'isdigit' of 'bytes' objects}` | Integer nanosecond timestamp check |

### B. Longest official copy: `data/official/MH_01_easy_b_s3` (`35,864` rows, `184.10 s`, non-canonical reading `b`)

Total profiled time: `1.601 s` (`1,971,181` function calls).

| Rank | `ncalls` | `tottime` (s) | `cumtime` (s) | Function (`pathfinder.py` / built-in) | Role |
|---:|---:|---:|---:|---|---|
| 1 | 1 | 0.000 | 1.601 | `pathfinder.py:1073(run)` | Top-level entry point |
| 2 | 1 | 0.000 | 1.356 | `pathfinder.py:1091(_run_smoothed)` | Two-pass forward + RTS smoother wrapper |
| 3 | 2 | 0.474 | 1.236 | `pathfinder.py:1107(_run)` | Forward strapdown + filter pass (store + write) |
| 4 | 608 | 0.251 | 0.252 | `pathfinder.py:816(_smooth_gain)` | 15x15 Cholesky + RTS smoother gain `C_k` |
| 5 | 1 | 0.008 | 0.214 | `{method 'writelines' of '_io._IOBase' objects}` | Writing temporary canonical CSV copy for reading `b` |
| 6 | 35,866 | 0.099 | 0.205 | `pathfinder.py:1048(_fe_canonical_lines)` | Front-end column reorder (`accel_first` -> `gyro_first`) |
| 7 | 7,296 | 0.127 | 0.127 | `pathfinder.py:661(_kf_update)` | Scalar Kalman measurement updates |
| 8 | 2 | 0.040 | 0.097 | `pathfinder.py:381(_calibrate)` | First-60 s stillness calibration scan |
| 9 | 2 | 0.049 | 0.088 | `pathfinder.py:458(_pre_segment)` | Backward pre-anchor strapdown integration |
| 10 | 1 | 0.000 | 0.087 | `pathfinder.py:262(_plat_hh)` | Step 7 platform detector wrapper |
| 11 | 1 | 0.071 | 0.087 | `pathfinder.py:203(_plat_stat)` | Step 7 platform detector file scan |
| 12 | 1,216 | 0.084 | 0.087 | `pathfinder.py:618(_kf_propagate)` | 15x15 covariance propagation |
| 13 | 34,678 | 0.050 | 0.072 | `pathfinder.py:175(_parse)` | CSV line parser in calibration/pre-anchor passes |
| 14 | 182,131 | 0.067 | 0.067 | `{method 'split' of 'bytes' objects}` | Byte-line comma splitting |
| 15 | 35,864 | 0.026 | 0.044 | `pathfinder.py:1033(_fe_ns_text)` | Exact nanosecond timestamp canonicalisation |

---

## 4. Independent Scorer Cross-Check (`AG-4`: `tools/ape_check.py` vs `score.py`)

### 4.1 Benchmarked `main` Trajectories (`commit = 5ba1c4b` / `3ddb2a4`)

Every benchmarked trajectory (shipped estimator `pathfinder.py` at `5ba1c4b` / `3ddb2a4`, identical estimator code, and never-moving floor `tools/baseline_still.py`) was scored independently with `score.py` (`vortex.scoring`) and `tools/ape_check.py` (SE(3) translational ATE RMSE). *(Correction, 20 Nov 2026: the initial revision of this table accidentally executed `main.py` from an older checkout `3559fe4` before Step 7 `PLATFORM_ON`, giving `3.746328` / `3.658338 m` on `room3_{a,b}_s1`; Sections 1–3 Docker runs genuinely used `5ba1c4b`. All 14 rows below were re-run directly against `origin/main@3ddb2a4`.)*

| Input sequence / copy | Trajectory | `score.py` ATE RMSE (m) | `tools/ape_check.py` ATE RMSE (m) | Difference (mm) | Matched poses |
|---|---|---:|---:|---:|---:|
| `MH_01_easy_b_s1` | estimator (`5ba1c4b` / `3ddb2a4`) | 4.204419 | 4.204419 | 0.000000 | 35,233 |
| `MH_01_easy_b_s1` | floor (`baseline_still.py`) | 4.321501 | 4.321501 | 0.000000 | 35,233 |
| `MH_03_medium_a_s1` | estimator (`5ba1c4b` / `3ddb2a4`) | 3.236912 | 3.236912 | 0.000000 | 25,376 |
| `MH_03_medium_a_s1` | floor (`baseline_still.py`) | 3.587666 | 3.587666 | 0.000000 | 25,376 |
| `MH_03_medium_b_s1` | estimator (`5ba1c4b` / `3ddb2a4`) | 2.861685 | 2.861685 | 0.000000 | 25,376 |
| `MH_03_medium_b_s1` | floor (`baseline_still.py`) | 3.587666 | 3.587666 | 0.000000 | 25,376 |
| `dataset-room3_512_16_a_s1` | estimator (`5ba1c4b` / `3ddb2a4`) | 1.185522 | 1.185522 | 0.000000 | 15,059 |
| `dataset-room3_512_16_a_s1` | floor (`baseline_still.py`) | 1.248938 | 1.248938 | 0.000000 | 15,059 |
| `dataset-room3_512_16_b_s1` | estimator (`5ba1c4b` / `3ddb2a4`) | 1.177312 | 1.177312 | 0.000000 | 15,059 |
| `dataset-room3_512_16_b_s1` | floor (`baseline_still.py`) | 1.248938 | 1.248938 | 0.000000 | 15,059 |
| `MH_01_easy_b_s3` | estimator (`5ba1c4b` / `3ddb2a4`) | 4.032716 | 4.032716 | 0.000000 | 35,392 |
| `MH_01_easy_b_s3` | floor (`baseline_still.py`) | 4.315114 | 4.315114 | 0.000000 | 35,392 |
| `MH_01_easy` (clean) | estimator (`5ba1c4b` / `3ddb2a4`) | 4.232143 | 4.232143 | 0.000000 | 36,382 |
| `MH_01_easy` (clean) | floor (`baseline_still.py`) | 4.307574 | 4.307574 | 0.000000 | 36,382 |

Largest difference across all 14 trajectories: **`0.000000 mm`** (`0.0 mm`, well below the `1 mm` escalation threshold).

### 4.2 Rule H Verdict Cross-Check (`AG-4`, `track3/stepL3-blind@d1aa245`, estimator `fb36d77` / `a5f5bd1`)

After CC-L3 judged Rule H OFF (`Docs/results/stepH-verdict.txt` at `d1aa245`), AG regenerated all **168 Rule H verdict trajectories** (`H` EuRoC seeds `13–15` off/on/floor, `T` TUM-VI `room3/4` seeds `13–15` off/on/floor, clean `C` EuRoC off/on, clean `CT` TUM-VI off/on) plus all **24 Rule H' clean trajectories** (`HP-C`, `HP-CT`) directly from `origin/track3/stepL3-blind:pathfinder.py` (`fb36d77`), and compared `tools/ape_check.py` (ChatGPT's independent pure-Python SE(3) scorer, unchanged) against both CC-L3's committed JSON `ape_se3_rmse`/`ate_se3_rmse` values and `score.py`. No Rule H' held-out seed `22–24` or `V2_*` files were touched.

| Block | CC-L3 JSON (`d1aa245`) | Runs | Max `\|CC JSON − ape_check\|` (mm) | Max `\|score.py − ape_check\|` (mm) | Worst-diff sequence |
|---|---|---:|---:|---:|---|
| `H-off` (EuRoC s13–15, `BLIND_ON=False`) | `Docs/results/stepH-H-off.json` | 36 | `0.000000` (`8.88e-13`) | `0.000000` (`8.88e-13`) | `V1_01_easy_a_s15` |
| `H-on` (EuRoC s13–15, `BLIND_ON=True`) | `Docs/results/stepH-H-on.json` | 36 | `0.000000` (`8.88e-13`) | `0.000000` (`8.88e-13`) | `MH_05_difficult_b_s13` |
| `H-flr` (EuRoC s13–15, floor) | `Docs/results/stepH-H-floor.json` | 36 | `0.000000` (`8.88e-13`) | `0.000000` (`8.88e-13`) | `MH_05_difficult_b_s13` |
| `T-off` (TUM-VI room3/4 s13–15, OFF) | `Docs/tumvi/stepH-T-off.json` | 12 | `0.000000` (`2.22e-13`) | `0.000000` (`2.22e-13`) | `dataset-room3_512_16_b_s15` |
| `T-on` (TUM-VI room3/4 s13–15, ON) | `Docs/tumvi/stepH-T-on.json` | 12 | `0.000000` (`2.22e-13`) | `0.000000` (`2.22e-13`) | `dataset-room3_512_16_b_s13` |
| `T-flr` (TUM-VI room3/4 s13–15, floor) | `Docs/tumvi/stepH-T-floor.json` | 12 | `0.000000` (`0.0`) | `0.000000` (`0.0`) | `dataset-room4_512_16_b_s15` |
| `C-off` (clean EuRoC, OFF) | `Docs/results/stepH-C-off.json` | 8 | `0.000000` (`8.88e-13`) | `0.000000` (`8.88e-13`) | `MH_04_difficult` |
| `C-on` (clean EuRoC, ON) | `Docs/results/stepH-C-on.json` | 8 | `0.000000` (`8.88e-13`) | `0.000000` (`8.88e-13`) | `MH_02_easy` |
| `CT-off` (clean TUM-VI, OFF) | `Docs/tumvi/stepH-CT-off.json` | 4 | `0.000000` (`0.0`) | `0.000000` (`0.0`) | `dataset-room4_512_16` |
| `CT-on` (clean TUM-VI, ON) | `Docs/tumvi/stepH-CT-on.json` | 4 | `0.000000` (`0.0`) | `0.000000` (`0.0`) | `dataset-room4_512_16` |
| `HP-C-off` (clean EuRoC, `DEAD_ONLY`, OFF) | `Docs/results/stepHP-C-off.json` | 8 | `0.000000` (`8.88e-13`) | `0.000000` (`8.88e-13`) | `MH_04_difficult` |
| `HP-C-on` (clean EuRoC, `DEAD_ONLY`, ON) | `Docs/results/stepHP-C-on.json` | 8 | `0.000000` (`8.88e-13`) | `0.000000` (`8.88e-13`) | `MH_04_difficult` |
| `HP-CT-off` (clean TUM-VI, `DEAD_ONLY`, OFF) | `Docs/tumvi/stepHP-CT-off.json` | 4 | `0.000000` (`0.0`) | `0.000000` (`0.0`) | `dataset-room4_512_16` |
| `HP-CT-on` (clean TUM-VI, `DEAD_ONLY`, ON) | `Docs/tumvi/stepHP-CT-on.json` | 4 | `0.000000` (`0.0`) | `0.000000` (`0.0`) | `dataset-room4_512_16` |

- **Global maximum difference across all 192 trajectories:** **`0.000000 mm`** (`8.88e-13 mm`, floating-point rounding only, well below the `1 mm` escalation limit; `HP-C-on` `MH_04_difficult`: `6.264892692099578` vs `6.264892692099577 m`).
- **CLI spot-checks (`python tools/ape_check.py --gt ... --est ...`):**
  - `H-on` `MH_04_difficult_b_s13`: `ATE RMSE m: 6.18326022834` (`19,674` matched poses; CC JSON `6.1832602283429985 m`).
  - `T-on` `dataset-room3_512_16_b_s13`: `ATE RMSE m: 1.19618176002` (`15,118` matched poses; CC JSON `1.1961817600169873 m`).
- **Not verified by `tools/ape_check.py`:** `tools/ape_check.py` checks full-trajectory SE(3) translational ATE RMSE only; it does not independently recompute phase-windowed `blind_rmse`, `gap_rmse_mean`, or `rpe200_rmse`.

### 4.3 Rule H' Held-Out Cross-Check (`AG-4`, `track3/stepL3-blind@3b3ad2e`, estimator `fb36d77` / `3b3ad2e`)

After CC-L3 recorded Rule H' held-out Conditions 1–7 PASS on seeds `22–24` (`3b3ad2e`, `BLIND_DEAD_ONLY=True`), AG regenerated all **144 Rule H' held-out trajectories** (`HP-H` EuRoC seeds `22–24` off/on/floor, `HP-T` TUM-VI `room3/4` seeds `22–24` off/on/floor) directly from `origin/track3/stepL3-blind:pathfinder.py` (`3b3ad2e`, identical estimator code to `fb36d77`) and cross-checked `tools/ape_check.py` against both CC-L3's committed JSONs and `score.py`. Zero `V2_*` or TUM-VI `s19–21` files were touched.

| Block | CC-L3 JSON (`3b3ad2e`) | Runs | Max `\|CC JSON − ape_check\|` (mm) | Max `\|score.py − ape_check\|` (mm) | Worst-diff sequence |
|---|---|---:|---:|---:|---|
| `HP-H-off` (EuRoC s22–24, `BLIND_ON=False`) | `Docs/results/stepHP-H-off.json` | 36 | `0.000000` (`8.88e-13`) | `0.000000` (`8.88e-13`) | `MH_05_difficult_b_s24` |
| `HP-H-on` (EuRoC s22–24, `BLIND_ON=True`, `DEAD_ONLY`) | `Docs/results/stepHP-H-on.json` | 36 | `0.000000` (`8.88e-13`) | `0.000000` (`8.88e-13`) | `MH_05_difficult_a_s24` |
| `HP-H-flr` (EuRoC s22–24, floor) | `Docs/results/stepHP-H-floor.json` | 36 | `0.000000` (`8.88e-13`) | `0.000000` (`8.88e-13`) | `MH_05_difficult_b_s22` |
| `HP-T-off` (TUM-VI room3/4 s22–24, OFF) | `Docs/tumvi/stepHP-T-off.json` | 12 | `0.000000` (`4.44e-13`) | `0.000000` (`4.44e-13`) | `dataset-room4_512_16_a_s24` |
| `HP-T-on` (TUM-VI room3/4 s22–24, ON, `DEAD_ONLY`) | `Docs/tumvi/stepHP-T-on.json` | 12 | `0.000000` (`1.11e-13`) | `0.000000` (`1.11e-13`) | `dataset-room4_512_16_b_s23` |
| `HP-T-flr` (TUM-VI room3/4 s22–24, floor) | `Docs/tumvi/stepHP-T-floor.json` | 12 | `0.000000` (`0.0`) | `0.000000` (`0.0`) | `dataset-room4_512_16_b_s24` |

- **Global maximum difference across all 144 Rule H' held-out trajectories (and all 336 combined Step L3 trajectories across Sec 4.2 + 4.3):** **`0.000000 mm`** (`8.88e-13 mm`, floating-point rounding only; `HP-H-flr` `MH_05_difficult_b_s22`: `6.870540660854006` vs `6.870540660854005 m`).
- **CLI spot-checks (`python tools/ape_check.py --gt ... --est ...`):**
  - `HP-H-on` `MH_04_difficult_b_s22`: `ATE RMSE m: 6.31895686446` (`19,683` matched poses; CC JSON `6.31895686445924 m`).
  - `HP-T-on` `dataset-room3_512_16_b_s22`: `ATE RMSE m: 1.15790266807` (`15,083` matched poses; CC JSON `1.1579026680652604 m`).
- **Not verified here:** Phase-windowed `blind_rmse`, `gap_rmse_mean`, `rpe200_rmse` (not computed by `tools/ape_check.py`).

---

## 5. FINAL Shipped CHUNKED Bundle: 15-Run Linux Docker Benchmark (`main@5e28668`, PR `#79`)

Measured inside the staged submission `bundle/Dockerfile` container (`python:3.12.7-slim-bookworm`, `ENTRYPOINT=["python", "-S", "/app/main.py"]`), built directly from `origin/main@5e28668` (`BLIND_ON=True`, `BLIND_DEAD_ONLY=True`, `CHUNKED` `src/main.py` SHA-256 `feb222ea9f27f077`). Every input CSV was copied onto container-local `/tmp/inputs/*.csv` via `docker cp` (no bind mounts). Each row is the **15-run median** of whole-process `python -S -B /app/main.py` (from source, zero bytecode), peak RSS via GNU `/usr/bin/time -v`, and direct `exec(compile)` whole-run `tracemalloc` peak (`typing_loaded=False`).

| Tag | Input file | Rows (`imu_s`) | Whole process `-S -B` median (`µs/row`) | Whole process `-S -B` median (`ms/IMU-s`) | Min (`ms/IMU-s`) | Direct `exec(compile)` heap (`KB`) | Peak RSS median (`MiB`) | Output SHA-256 (16 hex) |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `ag1-final-mh01-b-s1` | `MH_01_easy_b_s1` | 35,697 (`184.10s`) | 35.59 | **6.90** | 6.48 | 2,974.3 | 13.06 | `92fe58fe72028535` |
| `ag1-final-mh03-a-s1` | `MH_03_medium_a_s1` | 26,106 (`135.03s`) | 35.02 | **6.77** | 6.49 | 2,974.3 | 13.06 | `d72f2c299f637b5e` |
| `ag1-final-mh03-b-s1` | `MH_03_medium_b_s1` | 26,106 (`135.03s`) | 34.15 | **6.60** | 6.53 | 2,974.3 | 13.07 | `0e215ee3b078eaea` |
| `ag1-final-room3-a-s1` | `dataset-room3_512_16_a_s1` | 27,241 (`141.05s`) | 36.63 | **7.07** | 6.86 | 2,974.3 | 13.27 | `61af6b6530ac1514` |
| `ag1-final-room3-b-s1` | `dataset-room3_512_16_b_s1` | 27,241 (`141.05s`) | 39.71 | **7.67** | 7.41 | 2,974.3 | 13.28 | `bd75c9364f0face9` |
| `ag1-final-mh01-b-s3` | `MH_01_easy_b_s3` (longest official) | 35,864 (`184.10s`) | 33.65 | **6.56** | 6.35 | 2,974.2 | 13.10 | `a5258b3c6f4f0eeb` |
| `ag1-final-mh01-clean` | `MH_01_easy` clean (longest overall) | 36,820 (`184.10s`) | 35.89 | **7.18** | 6.84 | 2,974.2 | 13.21 | `d90f765bf1aa13a3` |

- **Headline (`FINAL`, `main@5e28668` CHUNKED inside `bundle/Dockerfile`):**
  - Whole-process from-source wall time (`python -S -B`, 15-run median): **`6.56 – 7.67 ms/IMU-s`** (`33.65 – 39.71 µs/row`) — more than 2× below the `15 ms/IMU-s` target and `20 ms/IMU-s` escalation limit.
  - Direct `exec(compile)` whole-run `tracemalloc` peak: **`2,974.2 – 2,974.3 KB` (`2.90 MB`)** across all 7 files (flat to `0.1 KB`, confirming `O(1)` memory independent of sequence length, well under half the `8 MB` cap).
  - Peak RSS (whole Linux Python 3.12.7 process): **`13.06 – 13.28 MiB`**.
  - Output SHA-256 hashes (`92fe58fe72028535`, `0e215ee3b078eaea`, `bd75c9364f0face9`) match `Docs/CLEAN_MACHINE.md` Section 2 byte-for-byte.

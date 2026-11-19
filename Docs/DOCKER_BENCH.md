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

## 4. Independent Scorer Cross-Check (`AG-4`: `tools/ape_check.py` vs `score.py`, `commit = 5ba1c4b`)

Every benchmarked trajectory (shipped estimator `main.py` at `5ba1c4b` and never-moving floor `tools/baseline_still.py`) was scored independently with `score.py` and `tools/ape_check.py` (SE(3) translational ATE RMSE):

| Input sequence / copy | Trajectory | `score.py` ATE RMSE (m) | `tools/ape_check.py` ATE RMSE (m) | Difference (mm) | Matched poses |
|---|---|---:|---:|---:|---:|
| `MH_01_easy_b_s1` | estimator (`5ba1c4b`) | 4.204419 | 4.204419 | 0.000000 | 35,233 |
| `MH_01_easy_b_s1` | floor (`baseline_still.py`) | 4.321501 | 4.321501 | 0.000000 | 35,233 |
| `MH_03_medium_a_s1` | estimator (`5ba1c4b`) | 3.236912 | 3.236912 | 0.000000 | 25,376 |
| `MH_03_medium_a_s1` | floor (`baseline_still.py`) | 3.587666 | 3.587666 | 0.000000 | 25,376 |
| `MH_03_medium_b_s1` | estimator (`5ba1c4b`) | 2.861685 | 2.861685 | 0.000000 | 25,376 |
| `MH_03_medium_b_s1` | floor (`baseline_still.py`) | 3.587666 | 3.587666 | 0.000000 | 25,376 |
| `dataset-room3_512_16_a_s1` | estimator (`5ba1c4b`) | 3.746328 | 3.746328 | 0.000000 | 15,059 |
| `dataset-room3_512_16_a_s1` | floor (`baseline_still.py`) | 1.248938 | 1.248938 | 0.000000 | 15,059 |
| `dataset-room3_512_16_b_s1` | estimator (`5ba1c4b`) | 3.658338 | 3.658338 | 0.000000 | 15,059 |
| `dataset-room3_512_16_b_s1` | floor (`baseline_still.py`) | 1.248938 | 1.248938 | 0.000000 | 15,059 |
| `MH_01_easy_b_s3` | estimator (`5ba1c4b`) | 4.032716 | 4.032716 | 0.000000 | 35,392 |
| `MH_01_easy_b_s3` | floor (`baseline_still.py`) | 4.315114 | 4.315114 | 0.000000 | 35,392 |
| `MH_01_easy` (clean) | estimator (`5ba1c4b`) | 4.232143 | 4.232143 | 0.000000 | 36,382 |
| `MH_01_easy` (clean) | floor (`baseline_still.py`) | 4.307574 | 4.307574 | 0.000000 | 36,382 |

Largest difference across all 14 trajectories: **`0.000000 mm`** (well below the `1 mm` escalation threshold).

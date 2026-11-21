# Clean-Machine Matrix (`AG-3`)

Verification ledger produced by `tools/clean_machine_check.py` (stdlib-only fresh bare virtual environments across Windows Python 3.13/3.14, Linux Docker Python 3.10–3.14, and the bundled `Dockerfile` image).

---

## 1. Pre-CC-1a Baseline: `main` (`5ba1c4b`) `pathfinder.py` & `dist/vortex_v0.95.zip` (`86711a9`) across Python 3.10–3.14

Before `CC-1a` (`track3/freeze-build`, PR `#79`) shipped the single-file CHUNKED B1/B2/B4 entry point, this baseline closed the Python `3.10` / `3.11` runtime blind spot and verified `dist/vortex_v0.95.zip`'s `Dockerfile` image on container-local storage (no Windows bind-mounts).

Each fresh bare venv (`python -m venv --without-pip`) ran standalone `pathfinder.py` (`python -S pathfinder.py IN OUT`, copied alone into an empty folder with zero sibling imports and zero packages installed); `v0.95-dockerfile` built `dist/vortex_v0.95.zip`'s `Dockerfile` and ran `python -S /app/main.py IN OUT`.

### A. `data/official/MH_03_medium_b_s1` (`26,106` rows) — Cross-version byte identity: **PASS (`1` unique SHA-256 across `8` environments)**

| Environment | Python | OS / Image | `vortex.check_output` | Output SHA-256 (16 hex) | Byte-identical across matrix? |
|---|---|---|---|---|---|
| `win-venv-3.13` | 3.13.5 | Windows (bare venv) | PASS | `03ada1d088015775` | YES |
| `win-venv-3.14` | 3.14.7 | Windows (bare venv) | PASS | `03ada1d088015775` | YES |
| `docker-3.10` | 3.10.22 | `python:3.10-slim-bookworm` (bare venv) | PASS | `03ada1d088015775` | YES |
| `docker-3.11` | 3.11.18 | `python:3.11-slim-bookworm` (bare venv) | PASS | `03ada1d088015775` | YES |
| `docker-3.12` | 3.12.7 | `python:3.12.7-slim-bookworm` (bare venv) | PASS | `03ada1d088015775` | YES |
| `docker-3.13` | 3.13.18 | `python:3.13-slim-bookworm` (bare venv) | PASS | `03ada1d088015775` | YES |
| `docker-3.14` | 3.14.10 | `python:3.14-slim` (bare venv) | PASS | `03ada1d088015775` | YES |
| `v0.95-dockerfile` | 3.12.7 | `dist/vortex_v0.95.zip` `Dockerfile` | PASS | `03ada1d088015775` | YES |

### B. `data/official_tumvi/dataset-room3_512_16_b_s1` (`27,206` rows) — Cross-version byte identity: **PASS (`1` unique SHA-256 across `8` environments)**

| Environment | Python | OS / Image | `vortex.check_output` | Output SHA-256 (16 hex) | Byte-identical across matrix? |
|---|---|---|---|---|---|
| `win-venv-3.13` | 3.13.5 | Windows (bare venv) | PASS | `d3a08d9ab2224404` | YES |
| `win-venv-3.14` | 3.14.7 | Windows (bare venv) | PASS | `d3a08d9ab2224404` | YES |
| `docker-3.10` | 3.10.22 | `python:3.10-slim-bookworm` (bare venv) | PASS | `d3a08d9ab2224404` | YES |
| `docker-3.11` | 3.11.18 | `python:3.11-slim-bookworm` (bare venv) | PASS | `d3a08d9ab2224404` | YES |
| `docker-3.12` | 3.12.7 | `python:3.12.7-slim-bookworm` (bare venv) | PASS | `d3a08d9ab2224404` | YES |
| `docker-3.13` | 3.13.18 | `python:3.13-slim-bookworm` (bare venv) | PASS | `d3a08d9ab2224404` | YES |
| `docker-3.14` | 3.14.10 | `python:3.14-slim` (bare venv) | PASS | `d3a08d9ab2224404` | YES |
| `v0.95-dockerfile` | 3.12.7 | `dist/vortex_v0.95.zip` `Dockerfile` | PASS | `d3a08d9ab2224404` | YES |

---

## 2. FINAL Freeze-Build Matrix (`main@5e28668`, PR `#79` CHUNKED Single-File Bundle)

- **Artifact tested:** staged zip built directly from `origin/main@5e28668` (`python tools/make_bundle.py stage` + `zip`, layout `CHUNKED`, `15` chunks `<= 120` lines, `BLIND_ON=True`, `BLIND_DEAD_ONLY=True`).
- **`src/main.py` SHA-256:** `feb222ea9f27f077c9113b39edd7cb513a6a3e496ec4db35f3c9416349d10811` (`1,962` lines, `83,541` bytes; byte-identical to `track3/freeze-build@69f52d9`, `1a83381`, and `9a304c7`).
- **Scope:** **5 inputs × 8 clean environments = `670/670` total case checks PASS (`0` failures)** — every fresh bare venv runs `src/main.py` ALONE in an empty directory with no sibling imports and no installed packages (`11/11` B1 invocation forms with/without `-S` from another cwd, `6/6` B2 formatting variants, `2/2` B4 injected-failure constant-pose fallback exit `0` + missing-input non-zero exit, `vortex.check_output` PASS); `zip-dockerfile` builds `bundle/Dockerfile` (`python:3.12.7-slim-bookworm`) and runs its configured `ENTRYPOINT` on container-local storage.

### 2.1 Cross-Version Correctness & Byte-Identity Summary (`FINAL`, 5 inputs × 8 envs)

| Input file | Rows | Environments passing B1/B2/B4 + `check_output` | Unique SHA-256 | Output SHA-256 (16 hex) | Byte-identical across 8 envs? |
|---|---:|---|---:|---|---|
| `data/official/MH_01_easy_b_s1` | 35,342 | `8/8` (`7 x 19 + 1 = 134/134`) | `1` | `92fe58fe72028535` | **YES (8/8)** |
| `data/official/MH_03_medium_b_s1` | 26,106 | `8/8` (`134/134`) | `1` | `0e215ee3b078eaea` | **YES (8/8)** |
| `data/official_tumvi/dataset-room3_512_16_b_s1` | 27,241 | `8/8` (`134/134`) | `1` | `bd75c9364f0face9` | **YES (8/8)** |
| `data/official/MH_03_medium_b_s22` | 26,106 | `8/8` (`134/134`) | `1` | `f4a2f441dc9e4121` | **YES (8/8)** |
| `data/official_tumvi/dataset-room3_512_16_b_s22` | 27,241 | `8/8` (`134/134`) | `1` | `8fea7c76a2545da0` | **YES (8/8)** |

### 2.2 From-Source Whole-Run Heap (`tracemalloc`) & Cold Speed on `MH_01_easy_b_s1` (`FINAL`, `35,342` rows, `182.10 s` IMU)

Both the **direct `exec(compile)` whole-run peak** (measuring `src/main.py` itself without `runpy`) and the **exact `tools/bundle_layouts.py` `runpy.run_path` probe** are reported below (`python -S -B`, no bundle bytecode).

| Environment | Python | Direct `exec(compile)` peak (KB) | `runpy.run_path` probe peak (KB) | `-X tracemalloc=1` peak (KB) | `> 7 MB` flag (`runpy` / direct) | Median `us/row` (5 runs) | Median `ms/IMU-s` | Timing flag |
|---|---|---:|---:|---:|---|---:|---:|---|
| `win-venv-3.13` | 3.13.5 | 3,516.2 | 4,158.1 | 6,080.8 | OK / OK | 64.08 | 12.43 | OK (<= 15 ms) |
| `win-venv-3.14` | 3.14.7 | 3,343.7 | 3,475.9 | 7,043.2 | OK / OK | 61.90 | 12.00 | OK (<= 15 ms) |
| `docker-3.10` | 3.10.22 | 2,459.0 | 2,609.6 | 5,945.1 | OK / OK | 49.53 | 9.60 | OK (<= 15 ms) |
| `docker-3.11` | 3.11.18 | 2,694.0 | 5,729.6 | 8,002.8 | OK / OK | 39.85 | 7.73 | OK (<= 15 ms) |
| `docker-3.12` | 3.12.7 | 2,973.3 | 5,659.1 | 7,743.9 | OK / OK | 37.73 | 7.32 | OK (<= 15 ms) |
| `docker-3.13` | 3.13.18 | 3,238.3 | 7,359.9 | 9,543.6 | **FLAG (> 7 MB, `runpy` artifact)** / **OK (3.16 MB)** | 41.29 | 8.01 | OK (<= 15 ms) |
| `docker-3.14` | 3.14.10 | 3,344.7 | 3,274.6 | 6,968.1 | OK / OK | 41.02 | 7.95 | OK (<= 15 ms) |
| `zip-dockerfile` | 3.12.7 | *(same image as `docker-3.12`: 2,973.3)* | 5,658.9 | 7,746.6 | OK / OK | **32.93** | **6.39** | OK (<= 15 ms) |

> **Root-cause note on the `docker-3.13` `runpy.run_path` flag (`7,359.9 KB` = `7.19 MB`, `< 8 MB`):**
> - Windows `win-venv-3.14` (`3,475.9 KB`) and `win-venv-3.13` (`4,158.1 KB`) match CC-freeze's `3,476` / `4,157 KB` within `1 KB`.
> - A `tracemalloc` snapshot on `python:3.13-slim-bookworm` proved why `runpy.run_path` jumped by `+4.1 MB` relative to direct execution: the official `python:3.11/3.12/3.13-slim-bookworm` Docker images strip most stdlib `.pyc` files (only 11–12 `.pyc` files remain in `/usr/local/lib/python3.1x/__pycache__`, excluding `typing.pyc`). Calling `runpy.run_path()` inside `tracemalloc` imports `typing.py` and compiles its 4,000+ lines from source.
> - `src/main.py` itself **never imports `typing`** (`typing_loaded=False` across all 7 Pythons). Under direct `exec(compile)` (matching `python -S src/main.py`), **every single Python 3.10–3.14 on Windows and Linux Docker peaks at `2,459.0 – 3,516.2 KB` (`2.40 – 3.43 MB`)** — well below half of `7 MB`.

### 2.3 From-Source Heap (`runpy` probe) & Cold Speed on `MH_03_medium_b_s1` & `dataset-room3_512_16_b_s1` (`FINAL`, 5 runs)

| Environment | Python | `MH_03_b_s1` heap (KB) | `MH_03_b_s1` `us/row` | `MH_03_b_s1` `ms/IMU-s` | `room3_b_s1` heap (KB) | `room3_b_s1` `us/row` | `room3_b_s1` `ms/IMU-s` |
|---|---|---:|---:|---:|---:|---:|---:|
| `win-venv-3.13` | 3.13.5 | 4,158.0 | 72.00 | 13.92 | 4,158.1 | 81.86 | 15.81 * |
| `win-venv-3.14` | 3.14.7 | 3,475.9 | 81.02 | 15.66 * | 3,475.9 | 86.10 | 16.63 * |
| `docker-3.10` | 3.10.22 | 2,609.7 | 47.54 | 9.19 | 2,609.8 | 53.79 | 10.39 |
| `docker-3.11` | 3.11.18 | 5,729.6 | 40.19 | 7.77 | 5,729.6 | 45.20 | 8.73 |
| `docker-3.12` | 3.12.7 | 5,659.2 | 33.94 | 6.56 | 5,659.2 | 38.28 | 7.39 |
| `docker-3.13` | 3.13.18 | 7,359.9 † | 41.20 | 7.97 | 7,359.8 † | 46.57 | 8.99 |
| `docker-3.14` | 3.14.10 | 3,274.6 | 42.71 | 8.26 | 3,274.6 | 48.54 | 9.37 |
| `zip-dockerfile` | 3.12.7 | 5,658.9 | **35.67** | **6.90** | 5,658.9 | **38.27** | **7.39** |

- `†` `docker-3.13` `runpy.run_path` `typing.pyc` probe artifact (`> 7 MB`, `< 8 MB`); true direct-exec peak is `3,238.3 KB` (`3.16 MB`).
- `*` Windows host slow-clock phase during `01:17–01:56 IST` (`15.66–16.63 ms/IMU-s`, `< 20 ms`); Linux Docker across all 6 Docker environments on the exact same run measured **`6.56 – 10.39 ms/IMU-s`** (`zip-dockerfile` `6.90` / `7.39 ms/IMU-s`, all `<= 10.4 ms/IMU-s`).

### 2.4 Reproduction

```powershell
python tools/make_bundle.py stage --dir dist/stage
python tools/make_bundle.py zip --name vortex_5e28668 --dir dist/stage --out dist
python tools/clean_machine_check.py --zip dist/vortex_5e28668.zip --input data/official/MH_01_easy_b_s1/mav0/imu0/data.csv --envs win-venv-3.13,win-venv-3.14,docker-3.10,docker-3.11,docker-3.12,docker-3.13,docker-3.14,zip-dockerfile --bench-runs 5 --commit 5e28668
```

---

## 3. FINAL `v1.0` Submission Zip Verification (`dist/vortex_v1.0.zip` = `dist/Vortex.zip`, tag `v1.0` `0e7c81d`)

- **Archive verified:** `dist/vortex_v1.0.zip` (`781,993` bytes; byte-identical to `Vortex-v1/dist/Vortex.zip`).
- **Archive SHA-256:** `e251c4010248caf5103bbf2923122146bba64ae7e2b225069a89672ffbd4447c` (**MATCH** against `LOOP_CC.md@32ea1b4`).
- **Contents (7 files, zero `.pyc` or compiled files):** `Dockerfile`, `LICENSE`, `MANIFEST.txt`, `README.md`, `estimated_trajectory.txt`, `metadata.json`, `src/main.py`.
- **Bundled `src/main.py` SHA-256:** `feb222ea9f27f077c9113b39edd7cb513a6a3e496ec4db35f3c9416349d10811` (byte-identical to Section 2 `main@5e28668`).
- **Bundled `estimated_trajectory.txt` (`MH_03_medium_b_s1`):** `vortex.check_output` **PASS** (`26,106` rows), SHA-256 `0e215ee3b078eaea` (byte-identical to Section 2).

Unzipped to an empty directory outside the repository and executed `src/main.py` in fresh bare virtual environments (`win-venv-3.13`, `win-venv-3.14`, `docker-3.12`) across 4 invocation modes (`no_args` with `-S`, `no_args` without `-S`, `IN OUT` with `-S`, `IN OUT` without `-S`) × 2 sequences (`MH_03_medium_b_s1`, `dataset-room3_512_16_b_s1`) = **`24/24` PASS**:

| Environment | Python | `MH_03_b_s1` (`no_args` & `IN OUT`, ±`-S`) | `MH_03_b_s1` SHA-256 (16 hex) | `room3_b_s1` (`no_args` & `IN OUT`, ±`-S`) | `room3_b_s1` SHA-256 (16 hex) | Matches Sec 2? |
|---|---|---|---|---|---|---|
| `win-venv-3.13` | 3.13.5 | `4/4` `check_output` PASS | `0e215ee3b078eaea` | `4/4` `check_output` PASS | `bd75c9364f0face9` | **YES** |
| `win-venv-3.14` | 3.14.7 | `4/4` `check_output` PASS | `0e215ee3b078eaea` | `4/4` `check_output` PASS | `bd75c9364f0face9` | **YES** |
| `docker-3.12` | 3.12.7 | `4/4` `check_output` PASS | `0e215ee3b078eaea` | `4/4` `check_output` PASS | `bd75c9364f0face9` | **YES** |

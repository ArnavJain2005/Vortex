# Vortex: trajectory from a degraded IMU (Samsung PRISM XR Hackathon 2026, Track 3)

Python only, as the organisers require (FAQ, 17 Nov 2026).

## Run

```
python -S src/main.py <imu0/data.csv> <estimated_trajectory.txt>
```

Pure Python 3, standard library only (`sys`, `math`, `array`): no numpy, nothing to install. Single
thread, offline, deterministic. Tested with CPython 3.12, 3.13 and 3.14. `main.py` is a stub that
imports `src/pathfinder.py` (the estimator), so Python loads the shipped bytecode (`src/__pycache__`)
instead of compiling the estimator on every run.

## Budget (measured on our laptop, Intel i7-14650HX, Windows 11; `benchmark.py`, `Docs/BUDGET.md`)

The 8 MB limit is measured at algorithm / heap level (FAQ), so we measure the heap with `tracemalloc`,
started before `main.py` runs.

| Input | Heap peak, whole run | Time per IMU row | ms per IMU-second |
|---|---|---|---|
| EuRoC MH_01 (36,820 rows, 184 s), Python 3.14 | 1.06 MB | 11.7 us | 2.3 |
| SYNTHETIC 36,000 rows, Python 3.14 / 3.13 | 0.76 / 1.19 MB | 13.5 / 9.4 us | 2.7 / 1.9 |

With no matching bytecode (another Python version), Python compiles `pathfinder.py` first and the
parser and compiler add to the traced heap: 4.4 MB (3.14) and 6.3 MB (3.13) peak on the same inputs,
still under 8 MB. Whole-process RSS, which includes the interpreter, is 11 to 12 MiB; it is not what
the organisers measure.

## Input and output

- Input: EuRoC `imu0/data.csv` format (`timestamp [ns], w_x, w_y, w_z [rad/s], a_x, a_y, a_z [m/s^2]`).
  Header and comment lines start with `#`; blank lines are skipped. Bad, missing or NaN values are
  allowed: every data row still gets a pose.
- Output: one line `timestamp tx ty tz qx qy qz qw` per input data row, same order, never more rows,
  timestamp in seconds (the input nanoseconds with the decimal point moved, so it is exact).
- Exit code 0 on success, 2 on wrong arguments, 1 if a file cannot be read or written.

## Docker

```
docker build -t vortex .
docker run --rm -v "<folder with the csv>:/data" vortex /data/data.csv /data/estimated_trajectory.txt
```

The image (`python:3.12.7-slim-bookworm`) compiles the estimator's bytecode at build time and runs
`python -S /app/main.py`.

## Files

| File | What it is |
|---|---|
| `estimated_trajectory.txt` | Our output for the evaluation input. |
| `metadata.json` | Runtime, heap peak, peak RSS and machine of that run. |
| `src/main.py`, `src/pathfinder.py` | Entry point (stub) and estimator. |
| `src/__pycache__/` | Bytecode of `pathfinder.py` for the CPython versions listed in `MANIFEST.txt` (hash-checked, so valid after unzipping). |
| `Dockerfile`, `LICENSE`, `MANIFEST.txt` | Container, licence, sha256 of every file. |

## Method (short)

The estimator never sees ground truth. It calibrates itself on the longest still period in the first
60 s (gyro bias, gravity, tilt), then runs an error-state Kalman filter (15 states) whose only
corrections come from the IMU's own physics: stillness (zero velocity and zero rotation) and a flight
envelope (bounded speed and volume). Dropouts and dead sensors (stuck or all-zero rows) are treated
as missing data with growing uncertainty; while the IMU is missing, velocity decays toward zero.

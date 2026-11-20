# Vortex: trajectory from a degraded IMU (Samsung PRISM XR Hackathon 2026, Track 3)

Python only, as the organisers require (FAQ, 17 Nov 2026).

## Run

`src/main.py` is one self-contained file: pure Python 3, standard library only, nothing to install,
no bytecode shipped. Single thread, offline, deterministic. Tested with CPython 3.12, 3.13 and 3.14.
It runs with or without `-S` and from any working directory. Every form below works:

```
python -S src/main.py                                   # searches the current folder, writes estimated_trajectory.txt there
python -S src/main.py IN                                # IN: the csv, or a sequence folder
python -S src/main.py IN OUT                            # OUT: the trajectory file, or a folder
python -S src/main.py --input IN --output OUT           # also -i IN -o OUT
```

A folder (or the current folder, with no `IN`) is searched for `imu0/data.csv`, `mav0/imu0/data.csv`,
`data.csv`, then a single `*.csv`. With no `OUT`, the output is `estimated_trajectory.txt` in the
current folder.

How the file runs: our estimator (`pathfinder.py`) sits verbatim, as source text, inside `main.py`. A short
loader at the top compiles it one function at a time, because compiling the whole 1,700-line file in one go
costs the Python parser about 7 MB of memory. Error messages give `pathfinder.py`'s line numbers.

## Budget (measured on our laptop, Intel i7-14650HX, Windows 11; `benchmark.py`, `Docs/BUDGET.md`)

The 8 MB limit is measured at algorithm / heap level (FAQ), so we measure the heap with `tracemalloc`,
started before Python compiles `main.py` (so compiling the file from source is counted).

BUDGET_TABLE

Whole-process RSS, which includes the interpreter, is not what the organisers measure.

## Input and output

- Input: EuRoC `imu0/data.csv` format (`timestamp [ns], w_x, w_y, w_z [rad/s], a_x, a_y, a_z [m/s^2]`).
  Comment lines start with `#`. A first line with letters and no number (a header without `#`) is
  skipped. Blank lines, CRLF line ends, extra columns and spaces after commas are accepted and do not
  change the output. Bad, missing or NaN values are allowed: every data row still gets a pose.
- Output: one line `timestamp tx ty tz qx qy qz qw` per input data row, same order, never more rows.
  The timestamp is the input nanoseconds with the decimal point moved (integer arithmetic, so it is
  exact); every quaternion has unit length.
- Never fails on a readable input: if the estimator raises anything, `main.py` notes it on stderr,
  writes a constant pose (identity) for every input row with the exact timestamps, and exits 0.
- Exit code 0 on success, 2 on wrong arguments, 1 if the input cannot be read or the output cannot
  be written.

## Docker

```
docker build -t vortex .
docker run --rm -v "<folder with the csv>:/data" -w /data vortex
docker run --rm -v "<folder with the csv>:/data" vortex /data/data.csv /data/estimated_trajectory.txt
```

The image (`python:3.12.7-slim-bookworm`) copies `src/main.py` and runs `python -S /app/main.py`.

## Files

| File | What it is |
|---|---|
| `estimated_trajectory.txt` | Our output for the evaluation input. |
| `metadata.json` | Source commit, build flags, input file and row count, calibration source, heap peak, time and machine of that run. |
| `src/main.py` | The whole estimator, one file. |
| `Dockerfile`, `LICENSE`, `MANIFEST.txt` | Container, licence, sha256 of every file. |

## Method (short)

The estimator never sees ground truth. It calibrates itself on the longest still period in the first
60 s (gyro bias, gravity, tilt), then runs an error-state Kalman filter (15 states) whose only
corrections come from the IMU's own physics: stillness (zero velocity and zero rotation) and a flight
envelope (bounded speed and volume). Dropouts and dead sensors (stuck or all-zero rows) are treated
as missing data with growing uncertainty; while the IMU is missing, velocity decays toward zero.

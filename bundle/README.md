# Vortex: trajectory from a degraded IMU (Samsung PRISM XR Hackathon 2026, Track 3)

Two entry points with the same output. The C core is the one that fits the 8 MB peak-RAM limit.

## C core (recommended): `src/main.cpp`

```
g++ -O2 -std=c++17 -ffp-contract=off -o vortex src/main.cpp      # Windows MinGW: add -static
./vortex <imu0/data.csv> <estimated_trajectory.txt>
```

C-style C++, standard library only, single thread, offline, deterministic, static buffers (no heap
allocation of its own). Measured on our laptop (Intel i7-14650HX), EuRoC MH_01 (36,820 rows, 184 s):

| | Peak RSS | Time per IMU row |
|---|---|---|
| Linux (Ubuntu 24.04, g++ 13.3) | 2.7 MB | 4.1 us (input on a slow WSL mount) |
| Windows 11 (MinGW g++ 13.2, `-static`) | 4.8 MB | 1.4 us |

Peak RSS does not grow with the flight length (2.4 MB on Linux for a 15-minute file).

## Python: `src/main.py`

```
python -S src/main.py <imu0/data.csv> <estimated_trajectory.txt>
```

Pure Python 3, standard library only (`sys`, `math`, `array`). Tested with CPython 3.12, 3.13 and
3.14. `main.py` is a stub that imports `src/pathfinder.py`, so Python loads the shipped bytecode
(`src/__pycache__`) instead of compiling the estimator, which would add about 4 MB of peak RSS. The
CPython interpreter alone already peaks above 8 MB (8.4 to 9.7 MB before any work), so this entry
point peaks at about 10 to 12 MB.

**Same output.** On Linux the two entry points give bit-identical poses on all our test inputs (clean
EuRoC MH_01 to MH_05 and 60 degraded copies). On Windows they give identical output files; the full
precision poses differ by at most 6e-13 m, from the two C maths libraries.

## Input and output

- Input: EuRoC `imu0/data.csv` format (`timestamp [ns], w_x, w_y, w_z [rad/s], a_x, a_y, a_z [m/s^2]`).
  Header and comment lines start with `#`; blank lines are skipped. Bad, missing or NaN values are
  allowed: every data row still gets a pose.
- Output: one line `timestamp tx ty tz qx qy qz qw` per input data row, same order, timestamp in
  seconds (the input nanoseconds with the decimal point moved, so it is exact).
- Exit code 0 on success, 2 on wrong arguments, 1 if a file cannot be read or written.

## Docker

```
docker build -t vortex .
docker run --rm -v "<folder with the csv>:/data" vortex /data/data.csv /data/estimated_trajectory.txt
```

The image builds the C core with Debian bookworm's g++ (12.2.0 when we built it) and runs it; the
Python entry point (CPython 3.12.7) is in the image too (see the Dockerfile). Built from this folder with
Docker Desktop 29.6.2: both entry points gave the same output files as above on all our test inputs, and
the C core peaked at 2.7 MB RSS inside the container on MH_01.

## Files

| File | What it is |
|---|---|
| `estimated_trajectory.txt` | Our output for the evaluation input. |
| `metadata.json` | Runtime, peak memory and machine of that run. |
| `src/main.cpp` | C core. |
| `src/main.py`, `src/pathfinder.py` | Python entry point (stub) and estimator. |
| `src/__pycache__/` | Bytecode of `pathfinder.py` for CPython 3.12, 3.13, 3.14 (hash-checked, so valid after unzipping). |
| `Dockerfile`, `LICENSE`, `MANIFEST.txt` | Container, licence, sha256 of every file. |

## Method (short)

The estimator never sees ground truth. It calibrates itself on the longest still period in the first
60 s (gyro bias, gravity, tilt), then runs an error-state Kalman filter (15 states) whose only
corrections come from the IMU's own physics: stillness (zero velocity and zero rotation) and a flight
envelope (bounded speed and volume). Dropouts and dead sensors (stuck or all-zero rows) are treated
as missing data with growing uncertainty; while the IMU is missing, velocity decays toward zero.

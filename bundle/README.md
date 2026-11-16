# Vortex: trajectory from a degraded IMU (Samsung PRISM XR Hackathon 2026, Track 3)

## Run

```
python -S main.py <imu0/data.csv> <estimated_trajectory.txt>
```

- Input: EuRoC `imu0/data.csv` format (`timestamp [ns], w_x, w_y, w_z [rad/s], a_x, a_y, a_z [m/s^2]`).
  Header and comment lines start with `#`; blank lines are skipped.
- Output: one line `timestamp tx ty tz qx qy qz qw` per input data row, same order, timestamp in seconds.
- Pure Python 3, standard library only (`sys`, `math`, `array`), single thread, offline, deterministic.
  Tested with CPython 3.12, 3.13 and 3.14. Nothing to install.
- Exit code 0 on success, 2 on wrong arguments, 1 if a file cannot be read or written.

With Docker (same program, Python 3.12):

```
docker build -t vortex .
docker run --rm -v "<folder with the csv>:/data" vortex /data/data.csv /data/estimated_trajectory.txt
```

## Files

| File | What it is |
|---|---|
| `main.py` | Entry point. A stub that imports `pathfinder.py` and runs it. |
| `pathfinder.py` | The estimator. `python -S pathfinder.py IN OUT` gives the same output. |
| `__pycache__/pathfinder.cpython-3XX.pyc` | Compiled bytecode of `pathfinder.py` for the listed Python versions. |
| `Dockerfile` | Container with the same program. |
| `MANIFEST.txt` | sha256 of every file and the source commit. |

**Why a stub.** Python compiles a script named on the command line every time it runs, and compiling
the estimator raises peak memory by about 4.8 MB. A module that is imported is loaded from its
bytecode in `__pycache__` instead, which costs about 0.2 MB. The bytecode files are hash-checked
against `pathfinder.py`, so they stay valid after unzipping; on a Python version without a matching
file, Python compiles `pathfinder.py` as usual. The output is identical either way.

## Method (short)

The estimator never sees ground truth. It calibrates itself on the longest still period in the first
60 s (gyro bias, gravity, tilt), then runs an error-state Kalman filter (15 states) whose only
corrections come from the IMU's own physics: stillness (zero velocity and zero rotation) and a flight
envelope (bounded speed and volume). Dropouts and dead sensors (stuck or all-zero rows) are treated
as missing data with growing uncertainty; while the IMU is missing, velocity decays toward zero.

"""Vortex, Samsung PRISM XR Hackathon 2026, Track 3: trajectory from a degraded IMU.

    python -S main.py <imu0/data.csv> <estimated_trajectory.txt>

The estimator is pathfinder.py (pure Python, standard library only); this file only imports it.
Python compiles a script named on the command line on every run, but loads an imported module from
its compiled bytecode in __pycache__ when a matching one is there. Compiling the estimator costs
about 4.8 MB of peak RSS, loading its bytecode about 0.2 MB (Docs/TRACK3_PLAN.md, step 9a). Without
matching bytecode Python compiles pathfinder.py as before; the output is the same either way.
"""
import sys

if __name__ == "__main__":
    # The script's own folder, also under -I (isolated mode leaves it off sys.path).
    _cut = max(__file__.rfind("/"), __file__.rfind("\\")) + 1
    sys.path.insert(0, __file__[:_cut] or ".")
    import pathfinder
    sys.exit(pathfinder.main(sys.argv))

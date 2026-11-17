"""Baseline: a trajectory that never moves (origin, identity attitude, one pose per row).

Runs the estimator's own I/O path (pathfinder.py) with integrate=False, so the output passes the same contract check. Any
estimator should beat this on EuRoC: its APE is the spread of the flight around its centroid.
Usage: python -S tools/baseline_still.py IMU.csv out.txt   (or tools/eval_euroc.py --main tools/baseline_still.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pathfinder as main  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.stderr.write(__doc__)
        sys.exit(2)
    main.run(sys.argv[1], sys.argv[2], integrate=False)

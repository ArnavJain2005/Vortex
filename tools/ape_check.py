"""Independent translational APE check for two TUM-format pose files.

Usage: python tools/ape_check.py --gt SEQUENCE_DIR|GROUND_TRUTH.csv|GT.txt --est ESTIMATE.txt

TUM-format files have rows ``timestamp tx ty tz qx qy qz qw`` (seconds,
metres). EuRoC ``mav0/state_groundtruth_estimate0/data.csv`` and TUM-VI
``mav0/mocap0/data.csv`` have nanosecond timestamps, position in fields 1–3,
and quaternion w,x,y,z in fields 4–7; any subsequent fields are ignored.
Quaternions are checked for validity but do not enter translational APE.
The default is evo_ape's nearest-timestamp association with a 0.01 s inclusive
maximum difference and zero offset, then an SE(3) fit of the estimate to truth.
No scale is fitted and no estimator or project scoring code is imported.

Definitions and default: https://github.com/MichaelGrupp/evo/wiki/Metrics
and https://github.com/MichaelGrupp/evo/wiki/evo_traj#temporal-alignment
The tie rule and shorter-first matching were checked against evo/core/sync.py;
the rotation is independently implemented with Horn's quaternion eigenproblem.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
import math
from pathlib import Path

Point = tuple[float, float, float]
Pose = tuple[float, Point]


def read_poses(path: str | Path) -> list[Pose]:
    poses: list[Pose] = []
    path = Path(path)
    if path.is_dir():
        path = ground_truth_path(path)
    csv = path.suffix.lower() == ".csv"
    with open(path, "r", encoding="utf-8-sig") as source:
        for number, line in enumerate(source, 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            fields = line.split(",") if csv else line.split()
            if (csv and len(fields) < 8) or (not csv and len(fields) != 8):
                raise ValueError(f"{path}:{number}: expected {'at least ' if csv else ''}8 numeric fields")
            try:
                values = [float(field) for field in fields[:8]]
                timestamp = int(fields[0]) / 1_000_000_000 if csv else values[0]
            except ValueError as exc:
                raise ValueError(f"{path}:{number}: invalid number") from exc
            # Match score.py's input cleaning: discard invalid rows, stable-sort
            # timestamps, and keep the first row of each duplicate timestamp.
            if not all(math.isfinite(v) for v in values) or not math.isfinite(timestamp):
                continue
            quaternion = values[4:8]  # CSV: w,x,y,z; TUM: x,y,z,w
            if math.fsum(q * q for q in quaternion) == 0:
                continue
            poses.append((timestamp, (values[1], values[2], values[3])))
    poses.sort(key=lambda pose: pose[0])
    poses = [pose for i, pose in enumerate(poses) if i == 0 or pose[0] > poses[i - 1][0]]
    if not poses:
        raise ValueError(f"{path}: no poses")
    return poses


def ground_truth_path(sequence: Path) -> Path:
    """Resolve a sequence folder or its mav0 folder without loading IMU data."""
    for base in (sequence / "mav0", sequence):
        for name in ("state_groundtruth_estimate0", "mocap0"):
            candidate = base / name / "data.csv"
            if candidate.is_file():
                return candidate
    raise FileNotFoundError(f"no EuRoC or TUM-VI ground-truth CSV under {sequence}")


def _nearest_pairs(short: list[Pose], long: list[Pose], max_diff: float) -> list[tuple[int, int]]:
    stamps = [pose[0] for pose in long]
    sorted_stamps = all(a <= b for a, b in zip(stamps, stamps[1:]))
    pairs = []
    for i, (timestamp, _) in enumerate(short):
        if sorted_stamps:
            upper = bisect_right(stamps, timestamp)
            candidates = [j for j in (upper - 1, upper) if 0 <= j < len(long)]
            # evo breaks equidistant ties toward the lower timestamp.
            chosen = min(candidates, key=lambda j: (abs(stamps[j] - timestamp), j))
        else:
            # evo uses a linear argmin if the longer trajectory is unsorted.
            chosen = min(range(len(long)), key=lambda j: abs(stamps[j] - timestamp))
        if abs(stamps[chosen] - timestamp) <= max_diff:
            pairs.append((i, chosen))
    return pairs


def associate(truth: list[Pose], estimate: list[Pose], max_diff: float = 0.01) -> list[tuple[Point, Point]]:
    if not math.isfinite(max_diff) or max_diff < 0:
        raise ValueError("max_diff must be finite and non-negative")
    # evo starts with the shorter trajectory. On equal lengths, its second
    # argument (the estimate) is the shorter-side iteration order.
    if len(estimate) <= len(truth):
        indices = _nearest_pairs(estimate, truth, max_diff)
        matches = [(truth[j][1], estimate[i][1]) for i, j in indices]
    else:
        indices = _nearest_pairs(truth, estimate, max_diff)
        matches = [(truth[i][1], estimate[j][1]) for i, j in indices]
    if not matches:
        raise ValueError("no timestamps matched within the specified tolerance")
    return matches


def _largest_eigenvector_symmetric_4(matrix: list[list[float]]) -> tuple[float, float, float, float]:
    """Jacobi rotations for a real symmetric 4x4 matrix; no external algebra."""
    a = [row[:] for row in matrix]
    eigenvectors = [[float(i == j) for j in range(4)] for i in range(4)]
    scale = max(1.0, *(abs(v) for row in a for v in row))
    for _ in range(100):
        p, q = max(((i, j) for i in range(4) for j in range(i + 1, 4)), key=lambda ij: abs(a[ij[0]][ij[1]]))
        apq = a[p][q]
        if abs(apq) <= 1e-15 * scale:
            break
        tau = (a[q][q] - a[p][p]) / (2.0 * apq)
        t = math.copysign(1.0, tau) / (abs(tau) + math.sqrt(1.0 + tau * tau))
        c = 1.0 / math.sqrt(1.0 + t * t)
        s = t * c
        a[p][p] -= t * apq
        a[q][q] += t * apq
        a[p][q] = a[q][p] = 0.0
        for k in range(4):
            if k != p and k != q:
                akp, akq = a[k][p], a[k][q]
                a[k][p] = a[p][k] = c * akp - s * akq
                a[k][q] = a[q][k] = s * akp + c * akq
            vkp, vkq = eigenvectors[k][p], eigenvectors[k][q]
            eigenvectors[k][p] = c * vkp - s * vkq
            eigenvectors[k][q] = s * vkp + c * vkq
    index = max(range(4), key=lambda i: a[i][i])
    v = tuple(eigenvectors[i][index] for i in range(4))
    norm = math.sqrt(sum(x * x for x in v))
    return tuple(x / norm for x in v)  # type: ignore[return-value]


def _rotate(q: tuple[float, float, float, float], point: Point) -> Point:
    w, x, y, z = q
    px, py, pz = point
    return (
        (1 - 2 * (y * y + z * z)) * px + 2 * (x * y - w * z) * py + 2 * (x * z + w * y) * pz,
        2 * (x * y + w * z) * px + (1 - 2 * (x * x + z * z)) * py + 2 * (y * z - w * x) * pz,
        2 * (x * z - w * y) * px + 2 * (y * z + w * x) * py + (1 - 2 * (x * x + y * y)) * pz,
    )


def ape(matches: list[tuple[Point, Point]]) -> dict[str, float | int]:
    """Fit R, t in truth ~= R * estimate + t; return translational errors."""
    n = len(matches)
    truth_mean = tuple(math.fsum(t[k] for t, _ in matches) / n for k in range(3))
    est_mean = tuple(math.fsum(e[k] for _, e in matches) / n for k in range(3))
    # Cross-dispersion S = sum((estimate - mean) (truth - mean)^T).
    s = [[math.fsum((e[i] - est_mean[i]) * (t[j] - truth_mean[j]) for t, e in matches)
          for j in range(3)] for i in range(3)]
    xx, xy, xz = s[0]
    yx, yy, yz = s[1]
    zx, zy, zz = s[2]
    horn = [
        [xx + yy + zz, yz - zy, zx - xz, xy - yx],
        [yz - zy, xx - yy - zz, xy + yx, zx + xz],
        [zx - xz, xy + yx, -xx + yy - zz, yz + zy],
        [xy - yx, zx + xz, yz + zy, -xx - yy + zz],
    ]
    rotation = _largest_eigenvector_symmetric_4(horn)
    rotated_mean = _rotate(rotation, est_mean)
    translation = tuple(truth_mean[i] - rotated_mean[i] for i in range(3))
    errors = []
    for truth, estimate in matches:
        aligned = _rotate(rotation, estimate)
        errors.append(math.dist(truth, tuple(aligned[k] + translation[k] for k in range(3))))
    return {
        "rmse": math.sqrt(math.fsum(e * e for e in errors) / n),
        "mean": math.fsum(errors) / n,
        "max": max(errors),
        "matched": n,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ground_truth", nargs="?", help="ground-truth path (legacy positional form)")
    parser.add_argument("estimate", nargs="?", help="estimated poses (legacy positional form)")
    parser.add_argument("--gt", help="EuRoC/TUM-VI sequence folder, ground-truth CSV or TUM pose file")
    parser.add_argument("--est", help="TUM-format estimated trajectory")
    parser.add_argument("--max-diff", type=float, default=0.01, help="association tolerance in seconds (evo default: 0.01)")
    arguments = parser.parse_args()
    gt, est = arguments.gt or arguments.ground_truth, arguments.est or arguments.estimate
    if not gt or not est:
        parser.error("provide --gt and --est (or both positional paths)")
    try:
        result = ape(associate(read_poses(gt), read_poses(est), arguments.max_diff))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"ATE RMSE m: {result['rmse']:.12g}")
    print(f"ATE mean m: {result['mean']:.12g}")
    print(f"ATE max m: {result['max']:.12g}")
    print(f"Matched poses: {result['matched']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

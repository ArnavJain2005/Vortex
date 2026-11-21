"""Check estimated_trajectory.txt against the Track 3 output contract. Stdlib only.

Contract (organisers' slides, plus our reading of them):
  - exactly one pose line per input data row (row rule: vortex/rowspec.py), in the same order;
  - each line: `timestamp tx ty tz qx qy qz qw`, 8 space-separated fields, no header or comments;
  - timestamp in seconds equal to the input ns timestamp / 1e9 (checked exactly as decimals,
    tolerance ts_tol_s, default 0); rows whose input timestamp is not an integer accept any finite value;
  - every value finite (no nan / inf);
  - quaternion unit norm within quat_tol.
'\\r\\n' line ends are accepted (evo reads them) and reported as a warning.
Output timestamps that do not increase are a warning, not an error: the contract mirrors the input
row for row, so an input with a repeated or swapped timestamp gives the same in the output. The
warning makes it visible, because scorers sort and drop such rows (vortex/scoring.py does).

CLI: python -m vortex.check_output IMU.csv estimated_trajectory.txt   (exit 0 = pass, 1 = fail)
"""

from __future__ import annotations

import math
import sys
from decimal import Decimal, InvalidOperation

from .rowspec import data_lines, seconds_text


def _expected_timestamps(imu_path):
    with open(imu_path, "rb") as f:
        return [seconds_text(line.split(b",", 1)[0]) for line in data_lines(f)]


def check(imu_path, out_path, ts_tol_s: float = 0.0, quat_tol: float = 1e-6, max_errors: int = 20) -> dict:
    expected = _expected_timestamps(imu_path)
    with open(out_path, "rb") as f:
        data = f.read()
    warnings = []
    if b"\r\n" in data:
        warnings.append("CRLF line ends")
    if data and not data.endswith(b"\n"):
        warnings.append("no newline at end of file")
    lines = data.decode("ascii", "replace").splitlines()
    errors, counts = [], {}

    def err(kind, msg):
        counts[kind] = counts.get(kind, 0) + 1
        if len(errors) < max_errors:
            errors.append(msg)

    poses = []
    for no, line in enumerate(lines, 1):
        s = line.strip()
        if not s:
            err("blank", "line %d: blank line" % no)
        elif s.startswith("#"):
            err("header", "line %d: header or comment line not allowed" % no)
        else:
            poses.append((no, line))
    if len(poses) != len(expected):
        err("count", "row count: %d input data rows, %d output pose lines" % (len(expected), len(poses)))

    tol = Decimal(repr(ts_tol_s))
    prev_t = None
    n_repeat = n_back = 0
    for i, (no, line) in enumerate(poses):
        if "\t" in line:
            err("separator", "line %d: tab separator" % no)
        fields = line.split()
        if len(fields) != 8:
            err("fields", "line %d: expected 8 fields, got %d" % (no, len(fields)))
            continue
        try:
            vals = [float(x) for x in fields]
        except ValueError:
            err("parse", "line %d: unparseable number" % no)
            continue
        if not all(math.isfinite(v) for v in vals):
            err("finite", "line %d: value not finite" % no)
            continue
        try:
            t_dec = Decimal(fields[0])
        except InvalidOperation:
            t_dec = None
        if t_dec is not None and prev_t is not None:
            if t_dec == prev_t:
                n_repeat += 1
            elif t_dec < prev_t:
                n_back += 1
        if t_dec is not None:
            prev_t = t_dec
        if i < len(expected) and expected[i] is not None:
            try:
                diff = abs(Decimal(fields[0]) - Decimal(expected[i]))
            except InvalidOperation:
                diff = None
            if diff is None or diff > tol:
                err("timestamp", "line %d: timestamp %s, input row %d expects %s"
                    % (no, fields[0], i + 1, expected[i]))
        n = math.sqrt(sum(v * v for v in vals[4:8]))
        if abs(n - 1.0) > quat_tol:
            err("unit", "line %d: quaternion not unit (norm %.9f)" % (no, n))

    if n_repeat:
        warnings.append("%d output timestamps repeat the previous one" % n_repeat)
    if n_back:
        warnings.append("%d output timestamps go backwards" % n_back)
    return {"ok": not counts, "input_rows": len(expected), "output_rows": len(poses),
            "errors": errors, "error_counts": counts, "warnings": warnings}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__)
        return 2
    r = check(argv[0], argv[1])
    status = "PASS" if r["ok"] else "FAIL"
    print("%s: %d input rows, %d output rows" % (status, r["input_rows"], r["output_rows"]))
    for w in r["warnings"]:
        print("  warning:", w)
    for kind, c in sorted(r["error_counts"].items()):
        print("  %s: %d" % (kind, c))
    for e in r["errors"]:
        print("  " + e)
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

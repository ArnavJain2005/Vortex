"""The input-row and timestamp rules shared by the loader, the output checker and main.py. Stdlib only.

A DATA ROW is any line that is not empty or whitespace-only and does not start with '#'. Each data row
gets exactly one output pose, in file order, whatever its values (NaN, empty, short, duplicated or out
of order). Blank lines are assumed not to be rows (pandas read_csv skips them by default); how the
organisers count rows is not confirmed.

Output timestamps are the input ns timestamp with the decimal point moved 9 digits left, done on the
text so it is exact (a double holds only ~16 significant digits; EuRoC timestamps have 19).
"""

from __future__ import annotations


def seconds_text(field) -> str | None:
    """'1403636579758555392' -> '1403636579.758555392'; '5' -> '0.000000005'.

    Returns None if the field is not a plain non-negative integer.
    """
    s = field.decode("ascii", "replace") if isinstance(field, (bytes, bytearray)) else field
    s = s.strip()
    if not s or not (s.isascii() and s.isdigit()):
        return None
    if len(s) <= 9:
        return "0." + s.rjust(9, "0")
    return s[:-9] + "." + s[-9:]


def is_data_line(line) -> bool:
    s = line.strip()
    if isinstance(s, (bytes, bytearray)):
        return bool(s) and s[:1] != b"#"
    return bool(s) and not s.startswith("#")

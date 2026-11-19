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
    return (s[:-9].lstrip("0") or "0") + "." + s[-9:]   # = str(ns // 10**9) + "." + 9-digit remainder


def is_text_header(line) -> bool:
    """A header written without '#' (e.g. `timestamp,w_x,...`): it has a letter and no comma field is a
    number. Only the FIRST data-like line of a file can be one, and then it is not a row (data_lines)."""
    s = line.decode("utf-8", "replace") if isinstance(line, (bytes, bytearray)) else line
    s = s.lstrip("﻿")
    if s.upper() == s.lower():
        return False
    for x in s.split(","):
        try:
            float(x)
            return False
        except ValueError:
            pass
    return True


def data_lines(lines):
    """The data rows of an iterable of lines: is_data_line, minus a first-line header without '#'."""
    first = True
    for line in lines:
        if not is_data_line(line):
            continue
        if first:
            first = False
            if is_text_header(line):
                continue
        yield line


BOM = b"\xef\xbb\xbf"


def is_data_line(line) -> bool:
    """Bytes or str. A UTF-8 byte-order mark at the start of a line is ignored."""
    s = line.strip()
    if isinstance(s, (bytes, bytearray)):
        if s[:3] == BOM:
            s = s[3:].strip()
        return bool(s) and s[:1] != b"#"
    s = s.lstrip("\ufeff").strip()
    return bool(s) and not s.startswith("#")

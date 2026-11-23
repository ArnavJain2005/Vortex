"""Render the README's result and budget cards from Docs/NUMBERS.md.

Every number drawn comes from a key in Docs/NUMBERS.md; nothing is typed by hand.

    python tools/readme_figures.py            # writes assets/readme-results.svg, assets/readme-budget.svg
    python tools/readme_figures.py --check    # exit 1 if the committed SVGs are out of date
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUMBERS = os.path.join(ROOT, "Docs", "NUMBERS.md")
OUT_RESULTS = os.path.join(ROOT, "assets", "readme-results.svg")
OUT_BUDGET = os.path.join(ROOT, "assets", "readme-budget.svg")

BG = "#0a0e2e"
PANEL = "#121a45"
GRID = "#2a3570"
TEXT = "#f3f5ff"
MUTED = "#9aa6d6"
CYAN = "#5ec8f2"
FLOOR = "#4b5694"
GOOD = "#7ee0b5"
TIE = "#f5c26b"
VIOLET = "#c38bf5"
SALMON = "#f2877e"
FONT = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"


def load_numbers(path=NUMBERS):
    vals = {}
    row = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|")
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = row.match(line)
            if m:
                vals[m.group(1)] = m.group(2)
    return vals


def num(vals, key):
    if key not in vals:
        raise KeyError("Docs/NUMBERS.md has no key %r" % key)
    return float(vals[key].replace(",", ""))


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=14, fill=TEXT, weight=400, anchor="start", extra=""):
    return ('<text x="%.1f" y="%.1f" font-family="%s" font-size="%s" font-weight="%d" '
            'fill="%s" text-anchor="%s"%s>%s</text>' % (x, y, FONT, size, weight, fill, anchor, extra, esc(s)))


def pct_text(p):
    return ("%.1f%%" % abs(p)) + (" lower" if p < 0 else " higher")


# (prefix in NUMBERS.md, dataset line, metric line)
RESULT_ROWS = [
    ("heldout", "6 held-out EuRoC sequences · 36 copies", "Full-trajectory APE"),
    ("heldout_gap", "6 held-out EuRoC sequences · seeds 4–6", "Error inside dropout gaps"),
    ("heldout_blind", "6 held-out EuRoC sequences · seeds 4–6", "Error in the blind 5 s"),
    ("heldout79", "Same 6 sequences · repeat trials (seeds 7–9)", "Full-trajectory APE"),
    ("heldout_rpe1s", "6 held-out EuRoC sequences · seeds 4–6", "1 s RPE (diagnostic, not scored)"),
    ("tumvi_room34", "TUM-VI held-out rooms 3–4 · 12 copies", "Full-trajectory APE · hand-held"),
    ("clean", "8 clean EuRoC sequences (incl. tuning)", "Full-trajectory APE · no degradation"),
]

TIE_PCT = 1.0  # |difference| below this is drawn and labelled "level", not a win


def result_keys(prefix):
    if prefix in ("heldout", "heldout79", "clean", "tumvi_room34", "tumvi"):
        return prefix + "_ape_m", prefix + "_ape_floor_m", prefix + "_ape_vs_floor_pct"
    return prefix + "_m", prefix + "_floor_m", prefix + "_vs_floor_pct"


def render_results(vals):
    W, top, rowh = 960, 128, 78
    H = top + rowh * len(RESULT_ROWS) + 70
    lx, bx, bw = 40, 330, 380
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img" '
           'aria-label="Vortex error versus a constant-pose baseline">' % (W, H, W, H),
           '<rect width="%d" height="%d" rx="20" fill="%s"/>' % (W, H, BG),
           text(lx, 52, "Vortex vs. a constant-pose baseline", 24, TEXT, 700),
           text(lx, 80, "Translational error (m) after the same per-run SE(3) alignment for both. Lower is better. "
                        "Bars: baseline = 100%.", 14, MUTED),
           '<rect x="%d" y="96" width="14" height="14" rx="3" fill="%s"/>' % (lx, CYAN),
           text(lx + 22, 108, "Vortex", 13, TEXT, 600),
           '<rect x="%d" y="96" width="14" height="14" rx="3" fill="%s"/>' % (lx + 100, FLOOR),
           text(lx + 122, 108, "Constant-pose baseline", 13, TEXT, 600)]
    for i, (prefix, ds, metric) in enumerate(RESULT_ROWS):
        kv, kf, kp = result_keys(prefix)
        v, f = num(vals, kv), num(vals, kf)
        p = num(vals, kp) if kp in vals else round(100.0 * (v - f) / f, 1)
        y = top + i * rowh
        out.append('<rect x="20" y="%d" width="%d" height="%d" rx="12" fill="%s"/>'
                   % (y, W - 40, rowh - 10, PANEL if i % 2 == 0 else BG))
        out.append(text(lx, y + 28, ds, 13, MUTED, 500))
        out.append(text(lx, y + 50, metric, 16, TEXT, 600))
        fw = bw
        vw = bw * min(v / f, 1.15)
        out.append('<rect x="%d" y="%d" width="%.1f" height="16" rx="4" fill="%s"/>' % (bx, y + 14, fw, FLOOR))
        out.append(text(bx + fw + 8, y + 27, "%.3f m" % f, 12, MUTED))
        out.append('<rect x="%d" y="%d" width="%.1f" height="16" rx="4" fill="%s"/>' % (bx, y + 38, vw, CYAN))
        out.append(text(bx + vw + 8, y + 51, "%.3f m" % v, 12, TEXT, 600))
        tie = abs(p) < TIE_PCT
        col = TIE if tie else (GOOD if p < 0 else SALMON)
        label = "level" if tie else ("−%.1f%%" % abs(p) if p < 0 else "+%.1f%%" % p)
        out.append('<rect x="%d" y="%d" width="104" height="34" rx="17" fill="none" stroke="%s" stroke-width="2"/>'
                   % (W - 150, y + 17, col))
        out.append(text(W - 98, y + 40, label, 17, col, 700, "middle"))
    out.append(text(lx, H - 44, "Held-out EuRoC = MH_03–05, V1_01–03, both column readings; copies = seeds × readings of the "
                                "same flights. Faults: organisers' degrade_imu.py.", 12, MUTED))
    out.append(text(lx, H - 24, "Source: Docs/NUMBERS.md, shipped v1.0 build.", 12, MUTED))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def gauge(x, y, w, label, sub, used, limit, unit, fmt, lim_fmt, color, note):
    frac = min(used / limit, 1.0)
    s = [text(x, y, label, 16, TEXT, 600), text(x, y + 20, sub, 12, MUTED),
         '<rect x="%d" y="%d" width="%d" height="22" rx="11" fill="%s"/>' % (x, y + 34, w, GRID),
         '<rect x="%d" y="%d" width="%.1f" height="22" rx="11" fill="%s"/>' % (x, y + 34, w * frac, color),
         text(x, y + 80, fmt.format(used) + " " + unit, 22, color, 700),
         text(x + w, y + 80, "limit " + lim_fmt.format(limit) + " " + unit, 13, MUTED, 500, "end"),
         text(x, y + 102, note, 12, MUTED)]
    return s


def render_budget(vals):
    W, H = 960, 330
    docker = num(vals, "budget_wall_ms_per_imu_s_ms")
    win = num(vals, "budget_win_wall_ms_per_imu_s_ms")
    heap314 = num(vals, "budget_heap_whole_run_kb")
    heap313 = num(vals, "budget313_heap_whole_run_kb")
    tests = int(num(vals, "pytest_passed_n"))
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img" '
           'aria-label="Vortex runtime and memory against the challenge limits">' % (W, H, W, H),
           '<rect width="%d" height="%d" rx="20" fill="%s"/>' % (W, H, BG),
           text(40, 52, "Inside the challenge budget", 24, TEXT, 700),
           text(40, 80, "Shipped single-file src/main.py on an official degraded copy (MH_03_medium_b_s1, {:,} rows).".format(
                int(num(vals, "budget_rows_n"))),
                14, MUTED)]
    out += gauge(40, 120, 410, "Wall time per IMU-second", "Whole process from source, Linux Docker, Python 3.12.7, 15-run median",
                 docker, 20.0, "ms", "{:.2f}", "{:.0f}", CYAN, "Windows 11, Python 3.14.7: %.2f ms wall time" % win)
    out += gauge(510, 120, 410, "Peak heap, whole run", "tracemalloc from source, Windows 11, Python 3.14.7",
                 heap314, 8192.0, "KB", "{:,.0f}", "{:,.0f}", VIOLET, "Windows 11, Python 3.13.5: {:,.0f} KB".format(heap313))
    out.append(text(40, H - 40, "Single thread · standard library only · %d tests passed (Windows 11, Python 3.14.7)" % tests,
                    14, GOOD, 600))
    out.append(text(W - 40, H - 40, "Source: Docs/NUMBERS.md, Docs/BUDGET.md", 12, MUTED, 400, "end"))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main(argv):
    vals = load_numbers()
    outputs = {OUT_RESULTS: render_results(vals), OUT_BUDGET: render_budget(vals)}
    if "--check" in argv:
        stale = [p for p, s in outputs.items()
                 if not os.path.exists(p) or open(p, encoding="utf-8").read() != s]
        for p in stale:
            print("out of date: " + os.path.relpath(p, ROOT))
        return 1 if stale else 0
    for p, s in outputs.items():
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(s)
        print("wrote " + os.path.relpath(p, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Docs/NUMBERS.md: every number the deck, video script and README may quote, generated from committed files.

Flat table `key | value | source tag | date`. ChatGPT's deck and script use `[[N:key]]` placeholders keyed to
it, so keys are stable: when the shipped build changes, point SOURCES at the new tags and re-run; the keys
stay, the values and source tags change. Never edit Docs/NUMBERS.md by hand.

Sources (tags are files written by tools/eval_euroc.py, benchmark.py, tools/tumvi_table.py):
    Docs/results/<tag>.json, Docs/tumvi/<tag>.json, Docs/budget/<tag>.json, Docs/numbers/pytest.json

    python tools/make_numbers.py            # writes Docs/NUMBERS.md and Docs/numbers/numbers.json
    python tools/make_numbers.py --check    # exit 1 if Docs/NUMBERS.md is not what the sources give
    python tools/make_numbers.py --pytest   # first runs the full pytest and records its summary line

Key suffixes give the unit: _m metres, _pct per cent, _kb kilobytes (1024 B), _us microseconds,
_ms milliseconds, _n a count. A key ending in _vs_floor_pct is 100 (est / floor - 1): negative = better
than the never-moving floor. "Sequences beat floor" pools every copy of a sequence (both readings, all
seeds; for a per-reading key only that reading) and compares the mean APE of the estimate with the mean
APE of the floor on the same copies.
"""
import datetime
import json
import os
import platform
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "Docs")
OUT_MD = os.path.join(DOCS, "NUMBERS.md")
OUT_JSON = os.path.join(DOCS, "numbers", "numbers.json")
PYTEST_JSON = os.path.join(DOCS, "numbers", "pytest.json")

# ---- which committed run is which. Change these (never the keys) when the shipped build changes. ----
SHIP = "shipped v1.0 build (the single src/main.py of tag v1.0; Step 7 + L2 + L3)"
SOURCES = {
    # Every estimate below is the SHIPPED single file (dist/stage/src/main.py at tag v1.0, sha256 feb222ea...0811)
    # run by tools/eval_euroc.py --main on 22 Nov 2026, one run per set; every floor was re-run the same day.
    # held-out official copies: MH_03..05 + V1_01..03, readings a and b
    "heldout": ("results/v10-H46", "results/v10floor-H46", "seeds 4-6, " + SHIP),
    "heldout79": ("results/v10-H79", "results/v10floor-H79", "seeds 7-9, " + SHIP),
    # rule H' held-out set (Step L3). Written after rule H failed: weaker evidence than seeds 4-6 / 7-9.
    "heldout_hp": ("results/v10-HP", "results/v10floor-HP",
                   "seeds 22-24, rule H' held-out set, WRITTEN AFTER RULE H FAILED; WEAKER EVIDENCE; " + SHIP),
    # clean sequences MH_01..05 + V1_01..03
    "clean": ("results/v10-clean", "results/v10floor-clean", "clean, " + SHIP),
    # TUM-VI rooms 1-4 (rooms 5, 6 are kept for the final table): official seeds 1-3, rule H' seeds 22-24, clean
    "tumvi": ("tumvi/v10-tumvi", "tumvi/v10floor-tumvi", "TUM-VI rooms 1-4 official copies seeds 1-3, " + SHIP),
    "tumvi_hp": ("tumvi/v10-tumvi-HP", "tumvi/v10floor-tumvi-HP",
                 "TUM-VI rooms 3-4 seeds 22-24, rule H' held-out set, WRITTEN AFTER RULE H FAILED; WEAKER EVIDENCE; "
                 + SHIP),
    "tumvi_clean": ("tumvi/v10-tumvi-clean", "tumvi/v10floor-tumvi-clean", "TUM-VI rooms 1-4 clean, " + SHIP),
    "tumvi_calib": "tumvi/v10-tumvi-calib",
    # budget: the shipped single file from source (benchmark.py --bundle), on the zip's own input MH_03_medium_b_s1
    # (reading b = accelerometer-first columns), Windows 11, Python 3.14 and 3.13
    "budget": "budget/v10-win-py314-mh03-b-s1",
    "budget313": "budget/v10-win-py313-mh03-b-s1",
    # wall time in Linux Docker: Antigravity's 15-run benchmark of the same file (Docs/DOCKER_BENCH.md section 5)
    "docker": "numbers/docker",
}
# The seven keys the deck and video script quote ([[N:key]]): name -> (key it repeats, what it is)
HEADLINE = [
    ("heldout_ape_reading_a", "heldout_a_ape_m", "held-out seeds 4-6, reading a, mean APE (m)"),
    ("heldout_ape_reading_b", "heldout_b_ape_m", "held-out seeds 4-6, reading b, mean APE (m)"),
    ("heldout_ape_floor", "heldout_ape_floor_m", "held-out seeds 4-6, never-moving floor, mean APE (m)"),
    ("blind_rmse_vortex", "heldout_blind_m", "held-out seeds 4-6, both readings, blind 5 s RMSE (m)"),
    ("blind_rmse_floor", "heldout_blind_floor_m", "held-out seeds 4-6, floor, blind 5 s RMSE (m)"),
]
TUMVI_TUNING = ("dataset-room1", "dataset-room2")
TUMVI_HELDOUT = ("dataset-room3", "dataset-room4")
SHORT = {"MH_01_easy": "mh01", "MH_02_easy": "mh02", "MH_03_medium": "mh03", "MH_04_difficult": "mh04",
         "MH_05_difficult": "mh05", "V1_01_easy": "v101", "V1_02_medium": "v102", "V1_03_difficult": "v103"}

# experiments judged by a pre-registered rule and shipped OFF (switch, step, one-line result; no numbers here:
# the numbers are in the step's section of Docs/TRACK3_PLAN.md)
OFF = [
    ("FF_STUCK6_ON", "Step 3", "stuck-row filter: failed its rule"),
    ("FF_SPIKE_ON", "Step 3", "spike filter: failed its rule"),
    ("INTERP_ON", "Step 3", "bridging missing rows: failed its rule"),
    ("LEARN_ON", "Step 4", "envelope learned per flight: failed its rule"),
    ("V3 rotor drag", "Step 5", "drag rule v2: NO-GO, not built"),
    ("JAM_ON", "Step 6c", "noise meter sets trust: failed its rule"),
    ("ZUPT_DEN_ON", "Step 7b", "denoised stillness: failed its rule"),
    ("RESET_ON", "Step F", "covariance reset: failed its rule"),
    ("SHRINK_ON", "Step L1", "shrinkage about the centroid: failed its rule"),
    ("BLIND_FALLBACK (rule H)", "Step L3", "blind window with a 5 s fallback: failed rule H (clean TUM-VI); "
                                           "the dead-run-only variant (rule H') ships"),
]


def shipped_on():
    """Every module-level boolean switch of pathfinder.py that is True (the shipped build's flags)."""
    import ast
    with open(os.path.join(ROOT, "pathfinder.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    return [n.targets[0].id for n in tree.body
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
            and n.targets[0].id.isupper() and isinstance(n.value, ast.Constant) and n.value.value is True]


def load(tag):
    with open(os.path.join(DOCS, tag + ".json"), encoding="utf-8") as f:
        return json.load(f)


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


class Table:
    def __init__(self):
        self.rows = []
        self.keys = set()

    def add(self, key, value, src, date, fmt="%.3f"):
        assert re.fullmatch(r"[a-z0-9_]+", key), key
        assert key not in self.keys, key
        self.keys.add(key)
        if value is None:
            text = "-"
        elif isinstance(value, str):
            text = value
        else:
            text = fmt % value
        self.rows.append((key, text, src, date))


def _pairs(est, floor):
    fl = {r["sequence"]: r for r in floor["results"] if "error" not in r}
    return [(r, fl[r["sequence"]]) for r in est["results"] if "error" not in r and r["sequence"] in fl]


def _beat(pairs):
    by = {}
    for e, f in pairs:
        by.setdefault(e["base"], []).append((e["ape_se3_rmse"], f["ape_se3_rmse"]))
    return sum(1 for v in by.values() if mean([a for a, _ in v]) < mean([b for _, b in v])), len(by)


def official_block(t, name, est_tag, floor_tag, per_seq=False, groups=None):
    est, floor = load(est_tag), load(floor_tag)
    src = "%s vs %s" % (est["tag"], floor["tag"])
    date = est["date"]
    pairs = _pairs(est, floor)
    t.add(name + "_copies_n", "%d" % len(pairs), src, date)
    t.add(name + "_contract_pass_n", "%d/%d" % (sum(1 for e, _ in pairs if e.get("contract") == "PASS"),
                                               len(est["results"])), est["tag"], date)
    sets = [("", pairs), ("_a", [p for p in pairs if p[0]["reading"] == "a"]),
            ("_b", [p for p in pairs if p[0]["reading"] == "b"])]
    for gname, pred in (groups or []):
        sets.append(("_" + gname, [p for p in pairs if pred(p[0])]))
    for sfx, ps in sets:
        if not ps:
            continue
        for metric, key in (("ape_se3_rmse", "ape"), ("gap_rmse_mean", "gap"), ("blind_rmse", "blind"),
                            ("rpe200_rmse", "rpe1s")):
            a = mean([e.get(metric) for e, _ in ps])
            b = mean([f.get(metric) for _, f in ps])
            t.add("%s%s_%s_m" % (name, sfx, key), a, src, date)
            t.add("%s%s_%s_floor_m" % (name, sfx, key), b, src, date)
            t.add("%s%s_%s_vs_floor_pct" % (name, sfx, key),
                  None if a is None or not b else 100.0 * (a / b - 1.0), src, date, "%+.1f")
        k, n = _beat(ps)
        t.add("%s%s_seqs_beat_floor_n" % (name, sfx), "%d/%d" % (k, n), src, date)
    if per_seq:
        for base in sorted({e["base"] for e, _ in pairs}):
            for rd in "ab":
                ps = [p for p in pairs if p[0]["base"] == base and p[0]["reading"] == rd]
                key = "%s_%s_%s" % (name, SHORT.get(base, base.lower()), rd)
                t.add(key + "_ape_m", mean([e["ape_se3_rmse"] for e, _ in ps]), src, date)
                t.add(key + "_ape_floor_m", mean([f["ape_se3_rmse"] for _, f in ps]), src, date)


def clean_block(t, name, est_tag, floor_tag, groups=None):
    est, floor = load(est_tag), load(floor_tag)
    src = "%s vs %s" % (est["tag"], floor["tag"])
    date = est["date"]
    pairs = _pairs(est, floor)
    sets = [("", pairs)] + [("_" + g, [p for p in pairs if pred(p[0])]) for g, pred in (groups or [])]
    for sfx, ps in sets:
        if not ps:
            continue
        t.add("%s%s_seqs_n" % (name, sfx), "%d" % len(ps), src, date)
        for metric, key in (("ate_se3_rmse", "ape"), ("rpe200_rmse", "rpe1s")):  # clean runs name APE ate_se3_rmse
            a = mean([e.get(metric) for e, _ in ps])
            b = mean([f.get(metric) for _, f in ps])
            t.add("%s%s_%s_m" % (name, sfx, key), a, src, date)
            t.add("%s%s_%s_floor_m" % (name, sfx, key), b, src, date)
            t.add("%s%s_%s_vs_floor_pct" % (name, sfx, key),
                  None if a is None or not b else 100.0 * (a / b - 1.0), src, date, "%+.1f")
        k = sum(1 for e, f in ps if e["ate_se3_rmse"] < f["ate_se3_rmse"])
        t.add("%s%s_seqs_beat_floor_n" % (name, sfx), "%d/%d" % (k, len(ps)), src, date)


def budget_block(t, name, tag):
    d = load(tag)
    src = os.path.basename(tag)
    date = d["date"]
    proc = {p["case"]: p for p in d["process"]}
    t.add(name + "_input", d["input"].split("data/")[-1] if d["input"].startswith("real") else d["input"],
          src, date, "%s")
    t.add(name + "_rows_n", "%d" % d["rows"], src, date)
    t.add(name + "_python", d["python"], src, date)
    t.add(name + "_heap_kb", d["tracemalloc_peak_kb"], src, date, "%.0f")
    t.add(name + "_heap_whole_run_kb", d["tracemalloc_process_peak_kb"], src, date, "%.0f")
    t.add(name + "_heap_no_bytecode_kb", d["tracemalloc_process_nocache_peak_kb"], src, date, "%.0f")
    p = proc["python -S main.py"]
    t.add(name + "_us_per_row_us", p["us_per_row"], src, date, "%.1f")
    t.add(name + "_cpu_ms_per_imu_s_ms", p["cpu_ms_per_imu_s"], src, date, "%.2f")
    # budget_wall_ms_per_imu_s_ms is the Linux Docker figure (docker_block); this machine's wall time is _win_
    wall = name + ("_win_wall_ms_per_imu_s_ms" if name == "budget" else "_wall_ms_per_imu_s_ms")
    t.add(wall, p.get("wall_ms_per_imu_s"), src, date, "%.2f")


def docker_block(t, tag):
    d = load(tag)
    src = "%s (%s)" % (d["source"], d["tag"])
    t.add("budget_wall_ms_per_imu_s_ms", d["wall_ms_per_imu_s"], src, d["date"], "%.2f")
    t.add("budget_docker_input", d["input"], src, d["date"], "%s")
    t.add("budget_docker_wall_range_ms", "%.2f-%.2f" % (d["range_ms_per_imu_s"][0], d["range_ms_per_imu_s"][1]),
          "%s, %d inputs" % (d["source"], d["range_inputs_n"]), d["date"], "%s")


def headline_block(t):
    have = {k: (v, s, d) for k, v, s, d in t.rows}
    for key, of, _ in HEADLINE:
        v, s, d = have[of]
        t.add(key, v, "= %s (%s)" % (of, s), d, "%s")


def build():
    t = Table()
    for name in ("heldout", "heldout79", "heldout_hp"):
        if name not in SOURCES:
            continue
        e, f, _ = SOURCES[name]
        official_block(t, name, e, f, per_seq=(name != "heldout79"))
    e, f, _ = SOURCES["clean"]
    clean_block(t, "clean", e, f)
    e, f, _ = SOURCES["tumvi"]
    official_block(t, "tumvi", e, f, groups=[("room12", lambda r: r["base"].startswith(TUMVI_TUNING)),
                                              ("room34", lambda r: r["base"].startswith(TUMVI_HELDOUT))])
    if "tumvi_hp" in SOURCES:
        e, f, _ = SOURCES["tumvi_hp"]
        official_block(t, "tumvi_hp", e, f)
    e, f, _ = SOURCES["tumvi_clean"]
    clean_block(t, "tumvi_clean", e, f, groups=[("room12", lambda r: r["sequence"].startswith(TUMVI_TUNING)),
                                                ("room34", lambda r: r["sequence"].startswith(TUMVI_HELDOUT))])
    cal = load(SOURCES["tumvi_calib"])
    src = os.path.basename(SOURCES["tumvi_calib"])
    date = load(SOURCES["tumvi_clean"][0])["date"]
    for part in ("clean", "official"):
        v = cal[part].values()
        t.add("tumvi_calib_%s_calibrated_n" % part, "%d/%d" % (sum(1 for x in v if x["calibrated"]), len(cal[part])),
              src, date)
        t.add("tumvi_calib_%s_zupt_any_n" % part, "%d/%d" % (sum(1 for x in v if x["zupt_ticks"] > 0),
                                                              len(cal[part])), src, date)
    budget_block(t, "budget", SOURCES["budget"])
    budget_block(t, "budget313", SOURCES["budget313"])
    if "docker" in SOURCES:
        docker_block(t, SOURCES["docker"])
    headline_block(t)
    if os.path.exists(PYTEST_JSON):
        with open(PYTEST_JSON, encoding="utf-8") as f:
            pt = json.load(f)
        src = "pytest %s, Python %s, commit %s" % (pt["platform"], pt["python"], pt["commit"])
        t.add("pytest_passed_n", "%d" % pt["passed"], src, pt["date"])
        t.add("pytest_failed_n", "%d" % pt["failed"], src, pt["date"])
        t.add("pytest_skipped_n", "%d" % pt["skipped"], src, pt["date"])
    t.add("experiments_off_n", "%d" % len(OFF), "make_numbers.OFF", "-")
    for sw, step, what in OFF:
        key = "off_" + re.sub(r"[^a-z0-9]+", "_", sw.lower().replace("_on", "")).strip("_")
        t.add(key, "%s (%s)" % (what, step), step, "-", "%s")
    t.add("switches_on", ", ".join(shipped_on()), "pathfinder.py", "-", "%s")
    return t


def render(t):
    lines = ["# Numbers you may quote", "",
             "Generated by `python tools/make_numbers.py` from committed result files; never edit by hand. Use",
             "`[[N:key]]` in the deck, script and README. Units by suffix: `_m` metres, `_pct` per cent, `_kb`",
             "kilobytes, `_us` microseconds, `_ms` milliseconds, `_n` a count. `_vs_floor_pct` = 100 (est / floor - 1):",
             "negative is better than standing still. Every APE is SE(3) Umeyama fitted on the run being scored.", "",
             "Sets:"]
    for name in ("heldout", "heldout79", "heldout_hp", "clean", "tumvi", "tumvi_hp", "tumvi_clean"):
        if name not in SOURCES:
            continue
        e, f, what = SOURCES[name]
        lines.append("- `%s_*`: %s (`%s` vs floor `%s`)." % (name, what, os.path.basename(e), os.path.basename(f)))
    lines += ["- `tumvi*_room12_*` are the TUM-VI tuning rooms, `tumvi*_room34_*` the held-out rooms.",
              "- `budget_*`: %s; `budget313_*`: %s. `budget_heap_whole_run_kb` is the tracemalloc peak of the "
              "whole run of the shipped single file compiled from source." % (
                  os.path.basename(SOURCES["budget"]), os.path.basename(SOURCES["budget313"]))]
    if "docker" in SOURCES:
        lines.append("- `budget_wall_ms_per_imu_s_ms`: Linux Docker wall time of the same file on the same input "
                     "(Antigravity, Docs/DOCKER_BENCH.md section 5); `budget_win_wall_ms_per_imu_s_ms`: this laptop.")
    lines.append("- Headline keys quoted by the deck and script (each repeats another key): " + "; ".join(
        "`%s` = `%s` (%s)" % (k, of, what) for k, of, what in HEADLINE) + ".")
    lines += ["", "| key | value | source tag | date |", "|---|---|---|---|"]
    for k, v, s, d in t.rows:
        lines.append("| `%s` | %s | %s | %s |" % (k, v, s, d))
    return "\n".join(lines) + "\n"


def run_pytest():
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rf", "-p", "no:cacheprovider"], cwd=ROOT,
                       capture_output=True, text=True)
    tail = [ln for ln in p.stdout.splitlines() if ln.strip()][-1]
    count = lambda w: int(m.group(1)) if (m := re.search(r"(\d+) " + w, tail)) else 0  # noqa: E731
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True).stdout.strip()
    rec = {"summary": tail.strip("= "), "passed": count("passed"), "failed": count("failed"),
           "skipped": count("skipped"), "python": platform.python_version(),
           "platform": "%s %s" % (platform.system(), platform.release()), "commit": commit,
           "date": datetime.date.today().isoformat()}
    os.makedirs(os.path.dirname(PYTEST_JSON), exist_ok=True)
    with open(PYTEST_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rec, f, indent=1)
        f.write("\n")
    for ln in p.stdout.splitlines():
        if ln.startswith("FAILED"):
            print(ln)
    print("pytest:", rec["summary"])
    return p.returncode


def main(argv):
    if "--pytest" in argv:
        run_pytest()
    t = build()
    md = render(t)
    if "--check" in argv:
        with open(OUT_MD, encoding="utf-8") as f:
            ok = f.read().replace("\r\n", "\n") == md
        print("Docs/NUMBERS.md", "matches its sources" if ok else "is STALE: run python tools/make_numbers.py")
        return 0 if ok else 1
    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump({k: {"value": v, "source": s, "date": d} for k, v, s, d in t.rows}, f, indent=1)
        f.write("\n")
    print("wrote Docs/NUMBERS.md and Docs/numbers/numbers.json (%d keys)" % len(t.rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

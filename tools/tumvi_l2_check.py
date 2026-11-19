"""Task G7a: compare two estimator builds (e.g. L2 TILT_ON off vs on) on TUM-VI tuning rooms 1 and 2.

Runs two separate worktrees/scripts via subprocess (`python -S <main.py> <imu.csv> <out.txt>`) without
editing any file, plus `tools/baseline_still.py` for the never-moving floor, on clean
`dataset-room1_512_16` and `dataset-room2_512_16` and their official copies (readings a and b,
default seeds 1..3). Strictly refuses held-out rooms 3..6, Vicon Room 2 (`V2_*`), and reserved/judging
seeds 10..18.

Usage:
    python tools/tumvi_l2_check.py --dir-off ../Vortex-tiltoff --dir-on ../Vortex-tilton
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vortex import check_output, scoring  # noqa: E402

DEFAULT_SEQS = ("dataset-room1_512_16", "dataset-room2_512_16")
DEFAULT_READINGS = ("a", "b")
DEFAULT_SEEDS = (1, 2, 3)
FORBIDDEN_PREFIXES = ("V2_", "dataset-room3", "dataset-room4", "dataset-room5", "dataset-room6")
FORBIDDEN_SEEDS = frozenset(range(10, 19))


def guard_inputs(seqs: list[str], seeds: list[int]) -> None:
    """Refuse held-out TUM-VI rooms 3..6, V2_*, and seeds 10..18."""
    bad_seqs = [s for s in seqs if s.startswith(FORBIDDEN_PREFIXES)]
    if bad_seqs:
        raise SystemExit(f"refused forbidden sequence(s): {', '.join(bad_seqs)}")
    bad_seeds = [s for s in seeds if s in FORBIDDEN_SEEDS]
    if bad_seeds:
        raise SystemExit(f"refused forbidden seed(s) in 10..18: {', '.join(str(s) for s in bad_seeds)}")


def git_short_head(worktree_dir: Path) -> str:
    try:
        p = subprocess.run(
            ["git", "-C", str(worktree_dir), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return p.stdout.strip() or "?"
    except OSError:
        return "?"


def load_pathfinder(worktree_dir: Path, mod_name: str):
    pf_path = worktree_dir / "pathfinder.py"
    spec = importlib.util.spec_from_file_location(mod_name, str(pf_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {pf_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def diagnose_cal_source(pf_mod, imu_path: Path, tmp_dir: Path) -> str:
    """Determine cal_source ('still_run', 'init_window_still', or 'fallback_zero') without mutating pf_mod."""
    lines = None
    if getattr(pf_mod, "FRONT_ON", False):
        lay = pf_mod._fe_detect(str(imu_path))
        if not lay["canonical"]:
            lines = pf_mod._fe_canonical_lines(str(imu_path), lay)
    canon = str(imu_path)
    if lines is not None:
        canon_path = tmp_dir / "canon_in.csv"
        with open(canon_path, "wb") as g:
            g.writelines(lines)
        canon = str(canon_path)
    cal = pf_mod._calibrate(canon)
    if cal is not None:
        return "still_run"
    init = pf_mod._initialise(pf_mod._init_window(canon))
    return "init_window_still" if init[8] else "fallback_zero"


def evaluate_copy(
    main_py: Path,
    pf_mod,
    imu_path: Path,
    gt_dir: Path,
    events: dict | None,
    tmp_dir: Path,
    tag: str,
) -> dict:
    est_path = tmp_dir / f"est_{tag}.txt"
    p = subprocess.run(
        [sys.executable, "-S", str(main_py), str(imu_path), str(est_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        raise RuntimeError(f"{main_py} failed on {imu_path}: {p.stderr[-400:]}")
    chk = check_output.check(str(imu_path), str(est_path))
    ref = scoring.read_ground_truth(str(gt_dir))
    est_traj, _ = scoring.read_tum(str(est_path))
    res = scoring.score(ref, est_traj, align="se3", rpe_deltas=(200,), events=events)
    gap_rmse = None
    blind_rmse = None
    if events is not None:
        ph = res["phases"]
        drops = [d for d in ph["dropouts"] if d.get("n")]
        gap_rmse = sum(d["rmse"] for d in drops) / len(drops) if drops else None
        blind_rmse = ph["blind"].get("rmse")
    cal_source = diagnose_cal_source(pf_mod, imu_path, tmp_dir) if pf_mod is not None else "-"
    return {
        "contract": "PASS" if chk["ok"] else "FAIL",
        "rows": chk["input_rows"],
        "ape": float(res["ape"]["rmse"]),
        "rpe200": float(res["rpe"]["200"]["rmse"]),
        "gap_rmse": None if gap_rmse is None else float(gap_rmse),
        "blind_rmse": None if blind_rmse is None else float(blind_rmse),
        "cal_source": cal_source,
        "raw_bytes": est_path.read_bytes(),
    }


def _mean(xs: list[float | None]) -> float | None:
    vals = [x for x in xs if x is not None]
    return sum(vals) / len(vals) if vals else None


def _counts(diffs: list[float], tol: float = 1e-12) -> dict[str, int]:
    better = sum(1 for d in diffs if d < -tol)
    worse = sum(1 for d in diffs if d > tol)
    same = len(diffs) - better - worse
    return {"better": better, "worse": worse, "same": same, "total": len(diffs)}


def compare_builds(
    dir_off: Path,
    dir_on: Path,
    tumvi_root: Path,
    official_root: Path,
    seqs: list[str],
    readings: list[str],
    seeds: list[int],
    commit_off: str | None = None,
    commit_on: str | None = None,
) -> dict:
    guard_inputs(seqs, seeds)
    c_off = commit_off or git_short_head(dir_off)
    c_on = commit_on or git_short_head(dir_on)
    pf_off = load_pathfinder(dir_off, "vortex_pf_off")
    pf_on = load_pathfinder(dir_on, "vortex_pf_on")
    main_off = dir_off / "main.py"
    main_on = dir_on / "main.py"
    still_py = dir_on / "tools" / "baseline_still.py"
    if not still_py.is_file():
        still_py = ROOT / "tools" / "baseline_still.py"

    rows = []
    with tempfile.TemporaryDirectory(prefix="vortex_g7a_") as tmp_str:
        tmp_dir = Path(tmp_str)
        for seq in seqs:
            gt_dir = tumvi_root / seq
            imu_path = gt_dir / "mav0" / "imu0" / "data.csv"
            r_off = evaluate_copy(main_off, pf_off, imu_path, gt_dir, None, tmp_dir, "off")
            r_on = evaluate_copy(main_on, pf_on, imu_path, gt_dir, None, tmp_dir, "on")
            r_fl = evaluate_copy(still_py, None, imu_path, gt_dir, None, tmp_dir, "fl")
            rows.append({
                "copy": seq,
                "base": seq,
                "reading": "clean",
                "seed": None,
                "contract_off": r_off["contract"],
                "contract_on": r_on["contract"],
                "byte_identical": r_off["raw_bytes"] == r_on["raw_bytes"],
                "ape_off": r_off["ape"],
                "ape_on": r_on["ape"],
                "ape_diff": r_on["ape"] - r_off["ape"],
                "ape_floor": r_fl["ape"],
                "gap_off": None,
                "gap_on": None,
                "gap_diff": None,
                "gap_floor": None,
                "blind_off": None,
                "blind_on": None,
                "blind_diff": None,
                "blind_floor": None,
                "cal_source_off": r_off["cal_source"],
                "cal_source_on": r_on["cal_source"],
            })

        for seq in seqs:
            gt_dir = tumvi_root / seq
            for reading in readings:
                for seed in seeds:
                    copy_name = f"{seq}_{reading}_s{seed}"
                    cdir = official_root / copy_name
                    imu_path = cdir / "mav0" / "imu0" / "data.csv"
                    events = json.loads((cdir / "degrade.json").read_text(encoding="utf-8"))
                    r_off = evaluate_copy(main_off, pf_off, imu_path, gt_dir, events, tmp_dir, "off")
                    r_on = evaluate_copy(main_on, pf_on, imu_path, gt_dir, events, tmp_dir, "on")
                    r_fl = evaluate_copy(still_py, None, imu_path, gt_dir, events, tmp_dir, "fl")
                    gap_diff = (
                        r_on["gap_rmse"] - r_off["gap_rmse"]
                        if r_on["gap_rmse"] is not None and r_off["gap_rmse"] is not None
                        else None
                    )
                    blind_diff = (
                        r_on["blind_rmse"] - r_off["blind_rmse"]
                        if r_on["blind_rmse"] is not None and r_off["blind_rmse"] is not None
                        else None
                    )
                    rows.append({
                        "copy": copy_name,
                        "base": seq,
                        "reading": reading,
                        "seed": seed,
                        "contract_off": r_off["contract"],
                        "contract_on": r_on["contract"],
                        "byte_identical": r_off["raw_bytes"] == r_on["raw_bytes"],
                        "ape_off": r_off["ape"],
                        "ape_on": r_on["ape"],
                        "ape_diff": r_on["ape"] - r_off["ape"],
                        "ape_floor": r_fl["ape"],
                        "gap_off": r_off["gap_rmse"],
                        "gap_on": r_on["gap_rmse"],
                        "gap_diff": gap_diff,
                        "gap_floor": r_fl["gap_rmse"],
                        "blind_off": r_off["blind_rmse"],
                        "blind_on": r_on["blind_rmse"],
                        "blind_diff": blind_diff,
                        "blind_floor": r_fl["blind_rmse"],
                        "cal_source_off": r_off["cal_source"],
                        "cal_source_on": r_on["cal_source"],
                    })

    summary = {}
    for label, pred in (
        ("clean", lambda r: r["reading"] == "clean"),
        ("a", lambda r: r["reading"] == "a"),
        ("b", lambda r: r["reading"] == "b"),
        ("a+b", lambda r: r["reading"] in ("a", "b")),
    ):
        sub = [r for r in rows if pred(r)]
        if not sub:
            continue
        ape_diffs = [r["ape_diff"] for r in sub]
        gap_diffs = [r["gap_diff"] for r in sub if r["gap_diff"] is not None]
        blind_diffs = [r["blind_diff"] for r in sub if r["blind_diff"] is not None]
        summary[label] = {
            "copies": len(sub),
            "ape_off_mean": _mean([r["ape_off"] for r in sub]),
            "ape_on_mean": _mean([r["ape_on"] for r in sub]),
            "ape_diff_mean": _mean(ape_diffs),
            "ape_floor_mean": _mean([r["ape_floor"] for r in sub]),
            "gap_off_mean": _mean([r["gap_off"] for r in sub]),
            "gap_on_mean": _mean([r["gap_on"] for r in sub]),
            "gap_diff_mean": _mean(gap_diffs),
            "gap_floor_mean": _mean([r["gap_floor"] for r in sub]),
            "blind_off_mean": _mean([r["blind_off"] for r in sub]),
            "blind_on_mean": _mean([r["blind_on"] for r in sub]),
            "blind_diff_mean": _mean(blind_diffs),
            "blind_floor_mean": _mean([r["blind_floor"] for r in sub]),
            "ape_counts": _counts(ape_diffs),
            "gap_counts": _counts(gap_diffs) if gap_diffs else None,
            "blind_counts": _counts(blind_diffs) if blind_diffs else None,
        }

    return {
        "commit_off": c_off,
        "commit_on": c_on,
        "seqs": list(seqs),
        "readings": list(readings),
        "seeds": list(seeds),
        "rows": rows,
        "summary": summary,
    }


def _fmt(v: float | None, d: int = 4, signed: bool = False) -> str:
    if v is None:
        return "-"
    return f"{v:+.{d}f}" if signed else f"{v:.{d}f}"


def format_markdown(report: dict) -> str:
    c_off = report["commit_off"]
    c_on = report["commit_on"]
    lines = [
        f"### Per-copy comparison (`off = {c_off}`, `on = {c_on}`)",
        "",
        "| Copy | Reading | APE off / on (`on-off`) m | Floor APE m | Gap RMSE off / on (`on-off`) m | Floor Gap m | Blind RMSE off / on (`on-off`) m | Floor Blind m | `cal_source` (off / on) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in report["rows"]:
        ape_cell = f"{_fmt(r['ape_off'])} / {_fmt(r['ape_on'])} (`{_fmt(r['ape_diff'], signed=True)}`)"
        gap_cell = (
            "-"
            if r["gap_off"] is None
            else f"{_fmt(r['gap_off'])} / {_fmt(r['gap_on'])} (`{_fmt(r['gap_diff'], signed=True)}`)"
        )
        blind_cell = (
            "-"
            if r["blind_off"] is None
            else f"{_fmt(r['blind_off'])} / {_fmt(r['blind_on'])} (`{_fmt(r['blind_diff'], signed=True)}`)"
        )
        cal_cell = (
            r["cal_source_off"]
            if r["cal_source_off"] == r["cal_source_on"]
            else f"{r['cal_source_off']} / {r['cal_source_on']}"
        )
        lines.append(
            f"| `{r['copy']}` | {r['reading']} | {ape_cell} | {_fmt(r['ape_floor'])} | "
            f"{gap_cell} | {_fmt(r['gap_floor'])} | {blind_cell} | {_fmt(r['blind_floor'])} | `{cal_cell}` |"
        )

    lines += [
        "",
        f"### Summary by reading (`off = {c_off}`, `on = {c_on}`)",
        "",
        "| Reading | Copies | Mean APE off / on (`on-off`) m | Floor APE m | Mean Gap off / on (`on-off`) m | Mean Blind off / on (`on-off`) m | APE better / worse / tied |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for label in ("clean", "a", "b", "a+b"):
        s = report["summary"].get(label)
        if not s:
            continue
        c = s["ape_counts"]
        ape_cell = f"{_fmt(s['ape_off_mean'])} / {_fmt(s['ape_on_mean'])} (`{_fmt(s['ape_diff_mean'], signed=True)}`)"
        gap_cell = (
            "-"
            if s["gap_off_mean"] is None
            else f"{_fmt(s['gap_off_mean'])} / {_fmt(s['gap_on_mean'])} (`{_fmt(s['gap_diff_mean'], signed=True)}`)"
        )
        blind_cell = (
            "-"
            if s["blind_off_mean"] is None
            else f"{_fmt(s['blind_off_mean'])} / {_fmt(s['blind_on_mean'])} (`{_fmt(s['blind_diff_mean'], signed=True)}`)"
        )
        lines.append(
            f"| {label} | {s['copies']} | {ape_cell} | {_fmt(s['ape_floor_mean'])} | "
            f"{gap_cell} | {blind_cell} | {c['better']} / {c['worse']} / {c['same']} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir-off", required=True, help="worktree directory for the tilt-off build")
    ap.add_argument("--dir-on", required=True, help="worktree directory for the tilt-on build")
    ap.add_argument("--commit-off", default=None, help="explicit short commit hash for off build")
    ap.add_argument("--commit-on", default=None, help="explicit short commit hash for on build")
    ap.add_argument("--tumvi-root", default=str(ROOT / "data" / "tumvi"))
    ap.add_argument("--official-root", default=str(ROOT / "data" / "official_tumvi"))
    ap.add_argument("--seqs", default=",".join(DEFAULT_SEQS))
    ap.add_argument("--readings", default=",".join(DEFAULT_READINGS))
    ap.add_argument("--seeds", default=",".join(str(s) for s in DEFAULT_SEEDS))
    ap.add_argument("--json", default=None, help="optional JSON output path")
    args = ap.parse_args(argv)

    seqs = [s.strip() for s in args.seqs.split(",") if s.strip()]
    readings = [r.strip() for r in args.readings.split(",") if r.strip()]
    seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]

    report = compare_builds(
        dir_off=Path(args.dir_off).resolve(),
        dir_on=Path(args.dir_on).resolve(),
        tumvi_root=Path(args.tumvi_root).resolve(),
        official_root=Path(args.official_root).resolve(),
        seqs=seqs,
        readings=readings,
        seeds=seeds,
        commit_off=args.commit_off,
        commit_on=args.commit_on,
    )
    print(format_markdown(report))
    if args.json:
        out_path = Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

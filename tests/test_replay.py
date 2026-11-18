"""Tests for tools/replay.py: self-contained HTML, no http references, header numbers match score.py. All inputs SYNTHETIC."""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

from vortex import scoring
from vortex.data import euroc
from vortex.geometry import quat_from_rotvec, quat_to_matrix

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
import replay  # noqa: E402


def _make_synthetic_run(tmp_path: Path, n: int = 3000):
    """Create a synthetic sequence folder (IMU + mocap0 GT), an estimate file, and a degrade.json."""
    seq_dir = tmp_path / "MH_03_medium_b_s1"
    imu_dir = seq_dir / "mav0" / "imu0"
    gt_dir = seq_dir / "mav0" / "mocap0"
    imu_dir.mkdir(parents=True)
    gt_dir.mkdir(parents=True)

    t0_ns = 1403637130_000_000_000
    dt_ns = 5_000_000
    t_ns = t0_ns + np.arange(n, dtype=np.int64) * dt_ns
    t_s = t_ns / 1e9
    s = np.arange(n) * 0.005
    dur = float(s[-1])

    p_gt = np.column_stack([
        2.0 * np.sin(0.4 * s),
        1.5 * np.cos(0.3 * s),
        0.3 * np.sin(0.2 * s),
    ])
    rv = np.column_stack([0.05 * np.sin(s), 0.04 * np.cos(s), 0.15 * s])
    q_wxyz = quat_from_rotvec(rv)
    R_gt = quat_to_matrix(q_wxyz)

    imu_csv = imu_dir / "data.csv"
    with open(imu_csv, "w", encoding="ascii", newline="\n") as f:
        f.write(euroc.HEADER + "\n")
        for i in range(n):
            if s[i] >= dur - 5.0:
                f.write(f"{t_ns[i]},0.0,0.0,0.0,0.0,0.0,0.0\n")
            else:
                f.write(f"{t_ns[i]},0.01,-0.02,0.03,0.1,-0.1,9.81\n")

    gt_csv = gt_dir / "data.csv"
    with open(gt_csv, "w", encoding="ascii", newline="\n") as f:
        f.write("#timestamp [ns],p_x,p_y,p_z,q_w,q_x,q_y,q_z\n")
        for i in range(n):
            f.write(
                f"{t_ns[i]},{p_gt[i,0]:.6f},{p_gt[i,1]:.6f},{p_gt[i,2]:.6f},"
                f"{q_wxyz[i,0]:.7f},{q_wxyz[i,1]:.7f},{q_wxyz[i,2]:.7f},{q_wxyz[i,3]:.7f}\n"
            )

    # Estimate with known drift + dropout bump + blind drift
    drift = np.column_stack([0.04 * s, -0.02 * s, 0.01 * np.sin(s)])
    in_drop = (s >= 4.0) & (s < 5.0)
    drift[in_drop, 0] += 0.35
    in_blind = s >= (dur - 5.0)
    drift[in_blind, 1] += 0.25 * (s[in_blind] - (dur - 5.0))
    p_est = p_gt + drift
    q_xyzw = scoring.matrices_to_quat_xyzw(R_gt)

    est_txt = tmp_path / "estimated_trajectory.txt"
    with open(est_txt, "w", encoding="ascii", newline="\n") as f:
        for i, ts in enumerate(t_ns):
            sec, frac = divmod(int(ts), 1_000_000_000)
            f.write(
                f"{sec}.{frac:09d} {p_est[i,0]:.6f} {p_est[i,1]:.6f} {p_est[i,2]:.6f} "
                f"{q_xyzw[i,0]:.7f} {q_xyzw[i,1]:.7f} {q_xyzw[i,2]:.7f} {q_xyzw[i,3]:.7f}\n"
            )

    events = {
        "source": "synthetic test",
        "seed": 1,
        "reading": "b",
        "t0_ns": int(t0_ns),
        "healthy_end_s": 2.0,
        "dropouts_s": [[4.0, 5.0], [7.0, 7.5]],
        "dropout_rows": [200, 100],
        "single_missing_rows": 12,
        "failure_at_s": dur - 5.0,
        "end_s": dur,
        "blind_s": 5.0,
    }
    events_json = seq_dir / "degrade.json"
    events_json.write_text(json.dumps(events, indent=1) + "\n", encoding="utf-8")
    return imu_csv, est_txt, seq_dir, events_json, events, t_s


def _extract_id_text(html_text: str, elem_id: str) -> str:
    m = re.search(rf'id="{re.escape(elem_id)}"[^>]*>([^<]+)<', html_text)
    assert m is not None, f"missing element #{elem_id}"
    return m.group(1).strip()


def test_replay_html_has_no_http_and_matches_score_py(tmp_path):
    imu_csv, est_txt, seq_dir, events_json, events, _ = _make_synthetic_run(tmp_path, n=3000)
    out_html = tmp_path / "replay.html"

    rc = replay.main([
        str(imu_csv), str(est_txt),
        "--gt", str(seq_dir),
        "--events", str(events_json),
        "--floor",
        "-o", str(out_html),
    ])
    assert rc == 0
    assert out_html.is_file()
    text = out_html.read_text(encoding="utf-8")

    # Self-contained: no http/https references anywhere
    assert "http" not in text.lower()
    assert "local scoring, not the organisers' evaluator" in text
    assert 'class="xy-dropout"' in text
    assert 'class="xy-blind"' in text

    # Compare header numbers directly with score.py (vortex.scoring.score)
    ref = scoring.read_ground_truth(seq_dir)
    est, _ = scoring.read_tum(est_txt)
    expected_est = scoring.score(ref, est, align="se3", rpe_deltas=(200,), events=events)

    floor_traj = scoring.Traj(
        t=est.t.copy(),
        p=np.zeros_like(est.p),
        R=np.broadcast_to(np.eye(3), est.R.shape).copy(),
    )
    expected_floor = scoring.score(ref, floor_traj, align="se3", rpe_deltas=(200,), events=events)

    exp_gap_est = sum(d["rmse"] for d in expected_est["phases"]["dropouts"]) / len(expected_est["phases"]["dropouts"])
    exp_gap_flo = sum(d["rmse"] for d in expected_floor["phases"]["dropouts"]) / len(expected_floor["phases"]["dropouts"])

    assert float(_extract_id_text(text, "val-ape-est")) == pytest.approx(expected_est["ape"]["rmse"], abs=1e-4)
    assert float(_extract_id_text(text, "val-rpe-est")) == pytest.approx(expected_est["rpe"]["200"]["rmse"], abs=1e-4)
    assert float(_extract_id_text(text, "val-gap-est")) == pytest.approx(exp_gap_est, abs=1e-4)
    assert float(_extract_id_text(text, "val-blind-est")) == pytest.approx(
        expected_est["phases"]["blind"]["rmse"], abs=1e-4
    )

    assert float(_extract_id_text(text, "val-ape-floor")) == pytest.approx(expected_floor["ape"]["rmse"], abs=1e-4)
    assert float(_extract_id_text(text, "val-rpe-floor")) == pytest.approx(expected_floor["rpe"]["200"]["rmse"], abs=1e-4)
    assert float(_extract_id_text(text, "val-gap-floor")) == pytest.approx(exp_gap_flo, abs=1e-4)
    assert float(_extract_id_text(text, "val-blind-floor")) == pytest.approx(
        expected_floor["phases"]["blind"]["rmse"], abs=1e-4
    )


def test_replay_works_with_no_ground_truth(tmp_path):
    imu_csv, est_txt, _, _, _, _ = _make_synthetic_run(tmp_path, n=1200)
    out_html = tmp_path / "replay_nogt.html"

    rc = replay.main([str(imu_csv), str(est_txt), "-o", str(out_html)])
    assert rc == 0
    text = out_html.read_text(encoding="utf-8")
    assert "http" not in text.lower()
    assert _extract_id_text(text, "val-ape-est") == "-"
    assert _extract_id_text(text, "val-blind-est") == "-"
    assert 'id="svg-xy"' in text and 'id="svg-z"' in text and 'id="svg-err"' in text


def test_replay_under_3mb_for_mh01_row_count(tmp_path):
    imu_csv, est_txt, seq_dir, events_json, _, _ = _make_synthetic_run(tmp_path, n=36820)
    out_html = tmp_path / "replay_mh01.html"

    rc = replay.main([
        str(imu_csv), str(est_txt),
        "--gt", str(seq_dir),
        "--events", str(events_json),
        "--floor",
        "-o", str(out_html),
    ])
    assert rc == 0
    size_bytes = out_html.stat().st_size
    assert size_bytes < 3_000_000
    assert "http" not in out_html.read_text(encoding="utf-8").lower()

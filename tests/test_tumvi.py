"""TUM-VI layout compatibility (mav0/imu0 + mav0/mocap0), scoring, and --root options. All inputs SYNTHETIC."""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

from vortex import scoring
from vortex.data import euroc
from vortex.geometry import quat_from_rotvec, quat_to_matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import eval_euroc  # noqa: E402
import official_degrade  # noqa: E402
import tumvi_inspect  # noqa: E402
import tumvi_table  # noqa: E402

IMU_HEADER = euroc.HEADER
MOCAP_HEADER = ("#timestamp [ns], p_RS_R_x [m], p_RS_R_y [m], p_RS_R_z [m], "
                "q_RS_w [], q_RS_x [], q_RS_y [], q_RS_z []")


def _make_synthetic_tumvi(base_dir: Path, name: str = "dataset-room1_512_16", n: int = 2400):
    """Create a minimal synthetic TUM-VI sequence folder (12 s at 200 Hz, 8-column mocap0)."""
    seq = base_dir / name
    imu_dir = seq / "mav0" / "imu0"
    mocap_dir = seq / "mav0" / "mocap0"
    imu_dir.mkdir(parents=True)
    mocap_dir.mkdir(parents=True)

    t0_ns = 1520530424_000_000_000
    dt_ns = 5_000_000
    t_ns = t0_ns + np.arange(n, dtype=np.int64) * dt_ns
    s = np.arange(n) * 0.005

    imu_lines = [IMU_HEADER]
    mocap_lines = [MOCAP_HEADER]
    rng = np.random.default_rng(42)
    # Moving gently after 2 s rest so SE3 alignment is well-conditioned
    p = np.column_stack([
        np.where(s > 2.0, 0.5 * np.sin(0.6 * (s - 2.0)), 0.0),
        np.where(s > 2.0, 0.4 * (1.0 - np.cos(0.6 * (s - 2.0))), 0.0),
        np.where(s > 2.0, 0.05 * (s - 2.0), 0.0),
    ])
    rv = np.column_stack([0.02 * np.sin(s), 0.02 * np.cos(s), 0.1 * s])
    q_wxyz = quat_from_rotvec(rv)

    g_noise = rng.normal(0.0, 0.001, size=(n, 3))
    a_noise = rng.normal(0.0, 0.01, size=(n, 3))
    for i in range(n):
        gx, gy, gz = 0.001 + g_noise[i, 0], -0.002 + g_noise[i, 1], 0.003 + g_noise[i, 2]
        ax, ay, az = a_noise[i, 0], a_noise[i, 1], 9.81 + a_noise[i, 2]
        imu_lines.append("%d,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f" % (t_ns[i], gx, gy, gz, ax, ay, az))
        mocap_lines.append("%d,%.6f,%.6f,%.6f,%.7f,%.7f,%.7f,%.7f" % (
            t_ns[i], p[i, 0], p[i, 1], p[i, 2], q_wxyz[i, 0], q_wxyz[i, 1], q_wxyz[i, 2], q_wxyz[i, 3]))

    (imu_dir / "data.csv").write_text("\n".join(imu_lines) + "\n", encoding="ascii")
    (mocap_dir / "data.csv").write_text("\n".join(mocap_lines) + "\n", encoding="ascii")
    return seq, t_ns, p, q_wxyz


def test_euroc_loader_reads_synthetic_tumvi(tmp_path):
    seq, t_ns, p, q_wxyz = _make_synthetic_tumvi(tmp_path)
    assert euroc.imu_path(seq) == seq / "mav0" / "imu0" / "data.csv"

    raw = euroc.read_imu_csv(seq)
    assert len(raw) == len(t_ns)
    assert np.all(raw.valid)
    assert np.array_equal(raw.t_ns, t_ns)

    gt = euroc.load_ground_truth(seq)
    assert len(gt) == len(t_ns)
    assert gt.name == "dataset-room1_512_16"
    assert np.allclose(gt.p, p, atol=1e-6)
    assert np.allclose(gt.q, q_wxyz, atol=1e-6)


def test_scoring_and_cli_on_synthetic_tumvi(tmp_path, capsys):
    seq, t_ns, p, q_wxyz = _make_synthetic_tumvi(tmp_path)
    ref = scoring.read_ground_truth(seq)
    R = quat_to_matrix(q_wxyz)
    est_traj = scoring.Traj(t=t_ns / 1e9, p=p + np.array([1.0, -0.5, 0.2]), R=R)
    res = scoring.score(ref, est_traj, align="se3", rpe_deltas=(200,))
    assert res["ape"]["rmse"] == pytest.approx(0.0, abs=1e-6)
    assert res["rpe"]["200"]["rmse"] == pytest.approx(0.0, abs=1e-6)

    est_file = tmp_path / "est.txt"
    q_xyzw = scoring.matrices_to_quat_xyzw(R)
    with open(est_file, "w", encoding="ascii") as f:
        for i, ts in enumerate(t_ns):
            sec, frac = divmod(int(ts), 1_000_000_000)
            f.write("%d.%09d %.6f %.6f %.6f %.7f %.7f %.7f %.7f\n" % (
                sec, frac, p[i, 0], p[i, 1], p[i, 2], *q_xyzw[i]))

    out_json = tmp_path / "score.json"
    rc = scoring.main(["--gt", str(seq), "--est", str(est_file), "--imu", str(euroc.imu_path(seq)),
                       "--align", "se3", "--json", str(out_json)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "output contract: PASS" in out
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["contract"]["ok"] is True
    assert data["ape"]["rmse"] == pytest.approx(0.0, abs=1e-5)


def test_official_degrade_root_and_eval_euroc_root(tmp_path, monkeypatch):
    if not os.path.exists(official_degrade.SCRIPT):
        pytest.skip("tools/official/degrade_imu.py not present")

    tumvi_root = tmp_path / "tumvi"
    seq, _, _, _ = _make_synthetic_tumvi(tumvi_root, "dataset-room1_512_16", n=2400)
    off_root = tmp_path / "official_tumvi"

    rc = official_degrade.main([
        "--all", "--root", str(tumvi_root), "--readings", "a,b", "--seeds", "1", "--out", str(off_root)
    ])
    assert rc == 0
    for r in ("a", "b"):
        copy_dir = off_root / f"dataset-room1_512_16_{r}_s1"
        assert (copy_dir / "mav0" / "imu0" / "data.csv").is_file()
        assert (copy_dir / "meta.json").is_file()
        assert (copy_dir / "degrade.json").is_file()

    # Keep Docs/RESULTS.md and Docs/tumvi/ untouched during tests
    monkeypatch.setattr(eval_euroc, "OUT_DIR", str(tmp_path / "docs" / "results"))
    still = str(ROOT / "tools" / "baseline_still.py")

    rc_clean = eval_euroc.main([
        "--tag", "syn-clean", "--root", str(tumvi_root), "--main", still
    ])
    assert rc_clean == 0
    clean_json = tmp_path / "docs" / "tumvi" / "syn-clean.json"
    assert clean_json.is_file()
    clean_data = json.loads(clean_json.read_text(encoding="utf-8"))
    assert len(clean_data["results"]) == 1
    assert clean_data["results"][0]["contract"] == "PASS"

    rc_off = eval_euroc.main([
        "--tag", "syn-off", "--root", str(tumvi_root), "--official", "--main", still
    ])
    assert rc_off == 0
    off_json = tmp_path / "docs" / "tumvi" / "syn-off.json"
    assert off_json.is_file()
    off_data = json.loads(off_json.read_text(encoding="utf-8"))
    assert len(off_data["results"]) == 2
    assert all(r["contract"] == "PASS" for r in off_data["results"])
    assert not (tmp_path / "docs" / "RESULTS.md").exists()


def test_tumvi_inspect_and_tumvi_table_on_synthetic(tmp_path, monkeypatch, capsys):
    if not os.path.exists(official_degrade.SCRIPT):
        pytest.skip("tools/official/degrade_imu.py not present")

    tumvi_root = tmp_path / "tumvi"
    _make_synthetic_tumvi(tumvi_root, "dataset-room1_512_16", n=2400)
    _make_synthetic_tumvi(tumvi_root, "dataset-room3_512_16", n=2400)
    off_root = tmp_path / "official_tumvi"

    assert official_degrade.main([
        "--all", "--root", str(tumvi_root), "--readings", "a,b", "--seeds", "1", "--out", str(off_root)
    ]) == 0

    inspect_json = tmp_path / "inspect.json"
    assert tumvi_inspect.main(["--root", str(tumvi_root), "--json", str(inspect_json)]) == 0
    inspected = json.loads(inspect_json.read_text(encoding="utf-8"))
    assert len(inspected) == 2
    assert inspected[0]["imu_rows"] == 2400 and inspected[0]["imu_gaps"] == 0
    assert "| dataset-room1_512_16 |" in capsys.readouterr().out

    monkeypatch.setattr(eval_euroc, "OUT_DIR", str(tmp_path / "docs" / "results"))
    still = str(ROOT / "tools" / "baseline_still.py")
    main_py = str(ROOT / "main.py")
    assert eval_euroc.main(["--tag", "tumvi-clean", "--root", str(tumvi_root), "--main", main_py]) == 0
    assert eval_euroc.main(["--tag", "tumvi-floor-clean", "--root", str(tumvi_root), "--main", still]) == 0
    assert eval_euroc.main(["--tag", "tumvi-off", "--root", str(tumvi_root), "--official", "--main", main_py]) == 0
    assert eval_euroc.main(["--tag", "tumvi-floor-off", "--root", str(tumvi_root), "--official", "--main", still]) == 0

    out_md = tmp_path / "TUMVI_BASELINE.md"
    docs_tumvi = str(tmp_path / "docs" / "tumvi")
    assert tumvi_table.main([
        "--docs-dir", docs_tumvi,
        "--tumvi-root", str(tumvi_root),
        "--official-root", str(off_root),
        "--out", str(out_md),
        "--collect-calib",
    ]) == 0
    md = out_md.read_text(encoding="utf-8")
    assert "dataset-room1_512_16" in md and "dataset-room3_512_16" in md
    assert "BG_MAX" in md and "LAST calibrated" in md
    calib = json.loads((tmp_path / "docs" / "tumvi" / "tumvi-calib.json").read_text(encoding="utf-8"))
    assert len(calib["clean"]) == 2 and len(calib["official"]) == 4
    assert calib["clean"]["dataset-room1_512_16"]["calibrated"] is True

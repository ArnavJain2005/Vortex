"""pathfinder.py (shipped, lean since 18 Nov 2026) against tools/pathfinder_lab.py (the full estimator with
every switched-off experiment): with all experiments off the lab copy must write byte-identical output, and
every constant the two share must be equal. All SYNTHETIC; the same check on every real input on disk is
recorded in Docs/TRACK3_PLAN.md (step "Lean pathfinder")."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_core_equivalence import _write_rows  # noqa: E402
from test_faults import _degraded_rows  # noqa: E402
from test_main import MESSY  # noqa: E402
from test_strapdown import _move_rest_move  # noqa: E402

EXPERIMENTS = ("FF_STUCK6_ON", "FF_SPIKE_ON", "LEARN_ON", "INTERP_ON", "JAM_ON", "RESET_ON", "SHRINK_ON")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pf = _load("vortex_pf_lean", ROOT / "pathfinder.py")
lab = _load("vortex_pf_lab", ROOT / "tools" / "pathfinder_lab.py")


def test_experiments_are_off_in_the_lab_and_absent_from_pathfinder():
    for name in EXPERIMENTS:
        assert getattr(lab, name) is False, name
        assert not hasattr(pf, name), name


def test_shared_constants_are_equal():
    shared = [n for n in dir(pf) if n.isupper() and n != "LAST" and hasattr(lab, n)]   # LAST: run state
    assert len(shared) > 60
    for n in shared:
        a, b = getattr(pf, n), getattr(lab, n)
        assert a == b or (a != a and b != b), n            # NAN: equal as NaN
    only_pf = [n for n in dir(pf) if n.isupper() and not hasattr(lab, n)]
    assert only_pf == [], only_pf


def _accel_first(rows):
    """The same rows written accelerometer first with an accel-first header (the front end reorders them)."""
    return b"#timestamp [ns],a_x,a_y,a_z,w_x,w_y,w_z\n" + b"".join(
        b"%d,%s\n" % (t, b",".join(repr(float(x)).encode() for x in v[3:] + v[:3])) for t, v in rows)


@pytest.mark.parametrize("case", ["messy", "degraded", "move_rest_move", "accel_first", "empty"])
def test_lab_with_everything_off_equals_pathfinder(tmp_path, case):
    src = tmp_path / "imu.csv"
    if case == "messy":
        src.write_bytes(MESSY)
    elif case == "degraded":
        _write_rows(src, _degraded_rows())
    elif case == "move_rest_move":
        rows, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.002, acc_noise=0.02, seed=5)
        _write_rows(src, rows)
    elif case == "accel_first":
        rows, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.002, acc_noise=0.02, seed=8)
        src.write_bytes(_accel_first(rows))
    else:
        src.write_bytes(b"#timestamp [ns],w_x,w_y,w_z,a_x,a_y,a_z\n")
    na = pf.run(str(src), str(tmp_path / "a.txt"))
    nb = lab.run(str(src), str(tmp_path / "b.txt"))
    assert na == nb
    assert (tmp_path / "a.txt").read_bytes() == (tmp_path / "b.txt").read_bytes()
    for k in ("pre_rows", "calibrated", "zupt_ticks", "ba", "tilt2", "frontend"):
        assert pf.LAST.get(k) == lab.LAST.get(k), k
    if case == "accel_first":
        assert not pf.LAST["frontend"]["canonical"]

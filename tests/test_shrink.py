"""Step L1: positions scaled about their centroid, alpha per noise class (vortex/core/shrink.py) and the
pathfinder.py copy (`_sh_*`). All SYNTHETIC."""

import importlib.util
import random
import sys
from pathlib import Path

import numpy as np
import pytest

from vortex.core import shrink as sh
from vortex.core import strapdown as sd
from vortex.core import witness as wx
from vortex.data import euroc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_core_equivalence as tce  # noqa: E402
from test_core_equivalence import FULL, _compare, _write_rows  # noqa: E402
from test_faults import _degraded_rows  # noqa: E402
from test_strapdown import _move_rest_move  # noqa: E402


def _load_pf():
    spec = importlib.util.spec_from_file_location("vortex_pf_shrink", ROOT / "pathfinder.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pf = _load_pf()
T0 = 1403636579758555392
DT = 5_000_000
NAMES = ("SHRINK_ON", "SHRINK_NOISE", "SHRINK_WIN_S", "SHRINK_BLIND_S", "SHRINK_BIN_S", "SHRINK_BIN_MIN",
         "SHRINK_MAX_DT", "SHRINK_ALPHA_LO", "SHRINK_ALPHA_HI")


def _noisy(n, sigma, seed=0, quiet_until=0):
    """Level sensor, slow sinusoidal turn, white gyro noise sigma (rad/s per sample) from row quiet_until."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        s = sigma if i >= quiet_until else 0.0
        w = 0.2 * np.sin(2 * np.pi * 0.2 * i * DT * 1e-9)
        rows.append((T0 + i * DT, (rng.gauss(0, s), rng.gauss(0, s), float(w) + rng.gauss(0, s),
                                   rng.gauss(0, 0.02), rng.gauss(0, 0.02), 9.81 + rng.gauss(0, 0.02))))
    return rows


def _set(monkeypatch, on=True, lo=None, hi=None, noise=None):
    for mod in (sh, pf):
        monkeypatch.setattr(mod, "SHRINK_ON", on)
        if lo is not None:
            monkeypatch.setattr(mod, "SHRINK_ALPHA_LO", lo)
        if hi is not None:
            monkeypatch.setattr(mod, "SHRINK_ALPHA_HI", hi)
        if noise is not None:
            monkeypatch.setattr(mod, "SHRINK_NOISE", noise)


def test_parameters_identical_and_shipped_state():
    for name in NAMES:
        assert getattr(pf, name) == getattr(sh, name), name
    assert sh.SHRINK_ON is False and pf.SHRINK_ON is False


@pytest.mark.parametrize("sigma", [0.015, 0.05, 0.2])
def test_meter_reads_the_white_noise(tmp_path, sigma):
    rows = _noisy(8000, sigma, seed=2)                 # 40 s: the window is 15..35 s
    src = _write_rows(tmp_path / "imu.csv", rows)
    got = pf._sh_noise(str(src))
    assert got == sh.gyro_noise(sd.rows_from_raw(euroc.read_imu_csv(src)))
    assert abs(got / sigma - 1.0) < 0.1, got


def test_meter_ignores_the_last_5_s_and_the_early_part(tmp_path):
    # noise only before the window (rows < 3000 = 15 s) and in the last 5 s
    rows = _noisy(8000, 0.0, seed=3)
    rng = random.Random(4)
    rows = [(t, tuple(x + (rng.gauss(0, 0.3) if (i < 3000 or i >= 7000) and k < 3 else 0.0)
                      for k, x in enumerate(v))) for i, (t, v) in enumerate(rows)]
    src = _write_rows(tmp_path / "imu.csv", rows)
    assert pf._sh_noise(str(src)) < 1e-3


def test_meter_on_a_degraded_file_matches_the_reference(tmp_path):
    rows = _degraded_rows()
    src = _write_rows(tmp_path / "imu.csv", rows)
    a = pf._sh_noise(str(src))
    b = sh.gyro_noise(sd.rows_from_raw(euroc.read_imu_csv(src)))
    assert a == b and a > 0.0


def test_meter_with_no_valid_window_is_minus_one(tmp_path):
    rows = [(T0 + i * DT, (0.0,) * 6) for i in range(3000)]
    src = _write_rows(tmp_path / "imu.csv", rows)
    assert pf._sh_noise(str(src)) == -1.0
    assert sh.gyro_noise(sd.rows_from_raw(euroc.read_imu_csv(src))) == -1.0


def test_apply_keeps_the_centroid_and_scales_the_spread():
    rng = random.Random(0)
    out = [(rng.gauss(1, 2), rng.gauss(-3, 1), rng.gauss(0.5, 0.2), 1.0, 0.0, 0.0, 0.0) for _ in range(500)]
    p = np.array(out)[:, :3]
    for alpha in (0.0, 0.3, 1.7):
        q = np.array(sh.apply(out, alpha))
        assert np.allclose(q[:, :3].mean(0), p.mean(0))
        assert np.allclose(q[:, :3] - q[:, :3].mean(0), alpha * (p - p.mean(0)))
        assert np.array_equal(q[:, 3:], np.array(out)[:, 3:])
    assert sh.apply(out, 1.0) is out


def test_off_and_alpha_one_leave_the_output_byte_identical(tmp_path, monkeypatch):
    rows, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.002, acc_noise=0.02, seed=5)
    src = _write_rows(tmp_path / "imu.csv", rows)
    _set(monkeypatch, on=False)
    pf.run(str(src), str(tmp_path / "off.txt"))
    _set(monkeypatch, on=True, lo=1.0, hi=1.0)
    pf.run(str(src), str(tmp_path / "one.txt"))
    assert (tmp_path / "off.txt").read_bytes() == (tmp_path / "one.txt").read_bytes()
    assert pf.LAST["shrink"][1] == 1.0


@pytest.mark.parametrize("case", ["move_rest_move", "degraded", "noisy"])
@pytest.mark.parametrize("lo,hi,noise", [(0.25, 1.0, 0.10), (1.0, 1.6, 0.10), (0.0, 0.0, 0.10), (0.4, 1.3, 1e-9)])
def test_reference_and_pathfinder_agree(tmp_path, monkeypatch, case, lo, hi, noise):
    if case == "move_rest_move":
        rows, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.002, acc_noise=0.02, seed=5)
    elif case == "degraded":
        rows = _degraded_rows()
    else:
        rows = _noisy(8000, 0.2, seed=1)
    src = _write_rows(tmp_path / "imu.csv", rows)
    _set(monkeypatch, on=True, lo=lo, hi=hi, noise=noise)
    monkeypatch.setattr(tce, "main", pf)
    monkeypatch.setattr(pf, "SH_FMT", b"%s %.17g %.17g %.17g %s")
    _compare(src, tmp_path, monkeypatch, reference=wx.estimate_file)
    assert pf.LAST["shrink"] == sh.LAST[0]


def test_the_class_picks_the_alpha(tmp_path, monkeypatch):
    src = _write_rows(tmp_path / "imu.csv", _noisy(8000, 0.2, seed=1))
    _set(monkeypatch, on=True, lo=0.25, hi=1.5)
    pf.run(str(src), str(tmp_path / "o.txt"))
    assert pf.LAST["shrink"][1] == 0.25
    src = _write_rows(tmp_path / "imu2.csv", _noisy(8000, 0.015, seed=1))
    pf.run(str(src), str(tmp_path / "o2.txt"))
    assert pf.LAST["shrink"][1] == 1.5


def test_output_contract_holds_with_shrink(tmp_path, monkeypatch):
    from vortex import check_output
    src = _write_rows(tmp_path / "imu.csv", _degraded_rows())
    _set(monkeypatch, on=True, lo=0.2, hi=0.2)
    pf.run(str(src), str(tmp_path / "o.txt"))
    assert check_output.check(str(src), str(tmp_path / "o.txt"))["ok"]
    assert not list(tmp_path.glob("*.vortex_sh"))


assert FULL  # the full-precision format the comparison uses (imported for clarity)

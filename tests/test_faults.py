"""Fault front end (Step 3): stuck rows, spikes, blind-window protection and bridging of missing samples,
in the reference (vortex/core/faults.py, witness.INTERP_ON) and its copy in pathfinder.py. All SYNTHETIC."""

import importlib.util
import math
import random
import sys
from pathlib import Path

import numpy as np
import pytest

from vortex.core import faults as ff
from vortex.core import witness as wx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_core_equivalence import _compare, _write_rows  # noqa: E402
from test_strapdown import _move_rest_move  # noqa: E402


def _load_pf():
    spec = importlib.util.spec_from_file_location("vortex_pf_faults", ROOT / "pathfinder.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pf = _load_pf()
HDR = b"#timestamp [ns],w_x,w_y,w_z,a_x,a_y,a_z\n"
T0 = 1403636579758555392
DT = 5_000_000


def _line(t, v):
    return (str(t) + "," + ",".join("%.6f" % x for x in v) + "\n").encode()


def _noisy(n, seed=0, spikes=(), gyro_only=()):
    """Smooth motion + small noise, 6 decimals; joint spikes at `spikes`, gyro-only bumps at `gyro_only`."""
    rng = random.Random(seed)
    out = [HDR]
    for i in range(n):
        s = i * 0.005
        v = [0.2 * math.sin(s), 0.1 * math.cos(0.7 * s), 0.05, 0.3 * math.sin(0.5 * s), 0.2, 9.81]
        v = [x + rng.gauss(0, 0.01 if k < 3 else 0.1) for k, x in enumerate(v)]
        if i in spikes:
            v = [x + (1.2 if k < 3 else 7.0) * (1 if (i + k) % 2 else -1) for k, x in enumerate(v)]
        if i in gyro_only:
            v = [x + (1.2 if k < 3 else 0.0) for k, x in enumerate(v)]
        out.append(_line(T0 + i * DT, v))
    return out


def _flags(lines, **kw):
    st = {}
    out = list(ff.filter_lines(lines, stats=st, **kw))
    data = [l for l in out if l.strip()[:1] != b"#"]
    return [l.rstrip().endswith(b",m") for l in data], data, st


def test_stuck_repeats_and_duplicates_become_missing():
    lines = _noisy(300)
    lines[101:101] = [lines[100]] * 4                        # a stuck run: 4 exact repeats of row 99
    dup = lines[201]
    lines.insert(201, dup)                                   # a duplicated row (same timestamp too)
    flags, data, st = _flags(lines, stuck=True, spike=False)
    assert len(data) == 305
    assert [i for i, f in enumerate(flags) if f] == [100, 101, 102, 103, 201]
    assert st["stuck"] == 5
    flags, _, _ = _flags(lines, stuck=False, spike=False)
    assert not any(flags)
    assert data[99] == lines[100]                            # the first row of the run is kept as it is


def test_trailing_zeros_are_the_blind_window_and_mid_zeros_are_a_fault():
    lines = _noisy(400)
    z = [_line(T0 + (400 + i) * DT, [0.0] * 6) for i in range(50)]
    mid = [_line(T0 + i * DT, [0.0] * 6) for i in range(1, 4)]
    lines = lines[:150] + mid + lines[150:] + z
    flags, data, st = _flags(lines, stuck=True, spike=False)
    assert st["blind_rows"] == 50 and st["zero_mid"] == 3
    assert not any(flags[-50:]) and data[-50:] == z          # blind rows untouched
    assert flags[149:152] == [True, True, True]
    flags, data, st = _flags(lines, stuck=False, spike=False)
    assert st["blind_rows"] == 50 and not any(flags)


def test_joint_spike_is_found_and_a_one_triple_bump_is_not():
    lines = _noisy(2000, spikes={500, 1500}, gyro_only={1000})
    flags, data, st = _flags(lines, stuck=True, spike=True)
    hits = [i for i, f in enumerate(flags) if f]
    assert 500 in hits and 1500 in hits and 1000 not in hits
    assert len(hits) <= 4                                    # no flood of false alarms on smooth noise
    flags, _, _ = _flags(lines, stuck=True, spike=False)
    assert not any(flags)


def test_rows_keep_their_number_and_order():
    lines = _noisy(1000, spikes={300})
    lines[600:600] = [lines[601]] * 3
    lines.insert(800, b"bad,1,2,3,4,5,6\n")
    _, data, _ = _flags(lines, stuck=True, spike=True)
    src = [l for l in lines if l[:1] != b"#"]
    assert len(data) == len(src)
    assert [l.split(b",")[0] for l in data] == [l.split(b",")[0] for l in src]


def test_pathfinder_copy_gives_the_same_lines():
    lines = _noisy(3000, seed=3, spikes={700, 2100}, gyro_only={1200})
    lines[900:900] = [lines[901]] * 5
    lines += [_line(T0 + (3000 + i) * DT, [0.0] * 6) for i in range(20)]
    for kw in ({"stuck": True, "spike": True}, {"stuck": True, "spike": False}, {"stuck": False, "spike": True}):
        assert list(pf._ff_filter_lines(lines, **kw)) == list(ff.filter_lines(lines, **kw))


def _degraded_rows():
    rows, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.002, acc_noise=0.02, seed=3)
    rows = [(t, tuple(round(x, 6) for x in v)) for t, v in rows]
    rng = random.Random(1)
    out = []
    for i, (t, v) in enumerate(rows):
        if i > 4500 and i % 997 == 0:                         # spike, then a stuck run repeating it
            v = tuple(x + (1.0 if k < 3 else 6.0) for k, x in enumerate(v))
            out += [(t, v)] + [(rows[i + j][0], v) for j in range(1, 4)]
            continue
        if out and t <= out[-1][0]:
            continue
        if i > 4500 and i % 1499 == 0:                        # a 40-row burst of missing rows
            continue
        if 5000 < i < 5040:
            continue
        out.append((t, v))
        if rng.random() < 0.003:
            out.append((t, v))                                # duplicated row
    out += [(out[-1][0] + DT * (k + 1), (0.0,) * 6) for k in range(200)]
    return out


@pytest.mark.parametrize("stuck,spike,interp", [(True, True, True), (True, False, True), (False, True, False),
                                                 (False, False, True)])
def test_reference_and_pathfinder_agree(tmp_path, monkeypatch, stuck, spike, interp):
    src = _write_rows(tmp_path / "imu.csv", _degraded_rows())
    monkeypatch.setattr(ff, "STUCK6_ON", stuck)
    monkeypatch.setattr(ff, "SPIKE_ON", spike)
    monkeypatch.setattr(wx, "INTERP_ON", interp)
    monkeypatch.setattr(pf, "FF_STUCK6_ON", stuck)
    monkeypatch.setattr(pf, "FF_SPIKE_ON", spike)
    monkeypatch.setattr(pf, "INTERP_ON", interp)
    import test_core_equivalence as tce
    monkeypatch.setattr(tce, "main", pf)
    _compare(src, tmp_path, monkeypatch, reference=wx.estimate_file)


def test_switches_off_change_nothing(tmp_path):
    src = _write_rows(tmp_path / "imu.csv", _degraded_rows())
    assert not (pf.FF_STUCK6_ON or pf.FF_SPIKE_ON or pf.INTERP_ON)
    pf.run(str(src), str(tmp_path / "a.txt"))
    assert pf.LAST["faults"] is None


def test_bridging_a_burst_beats_coasting(tmp_path, monkeypatch):
    """Noiseless SYNTHETIC motion with a 0.2 s burst of missing rows at 27 s (after the rest that anchors the
    calibration): integrating across it (INTERP_ON) ends closer to the run without the burst than coasting
    with the velocity decay does. Same anchor, so the same frame."""
    rows, _, _ = _move_rest_move(seconds=32.0)
    full = _write_rows(tmp_path / "full.csv", rows)
    pf.run(str(full), str(tmp_path / "full.txt"))
    end_full = np.array([float(x) for x in (tmp_path / "full.txt").read_text().splitlines()[-1].split()[1:4]])
    src = _write_rows(tmp_path / "imu.csv", [r for i, r in enumerate(rows) if not 5400 < i < 5440])
    err = {}
    for on in (False, True):
        monkeypatch.setattr(pf, "INTERP_ON", on)
        pf.run(str(src), str(tmp_path / "o.txt"))
        end = np.array([float(x) for x in (tmp_path / "o.txt").read_text().splitlines()[-1].split()[1:4]])
        err[on] = np.linalg.norm(end - end_full)
    assert err[True] < 0.2 * err[False], err

"""Seeded degradation: rising noise, bias drift, 2 s dropouts (NaN or missing rows), failure + blind tail."""

import json

import numpy as np
import pytest

from vortex import degrade
from vortex.data import euroc

RATE = 200.0
T0_NS = 1403636579758555392


def _clean(seconds=120.0, gyro=(0.01, -0.02, 0.03), accel=(9.8, 0.1, -0.2)):
    n = int(seconds * RATE)
    t_ns = T0_NS + np.arange(n, dtype=np.int64) * 5_000_000
    return euroc.RawImu(t_text=[str(int(v)) for v in t_ns], t_ns=t_ns,
                        gyro=np.tile(np.array(gyro, float), (n, 1)),
                        accel=np.tile(np.array(accel, float), (n, 1)), header=euroc.HEADER)


def _write_bytes(raw, tmp_path, name, **kw):
    p = tmp_path / name
    euroc.write_imu_csv(raw, p, **kw)
    return p.read_bytes()


def test_same_seed_same_bytes_different_seed_differs(tmp_path):
    clean = _clean()
    a, ea = degrade.degrade(clean, degrade.DegradeConfig(), seed=7)
    b, eb = degrade.degrade(clean, degrade.DegradeConfig(), seed=7)
    c, _ = degrade.degrade(clean, degrade.DegradeConfig(), seed=8)
    assert _write_bytes(a, tmp_path, "a.csv") == _write_bytes(b, tmp_path, "b.csv")
    assert json.dumps(ea, sort_keys=True) == json.dumps(eb, sort_keys=True)
    assert _write_bytes(a, tmp_path, "a.csv") != _write_bytes(c, tmp_path, "c.csv")


def test_input_is_not_modified():
    clean = _clean()
    before = clean.gyro.copy()
    degrade.degrade(clean, degrade.DegradeConfig(), seed=1)
    assert np.array_equal(clean.gyro, before)


def test_event_windows_are_valid():
    cfg = degrade.DegradeConfig(dropout_count=3, dropout_s=2.0, healthy_s=10.0, min_gap_s=5.0)
    _, ev = degrade.degrade(_clean(), cfg, seed=3)
    drops = ev["dropouts_s"]
    assert len(drops) == 3
    for s, e in drops:
        assert e - s == pytest.approx(2.0)
        assert s >= 10.0 and e + 5.0 <= ev["failure_at_s"] + 1e-9
    for (s0, e0), (s1, e1) in zip(drops, drops[1:]):
        assert s1 - e0 >= 5.0 - 1e-9
    assert ev["end_s"] == pytest.approx(ev["failure_at_s"] + 5.0, abs=1.0 / RATE)


def test_nan_dropouts_keep_row_count_and_blank_exactly_the_windows():
    cfg = degrade.DegradeConfig(dropout_mode="nan", failure_mode="nan")
    out, ev = degrade.degrade(_clean(), cfg, seed=4)
    t = (out.t_ns - T0_NS) / 1e9
    nan_row = np.all(np.isnan(out.gyro), axis=1) & np.all(np.isnan(out.accel), axis=1)
    expected = t >= ev["failure_at_s"]
    for s, e in ev["dropouts_s"]:
        expected |= (t >= s) & (t < e)
    assert np.array_equal(nan_row, expected)
    # rows end at failure + blind_s: input was longer, so the tail is cut
    assert len(out) == ev["rows_out"] and ev["rows_out"] < ev["rows_in"]
    assert np.all(np.diff(out.t_ns) > 0)


def test_missing_dropouts_remove_rows():
    cfg = degrade.DegradeConfig(dropout_mode="missing")
    out, ev = degrade.degrade(_clean(), cfg, seed=4)
    t = (out.t_ns - T0_NS) / 1e9
    for s, e in ev["dropouts_s"]:
        assert not np.any((t >= s) & (t < e))
    n_window = sum(int(round((e - s) * RATE)) for s, e in ev["dropouts_s"])
    n_kept = int(np.sum(t < ev["end_s"] + 1e-9))
    assert len(out) == n_kept
    assert ev["rows_dropped_missing"] == pytest.approx(n_window, abs=len(ev["dropouts_s"]))


@pytest.mark.parametrize("mode", ["zero", "stuck"])
def test_failure_modes(mode):
    cfg = degrade.DegradeConfig(failure_mode=mode, dropout_count=0)
    out, ev = degrade.degrade(_clean(), cfg, seed=5)
    t = (out.t_ns - T0_NS) / 1e9
    tail = t >= ev["failure_at_s"]
    assert tail.sum() == pytest.approx(5.0 * RATE, abs=1)
    if mode == "zero":
        assert np.all(out.gyro[tail] == 0) and np.all(out.accel[tail] == 0)
    else:
        first = np.argmax(tail)
        assert np.all(out.accel[tail] == out.accel[first - 1])


def test_noise_rises_and_healthy_phase_is_untouched():
    cfg = degrade.DegradeConfig(dropout_count=0, gyro_bias_rw=0.0, accel_bias_rw=0.0,
                                gyro_noise_start=0.0, gyro_noise_end=0.05,
                                accel_noise_start=0.0, accel_noise_end=0.5, healthy_s=10.0)
    clean = _clean()
    out, ev = degrade.degrade(clean, cfg, seed=6)
    t = (out.t_ns - T0_NS) / 1e9
    res = out.accel[:, 0] - 9.8
    assert np.all(res[t < 10.0] == 0.0)
    early = (t > 10.0) & (t < 30.0)
    late = (t > ev["failure_at_s"] - 20.0) & (t < ev["failure_at_s"])
    assert np.std(res[late]) > 3 * np.std(res[early])
    assert np.std(res[late]) == pytest.approx(0.5 * 0.92, rel=0.15)   # ramp averages ~0.92 of end


def test_bias_drift_moves_the_mean():
    cfg = degrade.DegradeConfig(dropout_count=0, gyro_noise_end=0.0, accel_noise_end=0.0,
                                gyro_bias_rw=0.0, accel_bias_rw=0.0,
                                gyro_bias_rate=1e-3, accel_bias_rate=1e-2, healthy_s=10.0)
    out, ev = degrade.degrade(_clean(), cfg, seed=0)
    t = (out.t_ns - T0_NS) / 1e9
    i = np.searchsorted(t, 50.0)
    assert out.accel[i, 0] - 9.8 == pytest.approx(1e-2 * (t[i] - 10.0))
    assert out.gyro[i, 2] - 0.03 == pytest.approx(1e-3 * (t[i] - 10.0))


def test_duplicates_and_swaps_are_recorded():
    cfg = degrade.DegradeConfig(dropout_count=0, duplicate_rows=3, swap_rows=2)
    out, ev = degrade.degrade(_clean(), cfg, seed=9)
    assert len(ev["duplicated_rows"]) == 3 and len(ev["swapped_rows"]) == 2
    d = np.diff(out.t_ns)
    assert np.sum(d == 0) == 3 and np.sum(d < 0) == 2


def test_impossible_config_raises():
    with pytest.raises(ValueError):
        degrade.degrade(_clean(seconds=20.0), degrade.DegradeConfig(dropout_count=10), seed=0)


def test_cli_writes_layout_and_events(tmp_path):
    src = tmp_path / "clean.csv"
    euroc.write_imu_csv(_clean(seconds=60.0), src)
    out_dir = tmp_path / "deg"
    assert degrade.main([str(src), str(out_dir), "--seed", "2", "--dropout-mode", "missing",
                         "--nan-text", ""]) == 0
    raw = euroc.read_imu_csv(out_dir / "mav0" / "imu0" / "data.csv")
    ev = json.loads((out_dir / "degrade.json").read_text())
    assert ev["seed"] == 2 and ev["config"]["dropout_mode"] == "missing"
    assert len(raw) == ev["rows_out"]

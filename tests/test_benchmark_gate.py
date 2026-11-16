"""benchmark.py: IMU seconds from timestamps, and the gate's RSS / time limits (no processes run here)."""

import benchmark


def _imu(tmp_path, ts, bom=False):
    p = tmp_path / "imu.csv"
    body = "#timestamp [ns],wx,wy,wz,ax,ay,az\n" + "".join("%s,0,0,0,0,0,9.81\n" % t for t in ts)
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + body.encode())
    return str(p)


def test_imu_seconds_from_timestamps_200hz(tmp_path):
    s, src = benchmark.imu_seconds(_imu(tmp_path, [1403636579758555392 + 5000000 * i for i in range(2000)]))
    assert src == "timestamps" and abs(s - 10.0) < 1e-9


def test_imu_seconds_not_rows_over_200_at_other_rates(tmp_path):
    # 100 Hz: rows / 200 would say 5 s for 10 s of data
    s, _ = benchmark.imu_seconds(_imu(tmp_path, [10 ** 18 + 10_000_000 * i for i in range(1000)]))
    assert abs(s - 10.0) < 1e-9


def test_imu_seconds_bom_and_bad_timestamps(tmp_path):
    ts = [10 ** 18 + 5_000_000 * i for i in range(400)]
    s, src = benchmark.imu_seconds(_imu(tmp_path, ts, bom=True))     # BOM before the first timestamp
    assert src == "timestamps" and abs(s - 2.0) < 1e-9
    ts[7] = "garbage"                                                  # skipped; the span is unchanged
    s, _ = benchmark.imu_seconds(_imu(tmp_path, ts))
    assert abs(s - 1.995 * 399 / 398) < 1e-9


def test_imu_seconds_falls_back_to_rows(tmp_path):
    s, src = benchmark.imu_seconds(_imu(tmp_path, ["x"] * 400))
    assert s == 2.0 and src.startswith("rows / 200")


def _res(rss_max, wall_ms_per_s=2.0, us=10.0):
    return {"process": [{"us_per_row": us, "wall_ms_per_imu_s": wall_ms_per_s,
                         "peak_rss_mb_median": rss_max - 0.1, "peak_rss_mb_max": rss_max}],
            "tracemalloc_peak_kb": 500.0, "output_check": "PASS"}


def test_gate_rss_uses_decimal_8mb_on_the_worst_run():
    assert benchmark.gate(_res(7.6)) == []                     # 7.97e6 bytes
    fails = benchmark.gate(_res(7.65))                         # 8.02e6 bytes: over 8,000,000
    assert len(fails) == 1 and "peak RSS" in fails[0]
    assert benchmark.gate(_res(11.95), rss=False) == []        # --allow-rss skips only RSS


def test_gate_compute_budget_per_imu_second():
    fails = benchmark.gate(_res(7.0, wall_ms_per_s=21.0))
    assert len(fails) == 1 and "ms per IMU-s" in fails[0]


def test_gate_c_core_uses_the_same_rss_rule_and_allow_rss_does_not_skip_it():
    res = _res(7.0)
    res["ccore"] = {"us_per_row": 1.0, "wall_ms_per_imu_s": 0.5, "peak_rss_mb_median": 7.5,
                    "peak_rss_mb_max": 7.65, "output_identical_to_main_py": True, "output_check": "PASS"}
    for rss in (True, False):
        fails = benchmark.gate(res, rss=rss)
        assert len(fails) == 1 and fails[0].startswith("C core peak RSS")
    res["ccore"]["peak_rss_mb_max"] = 4.3
    assert benchmark.gate(res) == []

"""benchmark.py: IMU seconds from timestamps, the gate's heap / time limits, and the whole-run heap probe."""

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


def _res(rss_max=11.9, wall_ms_per_s=2.0, us=10.0, heap_kb=500.0, heap_proc_kb=None):
    r = {"process": [{"us_per_row": us, "wall_ms_per_imu_s": wall_ms_per_s,
                      "peak_rss_mb_median": rss_max - 0.1, "peak_rss_mb_max": rss_max}],
         "tracemalloc_peak_kb": heap_kb, "output_check": "PASS"}
    if heap_proc_kb is not None:
        r["tracemalloc_process_peak_kb"] = heap_proc_kb
    return r


def test_gate_ignores_process_rss_since_the_faq():
    # FAQ 17 Nov 2026: 8 MB is measured at heap level, the interpreter's RSS does not count
    assert benchmark.gate(_res(rss_max=15.0)) == []
    assert benchmark.gate(_res(rss_max=15.0), rss=True) == []        # old keyword accepted, ignored


def test_gate_heap_target_and_limit_use_the_larger_reading():
    assert benchmark.gate(_res(heap_kb=3000.0, heap_proc_kb=3500.0)) == []
    fails = benchmark.gate(_res(heap_kb=3000.0, heap_proc_kb=4200.0))        # whole run above 4 MB target
    assert len(fails) == 1 and "design target" in fails[0]
    fails = benchmark.gate(_res(heap_kb=7900.0))                             # 8,089,600 bytes > 8,000,000
    assert len(fails) == 1 and "8 MB limit" in fails[0]


def test_gate_compute_budget_per_imu_second():
    fails = benchmark.gate(_res(wall_ms_per_s=21.0))
    assert len(fails) == 1 and "ms per IMU-s" in fails[0]


def test_gate_does_not_judge_the_c_core():
    res = _res()
    res["ccore"] = {"us_per_row": 1.0, "wall_ms_per_imu_s": 0.5, "peak_rss_mb_median": 7.5,
                    "peak_rss_mb_max": 9.0, "output_identical_to_main_py": False, "output_check": "FAIL"}
    assert benchmark.gate(res) == []


def test_gate_holds_the_no_bytecode_reading_to_8mb_only():
    assert benchmark.gate(_res(heap_proc_kb=600.0) | {"tracemalloc_process_nocache_peak_kb": 4500.0}) == []
    fails = benchmark.gate(_res(heap_proc_kb=600.0) | {"tracemalloc_process_nocache_peak_kb": 7900.0})
    assert len(fails) == 1 and "without cached bytecode" in fails[0]


def test_heap_probe_runs_main_py_whole(tmp_path):
    """The probe traces the whole run: the output is complete, and compiling pathfinder.py while traced
    (no cached bytecode) costs heap that loading its bytecode does not."""
    imu = _imu(tmp_path, [10 ** 18 + 5_000_000 * i for i in range(2000)])
    out = tmp_path / "out.txt"
    stub = benchmark.os.path.join(benchmark.ROOT, "main.py")
    cold, code_c = benchmark.heap_peak_process(stub, imu, str(out), no_cache_dir=str(tmp_path / "nocache"))
    assert code_c == 0 and len(out.read_text().splitlines()) == 2000
    assert 0 < cold < 8_000_000

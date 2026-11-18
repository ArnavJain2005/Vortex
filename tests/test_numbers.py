"""tools/make_numbers.py: Docs/NUMBERS.md is generated from committed result files. Values on SYNTHETIC result
files are checked by hand; the committed Docs/NUMBERS.md must match what its sources give."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("make_numbers", ROOT / "tools" / "make_numbers.py")
mn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mn)


def _off(tag, apes, date="2026-11-20"):
    """apes: {(base, reading, seed): ape}; gap = ape + 1, blind = ape + 2, rpe = ape / 10."""
    res = [{"sequence": "%s_%s_s%d" % (b, r, s), "base": b, "reading": r, "seed": s, "ape_se3_rmse": a,
            "gap_rmse_mean": a + 1.0, "blind_rmse": a + 2.0, "rpe200_rmse": a / 10.0, "contract": "PASS"}
           for (b, r, s), a in apes.items()]
    return {"tag": tag, "date": date, "results": res}


def _clean(tag, apes, date="2026-11-20"):
    return {"tag": tag, "date": date, "results": [{"sequence": s, "ate_se3_rmse": a, "rpe200_rmse": a / 10.0,
                                                   "contract": "PASS"} for s, a in apes.items()]}


def _budget(tag):
    return {"date": "2026-11-20", "input": "real: ../data/official/MH_01_easy_b_s1/mav0/imu0/data.csv",
            "rows": 1000, "python": "3.14.7", "tracemalloc_peak_kb": 500.4, "tracemalloc_process_peak_kb": 1000.6,
            "tracemalloc_process_nocache_peak_kb": 4900.0,
            "process": [{"case": "python -S main.py", "us_per_row": 12.345, "cpu_ms_per_imu_s": 2.5,
                         "wall_ms_per_imu_s": 2.75}]}


@pytest.fixture
def docs(tmp_path, monkeypatch):
    est = {("MH_03_medium", "a", 4): 6.0, ("MH_03_medium", "b", 4): 2.0,
           ("V1_01_easy", "a", 4): 3.0, ("V1_01_easy", "b", 4): 3.0}
    flo = {("MH_03_medium", "a", 4): 3.0, ("MH_03_medium", "b", 4): 3.0,
           ("V1_01_easy", "a", 4): 4.0, ("V1_01_easy", "b", 4): 4.0}
    tum = {("dataset-room1_512_16", "a", 1): 2.0, ("dataset-room3_512_16", "b", 1): 4.0}
    tumf = {("dataset-room1_512_16", "a", 1): 1.0, ("dataset-room3_512_16", "b", 1): 1.0}
    files = {
        "results/H": _off("H", est), "results/Hf": _off("Hf", flo),
        "results/H2": _off("H2", est), "results/H2f": _off("H2f", flo),
        "results/C": _clean("C", {"MH_01_easy": 2.0, "V1_01_easy": 5.0}),
        "results/Cf": _clean("Cf", {"MH_01_easy": 3.0, "V1_01_easy": 4.0}),
        "tumvi/T": _off("T", tum), "tumvi/Tf": _off("Tf", tumf),
        "tumvi/TC": _clean("TC", {"dataset-room1_512_16": 1.0}), "tumvi/TCf": _clean("TCf", {"dataset-room1_512_16": 2.0}),
        "tumvi/cal": {"clean": {"r1": {"calibrated": True, "zupt_ticks": 3}, "r2": {"calibrated": False, "zupt_ticks": 0}},
                      "official": {"x": {"calibrated": False, "zupt_ticks": 0}}},
        "budget/B": _budget("B"), "budget/B3": _budget("B3"),
    }
    for k, v in files.items():
        p = tmp_path / (k + ".json")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(v), encoding="utf-8")
    monkeypatch.setattr(mn, "DOCS", str(tmp_path))
    monkeypatch.setattr(mn, "PYTEST_JSON", str(tmp_path / "numbers" / "pytest.json"))
    monkeypatch.setattr(mn, "SOURCES", {
        "heldout": ("results/H", "results/Hf", "x"), "heldout79": ("results/H2", "results/H2f", "y"),
        "clean": ("results/C", "results/Cf", "c"), "tumvi": ("tumvi/T", "tumvi/Tf", "t"),
        "tumvi_clean": ("tumvi/TC", "tumvi/TCf", "tc"), "tumvi_calib": "tumvi/cal",
        "budget": "budget/B", "budget313": "budget/B3"})
    return tmp_path


def _values(t):
    return {k: (v, s, d) for k, v, s, d in t.rows}


def test_values_on_synthetic_results(docs):
    v = _values(mn.build())
    assert v["heldout_ape_m"][0] == "3.500"                       # (6 + 2 + 3 + 3) / 4
    assert v["heldout_ape_floor_m"][0] == "3.500"
    assert v["heldout_ape_vs_floor_pct"][0] == "+0.0"
    assert v["heldout_a_ape_m"][0] == "4.500" and v["heldout_a_ape_floor_m"][0] == "3.500"
    assert v["heldout_a_ape_vs_floor_pct"][0] == "+28.6"
    assert v["heldout_b_blind_m"][0] == "4.500"                   # ape + 2
    assert v["heldout_rpe1s_m"][0] == "0.350"
    # pooled per sequence: MH_03 4.0 vs 3.0 (worse), V1_01 3.0 vs 4.0 (better)
    assert v["heldout_seqs_beat_floor_n"][0] == "1/2"
    assert v["heldout_b_seqs_beat_floor_n"][0] == "2/2"
    assert v["heldout_mh03_a_ape_m"][0] == "6.000" and v["heldout_v101_b_ape_floor_m"][0] == "4.000"
    assert v["heldout_copies_n"][0] == "4" and v["heldout_contract_pass_n"][0] == "4/4"
    assert v["heldout_ape_m"][1:] == ("H vs Hf", "2026-11-20")
    assert "heldout79_mh03_a_ape_m" not in v                      # per-sequence keys only for the headline set
    assert v["clean_ape_m"][0] == "3.500" and v["clean_seqs_beat_floor_n"][0] == "1/2"
    assert v["tumvi_room12_ape_m"][0] == "2.000" and v["tumvi_room34_ape_floor_m"][0] == "1.000"
    assert v["tumvi_clean_room12_seqs_n"][0] == "1"
    assert v["tumvi_calib_clean_calibrated_n"][0] == "1/2" and v["tumvi_calib_official_zupt_any_n"][0] == "0/1"
    assert v["budget_heap_kb"][0] == "500" and v["budget_heap_no_bytecode_kb"][0] == "4900"
    assert v["budget_us_per_row_us"][0] == "12.3" and v["budget_cpu_ms_per_imu_s_ms"][0] == "2.50"
    assert v["budget_input"][0] == "official/MH_01_easy_b_s1/mav0/imu0/data.csv"
    assert "pytest_passed_n" not in v                             # no pytest record: no key, never a guess
    assert v["experiments_off_n"][0] == str(len(mn.OFF))


def test_pytest_record_and_render(docs):
    (docs / "numbers").mkdir()
    (docs / "numbers" / "pytest.json").write_text(json.dumps(
        {"passed": 321, "failed": 0, "skipped": 2, "python": "3.14.7", "platform": "Windows 11",
         "commit": "abc1234", "date": "2026-11-20"}), encoding="utf-8")
    t = mn.build()
    v = _values(t)
    assert v["pytest_passed_n"] == ("321", "pytest Windows 11, Python 3.14.7, commit abc1234", "2026-11-20")
    md = mn.render(t)
    assert "| `heldout_ape_m` | 3.500 | H vs Hf | 2026-11-20 |" in md
    keys = [r[0] for r in t.rows]
    assert len(keys) == len(set(keys))


def test_committed_numbers_match_their_sources():
    assert mn.main(["--check"]) == 0

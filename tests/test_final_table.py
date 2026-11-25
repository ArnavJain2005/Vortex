"""tools/final_table.py on SYNTHETIC result files (the real final table runs only on Arnav's word)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("final_table", ROOT / "tools" / "final_table.py")
ft = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ft)


def _res(tag, apes, contract="PASS"):
    """apes: {(base, reading, seed): ape}; gap = ape + 1, blind = ape / 2."""
    return {"tag": tag, "commit": "abc1234", "main": "src/main.py", "python": "3.14.7", "date": "2026-11-22",
            "results": [{"sequence": "%s_%s_s%d" % (b, r, s), "base": b, "reading": r, "seed": s,
                         "ape_se3_rmse": a, "gap_rmse_mean": a + 1.0, "blind_rmse": a / 2.0, "contract": contract}
                        for (b, r, s), a in apes.items()]}


def test_pooled_per_sequence_and_errors():
    est = _res("E", {("V2_01_easy", "a", 1): 2.0, ("V2_01_easy", "b", 1): 4.0,
                     ("V2_02_medium", "a", 1): 1.0, ("V2_02_medium", "b", 1): 1.0})
    est["results"].append({"sequence": "V2_03_difficult_a_s1", "base": "V2_03_difficult", "reading": "a",
                           "seed": 1, "error": "boom"})
    flo = _res("F", {("V2_01_easy", "a", 1): 2.0, ("V2_01_easy", "b", 1): 2.0,
                     ("V2_02_medium", "a", 1): 2.0, ("V2_02_medium", "b", 1): 2.0,
                     ("V2_03_difficult", "a", 1): 2.0})
    md = ft.build(est, flo)
    assert "| All copies | 4 | 2.000 / 2.000 | +0.0 % |" in md              # (2 + 4 + 1 + 1) / 4
    assert "| V2_01_easy | 2 | 3.000 / 2.000 | +50.0 % |" in md
    assert "| V2_02_medium, reading b | 1 | 1.000 / 2.000 | -50.0 % |" in md
    assert "Sequences better than the floor on pooled APE: 1/2." in md
    assert "Output contract: 4/5 PASS." in md                                # the errored copy counts as not passing
    assert "NOT in the means): V2_03_difficult_a_s1." in md
    assert "| Reading a | 2 | 1.500 / 2.000 | -25.0 % | 2.500 / 3.000 | -16.7 % | 0.750 / 1.000 | -25.0 % |" in md

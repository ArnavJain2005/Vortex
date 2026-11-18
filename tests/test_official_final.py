"""The organiser-copy wrapper must require an explicit Vicon Room 2 release."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import official_degrade  # noqa: E402


def test_v2_requires_explicit_final():
    for name in ("V2_01_easy", "V2_02_medium", "V2_03_difficult"):
        with pytest.raises(SystemExit, match="final test set"):
            official_degrade.guard_final(name)
        official_degrade.guard_final(name, final=True)
    official_degrade.guard_final("MH_01_easy")


def test_cli_final_requires_named_sequences(monkeypatch, capsys):
    monkeypatch.setattr(official_degrade, "load_script", lambda: pytest.fail("must reject before load"))
    with pytest.raises(SystemExit, match="final test set"):
        official_degrade.main(["--all", "--seqs", "V2_01_easy", "--seeds", "42"])
    with pytest.raises(SystemExit) as exc:
        official_degrade.main(["--all", "--final"])
    assert exc.value.code == 2
    assert "requires explicit --seqs" in capsys.readouterr().err


def test_cli_runs_each_requested_copy_once_with_final(monkeypatch):
    calls = []
    monkeypatch.setattr(official_degrade, "load_script", lambda: object())

    def fake_make(seq_dir, reading, seed, *args, **kwargs):
        calls.append((os.path.basename(seq_dir), reading, seed, kwargs["final"]))
        return "copy", dict(rows_in=1, rows_out=1, spikes=0, stuck_samples=0, dropped_total=0,
                            dropped_burst_gaps=0, duplicated_rows=0, failure_frames=0,
                            timestamp_unit="ns", accel_unit="m/s2"), {}

    monkeypatch.setattr(official_degrade, "make_copy", fake_make)
    assert official_degrade.main(["--all", "--seqs", "V2_01_easy,V2_02_medium,V2_03_difficult",
                                  "--readings", "a,b", "--seeds", "42", "--final"]) == 0
    assert calls == [(seq, reading, 42, True)
                     for seq in ("V2_01_easy", "V2_02_medium", "V2_03_difficult")
                     for reading in ("a", "b")]

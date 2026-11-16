"""tools/eval_euroc.py: the final test set (Vicon Room 2) is never run by accident; the C core runner."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import eval_euroc  # noqa: E402


def test_default_selection_skips_vicon_room_2():
    names = ["V2_01_easy", "MH_01_easy", "V1_01_easy", "V2_03_difficult_s1"]
    assert eval_euroc.select(names, None, final=False) == ["MH_01_easy", "V1_01_easy"]
    assert eval_euroc.select(names, None, final=True) == ["MH_01_easy", "V1_01_easy"]


def test_naming_vicon_room_2_needs_final():
    with pytest.raises(SystemExit):
        eval_euroc.select([], ["V1_01_easy", "V2_01_easy"], final=False)
    with pytest.raises(SystemExit):
        eval_euroc.select([], ["V2_02_medium_s1"], final=False)
    assert eval_euroc.select([], ["V2_01_easy"], final=True) == ["V2_01_easy"]
    assert eval_euroc.select([], ["MH_03_medium", "V1_02_medium"], final=False) == ["MH_03_medium", "V1_02_medium"]


def test_command_python_and_c_core():
    assert eval_euroc.command("main.py", "in.csv", "out.txt") == [sys.executable, "-S", "main.py", "in.csv", "out.txt"]
    assert eval_euroc.command(eval_euroc.CBIN + "build/vortex.exe", "in.csv", "out.txt") == [
        "build/vortex.exe", "in.csv", "out.txt"]

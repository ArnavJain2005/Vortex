"""Tests for tools/assemble_video.py."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import assemble_video as av  # noqa: E402

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def test_parse_clip_list_text_and_json(tmp_path: Path):
    c1 = tmp_path / "a.mp4"
    c2 = tmp_path / "b.mp4"
    c1.write_bytes(b"")
    c2.write_bytes(b"")

    txt = tmp_path / "clips.txt"
    txt.write_text("# header comment\n\na.mp4\n  b.mp4  \n", encoding="utf-8")
    specs = av.parse_clip_list(txt)
    assert [s.path for s in specs] == [c1.resolve(), c2.resolve()]
    assert all(s.start is None and s.duration is None for s in specs)

    js = tmp_path / "clips.json"
    js.write_text(
        json.dumps({"clips": ["a.mp4", {"path": "b.mp4", "start": 1.0, "duration": 2.5}]}),
        encoding="utf-8",
    )
    jspecs = av.parse_clip_list(js)
    assert len(jspecs) == 2
    assert jspecs[0].path == c1.resolve()
    assert jspecs[1].path == c2.resolve()
    assert jspecs[1].start == 1.0
    assert jspecs[1].duration == 2.5


def test_check_duration_limit():
    av.check_duration_limit(165.0)
    av.check_duration_limit(180.0)
    with pytest.raises(ValueError, match="exceeds maximum"):
        av.check_duration_limit(180.5)
    assert av.fmt_mmss(165.0) == "2:45.00"
    assert av.fmt_mmss(180.0) == "3:00.00"


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_assemble_end_to_end_and_length_cap(tmp_path: Path):
    clip1 = tmp_path / "c1.mp4"
    clip2 = tmp_path / "c2.mp4"
    vo = tmp_path / "silent.wav"
    subs = tmp_path / "subs.srt"

    for dst, color in [(clip1, "0x111827"), (clip2, "0x1e293b")]:
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x180:d=1.5:r=15",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dst),
            ],
            check=True,
            capture_output=True,
        )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "3.0", str(vo)],
        check=True,
        capture_output=True,
    )
    subs.write_text(
        "1\n00:00:00,000 --> 00:00:01,500\nClip one.\n\n2\n00:00:01,500 --> 00:00:03,000\nClip two.\n",
        encoding="utf-8",
    )

    clip_list = tmp_path / "clips.txt"
    clip_list.write_text("c1.mp4\nc2.mp4\n", encoding="utf-8")
    out_mp4 = tmp_path / "assembled.mp4"

    # Dry-run succeeds without creating output
    rc_dry = av.main(["--clips", str(clip_list), "--voiceover", str(vo), "--captions", str(subs), "-o", str(out_mp4), "--dry-run"])
    assert rc_dry == 0
    assert not out_mp4.exists()

    # Real assembly succeeds and probes valid streams & duration
    rc_ok = av.main([
        "--clips", str(clip_list), "--voiceover", str(vo), "--captions", str(subs),
        "-o", str(out_mp4), "--width", "320", "--height", "180", "--fps", "15", "--preset", "ultrafast",
    ])
    assert rc_ok == 0
    assert out_mp4.is_file()
    info = av.probe_media(out_mp4)
    assert info["has_video"] and info["has_audio"] and info["has_subtitle"]
    assert 2.8 <= info["duration_s"] <= 3.3

    # Exceeding max-duration MUST fail (exit 1)
    out_fail = tmp_path / "should_fail.mp4"
    rc_fail = av.main([
        "--clips", str(clip_list), "--voiceover", str(vo), "--captions", str(subs),
        "-o", str(out_fail), "--max-duration", "2.0",
    ])
    assert rc_fail == 1
    assert not out_fail.exists()

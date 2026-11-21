"""Assemble submission video from a clip list, voice-over audio, and captions into one MP4.

Standard library only; invokes `ffmpeg` and `ffprobe` on PATH.
Enforces the Track 3 video length limit using `ffprobe`:
  - Target duration: 2:45 (165.0 s)
  - Hard limit:      3:00 (180.0 s) — fails with exit code 1 if exceeded (checked both
    before encoding and on the assembled MP4 output).

Clip list formats accepted by `--clips`:
  1. Plain text file: one video file path per line (blank lines and `#` comments ignored).
  2. JSON file: either a list of strings/objects or `{"clips": [...]}` where each object
     has `{"path": "...", "start": 0.0, "duration": 10.0}` (`start` and `duration` optional).
Relative clip paths are resolved relative to the clip list file's directory (falling back
to the current working directory).

Usage:
    python tools/assemble_video.py --clips clips.txt --voiceover vo.wav --captions subs.srt -o out.mp4
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

TARGET_DURATION_S = 165.0  # 2:45
MAX_DURATION_S = 180.0     # 3:00 hard cap


@dataclass
class ClipSpec:
    path: Path
    start: float | None = None
    duration: float | None = None


def require_tool(name: str) -> str:
    exe = shutil.which(name)
    if not exe:
        raise RuntimeError(f"Required tool {name!r} was not found on PATH.")
    return exe


def probe_media(path: Path, ffprobe_exe: str | None = None) -> dict:
    """Inspect a media file using ffprobe and return duration, streams, and format metadata."""
    ffprobe = ffprobe_exe or require_tool("ffprobe")
    if not path.is_file():
        raise FileNotFoundError(f"Media file not found: {path}")
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
        "-of", "json",
        str(path),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {p.stderr.strip()}")
    data = json.loads(p.stdout)
    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    dur_raw = fmt.get("duration")
    if dur_raw is None:
        raise RuntimeError(f"ffprobe reported no duration for {path}")
    duration_s = float(dur_raw)
    if duration_s <= 0.0:
        raise RuntimeError(f"Media file has non-positive duration ({duration_s}s): {path}")
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]
    return {
        "path": str(path),
        "duration_s": duration_s,
        "size_bytes": int(fmt.get("size", path.stat().st_size)),
        "has_video": bool(video_streams),
        "has_audio": bool(audio_streams),
        "has_subtitle": bool(subtitle_streams),
        "video": video_streams[0] if video_streams else None,
        "audio": audio_streams[0] if audio_streams else None,
    }


def _resolve_clip_path(raw: str, base_dir: Path) -> Path:
    p = Path(raw)
    if p.is_absolute():
        return p
    cand = (base_dir / p).resolve()
    if cand.exists():
        return cand
    return p.resolve()


def parse_clip_list(clip_list_path: Path) -> list[ClipSpec]:
    """Parse a text or JSON clip list into validated ClipSpec entries."""
    if not clip_list_path.is_file():
        raise FileNotFoundError(f"Clip list not found: {clip_list_path}")
    base_dir = clip_list_path.resolve().parent
    raw_text = clip_list_path.read_text(encoding="utf-8-sig")

    entries: list[ClipSpec] = []
    if clip_list_path.suffix.lower() == ".json":
        obj = json.loads(raw_text)
        items = obj["clips"] if isinstance(obj, dict) else obj
        if not isinstance(items, list):
            raise ValueError("JSON clip list must be a list or an object with a 'clips' list.")
        for idx, item in enumerate(items):
            if isinstance(item, str):
                entries.append(ClipSpec(path=_resolve_clip_path(item, base_dir)))
            elif isinstance(item, dict) and "path" in item:
                start = float(item["start"]) if item.get("start") is not None else None
                dur = float(item["duration"]) if item.get("duration") is not None else None
                if start is not None and start < 0:
                    raise ValueError(f"Clip #{idx + 1} has negative start: {start}")
                if dur is not None and dur <= 0:
                    raise ValueError(f"Clip #{idx + 1} has non-positive duration: {dur}")
                entries.append(ClipSpec(path=_resolve_clip_path(str(item["path"]), base_dir), start=start, duration=dur))
            else:
                raise ValueError(f"Invalid clip entry #{idx + 1}: expected string or object with 'path'.")
    else:
        for line in raw_text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            entries.append(ClipSpec(path=_resolve_clip_path(s, base_dir)))

    if not entries:
        raise ValueError(f"Clip list is empty: {clip_list_path}")
    return entries


def validate_captions(captions_path: Path) -> Path:
    if not captions_path.is_file():
        raise FileNotFoundError(f"Captions file not found: {captions_path}")
    if captions_path.suffix.lower() not in (".srt", ".vtt"):
        raise ValueError(f"Unsupported captions extension {captions_path.suffix!r}; expected .srt or .vtt")
    text = captions_path.read_text(encoding="utf-8-sig").strip()
    if not text:
        raise ValueError(f"Captions file is empty: {captions_path}")
    return captions_path.resolve()


def _escape_ffmpeg_filter_path(path: Path) -> str:
    """Escape a filesystem path for ffmpeg's subtitles filter (handles Windows drive colons)."""
    s = path.resolve().as_posix()
    s = s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return s


def fmt_mmss(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds - 60 * m
    return f"{m}:{s:05.2f}"


def check_duration_limit(duration_s: float, max_duration_s: float = MAX_DURATION_S, label: str = "output") -> None:
    if duration_s > max_duration_s + 1e-3:
        raise ValueError(
            f"{label} duration {duration_s:.2f}s ({fmt_mmss(duration_s)}) exceeds maximum allowed "
            f"{max_duration_s:.2f}s ({fmt_mmss(max_duration_s)})"
        )


def assemble_video(
    clips_path: Path,
    voiceover_path: Path,
    captions_path: Path,
    output_path: Path,
    *,
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
    crf: int = 20,
    preset: str = "medium",
    captions_mode: str = "soft",
    max_duration_s: float = MAX_DURATION_S,
    target_duration_s: float = TARGET_DURATION_S,
    dry_run: bool = False,
) -> dict:
    """Validate inputs, enforce duration limits via ffprobe, assemble MP4, and re-verify output."""
    if captions_mode not in ("soft", "burn"):
        raise ValueError(f"captions_mode must be 'soft' or 'burn', got {captions_mode!r}")

    ffprobe = require_tool("ffprobe")
    ffmpeg = None if dry_run else require_tool("ffmpeg")

    clips = parse_clip_list(clips_path)
    captions = validate_captions(captions_path)
    vo_info = probe_media(voiceover_path.resolve(), ffprobe_exe=ffprobe)
    if not vo_info["has_audio"]:
        raise ValueError(f"Voice-over file has no audio stream: {voiceover_path}")

    clip_infos = []
    total_video_s = 0.0
    for idx, c in enumerate(clips):
        info = probe_media(c.path, ffprobe_exe=ffprobe)
        if not info["has_video"]:
            raise ValueError(f"Clip #{idx + 1} has no video stream: {c.path}")
        avail = info["duration_s"] - (c.start or 0.0)
        if avail <= 0.0:
            raise ValueError(f"Clip #{idx + 1} start ({c.start}s) is past end ({info['duration_s']:.2f}s): {c.path}")
        eff_dur = min(avail, c.duration) if c.duration is not None else avail
        total_video_s += eff_dur
        clip_infos.append({
            "path": str(c.path),
            "source_duration_s": round(info["duration_s"], 3),
            "effective_duration_s": round(eff_dur, 3),
            "start": c.start,
            "duration": c.duration,
        })

    expected_duration_s = max(total_video_s, vo_info["duration_s"])
    check_duration_limit(total_video_s, max_duration_s, label="concatenated clips")
    check_duration_limit(vo_info["duration_s"], max_duration_s, label="voice-over")
    check_duration_limit(expected_duration_s, max_duration_s, label="planned assembly")

    over_target = expected_duration_s > target_duration_s
    summary = {
        "clips_count": len(clips),
        "clips": clip_infos,
        "total_video_s": round(total_video_s, 3),
        "voiceover_s": round(vo_info["duration_s"], 3),
        "expected_duration_s": round(expected_duration_s, 3),
        "target_duration_s": target_duration_s,
        "max_duration_s": max_duration_s,
        "over_target": over_target,
        "captions": str(captions),
        "captions_mode": captions_mode,
        "output": str(output_path.resolve()),
        "dry_run": dry_run,
    }
    if dry_run:
        return summary

    assert ffmpeg is not None
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = [ffmpeg, "-y"]
    filter_parts: list[str] = []
    for i, c in enumerate(clips):
        if c.start is not None:
            cmd += ["-ss", f"{c.start:.3f}"]
        if c.duration is not None:
            cmd += ["-t", f"{c.duration:.3f}"]
        cmd += ["-i", str(c.path)]
        filter_parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={fps},format=yuv420p[v{i}]"
        )

    vo_idx = len(clips)
    cmd += ["-i", str(voiceover_path.resolve())]

    sub_idx = None
    if captions_mode == "soft":
        sub_idx = vo_idx + 1
        cmd += ["-i", str(captions)]

    concat_inputs = "".join(f"[v{i}]" for i in range(len(clips)))
    if captions_mode == "burn":
        esc = _escape_ffmpeg_filter_path(captions)
        filter_parts.append(f"{concat_inputs}concat=n={len(clips)}:v=1:a=0[vcat]")
        filter_parts.append(f"[vcat]subtitles='{esc}'[vout]")
    else:
        filter_parts.append(f"{concat_inputs}concat=n={len(clips)}:v=1:a=0[vout]")

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[vout]",
        "-map", f"{vo_idx}:a:0",
    ]
    if sub_idx is not None:
        cmd += ["-map", f"{sub_idx}:0", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng"]

    cmd += [
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", str(crf),
        "-preset", preset,
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path.resolve()),
    ]

    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg assembly failed (rc={p.returncode}): {p.stderr[-800:]}")

    out_info = probe_media(output_path.resolve(), ffprobe_exe=ffprobe)
    try:
        check_duration_limit(out_info["duration_s"], max_duration_s, label="assembled MP4")
    except ValueError:
        output_path.unlink(missing_ok=True)
        raise

    summary["output_probe"] = out_info
    summary["output_duration_s"] = round(out_info["duration_s"], 3)
    summary["over_target"] = out_info["duration_s"] > target_duration_s
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Assemble clips, voice-over, and captions into one MP4 (max 3:00).")
    ap.add_argument("--clips", required=True, help="Clip list file (.txt or .json)")
    ap.add_argument("--voiceover", required=True, help="Voice-over audio file (.wav, .mp3, .m4a, .aac)")
    ap.add_argument("--captions", required=True, help="Captions file (.srt or .vtt)")
    ap.add_argument("-o", "--output", required=True, help="Output MP4 file path")
    ap.add_argument("--width", type=int, default=1280, help="Output width in pixels (default: 1280)")
    ap.add_argument("--height", type=int, default=720, help="Output height in pixels (default: 720)")
    ap.add_argument("--fps", type=int, default=30, help="Output frame rate (default: 30)")
    ap.add_argument("--crf", type=int, default=20, help="H.264 CRF quality (default: 20)")
    ap.add_argument("--preset", default="medium", help="x264 preset (default: medium)")
    ap.add_argument("--captions-mode", choices=("soft", "burn"), default="soft",
                    help="Embed captions as mov_text track ('soft', default) or hard-burn ('burn')")
    ap.add_argument("--target-duration", type=float, default=TARGET_DURATION_S,
                    help="Target duration in seconds (default: 165.0 = 2:45)")
    ap.add_argument("--max-duration", type=float, default=MAX_DURATION_S,
                    help="Hard maximum duration in seconds (default: 180.0 = 3:00)")
    ap.add_argument("--dry-run", action="store_true", help="Probe inputs and verify limits without encoding")
    ap.add_argument("--json", action="store_true", help="Print machine-readable JSON summary")
    args = ap.parse_args(argv)

    try:
        res = assemble_video(
            Path(args.clips),
            Path(args.voiceover),
            Path(args.captions),
            Path(args.output),
            width=args.width,
            height=args.height,
            fps=args.fps,
            crf=args.crf,
            preset=args.preset,
            captions_mode=args.captions_mode,
            max_duration_s=args.max_duration,
            target_duration_s=args.target_duration,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        sys.stderr.write(f"assemble_video: ERROR: {exc}\n")
        return 1

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        dur = res.get("output_duration_s", res["expected_duration_s"])
        status = "DRY-RUN PASS" if res["dry_run"] else "PASS"
        note = " (above 2:45 target, within 3:00 limit)" if res["over_target"] else " (within 2:45 target)"
        print(
            f"{status}: {res['output']} | clips={res['clips_count']} | "
            f"duration={dur:.2f}s ({fmt_mmss(dur)}) / limit {fmt_mmss(res['max_duration_s'])}{note}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

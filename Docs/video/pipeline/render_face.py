"""Render the cut camera track as a 720x720 square (face crop), frame-locked to the voice timeline.
Each timeline frame f maps to source time src_in + (f/30 - tl_start) inside its segment, so lip
sync stays within half a frame across all 41 cuts. Holds freeze the last frame for their length."""
import json, subprocess, os
FPS = 30
AV = json.load(open("work/av_timeline.json")); FC = json.load(open("work/facecrop.json"))
os.makedirs("work/face_parts", exist_ok=True)
segs = AV["segs"]; total = AV["total"]
bounds = [round(s["tl_start"] * FPS) for s in segs] + [round(total * FPS) + 45]  # +1.5 s tail for the end hold
pieces = []

K = 1920 / 848  # originals are 1920x1080; face boxes were measured on the 848x478 copies
def crop_filter(c):
    f = FC[c]; side = min(1080, 1.9 * f["face_w"] * K); cx, cy = f["cx"] * K, (f["cy"] - 0.06 * f["face_w"]) * K
    x = min(max(0, cx - side / 2), 1920 - side); y = min(max(0, cy - side / 2), 1080 - side)
    return (f"crop={side:.0f}:{side:.0f}:{x:.0f}:{y:.0f},scale=720:720:flags=lanczos,"
            f"eq=contrast=1.04:brightness=0.015:saturation=0.96:gamma=1.03,setsar=1")

def piece(c, src_t, nframes, out, freeze=0):
    vf = crop_filter(c) + f",fps={FPS}"
    if freeze: vf += f",tpad=stop_mode=clone:stop={freeze}"
    vf += f",setpts=N/({FPS}*TB)"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f"talking-head/orig/{c}.mp4", "-ss", f"{max(0, src_t):.4f}",
                    "-vf", vf, "-frames:v", str(nframes + freeze), "-an", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "12", "-pix_fmt", "yuv420p", "-g", "30", "-r", str(FPS), out], check=True)
    pieces.append(out)

for k, s in enumerate(segs):
    f0, f1 = bounds[k], bounds[k + 1]; c = s["clip"]
    src0 = s["src_in"] + (f0 / FPS - s["tl_start"])
    if s["holds"]:
        h = s["holds"][0]; hf = round((s["tl_start"] + (h["at"] - s["src_in"])) * FPS); add = round(h["add"] * FPS)
        if h["at"] >= s["src_out"] - 0.1:   # join hold at the clip's end: play, then freeze the last calm frame
            piece(c, src0, f1 - f0 - add, f"work/face_parts/p{k:02d}.mp4", freeze=add); continue
        piece(c, src0, hf - f0, f"work/face_parts/p{k:02d}a.mp4", freeze=add)
        piece(c, h["at"] + 1 / FPS, f1 - hf - add, f"work/face_parts/p{k:02d}b.mp4")
    else:
        piece(c, src0, f1 - f0, f"work/face_parts/p{k:02d}.mp4")
open("work/face_parts/list.txt", "w").write("".join(f"file '{os.path.basename(p)}'\n" for p in pieces))
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", "work/face_parts/list.txt",
                "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-g", "15", "-pix_fmt", "yuv420p",
                "work/face_cut.mp4"], check=True)
json.dump(dict(cut_frames=bounds[:-1], fps=FPS, total=total), open("work/face_cuts.json", "w"))
print("frames", bounds[-1], "pieces", len(pieces))

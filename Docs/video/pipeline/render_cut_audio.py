"""Render the cut voice track from work/cutlist.json (48 kHz mono, 10 ms crossfades at cuts,
cuts nudged to the nearest zero crossing), insert room tone for padded emphasis pauses,
and write work/seams.txt + work/seams_check.wav (+-0.5 s around each seam, beeps between)."""
import json, subprocess, numpy as np, wave

SR = 48000
CL = json.load(open("work/cutlist.json"))

def load(clip):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", f"talking-head/{clip}.mp4", "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()

cache = {}
def audio(c):
    if c not in cache: cache[c] = load(c)
    return cache[c]

def zc(x, i, w=240):  # nearest zero crossing within +-5 ms
    a, b = max(1, i - w), min(len(x) - 1, i + w)
    seg = x[a:b]; s = np.where(np.sign(seg[:-1]) != np.sign(seg[1:]))[0]
    return a + int(s[np.argmin(np.abs(s + a - i))]) if len(s) else i

# room tone: quietest 0.6 s of c05 (between phrases)
x5 = audio("c05"); win = int(1.3 * SR)
rms = [np.sqrt(np.mean(x5[i:i + win] ** 2)) for i in range(0, len(x5) - win, SR // 20)]
rt0 = int(np.argmin(rms)) * SR // 20; room = x5[rt0:rt0 + win]

XF = int(0.010 * SR)
pieces, seams, t = [], [], 0
for k, s in enumerate(CL["segments"]):
    x = audio(s["clip"]); a = zc(x, int(s["in"] * SR)); b = zc(x, int(s["out"] * SR))
    seg = x[a:b].copy()
    for h in CL["holds"]:
        if h["clip"] == s["clip"] and s["in"] <= h["at"] <= s["out"]:
            p = zc(x, int(h["at"] * SR)) - a; n = int(h["add"] * SR)
            pad = room[:n].copy() if n <= len(room) else np.resize(room, n)
            seg = np.concatenate([seg[:p], pad, seg[p:]])
    # clip joins: clean room tone instead of breaths / handling noise in the tail and head silences
    rt = CL.get("roomtone", {}).get(s["clip"], [None, None])
    last_of_clip = k == len(CL["segments"]) - 1 or CL["segments"][k + 1]["clip"] != s["clip"]
    first_of_clip = k == 0 or CL["segments"][k - 1]["clip"] != s["clip"]
    F = int(0.015 * SR)
    def blend(seg, i0, i1):
        i0, i1 = max(0, i0), min(len(seg), i1)
        if i1 - i0 < 2 * F: return seg
        tone = np.resize(room[::-1] if i0 == 0 else room, i1 - i0)
        r = np.ones(i1 - i0, np.float32); r[:F] = np.linspace(0, 1, F); r[-F:] = np.linspace(1, 0, F)
        if i0 == 0: r[:F] = 1
        if i1 == len(seg): r[-F:] = 1
        seg[i0:i1] = seg[i0:i1] * (1 - r) + tone * r
        return seg
    if last_of_clip and rt[0] is not None:
        seg = blend(seg, int((rt[0] - a / SR) * SR), len(seg))
    if first_of_clip and rt[1] is not None:
        seg = blend(seg, 0, int((rt[1] - a / SR) * SR))
    pieces.append(seg)

out = pieces[0].copy(); seam_pos = []; starts = [0]
for seg in pieces[1:]:
    ramp = np.linspace(0, 1, XF, dtype=np.float32)
    tail = out[-XF:] * (1 - ramp) + seg[:XF] * ramp
    seam_pos.append(len(out) - XF // 2); starts.append(len(out) - XF)
    out = np.concatenate([out[:-XF], tail, seg[XF:]])

def write(path, y):
    y16 = (np.clip(y, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(y16.tobytes())

write("work/talk_cut_raw.wav", out)
beep = (0.2 * np.sin(2 * np.pi * 1000 * np.arange(int(0.12 * SR)) / SR)).astype(np.float32)
gap = np.zeros(int(0.15 * SR), np.float32); chk = []
lines = []
for i, p in enumerate(seam_pos):
    a, b = max(0, p - SR // 2), min(len(out), p + SR // 2)
    chk += [out[a:b], gap, beep, gap]
    s0, s1 = CL["segments"][i], CL["segments"][i + 1]
    lines.append(f"seam {i+1:02d} @ {p/SR:7.3f}s  {s0['clip']} out {s0['out']:.2f} | {s1['clip']} in {s1['in']:.2f}"
                 f"   ...{s0['words'][-28:]!r} | {s1['words'][:28]!r}...")
write("work/seams_check.wav", np.concatenate(chk))
open("work/seams.txt", "w").write("\n".join(lines) + "\n")
json.dump([p / SR for p in seam_pos], open("work/seam_times.json", "w"))
holdinfo = []
for k, s in enumerate(CL["segments"]):
    hs = [dict(at=h["at"], add=h["add"]) for h in CL["holds"] if h["clip"] == s["clip"] and s["in"] <= h["at"] <= s["out"]]
    holdinfo.append(dict(clip=s["clip"], face=s.get("face", True), src_in=zc(audio(s["clip"]), int(s["in"] * SR)) / SR, src_out=zc(audio(s["clip"]), int(s["out"] * SR)) / SR, tl_start=starts[k] / SR, holds=hs))
json.dump(dict(total=len(out) / SR, segs=holdinfo), open("work/av_timeline.json", "w"), indent=1)
print(f"cut voice {len(out)/SR:.2f}s, {len(seam_pos)} seams")

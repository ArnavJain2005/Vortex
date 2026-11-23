"""Final audio: cleaned voice + bar-edited BGM with sidechain-style ducking + SFX. Writes work/mix_pre.wav (48 kHz stereo)."""
import sys, json, subprocess, numpy as np
sys.path.insert(0, "/home/claude/vx/src/hf")
from common import W, LEAD, DURATION, SECTIONS, wend

SR = 48000
A = "/home/claude/assets"
DA = f"{A}/sfx_daedal/DAEDAL Transition SFX Pack"
AL = f"{A}/sfx_alfred/alfredmakes-sound-kit/kit"
N = int(DURATION * SR)

def load(path, mono=False):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1" if mono else "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).copy()
    return x if mono else x.reshape(-1, 2)

def db(g): return 10 ** (g / 20)
V = lambda v: LEAD + v              # voice time -> video time
S = {sid: (a, b) for sid, a, b in SECTIONS}

# ------------------------------------------------------------------ music edit (bar grid 2.669 s)
BAR, B0 = 2.669, 2.664
bar = lambda k: B0 + k * BAR
s0 = 0.924                                    # source time at video 0, so the drop lands on K-6 at a bar line
mus = load(f"{A}/single/d1dd2a93-yurasoop-abstract-technology-ambient-519876.mp3")
vbar = lambda k: 1.74 + k * BAR              # bar lines on the video timeline
drop_v = V(S["k6"][0])                       # K-6 start
segs = [  # (video_start, source_start, length)
    (0.0, s0, vbar(13) - 0.0),                                              # intro + groove through S-b
    (vbar(13), bar(42), 5 * BAR), (vbar(18), bar(42), 5 * BAR),             # breakdown x2 under the pipeline (drums out)
    (vbar(23), bar(42), 7 * BAR),                                           # breakdown builds into the drop
    (vbar(30), bar(49), 12 * BAR),                                          # the drop: big section under the results
    (vbar(42), bar(36), 5 * BAR),                                           # groove under K-7 / S-d
    (vbar(47), bar(61), (len(mus) / SR) - bar(61)),                         # end hit + ring-out resolves on the final line
]
music = np.zeros((N, 2), np.float32); XF = int(0.04 * SR)
for vs, ss, ln in segs:
    a, b = int(vs * SR), min(N, int((vs + ln) * SR)); src = mus[int(ss * SR): int(ss * SR) + (b - a)]
    b = a + len(src); seg = src.copy()
    r = np.ones(len(seg), np.float32); r[:XF] = np.linspace(0, 1, XF); r[-XF:] = np.minimum(r[-XF:], np.linspace(1, 0, XF))
    music[a - XF // 2 if a > 0 else a: b - XF // 2 if a > 0 else b] += (seg * r[:, None])[: (b - a)]
print("drop at video", round(vbar(30), 3), "K-6 starts", round(drop_v, 3), "final hit", round(vbar(47), 3))

# ------------------------------------------------------------------ voice
voice = load("/home/claude/vx/work/voice_clean.wav", mono=True)
vt = np.zeros(N, np.float32); a = int(LEAD * SR); vt[a:a + len(voice)] = voice[: N - a]
# room tone under the lead-in and the end hold (no digital silence); 0.3 s fade-in, 1 s fade-out at the end
room = load("/home/claude/vx/work/talk_cut_raw.wav", mono=True)[int(0.0 * SR):int(0.20 * SR)]
tone = np.resize(room, a)
vt[:a] = tone * np.linspace(0, 1, a)
end_v = a + len(voice)
if end_v < N:
    vt[end_v:] = np.resize(room, N - end_v)
fade_out = int(1.0 * SR); vt[-fade_out:] *= np.linspace(1, 0, fade_out)
vt[: int(0.3 * SR)] *= np.linspace(0, 1, int(0.3 * SR))

# ------------------------------------------------------------------ ducking envelope from the voice (attack 25 ms, release 450 ms)
hop = 480; n = N // hop
env = np.sqrt((vt[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9
edb = 20 * np.log10(env); thr = np.percentile(edb[edb > -60], 35) + 6
speech = (edb > thr).astype(np.float32)
# bridge tiny gaps (< 0.35 s) so music does not pump between words
k = int(0.35 / 0.01); s2 = speech.copy()
for i in range(n):
    if speech[i] == 0:
        lo, hi = max(0, i - k), min(n, i + k)
        if speech[lo:i].any() and speech[i:hi].any(): s2[i] = 1
g = np.zeros(n); att, rel = np.exp(-1 / 2.5), np.exp(-1 / 45)
for i in range(n):
    c = rel if s2[i] < g[i - 1] else att
    g[i] = c * g[i - 1] + (1 - c) * s2[i] if i else s2[i]
UNDER, GAP = -18.0, -6.0             # music RMS relative to the voice's speech RMS: under speech / in the gaps
music_db = GAP + (UNDER - GAP) * g
# deliberate silences right after the two 'dies' glitches (the silence is the emphasis)
for t in [V(W("dies", 12.5)), V(W("dies", 111.3))]:
    i0, i1 = int((t + 0.08) * 100), int((t + 0.65) * 100)
    music_db[i0:i1] = -60; music_db[i1:i1 + 30] = np.linspace(-60, music_db[min(n - 1, i1 + 30)], len(music_db[i1:i1 + 30]))
gain = np.repeat(db(music_db), hop); gain = np.pad(gain, (0, N - len(gain)), mode="edge")
# scale the music bed so 'gap' level ~ -16 LUFS: measure its RMS-based loudness proxy
mrms = 20 * np.log10(np.sqrt(np.mean(music[int(5 * SR): int(120 * SR)] ** 2)) + 1e-9)
vframes = vt[: n * hop].reshape(n, hop)[s2 > 0.5]
vrms = 20 * np.log10(np.sqrt(np.mean(vframes ** 2)) + 1e-9)
music *= db(vrms - mrms)                       # bed at voice RMS; the envelope then sets -6 dB (gaps) / -18 dB (under speech)
print("voice speech RMS", round(vrms, 1), "music RMS", round(mrms, 1))
music *= gain[:, None]
music[-int(1.0 * SR):] *= np.linspace(1, 0, int(1.0 * SR))[:, None]

# ------------------------------------------------------------------ SFX (−24 … −18 dB, 1–4 kHz scooped so words stay clear)
def sfx_load(p):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-af", "equalizer=f=2000:t=o:w=1.6:g=-7", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).reshape(-1, 2).copy()
    pk = np.abs(x).max() + 1e-9
    return x / pk                                   # peak-normalise, then place at a set peak level
SFX = []
def put(t, path, peak_db, pan=0.0, peak_at=0.0, maxlen=None):
    SFX.append((t, path, peak_db, pan, peak_at, maxlen))
wh, whip, deep = f"{DA}/Whooshes/DAEDAL_Whoosh_02_Airy.wav", f"{DA}/Whooshes/DAEDAL_Whoosh_04_Whip.wav", f"{DA}/Whooshes/DAEDAL_Whoosh_03_Deep.wav"
tick, click, blip = f"{DA}/UI_Clicks_Pops/DAEDAL_Click_03_Tick.wav", f"{AL}/alfredmakes-click-ui-1.wav", f"{AL}/alfredmakes-pop-tiny-1.wav"
glitch, thud = f"{DA}/Glitches/DAEDAL_Glitch_02.wav", f"{DA}/Impacts/DAEDAL_Impact_05_Thud_Dry.wav"
riser, sub = f"{DA}/Risers/DAEDAL_Riser_04_Short_1s.wav", f"{A}/single/7e6fd00e-brvhrtz-sub-drop-short-232033.mp3"
logo, data = f"{A}/single/7b315b9a-sergequadrado-warm-tech-logo-21474.mp3", f"{A}/single/0d2bdf12-soundshelfstudio-ui-data-processing-beep-527474.mp3"
# section transitions: soft whoosh panned with the motion (quieter when they overlap speech)
put(V(S["sa"][0]) + 0.2, wh, -26, +0.5)               # circle glides right
put(V(S["k2"][0]), wh, -26, -0.2)
put(V(W("Vortex", 20.1)) - 0.3, wh, -22, -0.6)         # CSV card travels left
put(V(W("Inside", 35.6)) + 0.35, deep, -19, 0.0)       # zoom-through into the node
put(V(S["sc"][0]) - 0.25, wh, -20, 0.0)                # pipeline collapses into main.py (in the join gap)
put(V(S["k5"][0]) - 0.1, wh, -26, 0.3)
put(drop_v - 0.95, riser, -21, 0.0)                    # riser into the results ...
put(drop_v - 0.28, whip, -18, -0.7)                    # ... whip-pan left ...
put(drop_v, sub, -19, 0.0)                             # ... and a sub impact on the drop
put(V(S["k7"][0]) - 0.2, wh, -20, 0.2)
put(V(S["sd"][0]) - 0.2, wh, -21, -0.2)
# glitch bursts on 'dies'
put(V(W("dies", 12.5)), glitch, -19, 0.0); put(V(W("dies", 111.3)), glitch, -19, 0.0)
# K-2 badges struck through
for w_, n_ in [("GPS", 17.4), ("camera", 18.2), ("map", 19.0)]: put(V(W(w_, n_)) + 0.24, click, -27, 0.0)
# K-3 rows flowing + pose markers appearing: light data blips
put(V(W("Vortex", 20.1)) + 0.35, data, -30, -0.3, maxlen=1.8)
for i in range(6): put(V(W("rebuilds", 23.3)) + 0.15 + i * 0.25, blip, -30, -0.2 + i * 0.12)
# K-4 pipeline blocks landing
for w_, n_ in [("calibrates", 38.5), ("15-state", 41.4), ("When", 44.7), ("prior", 50.7), ("Gravity", 58.2), ("smoother", 62.1)]:
    put(V(W(w_, n_)) + 0.12, tick, -26, 0.0)
put(V(W("zero", 48.7)) + 0.1, tick, -26, 0.0)        # needle settles
# K-5 numbers landing
put(V(W("3.5", 72.9)) + 0.35, tick, -25, -0.3); put(V(W("6.6", 75.4)) + 0.35, tick, -25, 0.3)
# K-6 tags landing
for w_, n_ in [("8.1%", 91.9), ("40%", 95.2), ("second", 98.5), ("14.8%", 105.3)]: put(V(W(w_, n_)) + 0.2, tick, -25, 0.25)
for i in range(4): put(V(W("all", 108.4)) + i * 0.16 + 0.15, blip, -29, -0.3 + i * 0.2)
# K-7 stamp thud
put(V(W("passes", 118.0)) + 0.2, thud, -19, 0.0)
# end slate: low warm hit as the wordmark assembles
put(V(W("Vortex", 123.9)) - 0.15, logo, -21, 0.0, maxlen=3.2)

sfx = np.zeros((N, 2), np.float32); cache = {}
for t, p, pk, pan, _, ml in SFX:
    if p not in cache: cache[p] = sfx_load(p)
    x = cache[p]
    if ml: x = x[: int(ml * SR)].copy(); f = int(0.3 * SR); x[-f:] *= np.linspace(1, 0, f)[:, None]
    L, R = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    y = x * db(pk) * np.array([L, R], np.float32) * 1.414
    a = int(t * SR); b = min(N, a + len(y)); sfx[a:b] += y[: b - a]

mix = music + sfx + np.stack([vt, vt], 1)
pk = np.abs(mix).max(); mix = mix / max(1.0, pk / 0.89)
raw = (np.clip(mix, -1, 1) * 32767).astype("<i2").tobytes()
import wave
with wave.open("/home/claude/vx/work/mix_pre.wav", "w") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(raw)
json.dump([dict(t=round(t, 3), file=p.split("/")[-1], peak_db=pk_, pan=pan) for t, p, pk_, pan, _, _ in SFX],
          open("/home/claude/vx/work/sfx_cues.json", "w"), indent=1)
print("mix", round(N / SR, 3), "s; sfx", len(SFX))

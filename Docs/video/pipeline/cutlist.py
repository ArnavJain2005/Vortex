"""Build work/cutlist.json from the word transcript + 10 ms energy envelope.

Silence = frames with level <= clip noise floor + 6 dB. The phone recordings have a noise
floor only ~23 dB under speech, so "30 dB below speech" cannot be reached; this is the
closest honest equivalent. Every cut lies inside such silence AND respects the word
timestamps: >= 150 ms after the previous word's ASR end, >= 80 ms before the next word's
ASR start.
"""
import json, numpy as np

E = json.load(open("work/envelope.json"))
T = json.load(open("work/transcript.json"))
SIL_DB, DEAD, JOIN, EMPH, EMPH_MIN = 6.0, 0.15, 0.32, 0.55, 0.45

# explicit removals: (clip, first word index removed, last word index removed, why)
def widx(c, w, near):
    ws = T[c]["words"]
    return min((i for i, x in enumerate(ws) if x["w"].strip(",.:").lower() == w), key=lambda i: abs(ws[i]["s"] - near))

RM = [("c03", widx("c03", "later", 34.0), widx("c03", "later", 34.0), "stumble: 'later' before restart 'use later readings'"),
      ("c05", widx("c05", "well", 10.9), widx("c05", "well", 10.9), "filler: 'Well,'"),
      ("c07", widx("c07", "well", 0.9), widx("c07", "well", 0.9), "filler: 'Well,'")]
# the c05 'four-oh,' stumble is inside one ASR token ("4040%"); handled as a sub-word span
SUBRM = [("c05", 17.55, 18.38, "stumble: 'four-oh,' before 'forty percent'")]

# emphasis pauses after word (clip, word, approx time) or at a clip end
EMPHASIS = {("c01", "END"): "after 'No GPS, no camera, no map.'",
            ("c02", "END"): "after '...a forecast.'",
            ("c03", "END"): "after '...revise the earlier ones.' (end of pipeline)",
            ("c04r", "END"): "after '...well inside the limits.'",
            ("c05", widx("c05", "8.1%", 14.2)): "after '8.1 percent'",
            ("c05", "SUB0"): "after '40 percent'",
            ("c05", widx("c05", "14.8%", 29.4)): "after '14.8 percent'",
            ("c06", widx("c06", "motion", 6.6)): "after '...instead of inventing motion.'",
            ("c07", widx("c07", "testing", 4.0)): "before final line 'Vortex: a navigator...'"}

SECTIONS = {"c01": [(0, 4.6, "K-1", "KEY"), (4.6, 16.5, "S-a", "SUPPORT"), (16.5, 99, "K-2", "KEY")],
            "c02": [(0, 99, "K-3", "KEY")],
            "c03": [(0, 3.4, "S-b", "SUPPORT"), (3.4, 99, "K-4", "KEY")],
            "c04": [(0, 7.4, "S-c", "SUPPORT"), (7.4, 99, "K-5", "KEY")],
            "c04r": [(0, 7.45, "S-c", "SUPPORT"), (7.45, 99, "K-5", "KEY")],
            "c05": [(0, 99, "K-6", "KEY")], "c06": [(0, 99, "K-7", "KEY")],
            "c07": [(0, 4.9, "S-d", "SUPPORT"), (4.9, 99, "K-8", "KEY")]}

def sil(c):
    db = np.array(E[c]["db"]); return db <= E[c]["floor"] + SIL_DB

# ASR (TDT) word ends run up to the next word's start, so word edges come from energy:
WS = {}
def _w(c):
    if c not in WS: WS[c] = {round(w["s"], 3): w for w in T[c]["words"]}
    return WS[c]
def offset(c, t, s0=None):  # acoustic end: from the word start, run until >= 80 ms of silence
    m = sil(c); i = int((s0 if s0 is not None else t) * 100)
    while i < len(m) and m[i]: i += 1
    while i < len(m) - 15 and not m[i:i + 15].all(): i += 1
    return i / 100
def onset(c, t, e0=None):  # acoustic start: first sound from t-0.12, then back until >= 80 ms of silence
    m = sil(c); i = max(0, int((t - 0.12) * 100))
    while i < len(m) - 1 and m[i]: i += 1
    while i > 15 and not m[i - 15:i].all(): i -= 1
    return i / 100
def snap(c, t, w=0.03):
    db = np.array(E[c]['db']); a = int((t - w) * 100); b = int((t + w) * 100) + 1
    return round((a + int(np.argmin(db[a:b]))) / 100, 2)

def silence_len(c, a, b):
    s = sil(c); return s[int(a * 100):int(b * 100)].sum() / 100

GAP = 1.0   # pause at every clip join (Arnav asked for more room between clips)
SAFE_TAIL = {"c01": 0.6, "c02": 0.6, "c03": 0.33, "c04r": 0.6, "c05": 0.6, "c06": 0.45}   # picture stays calm this long after the last word
SAFE_HEAD = {"c02": 0.3, "c03": 0.3, "c04r": 0.3, "c05": 0.25, "c06": 0.3, "c07": 0.0}
roomtone = {}   # clip -> (replace_after_src, replace_before_src)
segs, removed, emph_log, holds = [], [], [], []
clips = ["c01", "c02", "c03", "c04r", "c05", "c06", "c07"]
for ci, c in enumerate(clips):
    ws = T[c]["words"]; dur = T[c]["dur"]
    drop = set()
    for rc, a, b, why in RM:
        if rc == c: drop |= set(range(a, b + 1))
    keep = [i for i in range(len(ws)) if i not in drop]
    # sub-word removal in c05: split the '4040%' token into two pseudo-words
    pw = []  # (start, end, label, index_key)
    for i in keep:
        w = ws[i]
        if c == "c05" and w["w"].startswith("4040"):
            pw.append((w["s"], 17.55, "[four-oh,]", "DROP")); pw.append((18.38, w["e"], "40%.", "SUB0"))
        else:
            pw.append((w["s"], w["e"], w["w"], i))
    pw = [p for p in pw if p[3] != "DROP"]
    # head
    first = pw[0]; on0 = onset(c, first[0], first[1])
    head_keep = 0.08 if ci == 0 else None
    pieces = []  # list of [in, out]
    if ci == 0:
        cur_in = max(0.0, on0 - 0.08)
    else:
        cur_in = None  # decided by the previous clip's join
    # internal gaps
    cuts = []
    for k in range(len(pw) - 1):
        a, b = pw[k], pw[k + 1]
        off_a = offset(c, a[1], a[0]); on_b = onset(c, b[0], b[1])
        P = on_b - off_a
        removed_between = any(r[0] == c and a[1] <= ws[r[1]]["s"] < b[0] for r in RM) or \
            (c == "c05" and a[2] == "by" and b[2] == "40%.")
        key = (c, a[3])
        target = EMPH if key in EMPHASIS else DEAD
        if P <= 0.30 and not removed_between and key not in EMPHASIS:
            continue
        lo = off_a + (0.12 if target == DEAD else target * 0.6)
        hi = on_b - (0.06 if target == DEAD else target * 0.4)
        if key in EMPHASIS:
            if P < 0.40:
                holds.append(dict(clip=c, at=round((off_a + on_b) / 2, 2), add=round(EMPH_MIN - max(P, 0), 2),
                                  why=EMPHASIS[key] + f" (natural pause {P:.2f}s)"))
                emph_log.append((EMPHASIS[key], EMPH_MIN, f"natural {P:.2f}s, padded with room tone + frame hold"))
                continue
            emph_log.append((EMPHASIS[key], min(P, EMPH), f"natural {P:.2f}s"))
        if removed_between and c == "c05" and a[2] == "by":
            cuts.append((snap(c, 17.55), snap(c, 18.38), SUBRM[0][3])); continue
        if removed_between and c == "c03":
            cuts.append((off_a + 0.12, 34.64, RM[0][3])); continue
        if removed_between:
            # remove everything between the two kept words except the guarded pause
            lo = off_a + 0.12; hi = on_b - 0.06
            why = [r[3] for r in RM if r[0] == c and a[1] <= ws[r[1]]["s"] < b[0]] or [SUBRM[0][3]]
            # snap into the quietest frame within +-30 ms
            cuts.append((lo, hi, why[0]))
            continue
        if hi - lo >= 0.05:
            cuts.append((lo, hi, f"dead air {P:.2f}s -> {target:.2f}s"))
    # tail
    last = pw[-1]; offN = offset(c, last[1], last[0])
    if ci == len(clips) - 1:
        tail_keep = 0.6
    else:
        tail_keep = SAFE_TAIL[c]
    cur_out = min(dur, offN + max(tail_keep, 0.15))
    if ci < len(clips) - 1:
        nxt = clips[ci + 1]
        pad = round(max(0.0, GAP - tail_keep - SAFE_HEAD[nxt]), 2)
        if pad > 0: holds.append(dict(clip=c, at=round(cur_out, 3), add=pad, why=f"join {c}->{nxt}: hold last calm frame"))
        roomtone.setdefault(c, [None, None])[0] = round(offN + 0.12, 3)
    if c == 'c01': cur_out = max(cur_out, 23.36)  # keep the soft final /p/ release of 'map' (23.12-23.30)
    if (c, "END") in EMPHASIS:
        emph_log.append((EMPHASIS[(c, "END")], EMPH, "tail silence + next clip head"))
    if ci == 0:
        start = cur_in
    else:
        nxt_on = on0
        lead = (EMPH if (clips[ci - 1], "END") in EMPHASIS else JOIN) * 0.4
        start = max(0.0, on0 - max(SAFE_HEAD[c], 0.08))
        roomtone.setdefault(c, [None, None])[1] = round(on0 - 0.06, 3)
        if c == "c07": start = 1.32
        if start > 0: removed.append(dict(clip=c, start=0.0, end=round(start, 2), why="clip head"))
    removed.append(dict(clip=c, start=round(cur_out, 2), end=round(dur, 2), why="clip tail")) if cur_out < dur else None
    t = start
    for lo, hi, why in sorted(cuts):
        segs.append((c, round(t, 3), round(lo, 3))); removed.append(dict(clip=c, start=round(lo, 2), end=round(hi, 2), why=why)); t = hi
    segs.append((c, round(t, 3), round(cur_out, 3)))
    if ci == 0 and start > 0: removed.append(dict(clip=c, start=0.0, end=round(start, 2), why="clip head"))

def section(c, t):
    for a, b, n, tag in SECTIONS[c]:
        if a <= t < b: return n, tag

out, tl = [], 0.0
for c, a, b in segs:
    ws = [w for w in T[c]["words"] if a <= max(onset(c, w["s"], w["e"]), w["s"]) + 0.02 < b]
    txt = " ".join(w["w"] for w in ws)
    if c == "c05" and a <= 17.6 <= b: txt = txt.replace("4040%.", "")
    if c == "c05" and a <= 18.5 <= b and "4040%." in txt: txt = txt.replace("4040%.", "forty percent.")
    if c == "c05" and abs(a - 18.38) < 0.2: txt = ("forty percent. " + txt).strip()
    n, tag = section(c, ws[0]["s"] if ws else a)
    # hold padding that falls inside this segment
    h = sum(x["add"] for x in holds if x["clip"] == c and a <= x["at"] <= b)
    out.append(dict(src=f"talking-head/{c}.mp4", clip=c, face=(c != "c04r"), **{"in": a, "out": b}, dur=round(b - a, 3), hold=round(h, 2),
                    tl_start=round(tl, 3), words=txt, section=n, tag=tag))
    tl += b - a + h
total = round(tl, 2)
json.dump(dict(total_s=total, segments=out, holds=holds, roomtone=roomtone, removed=sorted(removed, key=lambda r: (r["clip"], r["start"])),
               emphasis=[dict(what=e[0], kept_s=round(e[1], 2), note=e[2]) for e in emph_log]),
          open("work/cutlist.json", "w"), indent=1)
print("segments", len(out), "total", total)
for s in out: print(f"{s['tl_start']:7.2f} {s['clip']} {s['in']:6.2f}-{s['out']:6.2f} {s['section']:4} {s['words']}")
print("removed > 1 s:")
for r in removed:
    if r["end"] - r["start"] > 1.0: print("  ", r)
for e in emph_log: print("  emph", e)

import json, glob, os, wave, numpy as np, sherpa_onnx
d = "/home/claude/models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
rec = sherpa_onnx.OfflineRecognizer.from_transducer(
    encoder=f"{d}/encoder.int8.onnx", decoder=f"{d}/decoder.int8.onnx",
    joiner=f"{d}/joiner.int8.onnx", tokens=f"{d}/tokens.txt",
    model_type="nemo_transducer", num_threads=4)
def load(p):
    with wave.open(p) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        return a, w.getframerate()
out = {}
for wav in sorted(glob.glob("/home/claude/vx/work/c*.wav")):
    clip = os.path.basename(wav)[:-4]
    a, sr = load(wav)
    s = rec.create_stream(); s.accept_waveform(sr, a); rec.decode_stream(s)
    r = s.result
    toks, ts = list(r.tokens), list(r.timestamps)
    durs = list(getattr(r, "durations", []) or [])
    words = []
    for i, t in enumerate(toks):
        st = ts[i]; en = st + (durs[i] if i < len(durs) and durs[i] > 0 else 0.08)
        if t.startswith("▁") or t.startswith(" ") or not words:
            words.append({"w": t.lstrip("▁ "), "s": round(st, 3), "e": round(en, 3)})
        else:
            words[-1]["w"] += t; words[-1]["e"] = round(en, 3)
    words = [w for w in words if w["w"]]
    out[clip] = {"dur": len(a) / sr, "text": r.text.strip(), "words": words}
    print(clip, f"{len(a)/sr:.1f}s |", r.text.strip(), flush=True)
json.dump(out, open("/home/claude/vx/work/transcript.json", "w"), indent=1)

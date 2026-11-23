# Seam check: at each seam, speech energy in the 20 ms either side must be near the floor
import json, numpy as np, wave
w = wave.open("work/talk_cut_raw.wav"); sr = w.getframerate()
x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
hop = sr // 100; n = len(x) // hop
db = 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
floor = np.percentile(db, 10); speech = np.percentile(db, 95)
bad = 0
for i, t in enumerate(json.load(open("work/seam_times.json"))):
    k = int(t * 100); around = db[k - 2:k + 2].max()
    flag = "FAIL" if around > floor + 9 else "ok"
    bad += flag == "FAIL"
    print(f"seam {i+1:02d} {t:7.2f}s  level at seam {around - floor:+5.1f} dB over floor  {flag}")
print(f"floor {floor:.1f} dB, speech {speech:.1f} dB, failures {bad}")

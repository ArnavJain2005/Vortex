import cv2, json, numpy as np, sys
casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
res = {}
for c in ["c01","c02","c03","c04r","c05","c06","c07"]:
    cap = cv2.VideoCapture(f"talking-head/{c}.mp4"); n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    boxes = []
    for k in np.linspace(5, n - 5, 24).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(k)); ok, f = cap.read()
        if not ok: continue
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        fs = casc.detectMultiScale(g, 1.1, 6, minSize=(80, 80))
        if len(fs): boxes.append(max(fs, key=lambda b: b[2] * b[3]))
    b = np.median(np.array(boxes), axis=0)  # smoothed fixed crop
    x, y, w, h = b; cx, cy = x + w / 2, y + h / 2 + 0.18 * h   # centre slightly below the eyes
    side = min(478, 2.15 * w)
    res[c] = dict(cx=round(cx, 1), cy=round(cy, 1), side=round(side, 1), face_w=round(w, 1), n=len(boxes),
                  spread=round(float(np.std(np.array(boxes)[:, 0])), 1))
    print(c, res[c])
json.dump(res, open("work/facecrop.json", "w"), indent=1)

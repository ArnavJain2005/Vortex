import os, sys, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import frame, scenes_a
P = "/home/claude/vx/proj"
os.makedirs(P + "/compositions", exist_ok=True)
def w(name, txt): open(f"{P}/{name}", "w").write(txt)
w("index.html", frame.index_html())
w("compositions/bg.html", frame.bg_html())
w("compositions/fx.html", frame.fx_html())
mods = [scenes_a]
try:
    import scenes_b; mods.append(scenes_b)
except ImportError: pass
try:
    import scenes_c; mods.append(scenes_c)
except ImportError: pass
built = set()
for m in mods:
    for sid in IDS + ["cap"]:
        if hasattr(m, sid): w(f"compositions/{sid}.html", getattr(m, sid)()); built.add(sid)
# placeholders for scenes not yet written
for sid in IDS + ["cap"]:
    if sid not in built:
        i = IDS.index(sid) if sid in IDS else None
        d = (host_end(i) - host_start(i)) if i is not None else DURATION
        w(f"compositions/{sid}.html", scene(sid, d, "", f'<div class="world" id="{sid}-world"></div>', ""))
# film grain tile (deterministic)
if not os.path.exists(P + "/assets/grain.png"):
    from PIL import Image
    r = np.random.default_rng(1).normal(128, 40, (512, 512)).clip(0, 255).astype("uint8")
    Image.fromarray(r, "L").save(P + "/assets/grain.png")
print("built", sorted(built), "duration", DURATION)

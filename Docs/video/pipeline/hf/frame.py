"""Root index.html, background world (bg) and finishing overlay (fx)."""
import json
from common import *

CUTS = json.load(open("/home/claude/vx/work/face_cuts.json"))

def T(v): return round(LEAD + v, 3)

def face_moves():
    """Root-timeline tweens for the face circle (all times = video time)."""
    s = []
    # positions are circle centres; the wrapper is 560 px and scales to the target size
    def to(t, cx, cy, size, d, ease="power3.inOut", op=1):
        s.append(f"tl.to('#faceWrap',{{x:{cx - size / 2:.1f},y:{cy - size / 2:.1f},scale:{size / 560:.4f},opacity:{op},duration:{d},ease:'{ease}'}},{t:.3f});")
    s.append("gsap.set('#faceWrap',{x:680,y:370,scale:1});")                     # 560 centred under the title (centre 960,650)
    s.append(f"tl.fromTo('#faceWrap',{{opacity:0}},{{opacity:1,duration:0.6,ease:'power2.out'}},0.05);")
    sec = {sid: (x, y) for sid, x, y in SECTIONS}
    to(T(sec["sa"][0] + 0.25), 1704, 864, 320, 0.8)                                   # glide to the corner on "Pip's story"
    to(T(sec["sc"][0] - 0.2), 1704, 864, 120, 0.45, "power3.in", 0)                    # voice-only stretch: circle bows out
    s.append(f"tl.set('#faceWrap',{{x:{1734-130},y:{894-130},scale:{260/560:.4f}}},{T(sec['k6'][0] - 0.3):.3f});")
    to(T(sec["k6"][0] + 0.1), 1734, 894, 260, 0.35, "expo.out", 1)                    # back, small, for the results board
    to(T(sec["k7"][0] + 0.05), 1704, 864, 320, 0.6)                                    # K-7 back to 320
    to(T(sec["k8"][0] + 0.1), 520, 560, 480, 0.8)                                      # end slate: 480 px centred-left
    # jump-cut hiding: alternate 1.00 / 1.07 framing at every picture cut, 2-frame ease
    k = 1.0
    for f in CUTS["cut_frames"][1:]:
        k = 1.07 if k == 1.0 else 1.0
        s.append(f"tl.to('#facePunch',{{scale:{k},duration:{2/FPS:.4f},ease:'power1.out'}},{LEAD + f / FPS - 1/FPS:.4f});")
    return "\n".join(s)

def index_html():
    hosts = []
    for i, (sid, a, b) in enumerate(SECTIONS):
        start, end = host_start(i), host_end(i)
        hosts.append(f'<div id="{sid}" data-composition-id="{sid}" data-composition-src="compositions/{sid}.html" '
                     f'data-start="{start:.3f}" data-duration="{end - start:.3f}" data-track-index="{2 + i % 2}" '
                     f'data-track-kind="graphics" data-width="1920" data-height="1080" style="z-index:{10 + i}"></div>')
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1920, height=1080" />
<script src="assets/lib/gsap.min.js"></script>
<script src="assets/lib/DrawSVGPlugin.min.js"></script>
<script src="assets/lib/MorphSVGPlugin.min.js"></script>
<script src="assets/lib/MotionPathPlugin.min.js"></script>
<script src="assets/lib/CustomEase.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
html,body{{margin:0;width:1920px;height:1080px;overflow:hidden;background:#0a0e2e;}}
#faceWrap{{position:absolute;left:0;top:0;width:560px;height:560px;border-radius:50%;z-index:60;transform-origin:0 0;
  box-shadow:0 12px 40px rgba(0,0,0,.45);}}
#faceClip{{position:absolute;inset:0;border-radius:50%;overflow:hidden;background:#0a0e2e;}}
#facePunch{{position:absolute;inset:0;transform-origin:50% 42%;}}
#face{{position:absolute;left:0;top:0;width:560px;height:560px;object-fit:cover;}}
#faceRing{{position:absolute;inset:-2px;border-radius:50%;border:4px solid #5ec8f2;box-shadow:0 0 18px rgba(94,200,242,.35);}}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{DURATION}" data-width="1920" data-height="1080">
<div id="bg" data-composition-id="bg" data-composition-src="compositions/bg.html" data-start="0" data-duration="{DURATION}"
  data-track-index="1" data-track-kind="graphics" data-width="1920" data-height="1080" style="z-index:1"></div>
{chr(10).join(hosts)}
<div id="cap" data-composition-id="cap" data-composition-src="compositions/cap.html" data-start="0" data-duration="{DURATION}"
  data-track-index="4" data-track-kind="captions" data-width="1920" data-height="1080" style="z-index:50"></div>
<div id="faceWrap" style="opacity:0"><div id="faceClip" data-layout-allow-overflow><div id="facePunch">
  <video id="face" class="clip" src="assets/face_cut.mp4" muted playsinline data-start="{LEAD}" data-duration="{DURATION - LEAD:.3f}" data-track-index="0"></video>
</div></div><div id="faceRing"></div></div>
<div id="fx" data-composition-id="fx" data-composition-src="compositions/fx.html" data-start="0" data-duration="{DURATION}"
  data-track-index="5" data-track-kind="graphics" data-width="1920" data-height="1080" style="z-index:90"></div>
</div>
<script>
const tl = gsap.timeline({{paused:true}});
{face_moves()}
window.__timelines["main"] = tl;
</script>
</body>
</html>
"""

def bg_html():
    # camera pans across one "world map": the grid/stars shift at every section change
    pans, x, y = [], 0, 0
    dirs = [(-260, 0), (0, -180), (-300, 60), (-120, -220), (-280, 0), (0, 200), (-320, 0), (-200, -120), (-260, 80), (0, -200), (-240, 0)]
    for i, (sid, a, b) in enumerate(SECTIONS[1:]):
        dx, dy = dirs[i % len(dirs)]; x += dx; y += dy
        d = 0.5 if sid == "k6" else 0.9
        pans.append(f"tl.to('#bg-grid',{{x:{x},y:{y},duration:{d},ease:'power2.inOut'}},{LEAD + a - 0.45:.3f});")
        pans.append(f"tl.to('#bg-fore',{{x:{x*1.8:.0f},y:{y*1.8:.0f},duration:{d},ease:'power2.inOut'}},{LEAD + a - 0.45:.3f});")
        pans.append(f"tl.to('#bg-stars',{{x:{x*0.35:.0f},y:{y*0.35:.0f},duration:{d},ease:'power2.inOut'}},{LEAD + a - 0.45:.3f});")
    css = """
#bg-base{position:absolute;inset:0;background:radial-gradient(1400px 900px at 50% 38%,#16205a 0%,#0d1340 45%,#0a0e2e 80%);}
#bg-grid{position:absolute;left:-1600px;top:-1200px;width:5200px;height:3600px;opacity:.18;
  background-image:linear-gradient(rgba(94,200,242,.22) 1px,transparent 1px),linear-gradient(90deg,rgba(94,200,242,.22) 1px,transparent 1px);
  background-size:96px 96px;}
#bg-stars{position:absolute;left:-600px;top:-400px;width:3120px;height:1880px;}
#bg-fore{position:absolute;left:-1600px;top:-1200px;width:5200px;height:3600px;opacity:.55;}
"""
    html = """<div class="world" id="bg-world" data-layout-ignore><div id="bg-base"></div><canvas id="bg-stars" width="3120" height="1880"></canvas>
<div id="bg-grid" data-layout-ignore></div><canvas id="bg-fore" width="2600" height="1800" style="width:5200px;height:3600px"></canvas></div>"""
    js = f"""
const st=document.getElementById('bg-stars').getContext('2d'); const r=rng(7); const S=[];
for(let i=0;i<380;i++) S.push([r()*3120,r()*1880,r()*1.6+0.3,r()*6.28,0.4+r()*1.2]);
const fg=document.getElementById('bg-fore').getContext('2d'); const r2=rng(11); const F=[];
for(let i=0;i<70;i++) F.push([r2()*2600,r2()*1800,r2()*3+1.5,r2()*6.28]);
const clock={{t:0}};
function draw(){{const t=clock.t; st.clearRect(0,0,3120,1880);
 for(const s of S){{const a=0.25+0.35*(0.5+0.5*Math.sin(t*s[4]+s[3])); st.fillStyle='rgba(200,225,255,'+a.toFixed(3)+')';
  st.beginPath(); st.arc(s[0]+Math.sin(t*0.05+s[3])*6, s[1], s[2], 0, 6.283); st.fill();}}
 fg.clearRect(0,0,2600,1800);
 for(const f of F){{const x=f[0]+Math.sin(t*0.07+f[3])*20, y=(f[1]+t*1.5)%1800, R=f[2]*5; const g=fg.createRadialGradient(x,y,0,x,y,R);
   g.addColorStop(0,'rgba(94,200,242,0.16)'); g.addColorStop(1,'rgba(94,200,242,0)'); fg.fillStyle=g; fg.fillRect(x-R,y-R,2*R,2*R);}}
}}
tl.fromTo(clock,{{t:0}},{{t:D,duration:D,ease:'none',onUpdate:draw}},0);
draw();
{chr(10).join(pans)}
"""
    return scene("bg", DURATION, css, html, js)

def fx_html():
    # letterbox bars only during SUPPORT (S) sections; fade from / to black
    bars = []
    for sid, a, b in SECTIONS:
        if sid.startswith("s"):
            bars.append(f"tl.to(['#fx-top','#fx-bot'],{{scaleY:1,duration:0.5,ease:'power2.out'}},{LEAD + a - 0.1:.3f});")
            bars.append(f"tl.to(['#fx-top','#fx-bot'],{{scaleY:0,duration:0.4,ease:'power2.in'}},{LEAD + b - 0.2:.3f});")
    css = """
#fx-vig{position:absolute;inset:0;background:radial-gradient(ellipse at 50% 50%,transparent 58%,rgba(0,0,0,.08) 80%,rgba(0,0,0,.08) 100%);}
#fx-grain{position:absolute;inset:-64px;background-image:url('assets/grain.png');background-size:512px 512px;opacity:.07;mix-blend-mode:overlay;}
#fx-top,#fx-bot{position:absolute;left:0;width:1920px;height:60px;background:#000;}
#fx-top{top:0;transform-origin:50% 0;} #fx-bot{bottom:0;transform-origin:50% 100%;}
#fx-black{position:absolute;inset:0;background:#000;}
"""
    html = """<div class="world" id="fx-world"><div id="fx-vig"></div><div id="fx-grain"></div><div id="fx-top"></div><div id="fx-bot"></div><div id="fx-black"></div></div>"""
    js = f"""
tl.set(['#fx-top','#fx-bot'],{{scaleY:0}},0);
tl.fromTo('#fx-black',{{opacity:1}},{{opacity:0,duration:0.6,ease:'power2.out'}},0);
tl.to('#fx-black',{{opacity:1,duration:0.9,ease:'power2.in'}},{DURATION - 0.95:.3f});
const g=document.getElementById('fx-grain'); const gr=rng(3); const JX=[],JY=[]; for(let i=0;i<64;i++){{JX.push(Math.floor(gr()*512));JY.push(Math.floor(gr()*512));}}
const gc={{f:0}}; tl.fromTo(gc,{{f:0}},{{f:{int(DURATION*FPS)},duration:D,ease:'none',onUpdate:()=>{{const i=Math.floor(gc.f)%64; g.style.backgroundPosition=JX[i]+'px '+JY[i]+'px';}}}},0);
{chr(10).join(bars)}
"""
    return scene("fx", DURATION, css, html, js).replace("tl.fromTo('#fx-world',{scale:1.0},{scale:1.03,duration:D,ease:'none'},0);", "")

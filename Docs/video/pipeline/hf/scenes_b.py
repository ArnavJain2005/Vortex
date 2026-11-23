"""S-b zoom-through, K-4 pipeline, S-c main.py, K-5 gauges."""
from common import *
from scenes_a import sub, dur

# ---------------------------------------------------------------- S-b
def sb():
    L = lambda v: local("sb", v)
    css = """
#sb-node{position:absolute;left:690px;top:295px;width:140px;height:140px;border-radius:50%;border:3px solid #5ec8f2;
  background:radial-gradient(circle,#1b2a6e 0%,#121a45 70%);box-shadow:0 0 40px rgba(94,200,242,.45),inset 0 0 30px rgba(94,200,242,.25);}
#sb-node .n{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:22px;letter-spacing:.14em;}
#sb-inner{position:absolute;inset:0;background:radial-gradient(ellipse at 50% 40%,#16205a,#0b1035 75%);}
#sb-rail{position:absolute;left:150px;top:328px;width:1620px;height:4px;border-radius:2px;background:#5ec8f2;box-shadow:0 0 18px #5ec8f2;}
.sb-slot{position:absolute;top:255px;width:250px;height:150px;border-radius:18px;border:2px dashed rgba(94,200,242,.35);}
#sb-txt{position:absolute;left:0;width:1920px;top:560px;text-align:center;font-size:46px;font-weight:700;letter-spacing:.3em;color:rgba(243,245,255,.85);}
"""
    slots = "".join(f'<div class="sb-slot" id="sb-s{i}" style="left:{110 + i*290}px"></div>' for i in range(6))
    html = f"""<div class="world" id="sb-world">
<div id="sb-inner"><div id="sb-rail"></div>{slots}<div id="sb-txt">IN STAGES</div></div>
<div id="sb-node"><div class="n">VORTEX</div></div></div>"""
    js = sub("""
// zoom-through: the camera dives into the VORTEX node until its inside fills the frame, then it opens like an iris
tl.set('#sb-inner',{clipPath:'circle(0px at 760px 365px)'},0);
tl.fromTo('#sb-node',{scale:1},{scale:16,duration:0.9,ease:'power3.in'},@in@);
tl.to('#sb-node .n',{opacity:0,duration:0.25},@in@+0.1);
tl.to('#sb-inner',{clipPath:'circle(1400px at 760px 365px)',duration:0.75,ease:'expo.out'},@in@+0.75);
tl.to('#sb-node',{opacity:0,duration:0.2},@in@+0.9);
tl.fromTo('#sb-rail',{scaleX:0,transformOrigin:'0 50%'},{scaleX:1,duration:0.9,ease:'expo.out'},@in@+0.95);
tl.fromTo('.sb-slot',{opacity:0,y:20},{opacity:1,y:0,duration:0.5,ease:'expo.out',stagger:0.08},@stages@-0.4);
tl.fromTo('#sb-txt',{opacity:0,filter:'blur(8px)'},{opacity:1,filter:'blur(0px)',duration:0.4},@stages@-0.15);
tl.to('#sb-txt',{opacity:0,filter:'blur(8px)',duration:0.25},@ho@);
""", **{"in": L(W("Inside", 35.6)) - 0.05, "stages": L(W("stages", 37.2)), "ho": round(dur("sb") - 0.5, 3)})
    return scene("sb", dur("sb"), css, html, js)

# ---------------------------------------------------------------- K-4
BLOCKS = [("Calibrate", "gyro bias · gravity · tilt, from a still interval"),
          ("15-state filter", "error-state Kalman filter on strapdown integration"),
          ("Stillness", "V1 witness · zero-velocity + gyro-bias update"),
          ("Speed & centre envelope", "V2 speed bound · V2P running centre"),
          ("Gravity alignment", "windowed tilt correction when the gyro is noisy"),
          ("Offline smoother", "forward-backward (RTS) pass over the whole file")]

def k4():
    L = lambda v: local("k4", v)
    css = """
#k4-rail{position:absolute;left:150px;top:328px;width:1620px;height:4px;border-radius:2px;background:#5ec8f2;box-shadow:0 0 18px #5ec8f2;}
.k4-b{position:absolute;top:255px;width:250px;height:150px;border-radius:18px;background:rgba(18,26,69,.95);
  border:2px solid rgba(94,200,242,.55);box-shadow:0 10px 40px rgba(0,0,0,.45);}
.k4-b .nm{position:absolute;left:0;right:0;top:20px;text-align:center;font-size:25px;font-weight:700;padding:0 10px;line-height:1.15;}
.k4-b .ix{position:absolute;left:16px;bottom:12px;font-family:'JetBrains Mono',monospace;font-size:20px;color:#5ec8f2;}
.k4-sub{position:absolute;top:418px;width:262px;font-family:'JetBrains Mono',monospace;font-size:19px;line-height:1.32;color:rgba(243,245,255,.8);text-align:center;}
.k4-slot{position:absolute;top:255px;width:250px;height:150px;border-radius:18px;border:2px dashed rgba(94,200,242,.35);}
#k4-prior{position:absolute;left:1010px;top:214px;padding:5px 16px;border-radius:999px;background:#c38bf5;color:#0a0e2e;font-weight:900;font-size:24px;letter-spacing:.14em;}
#k4-lane{position:absolute;left:150px;top:540px;width:1340px;height:54px;border-radius:12px;border:1px solid rgba(245,163,94,.45);
  background:rgba(245,163,94,.07);font-family:'JetBrains Mono',monospace;font-size:20px;color:#f5a35e;display:flex;align-items:center;padding:0 22px;white-space:nowrap;}
#k4-stage{position:absolute;left:150px;top:630px;width:1340px;height:400px;}
.k4-h{position:absolute;inset:0;}
.k4-cap{position:absolute;left:0;top:0;font-size:24px;font-weight:700;color:#5ec8f2;letter-spacing:.06em;}
/* approved 3D #2: line-shaded drone silhouette (four rotors, no face) */
#k4-d3{position:absolute;left:470px;top:40px;width:400px;height:330px;perspective:900px;}
#k4-dr{position:absolute;left:200px;top:180px;width:0;height:0;transform-style:preserve-3d;}
.k4-arm{position:absolute;left:-150px;top:-3px;width:300px;height:6px;border-radius:3px;background:#5ec8f2;box-shadow:0 0 12px rgba(94,200,242,.7);}
.k4-rot{position:absolute;width:110px;height:110px;margin:-55px 0 0 -55px;border-radius:50%;border:3px solid #7ee0b5;box-shadow:0 0 12px rgba(126,224,181,.5);}
.k4-body{position:absolute;left:-42px;top:-42px;width:84px;height:84px;border-radius:22px;border:4px solid #f3f5ff;background:rgba(18,26,69,.9);}
#k4-g{position:absolute;left:880px;top:40px;width:120px;height:300px;}
#k4-gl{position:absolute;left:1040px;top:120px;font-size:22px;color:rgba(243,245,255,.8);}
#k4-lvl{position:absolute;left:300px;top:330px;width:740px;height:2px;background:rgba(243,245,255,.25);}
.k4-cell{position:absolute;width:86px;height:46px;border-radius:9px;border:2px solid rgba(94,200,242,.4);}
.k4-rl{position:absolute;font-size:21px;color:rgba(243,245,255,.85);text-align:right;width:200px;}
#k4-dial{position:absolute;left:470px;top:50px;}
#k4-env{position:absolute;left:380px;top:20px;}
#k4-sm{position:absolute;left:180px;top:30px;}
"""
    xs = [110 + i * 290 for i in range(6)]
    blocks = "".join(f'<div class="k4-slot" style="left:{x}px"></div><div class="k4-b" id="k4-b{i}" style="left:{x}px"><div class="nm">{n}</div><div class="ix" data-layout-ignore>0{i+1}</div></div>'
                     f'<div class="k4-sub mono" id="k4-s{i}" style="left:{x - 6}px"></div>' for i, (x, (n, s)) in enumerate(zip(xs, BLOCKS)))
    cells = ""
    rows = ["position", "velocity", "attitude", "gyro bias", "accel bias"]
    for r_, nm in enumerate(rows):
        cells += f'<div class="k4-rl" style="left:200px;top:{30 + r_*62}px">{nm}</div>'
        for c in range(3):
            cells += f'<div class="k4-cell" id="k4-c{r_}{c}" style="left:{430 + c*102}px;top:{20 + r_*62}px"></div>'
    html = f"""<div class="world" id="k4-world">
<div id="k4-rail"></div>{blocks}
<div id="k4-prior">PRIOR</div>
<div id="k4-lane">gaps widen uncertainty · no rows invented · 0.5 s velocity-decay forecast on dead rows</div>
<div id="k4-stage">
 <div class="k4-h" id="k4-h0"><div class="k4-cap">calibrate: level from a still interval</div>
  <div id="k4-lvl"></div>
  <div id="k4-d3"><div id="k4-dr"><div class="k4-arm" style="transform:rotateZ(45deg)"></div><div class="k4-arm" style="transform:rotateZ(-45deg)"></div>
   <div class="k4-rot" style="transform:translate3d(106px,106px,0)"></div><div class="k4-rot" style="transform:translate3d(-106px,106px,0)"></div>
   <div class="k4-rot" style="transform:translate3d(106px,-106px,0)"></div><div class="k4-rot" style="transform:translate3d(-106px,-106px,0)"></div>
   <div class="k4-body"></div></div></div>
  <svg id="k4-g" viewBox="0 0 120 300"><line id="k4-gv" x1="60" y1="20" x2="60" y2="250" stroke="#f5a35e" stroke-width="6" stroke-linecap="round"/>
   <path d="M40 232 L60 270 L80 232" fill="none" stroke="#f5a35e" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/></svg>
  <div id="k4-gl">gravity</div></div>
 <div class="k4-h" id="k4-h1"><div class="k4-cap">15 error states, x · y · z</div>{cells}</div>
 <div class="k4-h" id="k4-h2"><div class="k4-cap">genuinely still → velocity pinned to zero</div>
  <svg id="k4-dial" width="400" height="320" viewBox="0 0 400 320"><path d="M60 260 A150 150 0 0 1 340 260" fill="none" stroke="rgba(243,245,255,.25)" stroke-width="10" stroke-linecap="round"/>
   <text x="200" y="300" fill="#f3f5ff" font-family="JetBrains Mono" font-size="26" text-anchor="middle">v = <tspan id="k4-v">0.42</tspan> m/s</text>
   <g id="k4-needle"><line x1="200" y1="260" x2="200" y2="125" stroke="#7ee0b5" stroke-width="7" stroke-linecap="round"/></g><circle cx="200" cy="260" r="12" fill="#7ee0b5"/></svg></div>
 <div class="k4-h" id="k4-h3"><div class="k4-cap" style="color:#c38bf5">a cautious assumption · not a sensor · no control</div>
  <svg id="k4-env" width="600" height="380" viewBox="0 0 600 380"><ellipse id="k4-eb" cx="300" cy="200" rx="230" ry="150" fill="rgba(195,139,245,.07)" stroke="#c38bf5" stroke-width="3" stroke-dasharray="12 10"/>
   <circle cx="300" cy="200" r="9" fill="#c38bf5"/><text x="300" y="240" fill="#c38bf5" font-family="Inter" font-size="22" text-anchor="middle">running centre</text>
   <circle id="k4-ed" cx="300" cy="200" r="11" fill="#7ee0b5"/></svg></div>
 <div class="k4-h" id="k4-h4"><div class="k4-cap">gravity alignment: tilt corrected slowly</div></div>
 <div class="k4-h" id="k4-h5"><div class="k4-cap">later readings revise earlier ones</div>
  <svg id="k4-sm" width="1000" height="360" viewBox="0 0 1000 360">
   <path id="k4-kink" d="M40 260 C 200 240 300 150 420 200 L 470 60 L 520 210 C 640 260 800 180 960 150" fill="none" stroke="#5ec8f2" stroke-width="5" stroke-linecap="round"/>
   <path id="k4-fix"  d="M40 260 C 200 240 300 150 420 200 L 470 190 L 520 210 C 640 260 800 180 960 150" fill="none" stroke="#7ee0b5" stroke-width="5" stroke-linecap="round" opacity="0"/>
   <g id="k4-sweep"><path d="M0 -16 L-30 0 L0 16 Z" fill="#7ee0b5"/></g>
   <text x="980" y="190" fill="rgba(243,245,255,.6)" font-family="JetBrains Mono" font-size="18" text-anchor="end">schematic</text></svg></div>
</div></div>"""
    cues = [L(W("calibrates", 38.5)), L(W("15-state", 41.4)), L(W("When", 44.7)), L(W("prior", 50.7)),
            L(W("Gravity", 58.2)), L(W("smoother", 62.1))]
    js = sub("""
const C=@cues@, S=@subs@;
tl.set('#k4-dr',{rotationX:64,rotationY:-18,rotationZ:14},0);
gsap.set(['.k4-b','.k4-sub','#k4-prior','#k4-lane','.k4-h'],{opacity:0});
tl.fromTo('#k4-rail',{opacity:1},{opacity:1,duration:0.01},0);
// one block per sentence, each with its subtitle typed on
for(let i=0;i<6;i++){
  tl.fromTo('#k4-b'+i,{opacity:0,y:-40,scale:0.9},{opacity:1,y:0,scale:1,duration:0.55,ease:'expo.out'},C[i]-0.1);
  tl.set('#k4-s'+i,{opacity:1},C[i]+0.15); typeOn(tl,'#k4-s'+i,S[i],C[i]+0.15,Math.min(1.3,S[i].length*0.028));
  tl.to('#k4-b'+i,{borderColor:'#7ee0b5',boxShadow:'0 0 36px rgba(126,224,181,.45)',duration:0.3},C[i]+0.1);
  if(i>0) tl.to('#k4-b'+(i-1),{borderColor:'rgba(94,200,242,.55)',boxShadow:'0 10px 40px rgba(0,0,0,.45)',duration:0.4},C[i]);
  // stage: one hero visual at a time
  const e=(i<5?C[i+1]:@endall@)-0.3;
  tl.fromTo('#k4-h'+i,{opacity:0,y:20},{opacity:1,y:0,duration:0.45,ease:'expo.out'},C[i]+0.05);
  if(i!==0&&i!==4) tl.to('#k4-h'+i,{opacity:0,y:-10,duration:0.3,ease:'power2.in'},e);
}
// 0 calibrate (3D): the drone silhouette starts tilted, then levels against gravity
tl.fromTo('#k4-dr',{rotationX:64,rotationY:-18,rotationZ:14},{rotationX:58,rotationY:0,rotationZ:0,duration:1.8,ease:'power3.inOut'},C[0]+0.5);
tl.fromTo('#k4-gv',{drawSVG:'0%'},{drawSVG:'100%',duration:0.6,ease:'power2.out'},C[0]+0.2);
tl.to('#k4-h0',{opacity:0,duration:0.3},C[1]-0.3);
// 1 filter: 15 slots fill row by row
for(let r=0;r<5;r++) for(let c=0;c<3;c++) tl.to('#k4-c'+r+c,{backgroundColor:'rgba(94,200,242,.45)',borderColor:'#5ec8f2',duration:0.18},C[1]+0.4+r*0.22+c*0.06);
// 2 stillness: the needle swings, then snaps to zero on 'zero'
const vv={v:0.42}; const vt=document.getElementById('k4-v');
tl.fromTo('#k4-needle',{rotation:-38,svgOrigin:'200 260'},{rotation:24,duration:1.0,ease:'sine.inOut',svgOrigin:'200 260'},C[2]+0.3);
tl.to('#k4-needle',{rotation:0,duration:0.35,ease:'back.out(2)',svgOrigin:'200 260'},@zero@-0.05);
tl.fromTo(vv,{v:0.42},{v:0,duration:0.35,ease:'power3.out',onUpdate:()=>{vt.textContent=vv.v.toFixed(2);}},@zero@-0.05);
// 3 envelope: a dot wanders but stays inside the soft boundary; PRIOR tag in violet
tl.fromTo('#k4-ed',{attr:{cx:300,cy:200}},{keyframes:[{attr:{cx:470,cy:140},duration:0.9},{attr:{cx:410,cy:290},duration:0.9},{attr:{cx:180,cy:240},duration:0.9},{attr:{cx:260,cy:130},duration:0.9},{attr:{cx:330,cy:220},duration:0.9}],ease:'sine.inOut'},C[3]+0.3);
tl.fromTo('#k4-prior',{opacity:0,scale:0.7},{opacity:1,scale:1,duration:0.45,ease:'back.out(1.8)'},C[3]-0.05);
tl.fromTo('#k4-eb',{drawSVG:'0%'},{drawSVG:'100%',duration:0.9,ease:'power2.inOut'},C[3]+0.15);
// 4 gravity alignment (3D reprise): the drone reappears tilted and rights itself slowly
tl.to('#k4-h0',{opacity:1,duration:0.35},C[4]+0.05);
tl.set('#k4-h0 .k4-cap',{opacity:0},C[4]); tl.set('#k4-h4',{opacity:1},C[4]+0.05);
tl.fromTo('#k4-dr',{rotationX:58,rotationY:22,rotationZ:-16},{rotationX:58,rotationY:0,rotationZ:0,duration:2.6,ease:'power1.inOut'},C[4]+0.35);
tl.to(['#k4-h0','#k4-h4'],{opacity:0,duration:0.3},C[5]-0.3);
// 5 smoother: an arrow sweeps backwards along the path and straightens the earlier kink
tl.fromTo('#k4-kink',{drawSVG:'0%'},{drawSVG:'100%',duration:0.8,ease:'power2.out'},C[5]+0.1);
tl.fromTo('#k4-sweep',{opacity:0},{opacity:1,duration:0.2},@revise@-0.4);
tl.fromTo('#k4-sweep',{motionPath:{path:'#k4-fix',align:'#k4-fix',alignOrigin:[0.5,0.5],start:1,end:1}},{motionPath:{path:'#k4-fix',align:'#k4-fix',alignOrigin:[0.5,0.5],start:1,end:0},duration:1.5,ease:'power2.inOut'},@revise@-0.4);
tl.to('#k4-kink',{morphSVG:'#k4-fix',stroke:'#7ee0b5',duration:0.6,ease:'power3.inOut'},@revise@+0.45);
// fault lane, then the full pipeline holds for its end pause
tl.fromTo('#k4-lane',{opacity:0,y:10},{opacity:1,y:0,duration:0.5,ease:'expo.out'},@lane@);
tl.to('#k4-b5',{borderColor:'rgba(94,200,242,.55)',boxShadow:'0 10px 40px rgba(0,0,0,.45)',duration:0.4},@endall@);
tl.to('#k4-h5',{opacity:0,duration:0.4},@endall@+0.2);
// hand-off: the pipeline collapses into main.py (S-c)
tl.to(['.k4-sub','#k4-lane','#k4-prior','.k4-slot'],{opacity:0,duration:0.3},@ho@);
tl.to('.k4-b',{x:(i)=>[850,560,270,-20,-310,-600][i],y:110,scale:0.3,opacity:0,duration:0.6,ease:'power3.in',stagger:0.03},@ho@+0.05);
tl.to('#k4-rail',{scaleX:0,transformOrigin:'50% 50%',opacity:0,duration:0.55,ease:'power3.in'},@ho@+0.05);
""", cues=[round(c, 3) for c in cues], subs=[s for _, s in BLOCKS], zero=L(W("zero", 48.7)), revise=L(W("revise", 63.8)),
        lane=L(W("earlier", 64.7)) - 0.6, endall=L(W("ones", 65.4)) + 0.5, ho=round(dur("k4") - 0.75, 3)).replace("'", "'")
    js = js.replace("['gyro", "['gyro")
    return scene("k4", dur("k4"), css, html, js)

# ---------------------------------------------------------------- S-c (voice only)
def sc():
    L = lambda v: local("sc", v)
    css = """
#sc-file{position:absolute;left:840px;top:300px;width:240px;height:300px;}
#sc-name{position:absolute;left:0;width:1920px;top:640px;text-align:center;font-family:'JetBrains Mono',monospace;font-size:52px;font-weight:700;color:#f3f5ff;}
#sc-std{position:absolute;left:0;width:1920px;top:718px;text-align:center;font-size:30px;letter-spacing:.24em;color:#7ee0b5;font-weight:700;}
#sc-svg{position:absolute;left:0;top:0;width:1920px;height:1080px;}
"""
    html = """<div class="world" id="sc-world">
<svg id="sc-svg" viewBox="0 0 1920 1080"><path id="sc-thread" d="M -40 452 C 400 452 640 452 840 452 L 1080 452 C 1280 452 1520 452 1960 452" fill="none" stroke="#5ec8f2" stroke-width="5" stroke-linecap="round"/></svg>
<svg id="sc-file" viewBox="0 0 240 300"><path d="M10 10 L170 10 L230 70 L230 290 L10 290 Z" fill="#121a45" stroke="#f3f5ff" stroke-width="5" stroke-linejoin="round"/>
<path d="M170 10 L170 70 L230 70" fill="none" stroke="#f3f5ff" stroke-width="5" stroke-linejoin="round"/>
<g stroke="rgba(94,200,242,.55)" stroke-width="7" stroke-linecap="round"><line x1="40" y1="110" x2="160" y2="110"/><line x1="40" y1="140" x2="190" y2="140"/><line x1="40" y1="200" x2="130" y2="200"/><line x1="40" y1="230" x2="180" y2="230"/></g></svg>
<div id="sc-name">main.py</div><div id="sc-std">ONE THREAD</div></div>"""
    js = sub("""
tl.fromTo('#sc-file',{opacity:0,scale:0.4,rotation:-8},{opacity:1,scale:1,rotation:0,duration:0.7,ease:'expo.out'},0.45);
tl.fromTo('#sc-name',{opacity:0,filter:'blur(8px)'},{opacity:1,filter:'blur(0px)',duration:0.4},@file@-0.2);
tl.fromTo('#sc-thread',{drawSVG:'50% 50%'},{drawSVG:'0% 100%',duration:1.1,ease:'expo.out'},@thread@-0.1);
tl.to('#sc-thread',{filter:'drop-shadow(0 0 10px #5ec8f2)',duration:0.4},@thread@+0.3);
tl.fromTo('#sc-std',{opacity:0,y:12},{opacity:1,y:0,duration:0.5,ease:'expo.out'},@single@);
// hand-off: main.py splits into the two gauges
tl.to('#sc-file',{scale:0.2,opacity:0,duration:0.5,ease:'power3.in'},@ho@);
tl.to(['#sc-name','#sc-std','#sc-thread'],{opacity:0,duration:0.35},@ho@);
""", file=L(W("python", 69.9)), thread=L(W("thread", 71.7)), single=L(W("single", 71.4)) - 0.3, ho=round(dur("sc") - 0.45, 3))
    return scene("sc", dur("sc"), css, html, js)

# ---------------------------------------------------------------- K-5 (voice only, full frame)
def k5():
    L = lambda v: local("k5", v)
    def gauge(gid, cx, label, unit, lim):
        return f"""<svg class="k5-g" id="k5-{gid}" style="left:{cx - 260}px" width="520" height="440" viewBox="0 0 520 440">
<path d="M118.58 371.42 A200 200 0 1 1 401.42 371.42" fill="none" stroke="rgba(243,245,255,.12)" stroke-width="30" stroke-linecap="round"/>
<path id="k5-{gid}-head" d="M118.58 371.42 A200 200 0 1 1 401.42 371.42" fill="none" stroke="rgba(126,224,181,.0)" stroke-width="30" stroke-linecap="round"/>
<path id="k5-{gid}-arc" d="M118.58 371.42 A200 200 0 1 1 401.42 371.42" fill="none" stroke="#5ec8f2" stroke-width="30" stroke-linecap="round"/>
<line id="k5-{gid}-lim" x1="0" y1="0" x2="0" y2="0" stroke="#ff6b6b" stroke-width="8" stroke-linecap="round"/>
<text x="260" y="250" text-anchor="middle" fill="#f3f5ff" font-family="Inter" font-weight="900" font-size="92"><tspan id="k5-{gid}-n">0.0</tspan><tspan font-size="44" font-weight="700" dx="10">{unit}</tspan></text>
<text x="260" y="300" text-anchor="middle" fill="rgba(243,245,255,.7)" font-family="Inter" font-size="26">of {lim} limit</text>
<text x="260" y="420" text-anchor="middle" fill="#f3f5ff" font-family="Inter" font-weight="700" font-size="30">{label}</text></svg>"""
    css = """
.k5-g{position:absolute;top:130px;overflow:visible;}
#k5-docker{position:absolute;left:1065px;top:600px;width:520px;text-align:center;font-family:'JetBrains Mono',monospace;font-size:27px;color:rgba(243,245,255,.6);}
#k5-chips{position:absolute;left:0;width:1920px;top:770px;display:flex;justify-content:center;gap:18px;flex-wrap:wrap;padding:0 160px;}
.k5-c{padding:12px 22px;border-radius:999px;border:1px solid rgba(126,224,181,.5);background:rgba(126,224,181,.08);font-size:25px;color:#f3f5ff;}
#k5-well{position:absolute;left:0;width:1920px;top:62px;text-align:center;font-size:30px;font-weight:700;letter-spacing:.2em;color:#7ee0b5;}
"""
    chips = ["one thread", "standard library only", "never crashes on any readable input: writes a valid pose for every row", "521 tests passed"]
    html = f"""<div class="world" id="k5-world">
{gauge('mem', 600, 'peak memory · whole run', 'MB', '8 MB')}{gauge('cpu', 1325, 'per IMU-second', 'ms', '20 ms')}
<div id="k5-docker">Linux Docker</div>
<div id="k5-well">WELL INSIDE THE LIMITS</div>
<div id="k5-chips">{''.join(f'<div class="k5-c" id="k5-c{i}">{c}</div>' for i, c in enumerate(chips))}</div></div>"""
    js = sub("""
// arc geometry: 270-degree sweep; value fraction f of the limit
function arcPt(f){ const a0=Math.PI*(0.75), a=a0+f*Math.PI*1.5; return [260+200*Math.cos(a), 230+200*Math.sin(a)]; }
['mem','cpu'].forEach(g=>{ const p=arcPt(1.0); const l=document.getElementById('k5-'+g+'-lim');
  const dx=Math.cos(Math.PI*2.25), dy=Math.sin(Math.PI*2.25); l.setAttribute('x1',p[0]-dx*26); l.setAttribute('y1',p[1]-dy*26); l.setAttribute('x2',p[0]+dx*26); l.setAttribute('y2',p[1]+dy*26); });
tl.fromTo('.k5-g',{opacity:0,scale:0.6,transformOrigin:'50% 50%'},{opacity:1,scale:1,duration:0.6,ease:'expo.out',stagger:0.08},0.15);
tl.set(['#k5-mem-arc','#k5-cpu-arc'],{drawSVG:'0%'},0);
tl.fromTo(['#k5-mem-lim','#k5-cpu-lim'],{opacity:0},{opacity:1,duration:0.3},0.6);
// 3.5 MB of 8 MB; 6.6 ms of 20 ms: arcs fill and numbers count up, landing on the spoken word
tl.to('#k5-mem-arc',{drawSVG:'0% '+(3.5/8*100).toFixed(2)+'%',duration:1.0,ease:'power3.out'},@mem@-0.6);
countUp(tl,'#k5-mem-n',3.5,1,@mem@-0.6,1.0);
tl.to('#k5-cpu-arc',{drawSVG:'0% '+(6.6/20*100).toFixed(2)+'%',duration:1.0,ease:'power3.out'},@cpu@-0.6);
countUp(tl,'#k5-cpu-n',6.6,1,@cpu@-0.6,1.0);
inBlur(tl,'#k5-docker',@cpu@+0.3,0.4);
// headroom glows mint on 'well inside the limits'
tl.set(['#k5-mem-head','#k5-cpu-head'],{drawSVG:'100% 100%'},0);
tl.to('#k5-mem-head',{drawSVG:(3.5/8*100+2).toFixed(2)+'% 100%',stroke:'rgba(126,224,181,.55)',duration:0.8,ease:'power2.out'},@well@);
tl.to('#k5-cpu-head',{drawSVG:(6.6/20*100+2).toFixed(2)+'% 100%',stroke:'rgba(126,224,181,.55)',duration:0.8,ease:'power2.out'},@well@);
tl.fromTo('#k5-well',{opacity:0,filter:'blur(8px)'},{opacity:1,filter:'blur(0px)',duration:0.4},@well@);
tl.fromTo('.k5-c',{opacity:0,y:16},{opacity:1,y:0,duration:0.45,ease:'expo.out',stagger:0.25},@cpu@+1.3);
// hand-off: whip-pan left into the results board
tl.to('#k5-world',{x:-1500,filter:'blur(14px)',duration:0.32,ease:'power3.in'},@ho@);
""", mem=L(W("3.5", 72.9)), cpu=L(W("6.6", 75.4)), well=L(W("well", 79.5)), ho=round(dur("k5") - 0.62, 3))
    return scene("k5", dur("k5"), css, html, js)

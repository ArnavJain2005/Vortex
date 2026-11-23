"""K-1 title, S-a Pip bridge + waveform, K-2 CSV card, K-3 offline rebuild."""
from common import *

def sub(s, **kw):
    for k, v in kw.items(): s = s.replace("@" + k + "@", str(v))
    return s

def dur(sid):
    i = IDS.index(sid); return host_end(i) - host_start(i)

# ---------------------------------------------------------------- K-1
def k1():
    L = lambda v: local("k1", v)
    css = """
#k1-dots{position:absolute;left:0;top:0;}
#k1-word{position:absolute;left:0;width:1920px;top:120px;text-align:center;font-weight:900;font-size:168px;letter-spacing:.16em;
  padding-left:.16em;color:#f3f5ff;text-shadow:0 0 30px rgba(94,200,242,.45);}
#k1-sub{position:absolute;left:0;width:1920px;top:322px;text-align:center;font-size:30px;font-weight:700;letter-spacing:.22em;color:#5ec8f2;}
#k1-sweep{position:absolute;left:560px;top:120px;width:800px;height:200px;}
"""
    html = """<div class="world" id="k1-world">
<canvas id="k1-dots" width="1920" height="1080"></canvas>
<div id="k1-word">VORTEX</div><div class="sweep" id="k1-sweep"></div>
<div id="k1-sub">TRACK 3 · PATH FINDER</div></div>"""
    js = sub("""
const cv=document.getElementById('k1-dots'), cx=cv.getContext('2d');
// sample the wordmark's own shape so the IMU sample dots land on the letters
const off=document.createElement('canvas'); off.width=1920; off.height=1080; const o=off.getContext('2d');
o.font='900 168px Inter'; o.textAlign='center'; o.textBaseline='alphabetic'; o.fillStyle='#fff';
o.letterSpacing='27px'; o.fillText('VORTEX',973,282);
const img=o.getImageData(0,0,1920,1080).data; const T=[]; const r=rng(5);
for(let y=100;y<300;y+=6) for(let x=400;x<1520;x+=6){ if(img[(y*1920+x)*4+3]>128) T.push([x,y]); }
const N=T.length, S=[];
for(let i=0;i<N;i++){ const a=r()*6.283, d=500+r()*700; S.push([960+Math.cos(a)*d, 300+Math.sin(a)*d*0.6, r()*0.5, r()]); }
const k={p:0, s:0}; const A=@a@, B=@b@;
function draw(){ cx.clearRect(0,0,1920,1080);
  for(let i=0;i<N;i++){ const s=S[i], t=T[i];
    let q=Math.min(1,Math.max(0,(k.p - s[2]*0.45)/0.55)); q=1-Math.pow(1-q,3);
    const x=s[0]+(t[0]-s[0])*q, y=s[1]+(t[1]-s[1])*q + Math.sin((1-q)*6+s[3]*6)*18*(1-q);
    const sc=k.s; const xx=x+(s[0]-x)*sc*0.0, yy=y - sc*260;
    cx.globalAlpha=(0.35+0.65*q)*(1-k.s); cx.fillStyle=q>0.98?'#f3f5ff':'#5ec8f2';
    cx.beginPath(); cx.arc(xx,yy,2.2,0,6.283); cx.fill(); } }
tl.fromTo(k,{p:0},{p:1,duration:B-A,ease:'none',onUpdate:draw},A);
tl.fromTo('#k1-word',{opacity:0,filter:'blur(6px)'},{opacity:1,filter:'blur(0px)',duration:0.35,ease:'power2.out'},B-0.12);
tl.to('#k1-dots',{opacity:0,duration:0.3},B+0.05);
sweep(tl,'#k1-sweep',B+0.25);
tl.fromTo('#k1-sub',{opacity:0,scaleX:1.25,filter:'blur(6px)'},{opacity:1,scaleX:1,filter:'blur(0px)',duration:0.8,ease:'expo.out'},@sub@);
// hand-off: title lifts away as the circle glides to the corner
tl.to(['#k1-word','#k1-sub'],{y:-60,opacity:0,filter:'blur(8px)',duration:0.5,ease:'power3.in'},@x@);
draw();
""", a=L(0.2), b=L(W("Vortex", 3.0)), x=round(dur("k1") - 0.55, 3), sub=L(W("Arnav", 1.1)) + 0.4)
    return scene("k1", dur("k1"), css, html, js)

# ---------------------------------------------------------------- S-a
def sa():
    L = lambda v: local("sa", v)
    css = """
#sa-card{position:absolute;left:96px;top:92px;width:372px;padding:6px 6px 0;border-radius:20px;background:#121a45;
  border:1px solid rgba(94,200,242,.3);box-shadow:0 16px 50px rgba(0,0,0,.5);}
#sa-card img{display:block;width:360px;height:201px;object-fit:cover;border-radius:15px;}
#sa-card .cap{font-size:24px;color:rgba(243,245,255,.75);padding:10px 8px 12px;font-style:italic;}
#sa-wave,#sa-wr,#sa-wb{position:absolute;left:0;top:0;}
#sa-wr{mix-blend-mode:screen;opacity:0;} #sa-wb{mix-blend-mode:screen;opacity:0;}
#sa-lbl{position:absolute;left:1240px;top:620px;font-size:30px;font-weight:700;color:#f5a35e;letter-spacing:.08em;}
#sa-pip{position:absolute;left:162px;top:640px;font-size:24px;font-weight:700;letter-spacing:.2em;color:#5ec8f2;}
"""
    html = """<div class="world" id="sa-world">
<canvas id="sa-wave" width="1920" height="1080"></canvas><canvas id="sa-wr" width="1920" height="1080"></canvas><canvas id="sa-wb" width="1920" height="1080"></canvas>
<div id="sa-card"><img src="assets/pip_still.jpg" alt="Pip"/><div class="cap">from our Pip film</div></div>
<div id="sa-pip">PIP · GYRO</div><div id="sa-lbl">LAST 5 S</div></div>"""
    js = sub("""
const t0=@t0@, tN=@tN@, tG=@tG@, tD=@tD@;     // scene-local times of: start, 'noisy', 'loses rows', 'dies'
const W0=160, W1=1440, Y=470, AMP=120, SPAN=5.0; // waveform box; 5 s of signal across the frame
function state(tau){ return tau<tN?0: tau<tG?1: tau<tD?2:3; }
function sig(tau){ return Math.sin(tau*3.1)*0.55+Math.sin(tau*7.7+1)*0.25+Math.sin(tau*1.3+2)*0.2; }
function jitter(tau){ const i=Math.floor(tau*200); const h=Math.sin(i*12.9898)*43758.5453; return (h-Math.floor(h))*2-1; }
function gap(tau){ const i=Math.floor(tau*3.0); const h=Math.sin(i*78.233)*12345.678; return (h-Math.floor(h))<0.42; }
const ctxs=['sa-wave','sa-wr','sa-wb'].map(id=>document.getElementById(id).getContext('2d'));
const cols=[null,'rgba(255,80,80,.9)','rgba(80,200,255,.9)'];
const clk={t:0};
function draw(){ const t=clk.t; ctxs.forEach((c,ci)=>{ c.clearRect(0,0,1920,1080); c.lineWidth=3.2; c.lineJoin='round';
  let pen=false, lastS=-1;
  for(let px=0;px<=W1-W0;px+=2){ const tau=t-SPAN+px/(W1-W0)*SPAN;
    const s=state(tau); let v=sig(tau); if(s>=1&&s<3) v+=jitter(tau)*0.55; if(s===3) v=0;
    const hide=(s===2&&gap(tau));
    if(hide){ if(pen){c.stroke();} pen=false; continue; }
    if(s!==lastS&&pen){ c.stroke(); pen=false; }
    if(!pen){ c.beginPath(); c.strokeStyle= ci? cols[ci] : (s===3?'#f5a35e':'#5ec8f2'); c.shadowColor=c.strokeStyle; c.shadowBlur=ci?0:10;
      c.moveTo(W0+px,Y-v*AMP); pen=true; lastS=s; } else c.lineTo(W0+px,Y-v*AMP); }
  if(pen) c.stroke();
  // write head
  if(ci===0){ c.fillStyle=state(t)===3?'#f5a35e':'#f3f5ff'; c.beginPath(); c.arc(W1,Y-(state(t)===3?0:sig(t))*AMP,6,0,6.283); c.fill(); }
 }); }
tl.fromTo(clk,{t:t0},{t:@end@,duration:@end@-t0,ease:'none',onUpdate:draw},t0);
// Pip bridge card: ~1.5 s, then dissolves into the waveform's start
tl.fromTo('#sa-card',{opacity:0,y:18,filter:'blur(8px)'},{opacity:1,y:0,filter:'blur(0px)',duration:0.55,ease:'expo.out'},@pip@-0.1);
tl.to('#sa-card',{x:80,y:330,scale:0.35,opacity:0,filter:'blur(10px)',duration:0.8,ease:'power3.in'},@pip@+1.6);
inBlur(tl,'#sa-pip',@pip@+1.9,0.4);
tl.fromTo(['#sa-wave'],{opacity:0},{opacity:1,duration:0.6},t0-0.3);
// glitch on 'dies': RGB split, tear and stutter, then stillness
tl.fromTo(['#sa-wr'],{opacity:0,x:0},{opacity:0.85,x:-14,duration:0.05},tD);
tl.fromTo(['#sa-wb'],{opacity:0,x:0},{opacity:0.85,x:14,duration:0.05},tD);
tl.to(['#sa-wr','#sa-wb'],{x:0,opacity:0,duration:0.06},tD+0.32);
tl.fromTo('#sa-world',{x:0},{keyframes:[{x:-22,duration:0.03},{x:16,duration:0.04},{x:-8,duration:0.03},{x:0,duration:0.05}]},tD);
tl.fromTo('#sa-wave',{clipPath:'inset(0 0 0 0)'},{keyframes:[{clipPath:'inset(38% 0 52% 0)',duration:0.04},{clipPath:'inset(0 0 0 0)',duration:0.05},{clipPath:'inset(55% 0 30% 0)',duration:0.04},{clipPath:'inset(0 0 0 0)',duration:0.05}]},tD+0.02);
tl.fromTo('#sa-lbl',{opacity:0,x:-20},{opacity:1,x:0,duration:0.5,ease:'expo.out'},tD+0.35);
// hand-off: the flat trace compresses towards the CSV card
tl.to(['#sa-wave','#sa-lbl','#sa-pip'],{scaleX:0.42,scaleY:0.6,x:150,y:-40,opacity:0,transformOrigin:'50% 44%',duration:0.6,ease:'power3.in'},@ho@);
draw();
""", t0=L(W("Pip's", 4.6)) + 1.9, tN=L(W("noisy", 10.3)), tG=L(W("loses", 11.0)), tD=L(W("dies", 12.5)),
        pip=L(W("Pip's", 4.6)), end=round(dur("sa"), 3), ho=round(dur("sa") - 0.62, 3))
    return scene("sa", dur("sa"), css, html, js)

# ---------------------------------------------------------------- K-2
def k2():
    L = lambda v: local("k2", v)
    css = """
#k2-card{left:520px;top:150px;width:880px;height:430px;overflow:hidden;}
#k2-card .hd{position:absolute;left:0;right:0;top:0;height:64px;border-bottom:1px solid rgba(94,200,242,.25);
  display:flex;align-items:center;padding:0 28px;font-size:26px;font-weight:700;}
#k2-card .hd span{color:#5ec8f2;font-family:'JetBrains Mono',monospace;}
#k2-cols{position:absolute;left:28px;top:80px;font-size:20px;color:#7ee0b5;letter-spacing:.06em;}
#k2-clip{position:absolute;left:0;right:0;top:112px;bottom:0;overflow:hidden;}
#k2-rows{position:absolute;left:28px;top:6px;}
.k2-r{height:34px;display:flex;align-items:center;gap:12px;}
.k2-r i{display:block;height:12px;border-radius:6px;background:rgba(94,200,242,.32);}
.k2-r b{display:block;width:18px;}
#k2-fade{position:absolute;left:0;right:0;bottom:0;height:120px;background:linear-gradient(transparent,#121a45);}
.k2-b{position:absolute;top:640px;width:200px;height:150px;}
.k2-b .ic{position:absolute;left:50px;top:0;width:100px;height:100px;}
.k2-b .t{position:absolute;left:0;top:108px;width:200px;text-align:center;font-size:26px;font-weight:700;}
.k2-b svg.x{position:absolute;left:10px;top:0;width:180px;height:140px;overflow:visible;}
"""
    # abstract rows (no invented values): one bar for the timestamp, three gyro, three accel
    import random
    rnd = random.Random(4)
    rows = []
    for i in range(16):
        cells = '<i style="width:210px"></i>' + "".join(f'<i style="width:{rnd.randint(52, 78)}px"></i>' for _ in range(3)) + '<b></b>' + \
                "".join(f'<i style="width:{rnd.randint(52, 78)}px;background:rgba(126,224,181,.28)"></i>' for _ in range(3))
        rows.append(f'<div class="k2-r">{cells}</div>')
    badge = lambda k, x, label, path: f"""<div class="k2-b" id="k2-b{k}" style="left:{x}px"><svg class="ic" viewBox="0 0 100 100" fill="none" stroke="#f3f5ff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">{path}</svg>
<div class="t">{label}</div><svg class="x" viewBox="0 0 180 140"><line id="k2-x{k}" x1="18" y1="120" x2="162" y2="14" stroke="#ff6b6b" stroke-width="7" stroke-linecap="round"/></svg></div>"""
    gps = '<circle cx="50" cy="42" r="20"/><path d="M50 62 L50 90"/><path d="M28 42 A22 22 0 0 1 72 42" /><circle cx="50" cy="42" r="6" fill="#f3f5ff"/>'
    cam = '<rect x="14" y="30" width="72" height="50" rx="8"/><circle cx="50" cy="55" r="15"/><path d="M36 30 L42 20 L58 20 L64 30"/>'
    mp = '<path d="M12 26 L36 16 L64 26 L88 16 L88 74 L64 84 L36 74 L12 84 Z"/><path d="M36 16 L36 74 M64 26 L64 84"/>'
    html = f"""<div class="world" id="k2-world">
<div class="panel" id="k2-card"><div class="hd">a degraded IMU log&nbsp;&nbsp;<span>imu0/data.csv</span></div>
<div id="k2-cols" class="mono">time · gyro · accel</div><div id="k2-clip" data-layout-ignore><div id="k2-rows" data-layout-ignore>{"".join(rows)}</div></div><div id="k2-fade"></div></div>
{badge(1, 560, 'GPS', gps)}{badge(2, 860, 'camera', cam)}{badge(3, 1160, 'map', mp)}</div>"""
    js = sub("""
tl.fromTo('#k2-card',{opacity:0,scaleX:0.45,scaleY:0.2,filter:'blur(8px)'},{opacity:1,scaleX:1,scaleY:1,filter:'blur(0px)',duration:0.7,ease:'expo.out'},0.05);
tl.fromTo('#k2-rows',{y:0},{y:-150,duration:D,ease:'none'},0);
[[1,@g@],[2,@c@],[3,@m@]].forEach(([k,t])=>{
  tl.fromTo('#k2-b'+k,{opacity:0,scale:0.6},{opacity:1,scale:1,duration:0.4,ease:'back.out(1.6)'},t-0.12);
  tl.fromTo('#k2-x'+k,{drawSVG:'0%'},{drawSVG:'100%',duration:0.28,ease:'power3.out'},t+0.22); });
// hand-off: badges clear, the card glides left and shrinks into K-3's input card
tl.to(['#k2-b1','#k2-b2','#k2-b3'],{opacity:0,y:30,duration:0.3,ease:'power2.in',stagger:0.04},@ho@);
tl.to('#k2-card',{x:-410,y:20,scaleX:0.511,scaleY:0.907,transformOrigin:'0 0',duration:0.7,ease:'power3.inOut'},@ho@);
tl.to('#k2-card',{opacity:0,duration:0.2},@ho@+0.72);
""", g=L(W("GPS", 17.4)), c=L(W("camera", 18.2)), m=L(W("map", 19.0)), ho=L(W("Vortex", 20.1)) - 0.25)
    return scene("k2", dur("k2"), css, html, js)

# ---------------------------------------------------------------- K-3
def k3():
    L = lambda v: local("k3", v)
    css = """
#k3-in{left:110px;top:170px;width:450px;height:390px;overflow:hidden;}
#k3-in .hd{position:absolute;left:22px;top:16px;font-size:22px;font-weight:700;} #k3-in .hd span{color:#5ec8f2;font-family:'JetBrains Mono',monospace;}
#k3-in .meta{position:absolute;left:22px;top:52px;font-size:17px;color:#7ee0b5;}
.k3-row{position:absolute;left:22px;width:406px;height:20px;border-radius:5px;background:rgba(94,200,242,.20);}
#k3-node{position:absolute;left:690px;top:295px;width:140px;height:140px;border-radius:50%;border:3px solid #5ec8f2;
  background:radial-gradient(circle,#1b2a6e 0%,#121a45 70%);box-shadow:0 0 40px rgba(94,200,242,.45),inset 0 0 30px rgba(94,200,242,.25);}
#k3-node .n{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:22px;letter-spacing:.14em;}
#k3-tag{position:absolute;left:615px;top:236px;width:290px;text-align:center;font-size:19px;color:#c38bf5;font-weight:700;letter-spacing:.05em;}
#k3-svg{position:absolute;left:0;top:0;width:1920px;height:1080px;overflow:visible;}
.k3-m{position:absolute;width:0;height:0;}
.k3-dot{position:absolute;left:-7px;top:-7px;width:14px;height:14px;border-radius:50%;background:#7ee0b5;box-shadow:0 0 12px rgba(126,224,181,.8);}
.k3-arr{position:absolute;left:0;top:-1.5px;width:34px;height:3px;background:#7ee0b5;transform-origin:0 50%;}
.k3-arr:after{content:'';position:absolute;right:-2px;top:-5px;border-left:10px solid #7ee0b5;border-top:6.5px solid transparent;border-bottom:6.5px solid transparent;}
.k3-m.blind .k3-dot{background:transparent;border:2px dashed #f5a35e;box-shadow:0 0 26px 10px rgba(245,163,94,.25);}
.k3-m.blind .k3-arr{background:#f5a35e;opacity:.55;} .k3-m.blind .k3-arr:after{border-left-color:#f5a35e;}
.k3-giz{position:absolute;left:0;top:0;width:0;height:0;perspective:600px;}
.k3-gz{position:absolute;left:0;top:0;transform-style:preserve-3d;}
.k3-ax{position:absolute;left:0;top:-2px;height:4px;width:70px;transform-origin:0 50%;border-radius:2px;}
.k3-ax i{position:absolute;right:-6px;top:-14px;font-style:normal;font-size:16px;font-weight:700;font-family:'JetBrains Mono',monospace;}
#k3-out{position:absolute;left:560px;top:690px;font-size:30px;color:#f3f5ff;letter-spacing:.02em;}
#k3-outc{position:absolute;left:560px;top:742px;font-size:22px;color:rgba(243,245,255,.7);}
#k3-nog{position:absolute;font-size:18px;color:rgba(243,245,255,.6);font-family:'JetBrains Mono',monospace;}
#k3-sch{left:1640px;top:110px;}
"""
    # schematic path (to the right of the node, kept out of the bottom-right reserve)
    path = "M 840 365 C 960 360 1010 250 1120 240 S 1300 330 1380 300 S 1520 170 1600 200 S 1700 330 1760 300"
    rows = "".join(f'<div class="k3-row" id="k3-r{i}" style="top:{96 + i*26}px"></div>' for i in range(11))
    # markers: 26 positions along the path; 9-12 missing (gap), 22-25 blind
    marks = "".join(f'<div class="k3-m{" blind" if i >= 22 else ""}" id="k3-m{i}"><div class="k3-dot"></div><div class="k3-arr"></div></div>' for i in range(26))
    giz = "".join(f'''<div class="k3-giz" id="k3-g{i}"><div class="k3-gz" id="k3-gz{i}">
<div class="k3-ax" style="background:#ff6b6b;transform:rotateZ(0deg)"><i style="color:#ff6b6b">x</i></div>
<div class="k3-ax" style="background:#7ee0b5;transform:rotateZ(-90deg)"><i style="color:#7ee0b5">y</i></div>
<div class="k3-ax" style="background:#5ec8f2;transform:rotateY(-90deg)"><i style="color:#5ec8f2">z</i></div></div></div>''' for i in range(3))
    html = f"""<div class="world" id="k3-world">
<svg id="k3-svg" viewBox="0 0 1920 1080"><path id="k3-path" d="{path}" fill="none" stroke="rgba(94,200,242,.35)" stroke-width="3" stroke-dasharray="2 10" stroke-linecap="round"/></svg>
<div class="panel" id="k3-in"><div class="hd">input <span>imu0/data.csv</span></div><div class="meta">EuRoC format · ~200 Hz · gyro + accel</div>{rows}</div>
<div id="k3-tag">offline · smoothing allowed</div>
<div id="k3-node"><div class="n">VORTEX</div></div>
{marks}{giz}
<div id="k3-nog">no output</div>
<div id="k3-out" class="mono"></div><div id="k3-outc">one pose per input row, in order</div>
<div class="schem" id="k3-sch" data-layout-ignore>schematic</div></div>"""
    js = sub("""
const path=MotionPathPlugin.getRawPath('#k3-path'); MotionPathPlugin.cacheRawPathMeasurements(path);
const M=26, pos=[];
for(let i=0;i<M;i++){ const p=MotionPathPlugin.getPositionOnPath(path, 0.03+i*0.94/(M-1), true); pos.push(p);
  const el=document.getElementById('k3-m'+i); el.style.left=p.x+'px'; el.style.top=p.y+'px';
  el.querySelector('.k3-arr').style.transform='rotate('+(p.angle-25+Math.sin(i*1.7)*35).toFixed(1)+'deg)'; }
const nog=document.getElementById('k3-nog'); nog.style.left=(pos[10].x-50)+'px'; nog.style.top=(pos[10].y+34)+'px';
[0,1,2].forEach(k=>{ const p=pos[[3,6,15][k]]; const g=document.getElementById('k3-g'+k); g.style.left=p.x+'px'; g.style.top=p.y+'px'; });
gsap.set('.k3-m',{opacity:0,scale:0.4}); gsap.set('.k3-giz',{opacity:0});
// enter: the K-2 card lands here as the input card; node and tag build
tl.fromTo('#k3-in',{opacity:0},{opacity:1,duration:0.2},@vortex@+0.42);
tl.fromTo('.k3-row',{scaleX:0,transformOrigin:'0 50%'},{scaleX:1,duration:0.4,ease:'expo.out',stagger:0.04},@vortex@+0.5);
popIn(tl,'#k3-node',@vortex@-0.1,0.6);
tl.fromTo('#k3-tag',{opacity:0,y:10},{opacity:1,y:0,duration:0.5,ease:'expo.out'},@offline@-0.1);
// rows stream from the card into the node (data dust)
for(let i=0;i<14;i++){ const d=document.createElement('div'); d.className='k3-fly'; d.id='k3-f'+i;
  d.style.cssText='position:absolute;left:560px;top:'+(270+(i%7)*26)+'px;width:26px;height:6px;border-radius:3px;background:#5ec8f2;box-shadow:0 0 10px #5ec8f2;opacity:0';
  document.getElementById('k3-world').appendChild(d);
  const t=@vortex@+0.3+i*0.22; tl.fromTo(d,{x:0,y:0,opacity:0},{keyframes:[{opacity:1,duration:0.08},{x:190,y:(365-(270+(i%7)*26))*1.0,duration:0.42,ease:'power2.in'},{opacity:0,duration:0.06}]},t); }
tl.to('#k3-path',{attr:{'stroke-dasharray':'2 10'},duration:0.1},@rebuild@);
tl.fromTo('#k3-path',{drawSVG:'0%'},{drawSVG:'100%',duration:1.6,ease:'power2.inOut'},@rebuild@-0.2);
// one pose marker per row, in order (rows 9-12 never arrive -> no marker)
for(let i=0;i<22;i++){ if(i>=9&&i<=12) continue; tl.to('#k3-m'+i,{opacity:1,scale:1,duration:0.35,ease:'expo.out'},@rebuild@+0.1+i*0.07); }
// approved 3D #1: three markers open into x/y/z gizmos, turn, then flatten back into the path
[0,1,2].forEach(k=>{ const g='#k3-g'+k, z='#k3-gz'+k;
  tl.fromTo(g,{opacity:0,scale:0.3},{opacity:1,scale:1,duration:0.45,ease:'expo.out'},@three@+k*0.12);
  tl.fromTo(z,{rotationX:-20,rotationY:30,rotationZ:0},{rotationX:-55,rotationY:160+k*40,rotationZ:25,duration:1.7,ease:'power2.inOut'},@three@+k*0.12);
  tl.to(z,{rotationX:0,rotationY:0,rotationZ:0,scale:0.4,duration:0.5,ease:'power3.in'},@three@+1.9);
  tl.to(g,{opacity:0,duration:0.25},@three@+2.25); });
// output line, typed
inBlur(tl,'#k3-outc',@orient@+0.6,0.4);
typeOn(tl,'#k3-out','timestamp tx ty tz qx qy qz qw',@orient@-0.3,0.9);
// missing rows: gaps in the input, no marker for them
tl.to(['#k3-r4','#k3-r5','#k3-r6'],{opacity:0.08,duration:0.3},@missing@);
tl.fromTo('#k3-nog',{opacity:0},{opacity:1,duration:0.4},@missing@+0.25);
// blind rows: grey-amber rows -> faded dashed markers with an uncertainty halo
tl.to(['#k3-r8','#k3-r9','#k3-r10'],{backgroundColor:'rgba(245,163,94,.28)',duration:0.4},@blind@);
for(let i=22;i<26;i++) tl.to('#k3-m'+i,{opacity:0.7,scale:1,duration:0.5,ease:'expo.out'},@blind@+0.4+(i-22)*0.22);
tl.fromTo('.k3-m.blind .k3-dot',{scale:0.6},{scale:1.25,duration:0.8,ease:'sine.inOut'},@forecast@);
tl.fromTo('#k3-sch',{opacity:0},{opacity:1,duration:0.5},@rebuild@+0.4);
// hand-off: everything but the node clears; S-b dives into it
tl.to(['#k3-in','#k3-tag','.k3-m','#k3-path','#k3-out','#k3-outc','#k3-nog','#k3-sch'],{opacity:0,filter:'blur(10px)',duration:0.45,ease:'power2.in'},@ho@);
""", vortex=L(W("Vortex", 20.1)), offline=L(W("offline", 21.6)), rebuild=L(W("rebuilds", 23.3)),
        three=L(W("3D", 25.2)), orient=L(W("orientation", 26.5)), missing=L(W("Missing", 28.8)),
        blind=L(W("blind", 31.8)), forecast=L(W("forecast", 33.8)), ho=round(dur("k3") - 0.9, 3))
    return scene("k3", dur("k3"), css, html, js)

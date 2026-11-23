"""K-6 results board, K-7 dead sensor, S-d rules, K-8 end slate, kinetic keyword captions."""
from common import *
from scenes_a import sub, dur

# ---------------------------------------------------------------- K-6
def k6():
    L = lambda v: local("k6", v)
    # bar lengths are proportional to the ledger values (NUMBERS.md: heldout_ape_m / _floor_m, heldout_rpe1s_*, heldout79_ape_*, tumvi_ape_*)
    SC = 760 / 3.75
    rows = [("r1a", 210, "Held-out EuRoC · error", 3.745, 3.440, "−8.1 %", "error"),
            ("r1b", 300, "Held-out EuRoC · 1 s drift", 0.941 * 3.75 / 0.941, 0.562 * 3.75 / 0.941, "−40.2 %", "one-second drift"),
            ("r2", 430, "Repeat, seeds 7–9 · error", 3.748, 3.481, "−7.1 %", ""),
            ("r3", 560, "TUM-VI hand-held, rooms 1–4 · error", 1.137 * 3.0, 0.969 * 3.0, "−14.8 %", "")]
    css = """
#k6-hd{position:absolute;left:110px;top:70px;font-size:30px;font-weight:700;letter-spacing:.18em;color:#7ee0b5;}
#k6-leg{position:absolute;left:560px;top:76px;font-size:22px;color:rgba(243,245,255,.75);}
#k6-leg i{display:inline-block;width:26px;height:12px;border-radius:6px;margin:0 8px 0 22px;vertical-align:middle;}
.k6-lab{position:absolute;left:110px;width:420px;font-size:26px;font-weight:700;line-height:1.15;}
.k6-bar{position:absolute;left:560px;height:26px;border-radius:13px;transform-origin:0 50%;}
.k6-ref{background:rgba(243,245,255,.28);} .k6-vx{background:#5ec8f2;box-shadow:0 0 18px rgba(94,200,242,.55);}
.k6-tag{position:absolute;padding:6px 16px;border-radius:12px;background:#7ee0b5;color:#0a0e2e;font-weight:900;font-size:34px;}
.k6-tag small{font-size:24px;font-weight:700;margin-left:8px;}
#k6-five{position:absolute;left:110px;top:240px;font-size:22px;color:#7ee0b5;font-weight:700;}
.k6-pip{position:absolute;top:618px;width:22px;height:22px;border-radius:50%;border:2px solid #7ee0b5;}
#k6-rooms{position:absolute;left:560px;top:614px;font-size:22px;color:rgba(243,245,255,.7);}
#k6-notes{position:absolute;left:110px;top:700px;width:1360px;font-size:23px;line-height:1.55;color:rgba(243,245,255,.78);}
#k6-notes b{color:#f3f5ff;}
#k6-foot{position:absolute;left:110px;top:965px;width:1360px;font-family:'JetBrains Mono',monospace;font-size:20px;color:rgba(243,245,255,.6);}
#k6-sweep{position:absolute;left:540px;top:180px;width:1000px;height:420px;}
"""
    bars = ""
    for rid, y, lab, ref, vx, tag, sm in rows:
        bars += (f'<div class="k6-lab" id="k6-l{rid}" style="top:{y - 6}px">{lab}</div>'
                 f'<div class="k6-bar k6-ref" id="k6-ref{rid}" style="top:{y - 4}px;width:{ref * SC:.0f}px"></div>'
                 f'<div class="k6-bar k6-vx" id="k6-vx{rid}" style="top:{y + 26}px;width:{vx * SC:.0f}px"></div>'
                 f'<div class="k6-tag" id="k6-t{rid}" style="left:{560 + ref * SC + 34:.0f}px;top:{y - 2}px">{tag}{f"<small>{sm}</small>" if sm else ""}</div>')
    pips = "".join(f'<div class="k6-pip" id="k6-p{i}" style="left:{1000 + i*40}px"></div>' for i in range(4))
    html = f"""<div class="world" id="k6-world">
<div id="k6-hd">LOWER IS BETTER</div>
<div id="k6-leg"><i style="background:rgba(243,245,255,.35)"></i>static reference, scored the same way <i style="background:#5ec8f2"></i>Vortex</div>
{bars}<div class="sweep" id="k6-sweep"></div>
<div id="k6-five">5 of 6 flights improved</div>
<div id="k6-rooms">rooms</div>{pips}
<div id="k6-notes"><b>Tuning:</b> only on EuRoC MH_01/02 and TUM-VI rooms 1–2 · EuRoC rows are held-out flights; the TUM-VI row covers <span style="white-space:nowrap">rooms 1–4</span>, incl. the 2 tuning rooms<br/>
<b>Metric key:</b> absolute error = APE after SE(3) alignment · drift = 1 s RPE</div>
<div id="k6-foot">Shipped v1.0 · organisers' degrade_imu.py · SE(3)-aligned APE vs a static reference</div></div>"""
    js = sub("""
// whip-pan arrival: lands blurred and sharpens
tl.fromTo('#k6-world',{x:1500,filter:'blur(14px)'},{x:0,filter:'blur(0px)',duration:0.45,ease:'expo.out'},0.0);
gsap.set(['.k6-tag','#k6-five','#k6-notes','#k6-foot','.k6-pip','#k6-rooms'],{opacity:0});
tl.fromTo(['#k6-hd','#k6-leg'],{opacity:0},{opacity:1,duration:0.4},0.35);
const R=[['r1a',@e81@],['r1b',@e40@],['r2',@rep@],['r3',@tum@]];
R.forEach(([r,t],k)=>{
  // every row's label and grey static-reference bar build in on 'static reference'; the Vortex bar lands with its tag
  const ref=@static@+k*0.14;
  inBlur(tl,'#k6-l'+r,ref,0.35);
  tl.fromTo('#k6-ref'+r,{scaleX:0},{scaleX:1,duration:0.8,ease:'expo.out'},ref+0.1);
  const enter = (r==='r1b') ? @e81@-1.2 : t-1.3;
  tl.fromTo('#k6-vx'+r,{scaleX:0},{scaleX:1,duration:0.9,ease:'expo.out'},enter+0.25);
  tl.fromTo('#k6-t'+r,{opacity:0,scale:0.7,x:-20},{opacity:1,scale:1,x:0,duration:0.5,ease:'back.out(1.7)'},t-0.13);
});
sweep(tl,'#k6-sweep',@e81@+0.2);
tl.to('#k6-five',{opacity:1,duration:0.5},@e81@+0.4);
// four TUM-VI room pips light one by one on 'all four rooms'
tl.to('#k6-rooms',{opacity:1,duration:0.3},@rooms@-0.3);
for(let i=0;i<4;i++) tl.fromTo('#k6-p'+i,{opacity:0,scale:0.5,backgroundColor:'rgba(126,224,181,0)'},{opacity:1,scale:1,backgroundColor:'#7ee0b5',duration:0.3,ease:'back.out(2)'},@rooms@+i*0.16);
tl.fromTo('#k6-notes',{opacity:0,y:12},{opacity:1,y:0,duration:0.5},@never@);
tl.fromTo('#k6-foot',{opacity:0},{opacity:1,duration:0.5},@degraded@);
// hand-off: the bars stretch into K-7's schematic path
tl.to(['.k6-lab','.k6-tag','.k6-ref','#k6-five','#k6-notes','#k6-foot','.k6-pip','#k6-rooms','#k6-hd','#k6-leg'],{opacity:0,duration:0.3},@ho@);
tl.to('.k6-vx',{scaleX:1.9,y:(i)=>[310,220,90,-40][i],opacity:0.0,duration:0.65,ease:'power3.inOut'},@ho@);
""", e81=L(W("8.1%", 91.9)), e40=L(W("40%", 95.2)), rep=L(W("second", 98.5)), tum=L(W("14.8%", 105.3)),
        rooms=L(W("all", 108.4)), static=L(W("static", 88.8)), never=L(W("never", 84.4)), degraded=L(W("degraded", 85.3)), ho=round(dur("k6") - 0.75, 3))
    return scene("k6", dur("k6"), css, html, js)

# ---------------------------------------------------------------- K-7
def k7():
    L = lambda v: local("k7", v)
    css = """
#k7-stage{position:absolute;left:0;top:0;width:1920px;height:1080px;perspective:1400px;}
#k7-plane{position:absolute;left:0;top:0;width:1920px;height:1080px;transform-style:preserve-3d;transform-origin:50% 60%;}
#k7-svg{position:absolute;left:0;top:0;width:1920px;height:1080px;overflow:visible;}
#k7-dead{position:absolute;left:930px;top:320px;padding:6px 14px;border-radius:10px;background:#f5a35e;color:#0a0e2e;font-weight:900;font-size:26px;letter-spacing:.08em;}
#k7-gl{position:absolute;left:1190px;top:170px;font-size:24px;color:#ff6b6b;font-family:'JetBrains Mono',monospace;}
#k7-hl{position:absolute;left:1180px;top:452px;font-size:26px;color:#7ee0b5;font-weight:700;}
#k7-stamp{position:absolute;left:1100px;top:170px;width:560px;padding:18px 24px;border:4px solid #7ee0b5;border-radius:16px;color:#7ee0b5;
  text-align:center;font-weight:900;font-size:34px;line-height:1.15;background:rgba(10,14,46,.85);}
#k7-stamp small{display:block;font-family:'JetBrains Mono',monospace;font-weight:700;font-size:24px;color:#f3f5ff;margin-top:8px;}
#k7-rule{left:110px;top:720px;width:900px;padding:20px 26px;font-size:24px;line-height:1.4;}
#k7-rule b{color:#f5a35e;}
#k7-sch{left:110px;top:110px;}
"""
    html = """<div class="world" id="k7-world"><div id="k7-stage"><div id="k7-plane">
<svg id="k7-svg" viewBox="0 0 1920 1080">
 <path id="k7-path" d="M 120 560 C 300 520 420 420 560 450 S 800 520 960 420" fill="none" stroke="#5ec8f2" stroke-width="6" stroke-linecap="round"/>
 <path id="k7-ghost" d="M 960 420 C 1080 340 1100 200 1180 230 S 1320 420 1250 140 S 1420 60 1500 120" fill="none" stroke="#ff6b6b" stroke-width="5" stroke-dasharray="14 10" stroke-linecap="round" opacity="0.9"/>
 <path id="k7-hold" d="M 960 420 L 1160 430" fill="none" stroke="#7ee0b5" stroke-width="7" stroke-linecap="round"/>
 <circle id="k7-dot" cx="960" cy="420" r="13" fill="#f5a35e"/>
</svg>
<div id="k7-dead">IMU DEAD</div><div id="k7-gl">raw integration</div><div id="k7-hl">last trusted state</div>
</div></div>
<div class="panel" id="k7-rule"><b>Blind rule:</b> trailing dead run ≥ 1 s → poses from 3 s before keep the attitude of the last trusted pose</div>
<div id="k7-stamp">100 % format checks passed · one pose per row<small>36/36 · 36/36 · 24/24</small></div>
<div class="schem" id="k7-sch" data-layout-ignore>schematic</div></div>"""
    js = sub("""
gsap.set(['#k7-ghost','#k7-hold','#k7-dot','#k7-dead','#k7-gl','#k7-hl','#k7-stamp','#k7-rule'],{opacity:0});
tl.fromTo('#k7-path',{drawSVG:'0%'},{drawSVG:'100%',duration:1.0,ease:'power2.inOut'},0.05);
tl.fromTo('#k7-sch',{opacity:0},{opacity:1,duration:0.4},0.4);
// 'dies': amber IMU-dead marker + glitch burst, then a beat of stillness
tl.to(['#k7-dot','#k7-dead'],{opacity:1,duration:0.15},@dies@);
tl.fromTo('#k7-world',{x:0},{keyframes:[{x:-18,duration:0.03},{x:14,duration:0.04},{x:-6,duration:0.03},{x:0,duration:0.05}]},@dies@);
tl.fromTo('#k7-svg',{filter:'drop-shadow(8px 0 0 rgba(255,80,80,.8)) drop-shadow(-8px 0 0 rgba(80,200,255,.8))'},{filter:'drop-shadow(0px 0 0 rgba(255,80,80,0)) drop-shadow(0px 0 0 rgba(80,200,255,0))',duration:0.3},@dies@);
tl.fromTo('#k7-dead',{clipPath:'inset(0 0 0 0)'},{keyframes:[{clipPath:'inset(40% 0 30% 0)',duration:0.04},{clipPath:'inset(0 0 0 0)',duration:0.06}]},@dies@+0.03);
// approved 3D #3 (optional): the path plane tilts into perspective, the ghost curls off in 3D, the held line stays put
tl.to('#k7-plane',{rotationX:38,rotationY:-10,y:-40,duration:0.9,ease:'power2.inOut'},@stops@-0.2);
tl.set('#k7-ghost',{opacity:0.9},@stops@);
tl.fromTo('#k7-ghost',{drawSVG:'0%'},{drawSVG:'100%',duration:1.0,ease:'power2.in'},@stops@);
tl.fromTo('#k7-gl',{opacity:0},{opacity:1,duration:0.3},@stops@+0.5);
tl.to(['#k7-ghost','#k7-gl'],{opacity:0,duration:0.6},@stops@+1.5);
tl.to('#k7-plane',{rotationX:0,rotationY:0,y:0,duration:0.9,ease:'power2.inOut'},@stops@+1.7);
tl.set('#k7-hold',{opacity:1},@holds@);
tl.fromTo('#k7-hold',{drawSVG:'0%'},{drawSVG:'100%',duration:0.7,ease:'power3.out'},@holds@);
tl.fromTo('#k7-hl',{opacity:0,x:-12},{opacity:1,x:0,duration:0.5,ease:'expo.out'},@holds@+0.3);
tl.fromTo('#k7-rule',{opacity:0,y:14},{opacity:1,y:0,duration:0.5,ease:'expo.out'},@holds@+0.7);
// stamp thud on 'format check'
tl.fromTo('#k7-stamp',{opacity:0,scale:1.6,rotation:-6},{opacity:1,scale:1,rotation:-2,duration:0.28,ease:'power4.in'},@check@-0.25);
tl.to('#k7-stamp',{scale:1.03,duration:0.08,yoyo:true,repeat:1},@check@+0.03);
// hand-off: path clears; the switch row comes up in S-d
tl.to(['#k7-plane','#k7-rule','#k7-stamp','#k7-sch'],{opacity:0,y:-20,duration:0.4,ease:'power2.in'},@ho@);
""", dies=L(W("dies", 111.3)), stops=L(W("stops", 112.4)), holds=L(W("holds", 113.5)), motion=L(W("motion", 115.9)),
        check=L(W("passes", 118.0)) + 0.15, ho=round(dur("k7") - 0.6, 3))
    return scene("k7", dur("k7"), css, html, js)

# ---------------------------------------------------------------- S-d
def sd():
    L = lambda v: local("sd", v)
    css = """
.sd-u{position:absolute;top:250px;width:200px;height:330px;}
.sd-card{position:absolute;left:10px;top:0;width:180px;height:120px;border-radius:14px;border:2px solid rgba(243,245,255,.3);background:rgba(18,26,69,.9);}
.sd-card svg{position:absolute;left:66px;top:22px;}
.sd-card .ln{position:absolute;left:24px;height:6px;border-radius:3px;background:rgba(243,245,255,.25);}
.sd-sw{position:absolute;left:50px;top:170px;width:100px;height:52px;border-radius:26px;background:rgba(243,245,255,.15);border:2px solid rgba(243,245,255,.3);}
.sd-k{position:absolute;left:5px;top:4px;width:40px;height:40px;border-radius:50%;background:#f3f5ff;}
#sd-t{position:absolute;left:0;width:1920px;top:660px;text-align:center;font-size:44px;font-weight:700;letter-spacing:.2em;}
#sd-l{position:absolute;left:0;width:1500px;top:742px;text-align:center;font-size:27px;color:rgba(243,245,255,.75);}
"""
    on = [0, 2, 3, 5]
    units = ""
    for i in range(7):
        units += f"""<div class="sd-u" id="sd-u{i}" style="left:{200 + i*215}px"><div class="sd-card" id="sd-c{i}">
<svg width="48" height="56" viewBox="0 0 48 56"><rect x="4" y="24" width="40" height="30" rx="6" fill="none" stroke="#f3f5ff" stroke-width="4"/>
<path d="M12 24 V16 A12 12 0 0 1 36 16 V24" fill="none" stroke="#f3f5ff" stroke-width="4"/></svg>
<div class="ln" style="top:88px;width:130px"></div></div><div class="sd-sw" id="sd-s{i}"><div class="sd-k" id="sd-k{i}"></div></div></div>"""
    html = f"""<div class="world" id="sd-world">{units}<div id="sd-t">RULE FIRST, TEST SECOND</div>
<div id="sd-l">every feature is a switch, off by default · rule committed before the held-out run · ships only if it passes</div></div>"""
    js = sub("""
const ON=@on@;
tl.fromTo('.sd-u',{opacity:0,y:40},{opacity:1,y:0,duration:0.5,ease:'expo.out',stagger:0.06},0.3);
for(let i=0;i<7;i++){ const t=@rule@-0.2+i*0.12;
  if(ON.includes(i)){ tl.to('#sd-c'+i,{borderColor:'#7ee0b5',backgroundColor:'rgba(126,224,181,.16)',duration:0.25},t);
    tl.to('#sd-k'+i,{x:48,backgroundColor:'#0a0e2e',duration:0.3,ease:'back.out(1.6)'},t+0.15);
    tl.to('#sd-s'+i,{backgroundColor:'#7ee0b5',borderColor:'#7ee0b5',duration:0.3},t+0.15); }
  else tl.to('#sd-c'+i,{opacity:0.55,duration:0.3},t); }
tl.fromTo('#sd-t',{opacity:0,filter:'blur(8px)'},{opacity:1,filter:'blur(0px)',duration:0.4},0.55);
tl.fromTo('#sd-l',{opacity:0},{opacity:1,duration:0.5},0.9);
// hand-off: the switches collapse into the VORTEX wordmark on the end slate
tl.to(['#sd-t','#sd-l'],{opacity:0,duration:0.3},@ho@);
tl.to('.sd-u',{x:(i)=>1290-(200+i*215)-100,y:-60,scale:0.25,opacity:0,duration:0.6,ease:'power3.in',stagger:0.03},@ho@);
""", on=on, rule=L(W("rule", 121.9)), ho=round(dur("sd") - 0.75, 3))
    return scene("sd", dur("sd"), css, html, js)

# ---------------------------------------------------------------- K-8 end slate
def k8():
    L = lambda v: local("k8", v)
    css = """
#k8-word{position:absolute;left:900px;width:900px;top:300px;text-align:center;font-weight:900;font-size:150px;letter-spacing:.14em;padding-left:.14em;
  text-shadow:0 0 34px rgba(94,200,242,.5);}
#k8-line{position:absolute;left:900px;width:900px;top:500px;text-align:center;font-size:30px;color:#5ec8f2;font-weight:700;letter-spacing:.04em;}
#k8-name{position:absolute;left:900px;width:900px;top:590px;text-align:center;font-size:36px;font-weight:700;}
#k8-url{position:absolute;left:900px;width:900px;top:648px;text-align:center;font-family:'JetBrains Mono',monospace;font-size:30px;color:#7ee0b5;}
#k8-disc{position:absolute;left:900px;width:900px;top:960px;text-align:center;font-size:26px;color:rgba(243,245,255,.6);}
#k8-sweep{position:absolute;left:960px;top:300px;width:780px;height:180px;}
"""
    html = """<div class="world" id="k8-world"><div id="k8-word">VORTEX</div><div class="sweep" id="k8-sweep"></div>
<div id="k8-line">a navigator that knows how much to trust its sensor</div>
<div id="k8-name">Arnav Jain · Manipal Institute of Technology</div>
<div id="k8-url">github.com/ArnavJain2005/Vortex</div>
<div id="k8-disc">Pip film: AI-animated · narration voice by ElevenLabs</div></div>"""
    js = sub("""
tl.fromTo('#k8-word',{opacity:0,scale:0.7,filter:'blur(12px)'},{opacity:1,scale:1,filter:'blur(0px)',duration:0.7,ease:'expo.out'},@vx@-0.15);
sweep(tl,'#k8-sweep',@vx@+0.5);
inBlur(tl,'#k8-line',@nav@,0.45);
tl.fromTo(['#k8-name','#k8-url'],{opacity:0,y:14},{opacity:1,y:0,duration:0.5,ease:'expo.out',stagger:0.15},@trust@);
tl.fromTo('#k8-disc',{opacity:0},{opacity:1,duration:0.6},@trust@+0.4);
""", vx=L(W("Vortex", 123.9)), nav=L(W("navigator", 125.0)), trust=L(W("trust", 127.2)))
    return scene("k8", dur("k8"), css, html, js)

# ---------------------------------------------------------------- kinetic keyword captions (whole film)
def cap():
    caps = [("cap-a", W("No", 17.0) - 0.05, W("map", 19.0) + 1.0, "no GPS · no camera · no map", "#f3f5ff"),
            ("cap-b", W("prior", 50.7) - 0.05, W("prior", 50.7) + 1.6, "PRIOR", "#c38bf5"),
            ("cap-c", W("8.1%", 91.9) - 0.1, W("8.1%", 91.9) + 1.7, "−8.1 %", "#7ee0b5"),
            ("cap-d", W("40%", 95.2) - 0.1, W("40%", 95.2) + 1.6, "−40 %", "#7ee0b5"),
            ("cap-e", W("14.8%", 105.3) - 0.1, W("14.8%", 105.3) + 1.9, "−14.8 %", "#7ee0b5"),
            ("cap-f", W("stops", 112.4) - 0.05, W("stops", 112.4) + 1.7, "stops trusting it", "#f5a35e")]
    POS = {"cap-b": "top:96px;", "cap-c": "top:812px;", "cap-d": "top:812px;", "cap-e": "top:812px;", "cap-f": "top:930px;"}
    css = """
.cp{position:absolute;left:110px;top:900px;font-weight:900;font-size:58px;letter-spacing:.02em;text-shadow:0 4px 24px rgba(0,0,0,.6);}
.cp span{display:inline-block;}
"""
    html = '<div class="world" id="cap-world">' + "".join(
        f'<div class="cp" id="{i}" style="color:{c};{POS.get(i, "")}">' + "".join(f"<span>{w}&nbsp;</span>" for w in t.split(" ")) + "</div>"
        for i, a, b, t, c in caps) + "</div>"
    js = "gsap.set('.cp',{opacity:0});\n" + "\n".join(
        f"tl.set('#{i}',{{opacity:1}},{LEAD + a:.3f});"
        f"tl.fromTo('#{i} span',{{opacity:0,filter:'blur(6px)'}},{{opacity:1,filter:'blur(0px)',duration:0.13,stagger:0.067}},{LEAD + a:.3f});"
        f"tl.to('#{i} span',{{opacity:0,filter:'blur(6px)',duration:0.18,stagger:0.03}},{LEAD + b:.3f});" for i, a, b, t, c in caps)
    return scene("cap", DURATION, css, html, js).replace("tl.fromTo('#cap-world',{scale:1.0},{scale:1.03,duration:D,ease:'none'},0);", "")

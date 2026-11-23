"""Shared constants, cue lookup and scene-file wrapper for the Vortex HyperFrames build."""
import json, re

LEAD = 0.5          # video time = LEAD + voice time
OV = 0.6            # overlap between consecutive scene hosts (continuity hand-offs)
FPS = 30
WORDS = json.load(open("/home/claude/vx/work/cut_words.json"))

def W(word, near):
    """Voice-timeline start of the spoken word closest to `near` (word compared without punctuation)."""
    key = re.sub(r"[^a-z0-9.%]", "", word.lower())
    c = [w for w in WORDS if re.sub(r"[^a-z0-9.%]", "", w["w"].lower()).rstrip(".") == key.rstrip(".")]
    if not c: raise KeyError(word)
    w = min(c, key=lambda w: abs(w["t"] - near))
    if abs(w["t"] - near) > 2.5: raise KeyError(f"{word} near {near}: closest {w['t']}")
    return w["t"]

def wend(word, near):
    key = re.sub(r"[^a-z0-9.%]", "", word.lower()).rstrip(".")
    c = [w for w in WORDS if re.sub(r"[^a-z0-9.%]", "", w["w"].lower()).rstrip(".") == key]
    return min(c, key=lambda w: abs(w["t"] - near))

def gapmid(prev_word, prev_near, next_word, next_near):
    """Midpoint of the pause between the end of one word and the start of the next (ASR ends overshoot, so cap at +0.45 s)."""
    e = wend(prev_word, prev_near); n = W(next_word, next_near)
    end = min(e["e"], e["t"] + 0.55)
    return round((end + n) / 2, 2)

B = [0.0,
     round(W("Pip's", 4.6) - 0.25, 2),
     gapmid("seconds", 13.7, "Afterwards", 14.2),
     gapmid("map", 19.0, "Vortex", 20.1),
     gapmid("forecast", 33.8, "Inside", 35.6),
     gapmid("stages", 37.2, "First", 37.9),
     gapmid("ones", 65.4, "It", 66.6),
     gapmid("thread", 71.4, "using", 72.0),
     gapmid("limits", 80.3, "We", 81.8),
     gapmid("rooms", 109.0, "When", 110.5),
     gapmid("check", 119.2, "Every", 120.3),
     gapmid("testing", 123.0, "Vortex", 123.9)]
LAST = wend("sensor", 127.9)
END_V = round(min(LAST["e"], LAST["t"] + 0.6) + 1.5 + 0.9, 2)   # hold 1.5 s after the last word, then a 0.9 s fade
IDS = ["k1", "sa", "k2", "k3", "sb", "k4", "sc", "k5", "k6", "k7", "sd", "k8"]
SECTIONS = [(IDS[i], B[i], B[i + 1] if i + 1 < len(B) else END_V) for i in range(len(IDS))]
DURATION = round(LEAD + END_V, 3)

def host_start(i):
    return 0.0 if i == 0 else round(LEAD + SECTIONS[i][1] - OV / 2, 3)

EXTRA = {"k2": 0.75}   # scenes whose hand-off object travels into the next scene after the boundary

def host_end(i):
    return round(LEAD + SECTIONS[i][2] + (OV / 2 if i < len(SECTIONS) - 1 else 0) + EXTRA.get(SECTIONS[i][0], 0), 3)

def local(sid, v):
    """Scene-local time of voice time v."""
    i = IDS.index(sid); return round(LEAD + v - host_start(i), 3)

PALETTE = dict(bg="#0a0e2e", panel="#121a45", text="#f3f5ff", cyan="#5ec8f2", mint="#7ee0b5",
               violet="#c38bf5", amber="#f5a35e", red="#ff6b6b")

BASE_CSS = """
#root{position:absolute;inset:0;overflow:hidden;font-family:Inter,sans-serif;color:#f3f5ff;}
#root .world{position:absolute;inset:0;transform-origin:50% 45%;}
#root .mono{font-family:'JetBrains Mono',monospace;}
#root .panel{position:absolute;background:rgba(18,26,69,.86);border:1px solid rgba(94,200,242,.22);border-radius:22px;
  box-shadow:0 18px 60px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.05);}
#root .label{font-weight:700;letter-spacing:.01em;}
#root .sub{color:rgba(243,245,255,.72);font-weight:400;}
#root .tag{position:absolute;padding:6px 14px;border-radius:999px;font-weight:700;font-size:22px;letter-spacing:.06em;}
#root .glow-c{text-shadow:0 0 18px rgba(94,200,242,.55),0 0 2px rgba(94,200,242,.9);}
#root .glow-m{text-shadow:0 0 18px rgba(126,224,181,.55),0 0 2px rgba(126,224,181,.9);}
#root [data-layout-ignore]{}
#root .schem{position:absolute;font-family:'JetBrains Mono',monospace;font-size:18px;letter-spacing:.12em;
  color:rgba(243,245,255,.55);text-transform:lowercase;border:1px solid rgba(243,245,255,.25);padding:4px 10px;border-radius:6px;}
#root .sweep{position:absolute;inset:0;pointer-events:none;mix-blend-mode:screen;
  background:linear-gradient(105deg,transparent 35%,rgba(255,255,255,.22) 50%,transparent 65%);background-size:300% 100%;}
"""

HELPERS_JS = """
const P={bg:'#0a0e2e',panel:'#121a45',text:'#f3f5ff',cyan:'#5ec8f2',mint:'#7ee0b5',violet:'#c38bf5',amber:'#f5a35e',red:'#ff6b6b'};
function rng(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;}}
function typeOn(tl,sel,text,at,dur){const el=document.querySelector(sel);const o={n:0};el.textContent='';
  tl.fromTo(o,{n:0},{n:text.length,duration:dur,ease:'none',onUpdate:()=>{el.textContent=text.slice(0,Math.round(o.n));}},at);}
function countUp(tl,sel,to,dec,at,dur,suffix){const el=document.querySelector(sel);const o={v:0};
  tl.fromTo(o,{v:0},{v:to,duration:dur,ease:'power3.out',onUpdate:()=>{el.textContent=o.v.toFixed(dec)+(suffix||'');}},at);}
function inBlur(tl,sel,at,d){tl.fromTo(sel,{opacity:0,filter:'blur(8px)'},{opacity:1,filter:'blur(0px)',duration:d||0.35,ease:'power3.out'},at);}
function outBlur(tl,sel,at,d){tl.to(sel,{opacity:0,filter:'blur(8px)',duration:d||0.22,ease:'power2.in'},at);}
function popIn(tl,sel,at,d){tl.fromTo(sel,{opacity:0,scale:0.86},{opacity:1,scale:1,duration:d||0.45,ease:'expo.out'},at);}
function sweep(tl,sel,at){tl.fromTo(sel,{backgroundPosition:'120% 0'},{backgroundPosition:'-20% 0',duration:0.9,ease:'power2.inOut'},at);
  tl.fromTo(sel,{opacity:0},{opacity:1,duration:0.15},at);tl.to(sel,{opacity:0,duration:0.2},at+0.75);}
"""

def scene(sid, dur, css, html, js, extra_root_attrs=""):
    """A sub-composition file. `js` builds onto `tl`; times are local seconds."""
    return f"""<template>
<style>
{BASE_CSS}
{css}
</style>
<div id="root" data-composition-id="{sid}" data-width="1920" data-height="1080" data-duration="{dur:.3f}" {extra_root_attrs}>
{html}
</div>
<script>
(function(){{
gsap.registerPlugin(DrawSVGPlugin, MorphSVGPlugin, MotionPathPlugin);
{HELPERS_JS}
const tl = gsap.timeline({{paused:true}});
const D={dur:.3f};
// slow, never-stopping drift of the whole scene (B-roll feel)
tl.fromTo('#{sid}-world',{{scale:1.0}},{{scale:1.03,duration:D,ease:'none'}},0);
{js}
window.__timelines["{sid}"] = tl;
}})();
</script>
</template>
"""

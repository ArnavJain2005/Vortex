import cv2, json, numpy as np, subprocess, sys
AV=json.load(open("work/av_timeline.json")); FC=json.load(open("work/facecrop.json"))
K=1920/848
def crop_box(c):
    f=FC[c]; side=min(1080,1.9*f["face_w"]*K); cx,cy=f["cx"]*K,(f["cy"]-0.06*f["face_w"])*K
    x=min(max(0,cx-side/2),1920-side); y=min(max(0,cy-side/2),1080-side); return int(x),int(y),int(side)
def frames(path, t0, n, fps=30):
    raw=subprocess.run(["ffmpeg","-v","error","-ss",f"{max(0,t0):.4f}","-i",path,"-frames:v",str(n),"-vf","scale=96:-2,format=gray","-f","rawvideo","-"],capture_output=True).stdout
    return raw
def gray_frames(path,t0,n,vf):
    raw=subprocess.run(["ffmpeg","-v","error","-ss",f"{max(0,t0):.4f}","-i",path,"-frames:v",str(n),"-vf",vf+",scale=64:64,format=gray","-f","rawvideo","-"],capture_output=True).stdout
    a=np.frombuffer(raw,np.uint8); return a.reshape(-1,64,64).astype(np.float32)
mode=sys.argv[1]  # facecut | final
for T in [10.0, 25.0, 33.0, 37.0, 45.0, 60.0, 90.0, 100.0, 115.0, 122.0]:
    v=T-0.5
    seg=[s for s in AV["segs"] if s["tl_start"]<=v][-1]
    c=seg["clip"]
    if c=="c04r": continue
    src=seg["src_in"]+(v-seg["tl_start"])
    x,y,side=crop_box(c)
    ref=gray_frames(f"talking-head/orig/{c}.mp4", src-0.5, 31, f"crop={side}:{side}:{x}:{y}")
    if mode=="facecut":
        q=gray_frames("work/face_cut.mp4", v, 1, "null")[0]
    else:
        # circle region of the final video; compare with a circular mask
        cx,cy,d={True:(1704,864,320)}[True]
        if 79.5<v<108.0: cx,cy,d=1734,894,260
        if v>=120.7: continue
        q=gray_frames("out/Vortex_Technical_review.mp4", T, 1, f"crop={d}:{d}:{cx-d//2}:{cy-d//2}")[0]
    yy,xx=np.mgrid[:64,:64]; m=((xx-31.5)**2+(yy-31.5)**2)<26**2
    def z(a): a=a[m]; return (a-a.mean())/(a.std()+1e-6)
    scores=[float(np.mean(z(q)*z(r))) for r in ref]
    best=int(np.argmax(scores))-15
    print(f"T={T:6.1f} clip {c} expected src {src:6.2f}  best match offset {best:+d} frames (score {max(scores):.3f})")

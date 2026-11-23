import numpy as np, subprocess, sys
def load(p, sr=8000):
    raw=subprocess.run(["ffmpeg","-v","error","-i",p,"-map","0:a","-ac","1","-ar",str(sr),"-f","f32le","-"],capture_output=True,check=True).stdout
    return np.frombuffer(raw,np.float32)
SR=8000; ref=load("work/talk_cut_raw.wav"); mix=load(sys.argv[1]); LEAD=0.5
ref=np.concatenate([np.zeros(int(LEAD*SR),np.float32),ref])     # where the voice should sit on the video timeline
worst=0
for t in [8,20,34,40,55,70,85,95,105,115,125]:
    a,b=int(t*SR),int((t+4)*SR); x=mix[a:b]-mix[a:b].mean(); y=ref[a:b]-ref[a:b].mean()
    n=len(x); F=np.fft.irfft(np.fft.rfft(x,2*n)*np.conj(np.fft.rfft(y,2*n))); lag=int(np.argmax(F)); lag=lag if lag<n else lag-2*n
    ms=lag/SR*1000; worst=max(worst,abs(ms)); print(f"t={t:4d}s  voice offset {ms:+7.1f} ms")
print("worst", worst, "ms")

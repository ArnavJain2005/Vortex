import wave, numpy as np, json, sys, webrtcvad
def load(c):
    w=wave.open(f"work/{c}.wav"); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16); return x, w.getframerate()
res={}
vad=webrtcvad.Vad(2)
for c in ["c01","c02","c03","c04","c04r","c05","c06","c07"]:
    x,sr=load(c); hop=160  # 10ms
    n=len(x)//hop
    fr=x[:n*hop].reshape(n,hop).astype(np.float32)/32768
    db=20*np.log10(np.sqrt((fr**2).mean(1))+1e-9)
    v=np.array([vad.is_speech(x[i*hop:(i+1)*hop].tobytes() if False else x[i*480:(i+1)*480].tobytes(), sr) if (i+1)*480<=len(x) else False for i in range(len(x)//480)])
    v10=np.repeat(v,3)[:n]; v10=np.pad(v10,(0,n-len(v10)))
    speech=np.percentile(db,95); floor=np.percentile(db,10)
    res[c]={"db":db.round(1).tolist(),"vad":v10.astype(int).tolist(),"speech":float(speech),"floor":float(floor)}
    print(c,f"speech95={speech:.1f} floor10={floor:.1f} margin={speech-floor:.1f}")
json.dump(res,open("work/envelope.json","w"))

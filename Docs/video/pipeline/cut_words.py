import json, wave, numpy as np, sherpa_onnx, subprocess
subprocess.run(["ffmpeg","-v","error","-y","-i","work/talk_cut_raw.wav","-ar","16000","work/talk_cut16.wav"],check=True)
d="/home/claude/models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
p=sherpa_onnx.OfflineRecognizer.from_transducer(encoder=f"{d}/encoder.int8.onnx",decoder=f"{d}/decoder.int8.onnx",joiner=f"{d}/joiner.int8.onnx",tokens=f"{d}/tokens.txt",model_type="nemo_transducer",num_threads=2)
w=wave.open("work/talk_cut16.wav"); sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),np.int16).astype(np.float32)/32768
s=p.create_stream(); s.accept_waveform(sr,x); p.decode_stream(s); r=s.result
words=[]
for t,st,du in zip(r.tokens,r.timestamps,r.durations):
    if t.startswith(" ") or not words: words.append({"w":t.strip(),"t":round(st,2),"e":round(st+du,2)})
    else: words[-1]["w"]+=t; words[-1]["e"]=round(st+du,2)
json.dump(words,open("work/cut_words.json","w"))

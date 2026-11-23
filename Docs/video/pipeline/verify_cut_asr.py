import json, wave, numpy as np, sherpa_onnx, subprocess
subprocess.run(["ffmpeg","-v","error","-y","-i","work/talk_cut_raw.wav","-ar","16000","work/talk_cut16.wav"],check=True)
w=wave.open("work/talk_cut16.wav"); sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),np.int16).astype(np.float32)/32768
d="/home/claude/models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
p=sherpa_onnx.OfflineRecognizer.from_transducer(encoder=f"{d}/encoder.int8.onnx",decoder=f"{d}/decoder.int8.onnx",joiner=f"{d}/joiner.int8.onnx",tokens=f"{d}/tokens.txt",model_type="nemo_transducer",num_threads=2)
s=p.create_stream(); s.accept_waveform(sr,x); p.decode_stream(s); print("PARAKEET FULL:\n"+s.result.text+"\n")
d2="/home/claude/models/sherpa-onnx-whisper-medium.en"
wh=sherpa_onnx.OfflineRecognizer.from_whisper(encoder=f"{d2}/medium.en-encoder.int8.onnx",decoder=f"{d2}/medium.en-decoder.int8.onnx",tokens=f"{d2}/medium.en-tokens.txt",language="en",task="transcribe",num_threads=2)
lines=[]
for i,t in enumerate(json.load(open("work/seam_times.json"))):
    a=max(0,int((t-1.6)*sr)); b=int((t+1.6)*sr)
    s=wh.create_stream(); s.accept_waveform(sr,x[a:b]); wh.decode_stream(s)
    lines.append(f"seam {i+1:02d} {t:7.2f}s | {s.result.text.strip()}"); print(lines[-1],flush=True)
open("work/seams_asr.txt","w").write("\n".join(lines)+"\n")

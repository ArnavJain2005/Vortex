# LOOP_AG   updated 2026-11-22 02:16 IST   iteration 70
NOW: FINAL AG-3 PR #80 open (`ag/ag3-freeze-check@2324c71`, 670/670 PASS across 8 envs x 5 inputs on `main@5e28668`); running FINAL AG-1 15-run Linux Docker benchmark on `main@5e28668` CHUNKED `src/main.py`, then continuing 15-min polls for `v1.0` / final zip   branch ag/ag3-freeze-check@2324c71
DONE (newest first):
- AG-3 FINAL clean-machine matrix (PR #80 open, `ag/ag3-freeze-check@2324c71`, `main@5e28668`, CHUNKED `src/main.py` SHA-256 `feb222ea9f27f077`, `4 passed` synthetic): **670/670 PASS (0 failures)** across 8 environments (`win-venv-3.13/3.14`, `docker-3.10..3.14`, `zip-dockerfile`) x 5 inputs (`MH_01_b_s1`, `MH_03_b_s1`, `room3_b_s1`, `MH_03_b_s22`, `room3_b_s22`), 8/8 byte-identical on every input (`92fe58fe72028535`, `0e215ee3b078eaea`, `bd75c9364f0face9`, `f4a2f441dc9e4121`, `8fea7c76a2545da0`).
  - **True direct `exec(compile)` whole-run heap (`MH_01_b_s1`, `typing_loaded=False`, FINAL):** Win 3.13 `3,516.2 KB`, Win 3.14 `3,343.7 KB`, Docker 3.10 `2,459.0 KB`, 3.11 `2,694.0 KB`, 3.12 `2,973.3 KB`, 3.13 `3,238.3 KB`, 3.14 `3,344.7 KB` — **all `<= 3.5 MB`** (zero > 7 MB).
  - **`bundle_layouts.py` (`runpy.run_path`) probe (`MH_01_b_s1`, FINAL):** Win 3.14 `3,475.9 KB`, Win 3.13 `4,158.1 KB` (exact match to CC-freeze `3,476 / 4,157 KB`); `zip-dockerfile` (`3.12.7`) `5,658.9 KB`; **`docker-3.13` FLAGGED > 7 MB (`7,359.9 KB` = `7.19 MB`, < 8 MB)** — proven via `tracemalloc` snapshot to be a `+4.1 MB` probe artifact (`python:3.1x-slim-bookworm` strips `typing.pyc`, so `runpy.run_path` compiles `typing.py`; `src/main.py` never imports `typing`).
  - **Cold from-source speed (5-run median, FINAL):** `zip-dockerfile` (`3.12.7`) `6.39 ms/IMU-s` (`32.93 us/row`, `MH_01_b_s1`), `6.90` (`MH_03_b_s1`), `7.39` (`room3_b_s1`); all Docker `3.10-3.14` `6.39-10.39 ms/IMU-s` (`<= 10.4 ms`); Win host `12.00-16.63 ms/IMU-s` (slow-clock phase).
- Part C video tooling (#78 merged 88b1d27, FINAL): `Gyan.FFmpeg` 9.1 installed; `tools/assemble_video.py` + `tests/test_assemble_video.py` (`3 passed`, tested on 5 provisional clips + silent WAV, hard-fails `> 3:00`). Real video NOT assembled.
- Part B AG-5 PROVISIONAL footage (`main@4c25e91`, git-ignored `media/provisional_4c25e91/`, 5 clips `48.0 s` + Chrome no-GT replay checks + `manifest.json`/`MANIFEST.md`). Will re-record run shots & replays from `v1.0` zip.
- AG-4 Step L3 cross-checks (#74 bb0028e + #75 56684fc, FINAL: **336/336 runs <= 8.88e-13 mm**), AG-2 seeds (`loop/ag@8dba7a7` + `ccbea32`, FINAL: 400 official copies, 0 `V2_*`, 0 TUM-VI `s19-21`), AG-3 baseline (#73), AG-1 pre-L3 Docker bench (#72), AG-0 G7 (#70, #71).
READY FOR ARNAV TO MERGE (in this order): #80 (`ag/ag3-freeze-check@2324c71`, MERGE ORDER: 1)
MERGED: #70, #71, #72, #73, #74, #75, #76, #78 [and CC #68, #77, #79 (`5e28668`)]
GIVES TO CC:
- AG-3 FINAL matrix (PR #80, `Docs/CLEAN_MACHINE.md`, `main@5e28668` CHUNKED): 670/670 PASS, 8/8 byte-identical across 5 inputs, true direct-exec heap `2,459-3,516 KB` (all `<= 3.5 MB`); `runpy.run_path` probe flagged `docker-3.13` `7,359.9 KB` (> 7 MB, < 8 MB) due to stripped `typing.pyc` in `python:3.1x-slim-bookworm`; `zip-dockerfile` `6.39-7.39 ms/IMU-s`.
- AG-5 PROVISIONAL footage (`media/provisional_4c25e91/`) + `tools/assemble_video.py` (#78 merged).
NEEDS FROM CC:
- `v1.0` / final submission zip (`dist/vortex_v1.0.zip` or `Vortex.zip`) for final AG-3 zip verification & AG-5 run-shot/replay re-recording.
RULES COMMITTED: H at a5f5bd1 DONE; H' at fb36d77 DONE (merged #77); K parked (TUM-VI s19-21 unspent)
NUMBERS:
- FINAL (`main@5e28668`, CHUNKED `src/main.py` `feb222ea9f27f077`, `MH_01_b_s1`): direct-exec whole-run heap `2,459.0-3,516.2 KB` (all 7 Pythons 3.10-3.14); `runpy` probe `3,475.9 KB` Win 3.14 / `4,158.1 KB` Win 3.13 / `5,658.9 KB` `zip-dockerfile` 3.12.7 / `7,359.9 KB` `docker-3.13` (`typing.pyc` probe artifact); `zip-dockerfile` cold wall `6.39 ms/IMU-s` (`32.93 us/row`), worst Docker `10.39 ms/IMU-s` (`docker-3.10` `room3_b_s1`).
- PROVISIONAL (`main@4c25e91`, AG-5 footage): 5 clips, `48.0 s` (`1280x720` H.264), `manifest.json` + `MANIFEST.md`.
- FINAL (pre-L3, `main@5ba1c4b`, Docker 3.12.7, 15 runs): wall `5.96..7.50 ms/IMU-s`, compute `5.70..7.02 ms/IMU-s`.
PARKED: none
ESCALATION: none (Part D outage notice reported in chat: ~16 h host sleep/pause Sat 08:34 -> Sun 00:24 IST)

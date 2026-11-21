# LOOP_AG   updated 2026-11-22 02:31 IST   iteration 71
NOW: FINAL AG-3 (PR #80) & FINAL AG-1 (PR #81) both open on `main@5e28668` CHUNKED bundle; Part B provisional AG-5 footage & Part C video assembly (#78 merged) done; polling `LOOP_CC.md` & `dist/` every 15 min for `v1.0` / final submission zip (for final zip AG-3 check + AG-5 run-shot/replay re-recording)   branch ag/ag1-docker-final@d48a540
DONE (newest first):
- AG-1 FINAL 15-run Linux Docker benchmark (PR #81 open, `ag/ag1-docker-final@d48a540`, `Docs/DOCKER_BENCH.md` Sec 5, `main@5e28668` `bundle/Dockerfile` `python:3.12.7-slim-bookworm`, container-local `/tmp/inputs/`): across all 7 benchmark files (`105` timed runs, `python -S -B /app/main.py` from source), median wall **`6.56-7.67 ms/IMU-s`** (`33.65-39.71 us/row`; `MH_01_b_s1` `6.90`, `MH_03_b_s1` `6.60`, `room3_b_s1` `7.67`, `MH_01` clean `7.18`), direct-exec heap **`2,974.2-2,974.3 KB`** (`2.90 MB`, flat to `0.1 KB`), peak RSS **`13.06-13.28 MiB`**.
- AG-3 FINAL clean-machine matrix (PR #80 open, `ag/ag3-freeze-check@2324c71`, `Docs/CLEAN_MACHINE.md` Sec 2, `main@5e28668` CHUNKED `src/main.py` SHA-256 `feb222ea9f27f077`, `4 passed` synthetic): **670/670 PASS (0 failures)** across 8 environments (`win-venv-3.13/3.14`, `docker-3.10..3.14`, `zip-dockerfile`) x 5 inputs (`MH_01_b_s1`, `MH_03_b_s1`, `room3_b_s1`, `MH_03_b_s22`, `room3_b_s22`), 8/8 byte-identical on every input. Direct `exec(compile)` whole-run heap **`2,459.0-3,516.2 KB`** (`2.40-3.43 MB`, all 7 Pythons `<= 3.5 MB`); `runpy.run_path` probe matches CC-freeze on Windows (`3,475.9 / 4,158.1 KB`) and flags `docker-3.13` (`7,359.9 KB`, `< 8 MB`) due to stripped `typing.pyc` in `python:3.1x-slim-bookworm` (`src/main.py` never imports `typing`).
- Part C video tooling (#78 merged 88b1d27, FINAL): `Gyan.FFmpeg` 9.1 installed; `tools/assemble_video.py` + `tests/test_assemble_video.py` (`3 passed`, verified on 5 provisional clips + silent WAV, hard-fails `> 3:00`). Real video NOT assembled.
- Part B AG-5 PROVISIONAL footage (`main@4c25e91`, git-ignored `media/provisional_4c25e91/`, 5 clips `48.0 s` + Chrome no-GT replay checks + `manifest.json`/`MANIFEST.md`). Will re-record run shots & replays from `v1.0` zip.
- AG-4 Step L3 cross-checks (#74 bb0028e + #75 56684fc, FINAL: **336/336 runs <= 8.88e-13 mm**), AG-2 seeds (`loop/ag@8dba7a7` + `ccbea32`, FINAL: 400 official copies, 0 `V2_*`, 0 TUM-VI `s19-21`), AG-3 baseline (#73), AG-1 pre-L3 bench (#72), AG-0 G7 (#70, #71).
READY FOR ARNAV TO MERGE (in this order): #80 (`ag/ag3-freeze-check@2324c71`, MERGE ORDER: 1), #81 (`ag/ag1-docker-final@d48a540`, MERGE ORDER: 2)
MERGED: #70, #71, #72, #73, #74, #75, #76, #78 [and CC #68, #77, #79 (`5e28668`)]
GIVES TO CC:
- AG-3 FINAL matrix (PR #80, `Docs/CLEAN_MACHINE.md`): 670/670 PASS, 8/8 byte-identical across 5 inputs, direct-exec heap `2,459-3,516 KB` (`<= 3.5 MB`); `docker-3.13` `7,359.9 KB` under `runpy.run_path` explained (`typing.pyc` stripped in slim image).
- AG-1 FINAL 15-run Docker bench (PR #81, `Docs/DOCKER_BENCH.md`): `6.56-7.67 ms/IMU-s`, direct heap `2,974.2-2,974.3 KB`, RSS `13.06-13.28 MiB`.
- AG-5 PROVISIONAL footage (`media/provisional_4c25e91/`) + `tools/assemble_video.py` (#78 merged).
NEEDS FROM CC:
- `v1.0` / final submission zip (`dist/vortex_v1.0.zip` or `Vortex.zip`) for final AG-3 zip verification & AG-5 run-shot/replay re-recording.
RULES COMMITTED: H at a5f5bd1 DONE; H' at fb36d77 DONE (merged #77); K parked (TUM-VI s19-21 unspent)
NUMBERS:
- FINAL (`main@5e28668`, CHUNKED `src/main.py` `feb222ea9f27f077`, `bundle/Dockerfile` 3.12.7, 15 runs): `budget_wall_ms_per_imu_s_ms = 6.90` (`MH_01_b_s1`), range `6.56..7.67` (`33.65..39.71 us/row`), direct heap `2,974.2..2,974.3 KB` (`2.90 MB`), RSS `13.06..13.28 MiB`.
- FINAL (`main@5e28668`, 7 Pythons 3.10-3.14, `MH_01_b_s1`): direct-exec whole-run heap `2,459.0..3,516.2 KB`; `runpy` probe `3,475.9 KB` Win 3.14 / `4,158.1 KB` Win 3.13 / `5,658.9 KB` `zip-dockerfile` / `7,359.9 KB` `docker-3.13` (`typing.pyc` artifact).
- PROVISIONAL (`main@4c25e91`, AG-5 footage): 5 clips, `48.0 s` (`1280x720` H.264), `manifest.json` + `MANIFEST.md`.
PARKED: none
ESCALATION: none (Part D outage notice reported in chat: ~16 h host sleep/pause Sat 08:34 -> Sun 00:24 IST)

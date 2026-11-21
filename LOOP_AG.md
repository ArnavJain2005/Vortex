# LOOP_AG   updated 2026-11-22 05:04 IST   iteration 76
NOW: AG DONE (video assembly on request)   branch ag/v10-zip-verify@5ce8b9a
DONE (newest first):
- Job 2 FINAL `v1.0` footage (`media/v1.0/`, replaces `media/provisional_4c25e91/`, FINAL): recorded all 5 clips (`49.0 s`, `1280x720` H.264) from shipped `vortex_v1.0.zip` (`e251c4010248caf5...`, tag `v1.0` `0e7c81d`) on a quiet machine: `shot_01_run_mh03.mp4` (`8s`), `shot_02_check_output.mp4` (`8s`), `shot_03_benchmark_gate.mp4` (`9s`, live `runs=15` gate on shipped `src/main.py` in WSL2 Py 3.12.3: **`22.86 us/row`, `4.57 ms/IMU-s`, `938.0 KB` est / `3,852.2 KB` whole-run, `GATE: PASS`**), and Chrome no-GT replay sweeps regenerated from `v1.0` zip outputs (`shot_04_replay_mh03_b_s1.mp4` `12s`, `shot_05_replay_room3_b_s1.mp4` `12s`, `0` console errors, `has_gt=false`). Manifests: `media/v1.0/manifest.json` + `MANIFEST.md`.
- Job 1 FINAL `v1.0` zip verification (PR #82 open, `ag/v10-zip-verify@5ce8b9a`, `Docs/CLEAN_MACHINE.md` Sec 3, FINAL): confirmed `dist/vortex_v1.0.zip` (= `Vortex-v1/dist/Vortex.zip`, `781,993` bytes) SHA-256 `e251c4010248caf5103bbf2923122146bba64ae7e2b225069a89672ffbd4447c` MATCH; 7 files, 0 compiled files; `src/main.py` SHA-256 `feb222ea9f27f077`; bundled `estimated_trajectory.txt` `check_output` PASS (`26,106` rows, `0e215ee3b078eaea`). Unzipped to empty folder: **`24/24` PASS** across `win-venv-3.13` (`3.13.5`), `win-venv-3.14` (`3.14.7`), `docker-3.12` (`3.12.7`) x 4 modes (`no_args`, `IN OUT`, ±`-S`) x 2 inputs (`MH_03_b_s1` `0e215ee3b078eaea`, `room3_b_s1` `bd75c9364f0face9`), 100% byte-identical to Sec 2.
- AG-1 FINAL 15-run Linux Docker benchmark (PR #81 open, `ag/ag1-docker-final@d48a540`, `Docs/DOCKER_BENCH.md` Sec 5, FINAL): `6.56-7.67 ms/IMU-s` (`33.65-39.71 us/row`), direct-exec heap `2,974.2-2,974.3 KB` (`2.90 MB`), peak RSS `13.06-13.28 MiB`.
- AG-3 FINAL 8-env x 5-input matrix (PR #80 open, `ag/ag3-freeze-check@2324c71`, `Docs/CLEAN_MACHINE.md` Sec 2, FINAL): **670/670 PASS**, 8/8 byte-identical across 5 inputs, direct-exec heap `2,459.0-3,516.2 KB` across all 7 Pythons (`3.10-3.14`); `docker-3.13` `runpy.run_path` `7,359.9 KB` (`< 8 MB`) explained (`typing.pyc` stripped in slim image).
- Part C video tooling (#78 merged 88b1d27, FINAL): `Gyan.FFmpeg` 9.1 installed; `tools/assemble_video.py` + `tests/test_assemble_video.py` (`3 passed`, `ffprobe` 3:00 cap). Ready for Job 3 when Arnav drops assets into `media/inbox/`.
- AG-4 Step L3 cross-checks (#74, #75, FINAL: **336/336 runs <= 8.88e-13 mm**), AG-2 seeds (`loop/ag@8dba7a7` + `ccbea32`, FINAL: 400 official copies, 0 `V2_*`, 0 TUM-VI `s19-21`), AG-3 baseline (#73), AG-1 pre-L3 bench (#72), AG-0 G7 (#70, #71).
READY FOR ARNAV TO MERGE (in this order): #80 (`ag/ag3-freeze-check`, MERGE ORDER: 1), #81 (`ag/ag1-docker-final`, MERGE ORDER: 2), #82 (`ag/v10-zip-verify`, stacked on #80, MERGE ORDER: 3)
MERGED: #70, #71, #72, #73, #74, #75, #76, #78 [and CC #68, #77, #79 (`5e28668`)]
GIVES TO CC:
- `v1.0` zip verified (`24/24` PASS, SHA-256 confirmed, PR #82) + full 8-env matrix (PR #80) + 15-run Docker bench (PR #81) + FINAL `v1.0` footage (`media/v1.0/`, 5 clips `49.0 s`).
NEEDS FROM CC: none — AG polling stopped (`AG DONE (video assembly on request)`).
RULES COMMITTED: H at a5f5bd1 DONE; H' at fb36d77 DONE (merged #77); K parked (TUM-VI s19-21 unspent)
NUMBERS:
- FINAL (`v1.0` zip `e251c401...`, tag `0e7c81d`): `24/24` unzipped clean checks PASS (`MH_03_b_s1` `0e215ee3b078eaea`, `room3_b_s1` `bd75c9364f0face9`); live quiet `runs=15` gate (WSL2 Py 3.12.3) **`22.86 us/row`**, **`4.57 ms/IMU-s`**, `938.0 KB` est / `3,852.2 KB` whole-run heap, `GATE: PASS`.
- FINAL (`main@5e28668`, `bundle/Dockerfile` 3.12.7, 15 runs): `6.56..7.67 ms/IMU-s`, direct heap `2,974.2..2,974.3 KB` (`2.90 MB`), RSS `13.06..13.28 MiB`.
- FINAL (`main@5e28668`, 7 Pythons 3.10-3.14, `MH_01_b_s1`): direct-exec whole-run heap `2,459.0..3,516.2 KB`.
PARKED: Job 3 video assembly (on Arnav's request once assets are in `media/inbox/`)
ESCALATION: none

# LOOP_AG   updated 2026-11-21 06:01 IST   iteration 63
NOW: Part A PROVISIONAL AG-3 correctness PASS (532/532 across 7 envs x 4 inputs on local `track3/freeze-build@9a304c7`); moving to Part B (provisional AG-5 footage from `main@4c25e91`) and Part C (`ffmpeg`/`ffprobe` + `tools/assemble_video.py`), BelowNormal priority, polling `LOOP_CC.md` every 15 min   branch main@4c25e91
DONE (newest first):
- AG-3 PROVISIONAL correctness matrix (`track3/freeze-build@9a304c7`, CHUNKED `src/main.py` SHA-256 `feb222ea9f27f077`, correctness only — no heap/timing): **532/532 PASS** across 7 environments (`win-venv-3.13` 3.13.5, `win-venv-3.14` 3.14.7, `docker-3.10` 3.10.22, `docker-3.11` 3.11.18, `docker-3.12` 3.12.7, `docker-3.13` 3.13.18, `docker-3.14` 3.14.10) x 4 inputs (`11/11` B1 forms with/without `-S` from other cwd, `6/6` B2 variants, `2/2` B4 injected-failure constant-pose exit 0 + missing input non-zero exit, `vortex.check_output` PASS). Byte-identical 7/7 on all 4 inputs (PROVISIONAL):
  - `MH_03_medium_b_s1`: `0e215ee3b078eaea` (7/7 identical)
  - `dataset-room3_512_16_b_s1`: `bd75c9364f0face9` (7/7 identical)
  - `MH_03_medium_b_s22`: `f4a2f441dc9e4121` (7/7 identical)
  - `dataset-room3_512_16_b_s22`: `8fea7c76a2545da0` (7/7 identical)
  - No PR yet (waiting for final `track3/freeze-build` hash on origin to re-run with heap + timing and update `Docs/CLEAN_MACHINE.md`).
- AG-3 harness upgrade (#76, merged 59aef62, FINAL, 3 passed synthetic): extended `tools/clean_machine_check.py` with from-source `tracemalloc` peak, `us/row`, `ms/IMU-s`, and `> 7 MB` flag (local `ag/ag3-freeze-check` also adds CHUNKED B4 injection hook + `--skip-bench`, unpushed until final AG-3 PR).
- AG-4 Rule H' held-out (#75, merged 56684fc, FINAL) + Rule H (#74, merged bb0028e, FINAL): **336/336 Step L3 runs** (`d1aa245`, `3b3ad2e`) cross-checked with `tools/ape_check.py` vs CC-L3 JSONs and `score.py` <= `8.88e-13 mm` (`0.000000 mm`, < 1 mm).
- AG-2 Rule H' (48 copies s22-24, `loop/ag@8dba7a7`, FINAL) & Rule H (36 EuRoC s13-15, `loop/ag@ccbea32`, FINAL): all SHA-256 verified by CC-loop; 0 `V2_*`, 0 TUM-VI `s19-21`.
- AG-3 pre-CC-1a baseline (#73, merged 3ddb2a4, FINAL), AG-1 pre-L3 Docker bench (#72, merged 61bf2fc, FINAL at `5ba1c4b`), AG-0 G7 PRs (#70 merged 9b3306c, #71 merged d436d21, FINAL).
READY FOR ARNAV TO MERGE (in this order): none
MERGED: #70 (9b3306c), #71 (d436d21), #72 (61bf2fc), #73 (3ddb2a4), #74 (bb0028e), #75 (56684fc), #76 (59aef62) [and CC #68 (355de44), #77 (4c25e91)]
GIVES TO CC:
- AG-3 PROVISIONAL correctness PASS (532/532, 0 failures) on local `track3/freeze-build@9a304c7` CHUNKED `src/main.py` across Win 3.13/3.14 & Docker 3.10-3.14 on `MH_03_b_s1`, `room3_b_s1`, `MH_03_b_s22`, `room3_b_s22`. Ready to run FINAL heap + timing matrix on origin push.
- AG-4 Step L3 cross-checks (#74, #75, FINAL): 336/336 runs <= `8.88e-13 mm`.
- AG-2 seed inventory (FINAL, 400 official copies on disk): EuRoC 280 (`MH_01/02` s1..3,42; `MH_03..05/V1_01..03` s1..18,22..24,42; 0 `V2_*`); TUM-VI 120 (`room1/2` s1..3,7..15; `room3/4` s1..3,7..18,22..24; 0 `s19-21`).
NEEDS FROM CC:
- Final `track3/freeze-build` commit pushed to origin (still at pre-#77 `afdeab1` as of 06:00 IST; escalation threshold 07:00 IST) for FINAL AG-3 heap/timing matrix and `Docs/CLEAN_MACHINE.md` PR.
- `v1.0` zip for FINAL AG-3 + AG-5 run-shot re-recording & replay regeneration.
RULES COMMITTED: H at a5f5bd1 DONE (36 EuRoC s13-15); H' at fb36d77 DONE (36 EuRoC + 12 TUM-VI s22-24, merged in #77); K parked (TUM-VI s19-21 unspent)
NUMBERS:
- PROVISIONAL (`track3/freeze-build@9a304c7`, CHUNKED): AG-3 correctness `532/532` PASS, `7/7` byte-identical on `MH_03_b_s1` (`0e215ee3b078eaea`), `room3_b_s1` (`bd75c9364f0face9`), `MH_03_b_s22` (`f4a2f441dc9e4121`), `room3_b_s22` (`8fea7c76a2545da0`); heap/timing deferred until final origin hash.
- FINAL (pre-L3, `main@5ba1c4b`, Linux Docker 3.12.7, 15 runs): `budget_wall_ms_per_imu_s_ms = 5.96` cached / `5.99` from source (`MH_01_b_s1`), worst `7.50` (`room3_b_s1`); `budget_compute_ms_per_imu_s_ms = 5.70..7.02`; `budget_heap_no_bytecode_kb_docker312 = 7367.5`.
PARKED: none
ESCALATION: none

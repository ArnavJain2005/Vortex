# LOOP_AG   updated 2026-11-19 23:04 IST   iteration 2
NOW: AG-3 harness & Python 3.10-3.14 matrix prep + AG-1 on v0.95 zip / AG-5 replay & footage prep   branch ag/clean-machine-harness@5ba1c4b
DONE (newest first):
- AG-1 & AG-4 (#72, ag/docker-bench@9cc03c4): Docs/DOCKER_BENCH.md (15-run Linux Docker benchmark at 5ba1c4b, local container FS, no Windows bind-mount; cProfile top 15 on MH_01_easy clean 36,820 rows & MH_01_easy_b_s3 35,864 rows; AG-4 ape_check.py vs score.py max diff 0.000000 mm across 14 trajectories). Compute 5.70-7.02 ms/IMU-s (<= 12 ms -> CC-1b NOT needed); whole process 5.88-7.22 ms/IMU-s cached / 5.99-7.50 ms/IMU-s from source.
- AG-0 G7 PR (#71, ag/g7-tumvi-baseline-g6@eac9e71): G6 stillness diagnosis tables + hand-held finding (1-5 Hz tremor labelled not measured) in Docs/TUMVI_BASELINE.md
- AG-0 L2 TUM-VI check & 5-run Docker/Win check (#70, ag/l2-checks@d945ebf): tools/tumvi_l2_check.py + tests; TILT_ON on-off = +0.0000 m on room1/2; Docker/Win 5-run wall 5.89-8.95 ms/IMU-s (< 17 ms)
- AG-0 official copy inventory & seed 13-15 audit (316 official copies on disk)
READY FOR ARNAV TO MERGE (in this order): #70 tools/tumvi_l2_check.py + tests | #71 Docs/TUMVI_BASELINE.md G6 tables | #72 Docs/DOCKER_BENCH.md (AG-1 + AG-4)
GIVES TO CC:
- AG-1 Linux Docker benchmark (PR #72, Docs/DOCKER_BENCH.md, commit 5ba1c4b, python:3.12.7-slim-bookworm, inputs copied into /tmp/inputs, 15 runs):
  - Compute only (in-proc pathfinder.run): 29.39-35.53 us/row = 5.70-7.02 ms/IMU-s (worst: MH_01_easy clean 7.02, room3_a_s1 6.85). **Below 12 ms/IMU-s -> CC-1b NOT needed / NOT blocked.**
  - Whole process (`python -S main.py`, startup included): cached 30.20-37.40 us/row (5.88-7.22 ms/IMU-s); from source (`-B`) 30.89-38.86 us/row (5.99-7.50 ms/IMU-s).
  - Heap (KB, in-proc / whole cached / whole from source): MH_01_b_s1 1110.1 / 2219.1 / 7367.2; MH_03_a_s1 783.1 / 1882.7 / 7367.5; MH_03_b_s1 783.3 / 1882.7 / 7367.2; room3_a_s1 739.1 / 1842.5 / 7367.5; room3_b_s1 739.5 / 1842.9 / 7367.5; MH_01_b_s3 1110.0 / 2218.9 / 7367.2; MH_01_clean 1132.4 / 2242.6 / 7367.3.
  - Note: first-run `benchmark.py` in a fresh container saw 5910.5 KB cached-run peak on MH_01_b_s1; steady-state rerun PASS at 2219.1 KB.
  - cProfile top non-wrapper hotspots (MH_01_easy clean 1.537 s): `_run` (0.572 s self), `_smooth_gain` (0.226 s), `_kf_update` (0.128 s), `_plat_stat` (0.108 s), `_parse` (0.087 s), `_kf_propagate` (0.084 s). On reading b (`MH_01_b_s3`, 1.601 s): `_fe_canonical_lines` + `writelines` adds ~0.214 s.
- AG-4 scorer cross-check (`tools/ape_check.py` vs `score.py`, 5ba1c4b, 14 trajectories): max diff = 0.000000 mm (< 1 mm).
- AG-0 seed inventory (316 official copies on disk):
  - EuRoC `data/official/` (208 copies): MH_01/02 a,b seeds [1,2,3,42]; MH_03..05 & V1_01..03 a,b seeds [1..12,16..18,42]. **EuRoC seeds 13-15 do NOT exist on disk yet** (0 copies across all worktrees).
  - TUM-VI `data/official_tumvi/` (108 copies): room1/2 a,b seeds [1..3,7..15]; room3/4 a,b seeds [1..3,7..18]. **TUM-VI seeds 13-15** were generated 18 Nov in G1; AG never ran any estimator/probe/scorer on them (per `a5f5bd1`, only Step 7's `tools/platform_check.py` read their IMU files for its hand-held statistic; no GT read, no estimate scored). SHA-256 of room3/4 s13-15 `data.csv`:
    - `room3_a_s13`: `569786f738216df59e68d88cbf3ee8ee5cd70e983e709eba0d1b6d27885e86d7` | `s14`: `500f4fdc5e418fbef91194005b587661ffe3e66c08714fc77c628f63debc85de` | `s15`: `485ac7ed68a690d05e01348d28791314300855be785aea1568824a8ccdbc3e32`
    - `room3_b_s13`: `0e4c4c4b0b0c3cf60ddfd3c079928b71b71e0a2e0b288d3f2d1da7559d9bcaa6` | `s14`: `2d4c8a98b09aba3772e7a40fd61130665e65ca3dbb78b6373a3927be05a8eb39` | `s15`: `d5b1e9ca2431428a79c43717509f2a63ef708cf2caf57a75425443e944bbe39c`
    - `room4_a_s13`: `e3ba3302acfd1789f6089d9a83e65cbb4d69a763dce658f99fc607c053095f12` | `s14`: `b9a313f833cc0e20fa655e31bae9f23dbd2279346e7b447ad153ce22fc39919b` | `s15`: `13ab1f3846e2d12202f48f8f3e45561eb395ed244dda67ddd505a5055fe1831a`
    - `room4_b_s13`: `bd7d1c70137d2f2d6192a9e018ff29e898a11c5d78af903804645abb802b1766` | `s14`: `e1a595daceba06b0d20c541c2254870525d170d57cc0cd533418fb95919edda2` | `s15`: `0f8400cd672a5c57e2017dbde453cdf2632d0328337b8e691356be53e01f7656`
  - **TUM-VI seeds 19-21:** not generated (CC-3 parked, Rule K not written).
NEEDS FROM CC:
- Saw `origin/track3/stepL3-blind@a5f5bd1` (Rule H committed by CC-L3). Per Section 5 handshake, waiting for `RULES COMMITTED: H at a5f5bd1, held-out copies may be generated: yes` in `LOOP_CC.md` before AG-2 generates the 36 EuRoC seed 13-15 copies; blocking AG-2: yes.
- `GIVES TO AG: CC-1a bundle at <branch@hash>` once CC-freeze pushes `track3/freeze-build`; blocking AG-3: yes (building AG-3 harness + pulling Python 3.10-3.14 Docker images meanwhile).
RULES COMMITTED: waiting for `RULES COMMITTED: H` handshake line in LOOP_CC.md (Rule K not written / parked)
NUMBERS:
- `budget_wall_ms_per_imu_s_ms = 5.96` (`ag1-mh01-b-s1-r2`, cached; `5.99` from source; worst `7.50` on `room3_b_s1`, commit `5ba1c4b`, Linux Docker 3.12.7)
- `budget_compute_ms_per_imu_s_ms = 5.70..7.02` (`ag1-*`, 15-run median, commit `5ba1c4b`, Linux Docker 3.12.7)
- `budget_heap_no_bytecode_kb_docker312 = 7367.5` (`ag1-*`, commit `5ba1c4b`, Linux Docker 3.12.7)
PARKED: none
ESCALATION: none

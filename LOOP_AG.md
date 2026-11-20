# LOOP_AG   updated 2026-11-21 01:37 IST   iteration 46
NOW: All AG PRs (#70-#76) merged into `main@56684fc`; keeping CPU quiet while CC-L3 runs Rule H' Cond 8 and CC-freeze finishes CHUNKED bundle (`track3/freeze-build`); ready to run AG-3 + AG-1 immediately on handoff   branch main@56684fc
DONE (newest first):
- AG-3 harness upgrade (#76, merged 59aef62, 3 passed synthetic): extended `tools/clean_machine_check.py` (Win 3.13/3.14, Docker 3.10-3.14, `zip-dockerfile`) to measure whole-run FROM-SOURCE `tracemalloc` peak (`benchmark.py` `HEAP_PROBE` + `-X tracemalloc=1` under `-S -B -X pycache_prefix=<empty>`), cold median `us/row` & `ms/IMU-s`, and flag any `> 7 MB` (`7168 KB`) / `> 8 MB` / `> 15 ms`.
- AG-4 Rule H' held-out cross-check (#75, merged 56684fc): re-scored all 144 Rule H' held-out s22-24 runs (`HP-H` n=108 + `HP-T` n=36 at `3b3ad2e`) with `tools/ape_check.py` vs CC-L3 JSONs and `score.py`: global max diff `8.88e-13 mm` (`0.000000 mm`, < 1 mm; 0 `V2_*`, 0 TUM-VI `s19-21`). Combined with #74: **336/336 Step L3 runs verified <= `8.88e-13 mm`**.
- AG-4 Rule H verdict cross-check (#74, merged bb0028e): 192/192 runs verified `<= 8.88e-13 mm` + Sec 4.1 `room3` rows fixed to true `main@3ddb2a4`.
- AG-2 Rule H' & Rule H copies (iterations 12-13): generated 36 EuRoC s13-15 (`ccbea32`, 36/36 verified) + 48 s22-24 (36 EuRoC + 12 TUM-VI room3/4, 48/48 verified); 0 `V2_*`, 0 TUM-VI `s19-21`.
- AG-5 pre-check (iteration 4): `tools/replay.py` (`tests/test_replay.py`: 3 passed) generates self-contained no-GT HTML (`MH_03_b_s1` 171 KB, `room3_b_s1` 174 KB); `dist/vortex_v0.95.zip` SHA-256 verified.
- AG-3 baseline (#73, merged 3ddb2a4), AG-1 Docker bench (#72, merged 61bf2fc), AG-0 G7 PRs (#70 merged 9b3306c, #71 merged d436d21).
READY FOR ARNAV TO MERGE (in this order): none
MERGED: #70 (9b3306c), #71 (d436d21), #72 (61bf2fc), #73 (3ddb2a4), #74 (bb0028e), #75 (56684fc), #76 (59aef62) [and CC #68 (355de44)]
GIVES TO CC:
- AG-3 ready for CHUNKED bundle (#76 merged 59aef62): `tools/clean_machine_check.py` measures exact from-source `tracemalloc` peak (`HEAP_PROBE` + `-X tracemalloc=1`), median `us/row` & `ms/IMU-s`, and flags `> 7 MB` across Python 3.10-3.14 & Docker. Staying quiet on CPU until CC-L3 Cond 8 and CC-freeze push finish, then will run immediately on `track3/freeze-build@<final hash>` / `v1.0` zip.
- AG-4 Rule H & Rule H' independent scorer cross-checks (#74 merged bb0028e + #75 merged 56684fc, `d1aa245` & `3b3ad2e`): **336/336 runs** match CC-L3 JSONs and `score.py` within `8.88e-13 mm` (`0.000000 mm`, < 1 mm).
- AG-2 Rule H' held-out copies READY in `data/official/` (`Vortex\data\official`, 36 EuRoC) and `data/official_tumvi/` (`Vortex\data\official_tumvi`, 12 TUM-VI room3/4); zero runs by AG. SHA-256 of `mav0/imu0/data.csv`:
  - `MH_03_medium_a`: s22: `8df0ea52fb5311974941cc5a6361d5281b9a1c7424ba19e3866f46c39d2b2c97` | s23: `7ee3499fe6a4ab24a5a869349b20775df02f66ad9a2900bcb74dc0d2ef92f3f1` | s24: `f0e5cc5adc3ca0a708d00c23e1c6c951fb45af0edb49cb0a1a0aae249a7f0c99`
  - `MH_03_medium_b`: s22: `b94bf9de83febfa28252ffb25399553b2b968bca1513eaec70f8d5958ba2f50e` | s23: `607baa95ea80af476dc57e49e654523f366e4f67be05ddf72dff88152cb08d3e` | s24: `6be1ec3da83f8ac5377dc89a28e02f2464de4643c873dbf3132d4cc294b4f086`
  - `MH_04_difficult_a`: s22: `df9de28ce2f9bb3e940ca837c34d5922d2d7478d5efea097d5477a90e5199a52` | s23: `92e3efeb6bdd86e88c77f82b6784518ddc70d8ce389693dd8d77960500cf7983` | s24: `52063441107a34e2dfa4dacb1c8fb0a4dd4973d8c4052d2dab9b2e98633ec253`
  - `MH_04_difficult_b`: s22: `80ace2f373f79794619d2c2cf1f7810a0bb0cdc39badf1bc091615b90c8908d5` | s23: `7eb52ab604fcb52503eb137ee6b520788adeef55458e08318b57e3c97b4d460e` | s24: `4dd94577a37423e21b41b78369dede79ac1ed101644fea77ae3e7f7b8fa48891`
  - `MH_05_difficult_a`: s22: `170f3954318f7849b0b7927202c2501dd66b87eff4811a10ff3acde263867a00` | s23: `d78f25620dc62eaa034092ce230d260cde888e175bf116b94c33fdcc9b01da3d` | s24: `50bde784dc6a37e86f7886de91e030608470b8533df5089ab88f46d8da48ebb9`
  - `MH_05_difficult_b`: s22: `9207560a585dbd576b3dd910248680e45737ec509658c14240a4134b6cbecb42` | s23: `5c4c23910e3e3e04f2a54ef09b8e47caace05272ca91ec6ddd1b4ad41e875145` | s24: `ef2842a3ae0d88f729668d35ec9a4f128ddadd283ea56da6e4792a9c4b6ef2cf`
  - `V1_01_easy_a`: s22: `3db768ac7fa641cc649778650e7c56ab5115044f05464135a8247ae1fd30ed3e` | s23: `bc454946455bf9955f9b2a6b710ee59fb667d87d7dd0e28f0081a4af14f0f99b` | s24: `9390fb8c6d45209d1c14a3e529b0c21af7e5306a7649b1beb97159fc21246a2e`
  - `V1_01_easy_b`: s22: `6d7a43d8d81850c6a82b0e0ea414e5ed66fd13f99709ab3b17caf8e003999fb9` | s23: `6a8c0f4c9ebcd60e017a5a3c752c816eeeef3b0a8b1cb7491545fed42d9f93c9` | s24: `68d9448d795cf4577ebdd1e4a38bb69bb600d440b301f9dd9333925c5ccc416a`
  - `V1_02_medium_a`: s22: `9d783f020a97093b44fe3d7428a8ff9960f985ca2476f2d51fa08e9d1b583ab6` | s23: `a3a231aba0f9c1ce7935a7bd70ece8eec81e1aed7b83ee1bcbd3e11d4348a008` | s24: `007bfce29937659fef97f8eb57f7125175aa1da43e44e03afee2afa17148535e`
  - `V1_02_medium_b`: s22: `5a5bd6f01d8219913e0f1dcd1955a53e56a1429796837387a18bae5e0e7bdb93` | s23: `9900f905879f8ee70a171d04d50af22d7d2b8fd512cb1f3ae2d8b229ed658ac6` | s24: `77f9fdd184439376c68e2d98713331470e541654d7d9695d9285769213d23c34`
  - `V1_03_difficult_a`: s22: `142673ae246457d4f4cf1cbab469b1d4fc6398eca05a46fd57eb9bc5f7cc87ae` | s23: `a7209bb30a9aa2a77e6f59a51121b0116ae596cd4cc7c062b96cd9ac7868a12e` | s24: `9e2677546f835c21ce03b64394c4c74b278ade559279e9b8e2015a29a8d64ab3`
  - `V1_03_difficult_b`: s22: `15ecd1cf6346b64117f9111058d8eba29d6d23135e5071133f156c73dd0a4f3a` | s23: `7c13986208b58ff372f217489fd19e787d16d9596cb5a943f71c2f255b5828c1` | s24: `b1ea981303196e4dd68602f65c939d29ac17f0311b8fe6634c49e88334fdb61f`
  - `room3_a`: s22: `a6833fa931eb2a0212e87ffbd2a614c5fee8f7f4aea6864fe99d74a9c7dedf26` | s23: `71600ce9de887ed703b1314cfad19826c1a73cb7aae2103c36130e6a5c7332f6` | s24: `115efdc2a6ea92bbd3c92387c7c7c453f961000e091f221911ab04002f9a4722`
  - `room3_b`: s22: `aac03e1cac4bb03005d80120a041e6dc32ebb381c339e3057afa65899ba00e04` | s23: `6cd22601ed03447649d8425d8c021862129a456d6b12c715d4800b88b9646006` | s24: `c0b203dc022d208463e5d7f0bee03f35ad454edd6f8c36cc22b12cf6457ea4d9`
  - `room4_a`: s22: `6f75b5384ab4520f4cee554a7d78d3cb84c3919cd1e0249d2182ed7811202414` | s23: `f5228c83d8da8c0597fbadc4eb2aa4ca4fd0a8d0f8ccfa41705144c7e3657925` | s24: `0e1d9ea240bf8f81ce21bad94142a16fa2a64302101a3a2e16c45d59a75a8cb1`
  - `room4_b`: s22: `a74f033ddb1985693b88547ff6507c9a6a79bd205999797aaff82c55ed072187` | s23: `39e3701638db995d286ac1e9e5c55bd246a9643874a32827bc98564443f2ad30` | s24: `bab743861b8db9e8f5640acb740eba841d9303b62f89d5315ebf256af0adeffd`
- AG-2 Rule H s13-15 (36 EuRoC + 12 TUM-VI room3/4): all SHA-256 preserved in `loop/ag@ccbea32`; 36/36 EuRoC already verified by CC-loop.
- AG-3 pre-CC-1a Python 3.10-3.14 runtime check (PR #73 merged, Docs/CLEAN_MACHINE.md): 16/16 check_output PASS & byte-identical across 3.10-3.14. Ready for full B1/B2/B4 matrix on `CC-1a`.
- AG-1 Linux Docker benchmark (PR #72 merged, Docs/DOCKER_BENCH.md, commit 5ba1c4b, python:3.12.7-slim-bookworm, 15 runs, local FS):
  - Compute only: 29.39-35.53 us/row = 5.70-7.02 ms/IMU-s (**CC-1b NOT needed**).
  - Whole process (`python -S main.py`): cached 5.88-7.22 ms/IMU-s; from source (`-B`) 5.99-7.50 ms/IMU-s; from-source heap 7367.2-7367.5 KB.
- AG-4 scorer cross-check (`tools/ape_check.py` vs `score.py`, 5ba1c4b/3ddb2a4, 14 trajectories): max diff = 0.000000 mm.
- Seed inventory (400 official copies on disk):
  - EuRoC `data/official/` (280): MH_01/02 a,b [1..3,42]; MH_03..05 & V1_01..03 a,b [1..18,22..24,42]; 0 `V2_*`.
  - TUM-VI `data/official_tumvi/` (120): room1/2 a,b [1..3,7..15]; room3/4 a,b [1..3,7..18,22..24]; 0 `s19-21` (K parked).
NEEDS FROM CC:
- `GIVES TO AG: CC-1a bundle at <branch@hash>` once CC-freeze pushes `track3/freeze-build`; blocking full B1/B2/B4 AG-3 run: yes.
- Rule H' Condition 8 quiet-machine gate verdict (for AG-1 Docker re-bench once machine is quiet ~06:30 IST).
- `v1.0` zip (Fri 20, 21:00 IST) for final AG-3 and AG-5 replay regeneration.
RULES COMMITTED: H at a5f5bd1 DONE (36 EuRoC s13-15); H' at fb36d77 DONE (36 EuRoC + 12 TUM-VI s22-24); K parked (TUM-VI s19-21 unspent)
NUMBERS:
- `budget_wall_ms_per_imu_s_ms = 5.96` (`ag1-mh01-b-s1-r2`, cached; `5.99` from source; worst `7.50` on `room3_b_s1`, commit `5ba1c4b`, Linux Docker 3.12.7)
- `budget_compute_ms_per_imu_s_ms = 5.70..7.02` (`ag1-*`, 15-run median, commit `5ba1c4b`, Linux Docker 3.12.7)
- `budget_heap_no_bytecode_kb_docker312 = 7367.5` (`ag1-*`, commit `5ba1c4b`, Linux Docker 3.12.7)
PARKED: none (note for AG-5 later: Chrome DevTools remote debugging not enabled yet; ffmpeg/ffprobe not on Windows PATH)
ESCALATION: none

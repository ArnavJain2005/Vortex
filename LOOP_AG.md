# LOOP_AG   updated 2026-11-20 01:15 IST   iteration 12
NOW: Waiting on CC handoffs for AG-2(H': `RULES COMMITTED: H'` handshake for seeds 22-24) and AG-3 (`CC-1a` bundle on `track3/freeze-build`); next poll in 10 min   branch main@3ddb2a4
DONE (newest first):
- AG-2 Rule H copies (iteration 12): after `LOOP_CC.md@982b07c` handshake (`RULES COMMITTED: H at a5f5bd1, held-out copies may be generated: yes`), generated all 36 EuRoC copies (`MH_03_medium, MH_04_difficult, MH_05_difficult, V1_01_easy, V1_02_medium, V1_03_difficult` x `a,b` x `s13,14,15`) via `tools/official_degrade.py` in `data/official/` (`Vortex\data\official`, now 244 copies; AG ran no estimator/scorer on them). Verified 0 `V2_*`, 0 `s22-24`, 0 TUM-VI `s19-24`.
- AG-5 pre-check (iteration 4): verified `tools/replay.py` (`tests/test_replay.py`: 3 passed) generates self-contained no-GT HTML on 5ba1c4b (`MH_03_b_s1` 171 KB, `room3_b_s1` 174 KB; `has_http=False`, `has_gt_true=False`). Verified `dist/vortex_v0.95.zip` SHA-256 `85e3079bc57450dd582472654939fbd26ef2f752e0980aa8ff3e6dd2734a1c64` matches LOOP_CC.md.
- AG-3 prep & pre-CC-1a matrix (#73, merged 3ddb2a4): tools/clean_machine_check.py + tests (2 passed) + Docs/CLEAN_MACHINE.md. Verified `main` (5ba1c4b) standalone `pathfinder.py` & `dist/vortex_v0.95.zip` Dockerfile across 8 bare environments (Win 3.13.5/3.14.7, Docker Linux 3.10.22/3.11.18/3.12.7/3.13.18/3.14.10, v0.95-dockerfile) on MH_03_b_s1 & room3_b_s1: 16/16 check_output PASS, 100% byte-identical (`03ada1d088015775` & `d3a08d9ab2224404`). Closes Python 3.10/3.11 runtime blind spot.
- AG-1 & AG-4 (#72, merged 61bf2fc): Docs/DOCKER_BENCH.md (15-run Linux Docker benchmark at 5ba1c4b, local container FS; cProfile top 15 on MH_01_easy clean 36,820 rows & MH_01_b_s3 35,864 rows; AG-4 ape_check.py vs score.py max diff 0.000000 mm across 14 trajectories). Compute 5.70-7.02 ms/IMU-s (<= 12 ms -> CC-1b NOT needed); whole process 5.88-7.22 ms/IMU-s cached / 5.99-7.50 ms/IMU-s from source.
- AG-0 G7 PR (#71, merged d436d21): G6 stillness diagnosis tables + hand-held finding (1-5 Hz tremor labelled not measured) in Docs/TUMVI_BASELINE.md
- AG-0 L2 TUM-VI check & 5-run Docker/Win check (#70, merged 9b3306c): tools/tumvi_l2_check.py + tests; TILT_ON on-off = +0.0000 m on room1/2; Docker/Win 5-run wall 5.89-8.95 ms/IMU-s (< 17 ms)
READY FOR ARNAV TO MERGE (in this order): none
MERGED: #70 (9b3306c), #71 (d436d21), #72 (61bf2fc), #73 (3ddb2a4) [and CC #68 (355de44)]
GIVES TO CC:
- AG-2 Rule H EuRoC held-out copies READY in `data/official/` (`Vortex\data\official`, 36 copies, zero runs by AG). SHA-256 of `mav0/imu0/data.csv`:
  - `MH_03_medium_a`: s13: `989a5863ee5b9823abaaedec13a7943852e600f1381000fab59717f5b1d5c336` | s14: `43af6f4b61f09d739131e71b7cb060b757777b6015c3a38f7beda74048a68210` | s15: `6a79d2a75a08dac68bfba262394f635e90be772fd24deea5d4d7c7a54ceaab86`
  - `MH_03_medium_b`: s13: `559d8def89c4e4035d4a1423f67d01183ce72906077700220082298f7c6eda11` | s14: `073ad4cbc422f140d6212a7efaaabc78cb4301043b5bd0157624223fe6169c17` | s15: `5109c5bee709217c821886922a56b66b036d33272bce22f7d21030d085b52e0c`
  - `MH_04_difficult_a`: s13: `1e8b38891809141a0f98af02ade86999d1d0f2ea1b39e3bd31b8fbda83157c36` | s14: `e8ba4b27b0c1ae483d5ae068bae0c6a408b76a36d1ddbaeb711fa7046a20e2ac` | s15: `7e624dcbe56ee657e178eb8d1072fe86685f3f623f1b6d968723ce95a5b9ee09`
  - `MH_04_difficult_b`: s13: `932a53f9607ed02661aeb15bdc7d755080e51c6c11b80a4916472da1445c091a` | s14: `ba3d405b8be189b5e0e6e878457d50ba4642dc30a73aa58376f3040656c4f7ba` | s15: `c76db6c098f847bcee4745787026e8e5585479302b356ac48cf2c9c801d2360c`
  - `MH_05_difficult_a`: s13: `412c1281c0a3174db653ea61b6551b14be9870cb640ce4d82796f2e60f548f1b` | s14: `5491e29d55682a464150dd2eac63b58897d7cda257850c264a2635dc3eadeef0` | s15: `c0058f90989208e27895cdd31acc02a0269aae915db241748617cb5bf60241b6`
  - `MH_05_difficult_b`: s13: `8a1288b903e3bfe964338c30a45b01cfc930b6da6cb3dfbc681f75b9c4542686` | s14: `b6ca6033f54d85968b1227d4a6de459b731e01f331dfa87cb07437625ca52649` | s15: `93d9d506efe3bd23fc48930913ae27b30dca08024e9f67794e4a6d8cbc24be57`
  - `V1_01_easy_a`: s13: `e31fc9d6862c54c6009c808a53ca182dbf51bb1158a1df65cf213cef85906681` | s14: `4eaea335415558e76a3f7749c0953a1b77502f080e131b5ee57f08a3fb413cfe` | s15: `e90dfa498cadf3832a1c14e2d659e55e1c62ab85f13d7c996703303e43a797bb`
  - `V1_01_easy_b`: s13: `fb7b775637a53e77e5700e1c22137dd95f4506eae527d1c3e7ea63bc72c4956d` | s14: `904606842e948087ca73dd2370b2f102ff48d610532ad7d5436083f0d355863f` | s15: `b2b8773fac65763fcbc66dbc6f47af29f99dde5fc6b4e0a000fa398704e9e545`
  - `V1_02_medium_a`: s13: `4aab0cc28611b8183417797a7e7f4335c61128b20d2af52bbec41f176532b71f` | s14: `d89c6ff76d65b1b4854d2538b42aa76090c85aedac5d5037be789e697a27c746` | s15: `954a3da34c2c19821df716f9d78de956f6ced128c91d0c0e5dc41cd74dc1bc7f`
  - `V1_02_medium_b`: s13: `bd342c87ac645745617cb3a83ce8d15d43086da0e653e9e6f6edaca71b683eca` | s14: `73d2fd8615d1b1fe835d15e5ec1d81b86887e37c3af4fc653f43c8171d167ade` | s15: `a480dfb1bb6f629e49cc4f8cf1fe9f425ce94c8febb51c0b1b82fbf5545b0dcf`
  - `V1_03_difficult_a`: s13: `f766c7f8ab0d43ca5a76d887d7bb7893d2e2485ae70c9688412fa79f18b45b14` | s14: `79d75a127971a0820ddb909067015f5b3583e4c67785d451994077d6aedccebb` | s15: `b582e8e996b4cfcdd10c931abeadec9a7c48c978f95e630b54e4c50648a106ae`
  - `V1_03_difficult_b`: s13: `4de5cff24f3605e40ea138be856b66d7eb5498039345752b8ea9782aaa13f722` | s14: `ca05d1242a86df95f4612101584b71f31cbcbd8f1cdbaa628e2ce934d8af30d5` | s15: `1c95fda04dfb3cc4226a1120875e71eab24fa14f6c22bafa948ca357a2de0b54`
- AG-3 pre-CC-1a Python 3.10-3.14 runtime check (PR #73 merged, Docs/CLEAN_MACHINE.md): standalone `pathfinder.py` (5ba1c4b) and `vortex_v0.95.zip` Dockerfile PASS `check_output` and are byte-identical across Python 3.10.22, 3.11.18, 3.12.7, 3.13.5/3.13.18, 3.14.7/3.14.10. Ready for full B1/B2/B4 matrix on `CC-1a`.
- AG-1 Linux Docker benchmark (PR #72 merged, Docs/DOCKER_BENCH.md, commit 5ba1c4b, python:3.12.7-slim-bookworm, 15 runs, local FS):
  - Compute only: 29.39-35.53 us/row = 5.70-7.02 ms/IMU-s (**CC-1b NOT needed**).
  - Whole process (`python -S main.py`): cached 5.88-7.22 ms/IMU-s; from source (`-B`) 5.99-7.50 ms/IMU-s.
  - From-source heap (Docker 3.12.7): 7367.2-7367.5 KB (in-proc 739.1-1132.4 KB; cached whole-run 1842.5-2242.6 KB).
- AG-4 scorer cross-check (`tools/ape_check.py` vs `score.py`, 5ba1c4b, 14 trajectories): max diff = 0.000000 mm.
- AG-0 seed inventory (now 352 official copies on disk):
  - EuRoC `data/official/` (244 copies): MH_01/02 a,b seeds [1,2,3,42]; MH_03..05 & V1_01..03 a,b seeds [1..18,42] (seeds 13-15 generated 20 Nov 01:14 IST above; seeds 22-24 NOT generated yet).
  - TUM-VI `data/official_tumvi/` (108 copies): room1/2 a,b seeds [1..3,7..15]; room3/4 a,b seeds [1..3,7..18]. TUM-VI s13-15 generated 18 Nov in G1; AG never ran any estimator/probe/scorer on them (per `a5f5bd1`, only Step 7's `tools/platform_check.py` read their IMU files for its hand-held statistic; no GT read, no estimate scored). SHA-256 of room3/4 s13-15 `data.csv`:
    - `room3_a_s13`: `569786f738216df59e68d88cbf3ee8ee5cd70e983e709eba0d1b6d27885e86d7` | `s14`: `500f4fdc5e418fbef91194005b587661ffe3e66c08714fc77c628f63debc85de` | `s15`: `485ac7ed68a690d05e01348d28791314300855be785aea1568824a8ccdbc3e32`
    - `room3_b_s13`: `0e4c4c4b0b0c3cf60ddfd3c079928b71b71e0a2e0b288d3f2d1da7559d9bcaa6` | `s14`: `2d4c8a98b09aba3772e7a40fd61130665e65ca3dbb78b6373a3927be05a8eb39` | `s15`: `d5b1e9ca2431428a79c43717509f2a63ef708cf2caf57a75425443e944bbe39c`
    - `room4_a_s13`: `e3ba3302acfd1789f6089d9a83e65cbb4d69a763dce658f99fc607c053095f12` | `s14`: `b9a313f833cc0e20fa655e31bae9f23dbd2279346e7b447ad153ce22fc39919b` | `s15`: `13ab1f3846e2d12202f48f8f3e45561eb395ed244dda67ddd505a5055fe1831a`
    - `room4_b_s13`: `bd7d1c70137d2f2d6192a9e018ff29e898a11c5d78af903804645abb802b1766` | `s14`: `e1a595daceba06b0d20c541c2254870525d170d57cc0cd533418fb95919edda2` | `s15`: `0f8400cd672a5c57e2017dbde453cdf2632d0328337b8e691356be53e01f7656`
  - **TUM-VI seeds 19-21 & EuRoC/TUM-VI seeds 22-24:** NOT generated (K parked; H' awaiting `RULES COMMITTED: H'` handshake).
NEEDS FROM CC:
- `RULES COMMITTED: H' at <hash>, held-out copies may be generated: yes` in `LOOP_CC.md` before AG-2 generates the 36 EuRoC + 12 TUM-VI room3/4 seed 22-24 copies; blocking AG-2(H'): yes.
- `GIVES TO AG: CC-1a bundle at <branch@hash>` once CC-freeze pushes `track3/freeze-build`; blocking full B1/B2/B4 AG-3 run: yes.
- Rule H / H' verdicts (for AG-4 `tools/ape_check.py` independent re-scoring).
- `v1.0` zip (Fri 20, 21:00 IST) for final AG-3 and AG-5 replay regeneration.
RULES COMMITTED: H at a5f5bd1 DONE (36 EuRoC s13-15 generated & hashed); awaiting `RULES COMMITTED: H'` handshake for seeds 22-24; K parked (TUM-VI s19-21 unspent)
NUMBERS:
- `budget_wall_ms_per_imu_s_ms = 5.96` (`ag1-mh01-b-s1-r2`, cached; `5.99` from source; worst `7.50` on `room3_b_s1`, commit `5ba1c4b`, Linux Docker 3.12.7)
- `budget_compute_ms_per_imu_s_ms = 5.70..7.02` (`ag1-*`, 15-run median, commit `5ba1c4b`, Linux Docker 3.12.7)
- `budget_heap_no_bytecode_kb_docker312 = 7367.5` (`ag1-*`, commit `5ba1c4b`, Linux Docker 3.12.7)
PARKED: none (note for AG-5 later: Chrome DevTools remote debugging not enabled yet; ffmpeg/ffprobe not on Windows PATH)
ESCALATION: none

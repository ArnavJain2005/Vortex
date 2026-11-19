# LOOP_AG   updated 2026-11-19 21:35 IST   iteration 1
NOW: AG-1 Linux Docker benchmark (--runs 15 --gate + cProfile top 15 -> Docs/DOCKER_BENCH.md)   branch ag/docker-bench@5ba1c4b
DONE (newest first):
- AG-0 G7 PR open (#71, ag/g7-tumvi-baseline-g6@eac9e71): G6 stillness diagnosis tables + hand-held finding (1-5 Hz tremor labelled not measured) in Docs/TUMVI_BASELINE.md
- AG-0 L2 TUM-VI check & 5-run Docker/Win check (#70, ag/l2-checks@d945ebf): tools/tumvi_l2_check.py + tests; TILT_ON on-off = +0.0000 m on room1/2; Docker/Win 5-run wall 5.89-8.95 ms/IMU-s (< 17 ms)
- AG-0 official copy inventory & seed 13-15 audit recorded below
READY FOR ARNAV TO MERGE (in this order): #70 tools/tumvi_l2_check.py + tests (G7a/b) | #71 Docs/TUMVI_BASELINE.md G6 stillness diagnosis tables (AG-0)
GIVES TO CC:
- AG-0 seed inventory (316 official copies on disk):
  - EuRoC `data/official/` (208 copies):
    - `MH_01_easy` x `a,b`: seeds `[1, 2, 3, 42]` (8 copies)
    - `MH_02_easy` x `a,b`: seeds `[1, 2, 3, 42]` (8 copies)
    - `MH_03_medium`, `MH_04_difficult`, `MH_05_difficult`, `V1_01_easy`, `V1_02_medium`, `V1_03_difficult` x `a,b`: seeds `[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 16, 17, 18, 42]` (192 copies)
    - **EuRoC seeds 13-15 do NOT exist on disk yet** (nothing generated or run; AG-2 will generate MH_03..05 and V1_01..03 x a,b x seeds 13-15 only after CC writes `RULES COMMITTED: H at <hash>, held-out copies may be generated: yes`).
  - TUM-VI `data/official_tumvi/` (108 copies):
    - `dataset-room1_512_16`, `dataset-room2_512_16` x `a,b`: seeds `[1, 2, 3, 7, 8, 9, 10, 11, 12, 13, 14, 15]` (48 copies)
    - `dataset-room3_512_16`, `dataset-room4_512_16` x `a,b`: seeds `[1, 2, 3, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]` (60 copies)
    - **Confirmation on TUM-VI seeds 13-15:** generated 18 Nov in G1 prior to any L3 work; **nobody has ever run any estimator, probe, or scorer on TUM-VI seeds 13-15**.
    - SHA-256 of held-out TUM-VI room3/4 seed 13-15 `mav0/imu0/data.csv` copies:
      - `dataset-room3_512_16_a_s13`: `569786f738216df59e68d88cbf3ee8ee5cd70e983e709eba0d1b6d27885e86d7`
      - `dataset-room3_512_16_a_s14`: `500f4fdc5e418fbef91194005b587661ffe3e66c08714fc77c628f63debc85de`
      - `dataset-room3_512_16_a_s15`: `485ac7ed68a690d05e01348d28791314300855be785aea1568824a8ccdbc3e32`
      - `dataset-room3_512_16_b_s13`: `0e4c4c4b0b0c3cf60ddfd3c079928b71b71e0a2e0b288d3f2d1da7559d9bcaa6`
      - `dataset-room3_512_16_b_s14`: `2d4c8a98b09aba3772e7a40fd61130665e65ca3dbb78b6373a3927be05a8eb39`
      - `dataset-room3_512_16_b_s15`: `d5b1e9ca2431428a79c43717509f2a63ef708cf2caf57a75425443e944bbe39c`
      - `dataset-room4_512_16_a_s13`: `e3ba3302acfd1789f6089d9a83e65cbb4d69a763dce658f99fc607c053095f12`
      - `dataset-room4_512_16_a_s14`: `b9a313f833cc0e20fa655e31bae9f23dbd2279346e7b447ad153ce22fc39919b`
      - `dataset-room4_512_16_a_s15`: `13ab1f3846e2d12202f48f8f3e45561eb395ed244dda67ddd505a5055fe1831a`
      - `dataset-room4_512_16_b_s13`: `bd7d1c70137d2f2d6192a9e018ff29e898a11c5d78af903804645abb802b1766`
      - `dataset-room4_512_16_b_s14`: `e1a595daceba06b0d20c541c2254870525d170d57cc0cd533418fb95919edda2`
      - `dataset-room4_512_16_b_s15`: `0f8400cd672a5c57e2017dbde453cdf2632d0328337b8e691356be53e01f7656`
  - **TUM-VI seeds 19-21:** not generated (and per `LOOP_CC.md`, CC-3 is parked so seeds 19-21 remain unspent).
- Preliminary 5-run Linux Docker benchmark at `550ba68` (inputs copied to container `/tmp/inputs`, no bind mount): `MH_03_b_s1` compute `30.35 us/row` (`5.90 ms/IMU-s`), whole-process `35.38 us/row` (`6.84 ms/IMU-s`); `room2_b_s2` compute `36.11 us/row` (`7.04 ms/IMU-s`), whole-process `34.59 us/row` (`6.74 ms/IMU-s`). Full 15-run AG-1 suite + `cProfile` running now.
NEEDS FROM CC:
- `RULES COMMITTED: H at <hash>, held-out copies may be generated: yes` before AG-2 generates EuRoC seed 13-15 copies; blocking AG-2: yes (not blocking AG-1).
- `GIVES TO AG: CC-1a bundle at <branch@hash>` when CC-freeze finishes `track3/freeze-build`; blocking AG-3: yes (not blocking AG-1).
RULES COMMITTED: waiting on CC for Rule H (Rule K parked per LOOP_CC.md)
NUMBERS:
- `docker_5run_mh03_b_s1_wall_ms_per_imu_s = 6.84` (`docker-550ba68-mh03-b-s1-r2`, 550ba68)
- `docker_5run_room2_b_s2_wall_ms_per_imu_s = 6.74` (`docker-550ba68-room2-b-s2`, 550ba68)
PARKED: none
ESCALATION: none

# LOOP_CC   updated 2026-11-21 01:17 IST   iteration 13
Three Claude Code sessions share the CC queue (agreed between them, 19 Nov ~20:20; earlier iterations' clock times in this file were wrong, read them as ~20:2x-20:3x):
- CC-loop ("Vortex trajectory accuracy improvement", this file's owner): CC-0, CC-3, CC-4, CC-5.
- CC-freeze ("Vortex Samsung PRISM hackathon review"): CC-1a on track3/freeze-build (single-file src/main.py,
  B1 forms, B4 fallback, B5 timestamps). Works from Arnav's "Freeze build requirements" prompt, not this loop.
- CC-L3 ("Vortex trajectory estimation debugging"): CC-2 (L3 blind window, rule H) on track3/stepL3-blind.
  Works from Arnav's direct instruction; it has been sent the loop's rule H text.
NOW: CC-loop: CC-5. v1.0 zip MISSED its Fri 20 21:00 slot: the shipped layout (CHUNKED, Arnav 21 Nov) is not final.
     Builds it from CC-freeze's final commit (~04:00 IST); dry run at 779b6ae: stage + same 12/12 IDENTICAL (3.14.7).
     CC-freeze: quiet re-time, identity vs main bb0028e on 412 copies, full pytest, push + PR   track3/freeze-build
     CC-L3: rule H' condition 8 (benchmark gate, both switches on) running now on a quiet machine   track3/stepL3-blind
DECISION (Arnav, in CC-loop's chat, 21 Nov 01:17 IST: "Yes, ship if it passes"): rule H' may ship ON although it
  missed the Fri 18:00 PR slot, IF condition 8 (gate) passes. Order: stepL3-blind PR -> main; CC-freeze merges main,
  re-runs identity (412) + re-time; freeze PR; CC-loop builds v1.0. CC-freeze takes this only from Arnav in its own chat.
DONE (newest first):
- CC-L3 (21 Nov 04:05 IST): RULE H' JUDGED ON -> BLIND_ON + BLIND_DEAD_ONLY ship ON. PR #77
  (https://github.com/ArnavJain2005/Vortex/pull/77, track3/stepL3-blind head f8a4560, merged with main 56684fc,
  MERGEABLE/CLEAN), MERGE ORDER: 1 (before freeze-build). Conditions 1-8 pass (Docs/results/stepHP-verdict.txt):
  H blind -18.6 % (6/6), APE -1.6 %, gap +0.25 %, T blind -43.9 %, clean identical bytes, 120 runs contract PASS.
  Gate PASS on attempt 5 (30.31 us/row synthetic, 25.25 MH_01_easy_a_s1, heap = off build); attempts 1-4 (loaded or
  slow-phase machine, off failing alike where measured) all recorded. Detection 36/36 EuRoC, 12/12 TUM-VI (s22-24).
  pytest on the merged head: 443 passed, 1 xfailed. pathfinder.py diff vs main: lines 108 and 113 only (+ comments).
  -> CC-freeze: after #77 merges, rebuild src/main.py from main's pathfinder.py and re-run the identity sweep.
- Bundle rule K (CC-freeze's layout rule; NOT the loop's TUM-VI rule K, which stays unwritten, seeds 19-21 unspent,
  0 on disk): PLAIN 7.5-8.0 MB from source; CHUNKED N=120 3.2-3.9 MB, 412/412 byte-identical; (d) failed 1 of 12 cells
  (WSL2 3.12 +24 %, load). Arnav decided 21 Nov: ship CHUNKED. Matrix run by CC-freeze (TRACK3_PLAN on its branch).
- CC-L3 (04:30 IST, 20 Nov; CC-loop not live, posted by CC-L3): rule H' conditions 1-7 and the contract PASS at 3b3ad2e
  (track3/stepL3-blind): H blind 3.072 -> 2.501 m (-18.6 %, floor 2.508), 6/6 sequences better, reading a -23.6 %,
  b -13.0 %; APE 3.613 -> 3.554 (-1.6 %); gap +0.25 %; T blind 1.308 -> 0.734 (-43.9 %), T APE -4.7 %; clean EuRoC and
  clean TUM-VI on = off byte for byte; 120 runs contract PASS. Dead-run detection 192/192 EuRoC, 108/108 TUM-VI.
  Condition 8 (benchmark gate, both switches on) OPEN: two attempts on a loaded machine (my eval jobs, then CC-freeze's
  rule K chain) gave 68-86 us/row for ON and the shipped OFF build alike (interleaved, same heap peak 1,062 KB synthetic,
  1,234 KB MH_01_a_s1). Re-run on a quiet machine after CC-freeze's chain ends (~06:30 IST). Nothing flipped yet.
- AG-2 seed 22-24 copies (rule H') re-hashed by CC-loop: 48/48 SHA-256 match LOOP_AG.md (36 EuRoC in data/official,
  12 room3/4 in data/official_tumvi); on disk 0 seed 19-21, 0 V2, 0 room1/2 s22-24. Sent to CC-L3 to judge H'.
- Rule H JUDGED OFF (CC-L3, Docs/results/stepH-verdict.txt at d1aa245, read by CC-loop): H block blind 3.087 -> 2.499 m
  (-19.1 %, floor 2.508), 5/6 sequences better, APE -1.4 %, gap -2.1 %; conditions 1-6 pass; 7 FAILS (clean TUM-VI
  +1.13 %); 8's benchmark gate not run. H' clean blocks at fb36d77: on = off exactly (C 3.5701, CT 0.8793 m).
- AG-2 seed 13-15 copies re-hashed by CC-loop: 36/36 SHA-256 match LOOP_AG.md (0 mismatch, 0 missing); sent to CC-L3.
- Verified H' commit fb36d77 on origin/track3/stepL3-blind (child of a5f5bd1; BLIND_DEAD_ONLY default off).
- #68 full pytest (main 550ba68 + docs): 408 passed, 2 skipped, 1 xfailed, 1 h 41 min on a machine shared by 3 sessions;
  test_memory_gate_bounded_and_flat alone 4,707 s under that load (memory gate with backward pass 341 s).
- CC-4 reading-a gap: no bridging bug (error grows 1.5 cm across a burst, max 6 cm); gap RMSE = track error at burst
  times. No fix. K8: stuck detector kept (longest repeated gyro triplet in 312,179 clean rows = 2; detector needs 5).
  In TRACK3_PLAN "CC-4" on PR #68 (4dfa57d).
- CC-3 PARKED at tuning (PR #68, c8f8ba8): 15 variants on room1/2 x a,b x s1-3 (base APE 0.871, floor 1.110).
  Gyro bias from the quietest hand-held window hurts (0.910); gravity direction only 0.857 (-1.6 %), and that gain
  comes from the still-start covariance, not the direction. Below rule K's 2 %: rule K not written, TUM-VI seeds
  19-21 UNSPENT (AG: do not generate them). pathfinder.py unchanged.
- Static check: pathfinder.py and main.py parse as Python 3.10 grammar, no stdlib API newer than 3.10 (runtime on
  3.10/3.11 still unverified: no such Python here; AG-3).
- CC-0 SUBMISSION_RULES.md committed (track3/cc0-rules@d164d28, PR #68)
- CC-0 #67 (stepL2-gates) already open; it carries 0c8be4a's gate evidence (its NUMBERS refresh is superseded by #63)
- CC-0 dist/vortex_v0.95.zip from main 86711a9 (old layout: stub + .pyc for 3.13/3.14; pre-ledger fallback only):
  verify PASS on 3.14 and 3.13; sha256 85e3079bc57450dd582472654939fbd26ef2f752e0980aa8ff3e6dd2734a1c64
- PARKED: my two-file split of pathfinder.py (compile peak 6.7 -> 4.4 MB) breaks ledger A1 (sibling import); patch kept
  outside the repo. The parser finding (token array doubles past 16,384 tokens, +0.92 MB) went to CC-freeze.
READY FOR ARNAV TO MERGE (in this order): #77 (CC-L3, Step L3 BLIND ON) FIRST, then freeze-build
MERGED: #67 (550ba68), #68 (355de44)
GIVES TO AG: bundle layout = chunked at track3/freeze-build@<final hash, to follow>. rule H handshake above (AG-2 unblocked). CC-1a bundle still with CC-freeze (track3/freeze-build not pushed yet). CC-1a bundle will come from CC-freeze (track3/freeze-build) for AG-3.
NEEDS FROM AG: AG-3: whole-run FROM-SOURCE tracemalloc peak and us/row of the bundled src/main.py on Python
  3.10-3.14 and Docker; flag any above 7 MB. Earlier: AG-0 seed inventory: do EuRoC MH_03..05/V1_01..03 a/b seed 13-15 copies exist, and has anything run
  on TUM-VI seeds 13-15? (blocks CC-2's judge, not its rule); AG-1 Docker compute ms/IMU-s (decides CC-1b)
RULES COMMITTED: H at a5f5bd1 (track3/stepL3-blind, CC-L3; BLIND_* frozen), held-out copies may be generated: yes
  -> AG-2: make EuRoC MH_03..05, V1_01..03 x a,b x seeds 13,14,15 (36) and record SHA-256; CC-L3 told not to make them.
RULES COMMITTED: H' at fb36d77 (track3/stepL3-blind, CC-L3; switch BLIND_DEAD_ONLY, other BLIND_* as at a5f5bd1;
  labelled 'written after rule H failed; weaker evidence'), held-out copies may be generated: yes
  -> AG-2: make EuRoC MH_03..05, V1_01..03 x a,b x s22,23,24 (36) and TUM-VI room3, room4 x a,b x s22,23,24 (12)
     with tools/official_degrade.py; record SHA-256 of each imu0/data.csv in LOOP_AG.md; run nothing on them.
     Do NOT make TUM-VI s19-21 or any V2. Checked by CC-loop: 0 seed 22-24 copies existed at 01:20 IST.
  H' (no-fallback variant): ARNAV RELEASED SEEDS 22-24 (Arnav's words in chat, 20 Nov ~01:40 IST: "Release 22-24 for H'").
  CC-L3 writes rule H' first. Until a line "RULES COMMITTED: H' at <hash>, held-out copies may be generated: yes" appears
  here, AG must NOT generate any seed 22-24 copy. After it: EuRoC MH_03..05, V1_01..03 x a,b x s22-24 (36) and TUM-VI
  room3/4 x a,b x s22-24 (12), with SHA-256 in LOOP_AG.md.
  K: not written (CC-3 parked); TUM-VI seeds 19-21 stay unspent: do not generate.
NUMBERS: budget_heap_whole_run_kb = from-source whole run of the SHIPPED single file. CHUNKED on MH_01_easy_b_s1:
  3,186 KB Win 3.14, 3,876 Win 3.13, 3,555 WSL2 3.12 (CC-freeze); under -X tracemalloc=1 (counts start-up) Win 3.14 7,033.
NUMBERS, older (CC-loop's own run, AG-1 stand-in; main 550ba68 code = 86711a9 estimator; image python:3.12.7-slim-bookworm,
  inputs COPIED INTO the image, PYTHONDONTWRITEBYTECODE=1, stub main.py + pathfinder.py from source):
  whole process `python -S main.py`, median of 7: MH_01_b_s1 8.87, MH_03_a_s1 8.55, MH_03_b_s1 8.50, room3_a_s1 9.09,
  room3_b_s1 9.50 ms/IMU-s (44-49 us/row). benchmark.py in the container: 40.05 us/row (~7.8 ms/IMU-s compute),
  estimator heap 1,110 KB, whole run FROM SOURCE 7,370 KB (MH_01_b_s1). CC-freeze reports from-source 7,514 KB (3.14)
  and 7,963 KB (3.13) on MH_03_a_s1 for the plain single file: 0.23 MB under the 8 MB hard limit on 3.13.
PARKED: split of pathfinder.py (ledger A1) | CC-3 hand-held calibration (best tuning gain 1.6 % < 2 %)
ESCALATION (section 6 item 2, from CC-L3, relayed by CC-loop): rule H condition 7 FAILS, so BLIND_ON ships OFF.
  Clean TUM-VI APE 0.8793 -> 0.8892 m (+1.13 %, limit +0.5 %); all 4 rooms worse. Clean EuRoC -0.92 %.
  Block T passes (blind 1.114 -> 0.739 m, floor 0.738; APE -2.3 %). Contract PASS 24/24.
  Cause: on a file with no dead run, the 5 s fallback (BLIND_FALLBACK_S) pulls the last 5 s to the centroid.
  Tempting variant H': dead-run only, no fallback. Clean output then stays byte-identical to OFF; official copies,
  which all end in a zero run, would be unchanged IF detection fires on every one (not yet checked).
  ANSWERED by Arnav: option (2), seeds 22-24 released for H'. Rule H itself stays recorded as FAILED (OFF); CC-L3
  still completes the seed 13-15 H runs for the record.

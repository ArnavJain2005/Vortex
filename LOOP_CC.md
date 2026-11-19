# LOOP_CC   updated 2026-11-20 01:35 IST   iteration 10
Three Claude Code sessions share the CC queue (agreed between them, 19 Nov ~20:20; earlier iterations' clock times in this file were wrong, read them as ~20:2x-20:3x):
- CC-loop ("Vortex trajectory accuracy improvement", this file's owner): CC-0, CC-3, CC-4, CC-5.
- CC-freeze ("Vortex Samsung PRISM hackathon review"): CC-1a on track3/freeze-build (single-file src/main.py,
  B1 forms, B4 fallback, B5 timestamps). Works from Arnav's "Freeze build requirements" prompt, not this loop.
- CC-L3 ("Vortex trajectory estimation debugging"): CC-2 (L3 blind window, rule H) on track3/stepL3-blind.
  Works from Arnav's direct instruction; it has been sent the loop's rule H text.
NOW: CC-loop: waiting for CC-freeze's two bundle layouts, then the add-on's measurement matrix (Win 3.13/3.14, WSL2 3.12,
     Docker 3.12.7); CC-5 at Fri 20 21:00. CC-1b NOT needed (Docker compute below 12 ms/IMU-s, see NUMBERS)
     CC-freeze: CC-1a PLAIN (finishing), then the CHUNKED add-on once Arnav confirms it IN THAT SESSION   track3/freeze-build
     CC-L3: rule H (seed 13-15 H runs, verdict OFF on record) and rule H' (waits for AG's 48 s22-24 copies)   track3/stepL3-blind
DONE (newest first):
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
READY FOR ARNAV TO MERGE (in this order): none from CC-loop
MERGED: #67 (550ba68), #68 (355de44)
GIVES TO AG: rule H handshake above (AG-2 unblocked). CC-1a bundle still with CC-freeze (track3/freeze-build not pushed yet). CC-1a bundle will come from CC-freeze (track3/freeze-build) for AG-3.
NEEDS FROM AG: AG-0 seed inventory: do EuRoC MH_03..05/V1_01..03 a/b seed 13-15 copies exist, and has anything run
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
NUMBERS (CC-loop's own run, AG-1 stand-in; main 550ba68 code = 86711a9 estimator; image python:3.12.7-slim-bookworm,
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

# LOOP_CC   updated 2026-11-19 20:40 IST   iteration 5
Three Claude Code sessions share the CC queue (agreed between them, 19 Nov ~20:20; earlier iterations' clock times in this file were wrong, read them as ~20:2x-20:3x):
- CC-loop ("Vortex trajectory accuracy improvement", this file's owner): CC-0, CC-3, CC-4, CC-5.
- CC-freeze ("Vortex Samsung PRISM hackathon review"): CC-1a on track3/freeze-build (single-file src/main.py,
  B1 forms, B4 fallback, B5 timestamps). Works from Arnav's "Freeze build requirements" prompt, not this loop.
- CC-L3 ("Vortex trajectory estimation debugging"): CC-2 (L3 blind window, rule H) on track3/stepL3-blind.
  Works from Arnav's direct instruction; it has been sent the loop's rule H text.
NOW: CC-loop: waiting for CC-freeze's two bundle layouts, then the add-on's measurement matrix (Win 3.13/3.14, WSL2 3.12,
     Docker 3.12.7); CC-5 at Fri 20 21:00. CC-1b NOT needed (Docker compute below 12 ms/IMU-s, see NUMBERS)
     CC-freeze: CC-1a PLAIN (finishing), then the CHUNKED add-on once Arnav confirms it IN THAT SESSION   track3/freeze-build
     CC-L3: CC-2, building candidates on tuning   branch track3/stepL3-blind
DONE (newest first):
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
READY FOR ARNAV TO MERGE (in this order): #68 rules ledger + CC-3/CC-4 findings (docs + 1 exploratory tool). It conflicted
  with #67 (both appended to TRACK3_PLAN); main merged in at the branch tip, both sections kept, MERGEABLE now.
MERGED: #67 (550ba68)
GIVES TO AG: Docker timing above (AG-1 can confirm or replace it). CC-1a bundle will come from CC-freeze (track3/freeze-build) for AG-3.
NEEDS FROM AG: AG-0 seed inventory: do EuRoC MH_03..05/V1_01..03 a/b seed 13-15 copies exist, and has anything run
  on TUM-VI seeds 13-15? (blocks CC-2's judge, not its rule); AG-1 Docker compute ms/IMU-s (decides CC-1b)
RULES COMMITTED: none yet (H: by CC-L3, due Fri 20 13:00). K: not written (CC-3 parked); seeds 19-21 stay unspent
NUMBERS (CC-loop's own run, AG-1 stand-in; main 550ba68 code = 86711a9 estimator; image python:3.12.7-slim-bookworm,
  inputs COPIED INTO the image, PYTHONDONTWRITEBYTECODE=1, stub main.py + pathfinder.py from source):
  whole process `python -S main.py`, median of 7: MH_01_b_s1 8.87, MH_03_a_s1 8.55, MH_03_b_s1 8.50, room3_a_s1 9.09,
  room3_b_s1 9.50 ms/IMU-s (44-49 us/row). benchmark.py in the container: 40.05 us/row (~7.8 ms/IMU-s compute),
  estimator heap 1,110 KB, whole run FROM SOURCE 7,370 KB (MH_01_b_s1). CC-freeze reports from-source 7,514 KB (3.14)
  and 7,963 KB (3.13) on MH_03_a_s1 for the plain single file: 0.23 MB under the 8 MB hard limit on 3.13.
PARKED: split of pathfinder.py (ledger A1) | CC-3 hand-held calibration (best tuning gain 1.6 % < 2 %)
ESCALATION: none from CC-loop (heap is with CC-freeze/Arnav; the CHUNKED add-on is Arnav's answer: paste it into the
  'Vortex Samsung PRISM hackathon review' session, which owns CC-1a and will not act on a relayed copy). Note for Arnav: from-source heap on main is already 7,188 KB (3.14) / 7,551 KB (3.13)
  per NUMBERS (budget_heap_no_bytecode_kb), above the loop's 7 MB gate; CC-freeze is escalating it with CC-1a.
  Likely fix: keep the generated single file under 16,384 tokens (parser step, -0.9 MB).

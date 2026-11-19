# LOOP_CC   updated 2026-11-19 21:30 IST   iteration 2
Three Claude Code sessions share the CC queue (agreed between them, 19 Nov 20:25-20:40):
- CC-loop ("Vortex trajectory accuracy improvement", this file's owner): CC-0, CC-3, CC-4, CC-5.
- CC-freeze ("Vortex Samsung PRISM hackathon review"): CC-1a on track3/freeze-build (single-file src/main.py,
  B1 forms, B4 fallback, B5 timestamps). Works from Arnav's "Freeze build requirements" prompt, not this loop.
- CC-L3 ("Vortex trajectory estimation debugging"): CC-2 (L3 blind window, rule H) on track3/stepL3-blind.
  Works from Arnav's direct instruction; it has been sent the loop's rule H text.
NOW: CC-loop: CC-3 tuning grid on room1/2 (probe outside the repo; pathfinder.py untouched until CC-1a lands)
     CC-freeze: CC-1a   branch track3/freeze-build (not pushed yet)
     CC-L3: CC-2, building candidates on tuning   branch track3/stepL3-blind
DONE (newest first):
- CC-4 reading-a gap: no bridging bug (error grows 1.5 cm across a burst, max 6 cm); gap RMSE = track error at burst
  times. No fix. K8: stuck detector kept (longest repeated gyro triplet in 312,179 clean rows = 2; detector needs 5).
  In TRACK3_PLAN "CC-4" on PR #68 (4dfa57d).
- CC-3 tuning so far (room1/2 x a,b x s1-3, 12 copies, mean APE; base 0.871, floor 1.110): gyro bias from the
  quietest hand-held window HURTS (0.910); gravity direction only from it: 0.857 (-1.6 %, both rooms better).
  Below rule K's 2 % bar on tuning, so a pass on held-out is unlikely; finishing a small grid before deciding.
- CC-0 SUBMISSION_RULES.md committed (track3/cc0-rules@d164d28, PR #68)
- CC-0 #67 (stepL2-gates) already open; it carries 0c8be4a's gate evidence (its NUMBERS refresh is superseded by #63)
- CC-0 dist/vortex_v0.95.zip from main 86711a9 (old layout: stub + .pyc for 3.13/3.14; pre-ledger fallback only):
  verify PASS on 3.14 and 3.13; sha256 85e3079bc57450dd582472654939fbd26ef2f752e0980aa8ff3e6dd2734a1c64
- PARKED: my two-file split of pathfinder.py (compile peak 6.7 -> 4.4 MB) breaks ledger A1 (sibling import); patch kept
  outside the repo. The parser finding (token array doubles past 16,384 tokens, +0.92 MB) went to CC-freeze.
READY FOR ARNAV TO MERGE (in this order): #67 L2 gate records (docs only) | #68 submission rules ledger + CC-4 findings (docs only)
GIVES TO AG: nothing yet. CC-1a bundle will come from CC-freeze (track3/freeze-build) for AG-3.
NEEDS FROM AG: AG-0 seed inventory: do EuRoC MH_03..05/V1_01..03 a/b seed 13-15 copies exist, and has anything run
  on TUM-VI seeds 13-15? (blocks CC-2's judge, not its rule); AG-1 Docker compute ms/IMU-s (decides CC-1b)
RULES COMMITTED: none yet (H: by CC-L3, due Fri 20 13:00; K: CC-loop, after CC-3 tuning)
NUMBERS: none new
PARKED: split of pathfinder.py (ledger A1)
ESCALATION: none

# LOOP_CC   updated 2026-11-19 20:45 IST   iteration 1
Three Claude Code sessions share the CC queue (agreed between them, 19 Nov 20:25-20:40):
- CC-loop ("Vortex trajectory accuracy improvement", this file's owner): CC-0, CC-3, CC-4, CC-5.
- CC-freeze ("Vortex Samsung PRISM hackathon review"): CC-1a on track3/freeze-build (single-file src/main.py,
  B1 forms, B4 fallback, B5 timestamps). Works from Arnav's "Freeze build requirements" prompt, not this loop.
- CC-L3 ("Vortex trajectory estimation debugging"): CC-2 (L3 blind window, rule H) on track3/stepL3-blind.
  Works from Arnav's direct instruction; it has been sent the loop's rule H text.
NOW: CC-loop: CC-3 exploration on room1/2 (reference + analysis only; pathfinder.py untouched until CC-1a lands)
     CC-freeze: CC-1a   branch track3/freeze-build (not pushed yet)
     CC-L3: CC-2, building candidates on tuning   branch track3/stepL3-blind
DONE (newest first):
- CC-0 SUBMISSION_RULES.md committed (track3/cc0-rules@d164d28, PR #68)
- CC-0 #67 (stepL2-gates) already open; it carries 0c8be4a's gate evidence (its NUMBERS refresh is superseded by #63)
- CC-0 dist/vortex_v0.95.zip from main 86711a9: see below once verify finishes
- PARKED: my two-file split of pathfinder.py (compile peak 6.7 -> 4.4 MB) breaks ledger A1 (sibling import); patch kept
  outside the repo. The parser finding (token array doubles past 16,384 tokens, +0.92 MB) went to CC-freeze.
READY FOR ARNAV TO MERGE (in this order): #67 L2 gate records (docs only) | #68 submission rules ledger (docs only)
GIVES TO AG: nothing yet. CC-1a bundle will come from CC-freeze (track3/freeze-build) for AG-3.
NEEDS FROM AG: AG-0 seed inventory: do EuRoC MH_03..05/V1_01..03 a/b seed 13-15 copies exist, and has anything run
  on TUM-VI seeds 13-15? (blocks CC-2's judge, not its rule); AG-1 Docker compute ms/IMU-s (decides CC-1b)
RULES COMMITTED: none yet (H: by CC-L3, due Fri 20 13:00; K: CC-loop, after CC-3 tuning)
NUMBERS: none new
PARKED: split of pathfinder.py (ledger A1)
ESCALATION: none

# Measured ideas that did not ship

This is a decision record, not a list of defects. “Off” means the proposed
switch did not pass its stated rule, or was stopped on tuning data before a
held-out rule was registered. Values and populations are named below so a
gain on a subset cannot be mistaken for a shipped result. The lean shipped
`pathfinder.py` at `d1fc504` no longer contains these switched-off pieces;
their experimental code is in `tools/pathfinder_lab.py` and/or `vortex/core`
(`Docs/TRACK3_PLAN.md`, “Lean pathfinder”). No ground truth enters the
shipped estimator.

## Rotor drag V3: signal gate failed twice

**Hypothesis.** Horizontal in-flight specific force could reveal velocity.
**Rule and data.** The first rule, committed at `a1a8f65` before real data,
required a positive stable drag coefficient and held-out half-sequence
R² of at least 0.5 on both horizontal axes of MH_01. Its two first-half
coefficients were −0.0927 and −0.1141 /s, and test R² values −0.709 and
−0.656: NO-GO (`Docs/DRAG.md`, “Pre-registered rule”; outcome `219af74`).
An airborne-only rule was then registered at `c1b594c` **after** exploring
Machine Hall, but before Vicon Room 1. It required two axes to meet the
fixed-k fit and coefficient tolerance on at least two of V1_01–03; only
V1_02 passed (one of three, two needed). Stage B was not reached and V3 was
not built (`Docs/TRACK3_PLAN.md`, “Step B” and “Step 5”; outcomes `e87301a`,
`2b679b5`). This is an offline fit involving ground-truth velocity for the
signal test, never a ground-truth input to the estimator.

## Denoised V1 stillness: no held-out gain

**Hypothesis.** Removing white-noise variance from the still test could
recover zero-velocity updates under degradation. **Pre-registered rule:**
at least 2% lower mean APE on 18 held-out MH_03–05 copies, no worse clean
APE, and no updates during actual motion. Seeds 19–21 used a healthy
10-second opening and 22–24 a 2-second one, on the project's own seeded
fault model. Held-out APE changed from 6.482 to 6.496 m (+0.2%); the
clean and false-update gates passed. **Verdict:** `ZUPT_DEN_ON` off, never
ported into the shipped path (`Docs/TRACK3_PLAN.md`, “Step 7b”, rule
`1ac2f45`; outcome `7c47cd1`). This was not an official-script
test or a post-TUM-VI retest.

## Noise-meter gating: target missed on the project's fault model

**Hypothesis.** A noise meter could set process noise more appropriately.
**Rule:** with `GAP_ON` on, at least 5% gain in mean APE or blind growth,
no worse APE and no clean harm. The first pre-registered reading on
MH_03–05 seeds 1–3 left both switches off; a second rule was registered
before seeds 4–6, explicitly a second look. With GAP on, APE was 6.687 m
without JAM versus 6.479 m with JAM (−3.1%), and blind growth changed
6.771 to 6.788 m (+0.3%): the 5% target failed. GAP alone passed on its
re-judgment. **Verdict:** `JAM_ON` off (`Docs/TRACK3_PLAN.md`, “Step 6c”,
rule v1/v2 and outcome; `Docs/RESULTS.md`, `step6c-rep-*`; historical
rule commits `44a3309` and `f8dfe4f`, outcome `ceb2d1f`). These are **not** the organisers' official degradation
copies; the later baseline supersedes them for submission claims.

## Official fault front end: three registered failures

**Hypotheses.** `STUCK6` would reject repeated six-axis rows; `SPIKE`
would reject joint outliers; `INTERP` would bridge short missing periods.
**Rule:** each needed at least 1% lower held-out mean APE, reading-wise
no-harm, gap/blind no-harm, clean no-harm and a passing output contract,
judged in that order. MH_03–05 and V1_01–03, both readings, seeds 1–3,
formed 36 official-script copies; all earlier switches failed and stayed
off. `STUCK6`: 5.086 → 5.075 m (−0.20%), but reading b worsened 2.60%.
`SPIKE`: 5.086 → 5.088 m (+0.05%). `INTERP`: 5.086 → 5.412 m
(+6.42%), with reading a +11.34% and blind RMSE +15.26%.
**Verdict:** all three off (`Docs/TRACK3_PLAN.md`, “Step 3”, rule
`99bf25b`, outcome `8cb550f`). These are experimental extra checks;
the shipped `DEAD_ON` zero/stuck detector and gap coasting still operate.

## Per-flight envelope learning: collapsed towards the floor

**Hypothesis.** Learning speed and position-prior widths from the same
flight could outperform fixed widths. **Rule:** on the same 36
official-script copies as Step 3, held-out mean APE had to be no worse
than the never-moving floor, clean mean APE no more than 0.5% worse, and
the output contract had to pass. The learned 3.739 m versus floor
3.748 m passed the first gate; clean APE rose 3.663 → 3.908 m (+6.68%)
and failed the second. **Verdict:** `LEARN_ON` off. This apparent degraded
gain removed clean movement and is no evidence of recovered motion
(`Docs/TRACK3_PLAN.md`, “Step 4”, rule `c1769cb`, outcome `59f65e0`).

## Covariance reset: held-out APE increased

**Hypothesis.** Applying an error-state covariance reset after attitude
injection could correct a mathematical omission. **Rule:** each filter fix
was judged sequentially on MH_03–05/V1_01–03, a/b, official-script seeds
4–6 (36 copies), with tight aggregate, per-reading, gap/blind and clean
no-harm gates. With the earlier passing fixes on, `RESET_ON` raised mean
APE 4.962 → 5.020 m (+1.15%) and reading-a APE 6.181 → 6.293 m
(+1.81%). **Verdict:** reset off; `BGCAP_ON`, `P0V_ON` and `REFRESH_ON`
passed and remain on (`Docs/TRACK3_PLAN.md`, “Step F”, rule `cba34e3`,
outcome `8ee0544`). Correct local Jacobian algebra did not establish a
held-out score gain.

## Per-row confidence: tuning correlation had the wrong sign

**Hypothesis.** Propagated position covariance might rank which poses
were least reliable. **Rule status:** this was reporting-only, not a
shipped estimator switch; no held-out rule or held-out run was spent.
On MH_01/02 clean plus six degraded copies each (seeds 100–105),
344,494 rows with a sigma produced Spearman correlation −0.07 between
sigma and aligned position error. **Verdict:** no calibrated per-row
confidence claim (`Docs/COVERAGE.md`, “step8b-tune”;
`Docs/TRACK3_PLAN.md`, “Step 8b”, commit `5825664`).

## Centroid shrinkage: the reverse-time control caught an artefact

**Hypothesis.** Scaling estimated positions about their centroid might
improve APE and blind/gap errors without losing information. **Rule:**
pre-registered before MH_03–05/V1_01–03, a/b, official-script seeds
7–9 (36 copies), with a per-copy floor-normalised objective, improvement
on at least five of six sequences, and a comparison with the candidate's
own *time-reversed* output, plus cross-reading, clean and contract gates.
The low-alpha arm lowered reading-a objective 143.17 → 72.35, but only
four of six sequences improved and the reversed control scored **69.75**
(lower is better). The other arm lowered reading-b objective 77.08 →
58.66, but only three of six sequences improved. **Verdict:** both arms
off (`Docs/TRACK3_PLAN.md`, “Step L1”, rule `d56c875`, outcome `dc162ac`).

Why reverse time? It preserves the estimate's positions and general
smoothness but destroys which pose belongs to which moment of the flight.
Because the evaluator rotates and translates each whole trajectory to
best fit ground truth, even a wrong temporal story can score below a
stationary trajectory once its amplitude is reduced. The reversed score
was better than the low-alpha candidate's score, so that arm could not
demonstrate information tied to the actual motion. A lower number than
the stationary floor alone is insufficient evidence.

## Interpretation boundary

The held-out *flights* are only six EuRoC sequences, and several later
experiments reuse them with fresh degradation seeds. This limits claims
of independent validation. The shipped Step 6 mean APE is 4.648 m
against the never-moving 3.745 m on 36 official copies (seeds 4–6), and
blind RMSE 7.559 against 2.504 m (`Docs/TRACK3_PLAN.md`, “Step 6”,
“Shipped build on the seeds spent by earlier steps”; `Docs/NUMBERS.md`,
“Sets”, `heldout_*`). TUM-VI official copies are a baseline **before**
Step 6, not evidence that any rejected switch would pass there
(`Docs/NUMBERS.md`, “Sets”; `Docs/TUMVI_BASELINE.md`, “Means by reading and set”).

**Historical status change.** The Step E smoother worsened MH_01/02 tuning
results and was left off without a held-out rule (`Docs/TRACK3_PLAN.md`,
“Step E” and “Step E, second look”; commits `52ae66a`, `5070b11`). A later,
pre-registered Step 6 test on six held-out EuRoC flights passed its aggregate
APE, gap and clean gates, so `SMOOTH_ON` **now ships on** (`Docs/TRACK3_PLAN.md`,
“Step 6”, rule and outcome at `8da205d`). Its earlier failure on the tuning
flights remains part of the record; it is not a current negative switch.

### Source-record discrepancies to settle

- `Docs/COVERAGE.md` labels `step8b-tune` with commit `7c47cd1`, which
  is actually the Step 7b denoised-V1 outcome. Git history shows the
  confidence study entered at `5825664`; the owner should correct the
  generated coverage source/renderer rather than editing the generated file.
- `Docs/RESULTS.md`, “means”, labels Step F seeds `1..3`, while its per-copy
  Step F rows use `_s4` through `_s6`; its new `step6-H46` means have the
  same label even though their per-copy rows also use `_s4` through `_s6`.
  The rules and outcome in `Docs/TRACK3_PLAN.md`, “Step F” and “Step 6”,
  specify seeds 4–6. The generated summaries need correction by their owner.
- `Docs/TUMVI_BASELINE.md` still calls its pre-Step-6 estimator “shipped” in
  the title. `Docs/NUMBERS.md`, “Sets”, correctly labels those TUM-VI runs as
  before the smoother. Until TUM-VI is rerun on the current build, use that
  build qualifier whenever quoting the baseline.

# Vortex: Track 3 PRD v2, plan of action and work split

**18 Nov 2026 (IST) · Arnav Jain (solo entrant) · supersedes "Vortex: Track 3 PRD, Plan of Action and Checklist" (15 Nov, `Vortex_Track3_PRD.pdf`)**

Repository: github.com/ArnavJain2005/Vortex, `main` at 33b841e (merge of PR #50, Step L1, 18 Nov 03:12 IST). This file lives at
`Docs/PRD.md`; `Docs/TRACK3_PLAN.md` stays the step-by-step running record, `CLAUDE.md` the working rules.
**Revised 18 Nov after ChatGPT's red-team review (C1):** L1 maths and centre variants made explicit, L2 redesigned as a slow
gravity alignment, L3 detailed, judging rule made paired and sequence-level, cut order added (section 3.1). Where this
file and the 15 Nov PDF disagree, this file wins. Where the organisers' FAQ (17 Nov) disagrees with
anything, the FAQ wins.

---

## 0. What changed since v1 (15 Nov)

| v1 said | Now |
|---|---|
| Team of three (Arnav, Arya, Nandhitha) | Solo entrant. The work is split across three AI tools instead: **Claude Code** (estimator and repo owner), **Gemini in Antigravity** (data, evaluation runs, replay page, footage, clean-machine checks), **ChatGPT** (review, deck, video script, organiser email, jury prep). Arnav decides, merges and submits |
| ~25 % done; estimator did not exist | Estimator, scorer, benchmark and bundle exist; work through PR #48 is merged. Efficiency is far inside budget. **Accuracy is the open problem**: on the organisers' degradation the estimator is worse than a trajectory that never moves |
| Python or C++; 8 MB maybe whole-process RSS | FAQ: **Python only**, 8 MB measured **at heap level**. The C core (`main.cpp`) is a recorded experiment, never shipped |
| Two-pass smoother is the biggest lever | Built (Step E) and **failed** on the tuning set: it smooths jitter but cannot add motion information the filter does not have. Off |
| V3 rotor drag is the strongest witness | Pre-registered rule v2: **NO-GO** on Vicon Room 1 (17 Nov). Dropped |
| Our own fault model | Organisers' `degrade_imu.py` received. All earlier degraded numbers are history, not evidence |
| Open questions Q1–Q8 | Q1, Q3, Q4, Q5, Q7, Q8 closed by the FAQ; Q2 mostly; **Q9 (column order fed to the script) open** |
| Replay page, deck, video, metadata.json | Not started (metadata.json is written by `tools/make_bundle.py eval`) |

## 1. The task (settled by the slides and the 17 Nov FAQ)

- **Input:** one degraded EuRoC-format `imu0/data.csv` (EuRoC MAV or TUM-VI, degraded by the organisers'
  `degrade_imu.py`). Gravity alignment unknown. Waypoints hidden, never an input.
- **Output:** `estimated_trajectory.txt`, `timestamp tx ty tz qx qy qz qw`, seconds, **exactly one pose per input
  row**, never append. Dropouts are physically missing rows. The last 5 s keep timestamps but the values are
  invalid (exact zeros): dead-reckon through them.
- **Limits:** Python only (`main.py`), single thread, offline (whole file in memory and non-causal smoothing are
  allowed), **8 MB peak at heap level**, **20 ms compute per second of IMU** (100 µs per row at 200 Hz).
- **Scoring (100):** efficiency 40 (memory 20, runtime 20); trajectory 60 (waypoints 30, blind 5 s 20,
  dropouts 10). evo ATE after **SE(3) Umeyama alignment** against hidden ground truth.
- **What `degrade_imu.py` does:** treats columns 2–4 as accelerometer and 5–7 as gyro; white noise, bias random
  walk and scale-factor walk on all six axes; spikes (up to 9 m/s² and 1.5 rad/s); stuck runs of 2–10 rows;
  single missing rows (up to 6 %) and bursts of 5–50; duplicated rows; exact zeros for the last 5 s; 6-decimal
  rounding. Severity ramps from 0.02 to 1.0 (gamma 1.7): **the end of every file is the worst part**. Seed fixed
  at 42 inside the script.
- **Deliverables:** `team_name.zip` (`estimated_trajectory.txt`, `src/main.py` + README, optional
  `metadata.json`), GitHub repo with README and Dockerfile, demo video **2–3 min (strict max 3)**, deck in the
  official template named `CollegeName_TeamName`. Deadline **Sun 22 Nov 2026, 11:59 PM IST**, Google Form
  (link in the announcements channel). Jury round for the top 12–15: 9 Dec.

## 2. Status at a glance (verified, 17–18 Nov)

**Built and working:** EuRoC/TUM-VI loader (keeps every row), input front end (detects column order and units
from the data), stillness self-calibration with fallbacks, pre-anchor hold, 15-state error-state Kalman filter with
V1 stillness and V2 flight envelope, dropout covariance, dead-sensor detection and a 0.5 s velocity-decay blind
forecaster, the Step F filter fixes, `score.py` (cross-checked against evo to 4.2e-7 m on synthetic data),
`benchmark.py` gates, official-script harness (both column readings), the bundle builder and Docker image.
`pytest`: 284 passed (Windows, Python 3.14, 17 Nov); 266 passed with the C-core tests excluded (Linux sandbox,
Python 3.13, 18 Nov).

### Scoreboard

Held-out set H = MH_03..05 + V1_01..03, organisers' script, readings a and b, seeds 4–6 (36 copies); APE with SE(3)
fitted on the run being scored; "floor" = one pose at the origin for every row, scored the same way
(`Docs/TRACK3_PLAN.md`, Step F, tag `stepF-H-p0v-refresh`).

| Measure | Vortex (shipped) | Never-moving floor | Reading |
|---|---:|---:|---|
| Held-out mean APE, both readings | 4.962 m | 3.745 m | **33 % worse than standing still** |
| Reading b (accelerometer columns first) | 3.744 m | 3.745 m | level |
| Reading a (raw EuRoC fed in: gyro gets accelerometer-sized faults) | 6.181 m | 3.745 m | attitude lost |
| Gap RMSE (missing-row bursts) | 5.036 m | 3.626 m | worse |
| Blind 5 s RMSE | 6.992 m | 2.504 m | **2.8x worse**; error at the failure moment dominates, not the 5 s growth |
| Clean held-out (6 seq., Step 2) | 3.59 m | 3.75 m | slightly better |
| Heap peak, MH_01_easy_b_s1 (shipped bytecode) | 1.10 MB | — | limit 8 MB, target 4 MB |
| Heap peak if the evaluator compiles from source | 5.51 MB | — | under 8 MB, over the 4 MB target |
| Compute, MH_01_easy_b_s1 | 11.4 µs/row ≈ 2.3 ms per IMU-second | — | limit 100 µs/row |

**Plain reading.** The 40 efficiency points look safe. The 60 trajectory points are where we lose: a team that
outputs zeros beats us on the official degradation today. Not checked at all: TUM-VI (not downloaded), Vicon
Room 2 (final test set, untouched), which column order the organisers use (Q9).

### Measured experiments that ship off (deck material, not claims)

V3 rotor drag (NO-GO, rule v2), denoised V1 (7b), per-row confidence W6 (rank correlation −0.07 with error),
RTS smoother (Step E, worse APE on the tuning set), noise meter `JAM_ON` (failed rule v2 on our old fault model;
**never judged on the official script**), stuck/spike/interpolation front end (Step 3), covariance reset (Step F).

**Added 18 Nov (PRs #49, #50):** the per-flight learned envelope (Step 4, `LEARN_ON`) ships off (held-out ties the floor, clean +6.7 %); the drag rule v2 re-run reproduces NO-GO and V3 is not built (Step 5); shrinkage about the centroid (Step L1, `SHRINK_ON`) was built, tuned on MH_01/02 and judged on seeds 7–9: both arms **failed** the pre-registered rule (4 of 6 and 3 of 6 sequences improved, 5 needed; arm LO also failed to beat its own time-reversed output, 72.35 vs 69.75). Reading a improved on the objective (143.17 to 72.35) but not credibly beyond what the alignment can fit. Shipped output is byte-identical to Step F. `pytest`: 310 passed (Windows, Python 3.14.7). **Seeds 7–9 are spent.**

## 3. Strategy for the last four days

**Principle: never worse than standing still; better wherever the IMU still carries information.** A navigator that
knows when it does not know and falls back to its safest guess is a defensible, honest product for a jammed
aircraft, and it is exactly what the scoreboard rewards. It fits the velocity-witness idea: the jamming meter sets
trust, and when trust is gone the estimate should collapse toward the vehicle's own running centre (V2P), not
keep integrating noise.

Levers, in priority order (each a switch, default off, built in `vortex/core` first, copied bit-identically into
`pathfinder.py`, judged by a rule committed before any held-out run):

| # | Lever | Why it should help | Points it targets | Owner |
|---|---|---|---|---|
| **L1 (DONE 18 Nov, FAILED, ships off)** | **Trust-scaled shrinkage** `SHRINK_ON`: output position = c + α·(p − c), c the running (or whole-run) centre, α ≤ 1 from a fixed constant (L1a) or from the measured IMU noise level (L1b) | Under SE(3)-aligned ATE a constant scores the GT spread; our estimate carries weak signal plus a lot of noise, so a shrink factor below 1 should beat both. It also caps the blind and end-of-file error where severity is highest | Waypoints 30, blind 20, dropouts 10 | Claude Code |
| **L2** | **Slow gravity alignment + gyro noise meter** `TILT_ON`: over a 10–20 s window the vehicle's mean world-frame acceleration is near zero (velocity is bounded), so the mean world-frame specific force must point along gravity; the residual corrects roll/pitch, weighted by the measured gyro jamming. Not an instantaneous accelerometer tilt | Under reading a the gyro is jammed and attitude is lost; the windowed residual is biased only by Δv/(g·T), about 1° for a 2 m/s change over 12 s | Waypoints, dropouts (reading a) | Claude Code |
| | *Why not instantaneous tilt* | On a multirotor the accelerometer mostly measures thrust along body z plus drag, not gravity (Leishman et al.), so an instantaneous tilt reading erases the true 5–20° tilt (a g·sin θ projection error of 0.85–3.4 m/s², calculated, not measured on EuRoC). **L2 is the first lever cut** if its gain is unclear | | |
| **L3** | **Blind window from a trusted state**: compare a few fixed lookback windows before the zero run (chosen on tuning), fit position and velocity robustly to the trusted states, pull velocity toward zero as trust falls, hold the last reliable attitude | Blind RMSE is set by the error at failure, not by the forecast; no window can remove an absolute offset that is unobservable | Blind 20 | Claude Code |
| **L4** | **Submission hardening**: move switched-off experiments out of `pathfinder.py` (they stay in the reference) to cut the from-source compile heap; `metadata.json`; frozen zips | Protects the 40 efficiency points if the evaluator does not use our bytecode | Memory 20 | Claude Code |
| **L5** | **TUM-VI coverage**: download, loader wiring, official copies, baselines, then no-harm fixes | The hidden test may be TUM-VI (hand-held, walking); we have never run it | All 60 | Antigravity (data, runs), Claude Code (fixes) |

**Judging protocol (revised 18 Nov).** Seeds 1–3 decided Step 3 and seeds 4–6 decided Step F, so they are spent.
The 36 copies per seed set are only **6 trajectories**, so every rule is paired and sequence-level:
- **Rule G (L2)**, committed with every candidate setting frozen before one held-out run on **seeds 10–12** (seeds 7–9 were spent by L1)
  (MH_03..05, V1_01..03 × readings a, b), plus TUM-VI room3/room4 as a separate block once they exist.
- **Rule H (L3)**, committed before one held-out run on **seeds 13–15**. Seeds 16–18 are the reserve. Fresh seeds are not fresh trajectories: every MH/V1 seed reuses the same 6 flights, so adaptive overfitting at flight level is real. The only untouched data are TUM-VI room3/room4 and Vicon Room 2 (final table).
- Ship conditions: held-out mean APE improves ≥ 2 % **and** the paired gain is positive on at least 4 of the 6 held-out
  sequences (readings pooled per sequence); neither reading worse by > 1 %; gap and blind RMSE not worse by > 2 %; clean
  mean APE not worse by > 0.5 %; contract PASS on every run; budget gates PASS. Rule H judges blind RMSE instead of APE
  for its 2 % and 4-of-6 conditions, and APE becomes a no-harm condition.
- Every verdict table shows per-sequence paired effects, the sequence-level spread and the floor beside the mean.
- A gain is called "better aligned APE", not motion recovery, unless RPE 1 s and path shape improve as well.

Tuning: MH_01/02 and TUM-VI room1/room2, seeds 1–3. **Vicon Room 2 (V2_01..03) stays the final test set**, run once,
only when Arnav says "run the final table".

### 3.1 Lever details after the 18 Nov review

- **L1 maths.** With a constant centre c, SE(3) alignment picks the rotation maximising K = tr(R·Cov(P, T)); scaling the
  centred estimate by α > 0 scales every rotation's score equally, so the rotation does not change and
  APE²(α) = σT² + α²σP² − 2αK, optimum α* = K/σP². Alignment can make K positive even for unrelated clouds, so a gain
  is not evidence of recovered motion. With a moving centre (V2P running centre) the formula no longer holds. Both
  variants are tested separately; APE is always reported beside RPE 1 s, path length and the floor.
- **α cannot be identified without ground truth.** The filter covariance did not rank error (−0.07), measured noise
  cannot separate true travel from integrated bias, and estimators sharing the same IMU and V2 prior are not
  independent. So constant α (L1a), noise-scaled α (L1b) and covariance-scaled α are candidate policies with constants
  fixed on tuning, never per-run estimates.
- **L2** is a slow world-frame gravity alignment (above), gated off when the window's mean acceleration is not small,
  with attitude error reported by flight phase on tuning data.
- **L3** is scored three ways: error at the failure moment, blind growth, blind RMSE.
- **Cut order** if time runs short: L2 first, then L3; L1 ships only with its floor comparison visible. TUM-VI coverage,
  the row-contract checks and the frozen zips are never cut.

## 4. Requirements (status as of 18 Nov)

| ID | Requirement | Status |
|---|---|---|
| F1 | Read `imu0/data.csv`, keep every row | Done (verified, EuRoC; TUM-VI not run) |
| F2 | One pose per row, contract checker | Done (verified on every run so far) |
| F3 | Gravity and gyro bias without ground truth | Done (verified, EuRoC); bias cap `BG_MAX` 0.15 rad/s not checked on TUM-VI |
| F4 | Detect dropouts, spikes, stuck values, failure | Missing rows, zero tail: done. Spike/stuck rejection: built, off (Step 3) |
| F5 | Pose for every row through dropouts | Done |
| F6 | Predict the blind 5 s | Done (velocity decay); worse than the floor → L3 |
| F7 | Trust follows the measured noise | Built (`JAM_ON`), off, never judged on the official script → L1b, L2 |
| F8 | One command, offline, single thread, Docker | Done (verified, Python bundle) |
| W1 | Velocity witnesses with ablation | V1, V2 on; V3 dropped; V4, V5 not started (V5 only if TUM-VI shows a need and time allows) |
| W2 | Healthy-phase self-calibration | Done for biases and gravity; envelope still fixed (chosen on MH_01/02) |
| W3 | Jamming meter | See F7 |
| W5 | Blind forecaster better than constant velocity | Done on our old fault model (−49.5 % blind growth); still worse than the floor on the official script |
| W6 | Per-row confidence | Not informative (−0.07); not claimed |
| NEW N1 | Never worse than the floor on held-out official copies | Not met (4.962 vs 3.745 m) → L1–L3 |
| NEW N2 | Runs and scores on TUM-VI | Not started → L5 |
| NEW N3 | Replay page from our outputs | Not started → Antigravity |
| NEW N4 | Every number in deck, video and README comes from a generated file | Not started → `Docs/NUMBERS.md` (Claude Code) |

## 5. Work split and rules of engagement

### Owners

| Area | Owner | Works in |
|---|---|---|
| Estimator (`pathfinder.py`, `main.py`, `vortex/core/*`), judging tools, `Docs/TRACK3_PLAN.md`, `Docs/RESULTS.md`, `Docs/BUDGET.md`, `README.md`, `CLAUDE.md`, `Docs/PRD.md`, `Docs/NUMBERS.md`, bundle and zips | **Claude Code** | Main clone, branches `track3/step*` |
| TUM-VI and V2 downloads, `--root` option on `tools/eval_euroc.py` and `tools/official_degrade.py`, `Docs/TUMVI_BASELINE.md`, `tools/replay.py` + replay HTML, demo footage, clean-machine verification of the zip, video assembly | **Gemini (Antigravity)** | Separate git worktree `../Vortex-ag`, branches `ag/*` |
| Independent tester and writer. **Repo:** `tests/independent/*` (black-box contract and adversarial tests), `tools/ape_check.py` (second, independently written scorer), `Docs/METHOD.md`, `Docs/NEGATIVE_RESULTS.md`, README.md draft (Claude Code verifies and commits it). **Chat:** pre-registration audits, PR claim audits, red-team review, Q9 email, deck, video script and shot list, jury Q&A | **ChatGPT** | Outputs complete files; Arnav commits them in worktree `../Vortex-gpt` on `gpt/*` branches; Claude Code reviews; never pushes itself |
| Decisions, merges, sending email, voice-over, Google Form | **Arnav** | — |

**README ownership (18 Nov):** ChatGPT writes the full README.md text from the repo's own docs and a change log naming a source for every changed claim; Arnav drops it into a `docs/readme-final` branch; Claude Code checks every number against `Docs/NUMBERS.md` or the Docs ledgers and commits it. Claude Code does not rewrite the README itself.

**ChatGPT in the repo (18 Nov evening):** every existing test was written by the agent that wrote the estimator. ChatGPT writes a second, black-box suite from the organisers' spec alone and a second scorer from evo's definition, so shared assumptions get caught. Failing tests are committed as `xfail(strict=True)` findings, never weakened; Claude Code decides bug vs test. From Fri 20, `tests/independent` gates every merge and v1.0; `tools/ape_check.py` must agree with `tools/eval_euroc.py` within 1 mm before any further judging.

### Rules all three follow

1. **One owner per file.** Antigravity never edits `pathfinder.py`, `main.py`, `vortex/core/*`, `Docs/TRACK3_PLAN.md`,
   `Docs/RESULTS.md`, `Docs/BUDGET.md` or `README.md`. Claude Code never edits `tools/replay.py` or
   `Docs/TUMVI_BASELINE.md`. The one shared file pair (`tools/eval_euroc.py`, `tools/official_degrade.py`) gets
   Antigravity's additive `--root` change merged **before Thu 19, 11 PM**; Claude Code rebases after.
2. **Numbers come from files, not memory.** Claude Code generates `Docs/NUMBERS.md` from the results JSON. The
   deck, the video and the README quote only that file. ChatGPT writes `[[N:key]]` placeholders until Arnav pastes
   the file.
3. **Never touch V2_01..03** (download only; no reading, plotting or running) until Arnav says "run the final table".
4. **Every PR gets a detailed description** (why; what changed per file; tests with exact counts and where; what was
   not checked; Windows steps for Arnav with expected output; which plan rows it updates). Never push to `main`.
5. **Freeze a valid zip before every risky change.** v0.9 = today's `main`; v1.0 = Fri 20, 9 PM.
6. Ask Arnav before deleting files, adding dependencies, copying third-party code, or committing `degrade_imu.py`.

## 6. Plan of action

| When (IST) | Claude Code | Antigravity | ChatGPT | Arnav |
|---|---|---|---|---|
| **Wed 18, evening** | K0: commit this PRD, freeze **v0.9 zip** of `main`. K1: L1 shrinkage in the reference, tuning curves on MH_01/02 seeds 1–3 | G1: download TUM-VI room1..6 (512_16, EuRoC export) and V2_01..03; extract IMU + ground truth only | C1: red-team this PRD and L1/L2 maths. C2: draft the Q9 email | Send the Q9 email; start Antigravity on G1 |
| **Thu 19, evening** | K2: L2 slow gravity alignment + gyro noise meter, tuning. L3 built and tuned. Write rule G (L2) and rule H (L3) | G1 cont.: `--root` option, TUM-VI official copies (room1..4 × a, b × seeds 1–3, 10–12, 13–15), baselines, `Docs/TUMVI_BASELINE.md`; PR merged by 11 PM | C3: deck v1. **C10** contract tests, **C11** `ape_check.py`, start **C12** adversarial tests (Arnav commits on `gpt/*`) | Merge the G1 PR (the C1 review is already folded into this PRD and the prompts) |
| **Fri 20** | AM: judge rule G (L2) on seeds 10–12 + TUM-VI room3/4. PM: judge rule H (L3) on seeds 13–15; TUM-VI no-harm fixes if the baseline shows failures. **9 PM: freeze v1.0** | G2: `tools/replay.py` (self-contained HTML), verified in the browser on MH_03 and room3 | C4: video script and shot list. C12 finished; C10–C12 merged by 6 PM (before v1.0). **C13** METHOD and NEGATIVE_RESULTS drafts | Review the verdicts; merge |
| **Sat 21** | K5: L4 hardening (strip off-switches, compile heap), `Docs/NUMBERS.md`, README and RESULTS refresh. On Arnav's word: **final table on V2_01..03** | G3: footage (terminal run, checker, benchmark gate, replay page); G4: clean-machine check of the v1.0 zip (fresh venv + Docker) | C5: deck v2 with real numbers from `NUMBERS.md`; narration; C13 final; C7b README sync | Record voice-over; **6 PM: submission-ready checkpoint** |
| **Sun 22** | Final zip, `verify`, tag `v1.0-submitted`; fix only what G4 reports | G5: assemble the video with ffmpeg (≤ 3:00), captions | C6: jury Q&A sheet; final proofread of deck and README | **Submit the Google Form by 6 PM** (6 h buffer); upload deck and video |

Anything not done by Sat 6 PM is cut, except the submission itself. Cut order: L2, then L3 (section 3.1).

## 7. Risks and open questions

| Risk | Impact | Mitigation |
|---|---|---|
| Hidden data is TUM-VI and we have never run it | Crash, bad calibration or envelope mismatch on the scored file | L5 on Thu–Fri; the contract checker runs on every TUM-VI copy first |
| L1 shrinkage reads as "giving up" to the jury | Weaker story | Present it as calibrated trust: the jamming meter decides how far to believe the IMU; show both the gain and the motion it keeps |
| Column order unknown (Q9) | Our tuning may target the wrong reading | Both readings judged separately; the ship rule protects each; email the organisers |
| Evaluator compiles from source and counts compile memory | Heap 5.5 MB instead of 1.1 MB | L4 strips switched-off code; stays under 8 MB either way |
| Overfitting the shrink factor to MH | Worse on hidden data | Fixed constants chosen on tuning only; fresh seeds; TUM-VI held-out rooms |
| 36 copies read as 36 independent tests | A 2 % gain that is seed noise on 6 trajectories | Paired, sequence-level rule (4 of 6 sequences); per-sequence tables |
| L2 tilt aiding biased on a multirotor | Hurts reading b and clean flights | Windowed world-frame gravity alignment, not instantaneous tilt; weight follows gyro jamming; per-reading no-harm; cut first |
| Two agents editing one repo | Merge conflicts, broken `main` | Separate worktree, file ownership above, Arnav merges |
| Numbers drift between deck, video and README | Credibility | `Docs/NUMBERS.md` is the single source |
| Evaluation input arrives late or in another form | Zip incomplete | `tools/make_bundle.py eval` already takes any IMU file; keep v0.9/v1.0 zips ready |

**Open:** Q9 column order. Whether the organisers run our code on hidden data or score the
`estimated_trajectory.txt` we submit for their file (the bundle supports both). The `degrade_imu.py` licence and
whether to commit it (Arnav).

## 8. Pitch (honest version)

Vortex is a self-calibrating inertial navigator that knows how much to believe its IMU. It learns the sensor's
health and the vehicle's limits in the clean opening seconds, listens to drift-free hints in the IMU's own physics
(stillness, the flight envelope), measures jamming as it rises, and pulls its estimate toward the safest guess as
trust falls, so it degrades gracefully instead of drifting away. It runs in about 1 MB of heap and about 2 ms per
second of IMU, uses no camera, GPS, ground truth or pretrained model, and every claim in the deck is a measured,
pre-registered result, including the ideas that failed.

## 9. Submission checklist

- [ ] v0.9 zip frozen (Wed) · [ ] v1.0 zip frozen (Fri 9 PM) · [ ] final zip verified (Sun)
- [ ] `estimated_trajectory.txt` for the evaluation input, contract PASS
- [ ] `src/main.py` + README + `metadata.json` in the zip; GitHub README and Dockerfile current
- [ ] TUM-VI baseline recorded; final table on V2_01..03 recorded
- [ ] `Docs/NUMBERS.md` generated; deck and video quote only it
- [ ] Deck `CollegeName_TeamName` in the official template
- [ ] Video ≤ 3:00
- [ ] Google Form submitted, confirmation saved

## 10. Addendum: status after the evening of 18 Nov (Claude Code)

Added after this file was placed; sections 0-9 above are unchanged. Where this addendum and section 3 disagree
about what is done, this addendum is the newer record (details in `Docs/TRACK3_PLAN.md`).

- **L1 was built and judged on 18 Nov, before this file reached the repo** (PR #50, branch `track3/stepL1-shrink`):
  constant centre (whole-run mean), alpha per gyro-noise class (0.10 / 0.20, tuned on MH_01/02 a, b, seeds 1-3),
  plus a second floor: the estimate reversed in time. Judged on **seeds 7-9** by a rule committed before those copies
  existed: **both arms fail** (sequence consistency 4/6 and 3/6 against 5/6 needed; the high-noise arm also loses to
  its reversed output), so `SHRINK_ON` ships off. L1a (one fixed alpha), the moving-centre variant and the
  APE^2(alpha) identity test against `score.py` were not built.
- **Seeds 7-9 are therefore spent.** Section 3 (updated 18 Nov) adopts the new split: rule G on seeds 10-12,
  rule H on 13-15, reserve 16-18.
- **L4's first part** (PR #51): switched-off experiments moved from `pathfinder.py` to
  `tools/pathfinder_lab.py` (not shipped; the reference in `vortex/core` keeps them too); output byte-identical on
  all 144 real inputs; no-bytecode heap 6,055 -> 4,935 KB (3.14), 6,431 -> 6,309 KB (3.13). The 4 MB target is not
  met; the 3.13 peak does not track the source size (not investigated). **#51 was stacked on #50 and merged into
  `track3/stepL1-shrink` after #50 had already landed, so it never reached `main`**; it is re-landed by a
  separate PR from `main` (gates re-run there).
- **Shared file:** PR #50 added `--reverse` to `tools/eval_euroc.py`; Antigravity's `--root` change (#54) landed
  after it on `main`.
- **v0.9 fallback zip** frozen from `main` da14417 (K0): `dist/vortex_v0.9.zip`, SHA-256
  0e558440a397ef4b78426cc471ac8d3fd17f8c658b28a6cd40aeb5a3ba555d6b.

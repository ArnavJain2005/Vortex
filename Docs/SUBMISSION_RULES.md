# Submission rules ledger (decided 19 Nov 2026; organisers assumed silent)

Committed verbatim from Appendix A of Arnav's autonomous-loop prompt of 19 Nov 2026, 20:30 IST. It overrides
anything older that disagrees with it (for example `Docs/PRD.md` on bytecode, and A6's heap figure, which
assumed bytecode: from source the whole run peaks at about 6.0–6.35 MB, see `Docs/BUDGET.md`).

Sources: Track 3 FAQ (17 Nov) and the slides as summarised in PRD v2. No further answers are expected. Where a rule
is explicit we follow it to the letter. Where it is silent we pick the option that cannot fail under any
reasonable reading of the organisers' harness.

## A. Explicit rules: follow exactly

| # | Rule (source) | What we do |
|---|---|---|
| A1 | Python only; "submit a standalone Python script (`main.py`)" (FAQ §3) | Ship ONE self-contained `src/main.py` with the estimator, core maths and I/O inlined. Standard library only. No sibling imports, no C/C++ extension, no ctypes, no compiled bytecode, no numpy. |
| A2 | Input is ONLY the degraded IMU file; waypoints hidden (FAQ §2) | No other input, ever. No per-sequence tables, no fingerprinting of public EuRoC/TUM-VI files, no embedded ground truth or per-dataset calibration. |
| A3 | Exactly one pose per IMU frame; never append (FAQ §2) | Output row count = input data row count, same order, same timestamps. Duplicated input rows get their own output row. |
| A4 | Dropouts are physically missing rows (FAQ §2) | Do not invent rows for gaps. |
| A5 | Blind 5 s rows keep timestamps, values invalid (FAQ §2) | Predict a pose for every one of them. |
| A6 | 8 MB peak, measured at heap level (FAQ §3) | Keep the tracemalloc peak well under (currently about 1.5–2.1 MB); stream the output. |
| A7 | Offline; whole file in memory and non-causal smoothing allowed (FAQ §3) | The smoother stays on. |
| A8 | evo ATE after SE(3) Umeyama alignment, no scale (FAQ §4) | Output frame and origin are free; only the shape counts. |
| A9 | Single thread; 20 ms compute per IMU-second (slides, PRD) | No threads or multiprocessing; aim for ≤ 15 ms per IMU-second in Linux Docker for safety. |
| A10 | Video 2–3 min, strict max 3:00 (FAQ §4) | Target 2:45; check with ffprobe. |
| A11 | Deadline 22 Nov 2026, 11:59 PM IST, Google Form (FAQ §4, PRD) | Submit by 9 PM IST. |
| A12 | Deliverables: `team_name.zip` (`estimated_trajectory.txt`, `src/main.py` + README, optional `metadata.json`), GitHub repo with README and Dockerfile, video, deck in the official template named `CollegeName_TeamName` (PRD) | `Vortex.zip`; deck `ManipalInstituteofTechnology_Vortex`. |

## B. Silent points: our decisions

| # | Unspecified | Decision |
|---|---|---|
| B1 | How `main.py` is invoked | Accept every plausible form: no args (search the working directory for `imu0/data.csv`, `mav0/imu0/data.csv`, `data.csv`, then a single `*.csv`; write `estimated_trajectory.txt` in the working directory); `main.py IN`; `main.py IN OUT`; IN as a sequence folder; `--input/--output` (and `-i/-o`). Works with and without `-S`, from any working directory. |
| B2 | Input formatting variations | Tolerate CRLF, a missing `#` header, no header, blank lines, extra columns, spaces after commas. |
| B3 | Column order (accelerometer-first vs raw EuRoC gyro-first) | Keep auto-detecting it from the data; never assume. |
| B4 | Failure behaviour | Never crash and never write the wrong row count. If the estimator raises, fall back to a constant-pose trajectory (the "floor") for all rows and exit 0, with a note on stderr. |
| B5 | Output timestamp format | TUM format in seconds, written exactly from the integer nanoseconds as a string (`s.nnnnnnnnn`) with no float rounding; space-separated; unit quaternions `qx qy qz qw`. |
| B6 | Whether they run our code or we submit an output for a released file | Be ready for both: one command reproduces any output in seconds. If an evaluation file is released, run it and put that output in the zip. If none is released by the deadline, include the output for an official degraded copy and name the file and commit in the README and `metadata.json`. |
| B7 | Bytecode / packaging | Source only (.py), per A1. |
| B8 | `metadata.json` contents (optional) | Commit hash, build flags, input file name and row count, calibration source, peak heap and time for that run. |
| B9 | Python version of their environment | Must run unchanged on Python 3.10–3.14; checked on 3.12 (Docker), 3.13 and 3.14. |

## C. Where being clever is allowed (estimator choices from the IMU alone)

- Shrinking the output toward its own centroid, and any other shape choice that helps under SE(3) alignment.
- Non-causal smoothing over the whole file, including the blind 5 s.
- Detecting column order, units, dead sensors and still periods from the data.

## D. Off-limits however clever

- Anything in A2 (using public ground truth or recognising which sequence it is).
- Native code, threads, or a second process.
- Writing more or fewer rows than the input has.

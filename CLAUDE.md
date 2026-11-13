# CLAUDE.md: working notes for Vortex

Read this first, then `Docs/TRACK3_PLAN.md` (current phase, what is verified, what is blocked).

## Mission

Turn Vortex into a strong, honest, reproducible submission for the **Samsung PRISM XR Hackathon
Challenge 2026, Track 3: "Path Finder: Trajectory Estimation Under Sensor Degradation"** ("design robust
trajectory-estimation techniques capable of maintaining reliable tracking and navigation when sensor
measurements become degraded or unreliable").

Only the poster is known. The detailed problem statement, dataset, metric, rubric, submission format and
deadline are **unknown until Arnav supplies them**. Do not invent a rubric.

The honest gap: Vortex today is a stationary tabletop station that classifies proximity and detects
knocks. It does not estimate motion or trajectory. The MPU6050 gyro is unused (accelerometer only, 100 Hz),
and on the accepted station the HC-SR04 gives no valid readings (`us_ok=0` in all 15 logged live runs), so
proximity is ToF-only at LOW confidence. The trajectory estimator is new work and the main deliverable.

Team: Arnav Jain (lead), Arya M, Nandhitha Chowdary Surapaneni. Arnav works on Windows; Unity and the
physical station exist only on his machine. Wants direct, concise answers; say plainly what was not verified.

## Invariants (change only with Arnav's approval, as a versioned change, via PR)

- Contract v1: one UTF-8 line, `\n`-terminated on serial (one per datagram on UDP), at most 512 bytes:
  `v=1;dev=phys-xr-01;boot=..;seq=..;ts=..;presence=..;confidence=..;disturbance=..;eventType=..;eventId=..;tEvent=..`
- `boot` change = reset; `seq` ordered only within a boot; `ts` is device ms and is **never** compared with
  Unity's clock; events dedup on `(boot, eventId)`.
- Freshness from Unity arrival time: FRESH <= 0.5 s, STALE <= 3 s, else UNAVAILABLE. Only FRESH reaches rules.
- Every rejection has a `PacketRejectCode`. `#` lines (`#HELLO`, `#DIAG`, `#CAL`, `#ERR`) never enter `PhysicalState`.
- The decision layer never consumes raw ToF, ultrasonic or IMU values. Raw data stays below `PhysicalState`.
- A stale packet never becomes a new event. An old `seq` never overwrites newer state.
- A sensor failure changes confidence/validity; it never directly selects an action.
- Decision logic lives only in the decision provider. Telemetry is observational and cannot alter anything.
- Deterministic decisions: same relevant `WorldState` -> same action and reason. Rule IDs (`R1`-`R8`,
  `X1`-`X3`, `E0`-`E6`) and reason strings are part of the contract.
- Physical events are evidence, not triggers: sensor disturbances never start an attack or shorten the
  1.5 s encounter telegraph.
- Tracking gets its **own versioned channel** (`TrackingState`, not `PhysicalState`) that never feeds the
  decision layer directly.

## Working agreements

- Read before writing: `Docs/ARCHITECTURE.md`, `GHOST_DECISION_SYSTEM.md`, `HARDWARE_SERIAL.md`,
  `LATENCY_PROTOCOL.md`, `TESTING_AND_EVALUATION.md`, `Firmware/README.md`. Keep their discipline of
  separating "verified", "written but not run" and "reported" claims, with dates.
- Tests first, and run them. New suites go in `Assets/PHYSXR/Testing/` and are registered in
  `Tools/TestHarness/Program.cs`. Report real pass/fail counts.
- Never fabricate sensor numbers, thresholds, latencies or results. Calibration-dependent values are named
  parameters with a documented default and a note.
- Small commits with clear messages on a feature branch. Never force-push or rewrite `main`. PR for
  anything that changes a contract or invariant.
- Every PR gets a detailed description (Arnav's standing request, 13 Nov 2026): why the change exists,
  what changed file by file, contract/invariant impact (or "none"), tests run with exact counts and the
  environment, what was not verified, any steps Arnav must run on Windows/hardware with expected output,
  and the `Docs/TRACK3_PLAN.md` rows it updates.
- Ask before: changing contract v1, renaming public types or rule IDs, deleting files, adding third-party
  dependencies, touching firmware pin assignments, publishing anything.
- No secrets in the repo (firmware Wi-Fi password lives in gitignored `secrets.h`; see
  `secrets.example.h`). No personal data beyond what the public docs already hold.
- Scope discipline: no new sensors, ML frameworks or cloud services without a measured need. "Research
  value is the pipeline, not fancy hardware."
- Anything needing Unity, the station or a headset becomes a short numbered checklist for Arnav with the
  exact expected output. Hardware: never advise powering a rewired station without
  `Docs/HARDWARE_ACCEPTANCE.md` A1-A3 (USB unplugged). HC-SR04 ECHO is 5 V and must be divided.
- Where docs disagree, the code and in-repo docs win over any planning documents (e.g. Wi-Fi/UDP, T0-T5,
  `RLDecisionProvider` are plans; the implemented link is USB serial 115200, firmware 1.0.0).
- Docs still say "PHYS-XR" / "The Presence" / "the game". Do not mass-rewrite; rebrand when a doc is touched.

## Verified test commands

Windows (Arnav's machine, as documented in PHYS-XR; .NET 9 SDK):

```
dotnet run -c Release --project Tools/TestHarness          # expect: SUITES RUN: 21, TOTAL FAILED: 0
g++ -std=c++17 -I Firmware/physxr_station Firmware/tests/semantics_test.cpp -o semantics_test && ./semantics_test
python Tools/esp32_sim.py --host 127.0.0.1 --scenario near --seconds 60
```

Linux cloud sandbox (verified 13 Nov 2026). Only .NET SDK 10 is installable (`apt-get install
dotnet-sdk-10.0`) and nuget.org is blocked, so build a net10.0 copy of the project outside the repo:

```
mkdir -p /tmp/harness /tmp/emptyfeed && R=$PWD
sed -e "s#../../Assets#$R/Assets#g" -e "s#\"Program.cs\"#\"$R/Tools/TestHarness/Program.cs\"#" \
    -e "s#\"SerialMonitor.cs\"#\"$R/Tools/TestHarness/SerialMonitor.cs\"#" -e "s#net9.0#net10.0#" \
    Tools/TestHarness/TestHarness.csproj > /tmp/harness/TestHarness.csproj
(cd /tmp/harness && dotnet build -c Release -p:RestoreSources=/tmp/emptyfeed -p:NuGetAudit=false \
   && dotnet bin/Release/net10.0/TestHarness.dll)
```

Results on 13 Nov 2026 (branch `track3/phase0-green`): harness **21 suites, 327 checks, 0 failed**
(net10.0, LangVersion 9; = PHYS-XR's 382 minus the 55 checks in the 5 game suites left behind);
firmware host test **53 checks, 0 failed** (g++ 13.3); `esp32_sim.py` all 7 non-interactive scenarios
emit well-formed v1 datagrams (checked by a throwaway UDP listener, not part of the repo).

Not runnable here: Unity, the ESP32 toolchain (`arduino-cli`), the station, the headset, net9.0 on Windows.

## Layout pointers

- Pure C# (no `UnityEngine`) is what the harness compiles: `Core`, `Communication`, `PhysicalWorld`,
  `WorldState`, `Decision`, `Telemetry`, `Ghost` (minus `GhostRuntime.cs`, `GhostVisual*`, `Presentation/`).
- Planned tracking code: `Assets/PHYSXR/Tracking/`, no `UnityEngine` dependency, harness-tested.
- Firmware semantic core: `Firmware/physxr_station/physxr_semantics.h` (portable C++17, host-tested).

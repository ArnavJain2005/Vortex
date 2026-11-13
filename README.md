# Vortex

Vortex is the sensing-to-decision core extracted from [PHYS-XR](https://github.com/ArnavJain2005/PHYS-XR): an ESP32 sensor station, a validated semantic transport, a Unity-side `WorldState`, and an explainable rule-based decision layer with timestamped telemetry. It is the base for a submission to the Samsung PRISM XR Hackathon Challenge 2026.

The game content (levels, art, audio, UI, game flow) is left behind in PHYS-XR. What remains is the part that senses, transports, fuses, decides and measures.

## Pipeline

```
ToF / ultrasonic / MPU6050 -> ESP32 firmware -> semantic PhysicalState / PhysicalEvent
  -> UDP or serial -> validator -> WorldState -> IDecisionProvider -> GhostAction -> telemetry
```

Raw sensor values stay below the `PhysicalState` boundary. See `Docs/ARCHITECTURE.md`.

## Layout

| Path | Contents |
|---|---|
| `Assets/PHYSXR/Core` | Data contracts, enums, decision interfaces |
| `Assets/PHYSXR/Communication` | UDP/serial receivers, packet parsing and validation, simulated station |
| `Assets/PHYSXR/PhysicalWorld`, `WorldState` | Physical state and event managers, `WorldState` assembly |
| `Assets/PHYSXR/Decision` | Rule-based provider, decision history, sensor response profile |
| `Assets/PHYSXR/Ghost` | Action executor and behaviour controller |
| `Assets/PHYSXR/Telemetry` | JSON-lines and in-memory telemetry sinks |
| `Assets/PHYSXR/Testing` | Edit-mode tests that do not depend on game code |
| `Firmware` | ESP32 sketches, semantic core and host-side tests |
| `Tools` | ESP32 simulator, telemetry analysis, serial test harness |
| `Evidence` | Telemetry summary scripts (raw logs stay in PHYS-XR) |
| `Docs` | Architecture, decision system, latency protocol, hardware and test docs |

## Status

This is a trimmed extract and has not been opened in the Unity editor since extraction. Source files were copied unchanged, and the retained tests were selected because they reference no game or app namespaces. `Packages/manifest.json` is included for reference. A full Unity project (`ProjectSettings`, scenes) is not, so import the `Assets` folder into a Unity 6 project to compile it.

Checks run on 13 Nov 2026 (Linux, branch `track3/phase0-green`):

| Check | Result |
|---|---|
| `Tools/TestHarness` (Unity-free suites) | 21 suites, 327 checks, 0 failed. Built as net10.0 with LangVersion 9 because only .NET 10 was available; not yet re-run on net9.0/Windows |
| Firmware semantic core host test (`g++ -std=c++17`) | 53 checks, 0 failed |
| `Tools/esp32_sim.py`, all non-interactive scenarios | Emit well-formed contract v1 datagrams |

Not run: Unity, the ESP32 firmware compile, the physical station, the headset. Vortex does not yet estimate motion or trajectory; that is the Track 3 work, tracked in [`Docs/TRACK3_PLAN.md`](Docs/TRACK3_PLAN.md).

## Origin

The code and most docs come from PHYS-XR, a PC-VR horror game (*The Presence*). Docs still refer to "PHYS-XR", "the game" and "The Hollow" (the ghost); they are rebranded as they are revised. The firmware's dashboard variant (`Firmware/physxr-unified`) needs a local `secrets.h`; see `Firmware/README.md`.

## Credit

Extracted from PHYS-XR by Arnav Jain, Arya M and Nandhitha Chowdary Surapaneni, Manipal Institute of Technology. MIT licensed.

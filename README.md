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

## Credit

Extracted from PHYS-XR by Arnav Jain, Arya M and Nandhitha Chowdary Surapaneni, Manipal Institute of Technology. MIT licensed.

# Vortex technical video: cut list (final)

**Voice length: 129.06 s.** Final video 131.42 s (0.5 s lead-in, 1.5 s end-slate hold, 0.9 s fade). Cap is 178 s; nothing was trimmed or sped up.

Sources: the 1080p originals (audio sample-identical to the WhatsApp copies, so every cut carried over). c04 was replaced by your retake (c04r, used voice-only).

| # | Video time | Clip | In → Out (s) | Section | Words |
|---|---|---|---|---|---|
| 1 | 0.50 | c01 | 0.55 → 11.51 | K-1 | Hi, I'm Arnav and this is Vortex. Pip's story is a real problem. A drone flies, its motion sensor gets noisy, |
| 2 | 11.45 | c01 | 12.04 → 13.21 | S-a | loses rose, |
| 3 | 12.61 | c01 | 13.62 → 15.58 | S-a | then dies for the last five seconds. |
| 4 | 14.56 | c01 | 16.93 → 19.62 | K-2 | Afterwards, all we have is that lock. |
| 5 | 17.24 | c01 | 20.31 → 23.41 | K-2 | No GPS, no camera and no map. |
| 6 | 20.43 | c02 | 0.46 → 2.70 | K-3 | Vortex reads that log offline |
| 7 | 22.67 | c02 | 3.29 → 7.39 | K-3 | after the flight and rebuilds the drone's path, one 3D position |
| 8 | 26.75 | c02 | 7.86 → 10.26 | K-3 | and orientation for every row it received. |
| 9 | 29.14 | c02 | 11.25 → 16.22 | K-3 | Missing rows get no output and the final blind rows still get |
| 10 | 34.10 | c02 | 16.41 → 17.66 | K-3 | a forecast. |
| 11 | 35.44 | c03 | 0.23 → 3.01 | S-b | Inside, it works in stages. |
| 12 | 38.21 | c03 | 3.64 → 7.14 | K-4 | First, it calibrates an altitude and sensor bias. |
| 13 | 41.70 | c03 | 7.86 → 11.29 | K-4 | A 15-state inertial filter then follows the motion. |
| 14 | 45.12 | c03 | 12.50 → 14.41 | K-4 | When the drone is genuinely still, |
| 15 | 47.02 | c03 | 14.59 → 17.31 | K-4 | that stillness spins velocity to zero. |
| 16 | 49.73 | c03 | 17.77 → 18.62 | K-4 | To stop drift, |
| 17 | 50.57 | c03 | 18.96 → 22.33 | K-4 | we add a prior a cautious assumption about speed |
| 18 | 53.93 | c03 | 22.74 → 24.49 | K-4 | and staying near a running center. |
| 19 | 55.67 | c03 | 25.47 → 28.47 | K-4 | It's not a sensor and it does not control anything. |
| 20 | 58.66 | c03 | 28.85 → 33.46 | K-4 | Gravity alignment then corrects slowly and finally an offline smoother |
| 21 | 63.26 | c03 | 34.64 → 37.65 | K-4 | later readings to revise the earlier ones. |
| 22 | 66.63 | c04r | 1.13 → 7.16 | S-c | It runs as one standard live dpython file on a single thread, |
| 23 | 72.65 | c04r | 7.57 → 10.51 | K-5 | using about 3.5MB of memory |
| 24 | 75.58 | c04r | 10.82 → 13.12 | K-5 | and 6.6 ms |
| 25 | 77.87 | c04r | 13.24 → 14.24 | K-5 | per second |
| 26 | 78.86 | c04r | 14.45 → 15.53 | K-5 | of sensor data, |
| 27 | 79.93 | c04r | 15.93 → 17.85 | K-5 | well inside the limits. |
| 28 | 81.99 | c05 | 1.22 → 2.39 | K-6 | We tested |
| 29 | 83.15 | c05 | 2.69 → 5.34 | K-6 | the ship file on flights that was never tuned on, |
| 30 | 85.79 | c05 | 5.77 → 7.86 | K-6 | degraded with the organized loan script, |
| 31 | 87.87 | c05 | 8.09 → 10.25 | K-6 | and compared it to a static reference. |
| 32 | 90.02 | c05 | 11.51 → 12.37 | K-6 | Vortex |
| 33 | 90.87 | c05 | 12.70 → 17.53 | K-6 | cuts absolute error by 8.1% and one second drift by |
| 34 | 95.69 | c05 | 18.41 → 19.78 | K-6 | forty percent. |
| 35 | 97.05 | c05 | 19.89 → 23.98 | K-6 | The result holds on a second set of test copies. |
| 36 | 101.13 | c05 | 24.63 → 26.88 | K-6 | On handheld TUM-6 |
| 37 | 103.37 | c05 | 27.07 → 34.31 | K-6 | recordings, the error is 14.8% lower in all four rooms. |
| 38 | 110.75 | c06 | 0.38 → 3.42 | K-7 | When the sensor dies, Vorte stops trusting it, |
| 39 | 113.78 | c06 | 3.86 → 10.33 | K-7 | it holds the last state it gleamed instead of inventing motion. Every output passes the format check. |
| 40 | 120.89 | c07 | 1.32 → 4.72 | S-d | every feature had to pass a rule fixed before testing: |
| 41 | 124.28 | c07 | 5.16 → 7.88 | K-8 | Vertex a navigator that knows |
| 42 | 126.99 | c07 | 8.03 → 10.60 | K-8 | how much to trust its sensor. |

## Removed spans longer than 1 s

- c01 15.58–16.93 s (1.35 s): dead air 1.53s -> 0.15s
- c01 23.41–24.58 s (1.17 s): clip tail
- c03 11.29–12.50 s (1.21 s): dead air 1.39s -> 0.15s
- c03 33.46–34.64 s (1.18 s): stumble: 'later' before restart 'use later readings'
- c03 37.65–39.27 s (1.62 s): clip tail
- c04r 0.00–1.13 s (1.13 s): clip head
- c05 0.00–1.22 s (1.22 s): clip head
- c05 10.25–11.51 s (1.26 s): filler: 'Well,'
- c06 10.33–11.48 s (1.15 s): clip tail
- c07 0.00–1.32 s (1.32 s): clip head
- c07 10.60–12.07 s (1.47 s): clip tail

## Content removed

- c03: the false start "…an offline smoother — *later* —" before "use later readings…".
- c05: the filler "*Well,*" before "Vortex cuts…".
- c05: the stumble "drift by *four-oh,* forty percent" → "drift by forty percent".
- c07: the filler "*Well,*" before "every feature…".
- Silences over 0.30 s inside a take compressed to ~0.15–0.18 s.

## Pauses kept

- **Every clip join: ~1.0 s** (your request). Picture uses only calm frames from the end and start of each take; the rest is a held frame; audio is clean room tone, so no breaths or phone-handling noise.
- Emphasis pauses after "8.1 percent", "40 percent", "14.8 percent", "inventing motion" and before the final line; two lengthened by 0.05 s and 0.10 s with room tone.

## Seam check

- 41 seams, 10 ms crossfades at zero crossings, cut only inside measured silence (`seams.txt`, `seams_check.wav`).
- One seam lands 20 ms before speech: "Every feature" (your "Well" runs straight into "every"); the word itself is intact.
- Whole cut track re-transcribed with two independent speech models: every kept word comes back complete.

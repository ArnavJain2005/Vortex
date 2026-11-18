# Getting the data

The scored Track 3 task uses **EuRoC MAV** and **TUM-VI**, both in EuRoC's ASL layout. Download on
Windows (the sandbox cannot reach these hosts) and unzip under `data/` at the repo root; `/data/` is
ignored by git, so nothing is committed.

## EuRoC MAV (start here)

Burri et al., *The EuRoC micro aerial vehicle datasets*, IJRR 2016. 11 indoor sequences flown on a
multirotor, IMU at 200 Hz, ground truth from a laser tracker or motion capture.

1. Go to https://projects.asl.ethz.ch/datasets/euroc-mav/ (files are now hosted on the ETH Research
   Collection, DOI 10.3929/ethz-b-000690084).
2. Download the **ASL Dataset Format** zips (not ROS bags). Order: `MH_01_easy`, then `MH_02_easy`,
   `V1_01_easy`, `MH_03_medium`.
3. Unzip so that you get:

   ```
   data/euroc/MH_01_easy/mav0/imu0/data.csv                         IMU: what main.py reads
   data/euroc/MH_01_easy/mav0/state_groundtruth_estimate0/data.csv  ground truth: scoring only
   ```

Only `imu0/` and `state_groundtruth_estimate0/` are needed; the camera folders can be deleted locally to
save space.

**Held-out data for drag rule v2 (V3).** `V1_01_easy`, `V1_02_medium`, `V1_03_difficult` (the Vicon Room 1
zip) are the decision sequences of the pre-registered rule in `tools/drag_fit.py` (commit c1b594c). Extract
them the same way, to `data/euroc/V1_0x_*/mav0/`. Do not use them for any tuning: run them once,
`python tools/drag_fit.py --rule v2 data/euroc/V1_01_easy data/euroc/V1_02_medium data/euroc/V1_03_difficult`,
and record the result. Vicon Room 2 (`V2_01..03`) is the final test set: extract it the same way if you like, but nothing
reads it until "run the final table" (`tools/eval_euroc.py` skips `V2_*` and refuses it without `--final`).

V1_01..03 were extracted on 17 Nov 2026 (IMU 200 Hz, 145.6 / 85.5 / 107.5 s).

## TUM-VI

Schubert et al., *The TUM VI Benchmark for Evaluating Visual-Inertial Odometry*, IROS 2018 (arXiv:1804.06120).
Hand-held rig, BMI160 IMU at ~199.4 Hz (`dt` 5.016 ms), 120 Hz motion-capture ground truth.

1. Go to https://cvg.cit.tum.de/data/datasets/vi-dataset.
2. Download the **Euroc / DSO 512x512** tars for `room1`..`room6` (`dataset-room1_512_16.tar` .. `dataset-room6_512_16.tar`).
3. Extract `mav0/imu0/data.csv` and `mav0/mocap0/data.csv` into `data/tumvi/dataset-roomN_512_16/mav0/`.
   (`vortex/data/euroc.py` reads `mav0/imu0/data.csv` and `mav0/mocap0/data.csv` directly.)

**Mocap ground-truth frame.** In the calibrated EuRoC/DSO exports, `mav0/mocap0/data.csv` poses are **in the
IMU body frame** (hand-eye calibration `T_MI` and clock offset already applied; no marker lever arm).
Citation: TUM-VI benchmark website (https://cvg.cit.tum.de/data/datasets/vi-dataset, *"All sequences have
been processed to have: ... ground truth poses in the IMU frame"* and *"the calibrated datasets already have
corrected IMU measurements and Ground Truth in IMU frame"*); Schubert et al., IROS 2018, Section IV-B.
Verified directly in `dataset-room1_512_16.tar`: all 16,541 data rows of `mav0/mocap0/data.csv` are
byte-for-byte identical to `dso/gt_imu.csv`.

Extracted 18 Nov 2026 (`python tools/tumvi_inspect.py --root data/tumvi`):

| Sequence | IMU rows | Length | IMU rate | Time gaps | Ground-truth rows | Ground truth covers |
|---|---|---|---|---|---|---|
| dataset-room1_512_16 | 28,122 | 141.1 s | 199.4 Hz (dt 5.016 ms) | none (max dt 5.04 ms) | 16,541 | 0.01..141.03 s (100.0%, 120 Hz, 9 gaps >50 ms, max 1.06 s) |
| dataset-room2_512_16 | 28,732 | 144.1 s | 199.4 Hz (dt 5.016 ms) | none (max dt 5.04 ms) | 15,477 | 0.01..144.08 s (100.0%, 120 Hz, 22 gaps >50 ms, max 2.49 s) |
| dataset-room3_512_16 | 28,124 | 141.1 s | 199.4 Hz (dt 5.016 ms) | none (max dt 5.04 ms) | 15,200 | 0.01..141.03 s (100.0%, 120 Hz, 31 gaps >50 ms, max 1.99 s) |
| dataset-room4_512_16 | 22,212 | 111.4 s | 199.4 Hz (dt 5.016 ms) | none (max dt 5.04 ms) | 13,075 | 0.02..111.39 s (100.0%, 120 Hz, 13 gaps >50 ms, max 0.48 s) |
| dataset-room5_512_16 | 28,381 | 142.3 s | 199.4 Hz (dt 5.016 ms) | none (max dt 5.04 ms) | 16,999 | 0.01..142.33 s (100.0%, 120 Hz, 3 gaps >50 ms, max 0.17 s) |
| dataset-room6_512_16 | 26,281 | 131.8 s | 199.4 Hz (dt 5.016 ms) | none (max dt 5.04 ms) | 15,244 | 0.97..131.79 s (99.3%, 120 Hz, 5 gaps >50 ms, max 3.15 s) |

Tuning sequences: `dataset-room1_512_16`, `dataset-room2_512_16`. Held out: `room3..room6`.

## ADVIO (earlier direction, optional)

Cortes, Solin, Rahtu, Kannala. *ADVIO: An Authentic Dataset for Visual-Inertial Odometry.* ECCV 2018.
Repository: https://github.com/AaltoVision/ADVIO. Licence: **CC BY-NC 4.0** (attribution required,
no commercial use). The data stays out of git (`/data/` is ignored).

23 sequences, 71 to 255 MB each zipped, about 5.1 GB unzipped in total. Start with two or three.

1. Download from Zenodo: https://zenodo.org/record/1476931 (files `advio-01.zip` ... `advio-23.zip`).
   ADVIO's README also links https://zenodo.org/record/1320824; use whichever lists the zips.
2. Unzip into `data/advio/` at the repo root so that you get:

   ```
   data/advio/advio-01/ground-truth/poses.csv
   data/advio/advio-01/iphone/accelerometer.csv
   data/advio/advio-01/iphone/gyroscope.csv      (or gyro.csv)
   data/advio/advio-01/iphone/arkit.csv
   data/advio/advio-01/pixel/arcore.csv          (optional)
   ```

   On Windows PowerShell: `Expand-Archive advio-01.zip -DestinationPath data\advio`

3. Validate:

   ```
   python -m vortex check --advio data/advio --seq 1
   ```

   Expected: sample counts, roughly 100 Hz IMU, 60 Hz pose, 100 Hz ground truth; `|accel|` median near
   9.8; and the line `OK: the loaded accelerometer sign fits ground truth better.` If it prints a
   WARNING instead, re-run with the `--accel-sign` value it suggests and report it, because the default
   sign is an assumption (Apple CoreMotion convention), not yet checked on the real files.

Per-batch IMU biases from ADVIO's calibration README (batches: sequences 1-12, 13-17, 18-19, 20-23)
are removed by default.

## Known caveats

- Ground truth and ARKit poses are **camera** poses; the IMU is offset by about 7.5 cm. The baselines
  rotate between the frames with ADVIO's published camera-IMU rotation and ignore the lever arm.
- ARKit's world frame differs from the ground-truth frame. Scoring fits one rigid transform on the
  undegraded ARKit stream and reuses it for every degraded run, so alignment cannot hide a fault.
- The dead-reckoning baseline is given ground-truth initial state and a gravity vector estimated with
  ground-truth orientation. It is a best case for inertial-only tracking.

## Our own recordings (Samsung Galaxy S24)

The S24 is recorded with **Sensor Logger** (Android, `com.kelvin.sensorapp`, free tier is enough).
Format reference: https://github.com/tszheichoi/awesome-sensor-logger. The S24 has an accelerometer,
gyroscope, magnetometer and barometer. Sensor Logger's published sampling table lists S24 models
(SM-S921B) at about 125 Hz accelerometer and 500 Hz gyroscope; `vortex check` reports what your phone
actually achieved.

### App settings (once)

1. Install Sensor Logger from the Play Store.
2. Enable: **Accelerometer** (it also writes TotalAcceleration.csv, which we use), **Gyroscope**,
   **Magnetometer**, **Barometer**, **Annotation**. Disable location, camera and audio.
3. Settings: sampling rate at the fastest option; export format **Zipped CSV**.

### Walk protocol

Phone recordings have no ground-truth trajectory, so the reference is a set of marked floor points.

1. Mark 4 to 6 points on the floor with tape (a corridor or a room is fine). Measure their positions
   with a tape measure in metres, taking the start mark as (0, 0, 0) and the first straight leg as +x.
   Write them to `data/phone/checkpoints.csv`:

   ```
   name,x,y,z
   start,0,0,0
   door,6.0,0,0
   corner,6.0,4.5,0
   ```

2. Hold the phone upright in front of you, as if looking through it. Start recording, stand on
   `start` and keep still for **3 seconds** (this is used to estimate the gyro bias and gravity).
3. At each mark, stop for a second and add an annotation whose text is exactly the checkpoint name.
4. Walk back to `start`, annotate `start` again, keep still for 3 seconds, stop recording.
5. Export as Zipped CSV and unzip into `data/phone/<walk-name>/`, e.g. `data/phone/walk-01/`.
6. Check it:

   ```
   python -m vortex check --phone data/phone/walk-01 --checkpoints data/phone/checkpoints.csv
   ```

   Expected: raw gyro and accelerometer rates, magnetometer and barometer sample counts, `|accel|`
   median near 9.8, a still period at the start with a small gyro bias (around 0.01 rad/s or less), all
   checkpoints matched, and `OK: recording looks usable.`

Record at least three walks: one clean, and two where you deliberately cause trouble (fast turns,
shaking the phone, covering it). These become our real-world fault examples.

### Live streaming (sensor station)

Instead of exporting files, the S24 can stream to the computer while it records.

1. Connect the phone and the computer to the same Wi-Fi. University and office networks often block
   device-to-device traffic; a phone hotspot with the laptop joined to it works.
2. On the computer: `python -m vortex station --source phone --save data/phone/live-01`.
   It prints a URL such as `http://192.168.1.20:8000/data`. On Windows, allow Python through the
   firewall when asked (private networks).
3. In Sensor Logger: Settings > Data Streaming > **HTTP Push**, enable it, paste the URL, tap
   **Tap to Test Pushing** (expect a 200 response). Enable the same sensors as above.
4. Start a recording. The station prints `phone connected: device ...`, then one line per second with
   the sample rate and current readings. Stop the recording and it prints `phone quiet`. Ctrl+C ends it
   and saves the stream.
5. `python -m vortex check --phone data/phone/live-01` validates the saved stream.

`python -m vortex station` (no `--source`) waits 30 s for the phone and otherwise runs the synthetic
station, so the rest of the pipeline can always run.

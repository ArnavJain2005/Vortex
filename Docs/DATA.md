# Getting the data

## ADVIO

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

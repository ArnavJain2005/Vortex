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

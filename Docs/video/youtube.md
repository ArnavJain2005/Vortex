# YouTube title and description

## Title options

1. Vortex: Rebuilding a Drone's Flight Path from a Broken IMU Log | Samsung PRISM XR Hackathon 2026
2. No GPS, No Camera, No Map: Recovering 6-DoF Flight from IMU Data Alone | Vortex
3. Vortex, a Navigator That Knows How Much to Trust Its Sensor (Track 3: Path Finder)

## Description

```
Vortex rebuilds a drone's full 6-DoF flight path offline, after the flight, from a degraded IMU log alone: gyro and accelerometer, with no GPS, no camera and no map. This is the technical walkthrough of my solo entry to the Samsung PRISM XR Hackathon 2026, Track 3: Path Finder.

The log is noisy, loses rows in bursts, and goes completely dead for the final 5 seconds. Vortex outputs one 3D position and orientation for every row it received, writes nothing for missing rows, and forecasts the final blind rows instead of inventing motion.

How it works
• Calibrates attitude and sensor bias from a still interval
• A 15-state error-state Kalman filter follows the motion
• Stillness detection pins velocity to zero
• A cautious speed-and-centre prior limits drift (an assumption, not a sensor, and it controls nothing)
• Windowed gravity alignment corrects tilt slowly
• An offline forward-backward (RTS) smoother lets later readings revise earlier ones

Runs as one standard-library Python file on a single thread: about 3.5 MB of memory and 6.6 ms per second of sensor data, against limits of 8 MB and 20 ms.

Results (absolute error = APE after SE(3) alignment, drift = 1 s RPE)
Compared with a static reference scored the same way, on held-out EuRoC flights degraded with the organisers' own script:
• −8.1% absolute error, −40% one-second drift (5 of 6 flights improved)
• −7.1% on a second set of test copies
• −14.8% error on hand-held TUM-VI recordings, all four rooms (tuning used EuRoC MH_01/02 and TUM-VI rooms 1–2)
• 100% of outputs passed the format check; 521 automated tests pass

Chapters
0:00 Intro
0:04 The problem: Pip's broken flight log
0:14 All we have is the log
0:20 What Vortex rebuilds
0:35 The pipeline, stage by stage
1:06 Runtime: one file, one thread
1:21 Results
1:50 When the sensor dies
2:00 Rule first, test second

Code: https://github.com/ArnavJain2005/Vortex

Arnav Jain · Manipal Institute of Technology

Credits: Pip film AI-animated, narration voice by ElevenLabs (stills only appear here). Music "Abstract Technology Ambient" by yurasoop (Pixabay). Sound effects from the DAEDAL Transition SFX Pack and the alfred.makes kit (CC0). All animation was built in code with HyperFrames.

#SamsungPRISM #IMU #SensorFusion #KalmanFilter #Drones #Robotics #Hackathon
```

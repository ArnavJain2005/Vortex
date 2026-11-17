# Third-party data, code and tools

| Item | Use in Vortex | Licence | Copied into this repo? |
|---|---|---|---|
| [ADVIO dataset](https://github.com/AaltoVision/ADVIO) (Cortes et al., ECCV 2018) | Evaluation data: iPhone IMU, ARKit pose, ground truth | CC BY-NC 4.0 | No. Downloaded by the user into the ignored `data/` folder |
| ADVIO calibration values (IMU biases, camera-IMU rotation) | Constants in `vortex/data/advio.py`, with source noted | Published with the dataset | Numeric constants only |
| ADVIO scripts (`my_utils.py`, `sync-data.py`) | Read to learn the CSV formats; no code reused | GPL-2.0 or later | No |
| [Sensor Logger](https://github.com/tszheichoi/awesome-sensor-logger) app (Kelvin Tsz Hei Choi) | Records our Samsung S24 sensors to CSV, and pushes them live over HTTP to `vortex station` | Proprietary app, free tier; we only read its exported files and its documented push JSON | No |
| [evo](https://github.com/MichaelGrupp/evo) | Independent cross-check of `vortex/scoring.py` (`tools/crosscheck_evo.py`, results in `Docs/EVO_CROSSCHECK.md`); our scorer re-implements the published definitions, no evo code copied | GPL-3.0 | No. Not a dependency; pip-installed in a separate venv only to run the cross-check |
| numpy, pandas, matplotlib, pytest | Runtime and test dependencies | BSD / PSF-style | No (installed by pip) |
| `degrade_imu.py` (organisers' Track 3 student package, received 17 Nov 2026) | Official degradation script; called by `tools/official_degrade.py` | No licence stated | **No** (git-ignored at `tools/official/` until Arnav decides) |

Our own code is MIT-licensed (see `LICENSE`). Anything that would bring GPL code into the repo needs a
decision first. Samsung's rules on prior work and open data have not been checked yet.

## Citation

```
@inproceedings{cortes2018advio,
  title     = {{ADVIO}: An Authentic Dataset for Visual-Inertial Odometry},
  author    = {Cort{\'e}s, Santiago and Solin, Arno and Rahtu, Esa and Kannala, Juho},
  booktitle = {European Conference on Computer Vision (ECCV)},
  year      = {2018}
}
```

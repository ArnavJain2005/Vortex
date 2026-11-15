"""Phone (Samsung S24 via Sensor Logger) loader tests, on synthetic files in Sensor Logger's export layout."""

import numpy as np
import pandas as pd
import pytest

from vortex.cli import main
from vortex.data import phone, synthetic

EPOCH_NS = 1_763_200_000_000_000_000  # an arbitrary 2025 epoch in ns


def _sensor_csv(path, t, xyz, cols=("x", "y", "z")):
    df = pd.DataFrame({"time": (EPOCH_NS + np.round(t * 1e9)).astype(np.int64), "seconds_elapsed": t})
    for i, c in enumerate(cols):
        df[c] = xyz[:, i]
    # Sensor Logger writes z, y, x in some files; the loader must read by name, so shuffle the order.
    df = df[["time", "seconds_elapsed", *reversed(cols)]]
    df.to_csv(path, index=False)


def _write_export(folder, still_s=3.0, platform="android", annotations=None):
    """Still for `still_s` seconds, then the synthetic walk. Gyro at 500 Hz, accel at 125 Hz (S24-like)."""
    folder.mkdir(parents=True)
    walk = synthetic.make_sequence(duration=20.0, imu_rate=500.0)
    t_still = np.arange(0.0, still_s, 1 / 500.0)
    t = np.concatenate([t_still, walk.imu.t + still_s])
    f_still = np.tile([0.0, 0.0, 9.81], (len(t_still), 1))
    # Start the walk from the same level orientation the still period implies.
    gyro = np.vstack([np.zeros((len(t_still), 3)), walk.imu.gyro])
    acc = np.vstack([f_still, walk.imu.accel])
    _sensor_csv(folder / "Gyroscope.csv", t, gyro)
    sub = slice(None, None, 4)  # 125 Hz
    if platform == "android":
        _sensor_csv(folder / "TotalAcceleration.csv", t[sub], acc[sub])
    else:  # iOS, unstandardised: inertial-force convention, split into user + gravity
        grav = np.tile([0, 0, 9.81], (len(t[sub]), 1))
        _sensor_csv(folder / "Accelerometer.csv", t[sub], -(acc[sub] - grav))
        _sensor_csv(folder / "Gravity.csv", t[sub], -grav)
    tb = np.arange(0.0, t[-1], 1 / 12.5)
    _sensor_csv(folder / "Barometer.csv", tb, np.column_stack([np.full_like(tb, 1013.0), np.zeros_like(tb)]),
                cols=("pressure", "relativeAltitude"))
    pd.DataFrame({"version": [3], "device name": ["SM-S921B"], "platform": [platform],
                  "standardisation": ["false"]}).to_csv(folder / "Metadata.csv", index=False)
    if annotations:
        pd.DataFrame({"time": [EPOCH_NS + int(ts * 1e9) for ts, _ in annotations],
                      "seconds_elapsed": [ts for ts, _ in annotations],
                      "millisecond_press_duration": [100] * len(annotations),
                      "text": [txt for _, txt in annotations]}).to_csv(folder / "Annotation.csv", index=False)
    return t, gyro, acc


def test_loader_resamples_and_keeps_convention(tmp_path):
    t, gyro, acc = _write_export(tmp_path / "rec")
    rec = phone.load_sensor_logger(tmp_path / "rec", rate=200.0)
    assert rec.meta["accel_source"] == "TotalAcceleration"
    assert rec.meta["raw_rate_hz"]["gyro"] == pytest.approx(500, rel=0.01)
    assert rec.meta["raw_rate_hz"]["accel"] == pytest.approx(125, rel=0.01)
    assert np.median(np.diff(rec.imu.t)) == pytest.approx(1 / 200)
    # At rest the specific force reads +g along +z (Android convention = ours).
    assert np.allclose(rec.imu.accel[rec.imu.t < 2.5].mean(axis=0), [0, 0, 9.81], atol=1e-6)
    # Resampled gyro matches the source (differences come only from nanosecond timestamp rounding).
    ref = np.column_stack([np.interp(rec.imu.t, t, gyro[:, i]) for i in range(3)])
    assert np.max(np.abs(rec.imu.gyro - ref)) < 1e-6
    assert rec.barometer is not None and rec.barometer.columns == ["pressure", "relativeAltitude"]
    assert rec.magnetometer is None


def test_ios_export_converted_to_android_convention(tmp_path):
    _write_export(tmp_path / "rec", platform="ios")
    rec = phone.load_sensor_logger(tmp_path / "rec")
    assert rec.meta["accel_source"] == "Accelerometer+Gravity"
    assert np.allclose(rec.imu.accel[rec.imu.t < 2.5].mean(axis=0), [0, 0, 9.81], atol=1e-6)


def test_still_window_detected(tmp_path):
    _write_export(tmp_path / "rec", still_s=3.0)
    rec = phone.load_sensor_logger(tmp_path / "rec")
    spans = phone.still_windows(rec.imu)
    assert spans and spans[0][0] == pytest.approx(0.0, abs=0.01) and spans[0][1] > 2.5


def test_annotations_and_checkpoints(tmp_path, capsys):
    _write_export(tmp_path / "rec", annotations=[(1.0, "start"), (10.0, "door"), (22.0, "start")])
    cps = tmp_path / "checkpoints.csv"
    cps.write_text("name,x,y,z\nstart,0,0,0\ndoor,4.2,0,0\npillar,4.2,3.0,0\n")
    rec = phone.load_sensor_logger(tmp_path / "rec")
    assert [a.text for a in rec.annotations] == ["start", "door", "start"]
    assert rec.annotations[1].t == pytest.approx(10.0)
    assert set(phone.read_checkpoints(cps)) == {"start", "door", "pillar"}
    assert main(["check", "--phone", str(tmp_path / "rec"), "--checkpoints", str(cps)]) == 0
    out = capsys.readouterr().out
    assert "SM-S921B" in out and "never annotated ['pillar']" in out and "OK" in out


def test_missing_sensor_has_clear_error(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(FileNotFoundError, match="Sensor Logger"):
        phone.load_sensor_logger(tmp_path / "empty")


def test_baselines_refuses_phone(tmp_path):
    _write_export(tmp_path / "rec")
    with pytest.raises(SystemExit):
        main(["baselines", "--phone", str(tmp_path / "rec")])

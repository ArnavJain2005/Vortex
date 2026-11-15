"""Live sensor stations: synthetic, and the phone (Sensor Logger HTTP push)."""

import json
import time
import urllib.request

import numpy as np
import pytest

from vortex import stations
from vortex.cli import main
from vortex.data import phone

T0 = 1_763_200_000_000_000_000


def _msg(i, items, device="SM-S921B-test", session="sess-1"):
    return {"messageId": i, "sessionId": session, "deviceId": device, "payload": items}


def _item(name, t_s, x, y, z):
    return {"name": name, "time": T0 + int(t_s * 1e9), "values": {"x": x, "y": y, "z": z}}


def test_synthetic_station_streams_the_sequence():
    st = stations.SyntheticStation(duration=5.0, rate=100.0, realtime=False).start()
    for _ in range(100):
        if st.finished:
            break
        time.sleep(0.02)
    samples = st.read()
    st.stop()
    imu = stations.samples_to_imu(samples)
    assert len(imu.t) == len(st.sequence.imu.t)
    assert np.allclose(imu.accel, st.sequence.imu.accel)
    # Starts at rest: gravity only.
    assert np.allclose(imu.accel[: 200].mean(axis=0), [0, 0, 9.81], atol=0.05)
    assert st.status().source == "synthetic"


def test_phone_station_pairs_gyro_with_latest_accel_and_reports_connection():
    st = stations.PhoneStation(port=0)  # ingest() needs no server
    seen = []
    st.on_connect(seen.append)
    items = [_item("TotalAcceleration", 0.000, 0.1, 0.2, 9.8)]
    items += [_item("gyroscope", 0.002 * k, 0.01 * k, 0.0, 0.0) for k in range(1, 6)]
    items += [_item("totalacceleration", 0.008, 0.3, 0.2, 9.7), _item("gyroscope", 0.012, 0.5, 0, 0)]
    items.append({"name": "battery", "time": T0, "values": {"batteryLevel": 0.9}})
    st.ingest(_msg(0, items))

    out = st.read()
    assert len(out) == 6
    assert np.allclose(out[0].accel, [0.1, 0.2, 9.8]) and np.allclose(out[-1].accel, [0.3, 0.2, 9.7])
    assert out[0].t == pytest.approx(0.002) and np.allclose(out[0].gyro, [0.01, 0, 0])
    s = st.status()
    assert s.connected and s.device == "SM-S921B-test" and s.messages == 1
    assert {"totalacceleration", "gyroscope", "battery"} <= s.sensors_seen
    assert len(seen) == 1 and seen[0].device == "SM-S921B-test"

    st.ingest(_msg(1, [_item("gyroscope", 0.014, 0, 0, 0)]))
    assert len(seen) == 1  # the connect callback fires once


def test_phone_station_sums_user_accel_and_gravity_without_total():
    st = stations.PhoneStation(port=0)
    st.ingest(_msg(0, [_item("accelerometer", 0.0, 0.5, 0, 0), _item("gravity", 0.0, 0, 0, 9.8),
                       _item("gyroscope", 0.001, 0, 0, 0.1)]))
    (s,) = st.read()
    assert np.allclose(s.accel, [0.5, 0, 9.8])


def test_phone_station_goes_quiet():
    st = stations.PhoneStation(port=0, quiet_after_s=0.1)
    assert not st.status().connected
    st.ingest(_msg(0, [_item("gyroscope", 0.0, 0, 0, 0)]))
    assert st.status().connected
    time.sleep(0.15)
    assert not st.status().connected


def test_phone_station_over_http():
    st = stations.PhoneStation(host="127.0.0.1", port=0).start()
    try:
        items = [_item("totalacceleration", 0.0, 0, 0, 9.81)] + [
            _item("gyroscope", 0.002 * k, 0, 0, 0.05) for k in range(1, 51)
        ]
        req = urllib.request.Request(f"http://127.0.0.1:{st.port}/data", data=json.dumps(_msg(0, items)).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 200
        bad = urllib.request.Request(f"http://127.0.0.1:{st.port}/data", data=b"not json", method="POST")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(bad, timeout=5)
        assert e.value.code == 400
        assert stations.wait_for_phone(st, timeout=1.0)
        assert len(st.read()) == 50
        assert st.status().rate_hz == pytest.approx(500, rel=0.01)
        assert st.push_url().endswith(f":{st.port}/data")
    finally:
        st.stop()


def test_saved_stream_reads_back_with_phone_loader(tmp_path):
    st = stations.SyntheticStation(duration=6.0, rate=200.0, realtime=False).start()
    while not st.finished:
        time.sleep(0.01)
    imu = stations.samples_to_imu(st.read())
    st.stop()
    out = stations.save_as_sensor_logger(imu, tmp_path / "live", device="synthetic")
    rec = phone.load_sensor_logger(out, rate=200.0)
    assert rec.meta["accel_source"] == "TotalAcceleration"
    assert abs(rec.imu.t[-1] - imu.t[-1]) < 0.01
    assert phone.still_windows(rec.imu)[0][0] == pytest.approx(0.0, abs=0.01)


def test_cli_station_auto_falls_back_to_synthetic(tmp_path, capsys):
    rc = main(["station", "--source", "auto", "--port", "0", "--wait", "0.3", "--seconds", "2",
               "--fast", "--save", str(tmp_path / "live")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "no phone connected; using the synthetic station" in out
    assert (tmp_path / "live" / "Gyroscope.csv").is_file()


def test_cli_station_phone_only_fails_without_phone(capsys):
    assert main(["station", "--source", "phone", "--port", "0", "--wait", "0.2"]) == 1
    assert "no phone connected" in capsys.readouterr().out

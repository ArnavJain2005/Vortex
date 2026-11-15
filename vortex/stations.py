"""Live sensor stations: where IMU samples come from while the program runs.

Two stations share one interface:

- SyntheticStation: generates a walking IMU stream with exact ground truth, paced in real time (or as fast
  as possible for tests). Always available; used when no phone is connected and in tests.
- PhoneStation: an HTTP endpoint that the Sensor Logger app on an Android phone (our Samsung Galaxy S24)
  pushes to during a recording ("HTTP Push" in the app's settings). It reports when a phone connects or
  goes quiet.

Sensor Logger's push format (github.com/tszheichoi/awesome-sensor-logger, PUSHING.md): POST with JSON
  {"messageId": int, "sessionId": str, "deviceId": str, "payload": [{"name": str, "time": ns, "values": {...}}]}
Sensor names are matched case-insensitively. We use "totalacceleration" (Android raw accelerometer with
gravity) when present, otherwise "accelerometer" + "gravity" summed, and "gyroscope". Unverified until a
real S24 pushes: the exact sensor names on Android. `status()["sensors_seen"]` lists what actually arrived.

Both stations emit ImuSample objects in our conventions (seconds, rad/s, specific force in m/s^2, +g up).
Accelerometer and gyroscope arrive separately and at different rates on a phone, so the phone station
emits one sample per gyroscope reading, paired with the most recent accelerometer reading.
"""

from __future__ import annotations

import json
import queue
import socket
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pandas as pd

from .data import synthetic
from .types import ImuData


@dataclass
class ImuSample:
    t: float  # seconds since the station started receiving
    gyro: np.ndarray  # (3,) rad/s
    accel: np.ndarray  # (3,) m/s^2 specific force


@dataclass
class StationStatus:
    source: str
    connected: bool = False
    device: str | None = None
    session: str | None = None
    samples: int = 0
    messages: int = 0
    last_seen_s_ago: float | None = None
    sensors_seen: set = field(default_factory=set)
    rate_hz: float | None = None


class SensorStation:
    """Common interface. Subclasses fill self._queue with ImuSample objects."""

    source = "base"

    def __init__(self) -> None:
        self._queue: queue.Queue[ImuSample] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._count = 0
        self._recent_t: list[float] = []

    # lifecycle
    def start(self) -> "SensorStation":
        raise NotImplementedError

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def __enter__(self) -> "SensorStation":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    # data
    def read(self, max_samples: int = 100_000, timeout: float = 0.0) -> list[ImuSample]:
        """All queued samples (up to max_samples). Waits up to timeout for the first one."""
        out: list[ImuSample] = []
        try:
            out.append(self._queue.get(timeout=timeout) if timeout > 0 else self._queue.get_nowait())
        except queue.Empty:
            return out
        while len(out) < max_samples:
            try:
                out.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return out

    def status(self) -> StationStatus:
        raise NotImplementedError

    def _emit(self, s: ImuSample) -> None:
        self._queue.put(s)
        with self._lock:
            self._count += 1
            self._recent_t.append(s.t)
            if len(self._recent_t) > 400:
                del self._recent_t[:-400]

    def _rate(self) -> float | None:
        with self._lock:
            ts = list(self._recent_t)
        if len(ts) < 3 or ts[-1] <= ts[0]:
            return None
        return (len(ts) - 1) / (ts[-1] - ts[0])


class SyntheticStation(SensorStation):
    """Replays a synthetic walk as a live stream. realtime=False emits as fast as possible."""

    source = "synthetic"

    def __init__(
        self, duration: float = 60.0, rate: float = 200.0, realtime: bool = True, seed: int = 0, still_s: float = 3.0
    ) -> None:
        super().__init__()
        self.realtime = realtime
        # Starts at rest for still_s seconds, like the phone walk protocol.
        self.sequence = synthetic.make_sequence(
            duration=duration,
            imu_rate=rate,
            gyro_noise=2.4e-3 * rate**0.5,
            accel_noise=4.8e-3 * rate**0.5,
            seed=seed,
            still_s=still_s,
        )
        self.ground_truth = self.sequence.ground_truth
        self._done = threading.Event()

    def start(self) -> "SyntheticStation":
        self._thread = threading.Thread(target=self._run, name="synthetic-station", daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        imu = self.sequence.imu
        t_wall0 = time.monotonic()
        for k in range(len(imu.t)):
            if self._stop.is_set():
                break
            if self.realtime:
                delay = imu.t[k] - (time.monotonic() - t_wall0)
                if delay > 0:
                    time.sleep(delay)
            self._emit(ImuSample(float(imu.t[k]), imu.gyro[k].copy(), imu.accel[k].copy()))
        self._done.set()

    @property
    def finished(self) -> bool:
        return self._done.is_set()

    def status(self) -> StationStatus:
        return StationStatus(
            source=self.source,
            connected=not self._done.is_set(),
            device="synthetic walk",
            samples=self._count,
            sensors_seen={"gyroscope", "accelerometer"},
            rate_hz=self._rate(),
        )


class PhoneStation(SensorStation):
    """Receives Sensor Logger HTTP pushes from a phone on the same network.

    In the app: Settings > Data Streaming > HTTP Push, URL = the one printed by `push_url()`
    (e.g. http://192.168.1.20:8000/data), then start a recording.
    """

    source = "phone"

    def __init__(self, host: str = "0.0.0.0", port: int = 8000, quiet_after_s: float = 2.0) -> None:
        super().__init__()
        self.host, self.port = host, port
        self.quiet_after_s = quiet_after_s
        self._server: ThreadingHTTPServer | None = None
        self._last_rx: float | None = None
        self._t0_ns: int | None = None
        self._device: str | None = None
        self._session: str | None = None
        self._messages = 0
        self._sensors: set[str] = set()
        self._last_acc: np.ndarray | None = None  # with gravity
        self._last_user_acc: np.ndarray | None = None
        self._last_gravity: np.ndarray | None = None
        self._on_connect: list = []

    def on_connect(self, callback) -> None:
        """callback(status) is called once, when the first message from a phone arrives."""
        self._on_connect.append(callback)

    def start(self) -> "PhoneStation":
        station = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 (http.server naming)
                if self.path.rstrip("/") != "/data":
                    self.send_response(404)
                    self.end_headers()
                    return
                n = int(self.headers.get("Content-Length", 0))
                try:
                    msg = json.loads(self.rfile.read(n) or b"{}")
                    station.ingest(msg)
                    self.send_response(200)
                except (ValueError, TypeError, KeyError):
                    self.send_response(400)
                self.end_headers()

            def log_message(self, *args):  # keep the console for our own status lines
                pass

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.port = self._server.server_address[1]  # resolves port 0
        self._thread = threading.Thread(target=self._server.serve_forever, name="phone-station", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        super().stop()

    def push_url(self) -> str:
        return f"http://{local_ip()}:{self.port}/data"

    def ingest(self, msg: dict) -> None:
        """Handle one pushed message (public so it can be tested without a network)."""
        payload = msg.get("payload", [])
        if not isinstance(payload, list):
            raise ValueError("payload must be a list")
        first = False
        with self._lock:
            if self._device is None:
                first = True
            self._device = str(msg.get("deviceId", self._device or "unknown"))
            self._session = str(msg.get("sessionId", self._session or ""))
            self._messages += 1
            self._last_rx = time.monotonic()

        gyro_rows = []
        for item in sorted(payload, key=lambda d: d.get("time", 0)):
            name = str(item.get("name", "")).lower()
            t_ns = item.get("time")
            vals = item.get("values")
            if t_ns is None or not isinstance(vals, dict):
                continue
            self._sensors.add(name)
            if self._t0_ns is None:
                self._t0_ns = int(t_ns)
            xyz = _xyz(vals)
            if xyz is None:
                continue
            if name == "totalacceleration":
                self._last_acc = xyz
            elif name == "accelerometer":
                self._last_user_acc = xyz
            elif name == "gravity":
                self._last_gravity = xyz
            elif name == "gyroscope":
                gyro_rows.append(((int(t_ns) - self._t0_ns) / 1e9, xyz))
            acc = self._current_accel()
            while gyro_rows and acc is not None:
                t, g = gyro_rows.pop(0)
                self._emit(ImuSample(t, g, acc.copy()))
        # Gyro samples that arrived before any accelerometer reading are dropped.

        if first:
            st = self.status()
            for cb in self._on_connect:
                cb(st)

    def _current_accel(self) -> np.ndarray | None:
        if self._last_acc is not None:
            return self._last_acc
        if self._last_user_acc is not None and self._last_gravity is not None:
            return self._last_user_acc + self._last_gravity
        return None

    def status(self) -> StationStatus:
        with self._lock:
            ago = None if self._last_rx is None else time.monotonic() - self._last_rx
            ts = list(self._recent_t)
            st = StationStatus(
                source=self.source,
                connected=ago is not None and ago < self.quiet_after_s,
                device=self._device,
                session=self._session,
                samples=self._count,
                messages=self._messages,
                last_seen_s_ago=ago,
                sensors_seen=set(self._sensors),
            )
        if len(ts) >= 3 and ts[-1] > ts[0]:
            st.rate_hz = (len(ts) - 1) / (ts[-1] - ts[0])
        return st


def wait_for_phone(station: PhoneStation, timeout: float, poll: float = 0.2) -> bool:
    """True once the phone has sent at least one message, False after timeout seconds."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if station.status().messages > 0:
            return True
        time.sleep(poll)
    return station.status().messages > 0


def samples_to_imu(samples: list[ImuSample]) -> ImuData:
    """Stack samples into ImuData, dropping any non-increasing timestamps."""
    if not samples:
        raise ValueError("no samples")
    t = np.array([s.t for s in samples])
    keep = np.concatenate([[True], np.diff(t) > 0])
    return ImuData(
        t=t[keep],
        gyro=np.array([s.gyro for s in samples])[keep],
        accel=np.array([s.accel for s in samples])[keep],
    )


def save_as_sensor_logger(imu: ImuData, folder: str | Path, device: str, platform: str = "android") -> Path:
    """Write a stream in Sensor Logger's export layout, so `vortex check --phone` and the phone loader read it."""
    d = Path(folder)
    d.mkdir(parents=True, exist_ok=True)
    epoch_ns = time.time_ns()
    t_ns = (epoch_ns + np.round(imu.t * 1e9)).astype(np.int64)
    for name, xyz in (("Gyroscope.csv", imu.gyro), ("TotalAcceleration.csv", imu.accel)):
        pd.DataFrame({"time": t_ns, "seconds_elapsed": imu.t, "x": xyz[:, 0], "y": xyz[:, 1], "z": xyz[:, 2]}).to_csv(
            d / name, index=False
        )
    pd.DataFrame({"device name": [device], "platform": [platform], "standardisation": ["true"],
                  "recorder": ["vortex station"]}).to_csv(d / "Metadata.csv", index=False)
    return d


def local_ip() -> str:
    """This computer's address on the local network (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _xyz(vals: dict) -> np.ndarray | None:
    try:
        return np.array([float(vals["x"]), float(vals["y"]), float(vals["z"])])
    except (KeyError, TypeError, ValueError):
        return None

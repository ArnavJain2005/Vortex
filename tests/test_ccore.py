"""main.cpp (the C core) against pathfinder.py: number parsing and formatting against Python itself,
parameters, and the same poses on every synthetic scenario of the equivalence tests.

Criterion (as tests/test_core_equivalence.py): position difference < 1e-6 m and quaternion difference
< 1e-7 on every row at full precision, and identical submission-format bytes. All inputs SYNTHETIC.
Skipped when no g++ is on PATH."""

import importlib.util
import math
import os
import random
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from vortex import check_output, degrade
from vortex.data import euroc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import synth_euroc  # noqa: E402
from test_main import MESSY  # noqa: E402
from test_strapdown import _move_rest_move, _moving, _static_rows  # noqa: E402
from test_witness import _profile  # noqa: E402

CXX = shutil.which("g++")
pytestmark = pytest.mark.skipif(CXX is None, reason="no g++ on PATH")
FLAGS = ["-O2", "-std=c++17", "-ffp-contract=off"] + (["-static"] if os.name == "nt" else [])
FULL = b"%s.%s %.17g %.17g %.17g %.17g %.17g %.17g %.17g\n"


def _load_pf():
    spec = importlib.util.spec_from_file_location("vortex_pf_ccore", ROOT / "tools" / "pathfinder_lab.py")  # frozen full copy
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pf = _load_pf()
# Compared with tools/pathfinder_lab.py (the full estimator; equal to pathfinder.py with its experiments off,
# tests/test_lab.py), since the C core still declares the JAM constants that left pathfinder.py on 18 Nov.
# The C core is a recorded experiment frozen before Step F (CLAUDE.md: kept, never extended). It is compared
# with pathfinder.py as it was then: the Step F switches (shipped on since 17 Nov 2026) and the Step 6
# smoother (shipped on since 18 Nov 2026) are set back off in this private copy of the module only.
STEP_F_OFF = ("BGCAP_ON", "P0V_ON", "REFRESH_ON", "RESET_ON", "SMOOTH_ON")
for _name in STEP_F_OFF:
    assert hasattr(pf, _name), _name
    setattr(pf, _name, False)


def _build(src, out):
    p = subprocess.run([CXX, *FLAGS, "-o", str(out), str(src)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return out


@pytest.fixture(scope="module")
def cbin(tmp_path_factory):
    return _build(ROOT / "main.cpp", tmp_path_factory.mktemp("cc") / "vortex.exe")


@pytest.fixture(scope="module")
def selftest(tmp_path_factory):
    return _build(ROOT / "tests" / "ccore_selftest.cpp", tmp_path_factory.mktemp("cc") / "selftest.exe")


def _ask(exe, lines):
    p = subprocess.run([str(exe)], input="\n".join(lines) + "\n", capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.splitlines()


def _bits(x):
    return struct.unpack("<Q", struct.pack("<d", x))[0]


# ---- number routines ----

EDGE = [b"0", b"-0", b"+0.0", b"1", b"1.", b".5", b"-.5", b".", b"", b"  ", b"-", b"+", b"1e", b"e5", b"1e5",
        b"1E-5", b"1e+5", b"1.5e", b"1.5e+", b" 1.5 ", b"\t-2.25\r", b"1.5\r\n", b"1_000.5", b"1__0", b"_1",
        b"1_", b"1._5", b"1.5_", b"1e1_0", b"1e_1", b"0x10", b"1.5.2", b"--1", b"+-1", b"inf", b"-inf", b"+INF",
        b"Infinity", b"-infinity", b"infinit", b"nan", b"-NaN", b"nan(1)", b"in_f", b"1e999", b"-1e999",
        b"1e-400", b"4.9e-324", b"2.2250738585072014e-308", b"2.2250738585072011e-308", b"0.1", b"0.5",
        b"9007199254740993", b"9007199254740992.5", b"123456789012345678901234567890", b"0.0000000000000000000000000001",
        b"1e22", b"1e23", b"8.1476917083333333", b"-0.099134701513277898", b"0.30000000000000004",
        b"1.7976931348623157e308", b"1.7976931348623159e308", b"00000000000000000000001.5", b"1.50000000000000000000000",
        b"1\x002", b"\xc2\xa01", b"1 2", b"12345678901234567890", b"1234567890123456789", b"0.1234567890123456789",
        b"5e-27", b"5e-28", b"7.450580596923828125e-9"]


def _random_fields(rng, n):
    out = []
    for _ in range(n):
        r = rng.random()
        if r < 0.4:                                   # shortest repr of a random double
            x = rng.choice([rng.uniform(-20, 20), rng.uniform(-1, 1) * 10 ** rng.randint(-30, 30),
                            struct.unpack("<d", struct.pack("<Q", rng.getrandbits(64)))[0]])
            out.append(repr(x).encode())
        elif r < 0.8:                                 # random digit strings with a point and maybe an exponent
            nd = rng.randint(1, 24)
            digits = "".join(rng.choice("0123456789") for _ in range(nd))
            pos = rng.randint(0, nd)
            s = rng.choice(["", "-", "+"]) + digits[:pos] + "." + digits[pos:]
            if rng.random() < 0.3:
                s += rng.choice("eE") + rng.choice(["", "-", "+"]) + str(rng.randint(0, 40))
            out.append(s.encode())
        else:                                         # EuRoC-like: 15 to 20 significant digits
            out.append(("%.*f" % (rng.randint(14, 20), rng.uniform(-12, 12))).encode())
    return out


def test_parse_matches_python_float(selftest):
    rng = random.Random(11)
    fields = EDGE + _random_fields(rng, 30000)
    got = _ask(selftest, ["P " + f.hex() for f in fields])
    assert len(got) == len(fields)
    for f, g in zip(fields, got):
        try:
            x = float(f)
        except ValueError:
            assert g == "bad", (f, g)
            continue
        assert g.startswith("ok "), (f, g)
        y = struct.unpack("<d", struct.pack("<Q", int(g[3:], 16)))[0]
        if math.isnan(x):
            assert math.isnan(y), (f, g)
        else:
            assert _bits(y) == _bits(x), (f, x, y)


def _random_doubles(rng, n):
    xs = [0.0, -0.0, 1e12, -1e12, 1e12 + 1, 0.5, 0.0078125, -0.0078125, 0.00000049999999999999999,
          0.0000005, 0.00000005, 0.9999995, 0.99999995, 5e-324, -5e-324, 123456.7890125, 2.5e-7, 1.5e-6]
    for _ in range(n):
        r = rng.random()
        if r < 0.3:
            xs.append(rng.uniform(-30, 30))
        elif r < 0.5:
            xs.append(rng.uniform(-1, 1) * 10 ** rng.randint(-12, 13))
        elif r < 0.8:                                  # exact binary fractions: decimal ties at 6 / 7 places
            xs.append(rng.randint(-2 ** 40, 2 ** 40) / 2 ** rng.randint(0, 30))
        else:
            xs.append(rng.randint(-10 ** 9, 10 ** 9) / 10 ** rng.randint(5, 9))
    return xs


def test_fixed_matches_python_percent(selftest):
    rng = random.Random(12)
    xs = _random_doubles(rng, 30000)
    reqs = []
    for x in xs:
        for d in (6, 7):
            reqs.append("F %016x %d" % (_bits(x), d))
    got = _ask(selftest, reqs)
    k = 0
    for x in xs:
        for d in (6, 7):
            assert got[k] == "%.*f" % (d, x), (x, d, got[k])
            k += 1


# ---- parameters ----

def test_parameters_match_pathfinder():
    src = (ROOT / "main.cpp").read_text(encoding="utf-8")
    consts = dict(re.findall(r"^static const (?:double|int) ([A-Z0-9_]+) = ([^;]+);", src, re.M))
    assert len(consts) >= 40
    for name, expr in consts.items():
        value = getattr(pf, expr) if expr in consts else float(expr)
        assert hasattr(pf, name), name
        assert getattr(pf, name) == value, (name, getattr(pf, name), value)
    assert int(re.search(r"enum \{ N = (\d+) \}", src).group(1)) == pf.N
    block = re.search(r"^// (CAL_NOISE_ON = .*\n// .*)$", src, re.M).group(1)
    switches = re.findall(r"([A-Z0-9_]+) = (True|False)", block)
    assert len(switches) == 9
    for name, value in switches:
        assert getattr(pf, name) is (value == "True"), name


# ---- poses ----

def _compare(cbin, src, tmp_path):
    """C core vs pathfinder.py on one input file; returns (dp, dq)."""
    a, b, c, d = (tmp_path / x for x in ("py_full.txt", "c_full.txt", "py.txt", "c.txt"))
    fmt = pf.FMT
    try:
        pf.FMT = FULL
        n = pf.run(str(src), str(a))
    finally:
        pf.FMT = fmt
    pf.run(str(src), str(c))
    for out, extra in ((b, ["--full"]), (d, [])):
        p = subprocess.run([str(cbin), str(src), str(out)] + extra, capture_output=True, text=True)
        assert p.returncode == 0 and p.stderr == "", p.stderr
    assert c.read_bytes() == d.read_bytes()
    la, lb = a.read_text().splitlines(), b.read_text().splitlines()
    assert len(la) == len(lb) == n
    if n == 0:
        return 0.0, 0.0
    assert [x.split()[0] for x in la] == [x.split()[0] for x in lb]
    ga = np.array([[float(v) for v in x.split()[1:]] for x in la])
    gb = np.array([[float(v) for v in x.split()[1:]] for x in lb])
    dp, dq = np.abs(ga[:, :3] - gb[:, :3]).max(), np.abs(ga[:, 3:] - gb[:, 3:]).max()
    assert dp < 1e-6 and dq < 1e-7, (dp, dq)
    assert check_output.check(src, d)["ok"]
    return dp, dq


def _write_rows(path, rows):
    with open(path, "w", newline="\n") as f:
        f.write(euroc.HEADER + "\n")
        for t, v in rows:
            f.write("%s,%s\n" % ("bad" if t is None else t, ",".join(repr(float(x)) for x in v)))
    return path


def test_messy_file(cbin, tmp_path):
    src = tmp_path / "imu.csv"
    src.write_bytes(MESSY)
    _compare(cbin, src, tmp_path)


def test_header_only_and_empty(cbin, tmp_path):
    src = tmp_path / "imu.csv"
    src.write_text(euroc.HEADER + "\n")
    _compare(cbin, src, tmp_path)
    src.write_bytes(b"")
    _compare(cbin, src, tmp_path)


@pytest.mark.parametrize("crlf", [False, True])
def test_random_synthetic_file(cbin, tmp_path, crlf):
    src = synth_euroc.write(tmp_path / "imu.csv", rows=6000, seed=0, crlf=crlf)
    _compare(cbin, src, tmp_path)


@pytest.mark.parametrize("mode, failure, nan_text", [("nan", "nan", ""), ("missing", "zero", "nan"),
                                                     ("nan", "stuck", "nan")])
def test_degraded_synthetic_file(cbin, tmp_path, mode, failure, nan_text):
    clean = synth_euroc.write(tmp_path / "clean.csv", rows=12000, seed=0)
    raw, _ = degrade.degrade(euroc.read_imu_csv(clean),
                             degrade.DegradeConfig(dropout_mode=mode, failure_mode=failure, healthy_s=5.0,
                                                   dropout_count=2, duplicate_rows=3, swap_rows=3), seed=5)
    src = tmp_path / "deg.csv"
    euroc.write_imu_csv(raw, src, nan_text=nan_text)
    _compare(cbin, src, tmp_path)


def test_physical_motion_with_still_start(cbin, tmp_path):
    rows, _, _ = _moving(seconds=20.0)
    still = _static_rows(2.0, np.eye(3), bias=(0.002, -0.001, 0.0005))
    shift = still[-1][0] + 5_000_000 - rows[0][0]
    src = _write_rows(tmp_path / "imu.csv", still + [(t + shift, v) for t, v in rows])
    _compare(cbin, src, tmp_path)


def test_move_rest_move_backward_pass(cbin, tmp_path):
    rows, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.002, acc_noise=0.02, seed=3)
    nan = float("nan")
    rows = list(rows)
    rows.insert(300, (None, rows[300][1]))
    rows.insert(500, (rows[499][0], rows[499][1]))
    rows.insert(700, (rows[699][0] + 2_500_000, (nan,) * 6))
    rows.insert(900, (rows[899][0] - 10**9, rows[899][1]))
    rows = rows[:1200] + [(t + 300_000_000, v) for t, v in rows[1200:]]
    src = _write_rows(tmp_path / "imu.csv", rows)
    _compare(cbin, src, tmp_path)
    assert pf.LAST["calibrated"] and pf.LAST["pre_rows"] > 1000


def test_pre_segment_cap_fallback(cbin, tmp_path):
    """SYNTHETIC, 400 Hz: tumbling for 45 s (18,000 rows, above PRE_MAX_ROWS), a 5 s rest, motion."""
    rng = random.Random(9)
    t = synth_euroc.T0_NS
    rows = []
    for i in range(18000 + 2000 + 4000):
        r = rng.random
        if 18000 <= i < 20000:
            v = (0.002 + 0.001 * (r() - 0.5), -0.001, 0.003, 0.01 * (r() - 0.5), 0.01 * (r() - 0.5), 9.81)
        else:
            ph = (i % 800) / 400.0 - 1.0
            v = (0.3 * ph, -0.2 * ph, 0.1 * ph, 9.3 + 0.8 * ph, -0.4 + 0.5 * ph, -2.4 + 0.3 * (r() - 0.5))
        rows.append((t, v))
        t += 2_500_000
    src = _write_rows(tmp_path / "imu.csv", rows)
    _compare(cbin, src, tmp_path)
    assert not pf.LAST["calibrated"] and pf.LAST["pre_rows"] == 0


def _rows_profile(*a, **k):
    rows, _, _ = _profile(*a, **k)
    return list(rows)


def test_witnesses_fire(cbin, tmp_path):
    rows = _rows_profile(46.0, [(8, 10, -1), (24, 26, +1), (34, 36, -1)], bias_step_s=25.0,
                         gyro_step=(0.0, 0.0, 0.01), acc_step=(0.08, -0.06, 0.0))
    _compare(cbin, _write_rows(tmp_path / "imu.csv", rows), tmp_path)
    assert pf.LAST["zupt_ticks"] > 30


def test_noise_gaps_dead_sensors(cbin, tmp_path):
    rows = _rows_profile(40.0, [(8, 10, -1), (22, 24, +1)], gyro_noise=0.03, acc_noise=0.4, seed=7)
    nan = float("nan")
    rows[5000:5400] = [(t, (nan,) * 6) for t, _ in rows[5000:5400]]
    g = rows[5999][1][:3]
    rows[6000:6100] = [(t, g + v[3:]) for t, v in rows[6000:6100]]
    rows[6500:6502] = [(t, v[:3] + (0.0, 0.0, 0.0)) for t, v in rows[6500:6502]]
    rows = rows[:6800] + rows[7200:]                                      # a 2 s hole with no rows
    rows[7000:] = [(t, rows[6999][1]) for t, _ in rows[7000:]]            # stuck failure
    _compare(cbin, _write_rows(tmp_path / "imu.csv", rows), tmp_path)
    assert pf.LAST["tilt2"] > 0.0


def test_denoised_calibration(cbin, tmp_path):
    rows, _, _ = _move_rest_move(bias=(0.01, -0.02, 0.08), gyro_noise=0.03, acc_noise=0.15, seed=4)
    rows = list(rows)
    rows[2500:2510] = [(t, (float("nan"),) * 6) for t, _ in rows[2500:2510]]
    rows.insert(3000, rows[2999])
    _compare(cbin, _write_rows(tmp_path / "imu.csv", rows), tmp_path)
    assert pf.LAST["calibrated"]


def test_odd_fields(cbin, tmp_path):
    """Underscores, inf, padded and zero-led timestamps, BOM, extra and missing columns, CR line ends.
    (Timestamps above 9.2e18 ns are a documented difference, so none here.)"""
    lines = [b"\xef\xbb\xbf# header", b"1403636579758555392,1_0e-3,0.002,-0.003,9.8_1,0.01,-0.02",
             b"1403636579763555584 ,0.001,inf,0.003,9.81,0.0,0.0", b"\t1403636579768555520,0.001,0.002,0.003,9.81",
             b"1403636579773555456,0.001,0.002,0.003,9.81,0.01,-0.02,extra,more",
             b"000001403636579778555392,0.001,0.002,0.003,9.81,0.01,-0.02",
             b"1403636579783555328,0.001,0.002,0.003,9.81,0.01,-0.02\r",
             b"1403636579788555392,0x1,0.002,0.003,9.81,0.01,-0.02", b"   ", b"",
             b"1403636579793555200,+.5e-2,-0.,0.003,9.81,1E-2,-2e-2"]
    src = tmp_path / "imu.csv"
    src.write_bytes(b"\n".join(lines))
    _compare(cbin, src, tmp_path)


# ---- command line ----

def test_cli_errors(cbin, tmp_path):
    p = subprocess.run([str(cbin)], capture_output=True, text=True)
    assert p.returncode == 2 and "usage" in p.stderr.lower()
    out = tmp_path / "o.txt"
    p = subprocess.run([str(cbin), str(tmp_path / "nope.csv"), str(out)], capture_output=True, text=True)
    assert p.returncode == 1 and "nope.csv" in p.stderr and not out.exists()

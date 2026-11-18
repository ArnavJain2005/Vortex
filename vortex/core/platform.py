"""Step 7: platform detection (multirotor or hand-held) from the accelerometer spectrum. No ground truth.

A multirotor in flight shakes its IMU with rotor vibration: the accelerometer has strong power near the
Nyquist frequency, which the second difference a[k] - 2 a[k-1] + a[k-2] picks out (its gain is 4 at Nyquist
and about (2 pi f dt)^2 at low frequency f). A hand-held device moves at walking and hand frequencies
(1 to 3 Hz), where the second difference is almost zero. Per window of PLAT_WIN_NS (1 s, from the first
valid row) the statistic is the mean over the window's terms and the three axes of the squared second
difference, (m/s^2)^2; the file's statistic is the PLAT_Q quantile over windows (the whole file: EuRoC flights
start with the drone carried by hand, so the opening seconds look hand-held). Hand-held when it is below
PLAT_HF. Rows that are invalid (NaN, inf, absurd) or all-zero accelerometer (the official script's blind
window) end the difference chain, as does a new window.

Tuning (EXPLORATORY, Docs/TRACK3_PLAN.md Step 7): clean and official copies (seeds 1-3, readings a, b) of
MH_01/02 and TUM-VI room1/2. Flight windows about 5.2 to 6 (m/s^2)^2; hand-held below 0.002 clean and at
most about 0.18 in the last 30 s of reading b (the noisiest part of the noisiest copy). PLAT_HF = 1.0 is
about the geometric mean of the two.
"""

from __future__ import annotations

from . import strapdown as sd

PLATFORM_ON = False          # Step 7: hand-held envelope (HH_*) when the detector says hand-held
PLAT_WIN_NS = 1000000000     # ns, window length
PLAT_Q = 0.75                # quantile of the window statistics
PLAT_HF = 1.0                # (m/s^2)^2: below this the file is hand-held
PLAT_MIN_TERMS = 100         # second differences a window needs to count (half a second at 200 Hz)
# Hand-held envelope (used instead of witness.V2_SIGMA_* / V2P_* when PLATFORM_ON and the file is hand-held),
# chosen on TUM-VI room1/room2 (clean and official copies seeds 1-3, EXPLORATORY one-factor sweep then a
# small second round, Docs/TRACK3_PLAN.md Step 7): a person walking in a room, not a drone in a hall.
HH_V2_SIGMA_H = 0.5          # m/s, horizontal speed envelope (drone: 2.0)
HH_V2_SIGMA_V = 0.3          # m/s, vertical (unchanged; 0.1 was worse)
HH_V2P_SIGMA_H = 1.0         # m, volume envelope around the running centre (drone: 5.0)
HH_V2P_SIGMA_V = 0.3         # m (drone: 2.0)
HH_V2P_TAU = 30.0            # s, running-centre time constant (drone: 10; 3 was much worse)


def hf_stat(rows):
    """rows: (t_ns or None, six values). Returns the PLAT_Q quantile of the window statistics, or None if
    no window has PLAT_MIN_TERMS terms."""
    es = []
    t0 = None
    k_cur = None
    s = 0.0
    n = 0
    a1 = a2 = None
    for t, v in rows:
        if t is None or v is None or not sd.is_valid(v) or (v[3] == 0.0 and v[4] == 0.0 and v[5] == 0.0):
            a1 = a2 = None
            continue
        if t0 is None:
            t0 = t
        k = (t - t0) // PLAT_WIN_NS
        if k != k_cur:
            if n >= PLAT_MIN_TERMS:
                es.append(s / (3.0 * n))
            k_cur = k
            s = 0.0
            n = 0
            a1 = a2 = None
        x, y, z = v[3], v[4], v[5]
        if a2 is not None:
            d0 = x - 2.0 * a1[0] + a2[0]
            d1 = y - 2.0 * a1[1] + a2[1]
            d2 = z - 2.0 * a1[2] + a2[2]
            s += d0 * d0 + d1 * d1 + d2 * d2
            n += 1
        a2 = a1
        a1 = (x, y, z)
    if n >= PLAT_MIN_TERMS:
        es.append(s / (3.0 * n))
    if not es:
        return None
    es.sort()
    return es[int(PLAT_Q * (len(es) - 1))]


def is_handheld(stat):
    """None (no usable window) counts as multirotor: the shipped behaviour."""
    return stat is not None and stat < PLAT_HF

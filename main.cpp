// Vortex, Samsung PRISM XR Hackathon 2026, Track 3: trajectory from a degraded IMU. C core.
//
//   g++ -O2 -std=c++17 -ffp-contract=off -o vortex main.cpp     (Windows MinGW: add -static)
//   ./vortex <imu0/data.csv> <estimated_trajectory.txt>
//
// A line-by-line port of pathfinder.py (the Python estimator that main.py runs) with the shipped
// switch settings: same passes, same row rules, same arithmetic order, so the two agree to rounding
// (tests/test_ccore.py). C-style C++, standard library only, single thread, offline, deterministic;
// static buffers only, no heap allocation of our own. Double precision, no -ffast-math (it would break
// the NaN checks); -ffp-contract=off keeps a*b+c from being fused, as Python never fuses.
//
// Passes: (1) calibration scan of the first 60 s (and, only when no strict still run exists, a second
// scan with the white noise removed); (2) rows before the calibration anchor are stored (64 bytes per
// row, at most PRE_MAX_ROWS) and integrated backward for their attitude; (3) one streaming forward pass
// (error-state Kalman filter, 15 states, one covariance step per 0.25 s tick) writes every row.
// Rules and their sources: vortex/core/witness.py and vortex/core/strapdown.py.
//
// Known differences from pathfinder.py, on inputs EuRoC and TUM-VI never contain: a timestamp above
// 9.2e18 ns is copied to the output but not integrated (Python integers have no limit); a line longer
// than LINE_CAP bytes is cut there.
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

typedef long long i64;

// ---- estimator parameters: identical to pathfinder.py (tests/test_ccore.py checks) ----
static const double INIT_S = 1.0;
static const int INIT_MAX_ROWS = 2000;
static const double STILL_GYRO_STD = 0.02;
static const double STILL_ACC_STD = 0.1;
static const double G_DEFAULT = 9.81;
static const double MAX_DT = 0.1;
static const double MAX_JUMP_S = 30.0;
static const double MAX_SUMSQ = 1e8;
static const double CAL_HORIZON_S = 60.0;
static const double BLOCK_S = 0.25;
static const int BLOCK_MIN_ROWS = 5;
static const double MIN_STILL_S = 1.0;
static const double STUCK_STD = 1e-5;
static const double ACC_NORM_MIN = 8.8;
static const double ACC_NORM_MAX = 10.8;
static const double STEADY_GYRO = 0.005;
static const double STEADY_ACC = 0.05;
static const double TRIM_S = 0.5;
static const int PRE_MAX_ROWS = 15000;
static const double TICK_S = BLOCK_S;
static const double GYRO_NOISE = 1.7e-3;
static const double ACC_NOISE = 2.0e-2;
static const double GYRO_WALK = 1.9e-4;
static const double ACC_WALK = 3.0e-3;
static const double P0_VEL = 0.01;
static const double P0_TILT = 0.02;
static const double P0_YAW = 0.0;
static const double P0_BG = 2e-3;
static const double P0_BA = 0.2;
static const double P0_TILT_FALLBACK = 0.1;
static const double P0_BG_FALLBACK = 0.02;
static const double ZUPT_SIGMA = 0.02;
static const double ZARU_SIGMA_MIN = 5e-4;
static const double V2_SIGMA_H = 2.0;
static const double V2_SIGMA_V = 0.3;
static const double V2P_SIGMA_H = 5.0;
static const double V2P_SIGMA_V = 2.0;
static const double V2P_TAU = 10.0;
static const int GAP_H_TICKS = 8;
static const double GAP_TAU = 20.0;
static const int STUCK_ROWS = 5;
static const double FC_TAU = 0.5;
// Switches: the port implements exactly these shipped settings (a test checks pathfinder.py's).
// CAL_NOISE_ON = True, V1_ON = True, V2_ON = True, V2P_ON = True, JAM_ON = False, GAP_ON = True,
// DEAD_ON = True, FC_ON = True, PRE_HOLD = True
enum { N = 15 };

// ---- input: buffered line reader over static memory ----
static const size_t READ_BUF = 1 << 16;
static const size_t LINE_CAP = 1 << 16;

struct Reader {
    FILE* f;
    size_t pos, len;
    bool eof;
    unsigned char buf[READ_BUF];
};

static Reader RD;
static unsigned char LINE[LINE_CAP + 1];
static char FBUF[LINE_CAP + 1];      // one numeric field without underscores, for strtod
static char OUTBUF[1 << 16];
static char SEC[LINE_CAP + 1] = "0";
static size_t SECLEN = 1;
static char FRAC[LINE_CAP + 1] = "000000000";
static char OLINE[LINE_CAP + 256];                   // one output line
static const char* g_err_path = 0;

static bool rd_fill(Reader& r) {
    if (r.eof) return false;
    r.len = fread(r.buf, 1, READ_BUF, r.f);
    r.pos = 0;
    if (r.len == 0) r.eof = true;
    return r.len > 0;
}

static bool rd_open(Reader& r, const char* path) {
    r.f = fopen(path, "rb");
    if (!r.f) {
        g_err_path = path;
        return false;
    }
    setvbuf(r.f, 0, _IONBF, 0);      // our own buffer is the only one
    r.eof = false;
    r.pos = r.len = 0;
    rd_fill(r);
    if (r.len >= 3 && r.buf[0] == 0xEF && r.buf[1] == 0xBB && r.buf[2] == 0xBF) r.pos = 3;
    return true;
}

static void rd_close(Reader& r) {
    if (r.f) fclose(r.f);
    r.f = 0;
}

// Next line without its '\n' (Python iterates binary files on '\n'). Returns false at end of file.
static bool rd_line(Reader& r, size_t* n) {
    size_t k = 0;
    bool any = false;
    for (;;) {
        if (r.pos >= r.len && !rd_fill(r)) return any;
        any = true;
        unsigned char* s = r.buf + r.pos;
        size_t avail = r.len - r.pos;
        unsigned char* nl = (unsigned char*)memchr(s, '\n', avail);
        size_t take = nl ? (size_t)(nl - s) : avail;
        size_t room = LINE_CAP - k;
        memcpy(LINE + k, s, take < room ? take : room);
        k += take < room ? take : room;
        if (nl) {
            r.pos += take + 1;
            *n = k;
            return true;
        }
        r.pos = r.len;
        *n = k;
    }
}

// ---- row rules (vortex/rowspec.py, pathfinder._parse) ----
static inline bool is_ws(unsigned char c) {
    return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\v' || c == '\f';
}
static inline bool is_dig(unsigned char c) { return c >= '0' && c <= '9'; }

static bool all_digits(const unsigned char* s, size_t n) {
    if (n == 0) return false;
    for (size_t i = 0; i < n; i++)
        if (!is_dig(s[i])) return false;
    return true;
}

static bool ci_eq(const unsigned char* s, const char* w, size_t n) {
    for (size_t i = 0; i < n; i++) {
        unsigned char c = s[i];
        if (c >= 'A' && c <= 'Z') c = (unsigned char)(c - 'A' + 'a');
        if (c != (unsigned char)w[i]) return false;
    }
    return true;
}

// ---- exact decimal <-> double without the C library (the Windows C library's strtod and printf
// cost about 5 and 4 us per row). Both round correctly (to nearest, ties to even, on the exact
// value), as Python's float() and %-formatting do; anything outside their range goes to the C library.
// tests/test_ccore.py checks both against Python on random and real inputs. ----
#if defined(__SIZEOF_INT128__)
typedef unsigned __int128 u128;
static const unsigned long long P10[20] = {
    1ULL, 10ULL, 100ULL, 1000ULL, 10000ULL, 100000ULL, 1000000ULL, 10000000ULL, 100000000ULL,
    1000000000ULL, 10000000000ULL, 100000000000ULL, 1000000000000ULL, 10000000000000ULL,
    100000000000000ULL, 1000000000000000ULL, 10000000000000000ULL, 100000000000000000ULL,
    1000000000000000000ULL, 10000000000000000000ULL};

static inline int clz128(u128 x) {
    unsigned long long hi = (unsigned long long)(x >> 64);
    return hi ? __builtin_clzll(hi) : 64 + __builtin_clzll((unsigned long long)x);
}

// s[0..n): [sign] digits [. digits] [(e|E) [sign] digits], already validated. False: use strtod.
static bool fast_dec(const char* s, size_t n, double* out) {
    size_t i = 0;
    bool neg = false;
    if (s[i] == '+' || s[i] == '-') neg = s[i++] == '-';
    unsigned long long m = 0;
    int nd = 0, k = 0, zeros = 0;                    // significant digits, decimal exponent, pending 0s
    bool frac = false;
    for (; i < n && s[i] != 'e' && s[i] != 'E'; i++) {
        if (s[i] == '.') { frac = true; continue; }
        unsigned d = (unsigned)(s[i] - '0');
        if (frac) k--;
        if (d == 0) {
            if (nd) zeros++;                         // trailing zeros are kept only if a digit follows
            continue;
        }
        if (nd + zeros + 1 > 19) return false;
        for (; zeros; zeros--) { m *= 10ULL; nd++; }
        m = m * 10ULL + d;
        nd++;
    }
    k += zeros;                                      // dropped trailing zeros scale the exponent
    if (i < n) {                                     // exponent
        i++;
        bool eneg = false;
        if (s[i] == '+' || s[i] == '-') eneg = s[i++] == '-';
        long e = 0;
        for (; i < n; i++) {
            e = e * 10 + (s[i] - '0');
            if (e > 100000) return false;
        }
        k += (int)(eneg ? -e : e);
    }
    if (m == 0) {
        *out = neg ? -0.0 : 0.0;
        return true;
    }
    if (k >= 0) {
        if (k > 19 - nd) return false;               // m * 10^k < 10^19 < 2^64: exact
        unsigned long long x = m * P10[k];
        if (x >> 53) return false;                   // more than 53 bits: leave the rounding to strtod
        *out = neg ? -(double)x : (double)x;
        return true;
    }
    int j = -k;
    if (j > 27) return false;                        // 5^27 < 2^63
    unsigned long long five = 1;
    for (int t = 0; t < j; t++) five *= 5ULL;
    int lz = __builtin_clzll(m);
    u128 num = (u128)m << (lz + 64);                 // top bit at 127
    u128 q = num / five;                             // value = (q + r / five) * 2^-(lz + 64 + j)
    bool sticky = (num - q * five) != 0;
    int bits = 128 - clz128(q);                      // 65..126
    int sh = bits - 53;
    unsigned long long mant = (unsigned long long)(q >> sh);
    u128 rem = q & ((((u128)1) << sh) - 1);
    u128 half = ((u128)1) << (sh - 1);
    if (rem > half || (rem == half && (sticky || (mant & 1ULL)))) mant++;
    if (mant >> 53) { mant >>= 1; sh++; }
    int e2 = sh - (lz + 64) - j;                     // value = mant * 2^e2
    if (e2 + 52 < -1022) return false;               // subnormal: leave it to strtod
    double v = ldexp((double)mant, e2);
    *out = neg ? -v : v;
    return true;
}

// x with d decimals (6 or 7) as printf("%.*f") prints it. Returns the length, 0 outside |x| <= 1e12.
static int fast_fixed(char* o, double x, int d) {
    if (!(x <= 1e12 && x >= -1e12)) return 0;        // also NaN
    unsigned long long b;
    memcpy(&b, &x, 8);
    bool neg = (b >> 63) != 0;
    int ex = (int)((b >> 52) & 0x7FF);
    unsigned long long m = b & ((1ULL << 52) - 1);
    int e;
    if (ex == 0) e = -1074;
    else { m |= 1ULL << 52; e = ex - 1075; }
    u128 prod = (u128)m * P10[d];                    // value * 10^d = prod * 2^e
    unsigned long long v;
    if (e >= 0) {
        v = (unsigned long long)(prod << e);
    } else if (-e >= 128) {
        v = 0;
    } else {
        int sh = -e;
        u128 q = prod >> sh;
        u128 rem = prod - (q << sh);
        u128 half = ((u128)1) << (sh - 1);
        if (rem > half || (rem == half && (q & 1))) q++;
        v = (unsigned long long)q;                   // < 1e19
    }
    unsigned long long ip = v / P10[d], fp = v % P10[d];
    int n = 0;
    if (neg) o[n++] = '-';
    char tmp[24];
    int t = 0;
    do { tmp[t++] = (char)('0' + ip % 10); ip /= 10; } while (ip);
    while (t) o[n++] = tmp[--t];
    o[n++] = '.';
    for (int i = d - 1; i >= 0; i--) { o[n + i] = (char)('0' + fp % 10); fp /= 10; }
    return n + d;
}
#else
static bool fast_dec(const char*, size_t, double*) { return false; }
static int fast_fixed(char*, double, int) { return 0; }
#endif

// Python float() of a bytes field: surrounding whitespace, sign, inf / infinity / nan, decimal with
// optional exponent, single underscores between digits. Anything else is invalid (pathfinder then
// uses NaN for that field).
static bool py_float(const unsigned char* s, size_t n, double* out) {
    size_t a = 0, b = n;
    while (a < b && is_ws(s[a])) a++;
    while (b > a && is_ws(s[b - 1])) b--;
    if (a == b) return false;
    size_t i = a, k = 0;
    bool neg = false;
    if (s[i] == '+' || s[i] == '-') {
        neg = s[i] == '-';
        FBUF[k++] = (char)s[i++];
    }
    size_t rest = b - i;
    if ((rest == 3 && ci_eq(s + i, "inf", 3)) || (rest == 8 && ci_eq(s + i, "infinity", 8))) {
        *out = neg ? -HUGE_VAL : HUGE_VAL;
        return true;
    }
    if (rest == 3 && ci_eq(s + i, "nan", 3)) {
        *out = neg ? -NAN : NAN;
        return true;
    }
    bool digits = false;
    for (int part = 0; part < 2; part++) {          // integer part, then fraction
        if (part == 1) {
            if (i < b && s[i] == '.') FBUF[k++] = (char)s[i++];
            else break;
        }
        while (i < b) {
            if (is_dig(s[i])) {
                FBUF[k++] = (char)s[i++];
                digits = true;
            } else if (s[i] == '_' && i > a && is_dig(s[i - 1]) && i + 1 < b && is_dig(s[i + 1])) {
                i++;
            } else {
                break;
            }
        }
    }
    if (!digits) return false;
    if (i < b && (s[i] == 'e' || s[i] == 'E')) {
        FBUF[k++] = (char)s[i++];
        if (i < b && (s[i] == '+' || s[i] == '-')) FBUF[k++] = (char)s[i++];
        bool ed = false;
        while (i < b) {
            if (is_dig(s[i])) {
                FBUF[k++] = (char)s[i++];
                ed = true;
            } else if (s[i] == '_' && is_dig(s[i - 1]) && i + 1 < b && is_dig(s[i + 1])) {
                i++;
            } else {
                break;
            }
        }
        if (!ed) return false;
    }
    if (i != b) return false;
    FBUF[k] = 0;
    if (!fast_dec(FBUF, k, out)) *out = strtod(FBUF, 0);
    return true;
}

struct Row {
    bool tok;                // timestamp field is all digits (after stripping)
    bool tint;               // ... and fits in 64 bits (integrated)
    i64 t;
    const unsigned char* ts;
    size_t tslen;
    double v[6];
};

static size_t FS[7], FE[7];

// One line -> false (not a data row: blank or '#') or a data row. values=false: timestamp only.
static bool parse_row(size_t n, Row& r, bool values) {
    size_t a = 0, b = n;
    if (n == 0 || LINE[0] < 48) {                    // pathfinder: line[0] < 48 -> strip
        while (a < b && is_ws(LINE[a])) a++;
        while (b > a && is_ws(LINE[b - 1])) b--;
        if (a == b || LINE[a] == '#') return false;
    }
    int nf = 0;
    size_t s = a;
    for (size_t i = a; nf < 7; i++) {
        if (i == b || LINE[i] == ',') {
            FS[nf] = s;
            FE[nf] = i;
            nf++;
            if (i == b) break;
            s = i + 1;
        }
    }
    const unsigned char* ts = LINE + FS[0];
    size_t tl = FE[0] - FS[0];
    if (!all_digits(ts, tl)) {
        while (tl && is_ws(*ts)) { ts++; tl--; }
        while (tl && is_ws(ts[tl - 1])) tl--;
    }
    r.tok = all_digits(ts, tl);
    r.tint = false;
    r.ts = ts;
    r.tslen = tl;
    if (r.tok) {
        unsigned long long x = 0;
        bool fits = true;
        for (size_t i = 0; i < tl; i++) {
            unsigned d = (unsigned)(ts[i] - '0');
            if (x > (9223372036854775807ULL - d) / 10ULL) { fits = false; break; }
            x = x * 10ULL + d;
        }
        r.tint = fits;
        r.t = fits ? (i64)x : -1;
    }
    if (values) {
        for (int k = 1; k <= 6; k++) {
            double x;
            if (k < nf && py_float(LINE + FS[k], FE[k] - FS[k], &x)) r.v[k - 1] = x;
            else r.v[k - 1] = NAN;
        }
    }
    return true;
}

static inline bool valid6(const double* v) {
    return v[0] * v[0] + v[1] * v[1] + v[2] * v[2] + v[3] * v[3] + v[4] * v[4] + v[5] * v[5] < MAX_SUMSQ;
}

static inline double max3(double a, double b, double c) {
    double m = a;
    if (b > m) m = b;
    if (c > m) m = c;
    return m;
}

// ---- pass 1: calibration (pathfinder._calibrate, _best_run, _still_denoised, _tilt) ----
enum { NB = 240 };                                  // int(CAL_HORIZON_S / BLOCK_S)
static int CN[NB], ND[NB];
static double CS[6 * NB], CSS[6 * NB], D2[6 * NB], WV[6 * NB];
static bool STILL[NB];

static void best_run(const bool* still, const double* w, int* bj, int* bl) {
    int best_j = 0, best_len = 0, j0 = -1;
    for (int j = 0; j <= NB; j++) {
        bool st = j < NB && still[j];
        bool steady = true;
        if (st && j0 >= 0) {
            int oa = 6 * (j - 1), ob = 6 * j;
            for (int i = 0; i < 6; i++) {
                double tol = i < 3 ? STEADY_GYRO : STEADY_ACC;
                if (w) tol += 3.0 * sqrt(w[oa + i] / CN[j - 1] + w[ob + i] / CN[j]);
                double d = CS[oa + i] / CN[j - 1] - CS[ob + i] / CN[j];
                if (d >= tol || d <= -tol) {
                    steady = false;
                    break;
                }
            }
        }
        if (st && j0 >= 0 && !steady) {
            if (j - j0 > best_len) { best_j = j0; best_len = j - j0; }
            j0 = j;
        } else if (st && j0 < 0) {
            j0 = j;
        }
        if (!st && j0 >= 0) {
            if (j - j0 > best_len) { best_j = j0; best_len = j - j0; }
            j0 = -1;
        }
    }
    *bj = best_j;
    *bl = best_len;
}

static bool still_denoised(const char* src, i64 t0) {
    const i64 bns = (i64)(BLOCK_S * 1e9);
    const i64 t_end = t0 + NB * bns;
    const double max_dt_ns = MAX_DT * 1e9;
    for (int j = 0; j < NB; j++) ND[j] = 0;
    for (int i = 0; i < 6 * NB; i++) D2[i] = 0.0;
    double h1[6], h2[6];
    bool has1 = false, has2 = false;
    i64 jl = -1, tl = -1;
    if (!rd_open(RD, src)) return false;
    size_t n;
    Row r;
    while (rd_line(RD, &n)) {
        if (!parse_row(n, r, true)) continue;
        if (!r.tint || !valid6(r.v) || r.t < t0) {
            has1 = has2 = false;
            continue;
        }
        i64 t = r.t;
        if (t >= t_end) break;
        i64 j = (t - t0) / bns;
        if (has1 && (j != jl || !(0 < t - tl && (double)(t - tl) <= max_dt_ns))) has1 = has2 = false;
        if (has2) {
            ND[j] += 1;
            int o = 6 * (int)j;
            for (int i = 0; i < 6; i++) {
                double d = r.v[i] - 2.0 * h1[i] + h2[i];
                D2[o + i] += d * d;
            }
        }
        has2 = has1;
        for (int i = 0; i < 6; i++) h2[i] = h1[i];
        has1 = true;
        for (int i = 0; i < 6; i++) h1[i] = r.v[i];
        jl = j;
        tl = t;
    }
    rd_close(RD);
    for (int j = 0; j < NB; j++)
        for (int i = 0; i < 6; i++) WV[6 * j + i] = ND[j] ? D2[6 * j + i] / ND[j] / 6.0 : 0.0;
    for (int j = 0; j < NB; j++) {
        STILL[j] = false;
        if (CN[j] < BLOCK_MIN_ROWS || ND[j] < BLOCK_MIN_ROWS - 2) continue;
        int o = 6 * j;
        double ex[6];
        double raw = 0.0;
        for (int i = 0; i < 6; i++) {
            double m = CS[o + i] / CN[j];
            double var = CSS[o + i] / CN[j] - m * m;
            if (var > raw) raw = var;
            var -= D2[o + i] / ND[j] / 6.0;
            ex[i] = var > 0.0 ? sqrt(var) : 0.0;
        }
        if (max3(ex[0], ex[1], ex[2]) >= STILL_GYRO_STD || max3(ex[3], ex[4], ex[5]) >= STILL_ACC_STD) continue;
        if (raw <= STUCK_STD * STUCK_STD) continue;
        double fx = CS[o + 3] / CN[j], fy = CS[o + 4] / CN[j], fz = CS[o + 5] / CN[j];
        double fn = sqrt(fx * fx + fy * fy + fz * fz);
        STILL[j] = ACC_NORM_MIN <= fn && fn <= ACC_NORM_MAX;
    }
    return true;
}

struct Init {
    double qw, qx, qy, qz, bgx, bgy, bgz, g;
    bool still;
};

static void tilt(double fx, double fy, double fz, Init& o) {
    double fn = sqrt(fx * fx + fy * fy + fz * fz);
    double ux = fx / fn, uy = fy / fn, uz = fz / fn;
    o.g = fn;
    if (1.0 + uz < 1e-9) {
        o.qw = 0.0; o.qx = 1.0; o.qy = 0.0; o.qz = 0.0;
        return;
    }
    double w = 1.0 + uz, x = uy, y = -ux;
    double k = 1.0 / sqrt(w * w + x * x + y * y);
    o.qw = w * k; o.qx = x * k; o.qy = y * k; o.qz = 0.0;
}

// 1 = calibrated (cal, t_anchor set), 0 = no usable still run, -1 = input cannot be opened.
static int calibrate(const char* src, Init& cal, i64* t_anchor) {
    const i64 bns = (i64)(BLOCK_S * 1e9);
    for (int j = 0; j < NB; j++) CN[j] = 0;
    for (int i = 0; i < 6 * NB; i++) CS[i] = CSS[i] = 0.0;
    bool have_t0 = false;
    i64 t0 = 0, t_end = 0;
    if (!rd_open(RD, src)) return -1;
    size_t n;
    Row r;
    while (rd_line(RD, &n)) {
        if (!parse_row(n, r, true)) continue;
        if (!r.tint || !valid6(r.v)) continue;
        i64 t = r.t;
        if (!have_t0) {
            have_t0 = true;
            t0 = t;
            t_end = t0 + NB * bns;
        }
        if (t >= t_end) break;
        if (t < t0) continue;
        int j = (int)((t - t0) / bns);
        CN[j] += 1;
        int o = 6 * j;
        for (int i = 0; i < 6; i++) {
            double x = r.v[i];
            CS[o + i] += x;
            CSS[o + i] += x * x;
        }
    }
    rd_close(RD);
    if (!have_t0) return 0;
    for (int j = 0; j < NB; j++) {
        STILL[j] = false;
        if (CN[j] < BLOCK_MIN_ROWS) continue;
        int o = 6 * j;
        double sd[6];
        for (int i = 0; i < 6; i++) {
            double m = CS[o + i] / CN[j];
            double var = CSS[o + i] / CN[j] - m * m;
            sd[i] = var > 0.0 ? sqrt(var) : 0.0;
        }
        if (max3(sd[0], sd[1], sd[2]) >= STILL_GYRO_STD || max3(sd[3], sd[4], sd[5]) >= STILL_ACC_STD) continue;
        if (max3(max3(sd[0], sd[1], sd[2]), sd[3], max3(sd[4], sd[5], sd[5])) <= STUCK_STD) continue;
        double fx = CS[o + 3] / CN[j], fy = CS[o + 4] / CN[j], fz = CS[o + 5] / CN[j];
        double fn = sqrt(fx * fx + fy * fy + fz * fz);
        STILL[j] = ACC_NORM_MIN <= fn && fn <= ACC_NORM_MAX;
    }
    int best_j, best_len;
    best_run(STILL, 0, &best_j, &best_len);
    if (best_len * BLOCK_S < MIN_STILL_S) {          // CAL_NOISE_ON
        if (!still_denoised(src, t0)) return -1;
        best_run(STILL, WV, &best_j, &best_len);
    }
    if (best_len * BLOCK_S < MIN_STILL_S) return 0;
    int trim = (int)(TRIM_S / BLOCK_S);
    int c0 = best_j, c1 = best_j + best_len;
    if ((best_len - 2 * trim) * BLOCK_S >= MIN_STILL_S) {
        c0 += trim;
        c1 -= trim;
    }
    i64 cnt = 0;
    double tot[6] = {0, 0, 0, 0, 0, 0};
    for (int j = c0; j < c1; j++) {
        cnt += CN[j];
        for (int i = 0; i < 6; i++) tot[i] += CS[6 * j + i];
    }
    double m[6];
    for (int i = 0; i < 6; i++) m[i] = tot[i] / (double)cnt;
    tilt(m[3], m[4], m[5], cal);
    cal.bgx = m[0]; cal.bgy = m[1]; cal.bgz = m[2];
    cal.still = true;
    *t_anchor = t0 + best_j * bns + (best_len * bns) / 2;
    return 1;
}

// ---- pass 2: rows before the anchor, integrated backward (pathfinder._pre_segment) ----
static i64 PT[PRE_MAX_ROWS];
static double PB[7 * PRE_MAX_ROWS];

// Number of rows before the anchor, -1 if more than PRE_MAX_ROWS, -2 if the input cannot be opened.
static int pre_segment(const char* src, i64 t_anchor, const Init& in) {
    int m = 0;
    bool have_anchor = false;
    i64 t_next = 0;
    double av[6];
    if (!rd_open(RD, src)) return -2;
    size_t n;
    Row r;
    while (rd_line(RD, &n)) {
        if (!parse_row(n, r, true)) continue;
        if (r.tint && valid6(r.v) && r.t >= t_anchor) {
            have_anchor = true;
            t_next = r.t;
            for (int i = 0; i < 6; i++) av[i] = r.v[i];
            break;
        }
        if (m >= PRE_MAX_ROWS) {
            rd_close(RD);
            return -1;
        }
        PT[m] = r.tint ? r.t : -1;
        for (int i = 0; i < 6; i++) PB[7 * m + i] = r.v[i];
        PB[7 * m + 6] = 0.0;
        m++;
    }
    rd_close(RD);
    double qw = in.qw, qx = in.qx, qy = in.qy, qz = in.qz;
    const double bgx = in.bgx, bgy = in.bgy, bgz = in.bgz, g = in.g;
    if (!have_anchor) {
        for (int i = 0; i < m; i++) {
            double* o = PB + 7 * i;
            o[0] = 0.0; o[1] = 0.0; o[2] = 0.0; o[3] = qw; o[4] = qx; o[5] = qy; o[6] = qz;
        }
        return m;
    }
    double px = 0.0, py = 0.0, pz = 0.0, vx = 0.0, vy = 0.0, vz = 0.0;
    double gx = av[0], gy = av[1], gz = av[2], ax = av[3], ay = av[4], az = av[5];
    double ncx = gx - bgx, ncy = gy - bgy, ncz = gz - bgz;
    double ux = 2.0 * (qy * az - qz * ay), uy = 2.0 * (qz * ax - qx * az), uz = 2.0 * (qx * ay - qy * ax);
    double nfx = ax + qw * ux + (qy * uz - qz * uy);
    double nfy = ay + qw * uy + (qz * ux - qx * uz);
    double nfz = az + qw * uz + (qx * uy - qy * ux);
    bool has_next = true;
    for (int i = m - 1; i >= 0; i--) {
        i64 t = PT[i];
        double* o = PB + 7 * i;
        if (t >= 0) {
            double dt = (double)(t_next - t) * 1e-9;
            gx = o[0]; gy = o[1]; gz = o[2]; ax = o[3]; ay = o[4]; az = o[5];
            if (gx * gx + gy * gy + gz * gz + ax * ax + ay * ay + az * az < MAX_SUMSQ) {
                if (0 < dt && dt <= MAX_JUMP_S) {
                    if (dt <= MAX_DT && has_next) {
                        double cx = gx - bgx, cy = gy - bgy, cz = gz - bgz;
                        double wx = -0.5 * (ncx + cx), wy = -0.5 * (ncy + cy), wz = -0.5 * (ncz + cz);
                        double th2 = (wx * wx + wy * wy + wz * wz) * dt * dt;
                        double c, k;
                        if (th2 < 1e-8) {
                            c = 1.0 - th2 / 8.0;
                            k = 0.5 * dt * (1.0 - th2 / 24.0);
                        } else {
                            double th = sqrt(th2);
                            c = cos(0.5 * th);
                            k = sin(0.5 * th) * dt / th;
                        }
                        double kx = wx * k, ky = wy * k, kz = wz * k;
                        double nw = qw * c - qx * kx - qy * ky - qz * kz;
                        double nx = qw * kx + qx * c + qy * kz - qz * ky;
                        double ny = qw * ky - qx * kz + qy * c + qz * kx;
                        double nz = qw * kz + qx * ky - qy * kx + qz * c;
                        double inv = 1.0 / sqrt(nw * nw + nx * nx + ny * ny + nz * nz);
                        nw *= inv; nx *= inv; ny *= inv; nz *= inv;
                        ux = 2.0 * (ny * az - nz * ay); uy = 2.0 * (nz * ax - nx * az); uz = 2.0 * (nx * ay - ny * ax);
                        double fwx = ax + nw * ux + (ny * uz - nz * uy);
                        double fwy = ay + nw * uy + (nz * ux - nx * uz);
                        double fwz = az + nw * uz + (nx * uy - ny * ux);
                        double awx = 0.5 * (nfx + fwx), awy = 0.5 * (nfy + fwy), awz = 0.5 * (nfz + fwz) - g;
                        double hdt2 = 0.5 * dt * dt;
                        double npx = px - vx * dt + awx * hdt2;
                        double npy = py - vy * dt + awy * hdt2;
                        double npz = pz - vz * dt + awz * hdt2;
                        double nvx = vx - awx * dt, nvy = vy - awy * dt, nvz = vz - awz * dt;
                        double chk = npx + npy + npz + nvx + nvy + nvz + nw;
                        if (chk - chk == 0) {
                            qw = nw; qx = nx; qy = ny; qz = nz;
                            px = npx; py = npy; pz = npz;
                            vx = nvx; vy = nvy; vz = nvz;
                            ncx = cx; ncy = cy; ncz = cz;
                            nfx = fwx; nfy = fwy; nfz = fwz;
                        } else {
                            has_next = false;
                        }
                    } else {
                        px = px - vx * dt; py = py - vy * dt; pz = pz - vz * dt;
                        ncx = gx - bgx; ncy = gy - bgy; ncz = gz - bgz;
                        ux = 2.0 * (qy * az - qz * ay); uy = 2.0 * (qz * ax - qx * az); uz = 2.0 * (qx * ay - qy * ax);
                        nfx = ax + qw * ux + (qy * uz - qz * uy);
                        nfy = ay + qw * uy + (qz * ux - qx * uz);
                        nfz = az + qw * uz + (qx * uy - qy * ux);
                        has_next = true;
                    }
                    t_next = t;
                }
            } else if (0 < dt && dt <= MAX_JUMP_S) {
                px = px - vx * dt; py = py - vy * dt; pz = pz - vz * dt;
                t_next = t;
                has_next = false;
            }
        }
        o[0] = px; o[1] = py; o[2] = pz;
        o[3] = qw; o[4] = qx; o[5] = qy; o[6] = qz;
    }
    return m;
}

// ---- fallback initialisation (pathfinder._init_window, _initialise) ----
static double WIN[6 * INIT_MAX_ROWS];

static bool initialise(const char* src, Init& o) {
    int nw = 0;
    bool have_t0 = false;
    i64 t0 = 0, t_end = 0;
    if (!rd_open(RD, src)) return false;
    size_t n;
    Row r;
    while (rd_line(RD, &n)) {
        if (!parse_row(n, r, true)) continue;
        if (!r.tok) continue;
        if (!valid6(r.v)) continue;
        if (!r.tint) continue;                       // see the header: not integrated
        i64 t = r.t;
        if (!have_t0) {
            have_t0 = true;
            t0 = t;
            t_end = t0 + (i64)(INIT_S * 1e9);
        }
        if (t > t_end) break;
        if (t >= t0) {
            for (int i = 0; i < 6; i++) WIN[6 * nw + i] = r.v[i];
            nw++;
            if (nw >= INIT_MAX_ROWS) break;
        }
    }
    rd_close(RD);
    o.qw = 1.0; o.qx = 0.0; o.qy = 0.0; o.qz = 0.0;
    o.bgx = 0.0; o.bgy = 0.0; o.bgz = 0.0; o.g = G_DEFAULT; o.still = false;
    if (nw == 0) return true;
    double mean[6] = {0, 0, 0, 0, 0, 0};
    for (int r2 = 0; r2 < nw; r2++)
        for (int i = 0; i < 6; i++) mean[i] += WIN[6 * r2 + i];
    for (int i = 0; i < 6; i++) mean[i] /= nw;
    double var[6] = {0, 0, 0, 0, 0, 0};
    for (int r2 = 0; r2 < nw; r2++)
        for (int i = 0; i < 6; i++) {
            double d = WIN[6 * r2 + i] - mean[i];
            var[i] += d * d;
        }
    double sd[6];
    for (int i = 0; i < 6; i++) sd[i] = sqrt(var[i] / nw);
    bool still = max3(sd[0], sd[1], sd[2]) < STILL_GYRO_STD && max3(sd[3], sd[4], sd[5]) < STILL_ACC_STD;
    double fx = mean[3], fy = mean[4], fz = mean[5];
    double fn = sqrt(fx * fx + fy * fy + fz * fz);
    if (fn < 1.0) return true;
    double ux = fx / fn, uy = fy / fn, uz = fz / fn;
    if (1.0 + uz < 1e-9) {
        o.qw = 0.0; o.qx = 1.0; o.qy = 0.0; o.qz = 0.0;
    } else {
        double w = 1.0 + uz, x = uy, y = -ux;
        double k = 1.0 / sqrt(w * w + x * x + y * y);
        o.qw = w * k; o.qx = x * k; o.qy = y * k; o.qz = 0.0;
    }
    if (still) {
        o.bgx = mean[0]; o.bgy = mean[1]; o.bgz = mean[2]; o.g = fn; o.still = true;
    }
    return true;
}

// ---- step 7a filter (pathfinder._kf_*, _inject, _gap_inflate, _bin_still, _bins_steady) ----
static double P[N * N], PM[N * N], PN[N * N], DX[N], PROW[N];
static int AI[27], AJ[27];
static double AA[27];

static void rot_matrix(double w, double x, double y, double z, double* r) {
    r[0] = 1.0 - 2.0 * (y * y + z * z); r[1] = 2.0 * (x * y - w * z); r[2] = 2.0 * (x * z + w * y);
    r[3] = 2.0 * (x * y + w * z); r[4] = 1.0 - 2.0 * (x * x + z * z); r[5] = 2.0 * (y * z - w * x);
    r[6] = 2.0 * (x * z - w * y); r[7] = 2.0 * (y * z + w * x); r[8] = 1.0 - 2.0 * (x * x + y * y);
}

static void kf_init(bool still) {
    double tl = still ? P0_TILT : P0_TILT_FALLBACK;
    double bg = still ? P0_BG : P0_BG_FALLBACK;
    const double sig[N] = {0.0, 0.0, 0.0, P0_VEL, P0_VEL, P0_VEL, tl, tl, P0_YAW, bg, bg, bg, P0_BA, P0_BA, P0_BA};
    for (int i = 0; i < N * N; i++) P[i] = 0.0;
    for (int i = 0; i < N; i++) P[i * N + i] = sig[i] * sig[i];
}

static void kf_propagate(const double* r, double fx, double fy, double fz, double T, double acc_d2,
                         double gyro_d2) {
    int na = 0;
    const int fi[9] = {0, 1, 2, 3, 3, 4, 4, 5, 5};
    const int fj[9] = {3, 4, 5, 7, 8, 6, 8, 6, 7};
    const double fa[9] = {T, T, T, T * fz, -T * fy, -T * fz, T * fx, T * fy, -T * fx};
    for (int e = 0; e < 9; e++) { AI[na] = fi[e]; AJ[na] = fj[e]; AA[na] = fa[e]; na++; }
    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++) {
            double a = -T * r[3 * i + j];
            AI[na] = 3 + i; AJ[na] = 12 + j; AA[na] = a; na++;
            AI[na] = 6 + i; AJ[na] = 9 + j; AA[na] = a; na++;
        }
    memcpy(PM, P, sizeof P);
    for (int e = 0; e < na; e++) {
        int oi = AI[e] * N, oj = AJ[e] * N;
        double a = AA[e];
        for (int c = 0; c < N; c++) PM[oi + c] += a * P[oj + c];
    }
    memcpy(PN, PM, sizeof P);
    for (int e = 0; e < na; e++) {
        int i = AI[e], j = AJ[e];
        double a = AA[e];
        for (int rr = 0; rr < N * N; rr += N) PN[rr + i] += a * PM[rr + j];
    }
    double qv = acc_d2 * T;
    double qt = gyro_d2 * T;
    double qg = GYRO_WALK * GYRO_WALK * T;
    double qa = ACC_WALK * ACC_WALK * T;
    for (int k = 0; k < 3; k++) {
        PN[(3 + k) * (N + 1)] += qv;
        PN[(6 + k) * (N + 1)] += qt;
        PN[(9 + k) * (N + 1)] += qg;
        PN[(12 + k) * (N + 1)] += qa;
    }
    memcpy(P, PN, sizeof P);
}

static void gap_inflate(double L, double tilt2, const double* dv2) {
    double s = L / (GAP_H_TICKS * TICK_S);
    s = s * s;
    P[6 * N + 6] += 0.5 * tilt2 * s;
    P[7 * N + 7] += 0.5 * tilt2 * s;
    for (int k = 0; k < 3; k++) {
        double a = dv2[k] * s;
        P[(3 + k) * (N + 1)] += a;
        P[k * (N + 1)] += a * L * L * 0.25;
        P[k * N + 3 + k] += a * L * 0.5;
        P[(3 + k) * N + k] += a * L * 0.5;
    }
}

static void kf_update(int k, double z, double var) {
    double S = P[k * N + k] + var;
    if (!(S > 0.0)) return;
    double inn = z - DX[k];
    for (int j = 0; j < N; j++) PROW[j] = P[k * N + j];
    for (int i = 0; i < N; i++) {
        double Ki = P[i * N + k] / S;
        if (Ki != 0.0) {
            DX[i] += Ki * inn;
            int oi = i * N;
            for (int j = 0; j < N; j++) P[oi + j] -= Ki * PROW[j];
        }
    }
}

static bool bin_still(int n, const double* s, const double* ss) {
    if (n < BLOCK_MIN_ROWS) return false;
    double sd[6];
    for (int i = 0; i < 6; i++) {
        double m = s[i] / n;
        double var = ss[i] / n - m * m;
        sd[i] = var > 0.0 ? sqrt(var) : 0.0;
    }
    if (max3(sd[0], sd[1], sd[2]) >= STILL_GYRO_STD || max3(sd[3], sd[4], sd[5]) >= STILL_ACC_STD) return false;
    if (max3(max3(sd[0], sd[1], sd[2]), sd[3], max3(sd[4], sd[5], sd[5])) <= STUCK_STD) return false;
    double fx = s[3] / n, fy = s[4] / n, fz = s[5] / n;
    double fn = sqrt(fx * fx + fy * fy + fz * fz);
    return ACC_NORM_MIN <= fn && fn <= ACC_NORM_MAX;
}

static bool bins_steady(int na, const double* sa, int nb, const double* sb) {
    for (int i = 0; i < 6; i++) {
        double tol = i < 3 ? STEADY_GYRO : STEADY_ACC;
        double d = sa[i] / na - sb[i] / nb;
        if (d >= tol || d <= -tol) return false;
    }
    return true;
}

struct State {
    double qw, qx, qy, qz, px, py, pz, vx, vy, vz, bgx, bgy, bgz, bax, bay, baz;
};

static void inject(State& x) {
    double chk = 0.0;
    for (int i = 0; i < N; i++) chk += DX[i];
    if (chk - chk != 0.0) return;
    double ex = DX[6], ey = DX[7], ez = DX[8];
    double th2 = (ex * ex + ey * ey + ez * ez) * 1.0 * 1.0;
    double c, k;
    if (th2 < 1e-8) {
        c = 1.0 - th2 / 8.0;
        k = 0.5 * 1.0 * (1.0 - th2 / 24.0);
    } else {
        double th = sqrt(th2);
        c = cos(0.5 * th);
        k = sin(0.5 * th) * 1.0 / th;
    }
    double kx = ex * k, ky = ey * k, kz = ez * k;
    double nw = c * x.qw - kx * x.qx - ky * x.qy - kz * x.qz;
    double nx = c * x.qx + kx * x.qw + ky * x.qz - kz * x.qy;
    double ny = c * x.qy - kx * x.qz + ky * x.qw + kz * x.qx;
    double nz = c * x.qz + kx * x.qy - ky * x.qx + kz * x.qw;
    double inv = 1.0 / sqrt(nw * nw + nx * nx + ny * ny + nz * nz);
    x.qw = nw * inv; x.qx = nx * inv; x.qy = ny * inv; x.qz = nz * inv;
    x.px = x.px + DX[0]; x.py = x.py + DX[1]; x.pz = x.pz + DX[2];
    x.vx = x.vx + DX[3]; x.vy = x.vy + DX[4]; x.vz = x.vz + DX[5];
    x.bgx = x.bgx + DX[9]; x.bgy = x.bgy + DX[10]; x.bgz = x.bgz + DX[11];
    x.bax = x.bax + DX[12]; x.bay = x.bay + DX[13]; x.baz = x.baz + DX[14];
}

// ---- output ----
static FILE* g_out = 0;
static bool g_full = false;

static void set_ts(const Row& r) {
    size_t n = r.tslen;
    if (n > 9) {
        SECLEN = n - 9;
        memcpy(SEC, r.ts, SECLEN);
        memcpy(FRAC, r.ts + n - 9, 9);
    } else {
        SEC[0] = '0';
        SECLEN = 1;
        memset(FRAC, '0', 9 - n);
        memcpy(FRAC + 9 - n, r.ts, n);
    }
    SEC[SECLEN] = 0;
    FRAC[9] = 0;
}

static inline int put_fixed(char* o, double x, int d) {
    int n = fast_fixed(o, x, d);
    return n ? n : snprintf(o, 64, "%.*f", d, x);
}

// One output line: "sec.frac tx ty tz qx qy qz qw" with 6 / 7 decimals (pathfinder.FMT).
static inline void put(double px, double py, double pz, double qx, double qy, double qz, double qw) {
    if (g_full) {
        fprintf(g_out, "%s.%s %.17g %.17g %.17g %.17g %.17g %.17g %.17g\n", SEC, FRAC, px, py, pz, qx, qy, qz, qw);
        return;
    }
    char* o = OLINE;
    memcpy(o, SEC, SECLEN);
    o += SECLEN;
    *o++ = '.';
    memcpy(o, FRAC, 9);
    o += 9;
    const double v[7] = {px, py, pz, qx, qy, qz, qw};
    for (int i = 0; i < 7; i++) {
        *o++ = ' ';
        o += put_fixed(o, v[i], i < 3 ? 6 : 7);
    }
    *o++ = '\n';
    fwrite(OLINE, 1, (size_t)(o - OLINE), g_out);
}

// ---- pass 3: the forward filter (pathfinder.run) ----
static int run(const char* src, const char* dst) {
    Init in;
    i64 t_anchor = 0;
    int n_pre = 0;
    int c = calibrate(src, in, &t_anchor);
    if (c < 0) return 1;
    if (c == 1) {
        n_pre = pre_segment(src, t_anchor, in);
        if (n_pre == -2) return 1;
        if (n_pre < 0) {                             // too many rows before the anchor: fall back
            c = 0;
            n_pre = 0;
        }
    }
    if (c == 0) {
        if (!initialise(src, in)) return 1;          // 6a: rows before the first valid row keep this pose
    }
    State x;
    x.qw = in.qw; x.qx = in.qx; x.qy = in.qy; x.qz = in.qz;
    x.bgx = in.bgx; x.bgy = in.bgy; x.bgz = in.bgz;
    const double g = in.g;
    x.px = x.py = x.pz = x.vx = x.vy = x.vz = 0.0;
    x.bax = x.bay = x.baz = 0.0;
    kf_init(in.still);
    for (int i = 0; i < N; i++) DX[i] = 0.0;
    const i64 tick_ns = (i64)(TICK_S * 1e9);
    i64 tick_end = 0, t_tick = 0;
    double r0[9], r1[9], r[9];
    rot_matrix(x.qw, x.qx, x.qy, x.qz, r0);
    double fsx = 0.0, fsy = 0.0, fsz = 0.0;
    int fcount = 0, bn = 0, pn = 0;
    double bs[6] = {0, 0, 0, 0, 0, 0}, bq[6] = {0, 0, 0, 0, 0, 0}, ps[6] = {0, 0, 0, 0, 0, 0};
    bool pstill = false;
    double ccx = 0.0, ccy = 0.0, ccz = 0.0;
    double gap = 0.0;
    double ring_z[GAP_H_TICKS][3], ring_v[GAP_H_TICKS][3];
    int ring_n = 0, ring_head = 0;
    double tilt2 = -1.0;
    double dv2[3] = {0.0, 0.0, 0.0};
    int sg = 0, sa = 0;
    double sgx = NAN, sgy = NAN, sgz = NAN, sax = NAN, say = NAN, saz = NAN;
    const double zs2 = ZUPT_SIGMA * ZUPT_SIGMA, zm2 = ZARU_SIGMA_MIN * ZARU_SIGMA_MIN;
    const double tau = FC_TAU;
    i64 t = 0, tl = 0;
    bool have_t = false, has_prev = false;
    double pcx = 0.0, pcy = 0.0, pcz = 0.0, pfx = 0.0, pfy = 0.0, pfz = 0.0;

    if (!rd_open(RD, src)) return 1;
    g_out = fopen(dst, "wb");
    if (!g_out) {
        rd_close(RD);
        g_err_path = dst;
        return 1;
    }
    setvbuf(g_out, OUTBUF, _IOFBF, sizeof OUTBUF);
    size_t n;
    Row rw;
    int k = 0;
    if (n_pre) {
        // rows before the anchor: attitude from the backward pass, position held at the anchor's (6d)
        while (rd_line(RD, &n)) {
            if (!parse_row(n, rw, false)) continue;
            if (rw.tok) set_ts(rw);
            const double* o = PB + 7 * k;
            k++;
            put(0.0, 0.0, 0.0, o[4], o[5], o[6], o[3]);
            if (k == n_pre) break;
        }
    }
    while (rd_line(RD, &n)) {
        if (!parse_row(n, rw, true)) continue;
        if (rw.tok) set_ts(rw);                      // else: keep the previous output timestamp
        double gx = rw.v[0], gy = rw.v[1], gz = rw.v[2], ax = rw.v[3], ay = rw.v[4], az = rw.v[5];
        if (rw.tint) {
            t = rw.t;
            bool ok = gx * gx + gy * gy + gz * gz + ax * ax + ay * ay + az * az < MAX_SUMSQ;
            if (ok) {
                // ---- dead sensor: a triple repeating exactly, or an all-zero accelerometer ----
                if (gx == sgx && gy == sgy && gz == sgz) sg += 1;
                else { sgx = gx; sgy = gy; sgz = gz; sg = 1; }
                if (ax == sax && ay == say && az == saz) sa += 1;
                else { sax = ax; say = ay; saz = az; sa = 1; }
                if (sg >= STUCK_ROWS || sa >= STUCK_ROWS || !(ax != 0.0 || ay != 0.0 || az != 0.0)) ok = false;
            }
            if (ok) {
                if (have_t) {
                    double dt = (double)(t - tl) * 1e-9;
                    if (0 < dt && dt <= MAX_JUMP_S) {
                        if (t >= tick_end) {
                            // ---- close the tick (every 0.25 s): propagate, witnesses, inject ----
                            double T = (double)(tl - t_tick) * 1e-9;
                            rot_matrix(x.qw, x.qx, x.qy, x.qz, r1);
                            if (T > 0.0) {
                                for (int i = 0; i < 9; i++) r[i] = 0.5 * (r0[i] + r1[i]);
                                if (gap > 0.0 && tilt2 >= 0.0) gap_inflate(gap, tilt2, dv2);
                                double ad2 = ACC_NOISE * ACC_NOISE;
                                double gd2 = GYRO_NOISE * GYRO_NOISE;
                                if (fcount) kf_propagate(r, fsx / fcount, fsy / fcount, fsz / fcount, T, ad2, gd2);
                                else kf_propagate(r, 0.0, 0.0, g, T, ad2, gd2);
                            }
                            bool still = bin_still(bn, bs, bq);
                            bool zupt = still && pstill && bins_steady(pn, ps, bn, bs);
                            if (zupt) {
                                kf_update(3, -x.vx, zs2);
                                kf_update(4, -x.vy, zs2);
                                kf_update(5, -x.vz, zs2);
                                const double bgl[3] = {x.bgx, x.bgy, x.bgz};
                                for (int i = 0; i < 3; i++) {
                                    double m = bs[i] / bn;
                                    double var = (bq[i] / bn - m * m) / bn;
                                    if (var < zm2) var = zm2;
                                    kf_update(9 + i, m - bgl[i], var);
                                }
                            } else {
                                kf_update(3, -x.vx, V2_SIGMA_H * V2_SIGMA_H);
                                kf_update(4, -x.vy, V2_SIGMA_H * V2_SIGMA_H);
                                kf_update(5, -x.vz, V2_SIGMA_V * V2_SIGMA_V);
                            }
                            if (!zupt && T > 0.0) {
                                double a = T < V2P_TAU ? T / V2P_TAU : 1.0;
                                ccx += (x.px - ccx) * a;
                                ccy += (x.py - ccy) * a;
                                ccz += (x.pz - ccz) * a;
                                kf_update(0, ccx - x.px, V2P_SIGMA_H * V2P_SIGMA_H);
                                kf_update(1, ccy - x.py, V2P_SIGMA_H * V2P_SIGMA_H);
                                kf_update(2, ccz - x.pz, V2P_SIGMA_V * V2P_SIGMA_V);
                            }
                            inject(x);
                            for (int i = 0; i < N; i++) DX[i] = 0.0;
                            rot_matrix(x.qw, x.qx, x.qy, x.qz, r0);
                            if (ring_n == GAP_H_TICKS) {
                                const double* oz = ring_z[ring_head];
                                const double* ov = ring_v[ring_head];
                                double e0 = r0[6] - oz[0];
                                double e1 = r0[7] - oz[1];
                                double e2a = r0[8] - oz[2];
                                double e2 = e0 * e0 + e1 * e1 + e2a * e2a;
                                double d0 = x.vx - ov[0];
                                double d1 = x.vy - ov[1];
                                double d2 = x.vz - ov[2];
                                if (tilt2 < 0.0) {
                                    tilt2 = e2;
                                    dv2[0] = d0 * d0; dv2[1] = d1 * d1; dv2[2] = d2 * d2;
                                } else {
                                    double b = TICK_S / GAP_TAU;
                                    tilt2 += (e2 - tilt2) * b;
                                    dv2[0] += (d0 * d0 - dv2[0]) * b;
                                    dv2[1] += (d1 * d1 - dv2[1]) * b;
                                    dv2[2] += (d2 * d2 - dv2[2]) * b;
                                }
                                ring_head = (ring_head + 1) % GAP_H_TICKS;
                                ring_n--;
                            }
                            int slot = (ring_head + ring_n) % GAP_H_TICKS;
                            ring_z[slot][0] = r0[6]; ring_z[slot][1] = r0[7]; ring_z[slot][2] = r0[8];
                            ring_v[slot][0] = x.vx; ring_v[slot][1] = x.vy; ring_v[slot][2] = x.vz;
                            ring_n++;
                            tick_end += tick_ns * ((t - tick_end) / tick_ns + 1);
                            t_tick = tl;
                            fsx = fsy = fsz = 0.0;
                            fcount = 0;
                            gap = 0.0;
                            pn = bn;
                            for (int i = 0; i < 6; i++) ps[i] = bs[i];
                            pstill = still;
                            bn = 0;
                            for (int i = 0; i < 6; i++) bs[i] = bq[i] = 0.0;
                        }
                        bn += 1;
                        bs[0] += gx; bs[1] += gy; bs[2] += gz; bs[3] += ax; bs[4] += ay; bs[5] += az;
                        bq[0] += gx * gx; bq[1] += gy * gy; bq[2] += gz * gz;
                        bq[3] += ax * ax; bq[4] += ay * ay; bq[5] += az * az;
                        ax = ax - x.bax; ay = ay - x.bay; az = az - x.baz;
                        if (dt <= MAX_DT && has_prev) {
                            // ---- strapdown step (trapezoid), as strapdown._step ----
                            double cx = gx - x.bgx, cy = gy - x.bgy, cz = gz - x.bgz;
                            double wx = 0.5 * (pcx + cx), wy = 0.5 * (pcy + cy), wz = 0.5 * (pcz + cz);
                            double th2 = (wx * wx + wy * wy + wz * wz) * dt * dt;
                            double cc, s;
                            if (th2 < 1e-8) {
                                cc = 1.0 - th2 / 8.0;
                                s = 0.5 * dt * (1.0 - th2 / 24.0);
                            } else {
                                double th = sqrt(th2);
                                cc = cos(0.5 * th);
                                s = sin(0.5 * th) * dt / th;
                            }
                            double kx = wx * s, ky = wy * s, kz = wz * s;
                            double qw = x.qw, qx = x.qx, qy = x.qy, qz = x.qz;
                            double nw = qw * cc - qx * kx - qy * ky - qz * kz;
                            double nx = qw * kx + qx * cc + qy * kz - qz * ky;
                            double ny = qw * ky - qx * kz + qy * cc + qz * kx;
                            double nz = qw * kz + qx * ky - qy * kx + qz * cc;
                            double inv = 1.0 / sqrt(nw * nw + nx * nx + ny * ny + nz * nz);
                            nw *= inv; nx *= inv; ny *= inv; nz *= inv;
                            double ux = 2.0 * (ny * az - nz * ay);
                            double uy = 2.0 * (nz * ax - nx * az);
                            double uz = 2.0 * (nx * ay - ny * ax);
                            double fwx = ax + nw * ux + (ny * uz - nz * uy);
                            double fwy = ay + nw * uy + (nz * ux - nx * uz);
                            double fwz = az + nw * uz + (nx * uy - ny * ux);
                            double awx = 0.5 * (pfx + fwx);
                            double awy = 0.5 * (pfy + fwy);
                            double awz = 0.5 * (pfz + fwz) - g;
                            double hdt2 = 0.5 * dt * dt;
                            double npx = x.px + x.vx * dt + awx * hdt2;
                            double npy = x.py + x.vy * dt + awy * hdt2;
                            double npz = x.pz + x.vz * dt + awz * hdt2;
                            double nvx = x.vx + awx * dt, nvy = x.vy + awy * dt, nvz = x.vz + awz * dt;
                            double chk = npx + npy + npz + nvx + nvy + nvz + nw;
                            if (chk - chk == 0) {
                                x.qw = nw; x.qx = nx; x.qy = ny; x.qz = nz;
                                x.px = npx; x.py = npy; x.pz = npz;
                                x.vx = nvx; x.vy = nvy; x.vz = nvz;
                                pcx = cx; pcy = cy; pcz = cz;
                                pfx = fwx; pfy = fwy; pfz = fwz;
                                fsx += fwx; fsy += fwy; fsz += fwz;
                                fcount += 1;
                            } else {
                                has_prev = false;
                            }
                        } else {
                            // gap or no previous sample: coast (velocity decays, FC_ON), then take this sample
                            double e = exp(-dt / tau);
                            double s = tau * (1.0 - e);
                            x.px = x.px + x.vx * s; x.py = x.py + x.vy * s; x.pz = x.pz + x.vz * s;
                            x.vx = x.vx * e; x.vy = x.vy * e; x.vz = x.vz * e;
                            gap += dt;
                            pcx = gx - x.bgx; pcy = gy - x.bgy; pcz = gz - x.bgz;
                            double qw = x.qw, qx = x.qx, qy = x.qy, qz = x.qz;
                            double ux = 2.0 * (qy * az - qz * ay);
                            double uy = 2.0 * (qz * ax - qx * az);
                            double uz = 2.0 * (qx * ay - qy * ax);
                            pfx = ax + qw * ux + (qy * uz - qz * uy);
                            pfy = ay + qw * uy + (qz * ux - qx * uz);
                            pfz = az + qw * uz + (qx * uy - qy * ux);
                            has_prev = true;
                        }
                        tl = t;
                    }
                } else {
                    tl = t;
                    have_t = true;
                    tick_end = t + tick_ns;
                    t_tick = t;
                    bn += 1;
                    bs[0] += gx; bs[1] += gy; bs[2] += gz; bs[3] += ax; bs[4] += ay; bs[5] += az;
                    bq[0] += gx * gx; bq[1] += gy * gy; bq[2] += gz * gz;
                    bq[3] += ax * ax; bq[4] += ay * ay; bq[5] += az * az;
                    ax = ax - x.bax; ay = ay - x.bay; az = az - x.baz;
                    pcx = gx - x.bgx; pcy = gy - x.bgy; pcz = gz - x.bgz;
                    double qw = x.qw, qx = x.qx, qy = x.qy, qz = x.qz;
                    double ux = 2.0 * (qy * az - qz * ay);
                    double uy = 2.0 * (qz * ax - qx * az);
                    double uz = 2.0 * (qx * ay - qy * ax);
                    pfx = ax + qw * ux + (qy * uz - qz * uy);
                    pfy = ay + qw * uy + (qz * ux - qx * uz);
                    pfz = az + qw * uz + (qx * uy - qy * ux);
                    has_prev = true;
                }
            } else if (have_t) {
                double dt = (double)(t - tl) * 1e-9;
                if (0 < dt && dt <= MAX_JUMP_S) {
                    double e = exp(-dt / tau);
                    double s = tau * (1.0 - e);
                    x.px = x.px + x.vx * s; x.py = x.py + x.vy * s; x.pz = x.pz + x.vz * s;
                    x.vx = x.vx * e; x.vy = x.vy * e; x.vz = x.vz * e;
                    tl = t;
                    has_prev = false;
                    gap += dt;
                }
            }
        }
        put(x.px, x.py, x.pz, x.qx, x.qy, x.qz, x.qw);
    }
    rd_close(RD);
    bool bad = ferror(g_out) != 0;
    if (fclose(g_out) != 0) bad = true;
    g_out = 0;
    if (bad) {
        g_err_path = dst;
        return 1;
    }
    return 0;
}

#ifndef VORTEX_NO_MAIN    // tests/ccore_selftest.cpp includes this file for its number routines
int main(int argc, char** argv) {
    if (argc == 4 && !strcmp(argv[3], "--full")) g_full = true;   // full precision (equivalence tests)
    else if (argc != 3) {
        fputs("usage: main <imu.csv> <estimated_trajectory.txt>\n", stderr);
        return 2;
    }
    int rc = run(argv[1], argv[2]);
    if (rc) fprintf(stderr, "main: cannot read or write %s\n", g_err_path ? g_err_path : "a file");
    return rc;
}
#endif

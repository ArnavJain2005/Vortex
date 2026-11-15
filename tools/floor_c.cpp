// Floor-measurement worker in C-style C++ (standard library only): the same parse + write
// identity-pose job as floor_worker.py's pw_bytes_* modes, to show what a compiled core costs.
// Static buffers only; no heap allocation of our own.
//
// Build: g++ -O2 -o floor_c floor_c.cpp            (Windows MinGW: add -static)
// Usage: floor_c MODE IN.csv OUT.txt              MODE = noop | pw_id | pw_real
#include <cstdio>
#include <cstdlib>
#include <cstring>

static char inbuf[1 << 16];
static char outbuf[1 << 16];
static char line[1024];

int main(int argc, char** argv) {
    if (argc < 4) return 2;
    if (!strcmp(argv[1], "noop")) return 0;
    const bool real = !strcmp(argv[1], "pw_real");
    FILE* f = fopen(argv[2], "rb");
    FILE* g = fopen(argv[3], "wb");
    if (!f || !g) return 3;
    setvbuf(f, inbuf, _IOFBF, sizeof inbuf);
    setvbuf(g, outbuf, _IOFBF, sizeof outbuf);
    double v[6] = {0, 0, 0, 0, 0, 0};
    double qx = 0, qy = 0, qz = 0, qw = 1;
    if (real) { qx = 0.1234567; qy = -0.2345678; qz = 0.3456789; qw = 0.8995023; }
    long n = 0;
    char ts[40];
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '#') continue;
        size_t L = strcspn(line, ",\r\n");
        if (L > 30) L = 30;
        // left-pad to at least 10 digits so there is always an integer part
        size_t pad = L < 10 ? 10 - L : 0;
        memset(ts, '0', pad);
        memcpy(ts + pad, line, L);
        size_t T = L + pad;
        if (line[L] == ',') {
            double w[6];
            char* p = line + L + 1;
            int k = 0;
            for (; k < 6; ++k) {
                char* e;
                w[k] = strtod(p, &e);
                if (e == p) break;
                p = (*e == ',') ? e + 1 : e;
            }
            if (k == 6) memcpy(v, w, sizeof v);
        }
        double tx = real ? v[3] : 0.0, ty = real ? v[4] : 0.0, tz = real ? v[5] : 0.0;
        fprintf(g, "%.*s.%.*s %.6f %.6f %.6f %.7f %.7f %.7f %.7f\n", (int)(T - 9), ts, 9, ts + T - 9,
                tx, ty, tz, qx, qy, qz, qw);
        ++n;
    }
    fclose(f);
    fclose(g);
    return n > 0 ? 0 : 4;
}

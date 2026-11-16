// Harness for main.cpp's number routines (driven by tests/test_ccore.py). One request per stdin line:
//   P <hex of the field bytes>   -> "ok <hex of the double's bits>" (py_float result) or "bad"
//   F <hex of the double's bits> <decimals>   -> the text put_fixed writes
#define VORTEX_NO_MAIN
#include "../main.cpp"

static char REQ[2 * LINE_CAP + 64];
static unsigned char FIELD[LINE_CAP];

static int hexval(char c) { return c <= '9' ? c - '0' : (c | 32) - 'a' + 10; }

int main() {
    while (fgets(REQ, sizeof REQ, stdin)) {
        size_t n = strlen(REQ);
        while (n && (REQ[n - 1] == '\n' || REQ[n - 1] == '\r')) REQ[--n] = 0;
        if (REQ[0] == 'P') {
            size_t m = 0;
            for (size_t i = 2; i + 1 < n; i += 2) FIELD[m++] = (unsigned char)(hexval(REQ[i]) * 16 + hexval(REQ[i + 1]));
            double x;
            if (py_float(FIELD, m, &x)) {
                unsigned long long b;
                memcpy(&b, &x, 8);
                printf("ok %016llx\n", b);
            } else {
                puts("bad");
            }
        } else if (REQ[0] == 'F') {
            unsigned long long b = strtoull(REQ + 2, 0, 16);
            int d = atoi(REQ + 19);
            double x;
            memcpy(&x, &b, 8);
            char o[128];
            int k = put_fixed(o, x, d);
            o[k] = 0;
            puts(o);
        }
    }
    return 0;
}

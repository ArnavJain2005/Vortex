# Clean-Machine Matrix (`AG-3`)

Verification ledger produced by `tools/clean_machine_check.py` (stdlib-only fresh bare virtual environments across Windows Python 3.13/3.14, Linux Docker Python 3.10–3.14, and the bundled `Dockerfile` image).

---

## 1. Pre-CC-1a Baseline: `main` (`5ba1c4b`) `pathfinder.py` & `dist/vortex_v0.95.zip` (`86711a9`) across Python 3.10–3.14

Before `CC-1a` (`track3/freeze-build`) ships the single-file B1/B2/B4 entry point, this baseline closes the Python `3.10` / `3.11` runtime blind spot noted in `LOOP_CC.md` and verifies `dist/vortex_v0.95.zip`'s `Dockerfile` image on container-local storage (no Windows bind-mounts).

Each fresh bare venv (`python -m venv --without-pip`) ran standalone `pathfinder.py` (`python -S pathfinder.py IN OUT`, copied alone into an empty folder with zero sibling imports and zero packages installed); `v0.95-dockerfile` built `dist/vortex_v0.95.zip`'s `Dockerfile` and ran `python -S /app/main.py IN OUT`.

### A. `data/official/MH_03_medium_b_s1` (`26,106` rows) — Cross-version byte identity: **PASS (`1` unique SHA-256 across `8` environments)**

| Environment | Python | OS / Image | `vortex.check_output` | Output SHA-256 (16 hex) | Byte-identical across matrix? |
|---|---|---|---|---|---|
| `win-venv-3.13` | 3.13.5 | Windows (bare venv) | PASS | `03ada1d088015775` | YES |
| `win-venv-3.14` | 3.14.7 | Windows (bare venv) | PASS | `03ada1d088015775` | YES |
| `docker-3.10` | 3.10.22 | `python:3.10-slim-bookworm` (bare venv) | PASS | `03ada1d088015775` | YES |
| `docker-3.11` | 3.11.18 | `python:3.11-slim-bookworm` (bare venv) | PASS | `03ada1d088015775` | YES |
| `docker-3.12` | 3.12.7 | `python:3.12.7-slim-bookworm` (bare venv) | PASS | `03ada1d088015775` | YES |
| `docker-3.13` | 3.13.18 | `python:3.13-slim-bookworm` (bare venv) | PASS | `03ada1d088015775` | YES |
| `docker-3.14` | 3.14.10 | `python:3.14-slim` (bare venv) | PASS | `03ada1d088015775` | YES |
| `v0.95-dockerfile` | 3.12.7 | `dist/vortex_v0.95.zip` `Dockerfile` | PASS | `03ada1d088015775` | YES |

### B. `data/official_tumvi/dataset-room3_512_16_b_s1` (`27,206` rows) — Cross-version byte identity: **PASS (`1` unique SHA-256 across `8` environments)**

| Environment | Python | OS / Image | `vortex.check_output` | Output SHA-256 (16 hex) | Byte-identical across matrix? |
|---|---|---|---|---|---|
| `win-venv-3.13` | 3.13.5 | Windows (bare venv) | PASS | `d3a08d9ab2224404` | YES |
| `win-venv-3.14` | 3.14.7 | Windows (bare venv) | PASS | `d3a08d9ab2224404` | YES |
| `docker-3.10` | 3.10.22 | `python:3.10-slim-bookworm` (bare venv) | PASS | `d3a08d9ab2224404` | YES |
| `docker-3.11` | 3.11.18 | `python:3.11-slim-bookworm` (bare venv) | PASS | `d3a08d9ab2224404` | YES |
| `docker-3.12` | 3.12.7 | `python:3.12.7-slim-bookworm` (bare venv) | PASS | `d3a08d9ab2224404` | YES |
| `docker-3.13` | 3.13.18 | `python:3.13-slim-bookworm` (bare venv) | PASS | `d3a08d9ab2224404` | YES |
| `docker-3.14` | 3.14.10 | `python:3.14-slim` (bare venv) | PASS | `d3a08d9ab2224404` | YES |
| `v0.95-dockerfile` | 3.12.7 | `dist/vortex_v0.95.zip` `Dockerfile` | PASS | `d3a08d9ab2224404` | YES |

---

## 2. Full B1 / B2 / B4 Single-File Matrix (`CC-1a` / `v1.0` / Final Zip)

*Pending CC-1a bundle handoff (`GIVES TO AG: CC-1a bundle at <branch@hash>` in `LOOP_CC.md`).*

Once `CC-1a` lands, run:

```powershell
python tools/clean_machine_check.py --zip dist/<bundle>.zip --input data/official/MH_03_medium_b_s1/mav0/imu0/data.csv --envs win-venv-3.13,win-venv-3.14,docker-3.10,docker-3.11,docker-3.12,docker-3.13,docker-3.14,zip-dockerfile --commit <sha> --out Docs/CLEAN_MACHINE.md
```

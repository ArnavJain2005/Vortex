"""AG-3 clean-machine verification matrix for a bundled standalone src/main.py or submission zip.

Tests the bundled `src/main.py` ALONE (copied into an empty directory with no sibling imports and no
`vortex` package installed) across fresh virtual environments on Windows (Python 3.13, 3.14) and Linux
Docker (Python 3.10, 3.11, 3.12, 3.13, 3.14, plus optional zip Dockerfile image):
  - B1 invocation forms (no args x 4 search paths, IN, IN OUT with/without -S, sequence dirs, --input/--output, -i/-o)
  - B2 input formatting variants (CRLF, missing-# header, no header, blank lines, spaces after commas, extra columns)
  - B4 injected-failure constant-pose fallback (exit 0, stderr note, exact row count) and missing-file non-zero exit
  - Output validation with `python -m vortex.check_output` and byte-for-byte SHA-256 comparison across Pythons.

Usage:
    python tools/clean_machine_check.py --zip dist/vortex_v1.0.zip --input data/official/MH_03_medium_b_s1/mav0/imu0/data.csv --out Docs/CLEAN_MACHINE.md
    python tools/clean_machine_check.py --main path/to/src/main.py --input IMU.csv --envs host-venv
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import textwrap
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vortex import check_output  # noqa: E402

DOCKER_IMAGES = {
    "docker-3.10": "python:3.10-slim-bookworm",
    "docker-3.11": "python:3.11-slim-bookworm",
    "docker-3.12": "python:3.12.7-slim-bookworm",
    "docker-3.13": "python:3.13-slim-bookworm",
    "docker-3.14": "python:3.14-slim",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def make_b2_variants(base_csv: Path, out_dir: Path) -> dict[str, Path]:
    """Build B2 formatting variants from one base IMU CSV (same data rows, same order)."""
    raw_lines = base_csv.read_text(encoding="utf-8-sig").splitlines()
    has_header = bool(raw_lines) and raw_lines[0].lstrip().startswith("#")
    header = raw_lines[0] if has_header else "#timestamp [ns],w_x,w_y,w_z,a_x,a_y,a_z"
    data_rows = [ln for ln in (raw_lines[1:] if has_header else raw_lines) if ln.strip() and not ln.lstrip().startswith("#")]

    variants: dict[str, Path] = {}

    p_crlf = out_dir / "b2_crlf.csv"
    p_crlf.write_bytes(("\r\n".join([header] + data_rows) + "\r\n").encode("ascii"))
    variants["crlf"] = p_crlf

    p_nohash = out_dir / "b2_no_hash_header.csv"
    nohash_hdr = header.lstrip("#").strip()
    p_nohash.write_bytes(("\n".join([nohash_hdr] + data_rows) + "\n").encode("ascii"))
    variants["no_hash_header"] = p_nohash

    p_nohdr = out_dir / "b2_no_header.csv"
    p_nohdr.write_bytes(("\n".join(data_rows) + "\n").encode("ascii"))
    variants["no_header"] = p_nohdr

    p_blank = out_dir / "b2_blank_lines.csv"
    bl = [header, ""]
    for i, row in enumerate(data_rows):
        bl.append(row)
        if i in (0, len(data_rows) // 2):
            bl.append("   ")
            bl.append("")
    p_blank.write_bytes(("\n".join(bl) + "\n").encode("ascii"))
    variants["blank_lines"] = p_blank

    p_spaces = out_dir / "b2_spaces_after_commas.csv"
    sp_rows = [", ".join(field.strip() for field in row.split(",")) for row in data_rows]
    p_spaces.write_bytes(("\n".join([header] + sp_rows) + "\n").encode("ascii"))
    variants["spaces_after_commas"] = p_spaces

    p_extra = out_dir / "b2_extra_columns.csv"
    ex_rows = [row + ",42.0,unused" for row in data_rows]
    p_extra.write_bytes(("\n".join([header] + ex_rows) + "\n").encode("ascii"))
    variants["extra_columns"] = p_extra

    return variants


# Inner runner executed inside a clean Python venv (either Windows host venv or Docker Linux venv).
# Uses standard library ONLY so it runs inside any bare Python 3.10-3.14 venv.
_INNER_RUNNER = textwrap.dedent(r'''
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

main_src = Path(sys.argv[1]).resolve()
base_csv = Path(sys.argv[2]).resolve()
variants_dir = Path(sys.argv[3]).resolve()
out_dir = Path(sys.argv[4]).resolve()
out_dir.mkdir(parents=True, exist_ok=True)

py = sys.executable

def sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

def run_case(name: str, args: list[str], cwd: Path, expected_out: Path, use_S: bool = True) -> dict:
    cmd = [py, "-S"] + args if use_S else [py] + args
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=180)
    saved = None
    if expected_out.is_file():
        saved = out_dir / f"{name}.txt"
        shutil.copyfile(expected_out, saved)
    return {
        "case": name,
        "rc": p.returncode,
        "exists": expected_out.is_file(),
        "sha256": sha(saved) if saved else None,
        "saved": str(saved) if saved else None,
        "stderr": p.stderr.strip()[-300:],
    }

results = {
    "python": platform.python_version(),
    "platform": f"{platform.system()} {platform.release()}",
    "b1": [],
    "b2": [],
    "b4": [],
}

with tempfile.TemporaryDirectory(prefix="ag3_run_") as tmp_s:
    tmp = Path(tmp_s)
    solo = tmp / "solo"
    solo.mkdir()
    solo_main = solo / "main.py"
    shutil.copyfile(main_src, solo_main)
    work_other = tmp / "other_cwd"
    work_other.mkdir()

    # B1: standard IN OUT with -S and without -S from another working directory
    o_s = tmp / "o_in_out_S.txt"
    results["b1"].append(run_case("in_out_with_S", [str(solo_main), str(base_csv), str(o_s)], work_other, o_s, use_S=True))
    o_nos = tmp / "o_in_out_noS.txt"
    results["b1"].append(run_case("in_out_no_S", [str(solo_main), str(base_csv), str(o_nos)], work_other, o_nos, use_S=False))

    # B1: IN only (writes estimated_trajectory.txt in cwd)
    c_in = tmp / "cwd_in_only"
    c_in.mkdir()
    results["b1"].append(run_case("in_only", [str(solo_main), str(base_csv)], c_in, c_in / "estimated_trajectory.txt", use_S=True))

    # B1: no args x 4 search orders
    for cname, rel in [
        ("no_args_imu0", "imu0/data.csv"),
        ("no_args_mav0", "mav0/imu0/data.csv"),
        ("no_args_data_csv", "data.csv"),
        ("no_args_single_csv", "flight.csv"),
    ]:
        cdir = tmp / f"cwd_{cname}"
        dst_in = cdir / rel
        dst_in.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base_csv, dst_in)
        results["b1"].append(run_case(cname, [str(solo_main)], cdir, cdir / "estimated_trajectory.txt", use_S=True))

    # B1: IN as a sequence folder (mav0/imu0/data.csv and imu0/data.csv)
    for cname, rel in [("seq_dir_mav0", "mav0/imu0/data.csv"), ("seq_dir_imu0", "imu0/data.csv")]:
        sdir = tmp / f"seq_{cname}"
        dst_in = sdir / rel
        dst_in.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base_csv, dst_in)
        out_f = tmp / f"o_{cname}.txt"
        results["b1"].append(run_case(cname, [str(solo_main), str(sdir), str(out_f)], work_other, out_f, use_S=True))

    # B1: --input/--output and -i/-o
    o_long = tmp / "o_long.txt"
    results["b1"].append(run_case("long_flags", [str(solo_main), "--input", str(base_csv), "--output", str(o_long)], work_other, o_long, use_S=True))
    o_short = tmp / "o_short.txt"
    results["b1"].append(run_case("short_flags", [str(solo_main), "-i", str(base_csv), "-o", str(o_short)], work_other, o_short, use_S=True))

    # B2: formatting variants
    for vpath in sorted(variants_dir.glob("b2_*.csv")):
        vname = vpath.stem
        out_f = tmp / f"o_{vname}.txt"
        results["b2"].append(run_case(vname, [str(solo_main), str(vpath), str(out_f)], work_other, out_f, use_S=True))

    # B4: injected failure fallback
    out_fb = tmp / "o_fallback.txt"
    inject_code = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('solo_main', {str(solo_main)!r})\n"
        "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)\n"
        "def boom(*a, **kw): raise RuntimeError('AG-3 injected failure')\n"
        "mod.run = boom\n"
        f"sys.exit(mod.main(['main.py', {str(base_csv)!r}, {str(out_fb)!r}]))\n"
    )
    p_fb = subprocess.run([py, "-S", "-c", inject_code], cwd=str(work_other), capture_output=True, text=True, timeout=60)
    saved_fb = None
    const_pose = False
    if out_fb.is_file():
        saved_fb = out_dir / "b4_injected_failure.txt"
        shutil.copyfile(out_fb, saved_fb)
        lines = out_fb.read_text(encoding="ascii", errors="replace").splitlines()
        poses = {tuple(ln.split()[1:]) for ln in lines if ln.strip()}
        const_pose = len(lines) > 0 and len(poses) == 1
    results["b4"].append({
        "case": "injected_failure",
        "rc": p_fb.returncode,
        "exists": out_fb.is_file(),
        "constant_pose": const_pose,
        "has_stderr_note": bool(p_fb.stderr.strip()),
        "sha256": sha(saved_fb) if saved_fb else None,
        "saved": str(saved_fb) if saved_fb else None,
        "stderr": p_fb.stderr.strip()[-300:],
    })

    # B4: missing input -> non-zero exit with stderr message
    out_miss = tmp / "o_missing.txt"
    p_miss = subprocess.run([py, "-S", str(solo_main), str(tmp / "does_not_exist.csv"), str(out_miss)],
                            cwd=str(work_other), capture_output=True, text=True, timeout=30)
    results["b4"].append({
        "case": "missing_input",
        "rc": p_miss.returncode,
        "nonzero_exit": p_miss.returncode != 0,
        "has_stderr_note": bool(p_miss.stderr.strip()),
        "stderr": p_miss.stderr.strip()[-300:],
    })

(out_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
''')


def _check_outputs_with_vortex(env_res: dict, base_csv: Path, variants: dict[str, Path], out_dir: Path) -> None:
    """Validate every produced trajectory file with vortex.check_output.check()."""
    b1_ref_sha = None
    for item in env_res["b1"]:
        saved = out_dir / f"{item['case']}.txt"
        if item["rc"] == 0 and saved.is_file():
            chk = check_output.check(str(base_csv), str(saved))
            item["check_ok"] = bool(chk["ok"])
            item["check_errors"] = chk["errors"][:3]
            if item["case"] == "in_out_with_S":
                b1_ref_sha = item["sha256"]
        else:
            item["check_ok"] = False
            item["check_errors"] = [f"rc={item['rc']} exists={item['exists']}"]
    for item in env_res["b1"]:
        item["matches_b1_ref"] = (b1_ref_sha is not None and item["sha256"] == b1_ref_sha)
    env_res["ref_sha256"] = b1_ref_sha

    for item in env_res["b2"]:
        vkey = item["case"].removeprefix("b2_")
        # Compare against base_csv for no_hash_header if repo check_output predates is_text_header(),
        # otherwise validate directly against the variant CSV.
        vcsv = variants[vkey]
        check_ref = base_csv if (vkey == "no_hash_header" and not hasattr(check_output, "data_lines")) else vcsv
        saved = out_dir / f"{item['case']}.txt"
        if item["rc"] == 0 and saved.is_file():
            chk = check_output.check(str(check_ref), str(saved))
            item["check_ok"] = bool(chk["ok"])
            item["check_errors"] = chk["errors"][:3]
        else:
            item["check_ok"] = False
            item["check_errors"] = [f"rc={item['rc']} exists={item['exists']}"]

    for item in env_res["b4"]:
        if item["case"] == "injected_failure":
            saved = out_dir / "b4_injected_failure.txt"
            if item["rc"] == 0 and saved.is_file():
                chk = check_output.check(str(base_csv), str(saved))
                item["check_ok"] = bool(chk["ok"]) and bool(item.get("constant_pose")) and bool(item.get("has_stderr_note"))
                item["check_errors"] = chk["errors"][:3]
            else:
                item["check_ok"] = False
                item["check_errors"] = [f"rc={item['rc']} exists={item['exists']}"]
        elif item["case"] == "missing_input":
            item["check_ok"] = bool(item.get("nonzero_exit")) and bool(item.get("has_stderr_note"))
            item["check_errors"] = [] if item["check_ok"] else [f"rc={item['rc']}"]


def run_host_venv(env_name: str, base_py_cmd: list[str], main_src: Path, base_csv: Path,
                  variants_dir: Path, variants: dict[str, Path], scratch_dir: Path) -> dict:
    env_dir = scratch_dir / env_name
    venv_dir = env_dir / "venv"
    out_dir = env_dir / "out"
    runner_py = env_dir / "inner_runner.py"
    env_dir.mkdir(parents=True, exist_ok=True)
    runner_py.write_text(_INNER_RUNNER, encoding="utf-8")

    subprocess.run(base_py_cmd + ["-m", "venv", "--without-pip", str(venv_dir)], check=True, capture_output=True, text=True)
    venv_py = venv_dir / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    p = subprocess.run(
        [str(venv_py), str(runner_py), str(main_src), str(base_csv), str(variants_dir), str(out_dir)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if p.returncode != 0:
        raise RuntimeError(f"{env_name} runner failed: {p.stderr[-500:]}")
    res = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    res["env"] = env_name
    _check_outputs_with_vortex(res, base_csv, variants, out_dir)
    return res


def run_docker_venv(env_name: str, image: str, main_src: Path, base_csv: Path,
                    variants_dir: Path, variants: dict[str, Path], scratch_dir: Path) -> dict:
    env_dir = scratch_dir / env_name
    out_dir = env_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    runner_py = env_dir / "inner_runner.py"
    runner_py.write_text(_INNER_RUNNER, encoding="utf-8")

    cname = f"vortex-ag3-{env_name.replace('.', '-')}"
    subprocess.run(["docker", "rm", "-f", cname], capture_output=True)
    try:
        subprocess.run(["docker", "run", "-d", "--name", cname, "--entrypoint", "sleep", image, "1800"],
                       check=True, capture_output=True, text=True)
        subprocess.run(["docker", "exec", cname, "sh", "-c", "mkdir -p /tmp/ag3/variants /tmp/ag3/out"],
                       check=True, capture_output=True, text=True)
        subprocess.run(["docker", "cp", str(main_src), f"{cname}:/tmp/ag3/main.py"], check=True, capture_output=True)
        subprocess.run(["docker", "cp", str(base_csv), f"{cname}:/tmp/ag3/base.csv"], check=True, capture_output=True)
        subprocess.run(["docker", "cp", str(runner_py), f"{cname}:/tmp/ag3/inner_runner.py"], check=True, capture_output=True)
        for vpath in variants.values():
            subprocess.run(["docker", "cp", str(vpath), f"{cname}:/tmp/ag3/variants/{vpath.name}"],
                           check=True, capture_output=True)
        cmd = (
            "python -m venv --without-pip /tmp/ag3/venv && "
            "/tmp/ag3/venv/bin/python /tmp/ag3/inner_runner.py /tmp/ag3/main.py /tmp/ag3/base.csv /tmp/ag3/variants /tmp/ag3/out"
        )
        p = subprocess.run(["docker", "exec", cname, "sh", "-c", cmd], capture_output=True, text=True, timeout=600)
        if p.returncode != 0:
            raise RuntimeError(f"{env_name} ({image}) failed: {p.stderr[-500:]}")
        subprocess.run(["docker", "cp", f"{cname}:/tmp/ag3/out/.", str(out_dir)], check=True, capture_output=True)
    finally:
        subprocess.run(["docker", "rm", "-f", cname], capture_output=True)

    res = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    res["env"] = env_name
    res["image"] = image
    _check_outputs_with_vortex(res, base_csv, variants, out_dir)
    return res


def run_dockerfile_image(zip_dir: Path, base_csv: Path, scratch_dir: Path) -> dict:
    """Build the zip's Dockerfile and run its default ENTRYPOINT on a container-local input copy."""
    img = "vortex-ag3-zip-test"
    cname = "vortex-ag3-zip-run"
    out_dir = scratch_dir / "zip-dockerfile" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["docker", "rm", "-f", cname], capture_output=True)
    subprocess.run(["docker", "build", "-q", "-t", img, str(zip_dir)], check=True, capture_output=True, text=True)
    try:
        # Copy input into a container-local /tmp/in.csv, then run ENTRYPOINT's command via docker exec
        # after verifying the image's configured Entrypoint.
        ep_json = subprocess.run(
            ["docker", "inspect", "--format", "{{json .Config.Entrypoint}}", img],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        ep = json.loads(ep_json) or ["python", "-S", "/app/main.py"]
        subprocess.run(["docker", "run", "-d", "--name", cname, "--entrypoint", "sleep", img, "600"],
                       check=True, capture_output=True, text=True)
        subprocess.run(["docker", "cp", str(base_csv), f"{cname}:/tmp/in.csv"], check=True, capture_output=True)
        p = subprocess.run(["docker", "exec", cname] + ep + ["/tmp/in.csv", "/tmp/out.txt"],
                           capture_output=True, text=True, timeout=180)
        py_ver = subprocess.run(["docker", "exec", cname, "python", "-c", "import platform; print(platform.python_version())"],
                                check=True, capture_output=True, text=True).stdout.strip()
        plat = subprocess.run(["docker", "exec", cname, "python", "-c", "import platform; print(platform.system(), platform.release())"],
                              check=True, capture_output=True, text=True).stdout.strip()
        saved = out_dir / "in_out_with_S.txt"
        exists = False
        if p.returncode == 0:
            cp = subprocess.run(["docker", "cp", f"{cname}:/tmp/out.txt", str(saved)], capture_output=True)
            exists = cp.returncode == 0 and saved.is_file()
    finally:
        subprocess.run(["docker", "rm", "-f", cname], capture_output=True)

    chk_ok = False
    chk_errs = [f"rc={p.returncode} exists={exists}"]
    rsha = None
    if exists:
        chk = check_output.check(str(base_csv), str(saved))
        chk_ok = bool(chk["ok"])
        chk_errs = chk["errors"][:3]
        rsha = sha256_file(saved)
    return {
        "env": "zip-dockerfile",
        "image": img,
        "entrypoint": ep,
        "python": py_ver,
        "platform": plat,
        "ref_sha256": rsha,
        "b1": [{
            "case": "in_out_with_S",
            "rc": p.returncode,
            "exists": exists,
            "sha256": rsha,
            "check_ok": chk_ok,
            "check_errors": chk_errs,
            "matches_b1_ref": chk_ok,
            "stderr": p.stderr.strip()[-300:],
        }],
        "b2": [],
        "b4": [],
    }


def format_markdown(report: dict) -> str:
    lines = [
        "# Clean-Machine Matrix (`AG-3`)",
        "",
        f"- **Artifact tested:** `{report['artifact']}` (commit `{report['commit']}`, `src/main.py` SHA-256 `{report['main_sha256'][:16]}`)",
        f"- **Input file:** `{report['input']}`",
        f"- **Cross-version byte identity (`in_out_with_S`):** **{'PASS (all identical)' if report['all_versions_byte_identical'] else 'DIFFERS'}** "
        f"(`{len(report['unique_ref_sha256'])}` unique SHA-256 across `{len(report['environments'])}` environments)",
        "",
        "## 1. Environment Summary",
        "",
        "| Environment | Python | Platform | B1 forms | B2 variants | B4 fallback & missing | `in_out_with_S` SHA-256 (16 hex) | Byte-identical across matrix? |",
        "|---|---|---|---:|---:|---|---|---|",
    ]
    base_sha = report["unique_ref_sha256"][0] if report["unique_ref_sha256"] else None
    for e in report["environments"]:
        b1_ok = sum(1 for x in e["b1"] if x["check_ok"] and x["matches_b1_ref"])
        b2_ok = sum(1 for x in e["b2"] if x["check_ok"])
        b4_ok = sum(1 for x in e["b4"] if x["check_ok"])
        rsha = e.get("ref_sha256") or "-"
        same = "YES" if (base_sha and rsha == base_sha) else "NO"
        lines.append(
            f"| `{e['env']}` | {e['python']} | {e['platform']} | {b1_ok}/{len(e['b1'])} | "
            f"{b2_ok}/{len(e['b2'])} | {b4_ok}/{len(e['b4'])} | `{rsha[:16]}` | {same} |"
        )

    lines += [
        "",
        "## 2. Detailed Case Failures (if any)",
        "",
    ]
    failures = []
    for e in report["environments"]:
        for group in ("b1", "b2", "b4"):
            for item in e[group]:
                ok = item["check_ok"] and (group != "b1" or item.get("matches_b1_ref", True))
                if not ok:
                    failures.append((e["env"], group, item["case"], item.get("rc"), item.get("check_errors"), item.get("stderr")))
    if not failures:
        lines.append("None — all B1, B2, and B4 checks passed on every tested environment.")
    else:
        lines += [
            "| Environment | Group | Case | Exit | Errors | Stderr |",
            "|---|---|---|---:|---|---|",
        ]
        for env, grp, case, rc, errs, err in failures:
            lines.append(f"| `{env}` | {grp} | `{case}` | {rc} | `{errs}` | `{err}` |")
    lines.append("")
    return "\n".join(lines)


def run_matrix(
    main_src: Path,
    base_csv: Path,
    envs: list[str],
    artifact_label: str,
    commit: str,
    zip_dir: Path | None = None,
) -> dict:
    with tempfile.TemporaryDirectory(prefix="vortex_ag3_") as tmp_s:
        tmp = Path(tmp_s)
        variants_dir = tmp / "variants"
        variants_dir.mkdir()
        variants = make_b2_variants(base_csv, variants_dir)

        env_results = []
        for env in envs:
            if env == "host-venv":
                env_results.append(run_host_venv(env, [sys.executable], main_src, base_csv, variants_dir, variants, tmp))
            elif env == "win-venv-3.13":
                env_results.append(run_host_venv(env, ["py", "-3.13"], main_src, base_csv, variants_dir, variants, tmp))
            elif env == "win-venv-3.14":
                env_results.append(run_host_venv(env, ["py", "-3.14"], main_src, base_csv, variants_dir, variants, tmp))
            elif env in DOCKER_IMAGES:
                env_results.append(run_docker_venv(env, DOCKER_IMAGES[env], main_src, base_csv, variants_dir, variants, tmp))
            elif env == "zip-dockerfile":
                if zip_dir is None or not (zip_dir / "Dockerfile").is_file():
                    raise SystemExit("zip-dockerfile requested but no Dockerfile found in --zip")
                env_results.append(run_dockerfile_image(zip_dir, base_csv, tmp))
            elif env.startswith("docker-image:"):
                img = env.split(":", 1)[1]
                env_results.append(run_docker_venv(env, img, main_src, base_csv, variants_dir, variants, tmp))
            else:
                raise SystemExit(f"unknown environment: {env}")

    shas = sorted({e["ref_sha256"] for e in env_results if e.get("ref_sha256")})
    all_passed = all(
        all(x["check_ok"] and x["matches_b1_ref"] for x in e["b1"])
        and all(x["check_ok"] for x in e["b2"])
        and all(x["check_ok"] for x in e["b4"])
        for e in env_results
    )
    return {
        "artifact": artifact_label,
        "commit": commit,
        "main_sha256": sha256_file(main_src),
        "input": str(base_csv),
        "environments": env_results,
        "unique_ref_sha256": shas,
        "all_versions_byte_identical": len(shas) == 1 and all(e.get("ref_sha256") == shas[0] for e in env_results),
        "all_passed": all_passed,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--zip", dest="zip_path", default=None, help="submission zip containing src/main.py")
    ap.add_argument("--main", dest="main_path", default=None, help="path to standalone src/main.py")
    ap.add_argument("--input", required=True, help="IMU CSV input file")
    ap.add_argument(
        "--envs",
        default="win-venv-3.13,win-venv-3.14,docker-3.10,docker-3.11,docker-3.12,docker-3.13,docker-3.14",
        help="comma-separated environments to test",
    )
    ap.add_argument("--commit", default="?", help="commit hash label for the report")
    ap.add_argument("--out", default=None, help="optional Markdown output path (e.g. Docs/CLEAN_MACHINE.md)")
    ap.add_argument("--json", default=None, help="optional JSON output path")
    args = ap.parse_args(argv)

    if bool(args.zip_path) == bool(args.main_path):
        ap.error("provide exactly one of --zip or --main")

    envs = [e.strip() for e in args.envs.split(",") if e.strip()]
    base_csv = Path(args.input).resolve()

    with tempfile.TemporaryDirectory(prefix="vortex_ag3_zip_") as ztmp:
        zip_dir = None
        if args.zip_path:
            zp = Path(args.zip_path).resolve()
            with zipfile.ZipFile(zp) as zf:
                zf.extractall(ztmp)
            zip_dir = Path(ztmp)
            main_src = zip_dir / "src" / "main.py"
            label = zp.name
        else:
            main_src = Path(args.main_path).resolve()
            label = str(main_src)

        report = run_matrix(main_src, base_csv, envs, label, args.commit, zip_dir=zip_dir)

    md = format_markdown(report)
    print(md)
    if args.out:
        out_p = Path(args.out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(md, encoding="utf-8", newline="\n")
    if args.json:
        jp = Path(args.json)
        jp.parent.mkdir(parents=True, exist_ok=True)
        jp.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["all_passed"] and report["all_versions_byte_identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

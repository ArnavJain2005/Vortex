"""Step 7, rule part A and C: the platform detector (pathfinder._plat_stat) on every file on disk outside the
final sets, and byte identity of the output with PLATFORM_ON on EuRoC files. Never reads V2_* or TUM-VI
room5/room6 (the final table). No ground truth is read.

    python tools/platform_check.py [--identity N]    # writes Docs/tumvi/step7-detect.json

--identity N: also run pathfinder.py with PLATFORM_ON off and on on the first N EuRoC official copies
(sorted) and compare the bytes (default 6).
"""
import importlib.util
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINAL = ("V2_", "dataset-room5", "dataset-room6")
SETS = (("euroc", "multirotor", os.path.join(ROOT, "data", "euroc")),
        ("official", "multirotor", os.path.join(ROOT, "data", "official")),
        ("tumvi", "handheld", os.path.join(ROOT, "data", "tumvi")),
        ("official_tumvi", "handheld", os.path.join(ROOT, "data", "official_tumvi")))


def load():
    spec = importlib.util.spec_from_file_location("pf_check", os.path.join(ROOT, "pathfinder.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv):
    n_id = int(argv[argv.index("--identity") + 1]) if "--identity" in argv else 6
    pf = load()
    out = []
    for name, truth, d in SETS:
        if not os.path.isdir(d):
            continue
        for s in sorted(os.listdir(d)):
            if s.startswith(FINAL):
                continue
            imu = os.path.join(d, s, "mav0", "imu0", "data.csv")
            if not os.path.isfile(imu):
                continue
            st = pf._plat_stat(imu)
            got = "handheld" if (st is not None and st < pf.PLAT_HF) else "multirotor"
            out.append({"set": name, "file": s, "truth": truth, "stat": st, "detected": got, "ok": got == truth})
            print("%-15s %-30s %-10s stat %s %s" % (name, s, got, "None" if st is None else "%.4f" % st,
                                                     "ok" if got == truth else "WRONG"), flush=True)
    ident = []
    eu = [r["file"] for r in out if r["set"] == "official"][:n_id]
    tmp = tempfile.mkdtemp(prefix="vortex_plat_")
    for s in eu:
        imu = os.path.join(ROOT, "data", "official", s, "mav0", "imu0", "data.csv")
        res = []
        for on in (False, True):
            pf.PLATFORM_ON = on
            dst = os.path.join(tmp, "%s_%d.txt" % (s, on))
            pf.run(imu, dst)
            with open(dst, "rb") as f:
                res.append(f.read())
        pf.PLATFORM_ON = False
        ident.append({"file": s, "identical": res[0] == res[1]})
        print("identity %-30s %s" % (s, "identical" if res[0] == res[1] else "DIFFERENT"), flush=True)
    eu_stats = [r["stat"] for r in out if r["truth"] == "multirotor" and r["stat"] is not None]
    tv_stats = [r["stat"] for r in out if r["truth"] == "handheld" and r["stat"] is not None]
    summary = {"files": len(out), "wrong": [r["file"] for r in out if not r["ok"]],
               "min_multirotor_stat": min(eu_stats) if eu_stats else None,
               "max_handheld_stat": max(tv_stats) if tv_stats else None,
               "identity": ident, "threshold": pf.PLAT_HF}
    print("files %d, wrong %d, smallest multirotor %.4f, largest hand-held %.4f, threshold %.1f" % (
        len(out), len(summary["wrong"]), summary["min_multirotor_stat"], summary["max_handheld_stat"], pf.PLAT_HF))
    with open(os.path.join(ROOT, "Docs", "tumvi", "step7-detect.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": out}, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Re-measure rule G's reversed-output null on the smoother-on base (Docs/TRACK3_PLAN.md, Step L2,
"Re-measurement ..."). INFORMATIONAL, NOT A RE-JUDGE: rule G's verdict (OFF, 5fd288c) stands as recorded and
the ship decision is rule G2 alone.

    python tools/remeasure_stepG.py [--off stepGR-H-off --on stepGR-H-on --on-rev stepGR-H-on-rev
                                     --off-rev stepGR-H-off-rev --floor stepG-H-floor]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from judge_stepG import SEEDS, SEQS, apem, load, mean  # noqa: E402


def report(off, on, on_rev, off_rev, floor, commits=None):
    H = sorted(off)
    assert len(H) == 36 and set(H) == set(on) == set(on_rev) == set(off_rev) == set(floor), "H: 36 copies per tag"
    assert all(int(n.rsplit("_s", 1)[1]) in SEEDS for n in H), "H must be the seed 10-12 copies"
    if commits:
        print("Builds: " + ", ".join("%s %s" % kv for kv in commits.items()))
    print("| Copies | off | on | on reversed | off reversed | floor | gain off-on | gain reversed |")
    print("|---|---|---|---|---|---|---|---|")
    out = {}
    for lab, ns in (("a", [n for n in H if off[n]["reading"] == "a"]), ("b", [n for n in H if off[n]["reading"] == "b"]),
                    ("both", H)):
        v = [apem(t, ns) for t in (off, on, on_rev, off_rev, floor)]
        out[lab] = v
        print("| %s | %.3f | %.3f | %.3f | %.3f | %.3f | %.3f | %.3f |" % (lab, *v, v[0] - v[1], v[3] - v[2]))
    o, n, nr, orv, f = out["both"]
    print("\nRule G's null (level): on %.3f vs on reversed %.3f m -> %s" % (n, nr, "on below" if n < nr else "on NOT below"))
    print("G2's null form (gain): %.3f vs %.3f m reversed -> %s" % (o - n, orv - nr,
                                                                    "gain larger" if o - n > orv - nr else "gain NOT larger"))
    print("\nPer sequence (mean of 6 copies: a, b x seeds 10-12; paired effect = off - on, m)")
    print("| Sequence | off | on | effect | % | on reversed | off reversed | floor | b off | b on |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for s in SEQS:
        ns = [x for x in H if x.startswith(s)]
        nb = [x for x in ns if off[x]["reading"] == "b"]
        o, n = apem(off, ns), apem(on, ns)
        print("| %s | %.3f | %.3f | %+.3f | %+.1f | %.3f | %.3f | %.3f | %.3f | %.3f |" % (
            s, o, n, o - n, 100 * (o - n) / o, apem(on_rev, ns), apem(off_rev, ns), apem(floor, ns),
            apem(off, nb), apem(on, nb)))
    print("RPE 1 s %.3f -> %.3f; gap %.3f -> %.3f; blind %.3f -> %.3f m" % (
        mean(off, "rpe200_rmse"), mean(on, "rpe200_rmse"), mean(off, "gap_rmse_mean"), mean(on, "gap_rmse_mean"),
        mean(off, "blind_rmse"), mean(on, "blind_rmse")))
    print("INFORMATIONAL re-measurement on a new base; rule G's verdict (OFF, 5fd288c) stands; the decision is G2.")
    return out


def main(argv):
    get = lambda k, d: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    tags = [get("--off", "stepGR-H-off"), get("--on", "stepGR-H-on"), get("--on-rev", "stepGR-H-on-rev"),
            get("--off-rev", "stepGR-H-off-rev"), get("--floor", "stepG-H-floor")]
    import json
    commits = {}
    for t in tags:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Docs", "results",
                               t + ".json"), encoding="utf-8") as f:
            commits[t] = json.load(f).get("commit")
    report(*[load(t) for t in tags], commits=commits)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

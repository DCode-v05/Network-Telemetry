import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))
from eval.tabio import read_csv

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")
rows = read_csv(os.path.join(RESULTS, "agg_detector_window_type.csv"))

NEW = {"ewma_z_hold", "ewmv_hold", "cusum_gated", "page_hinkley_gated",
       "ewmv_gated", "ewmv_hold_gated", "acf_gated"}

for atype in ["spike", "drift", "periodicity", "transient", "real"]:
    sub = [r for r in rows if r["anomaly_type"] == atype]
    # best window per detector by event_f1
    best = {}
    for r in sub:
        d = r["detector"]
        ef = r.get("event_f1") or 0.0
        if d not in best or ef > (best[d].get("event_f1") or 0.0):
            best[d] = r
    ranked = sorted(best.values(), key=lambda r: (r.get("event_f1") or 0.0), reverse=True)
    print("\n=== %s ===  (point_f1 -> event_f1, best window per detector)" % atype)
    print("   %-20s %3s  %7s %8s %9s" % ("detector", "win", "pointF1", "eventF1", "precision"))
    for r in ranked[:8]:
        tag = " *NEW" if r["detector"] in NEW else ""
        star = "  <0.90" if (r.get("event_f1") or 0) < 0.90 else "  >=0.90"
        print("   %-20s %3d  %7.3f %8.3f %9.3f%s%s" % (
            r["detector"], r["window"], r.get("f1") or 0, r.get("event_f1") or 0,
            r.get("event_precision") or 0, star, tag))

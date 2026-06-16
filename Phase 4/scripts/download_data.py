"""Download a curated, network-relevant subset of the Numenta Anomaly Benchmark (NAB).

NAB ships labelled real-world streams; we take the traffic / known-cause families that
most resemble device/network telemetry. Failures are logged loudly and never treated as
success (the plan forbids silent truncation of coverage).

Usage:  python scripts/download_data.py
Writes: data/real/nab/<family>/<file>.csv  and  data/real/nab/combined_windows.json
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

RAW = "https://raw.githubusercontent.com/numenta/NAB/master"

FILES = [
    "realTraffic/occupancy_6005.csv",
    "realTraffic/occupancy_t4013.csv",
    "realTraffic/speed_6005.csv",
    "realTraffic/speed_7578.csv",
    "realTraffic/speed_t4013.csv",
    "realTraffic/TravelTime_387.csv",
    "realTraffic/TravelTime_451.csv",
    "realKnownCause/ec2_request_latency_system_failure.csv",
    "realKnownCause/machine_temperature_system_failure.csv",
    "realKnownCause/cpu_utilization_asg_misconfiguration.csv",
    "realKnownCause/ambient_temperature_system_failure.csv",
    "realKnownCause/nyc_taxi.csv",
    "realKnownCause/rogue_agent_key_hold.csv",
    "realKnownCause/rogue_agent_key_updown.csv",
]

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "data", "real", "nab"))


def _get(url, dest, timeout=60):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "phase4-downloader"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    with open(dest, "wb") as f:
        f.write(data)
    return len(data)


def main():
    os.makedirs(OUT, exist_ok=True)
    ok, fail = [], []

    try:
        n = _get(f"{RAW}/labels/combined_windows.json",
                 os.path.join(OUT, "combined_windows.json"))
        print(f"[ok]   combined_windows.json ({n} bytes)")
    except Exception as e:
        print(f"[FAIL] combined_windows.json -> {e}")
        print("Cannot label NAB streams without the windows file; aborting real download.")
        return 1

    for rel in FILES:
        dest = os.path.join(OUT, rel.replace("/", os.sep))
        try:
            n = _get(f"{RAW}/data/{rel}", dest)
            print(f"[ok]   {rel} ({n} bytes)")
            ok.append(rel)
        except Exception as e:
            print(f"[FAIL] {rel} -> {e}")
            fail.append(rel)

    manifest = {"ok": ok, "failed": fail, "source": "numenta/NAB@master"}
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nDownloaded {len(ok)}/{len(FILES)} files. Failed: {len(fail)}")
    if fail:
        print("Failed files (coverage reduced, logged in manifest.json):", fail)
    return 0


if __name__ == "__main__":
    sys.exit(main())

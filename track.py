#!/usr/bin/env python3
"""
Traffic tracker for Subnet 105 orchestrators.

Snapshots the orchestrators endpoint and appends one compact line per poll to
traffic.jsonl. Diffing consecutive lines gives per-orchestrator traffic RATE
(tasks/hour) and trend — the dashboard reads this for the Δtasks/hr column and
the per-orchestrator sparkline.

Each orchestrator record is [verified_task_count, lifetime_verified_task_count,
verified_transfer_count, verified_bandwidth_mbps, epoch_weight_pct].

Usage:
    python3 track.py                 # one poll, append, exit  (good for cron)
    python3 track.py --loop 600      # poll every 600s until Ctrl+C
    python3 track.py --local         # read data.json instead of fetching live

Cron example (every 10 min):
    */10 * * * * cd /path/to/dashboard && python3 track.py >> track.log 2>&1
"""
import datetime
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = "https://data.b1m.ai/api/dashboard/orchestrators"
OUT = os.path.join(HERE, "traffic.jsonl")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def fetch(local):
    if local:
        return json.load(open(os.path.join(HERE, "data.json")))["orchestrators"]
    req = urllib.request.Request(LIVE, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def poll_once(local=False):
    o = fetch(local)
    rec = {}
    for x in o.get("orchestrators", []):
        rec[str(x["uid"])] = [
            x.get("verified_task_count") or 0,
            x.get("lifetime_verified_task_count") or 0,
            x.get("verified_transfer_count") or 0,
            round(x.get("verified_bandwidth_mbps") or 0, 1),
            round(x.get("epoch_weight_pct") or 0, 4),
        ]
    line = {
        "ts": datetime.datetime.now(datetime.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "we": o.get("weight_epoch"),
        "d": rec,
    }
    with open(OUT, "a") as f:
        f.write(json.dumps(line, separators=(",", ":")) + "\n")
    return len(rec), line["ts"]


def main():
    local = "--local" in sys.argv
    loop = None
    if "--loop" in sys.argv:
        i = sys.argv.index("--loop")
        loop = int(sys.argv[i + 1]) if i + 1 < len(sys.argv) else 600
    while True:
        try:
            n, ts = poll_once(local)
            samples = sum(1 for _ in open(OUT)) if os.path.exists(OUT) else 0
            print(f"[{ts}] polled {n} orchestrators → traffic.jsonl "
                  f"({samples} samples total)")
        except Exception as e:
            print(f"poll failed: {e}", file=sys.stderr)
        if loop is None:
            break
        time.sleep(loop)


if __name__ == "__main__":
    main()

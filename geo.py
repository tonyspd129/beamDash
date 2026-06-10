#!/usr/bin/env python3
"""
Enrich Subnet 105 orchestrators with VPS / hosting details.

Reads each orchestrator's gateway_url, resolves it to an IP (DNS if it's a
hostname), then geolocates the IPs via ip-api.com (provider, ASN, datacenter
flag, country/city). Writes geo.json which the dashboard joins by UID.

Note: the orchestrators' gateway IPs are PUBLIC (already on data.b1m.ai). The
15 "Shared"-gateway orchestrators point at BeamCore's public gateway, not their
own host, and are flagged shared_gateway=true.

Usage:
    python3 geo.py            # fetch live orchestrators, then enrich
    python3 geo.py --local    # use the bundled data.json instead of fetching
"""
import json
import re
import socket
import sys
import time
import urllib.request

HERE_FETCH = "https://data.b1m.ai/api/dashboard/orchestrators"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
FIELDS = ("status,message,query,country,countryCode,regionName,city,"
          "isp,org,as,asname,hosting,proxy,mobile,reverse")
SHARED_GW_IPS = {"8.6.112.0"}  # public-worker-gateway.b1m.ai
HOST_RE = re.compile(r'https?://([^:/]+)')
IPV4_RE = re.compile(r'^\d{1,3}(?:\.\d{1,3}){3}$')


def is_public(ip):
    a = [int(x) for x in ip.split(".")]
    return not (a[0] in (0, 10, 127) or a[0] >= 224
                or (a[0] == 172 and 16 <= a[1] <= 31)
                or (a[0] == 192 and a[1] == 168)
                or (a[0] == 169 and a[1] == 254))


def load_orchestrators(local):
    if local:
        return json.load(open("data.json"))["orchestrators"]["orchestrators"]
    req = urllib.request.Request(HERE_FETCH, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)["orchestrators"]


def geolocate(ips):
    geo = {}
    for i in range(0, len(ips), 100):
        chunk = ips[i:i + 100]
        req = urllib.request.Request(
            f"http://ip-api.com/batch?fields={FIELDS}",
            data=json.dumps(chunk).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            for x in json.load(r):
                if x.get("query"):
                    geo[x["query"]] = x
        print(f"  geolocated batch {i // 100 + 1} ({len(chunk)} IPs)")
        if i + 100 < len(ips):
            time.sleep(4)  # ip-api free rate limit
    return geo


def main():
    local = "--local" in sys.argv
    socket.setdefaulttimeout(3)
    orch = load_orchestrators(local)
    print(f"orchestrators: {len(orch)}")

    uid_ip, types, dns_fail = {}, {}, 0
    for o in orch:
        uid = str(o["uid"])
        types[uid] = o.get("gateway_resolved_type")
        m = HOST_RE.match(o.get("gateway_url") or "")
        if not m:
            continue
        host = m.group(1)
        if IPV4_RE.match(host):
            uid_ip[uid] = host
        else:
            try:
                uid_ip[uid] = socket.gethostbyname(host)
            except Exception:
                dns_fail += 1
    ips = sorted({ip for ip in uid_ip.values() if is_public(ip)})
    print(f"  mapped to IP: {len(uid_ip)} (DNS failures: {dns_fail}) | "
          f"unique public IPs: {len(ips)}")

    geo = geolocate(ips)

    out = {}
    for uid, ip in uid_ip.items():
        g = geo.get(ip)
        shared = types.get(uid) == "public_worker" or ip in SHARED_GW_IPS
        if g and g.get("status") == "success":
            out[uid] = {
                "ip": ip, "shared_gateway": shared,
                "country": g.get("country"), "country_code": g.get("countryCode"),
                "region": g.get("regionName"), "city": g.get("city"),
                "isp": g.get("isp"), "org": g.get("org"),
                "asn": g.get("as"), "asname": g.get("asname"),
                "hosting": bool(g.get("hosting")), "proxy": bool(g.get("proxy")),
                "mobile": bool(g.get("mobile")), "reverse": g.get("reverse") or None,
            }
        else:
            out[uid] = {"ip": ip, "shared_gateway": shared, "unresolved": True}

    import datetime
    meta = {"fetched_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"), "count": len(out)}
    json.dump({"_meta": meta, "by_uid": out}, open("geo.json", "w"))
    prov = sum(1 for v in out.values() if v.get("asname"))
    print(f"geo.json written: {len(out)} enriched, {prov} with provider info, "
          f"{sum(1 for v in out.values() if v.get('shared_gateway'))} shared-gateway")


if __name__ == "__main__":
    main()

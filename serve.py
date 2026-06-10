#!/usr/bin/env python3
"""
Local server for the Subnet 105 orchestrator dashboard.

Serves the static dashboard and proxies the BeamCore dashboard API
(https://data.b1m.ai/api/dashboard/*) so the browser avoids CORS.
On every successful proxy fetch it refreshes data.json as an offline snapshot.

Usage:
    python3 serve.py [port]      # default port 8765
Then open http://localhost:8765
"""
import http.server
import json
import os
import socketserver
import sys
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
HERE = os.path.dirname(os.path.abspath(__file__))
UPSTREAM = "https://data.b1m.ai"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
# only these upstream paths may be proxied
ALLOWED = {"orchestrators", "metrics", "workers"}


def fetch(path: str) -> bytes:
    req = urllib.request.Request(f"{UPSTREAM}/api/dashboard/{path}",
                                 headers={"User-Agent": UA,
                                          "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=HERE, **k)

    def log_message(self, fmt, *args):
        sys.stderr.write("  " + (fmt % args) + "\n")

    def do_GET(self):
        if self.path.startswith("/api/dashboard/"):
            return self._proxy()
        if self.path in ("", "/"):
            self.path = "/index.html"
        return super().do_GET()

    def _proxy(self):
        name = self.path[len("/api/dashboard/"):].split("?")[0].strip("/")
        if name not in ALLOWED:
            self.send_error(404, "unknown endpoint")
            return
        try:
            body = fetch(name)
            self._refresh_snapshot(name, body)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Beam-Source", "live")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            # fall back to the bundled snapshot so the page still works offline
            self._serve_snapshot(name, str(e))

    def _refresh_snapshot(self, name, body):
        path = os.path.join(HERE, "data.json")
        try:
            snap = json.load(open(path)) if os.path.exists(path) else {}
        except Exception:
            snap = {}
        snap[name] = json.loads(body)
        import datetime
        try:
            snap["fetched_at"] = datetime.datetime.now(
                datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass
        try:
            json.dump(snap, open(path, "w"))
        except Exception:
            pass

    def _serve_snapshot(self, name, err):
        try:
            snap = json.load(open(os.path.join(HERE, "data.json")))
            payload = json.dumps(snap.get(name) or {}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Beam-Source", "snapshot")
            self.send_header("X-Beam-Error", err[:200])
            self.end_headers()
            self.wfile.write(payload)
        except Exception:
            self.send_error(502, f"upstream failed and no snapshot: {err}")


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    os.chdir(HERE)
    with Server(("127.0.0.1", PORT), Handler) as httpd:
        print(f"Subnet 105 dashboard → http://localhost:{PORT}")
        print(f"  proxying live API from {UPSTREAM}/api/dashboard/  (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nbye")

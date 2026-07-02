"""Engine server for the Live Pipeline — run the detector in real Python or C,
and capture REAL device / network telemetry.

Endpoints (all CORS-enabled, stdlib only):
  GET  /api/health                         -> {ok, langs, device_ip}
  GET  /api/run?stream=&window=&lang=      -> run a bundled stream (synthetic/NAB) in python|c
  GET  /api/ping?ip=<ipv4>                 -> single ping reachability check {ok, rtt_ms}
  GET  /api/live?source=device|ip&ip=&n=   -> capture live telemetry:
         device -> network throughput (KB/s) sampled from netstat -e
         ip     -> ping round-trip latency (ms) to the target
  POST /api/run_values  {values,window,lang,standardize} -> score arbitrary values in python|c

All engines are parity-identical (Δ = 0). Live capture happens here because a
browser cannot ping or read network counters.

No third-party dependencies. Run:  python server.py   (from Final Pipeline)
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "python"))

from unified_detector import UnifiedDetector          # noqa: E402
from pipeline import CausalStandardizer                # noqa: E402

STREAMS_PATH = os.path.join(HERE, "dashboard", "public", "data", "streams.json")
C_EXE = os.path.join(HERE, "c", "build", "score_cli.exe")
if not os.path.exists(C_EXE):
    C_EXE = os.path.join(HERE, "c", "build", "score_cli")
PORT = int(os.environ.get("ENGINE_PORT", "8008"))
IS_WIN = os.name == "nt"

_STREAMS = {}


def load_streams():
    global _STREAMS
    with open(STREAMS_PATH) as f:
        _STREAMS = {s["id"]: s for s in json.load(f)["streams"]}


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ---------------------------------------------------------------------------
# detector
# ---------------------------------------------------------------------------

def _feed(values, standardize):
    if not standardize:
        return [float(v) for v in values]
    std = CausalStandardizer()
    return [std.push(float(v)) for v in values]


def run_python(fed, window):
    det = UnifiedDetector(window=window)
    scores, heads = [], []
    t0 = time.perf_counter()
    for x in fed:
        s = det.update(x)
        scores.append(round(s, 6))
        heads.append([round(det.s_drv, 5), round(det.s_drift, 5), round(det.s_per, 5)])
    return scores, heads, (time.perf_counter() - t0) * 1000.0


def run_c(fed, window):
    if not os.path.exists(C_EXE):
        raise FileNotFoundError("score_cli not built — run c/build.ps1")
    inp = "\n".join(repr(float(x)) for x in fed) + "\n"
    t0 = time.perf_counter()
    out = subprocess.run([C_EXE, str(window)], input=inp, capture_output=True, text=True, timeout=60)
    dt = (time.perf_counter() - t0) * 1000.0
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "score_cli failed")
    scores, heads = [], []
    for line in out.stdout.splitlines():
        p = line.split()
        if len(p) < 4:
            continue
        scores.append(round(float(p[0]), 6))
        heads.append([round(float(p[1]), 5), round(float(p[2]), 5), round(float(p[3]), 5)])
    return scores, heads, dt


def score_values(values, window, lang, standardize):
    fed = _feed(values, standardize)
    return run_c(fed, window) if lang == "c" else run_python(fed, window)


# ---------------------------------------------------------------------------
# live telemetry capture
# ---------------------------------------------------------------------------

def ping_once(ip):
    """One ICMP echo; return (ok, rtt_ms)."""
    cmd = ["ping", "-n", "1", "-w", "1000", ip] if IS_WIN else ["ping", "-c", "1", "-W", "1", ip]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    m = re.search(r"time[=<]\s*([\d.]+)\s*ms", out)
    ok = ("Reply from" in out or "bytes from" in out) and m is not None
    return ok, (float(m.group(1)) if m else None)


def capture_ping(ip, n):
    """Ping latency time-series (ms). A lost packet is recorded as a 1000 ms spike."""
    vals = []
    t0 = time.perf_counter()
    for _ in range(n):
        ok, rtt = ping_once(ip)
        vals.append(rtt if (ok and rtt is not None) else 1000.0)
    return vals, "ms", (time.perf_counter() - t0) * 1000.0


def _netstat_total_bytes():
    try:
        out = subprocess.run(["netstat", "-e"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            p = line.split()
            if p and p[0].lower() == "bytes" and len(p) >= 3:
                return int(p[1]) + int(p[2])
    except Exception:
        pass
    return None


def capture_device(n, interval=0.12):
    """Device network throughput time-series (KB/s) via netstat byte-counter deltas."""
    vals = []
    last = _netstat_total_bytes()
    t = time.perf_counter()
    t0 = t
    for _ in range(n):
        time.sleep(interval)
        cur = _netstat_total_bytes()
        now = time.perf_counter()
        dt = now - t
        t = now
        kbs = ((cur - last) / 1024.0 / dt) if (cur is not None and last is not None and dt > 0) else 0.0
        vals.append(round(max(0.0, kbs), 3))
        last = cur
    return vals, "KB/s", (time.perf_counter() - t0) * 1000.0


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/api/health":
                return self._send(200, {"ok": True, "device_ip": local_ip(),
                                        "langs": ["python"] + (["c"] if os.path.exists(C_EXE) else [])})

            if u.path == "/api/run":
                sid = q.get("stream", [""])[0]
                lang = q.get("lang", ["python"])[0]
                window = int(q.get("window", ["24"])[0])
                s = _STREAMS.get(sid)
                if not s:
                    return self._send(404, {"error": f"unknown stream '{sid}'"})
                scores, heads, dt = score_values(s["values"], window, lang, s.get("standardize", False))
                return self._send(200, {"lang": lang if lang == "c" else "python", "window": window,
                                        "n": len(scores), "elapsed_ms": round(dt, 2), "scores": scores, "heads": heads})

            if u.path == "/api/ping":
                ip = q.get("ip", [""])[0].strip()
                try:
                    ipaddress.IPv4Address(ip)
                except Exception:
                    return self._send(400, {"ok": False, "error": "not a valid IPv4 address"})
                ok, rtt = ping_once(ip)
                return self._send(200, {"ok": ok, "ip": ip, "rtt_ms": rtt})

            if u.path == "/api/sample":
                # one live sample (for continuous capture)
                source = q.get("source", ["device"])[0]
                if source == "ip":
                    ip = q.get("ip", [""])[0].strip()
                    try:
                        ipaddress.IPv4Address(ip)
                    except Exception:
                        return self._send(400, {"ok": False, "error": "not a valid IPv4 address"})
                    ok, rtt = ping_once(ip)
                    return self._send(200, {"ok": True, "source": "ip", "ip": ip, "unit": "ms",
                                            "value": rtt if (ok and rtt is not None) else 1000.0, "alive": ok})
                b0 = _netstat_total_bytes()
                time.sleep(0.12)
                b1 = _netstat_total_bytes()
                kbs = max(0.0, (b1 - b0) / 1024.0 / 0.12) if (b0 is not None and b1 is not None) else 0.0
                return self._send(200, {"ok": True, "source": "device", "ip": local_ip(),
                                        "unit": "KB/s", "value": round(kbs, 3)})

            if u.path == "/api/live":
                source = q.get("source", ["device"])[0]
                n = max(10, min(300, int(q.get("n", ["60"])[0])))
                if source == "ip":
                    ip = q.get("ip", [""])[0].strip()
                    try:
                        ipaddress.IPv4Address(ip)
                    except Exception:
                        return self._send(400, {"ok": False, "error": "not a valid IPv4 address"})
                    vals, unit, cap = capture_ping(ip, n)
                    return self._send(200, {"ok": True, "source": "ip", "ip": ip, "unit": unit,
                                            "n": len(vals), "capture_ms": round(cap), "values": vals})
                vals, unit, cap = capture_device(n)
                return self._send(200, {"ok": True, "source": "device", "ip": local_ip(), "unit": unit,
                                        "n": len(vals), "capture_ms": round(cap), "values": vals})

            return self._send(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"error": str(e)})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/api/run_values":
            try:
                ln = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(ln) or b"{}")
                values = body.get("values", [])
                window = int(body.get("window", 24))
                lang = body.get("lang", "python")
                standardize = bool(body.get("standardize", True))
                if not values:
                    return self._send(400, {"error": "no values"})
                scores, heads, dt = score_values(values, window, lang, standardize)
                return self._send(200, {"lang": lang if lang == "c" else "python", "n": len(scores),
                                        "elapsed_ms": round(dt, 2), "scores": scores, "heads": heads})
            except Exception as e:  # noqa: BLE001
                return self._send(500, {"error": str(e)})
        return self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass


def main():
    load_streams()
    langs = "python" + (", c" if os.path.exists(C_EXE) else " (c not built)")
    print(f"engine server on http://localhost:{PORT}  ·  device_ip={local_ip()}  ·  engines: {langs}")
    print("  live telemetry: device throughput (netstat) + ping latency. Dashboard auto-detects this.")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()

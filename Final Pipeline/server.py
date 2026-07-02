"""Engine server for the Live Pipeline — run the detector in real Python or C.

The dashboard's Live Pipeline lets you pick the execution engine. JS runs in the
browser; Python and C are executed HERE by this tiny stdlib HTTP server:

  * lang=python -> imports the standalone unified_detector and streams the signal
  * lang=c      -> pipes the signal through the compiled c/build/score_cli.exe

Both apply the same causal standardization the browser uses, so all three engines
produce identical scores (parity Δ = 0) — the point is you can prove it runs in
each language, and see the real per-language execution time.

No third-party dependencies. Run:  python server.py   (from Final Pipeline)
Then open the dashboard; the Live Pipeline auto-detects the server on :8008.
"""

from __future__ import annotations

import json
import os
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

_STREAMS = {}


def load_streams():
    global _STREAMS
    with open(STREAMS_PATH) as f:
        doc = json.load(f)
    _STREAMS = {s["id"]: s for s in doc["streams"]}


def _feed(values, standardize):
    """Apply the same causal z-score the browser uses (or pass raw)."""
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
    dt = (time.perf_counter() - t0) * 1000.0
    return scores, heads, dt


def run_c(fed, window):
    if not os.path.exists(C_EXE):
        raise FileNotFoundError("score_cli not built — run c/build.ps1")
    inp = "\n".join(repr(float(x)) for x in fed) + "\n"
    t0 = time.perf_counter()
    out = subprocess.run([C_EXE, str(window)], input=inp, capture_output=True,
                         text=True, timeout=60)
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
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/health":
            return self._send(200, {"ok": True, "langs": ["python"] + (["c"] if os.path.exists(C_EXE) else [])})
        if u.path == "/api/run":
            q = parse_qs(u.query)
            sid = q.get("stream", [""])[0]
            lang = q.get("lang", ["python"])[0]
            window = int(q.get("window", ["24"])[0])
            s = _STREAMS.get(sid)
            if not s:
                return self._send(404, {"error": f"unknown stream '{sid}'"})
            try:
                fed = _feed(s["values"], s.get("standardize", False))
                if lang == "c":
                    scores, heads, dt = run_c(fed, window)
                else:
                    lang = "python"
                    scores, heads, dt = run_python(fed, window)
                return self._send(200, {"lang": lang, "window": window, "n": len(scores),
                                        "elapsed_ms": round(dt, 2), "scores": scores, "heads": heads})
            except Exception as e:  # noqa: BLE001
                return self._send(500, {"error": str(e)})
        return self._send(404, {"error": "not found"})

    def log_message(self, *a):  # quiet
        pass


def main():
    load_streams()
    langs = "python" + (", c" if os.path.exists(C_EXE) else " (c not built)")
    print(f"engine server on http://localhost:{PORT}  ·  streams={len(_STREAMS)}  ·  engines: {langs}")
    print("  the dashboard Live Pipeline will detect this automatically.")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()

"""Vercel serverless — POST /api/verify — validates adauto license keys."""
import sys, os, json, hashlib
from http.server import BaseHTTPRequestHandler

_API_DIR = os.path.dirname(__file__)
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

KEY_PREFIX = "ADTO"
SALT       = "adauto-2026-salt"

def _process(body: dict) -> tuple[int, dict]:
    key = body.get("key", "").upper().strip()

    if not key.startswith(KEY_PREFIX + "-"):
        return 400, {"valid": False, "message": "Invalid key prefix"}

    parts = key.split("-")
    if len(parts) != 5 or not all(len(p) == 5 for p in parts[1:]):
        return 400, {"valid": False, "message": "Invalid key format"}

    # Check KV store for revocation
    try:
        from kv import kv_get
        revoked = kv_get(f"revoked:{key}")
        if revoked:
            return 200, {"valid": False, "message": "Key revoked"}
        tier = kv_get(f"tier:{key}") or "standard"
    except Exception:
        tier = "standard"

    return 200, {"valid": True, "key": key, "tier": tier, "message": "OK"}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = {}
        if length:
            try:
                body = json.loads(self.rfile.read(length))
            except Exception:
                pass
        status, result = _process(body)
        self._respond(status, result)

    def do_GET(self):
        self._respond(200, {"service": "adauto-verify", "status": "ok"})

    def _respond(self, status: int, data: dict) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_): pass

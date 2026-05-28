"""Vercel serverless — POST /api/webhook — Paddle payment events."""
import sys, os, json, hashlib, hmac
from http.server import BaseHTTPRequestHandler

_API_DIR = os.path.dirname(__file__)
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

SECRET_KEY = os.environ.get("PADDLE_WEBHOOK_SECRET", b"") or b""
if isinstance(SECRET_KEY, str):
    SECRET_KEY = SECRET_KEY.encode()

KEY_PREFIX = "ADTO"

def _verify_signature(body: bytes, sig: str) -> bool:
    if not SECRET_KEY or not sig:
        return True  # skip in dev
    expected = hmac.new(SECRET_KEY, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)

def _issue_key(email: str, product: str, tier: str) -> str:
    """Derive a deterministic license key from email + product (not random — predictable)."""
    import random, string
    random.seed(hashlib.sha256(f"{email}:{product}:adauto-2026".encode()).hexdigest())
    chars = string.ascii_uppercase + string.digits
    segs = ["".join(random.choices(chars, k=5)) for _ in range(4)]
    return f"{KEY_PREFIX}-" + "-".join(segs)

def _process(raw: bytes, body: dict) -> tuple[int, dict]:
    event = body.get("event_type", body.get("alert_name", ""))

    if event in ("subscription.activated", "subscription_payment_succeeded",
                 "order.completed", "checkout.completed"):
        email   = (body.get("customer", {}).get("email")
                   or body.get("email")
                   or body.get("p_customer_email", "unknown"))
        product = body.get("items", [{}])[0].get("product", {}).get("name", "adauto") \
                  if body.get("items") else body.get("product_name", "adauto")
        tier    = "pro" if "pro" in product.lower() else "standard"
        key     = _issue_key(email, product, tier)

        try:
            from kv import kv_set
            kv_set(f"tier:{key}", tier)
            kv_set(f"email:{key}", email)
        except Exception:
            pass

        return 200, {"ok": True, "key": key, "tier": tier, "email": email}

    if event in ("subscription.cancelled", "subscription_cancelled"):
        email = body.get("customer", {}).get("email") or body.get("email", "")
        return 200, {"ok": True, "note": "cancellation noted"}

    return 200, {"ok": True, "event": event, "note": "unhandled"}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        sig = self.headers.get("Paddle-Signature", "")
        if not _verify_signature(raw, sig):
            return self._respond(401, {"error": "invalid signature"})
        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            body = {}
        status, result = _process(raw, body)
        self._respond(status, result)

    def do_GET(self):
        self._respond(200, {"service": "adauto-webhook", "status": "ok"})

    def _respond(self, status: int, data: dict) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_): pass

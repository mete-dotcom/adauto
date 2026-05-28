"""Vercel KV store wrapper — uses env vars set in Vercel dashboard."""
import os
import json

try:
    from vercel_kv import kv as _kv
    def kv_set(key: str, value) -> None:
        _kv.set(key, json.dumps(value))
    def kv_get(key: str):
        v = _kv.get(key)
        return json.loads(v) if v else None
except ImportError:
    # Fallback: use Upstash REST API directly
    import urllib.request

    def _upstash(cmd: list):
        url   = os.environ.get("KV_REST_API_URL", "")
        token = os.environ.get("KV_REST_API_TOKEN", "")
        if not url:
            return None
        req = urllib.request.Request(
            f"{url}/{'/'.join(str(c) for c in cmd)}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())["result"]

    def kv_set(key: str, value) -> None:
        _upstash(["SET", key, json.dumps(value)])

    def kv_get(key: str):
        v = _upstash(["GET", key])
        return json.loads(v) if v else None

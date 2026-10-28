"""GET/POST /api/track: the outreach tracker, kept in a private Vercel Blob so every device sees the same history.

Needs BLOB_READ_WRITE_TOKEN (Vercel sets it when the Blob store is linked; locally: vercel env pull).
"""
import hmac, json, os, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler

API = "https://blob.vercel-storage.com"
_PW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".site_password")
_ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env.local")


def authed(headers):
    want = os.environ.get("SITE_PASSWORD") or (open(_PW).read().strip() if os.path.exists(_PW) else "")
    return bool(want) and hmac.compare_digest(str(headers.get("X-Pass", "")), want)


def token():
    t = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not t and os.path.exists(_ENV):
        for line in open(_ENV):
            if line.startswith("BLOB_READ_WRITE_TOKEN="):
                t = line.split("=", 1)[1].strip().strip('"')
    return t or ""


def call(method, url, data=None, extra=None):
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": "Bearer " + token(), "x-api-version": "12", **(extra or {})})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


def blobs():
    return json.loads(call("GET", f"{API}/?" + urllib.parse.urlencode({"prefix": "tracker/", "limit": 1000})))["blobs"]


def load():
    # one new file per save (tracker/<ms>.json), newest wins: an overwritten blob can be served stale from the CDN, a new one can't
    try:
        found = sorted(blobs(), key=lambda b: b["pathname"])
        return json.loads(call("GET", found[-1]["url"])) if found else {}
    except Exception:
        return {}


def save(data):
    cur = load(); cur.update(data)   # merge, so a device with older data can't wipe another device's history
    old = blobs()
    call("PUT", f"{API}/?" + urllib.parse.urlencode({"pathname": f"tracker/{int(time.time() * 1000)}.json"}), json.dumps(cur).encode(),
         {"x-vercel-blob-access": "private", "x-add-random-suffix": "0", "content-type": "application/json"})
    if old:
        call("POST", f"{API}/delete", json.dumps({"urls": [b["url"] for b in old]}).encode(), {"content-type": "application/json"})
    return cur


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        self._send(*((200, load()) if authed(self.headers) else (401, {})))

    def do_POST(self):
        if not authed(self.headers):
            return self._send(401, {})
        try:
            self._send(200, save(json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")))
        except Exception as e:
            self._send(500, {"error": str(e)[:200]})

"""POST /api/draft  {to, subject, body} -> saves a draft in the Gmail account's Drafts via IMAP.

Needs GMAIL_APP_PASSWORD (a Google app password) in the environment, or a .gmail_app_password file next to the repo root locally.
"""
import hmac, imaplib, json, os, time
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler

ME = os.environ.get("GMAIL_USER", "")
ACCFILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".gmail_accounts.json")
PWFILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".gmail_app_password")

_PW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".site_password")


def authed(headers):
    # site password: SITE_PASSWORD env var (Vercel) or a .site_password file (local); the page sends it as X-Pass
    want = os.environ.get("SITE_PASSWORD") or (open(_PW).read().strip() if os.path.exists(_PW) else "")
    return bool(want) and hmac.compare_digest(str(headers.get("X-Pass", "")), want)


def accounts():
    """Sending accounts in fill order: GMAIL_ACCOUNTS env (JSON) or .gmail_accounts.json, else the single app-password account."""
    raw = os.environ.get("GMAIL_ACCOUNTS") or (open(ACCFILE).read() if os.path.exists(ACCFILE) else "")
    if raw:
        return json.loads(raw)
    pw = os.environ.get("GMAIL_APP_PASSWORD") or (open(PWFILE).read().strip() if os.path.exists(PWFILE) else "")
    return [{"email": ME, "password": pw, "cap": 20}] if pw else []


def make_draft(to, subject, body, used=None):
    accts = accounts()
    if not accts:
        return 501, {"ok": False, "error": "no app password"}
    used = used or {}
    first = accts[0]["email"]
    # drafts made before accounts were tracked have no account name; they were all from the first one
    count = lambda a: used.get(a, 0) + (used.get("", 0) if a == first else 0)
    pick = next((a for a in accts if count(a["email"]) < a.get("cap", 20)), None)
    if not pick:
        return 429, {"ok": False, "error": "Every account is at today's limit. Pick it up again tomorrow."}
    m = EmailMessage(); m["From"] = pick["email"]; m["Reply-To"] = first; m["To"] = to; m["Subject"] = subject; m.set_content(body)
    err = ""
    for _ in range(2):   # Gmail IMAP sometimes stalls from serverless; a short timeout plus one retry beats hanging until the function dies
        try:
            imap = imaplib.IMAP4_SSL("imap.gmail.com", timeout=9); imap.login(pick["email"], pick["password"].replace(" ", ""))
            imap.append("[Gmail]/Drafts", "\\Draft", imaplib.Time2Internaldate(time.time()), m.as_bytes()); imap.logout()
            return 200, {"ok": True, "account": pick["email"]}
        except Exception as e:
            err = str(e)[:200] or type(e).__name__
    return 500, {"ok": False, "error": "Gmail didn't respond (" + err + "). Try again."}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        ok = authed(self.headers)
        body = json.dumps([{"email": a["email"], "cap": a.get("cap", 20)} for a in accounts()] if ok else []).encode()
        self.send_response(200 if ok else 401); self.send_header("Content-Type", "application/json"); self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        try:
            if not authed(self.headers):
                raise PermissionError("Wrong password")
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            status, body = make_draft(d["to"], d["subject"], d["body"], d.get("used"))
        except Exception as e:
            status, body = (401 if isinstance(e, PermissionError) else 400), {"ok": False, "error": str(e)}
        data = json.dumps(body).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(data)

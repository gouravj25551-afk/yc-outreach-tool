#!/usr/bin/env python3
"""Run the site locally: python3 serve.py  ->  http://localhost:8765

Serves index.html and routes /api/yc to the same handler Vercel runs.
"""
import os, sys, json, time, imaplib
from email.message import EmailMessage
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "api"))
import yc, draft, track
from draft import authed

ME = os.environ.get("GMAIL_USER", "")
PWFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".gmail_app_password")
TRACK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracker.json")

class Handler(SimpleHTTPRequestHandler):
    def reply(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_POST(self):
        if not authed(self.headers):
            return self.reply(401, {"ok": False, "error": "Wrong password"})
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/api/track":
            return self.reply(200, track.save(data))
        if self.path == "/api/draft":
            code, body = draft.make_draft(data["to"], data["subject"], data["body"], data.get("used"), data.get("in_reply_to"), data.get("quote"))
            return self.reply(code, body)
        self.send_error(404)

    def do_GET(self):
        if self.path == "/api/draft":
            return draft.handler.do_GET(self)
        if self.path == "/api/track":
            if not authed(self.headers):
                return self.reply(401, {})
            return self.reply(200, track.load())
        if self.path.startswith("/api/yc"):
            return yc.handler.do_GET(self)
        if self.path.startswith("/api/"):
            return self.send_error(404)
        return super().do_GET()

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    port = int(os.environ.get("PORT", 8765))
    print(f"http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()

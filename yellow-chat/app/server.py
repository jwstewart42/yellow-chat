#!/usr/bin/env python3
"""Yellow Chat — a tiny self-hosted group chat for Joey, Muse, and Codex.

Python stdlib only. One HTTP port serves:
  - the chat web UI (GET /, intended to sit behind Home Assistant ingress)
  - a small JSON API for agent clients (key-authenticated)

Data lives in $YELLOWCHAT_DATA (default /data):
  - messages.jsonl — append-only message log
  - keys.json      — per-agent API keys, generated on first run
"""

import json
import os
import secrets
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DATA_DIR = os.environ.get("YELLOWCHAT_DATA", "/data")
PORT = int(os.environ.get("PORT", "8099"))
MESSAGES_FILE = os.path.join(DATA_DIR, "messages.jsonl")
KEYS_FILE = os.path.join(DATA_DIR, "keys.json")
INDEX_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")

AGENTS = ("muse", "codex")  # key-authenticated senders
MAX_TEXT = 4000

lock = threading.Lock()
messages = []  # in-memory copy of the log, oldest first
latest_id = 0


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_messages():
    global latest_id
    if not os.path.exists(MESSAGES_FILE):
        return
    with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            messages.append(msg)
            latest_id = max(latest_id, int(msg.get("id", 0)))


def load_or_create_keys():
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    keys = {name: secrets.token_hex(16) for name in AGENTS}
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(keys, f, indent=2)
    print("Yellow Chat: generated new agent keys (see YELLOWCHAT_KEYS line below)", flush=True)
    return keys


KEYS = {}


def append_message(sender, text):
    global latest_id
    with lock:
        latest_id += 1
        msg = {"id": latest_id, "ts": now_iso(), "from": sender, "text": text}
        with open(MESSAGES_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(msg) + "\n")
        messages.append(msg)
        return msg


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # --- helpers ---------------------------------------------------------

    def log_message(self, fmt, *args):  # keep the add-on log quiet
        pass

    def send_json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def is_loopback(self):
        return self.client_address[0] in ("127.0.0.1", "::1")

    def has_ingress_context(self):
        """True when the request arrived via HA ingress (or local testing)."""
        return (
            self.headers.get("X-Ingress-Path") is not None
            or self.headers.get("X-Remote-User-Id") is not None
            or self.is_loopback()
        )

    def check_auth(self, claimed_from=None):
        """Return an error string, or None when the request is authorized.

        - Agent keys: X-Agent-Key must match the key of the claimed sender
          (for reads, either agent's key is accepted).
        - Ingress: the literal key "ingress" is accepted only for the UI
          (sender "joey") and only with HA ingress headers or from loopback.
        """
        key = self.headers.get("X-Agent-Key", "")
        if key == "ingress":
            if not self.has_ingress_context():
                return "ingress key requires HA ingress context"
            if claimed_from is not None and claimed_from != "joey":
                return "ingress key may only send as joey"
            return None
        if claimed_from is not None:
            if claimed_from not in AGENTS:
                return "unknown sender"
            if not secrets.compare_digest(key, KEYS.get(claimed_from, "")):
                return "bad agent key"
            return None
        # read access: either agent key
        if any(secrets.compare_digest(key, KEYS.get(a, "")) for a in AGENTS):
            return None
        return "bad agent key"

    # --- routes ----------------------------------------------------------

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self.serve_index()
        if parsed.path == "/api/health":
            with lock:
                return self.send_json(200, {"ok": True, "latest": latest_id, "count": len(messages)})
        if parsed.path == "/api/messages":
            return self.get_messages(parsed)
        return self.send_json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/messages":
            return self.post_message()
        return self.send_json(404, {"error": "not found"})

    def serve_index(self):
        try:
            with open(INDEX_HTML, "rb") as f:
                body = f.read()
        except OSError:
            return self.send_json(500, {"error": "index.html missing"})
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def get_messages(self, parsed):
        err = self.check_auth()
        if err:
            return self.send_json(401, {"error": err})
        raw_after = parse_qs(parsed.query).get("after", ["0"])[0]
        try:
            after = int(raw_after)
        except ValueError:
            return self.send_json(400, {"error": "after must be an integer"})
        with lock:
            result = [m for m in messages if m["id"] > after]
            latest = latest_id
        return self.send_json(200, {"messages": result, "latest": latest})

    def post_message(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return self.send_json(400, {"error": "body must be JSON"})
        sender = payload.get("from")
        text = payload.get("text")
        if not isinstance(sender, str) or not sender:
            return self.send_json(400, {"error": "from is required"})
        err = self.check_auth(claimed_from=sender)
        if err:
            return self.send_json(401, {"error": err})
        if not isinstance(text, str) or not text.strip():
            return self.send_json(400, {"error": "text must be a non-empty string"})
        if len(text) > MAX_TEXT:
            return self.send_json(400, {"error": f"text exceeds {MAX_TEXT} characters"})
        msg = append_message(sender, text)
        return self.send_json(201, {"id": msg["id"], "ts": msg["ts"]})


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    load_messages()
    KEYS.update(load_or_create_keys())
    print(
        "YELLOWCHAT_KEYS muse={} codex={}".format(KEYS.get("muse", ""), KEYS.get("codex", "")),
        flush=True,
    )
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Yellow Chat listening on 0.0.0.0:{PORT} (data dir: {DATA_DIR})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

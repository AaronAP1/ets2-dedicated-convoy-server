#!/usr/bin/env python3
"""
ETS2/ATS convoy server monitor.

Reads the dedicated server log file (read-only) and exposes:
  - An HTTP JSON API: connected count, current player list, recent events.
  - Optional Discord webhook notifications on player connect / disconnect.

Pure standard library. No external dependencies.

Real log format this parser is built for:
  03:09:04.638 : [MP] State: running;  Time: 11344626;  Players: 7
  00:05:12.106 : [MP] [JDT] Bless. connected, client_id = 10
  00:15:04.311 : [MP] [JDT] Bless. disconnected, client_id = 10
"""

import json
import os
import re
import sys
import threading
import time
import urllib.request
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# --------------------------------------------------------------------------- #
# Configuration (all via environment variables)
# --------------------------------------------------------------------------- #
LOG_FILE = os.getenv("MONITOR_LOG_FILE", "/logs/server.log.txt")
API_HOST = os.getenv("MONITOR_HOST", "0.0.0.0")
API_PORT = int(os.getenv("MONITOR_PORT", "8080"))
# Optional bearer token to protect the HTTP API. Empty = open (no auth).
API_TOKEN = os.getenv("MONITOR_TOKEN", "").strip()
# Discord webhook URL. Empty = notifications disabled.
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
SERVER_NAME = os.getenv("MONITOR_SERVER_NAME", "ETS2 Server").strip()
# How many recent events to keep in memory / expose.
MAX_EVENTS = int(os.getenv("MONITOR_MAX_EVENTS", "200"))
POLL_INTERVAL = float(os.getenv("MONITOR_POLL_INTERVAL", "1.0"))


# --------------------------------------------------------------------------- #
# Log line patterns
# --------------------------------------------------------------------------- #
# A player joined / left. The clean event always carries a client_id.
# [Chat] duplicates never carry a client_id, so requiring it filters them out.
EVENT_RE = re.compile(
    r"^(?P<ts>\d\d:\d\d:\d\d\.\d+)\s*:\s*\[MP\]\s+"
    r"(?P<name>.+?)\s+(?P<action>connected|disconnected),\s*client_id\s*=\s*(?P<cid>\d+)\s*$"
)

# Authoritative periodic count line.
STATE_RE = re.compile(
    r"^(?P<ts>\d\d:\d\d:\d\d\.\d+)\s*:\s*\[MP\]\s+State:\s*(?P<state>\w+);\s*"
    r"Time:\s*(?P<time>\d+);\s*Players:\s*(?P<players>\d+)"
)


# --------------------------------------------------------------------------- #
# Shared state
# --------------------------------------------------------------------------- #
class Monitor:
    def __init__(self):
        self.lock = threading.Lock()
        # client_id -> {"name": str, "since": iso-ts, "log_ts": str}
        self.connected: dict[str, dict] = {}
        # Authoritative "Players: N" from the server's periodic State line.
        self.authoritative_count: int | None = None
        self.server_state: str | None = None
        self.last_state_log_ts: str | None = None
        self.last_update: str | None = None
        self.peak: int = 0
        self.started_at = _now_iso()
        self.events: deque = deque(maxlen=MAX_EVENTS)

    def snapshot(self) -> dict:
        with self.lock:
            players = sorted(
                (
                    {"client_id": cid, "name": info["name"], "since": info["since"]}
                    for cid, info in self.connected.items()
                ),
                key=lambda p: p["name"].lower(),
            )
            # Prefer the server's own authoritative number; fall back to the
            # reconstructed set if we haven't seen a State line yet.
            count = (
                self.authoritative_count
                if self.authoritative_count is not None
                else len(players)
            )
            return {
                "server_name": SERVER_NAME,
                "connected_count": count,
                "tracked_players": len(players),
                "players": players,
                "server_state": self.server_state,
                "peak_since_start": self.peak,
                "last_state_log_ts": self.last_state_log_ts,
                "last_update": self.last_update,
                "monitor_started_at": self.started_at,
                "time": _now_iso(),
            }

    def recent_events(self, limit: int) -> list:
        with self.lock:
            items = list(self.events)
        return items[-limit:][::-1]  # newest first


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


MON = Monitor()


# --------------------------------------------------------------------------- #
# Discord notifications
# --------------------------------------------------------------------------- #
def send_discord(action: str, name: str, count: int):
    if not DISCORD_WEBHOOK_URL:
        return
    if action == "connected":
        title = "🟢 Jugador conectado"
        color = 0x2ECC71
    else:
        title = "🔴 Jugador desconectado"
        color = 0xE74C3C

    payload = {
        "embeds": [
            {
                "title": title,
                "color": color,
                "fields": [
                    {"name": "Jugador", "value": name[:256] or "?", "inline": True},
                    {"name": "Conectados", "value": str(count), "inline": True},
                ],
                "footer": {"text": SERVER_NAME},
                "timestamp": _now_iso(),
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as exc:  # noqa: BLE001 - never let Discord break the tailer
        print(f"[WARN] Discord notification failed: {exc}", flush=True)


def notify_async(action: str, name: str, count: int):
    threading.Thread(
        target=send_discord, args=(action, name, count), daemon=True
    ).start()


# --------------------------------------------------------------------------- #
# Log processing
# --------------------------------------------------------------------------- #
def process_line(line: str, live: bool):
    """Update state from a single log line.

    live=False during the initial replay of existing log content (no Discord
    spam for historical events); live=True for lines read as they arrive.
    """
    state_match = STATE_RE.match(line)
    if state_match:
        with MON.lock:
            MON.authoritative_count = int(state_match.group("players"))
            MON.server_state = state_match.group("state")
            MON.last_state_log_ts = state_match.group("ts")
            MON.last_update = _now_iso()
            if MON.authoritative_count > MON.peak:
                MON.peak = MON.authoritative_count
        return

    event_match = EVENT_RE.match(line)
    if not event_match:
        return

    action = event_match.group("action")
    name = event_match.group("name").strip()
    cid = event_match.group("cid")
    log_ts = event_match.group("ts")

    with MON.lock:
        if action == "connected":
            MON.connected[cid] = {
                "name": name,
                "since": _now_iso(),
                "log_ts": log_ts,
            }
        else:
            MON.connected.pop(cid, None)
        count = (
            MON.authoritative_count
            if MON.authoritative_count is not None
            else len(MON.connected)
        )
        MON.last_update = _now_iso()
        if live:
            MON.events.append(
                {
                    "action": action,
                    "name": name,
                    "client_id": cid,
                    "log_ts": log_ts,
                    "time": _now_iso(),
                    "connected_count": count,
                }
            )

    if live:
        print(f"[EVENT] {action}: {name} (client_id={cid}) -> {count}", flush=True)
        notify_async(action, name, count)


def tail_log():
    """Continuously follow the log file, tolerating rotation/truncation."""
    print(f"[INFO] Waiting for log file: {LOG_FILE}", flush=True)
    while not os.path.isfile(LOG_FILE):
        time.sleep(2)

    while True:
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as fh:
                # Initial replay: rebuild state silently from existing content.
                for line in fh:
                    process_line(line, live=False)
                print(
                    f"[INFO] Initial replay done. Tracked players: "
                    f"{len(MON.connected)}, authoritative count: "
                    f"{MON.authoritative_count}",
                    flush=True,
                )
                pos = fh.tell()
                inode = os.fstat(fh.fileno()).st_ino

                # Live follow.
                while True:
                    line = fh.readline()
                    if line:
                        pos = fh.tell()
                        process_line(line, live=True)
                        continue

                    time.sleep(POLL_INTERVAL)

                    # Detect truncation or rotation (server restart / new log).
                    try:
                        size = os.path.getsize(LOG_FILE)
                        cur_inode = os.stat(LOG_FILE).st_ino
                    except FileNotFoundError:
                        break  # reopen from scratch

                    if cur_inode != inode or size < pos:
                        print(
                            "[INFO] Log rotated/truncated. Resetting state.",
                            flush=True,
                        )
                        with MON.lock:
                            MON.connected.clear()
                            MON.authoritative_count = None
                            MON.server_state = None
                        break  # reopen and replay
        except Exception as exc:  # noqa: BLE001 - keep the tailer alive
            print(f"[WARN] Tailer error: {exc}. Retrying in 3s.", flush=True)
            time.sleep(3)


# --------------------------------------------------------------------------- #
# HTTP API
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict | list):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        if not API_TOKEN:
            return True
        header = self.headers.get("Authorization", "")
        return header == f"Bearer {API_TOKEN}"

    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"

        if path == "/health":
            self._json(200, {"status": "ok", "time": _now_iso()})
            return

        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return

        if path in ("/", "/status"):
            self._json(200, MON.snapshot())
            return

        if path == "/players":
            snap = MON.snapshot()
            self._json(
                200,
                {
                    "connected_count": snap["connected_count"],
                    "players": snap["players"],
                    "time": snap["time"],
                },
            )
            return

        if path == "/events":
            limit = 50
            if "?" in self.path:
                query = self.path.split("?", 1)[1]
                for part in query.split("&"):
                    if part.startswith("limit="):
                        try:
                            limit = max(1, min(MAX_EVENTS, int(part[6:])))
                        except ValueError:
                            pass
            self._json(200, {"events": MON.recent_events(limit), "time": _now_iso()})
            return

        self._json(
            404,
            {
                "error": "not_found",
                "endpoints": ["/health", "/status", "/players", "/events"],
            },
        )

    def log_message(self, *args):  # silence default request logging
        return


class QuietHTTPServer(ThreadingHTTPServer):
    """HTTP server that ignores benign client disconnects (internet scanners/bots
    hitting the public port with malformed requests) instead of dumping a traceback."""

    daemon_threads = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return  # el cliente cerró la conexión; nada que hacer
        print(f"[WARN] Error atendiendo request de {client_address}: {exc}", flush=True)


def main():
    # Player names contain emojis / unicode; never let a print crash the tailer.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    threading.Thread(target=tail_log, daemon=True).start()
    server = QuietHTTPServer((API_HOST, API_PORT), Handler)
    print(
        f"[INFO] Monitor API on http://{API_HOST}:{API_PORT} "
        f"(auth={'on' if API_TOKEN else 'off'}, "
        f"discord={'on' if DISCORD_WEBHOOK_URL else 'off'})",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()

#!/usr/bin/python3

import json
import os
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer


LOG_PATH = os.getenv(
    "ETS_SERVER_LOG_FILE",
    "/home/steam/.local/share/Euro Truck Simulator 2/server.log.txt",
)
API_HOST = os.getenv("ETS_STATUS_API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("ETS_STATUS_API_PORT", "8080"))
API_PATH = os.getenv("ETS_STATUS_API_PATH", "/active-users")


EXPLICIT_ACTIVE_PATTERNS = [
    re.compile(r"\\[MP\\].*?(?:active|connected|online)\\s+(?:players|clients?)\\s*[:=]\\s*(\\d+)", re.IGNORECASE),
    re.compile(r"\\[MP\\].*?(?:players|clients?)\\s*[:=]\\s*(\\d+)\\s*/\\s*\\d+", re.IGNORECASE),
]

JOIN_EVENT_PATTERNS = [
    re.compile(r"\\[MP\\].*\\b(joined|connected)\\b", re.IGNORECASE),
]

LEAVE_EVENT_PATTERNS = [
    re.compile(r"\\[MP\\].*\\b(left|disconnected)\\b", re.IGNORECASE),
]


def _load_lines() -> list[str]:
    if not os.path.isfile(LOG_PATH):
        return []

    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        return f.readlines()


def _calculate_active_users(lines: list[str]) -> tuple[int, str]:
    explicit_count = None
    inferred_count = 0

    for line in lines:
        for pattern in EXPLICIT_ACTIVE_PATTERNS:
            match = pattern.search(line)
            if match:
                explicit_count = int(match.group(1))

        if any(pattern.search(line) for pattern in JOIN_EVENT_PATTERNS):
            inferred_count += 1

        if any(pattern.search(line) for pattern in LEAVE_EVENT_PATTERNS):
            inferred_count = max(0, inferred_count - 1)

    if explicit_count is not None:
        return explicit_count, "explicit_log_counter"

    return inferred_count, "inferred_join_leave_events"


class ActiveUsersHandler(BaseHTTPRequestHandler):
    def _write_json(self, status_code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._write_json(
                200,
                {
                    "status": "ok",
                    "time": datetime.now(timezone.utc).isoformat(),
                },
            )
            return

        if self.path != API_PATH:
            self._write_json(
                404,
                {
                    "error": "not_found",
                    "message": f"Use '{API_PATH}' or '/health'.",
                },
            )
            return

        lines = _load_lines()
        active_users, source = _calculate_active_users(lines)

        payload = {
            "active_users": active_users,
            "source": source,
            "log_file": LOG_PATH,
            "log_lines": len(lines),
            "time": datetime.now(timezone.utc).isoformat(),
        }
        self._write_json(200, payload)

    # Silence default request logging to keep container logs clean.
    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    server = HTTPServer((API_HOST, API_PORT), ActiveUsersHandler)
    print(f"[INFO]: Active users API listening on http://{API_HOST}:{API_PORT}{API_PATH}")
    server.serve_forever()

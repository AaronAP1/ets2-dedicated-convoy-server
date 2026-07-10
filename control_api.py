#!/usr/bin/python3

import errno
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer


API_HOST = os.getenv("ETS_CONTROL_API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("ETS_CONTROL_API_PORT", "8081"))
AUTH_TOKEN = os.getenv("ETS_CONTROL_API_TOKEN", "").strip()
COMMAND_FIFO = os.getenv("ETS_CONTROL_FIFO", "/tmp/ets_server_commands.fifo")
CHAT_TEMPLATE = os.getenv("ETS_CONTROL_CHAT_TEMPLATE", "say {message}")


def _response(handler: BaseHTTPRequestHandler, status: int, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _authorized(headers) -> bool:
    if not AUTH_TOKEN:
        return True
    auth_header = headers.get("Authorization") or headers.get("authorization")
    return auth_header == f"Bearer {AUTH_TOKEN}"


def _send_to_fifo(command: str):
    try:
        fd = os.open(COMMAND_FIFO, os.O_WRONLY | os.O_NONBLOCK)
    except OSError as exc:
        if exc.errno in (errno.ENXIO, errno.ENOENT):
            raise RuntimeError("server_not_ready") from exc
        raise

    try:
        os.write(fd, (command + "\n").encode("utf-8"))
    finally:
        os.close(fd)


class ControlHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            _response(self, 404, {"error": "not_found", "message": "Use /health, /command or /chat"})
            return

        _response(
            self,
            200,
            {
                "status": "ok",
                "time": datetime.now(timezone.utc).isoformat(),
                "fifo": COMMAND_FIFO,
            },
        )

    def do_POST(self):
        if not _authorized(self.headers):
            _response(self, 401, {"error": "unauthorized"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            _response(self, 400, {"error": "invalid_json"})
            return

        if self.path == "/command":
            command = (payload.get("command") or "").strip()
        elif self.path == "/chat":
            message = (payload.get("message") or "").strip()
            if "{message}" in CHAT_TEMPLATE:
                command = CHAT_TEMPLATE.format(message=message)
            else:
                command = f"{CHAT_TEMPLATE} {message}".strip()
        else:
            _response(self, 404, {"error": "not_found", "message": "Use /command or /chat"})
            return

        if not command:
            _response(self, 400, {"error": "empty_command"})
            return

        if "\n" in command or "\r" in command:
            _response(self, 400, {"error": "invalid_command", "message": "Newlines are not allowed."})
            return

        if len(command) > 512:
            _response(self, 400, {"error": "command_too_long", "max": 512})
            return

        try:
            _send_to_fifo(command)
        except RuntimeError:
            _response(self, 503, {"error": "server_not_ready"})
            return
        except OSError as exc:
            _response(self, 500, {"error": "fifo_write_failed", "message": str(exc)})
            return

        _response(
            self,
            200,
            {
                "ok": True,
                "command": command,
                "time": datetime.now(timezone.utc).isoformat(),
            },
        )

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    print(f"[INFO]: Control API listening on http://{API_HOST}:{API_PORT}")
    server = HTTPServer((API_HOST, API_PORT), ControlHandler)
    server.serve_forever()
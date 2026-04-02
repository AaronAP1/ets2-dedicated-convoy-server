#!/usr/bin/python3

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from active_users_api import LOG_PATH, _calculate_active_users, _load_lines


PUSH_URL = os.getenv("ETS_STATUS_PUSH_URL", "").strip()
PUSH_ENABLED = os.getenv("ETS_STATUS_PUSH_ENABLED", "false").lower() in ["1", "true", "yes", "on"]
PUSH_INTERVAL_SEC = int(os.getenv("ETS_STATUS_PUSH_INTERVAL_SEC", "30"))
PUSH_TIMEOUT_SEC = int(os.getenv("ETS_STATUS_PUSH_TIMEOUT_SEC", "10"))
PUSH_TOKEN = os.getenv("ETS_STATUS_PUSH_TOKEN", "").strip()
SERVER_ID = os.getenv("ETS_STATUS_SERVER_ID", os.getenv("ETS_SERVER_NAME", "ets2-server")).strip()


def build_payload() -> dict:
    lines = _load_lines()
    active_users, source = _calculate_active_users(lines)
    return {
        "server_id": SERVER_ID,
        "status": "active",
        "active_users": active_users,
        "source": source,
        "log_file": LOG_PATH,
        "log_lines": len(lines),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def post_status(payload: dict):
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
    }
    if PUSH_TOKEN:
        headers["Authorization"] = f"Bearer {PUSH_TOKEN}"

    req = urllib.request.Request(PUSH_URL, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=PUSH_TIMEOUT_SEC) as resp:
        status_code = resp.getcode()
        print(f"[INFO]: Status pushed ({status_code}) to {PUSH_URL}")


if __name__ == "__main__":
    if not PUSH_ENABLED:
        print("[INFO]: Status push disabled. Skipping reporter.")
        raise SystemExit(0)

    if not PUSH_URL:
        print("[ERROR]: ETS_STATUS_PUSH_ENABLED=true but ETS_STATUS_PUSH_URL is empty.")
        raise SystemExit(1)

    print(f"[INFO]: Starting status reporter. target={PUSH_URL} interval={PUSH_INTERVAL_SEC}s")
    while True:
        try:
            post_status(build_payload())
        except urllib.error.HTTPError as e:
            print(f"[ERROR]: Push failed with HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            print(f"[ERROR]: Push failed: {e.reason}")
        except Exception as e:
            print(f"[ERROR]: Push failed: {e}")

        time.sleep(max(5, PUSH_INTERVAL_SEC))

import json
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError


TABLE_NAME = os.getenv("TABLE_NAME", "ets2-server-status")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def _response(status_code: int, body: dict):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body),
    }


def _is_authorized(headers: dict) -> bool:
    if not AUTH_TOKEN:
        return True

    if not headers:
        return False

    auth_header = headers.get("authorization") or headers.get("Authorization")
    return auth_header == f"Bearer {AUTH_TOKEN}"


def _handle_post(event: dict):
    if not _is_authorized(event.get("headers", {})):
        return _response(401, {"error": "unauthorized"})

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "invalid_json"})

    server_id = (body.get("server_id") or "").strip()
    if not server_id:
        return _response(400, {"error": "server_id_required"})

    item = {
        "server_id": server_id,
        "status": body.get("status", "active"),
        "active_users": int(body.get("active_users", 0)),
        "source": body.get("source", "unknown"),
        "timestamp": body.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "log_lines": int(body.get("log_lines", 0)),
    }

    try:
        table.put_item(Item=item)
    except ClientError as exc:
        return _response(500, {"error": "db_write_failed", "message": str(exc)})

    return _response(200, {"ok": True, "server_id": server_id})


def _handle_get(event: dict):
    query = event.get("queryStringParameters") or {}
    server_id = (query.get("server_id") or "").strip()
    if not server_id:
        return _response(400, {"error": "server_id_required"})

    try:
        resp = table.get_item(Key={"server_id": server_id})
    except ClientError as exc:
        return _response(500, {"error": "db_read_failed", "message": str(exc)})

    item = resp.get("Item")
    if not item:
        return _response(404, {"error": "not_found", "server_id": server_id})

    return _response(200, item)


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method")
    raw_path = event.get("rawPath", "")

    if method == "OPTIONS":
        return _response(200, {"ok": True})

    if method == "POST" and raw_path.endswith("/report"):
        return _handle_post(event)

    if method == "GET" and raw_path.endswith("/status"):
        return _handle_get(event)

    return _response(404, {"error": "not_found"})

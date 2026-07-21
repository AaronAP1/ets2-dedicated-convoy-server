# ETS2 Convoy Server Monitor

Small sidecar service that reads the dedicated server log (read-only) and exposes
a JSON HTTP API plus optional Discord notifications on player connect/disconnect.

It does **not** touch the game server container or image. It only mounts the
`save-data` folder read-only and follows `server.log.txt`.

## Endpoints

| Method | Path              | Description                                             |
|--------|-------------------|---------------------------------------------------------|
| GET    | `/health`         | Liveness check (no auth).                                |
| GET    | `/status` (or `/`)| Connected count, current player list, server state.     |
| GET    | `/players`        | Just the count + list of currently connected players.   |
| GET    | `/events?limit=N` | Recent connect/disconnect events (newest first).        |

### Example: `GET /status`

```json
{
  "server_name": "PERU IM",
  "connected_count": 7,
  "tracked_players": 7,
  "players": [
    { "client_id": "25", "name": "[ TCS ] SCORPIO", "since": "2026-07-21T03:10:00+00:00" }
  ],
  "server_state": "running",
  "peak_since_start": 12,
  "last_state_log_ts": "03:09:04.638",
  "last_update": "2026-07-21T03:09:05+00:00",
  "time": "2026-07-21T03:09:10+00:00"
}
```

> `connected_count` comes from the server's own authoritative
> `State: running; ...; Players: N` log line (written every ~3 min).
> `players` is the best-effort reconstructed list from `connected` /
> `disconnected` events. The two can briefly differ between State lines.

## Configuration (environment variables)

| Variable                 | Default                 | Description                                   |
|--------------------------|-------------------------|-----------------------------------------------|
| `MONITOR_LOG_FILE`       | `/logs/server.log.txt`  | Path to the server log inside the container.  |
| `MONITOR_PORT`           | `8080`                  | HTTP port.                                    |
| `MONITOR_TOKEN`          | *(empty)*               | If set, API requires `Authorization: Bearer <token>` (except `/health`). |
| `DISCORD_WEBHOOK_URL`    | *(empty)*               | If set, sends an embed to Discord on each join/leave. |
| `MONITOR_SERVER_NAME`    | `ETS2 Server`           | Name shown in API responses / Discord footer. |
| `MONITOR_MAX_EVENTS`     | `200`                   | How many recent events to keep in memory.     |

## Usage

Add the `ets2-monitor` service to `docker-compose.yml` (already included in this repo),
then:

```bash
docker compose up -d --build ets2-monitor
curl http://localhost:8080/status
```

To protect the endpoint, set `MONITOR_TOKEN` and call it with:

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8080/status
```

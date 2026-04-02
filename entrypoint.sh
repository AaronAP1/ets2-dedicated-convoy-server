#!/bin/sh

# Copy default server_packages if they do not exist
cp -n /default_packages/server_packages.sii "${SAVEGAME_LOCATION}"
cp -n /default_packages/server_packages.dat "${SAVEGAME_LOCATION}"

# Generate config and update server
/usr/bin/python3 /ets_server_entrypoint.py

if [ "${ETS_STATUS_API_ENABLED:-true}" = "true" ]; then
	echo "[INFO]: Starting active users API..."
	/usr/bin/python3 /active_users_api.py &
fi

if [ "${ETS_STATUS_PUSH_ENABLED:-false}" = "true" ]; then
	echo "[INFO]: Starting status push reporter..."
	/usr/bin/python3 /status_reporter.py &
fi

echo "[INFO]: Starting server..."
exec "$@"
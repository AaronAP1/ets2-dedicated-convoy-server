#!/bin/sh

# Copy the bundled server package files into the save-data folder on first start.
cp -n /default_packages/server_packages.sii "${SAVEGAME_LOCATION}"
cp -n /default_packages/server_packages.dat "${SAVEGAME_LOCATION}"

# Generates server_config.sii from the ETS_SERVER_* env vars (incl. the logon
# token that gives the server a persistent id), updates the server via steamcmd
# and applies the >8 players workaround to config_ds.cfg.
/usr/bin/python3 /ets_server_entrypoint.py

echo "[INFO]: Starting server..."
exec "$@"

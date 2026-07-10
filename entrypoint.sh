#!/bin/sh

# Copy the bundled server package files into the save-data folder on first start.
cp -n /default_packages/server_packages.sii "${SAVEGAME_LOCATION}"
cp -n /default_packages/server_packages.dat "${SAVEGAME_LOCATION}"

if [ "${ETS_SERVER_UPDATE_ON_START:-true}" = "true" ] || [ ! -x "${EXECUTABLE}" ]; then
	echo "[INFO]: Updating ETS Server..."
	beta_argument=""
	if [ -n "${ETS_SERVER_BRANCH}" ]; then
		beta_argument=" -beta ${ETS_SERVER_BRANCH}"
	fi
	/home/steam/steamcmd/steamcmd.sh +force_install_dir /app +login anonymous +app_update "${APP_ID}"${beta_argument} +quit
	echo "[INFO]: Update done."
fi

echo "[INFO]: Starting server..."
exec "$@"
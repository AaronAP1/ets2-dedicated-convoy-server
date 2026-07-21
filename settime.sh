#!/bin/bash
# settime.sh — cambia la hora del juego en el server ETS2 EN VIVO (aunque haya jugadores online).
# Uso:  ./settime.sh 14      (hora de 1 a 24; 14 = las 2 de la tarde)
#
# Envia el comando `g_set_time <hora>` a la consola del servidor a traves de un FIFO.
# Requiere que el contenedor tenga `tty: true` y `stdin_open: true` en docker-compose.yml.

CONTAINER="ets2-server"
FIFO="/tmp/ets2_cmd.fifo"

HORA="$1"

# Validar que sea un numero entre 1 y 24
if ! [[ "$HORA" =~ ^[0-9]+$ ]] || [ "$HORA" -lt 1 ] || [ "$HORA" -gt 24 ]; then
  echo "Uso: $0 <hora 1-24>    ejemplo: $0 14"
  exit 1
fi

# 1) Crear el FIFO si no existe
[ -p "$FIFO" ] || mkfifo "$FIFO"

# 2) Levantar el "puente" hacia la consola si no esta corriendo.
#    tail -f mantiene el FIFO abierto para que docker attach no se desconecte.
if ! pgrep -f "tail -f $FIFO" >/dev/null 2>&1; then
  setsid bash -c "tail -f '$FIFO' | docker attach '$CONTAINER'" >/dev/null 2>&1 </dev/null &
  sleep 1
fi

# 3) Enviar el comando
printf 'g_set_time %s\n' "$HORA" > "$FIFO"
echo "✔ Hora del servidor cambiada a las ${HORA}:00"

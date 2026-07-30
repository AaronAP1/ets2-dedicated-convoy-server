#!/bin/bash
# cmd.sh — envia CUALQUIER comando a la consola del server ETS2 EN VIVO.
# Uso:
#   ./cmd.sh help              -> lista los comandos que soporta el server
#   ./cmd.sh players           -> lista jugadores conectados (con su id)
#   ./cmd.sh "ban 5"           -> ejecuta el comando "ban 5"
#   ./cmd.sh "say Hola a todos" -> manda un mensaje al chat
#
# Requiere `tty: true` y `stdin_open: true` en el servicio ets2-server del compose.
# La respuesta del server se ve con:  docker compose logs --tail 40 ets2-server

CONTAINER="ets2-server"
FIFO="/tmp/ets2_cmd.fifo"

CMD="$*"
if [ -z "$CMD" ]; then
  echo "Uso: $0 <comando>"
  echo "Ejemplos: $0 help | $0 players | $0 \"ban 5\" | $0 \"say Hola\""
  exit 1
fi

# 1) FIFO
[ -p "$FIFO" ] || mkfifo "$FIFO"

# 2) Puente hacia la consola (se auto-levanta si no esta corriendo)
if ! pgrep -f "tail -f $FIFO" >/dev/null 2>&1; then
  setsid bash -c "tail -f '$FIFO' | docker attach '$CONTAINER'" >/dev/null 2>&1 </dev/null &
  sleep 1
fi

# 3) Enviar
printf '%s\n' "$CMD" > "$FIFO"
echo "✔ Enviado a la consola: $CMD"
echo "  Ver respuesta:  docker compose logs --tail 40 ets2-server"

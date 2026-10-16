#!/usr/bin/env bash
# Measure SenseHive's resource use (docs/PERFORMANCE.md): image size, then idle,
# 500 heartbeat nodes (50 verified messages/s), then also 100 topics at 50 msg/s.
# Needs Docker and openssl. Usage: TAG=1.4.2 PHASE=120 bash tools/measure/run.sh
set -u
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd -W 2>/dev/null || pwd)"
PROTO="$(cd "$(dirname "$0")/../../version-1.0" && pwd -W 2>/dev/null || pwd)"
TAG="${TAG:-1.4.2}"
PW="load-$(openssl rand -hex 6)"
MASTER="$(openssl rand -hex 32)"
docker rm -f sh broker shload >/dev/null 2>&1
docker network rm shm >/dev/null 2>&1
docker network create shm >/dev/null
docker pull -q devprincekumar/sense-hive:$TAG >/dev/null
echo "IMAGE $(docker image inspect devprincekumar/sense-hive:$TAG --format '{{.Size}}')"
docker run -d --name broker --network shm eclipse-mosquitto:1.6 >/dev/null
docker run -d --name sh --network shm -e SENSEHIVE_ADMIN_PASSWORD="$PW" -e HEARTBEAT_MASTER_KEY="$MASTER" \
  -e HEARTBEAT_API_TOKEN="$(openssl rand -hex 24)" -e HEARTBEAT_BROKER=broker -e HEARTBEAT_PORT=1883 -e HEARTBEAT_TLS=false \
  -e DEFAULT_BROKER_HOST=broker -e DEFAULT_BROKER_PORT=1883 devprincekumar/sense-hive:$TAG >/dev/null
sleep 8
docker run -d --name shload --network shm -e PW="$PW" -e MASTER="$MASTER" -e PHASE="${PHASE:-120}" \
  -v "$HERE:/load:ro" -v "$PROTO:/proto:ro" python:3.11-slim \
  sh -c 'pip install -q paho-mqtt==2.1.0 requests cryptography 2>/dev/null; python -u /load/load.py' >/dev/null
# sample docker stats every 5 s until the load container exits
while [ "$(docker inspect -f '{{.State.Running}}' shload 2>/dev/null)" = true ]; do
  echo "STAT $(date +%s) $(docker stats --no-stream --format '{{.CPUPerc}} {{.MemUsage}}' sh)"
  sleep 5
done
docker logs shload 2>&1 | grep -v "^WARNING"
echo "DBFILE $(docker exec sh sh -c 'ls -l /app/data/ | tr -s " " | cut -d" " -f5,9 | tr "\n" ";"')"
echo "LOGLINES $(docker logs sh 2>&1 | wc -l)"
docker rm -f sh broker shload >/dev/null; docker network rm shm >/dev/null

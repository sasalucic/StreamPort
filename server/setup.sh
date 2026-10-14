#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
command -v docker >/dev/null || { echo 'Install Docker Engine and Docker Compose on Ubuntu first: https://docs.docker.com/engine/install/ubuntu/'; exit 1; }
docker compose version >/dev/null || { echo 'Docker Compose plugin is required. Ubuntu repository: sudo apt install docker-compose-v2; Docker official repository: sudo apt install docker-compose-plugin.'; exit 1; }
docker info >/dev/null 2>&1 || { echo 'Cannot access Docker. Run with a Docker-enabled account or use sudo bash setup.sh.'; exit 1; }
if [[ ! -f .env ]]; then
  read -r -p 'Absolute path to your existing MOVIES folder: ' movies_path
  read -r -p 'Absolute path to your existing TV SHOWS folder: ' tv_path
  for path in "$movies_path" "$tv_path"; do
    [[ "$path" = /* && -d "$path" ]] || { echo "Directory does not exist: $path"; exit 1; }
    [[ "$path" != *"'"* && "$path" != *$'\n'* && "$path" != *$'\r'* ]] || { echo 'Paths with quotes/newlines are not supported by this setup helper.'; exit 1; }
  done
  app_uid="${SUDO_UID:-$(id -u)}"
  app_gid="${SUDO_GID:-$(id -g)}"
  umask 077
  cat > .env <<EOF
MOVIES_PATH='$movies_path'
TV_PATH='$tv_path'
PUID=$app_uid
PGID=$app_gid
STREAMPORT_PORT=8097
BIND_ADDRESS=0.0.0.0
MAX_TRANSCODES=1
COOKIE_SECURE=false
OPENSUBTITLES_API_KEY=
EOF
  mkdir -p data
  if [[ $(id -u) == 0 ]]; then chown "$app_uid:$app_gid" data; fi
  chmod 700 data
else
  echo 'Using your existing .env. Existing configuration is preserved.'
  mkdir -p data
fi
docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 180
echo 'StreamPort is running. Open http://YOUR_SERVER_HOST:8097 (or your configured port).'
echo 'Create your admin account, then configure Radarr, Sonarr and OpenSubtitles under Settings.'
echo 'Existing media-management services are unchanged.'

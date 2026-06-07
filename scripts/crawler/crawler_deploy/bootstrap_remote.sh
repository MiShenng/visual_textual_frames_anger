#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

APP_DIR="${HOME}/crawler_app"
VENV_DIR="${APP_DIR}/.venv"
SERVICE_NAME="short-video-crawler"

echo "[1/7] apt update"
sudo apt-get update

echo "[2/7] install system packages"
sudo apt-get install -y \
  build-essential \
  ca-certificates \
  curl \
  git \
  jq \
  python3-pip \
  python3-venv \
  rsync \
  sqlite3 \
  tmux

echo "[3/7] create app directories"
mkdir -p "${APP_DIR}" "${APP_DIR}/data" "${APP_DIR}/playwright_states"
touch "${APP_DIR}/crawler.log"

echo "[4/7] create virtual environment"
if [ ! -d "${VENV_DIR}" ]; then
  python3 -m venv "${VENV_DIR}"
fi

echo "[5/8] install python dependencies"
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip
pip install -e "${APP_DIR}"

echo "[6/8] install playwright browser"
"${VENV_DIR}/bin/python" -m playwright install chromium

echo "[7/8] prepare environment file"
if [ ! -f "${APP_DIR}/.env" ]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
fi

echo "[8/8] install systemd service"
sudo cp "${APP_DIR}/crawler_deploy/${SERVICE_NAME}.service" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"

echo "bootstrap complete"
echo "app_dir=${APP_DIR}"
echo "service_name=${SERVICE_NAME}"
echo "next=run 'sudo systemctl restart ${SERVICE_NAME}' after each deploy"

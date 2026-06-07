#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <ssh-host-alias-or-user@host>" >&2
  exit 1
fi

TARGET="$1"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_DIR="~/crawler_app"
REMOTE_TMP="~/crawler_app_staging"
FILES=(
  "app"
  "templates"
  "tests"
  "crawler_deploy"
  "pyproject.toml"
  ".env.example"
  "README_crawler.md"
)

echo "[1/6] prepare remote directories"
ssh "${TARGET}" "mkdir -p ${REMOTE_TMP} ${REMOTE_DIR}"

echo "[2/6] upload project files"
rsync -az --delete \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude '.venv' \
  --exclude 'crawler.sqlite3' \
  "${FILES[@]/#/${ROOT_DIR}/}" \
  "${TARGET}:${REMOTE_TMP}/"

echo "[3/6] sync staging into app directory"
ssh "${TARGET}" "rsync -a --delete ${REMOTE_TMP}/ ${REMOTE_DIR}/"

echo "[4/6] run remote bootstrap"
ssh "${TARGET}" "bash ${REMOTE_DIR}/crawler_deploy/bootstrap_remote.sh"

echo "[5/6] restart service"
ssh "${TARGET}" "sudo systemctl restart short-video-crawler"

echo "[6/6] show service status"
ssh "${TARGET}" "systemctl --no-pager --full status short-video-crawler | sed -n '1,18p'"

echo "done"

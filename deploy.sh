#!/usr/bin/env bash
# deploy.sh — push to GitHub, then pull and restart on zephyr
#
# Usage: ./deploy.sh [remote] [deploy_path]
# Defaults: remote=zephyr, path=/var/www/nthmost.com/lm

set -e

REMOTE="${1:-zephyr}"
DEPLOY_PATH="${2:-/var/www/nthmost.com/lm}"
SERVICE="${3:-lm}"

echo "── pushing to GitHub..."
git push origin main

echo "── deploying to ${REMOTE}:${DEPLOY_PATH}..."
ssh "$REMOTE" "
  cd ${DEPLOY_PATH}
  git pull origin main
  sudo systemctl restart ${SERVICE}
  echo '── restarted ${SERVICE}'
  sudo systemctl status ${SERVICE} --no-pager | head -6
"

echo "── done."

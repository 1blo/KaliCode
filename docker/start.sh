#!/usr/bin/env bash
# Start the Kali Code mobile companion server on Render.
#
# Render's free web services have an ephemeral filesystem, so anything that
# must survive a restart lives in git. If KALI_GIT_REPO is set we clone (or
# pull) that repository into KALI_WORKSPACE before starting the agent.
set -euo pipefail

PORT="${PORT:-8000}"
WORKSPACE="${KALI_WORKSPACE:-/workspace}"

echo "[start] Kali Code companion"
echo "[start] port=${PORT} workspace=${WORKSPACE}"

# ---- clone / sync the game repository -------------------------------------- #
if [ -n "${KALI_GIT_REPO:-}" ]; then
  echo "[start] syncing ${KALI_GIT_REPO}"
  mkdir -p "${WORKSPACE}"
  cd "${WORKSPACE}"
  if [ -d .git ]; then
    git fetch --depth=1 origin || true
    git reset --hard "origin/${KALI_GIT_BRANCH:-main}" || true
  else
    rm -rf ./*
    git clone --depth=1 --branch "${KALI_GIT_BRANCH:-main}" "${KALI_GIT_REPO}" . || {
      echo "[start] WARNING: clone failed - continuing without a workspace"
    }
  fi
  # Credentials for pushes, if provided.
  if [ -n "${KALI_GIT_TOKEN:-}" ]; then
    git config user.name  "Kali Code"
    git config user.email "kali.code@users.noreply.github.com"
    git remote set-url origin \
      "https://x-access-token:${KALI_GIT_TOKEN}@github.com/${KALI_GIT_REPO#https://github.com/}.git" \
      2>/dev/null || true
  fi
else
  echo "[start] KALI_GIT_REPO not set - using an empty workspace"
  mkdir -p "${WORKSPACE}"
fi

cd /app

# ---- start ----------------------------------------------------------------- #
exec python -m kali.serve \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --cwd "${WORKSPACE}" \
  ${KALI_MODEL:+--model "$KALI_MODEL"} \
  ${KALI_PERMISSION_MODE:+--permission-mode "$KALI_PERMISSION_MODE"}

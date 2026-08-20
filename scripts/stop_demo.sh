#!/usr/bin/env bash

# ==============================================================================
# Truth Lens — Stop Demo Services
# Safely stops ONLY the server and tunnel processes started by start_demo.sh.
# ==============================================================================

set -uo pipefail

# Color definitions
GREEN='[0;32m'
YELLOW='[1;33m'
RED='[0;31m'
BOLD='[1m'
NC='[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_DIR="${REPO_ROOT}/storage/demo_run"

SERVER_PID_FILE="${RUN_DIR}/server.pid"
TUNNEL_PID_FILE="${RUN_DIR}/tunnel.pid"

STOPPED_ANY=false

echo -e "${YELLOW}Checking for running Truth Lens demo launcher processes...${NC}"

# Stop Tunnel
if [[ -f "${TUNNEL_PID_FILE}" ]]; then
    TUNNEL_PID=$(cat "${TUNNEL_PID_FILE}" 2>/dev/null || true)
    if [[ -n "${TUNNEL_PID}" ]] && kill -0 "${TUNNEL_PID}" 2>/dev/null; then
        CMD=$(ps -p "${TUNNEL_PID}" -o comm= 2>/dev/null || true)
        if [[ "${CMD}" == *"cloudflared"* ]]; then
            echo -e "   Stopping Cloudflare Quick Tunnel (PID: ${TUNNEL_PID})..."
            kill -TERM "${TUNNEL_PID}" 2>/dev/null || true
            sleep 1
            if kill -0 "${TUNNEL_PID}" 2>/dev/null; then
                kill -KILL "${TUNNEL_PID}" 2>/dev/null || true
            fi
            STOPPED_ANY=true
        fi
    fi
    rm -f "${TUNNEL_PID_FILE}"
fi

# Stop Server
if [[ -f "${SERVER_PID_FILE}" ]]; then
    SERVER_PID=$(cat "${SERVER_PID_FILE}" 2>/dev/null || true)
    if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
        CMD=$(ps -p "${SERVER_PID}" -o command= 2>/dev/null || true)
        if [[ "${CMD}" == *"app.main:app"* || "${CMD}" == *"uvicorn"* ]]; then
            echo -e "   Stopping Truth Lens FastAPI Server (PID: ${SERVER_PID})..."
            kill -TERM "${SERVER_PID}" 2>/dev/null || true
            sleep 1
            if kill -0 "${SERVER_PID}" 2>/dev/null; then
                kill -KILL "${SERVER_PID}" 2>/dev/null || true
            fi
            STOPPED_ANY=true
        fi
    fi
    rm -f "${SERVER_PID_FILE}"
fi

if [[ "${STOPPED_ANY}" == true ]]; then
    echo -e "${GREEN}✓ Truth Lens demo stopped successfully.${NC}"
else
    echo -e "${GREEN}No active Truth Lens demo launcher processes found.${NC}"
fi

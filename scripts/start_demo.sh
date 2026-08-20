#!/usr/bin/env bash

# ==============================================================================
# Truth Lens — One-Command macOS Demo Launcher
# Starts Truth Lens on 127.0.0.1:8000 and exposes a temporary Cloudflare Quick Tunnel.
# ==============================================================================

set -uo pipefail

# Ensure standard Homebrew & system binary paths are accessible on macOS (Apple Silicon & Intel)
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Color definitions
CYAN='[0;36m'
GREEN='[0;32m'
YELLOW='[1;33m'
RED='[0;31m'
BOLD='[1m'
NC='[0m' # No Color

# Determine repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Directory for runtime demo artifacts (PIDs and logs)
RUN_DIR="${REPO_ROOT}/storage/demo_run"
mkdir -p "${RUN_DIR}"

SERVER_PID_FILE="${RUN_DIR}/server.pid"
TUNNEL_PID_FILE="${RUN_DIR}/tunnel.pid"
SERVER_LOG="${RUN_DIR}/server.log"
TUNNEL_LOG="${RUN_DIR}/tunnel.log"

SERVER_PID=""
TUNNEL_PID=""

# Cleanup function triggered on EXIT / INT / TERM
cleanup() {
    echo ""
    echo -e "${YELLOW}🛑 Shutting down Truth Lens demo services...${NC}"

    # Stop Cloudflare tunnel if started by this script
    if [[ -n "${TUNNEL_PID}" ]] && kill -0 "${TUNNEL_PID}" 2>/dev/null; then
        echo -e "   Stopping Cloudflare Quick Tunnel (PID: ${TUNNEL_PID})..."
        kill -TERM "${TUNNEL_PID}" 2>/dev/null || true
        wait "${TUNNEL_PID}" 2>/dev/null || true
    fi
    rm -f "${TUNNEL_PID_FILE}"

    # Stop Truth Lens backend server if started by this script
    if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
        echo -e "   Stopping Truth Lens FastAPI Server (PID: ${SERVER_PID})..."
        kill -TERM "${SERVER_PID}" 2>/dev/null || true
        wait "${SERVER_PID}" 2>/dev/null || true
    fi
    rm -f "${SERVER_PID_FILE}"

    echo -e "${GREEN}✓ Truth Lens demo stopped cleanly.${NC}"
    exit 0
}

trap cleanup INT TERM EXIT

echo -e "${CYAN}${BOLD}"
echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║             TRUTH LENS — FORENSIC MEDIA DEMO LAUNCHER                     ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── 1. Check Python Virtual Environment ────────────────────────────────────────
echo -e "${CYAN}[1/4] Checking Python virtual environment...${NC}"
if [[ ! -f "venv/bin/python" ]]; then
    echo -e "${RED}[ERROR] Python virtual environment not found at 'venv/bin/python'.${NC}"
    echo ""
    echo "To set up the required environment, run the following commands from the project root:"
    echo "  python3 -m venv venv"
    echo "  ./venv/bin/pip install --upgrade pip"
    echo "  ./venv/bin/pip install -r requirements.txt"
    echo ""
    trap - INT TERM EXIT
    exit 1
fi
echo -e "${GREEN}✓ Found virtual environment at venv/bin/python${NC}"

# ── 2. Check cloudflared CLI ───────────────────────────────────────────────────
echo -e "${CYAN}[2/4] Checking Cloudflare Tunnel CLI (cloudflared)...${NC}"
if ! command -v cloudflared &> /dev/null; then
    echo -e "${RED}[ERROR] 'cloudflared' CLI tool was not found in PATH.${NC}"
    echo ""
    echo "To install cloudflared on macOS using Homebrew:"
    echo "  brew install cloudflared"
    echo ""
    echo "Or download the macOS standalone binary from:"
    echo "  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    echo ""
    trap - INT TERM EXIT
    exit 1
fi
CLOUDFLARED_VERSION=$(cloudflared --version 2>/dev/null | head -n 1)
echo -e "${GREEN}✓ Found ${CLOUDFLARED_VERSION}${NC}"

# Check for existing local config files that might conflict
if [[ -f "${HOME}/.cloudflared/config.yml" || -f "${HOME}/.cloudflared/config.yaml" ]]; then
    echo -e "${YELLOW}[NOTICE] Found local configuration in ~/.cloudflared/. Starting in ad-hoc Quick Tunnel mode.${NC}"
    echo -e "${YELLOW}         Your existing Cloudflare configuration will NOT be modified or deleted.${NC}"
fi

# ── 3. Check Port 8000 Availability ───────────────────────────────────────────
echo -e "${CYAN}[3/4] Checking port 8000 availability...${NC}"
if lsof -nP -iTCP:8000 -sTCP:LISTEN &>/dev/null; then
    OCCUPIER=$(lsof -nP -iTCP:8000 -sTCP:LISTEN | tail -n +2 | awk '{print $1 " (PID " $2 ")"}')
    echo -e "${RED}[ERROR] Port 8000 is already in use by: ${OCCUPIER}${NC}"
    echo ""
    echo "To resolve this conflict:"
    echo "  1. If a previous Truth Lens demo is still running, run: ./scripts/stop_demo.sh"
    echo "  2. Or inspect the process listening on port 8000: lsof -i :8000"
    echo "  3. Or stop the process: kill \$(lsof -t -i:8000)"
    echo ""
    trap - INT TERM EXIT
    exit 1
fi

# ── 4. Start Truth Lens FastAPI Backend ───────────────────────────────────────
# ── 4. Start Truth Lens FastAPI Backend ───────────────────────────────────────
echo -e "${CYAN}[4/4] Starting Truth Lens backend on 127.0.0.1:8000...${NC}"
> "${SERVER_LOG}"
> "${TUNNEL_LOG}"

./venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips='*' > "${SERVER_LOG}" 2>&1 &
SERVER_PID=$!
echo "${SERVER_PID}" > "${SERVER_PID_FILE}"

# Wait for health check (up to 30 seconds)
HEALTH_URL="http://127.0.0.1:8000/health"
MAX_ATTEMPTS=30
ATTEMPT=0
SERVER_READY=false

printf "      Waiting for Truth Lens health endpoint..."
while [[ ${ATTEMPT} -lt ${MAX_ATTEMPTS} ]]; do
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
        echo ""
        echo -e "${RED}[ERROR] Truth Lens backend process exited prematurely.${NC}"
        echo -e "Check the log file for details: ${BOLD}${SERVER_LOG}${NC}"
        if [[ -s "${SERVER_LOG}" ]]; then
            echo ""
            echo "--- Server Log Output ---"
            cat "${SERVER_LOG}"
            echo "-------------------------"
        fi
        trap - INT TERM EXIT
        exit 1
    fi

    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${HEALTH_URL}" 2>/dev/null || true)
    if [[ "${HTTP_STATUS}" == "200" ]]; then
        SERVER_READY=true
        break
    fi

    printf "."
    sleep 1
    ((ATTEMPT++))
done
echo ""

if [[ "${SERVER_READY}" != true ]]; then
    echo -e "${RED}[ERROR] Timed out waiting for Truth Lens server to start.${NC}"
    echo -e "Check server log: ${BOLD}${SERVER_LOG}${NC}"
    trap - INT TERM EXIT
    kill -TERM "${SERVER_PID}" 2>/dev/null || true
    exit 1
fi

echo -e "${GREEN}✓ Truth Lens local server is healthy and listening on http://127.0.0.1:8000${NC}"

# ── 5. Start Cloudflare Quick Tunnel ──────────────────────────────────────────
echo -e "${CYAN}Starting Cloudflare Quick Tunnel (HTTP/2 protocol)...${NC}"

cloudflared tunnel --url http://127.0.0.1:8000 --protocol http2 --no-autoupdate > "${TUNNEL_LOG}" 2>&1 &
TUNNEL_PID=$!
echo "${TUNNEL_PID}" > "${TUNNEL_PID_FILE}"

# Extract public Quick Tunnel URL
TUNNEL_MAX_WAIT=25
TUNNEL_WAIT=0
TUNNEL_URL=""

printf "      Establishing encrypted Cloudflare Quick Tunnel..."
while [[ ${TUNNEL_WAIT} -lt ${TUNNEL_MAX_WAIT} ]]; do
    if ! kill -0 "${TUNNEL_PID}" 2>/dev/null; then
        echo ""
        echo -e "${RED}[ERROR] Cloudflare tunnel process exited unexpectedly.${NC}"
        echo -e "Check tunnel log: ${BOLD}${TUNNEL_LOG}${NC}"
        if [[ -s "${TUNNEL_LOG}" ]]; then
            echo ""
            echo "--- Tunnel Log Output ---"
            cat "${TUNNEL_LOG}"
            echo "-------------------------"
        fi
        exit 1
    fi

    TUNNEL_URL=$(grep -Eo 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "${TUNNEL_LOG}" 2>/dev/null | head -n 1 || true)
    if [[ -n "${TUNNEL_URL}" ]]; then
        break
    fi

    printf "."
    sleep 1
    ((TUNNEL_WAIT++))
done
echo ""

if [[ -z "${TUNNEL_URL}" ]]; then
    echo -e "${YELLOW}[WARNING] Cloudflare Quick Tunnel URL could not be automatically detected.${NC}"
    echo -e "Check tunnel logs for connection details: ${BOLD}${TUNNEL_LOG}${NC}"
    echo -e "Local URL is still accessible at: ${BOLD}http://127.0.0.1:8000${NC}"
else
    # Verify public reachability
    printf "      Verifying Cloudflare Edge reachability..."
    TUNNEL_REACHABLE=false
    for i in {1..12}; do
        TUNNEL_HTTP=$(curl -s -k -o /dev/null -w "%{http_code}" "${TUNNEL_URL}/health" --max-time 4 2>/dev/null || true)
        if [[ "${TUNNEL_HTTP}" == "200" ]]; then
            TUNNEL_REACHABLE=true
            break
        fi
        printf "."
        sleep 1
    done
    echo ""

    echo ""
    echo -e "${GREEN}${BOLD}==============================================================================${NC}"
    echo -e "${GREEN}${BOLD}🚀 TRUTH LENS LIVE DEMO IS ONLINE!${NC}"
    echo -e "${GREEN}${BOLD}==============================================================================${NC}"
    echo ""
    echo -e "  🌐 Public HTTPS URL : ${CYAN}${BOLD}${TUNNEL_URL}${NC}"
    echo -e "  💻 Localhost URL    : ${BOLD}http://127.0.0.1:8000${NC}"
    echo -e "  📄 Health Endpoint  : ${BOLD}${TUNNEL_URL}/health${NC}"
    echo ""
    if [[ "${TUNNEL_REACHABLE}" == true ]]; then
        echo -e "${GREEN}  ✓ Cloudflare tunnel is active, verified, and reachable worldwide!${NC}"
    else
        echo -e "${YELLOW}  ℹ️  Cloudflare DNS is propagating globally (may take 5-15s on first load).${NC}"
        echo -e "${YELLOW}     If your browser displays 'DNS not found', wait a few seconds and refresh.${NC}"
    fi
    echo ""
    echo -e "${YELLOW}${BOLD}⚠️  IMPORTANT DEMO NOTICES:${NC}"
    echo -e "${YELLOW}  1. Temporary URL: The trycloudflare.com URL changes every time this script restarts.${NC}"
    echo -e "${YELLOW}  2. Keep-Alive: Keep this terminal window OPEN while sharing the link with judges/users.${NC}"
    echo -e "${YELLOW}  3. Privacy & Security: This public demo has NO user authentication. Do NOT upload real private data.${NC}"
    echo -e "${YELLOW}  4. Safety: 100% local analysis; no API keys or private credentials are exposed.${NC}"
    echo ""
    echo -e "${BOLD}Logs available at:${NC}"
    echo -e "  Server log : ${SERVER_LOG}"
    echo -e "  Tunnel log : ${TUNNEL_LOG}"
    echo ""
    echo -e "${CYAN}Press ${BOLD}Ctrl+C${NC}${CYAN} to stop the demo and shut down all services.${NC}"
    echo -e "${GREEN}${BOLD}==============================================================================${NC}"
fi

# Keep script running and wait for background processes or SIGINT (Ctrl+C)
while true; do
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
        echo -e "${RED}[ERROR] Truth Lens backend stopped unexpectedly.${NC}"
        break
    fi
    if ! kill -0 "${TUNNEL_PID}" 2>/dev/null; then
        echo -e "${RED}[ERROR] Cloudflare tunnel stopped unexpectedly.${NC}"
        break
    fi
    sleep 2
done

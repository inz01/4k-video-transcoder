#!/usr/bin/env bash
# =============================================================================
# remote_install.sh — One-Command Installer for 4K Video Transcoder
# =============================================================================
# Run this on ANY fresh Ubuntu 22.04+ machine to install and start the app.
#
# Usage (one-liner — copy & paste into terminal):
#
#   curl -sSL https://raw.githubusercontent.com/inz01/4k-video-transcoder/main/remote_install.sh | bash
#
# Or download and run:
#
#   wget https://raw.githubusercontent.com/inz01/4k-video-transcoder/main/remote_install.sh
#   bash remote_install.sh
#
# What this script does:
#   1. Installs system dependencies (ffmpeg, redis, python3-venv, curl)
#   2. Clones the repository from GitHub
#   3. Creates Python virtual environment & installs pip packages
#   4. Configures Redis
#   5. Starts the RQ Worker (background)
#   6. Starts the FastAPI server (background)
#   7. Prints the URL to access the app
#
# Requirements:
#   - Ubuntu 22.04+ (or Debian-based Linux)
#   - Internet access
#   - sudo privileges
# =============================================================================

set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
RESET="\033[0m"

info()    { echo -e "${GREEN}[INFO]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; exit 1; }
section() { echo -e "\n${BOLD}${CYAN}==> $*${RESET}"; }

# ─── Configuration ────────────────────────────────────────────────────────────
REPO_URL="https://github.com/inz01/4k-video-transcoder.git"
INSTALL_DIR="${HOME}/4k-video-transcoder"
API_PORT=8000

# ─── 0. Check OS ─────────────────────────────────────────────────────────────
section "Checking system"
if [[ "$(uname -s)" != "Linux" ]]; then
    error "This script requires Linux. Detected: $(uname -s)"
fi

if ! command -v apt-get &>/dev/null; then
    error "This script requires apt-get (Debian/Ubuntu). Your system uses a different package manager."
fi

# Check Ubuntu version
if grep -qi "ubuntu" /etc/os-release 2>/dev/null; then
    OS_VERSION=$(grep VERSION_ID /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')
    info "Ubuntu ${OS_VERSION} detected ✓"
else
    warn "Non-Ubuntu system detected. Script may still work on Debian-based distros."
fi

# ─── 1. Install system dependencies ──────────────────────────────────────────
section "Installing system dependencies"
info "This requires sudo — you may be prompted for your password."

sudo apt-get update -qq
sudo apt-get install -y git ffmpeg redis-server python3-venv python3-pip curl netcat-openbsd

# Verify critical tools
command -v ffmpeg  &>/dev/null || error "ffmpeg installation failed"
command -v git     &>/dev/null || error "git installation failed"
command -v python3 &>/dev/null || error "python3 installation failed"
info "System dependencies installed ✓"

# ─── 2. Clone the repository ─────────────────────────────────────────────────
section "Cloning repository"
if [[ -d "${INSTALL_DIR}" ]]; then
    info "Directory ${INSTALL_DIR} already exists. Pulling latest changes..."
    cd "${INSTALL_DIR}"
    git pull origin main 2>/dev/null || warn "Could not pull latest. Using existing code."
else
    git clone "${REPO_URL}" "${INSTALL_DIR}"
    info "Repository cloned to ${INSTALL_DIR}"
fi

cd "${INSTALL_DIR}"

# ─── 3. Run setup.sh ─────────────────────────────────────────────────────────
section "Running setup (venv, pip packages, Redis config)"
if [[ -f "setup.sh" ]]; then
    bash setup.sh
else
    # Manual setup fallback
    warn "setup.sh not found. Running manual setup..."

    # Create venv
    if [[ ! -d ".venv" ]]; then
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    pip install --upgrade pip -q
    pip install -r requirements.txt -q

    # Create directories
    mkdir -p uploads outputs logs metrics

    # Start Redis
    if ! redis-cli ping &>/dev/null; then
        sudo systemctl start redis-server 2>/dev/null || redis-server --daemonize yes --logfile redis.log
    fi

    # Create .env if missing
    if [[ ! -f ".env" ]]; then
        cat > .env <<EOF
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
API_HOST=0.0.0.0
API_PORT=${API_PORT}
EOF
    fi
fi

info "Setup complete ✓"

# ─── 4. Stop any existing instances ──────────────────────────────────────────
section "Checking for existing instances"
# Kill any existing worker/API processes from previous runs
pkill -f "python.*app.worker" 2>/dev/null && info "Stopped existing worker" || true
pkill -f "uvicorn.*app.main" 2>/dev/null && info "Stopped existing API" || true
sleep 1

# ─── 5. Start the RQ Worker (background) ─────────────────────────────────────
section "Starting RQ Worker"
cd "${INSTALL_DIR}"
source .venv/bin/activate
export $(grep -v '^#' .env 2>/dev/null | xargs 2>/dev/null) 2>/dev/null || true

nohup python3 -m app.worker > logs/worker.log 2>&1 &
WORKER_PID=$!
sleep 2

if kill -0 ${WORKER_PID} 2>/dev/null; then
    info "RQ Worker started (PID: ${WORKER_PID}) ✓"
else
    error "Worker failed to start. Check logs/worker.log"
fi

# ─── 6. Start the FastAPI server (background) ────────────────────────────────
section "Starting FastAPI API server"
nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${API_PORT} > logs/api.log 2>&1 &
API_PID=$!
sleep 3

if kill -0 ${API_PID} 2>/dev/null; then
    info "FastAPI server started (PID: ${API_PID}) ✓"
else
    error "API server failed to start. Check logs/api.log"
fi

# ─── 7. Health check ─────────────────────────────────────────────────────────
section "Running health check"
sleep 2
HEALTH=$(curl -s "http://127.0.0.1:${API_PORT}/health" 2>/dev/null || echo "")
if echo "$HEALTH" | grep -q '"status":"ok"'; then
    info "Health check passed ✓"
else
    warn "Health check did not return OK. The server may still be starting up."
    warn "Try: curl http://127.0.0.1:${API_PORT}/health"
fi

# ─── 8. Detect IP for remote access ──────────────────────────────────────────
HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [[ -z "$HOST_IP" ]]; then
    HOST_IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+' || echo "127.0.0.1")
fi

# ─── 9. Summary ──────────────────────────────────────────────────────────────
section "Installation Complete!"
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║         4K Video Transcoder — Ready to Use!                 ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${BOLD}Access the app:${RESET}"
echo ""
echo "    Local  : http://127.0.0.1:${API_PORT}/"
echo "    Network: http://${HOST_IP}:${API_PORT}/"
echo ""
echo -e "  ${BOLD}Process IDs:${RESET}"
echo ""
echo "    API Server : PID ${API_PID}"
echo "    RQ Worker  : PID ${WORKER_PID}"
echo ""
echo -e "  ${BOLD}Logs:${RESET}"
echo ""
echo "    API    : tail -f ${INSTALL_DIR}/logs/api.log"
echo "    Worker : tail -f ${INSTALL_DIR}/logs/worker.log"
echo ""
echo -e "  ${BOLD}Stop the app:${RESET}"
echo ""
echo "    kill ${API_PID} ${WORKER_PID}"
echo "    # Or: pkill -f 'uvicorn.*app.main'; pkill -f 'python.*app.worker'"
echo ""
echo -e "  ${BOLD}Restart later:${RESET}"
echo ""
echo "    cd ${INSTALL_DIR}"
echo "    bash start_worker.sh &"
echo "    bash start_api.sh"
echo ""
echo -e "${GREEN}Open your browser and go to: http://${HOST_IP}:${API_PORT}/${RESET}"
echo ""

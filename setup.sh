#!/usr/bin/env bash
# =============================================================================
# setup.sh — 4K Video Transcoder Setup Script
# Installs system dependencies, creates Python venv, installs pip packages,
# configures Redis, and prepares all runtime directories.
# Usage: bash setup.sh
# =============================================================================

set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()    { echo -e "${GREEN}[INFO]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; exit 1; }
section() { echo -e "\n${BOLD}==> $*${RESET}"; }

# ─── 1. Check OS ──────────────────────────────────────────────────────────────
section "Checking OS"
if [[ "$(uname -s)" != "Linux" ]]; then
    error "This script is designed for Linux only."
fi
info "Linux detected."

# ─── 2. Install system packages ───────────────────────────────────────────────
section "Installing system packages (ffmpeg, redis-server, python3-venv)"
sudo apt-get update -qq
sudo apt-get install -y ffmpeg redis-server python3-venv python3-pip curl
info "System packages installed."

# ─── 3. Verify ffmpeg & ffprobe ───────────────────────────────────────────────
section "Verifying FFmpeg"
ffmpeg -version 2>&1 | head -1 || error "ffmpeg not found in PATH"
ffprobe -version 2>&1 | head -1 || error "ffprobe not found in PATH"
info "FFmpeg OK."

# ─── 4. Create Python virtual environment ─────────────────────────────────────
section "Setting up Python virtual environment (.venv)"
if [[ ! -d ".venv" ]]; then
    python3 -m venv .venv
    info "Virtual environment created at .venv/"
else
    info "Virtual environment already exists, skipping creation."
fi

# ─── 5. Install Python dependencies ───────────────────────────────────────────
section "Installing Python dependencies"
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
info "Python dependencies installed."

# ─── 6. Create runtime directories ────────────────────────────────────────────
section "Creating runtime directories"
mkdir -p uploads outputs logs metrics
info "Directories created: uploads/ outputs/ logs/ metrics/"

# ─── 7. Configure and start Redis ─────────────────────────────────────────────
section "Configuring Redis"
if systemctl is-active --quiet redis-server 2>/dev/null; then
    info "Redis is already running via systemd."
elif systemctl is-active --quiet redis 2>/dev/null; then
    info "Redis is already running via systemd (redis)."
else
    warn "Redis not running via systemd. Starting manually..."
    redis-server --daemonize yes --logfile redis.log
    sleep 1
fi

# Verify Redis connectivity
if redis-cli ping | grep -q "PONG"; then
    info "Redis is responding to PING."
else
    error "Redis is not responding. Check redis.log for details."
fi

# ─── 8. Write environment config ──────────────────────────────────────────────
section "Writing .env configuration"
if [[ ! -f ".env" ]]; then
cat > .env <<EOF
# 4K Video Transcoder — Environment Configuration
# Edit REDIS_HOST when deploying worker on a separate VM (OpenStack VM-2)

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# API bind settings
API_HOST=0.0.0.0
API_PORT=8000
EOF
    info ".env file created."
else
    info ".env already exists, skipping."
fi

# ─── 9. Write start scripts ───────────────────────────────────────────────────
section "Writing convenience start scripts"

cat > start_api.sh <<'SCRIPT'
#!/usr/bin/env bash
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
echo "[API] Starting FastAPI on ${API_HOST:-0.0.0.0}:${API_PORT:-8000} ..."
uvicorn app.main:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8000}" --reload
SCRIPT
chmod +x start_api.sh

cat > start_worker.sh <<'SCRIPT'
#!/usr/bin/env bash
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
echo "[WORKER] Starting RQ worker (Redis: ${REDIS_HOST:-localhost}:${REDIS_PORT:-6379}) ..."
python3 -m app.worker
SCRIPT
chmod +x start_worker.sh

info "start_api.sh and start_worker.sh created."

# ─── 10. Summary ──────────────────────────────────────────────────────────────
section "Setup Complete"
echo ""
echo -e "${BOLD}Next steps:${RESET}"
echo ""
echo "  1. Start the worker (new terminal):"
echo "       bash start_worker.sh"
echo ""
echo "  2. Start the API (new terminal):"
echo "       bash start_api.sh"
echo ""
echo "  3. Open the frontend:"
echo "       Open index.html in your browser"
echo "       (API base: http://127.0.0.1:8000)"
echo ""
echo "  4. View KPI metrics:"
echo "       source .venv/bin/activate"
echo "       python3 kpi_viewer.py"
echo ""
echo "  5. Export KPI CSV:"
echo "       python3 kpi_viewer.py --csv"
echo ""
echo -e "${GREEN}Setup finished successfully.${RESET}"

#!/usr/bin/env bash
# =============================================================================
# openstack_deploy.sh — Automated OpenStack VM + App Deployment
# =============================================================================
# Creates the full 2-VM topology for the 4K Video Transcoder on DevStack:
#
#   VM-1 (transcoder-api)    : FastAPI + Redis  — gets a floating IP
#   VM-2 (transcoder-worker) : RQ Worker + FFmpeg — internal network only
#
# Prerequisites:
#   - DevStack is installed and running (run devstack_install.sh first)
#   - OpenStack credentials are sourced:
#       source /opt/stack/devstack/openrc admin admin
#   - This script is run from the project root directory
#
# Usage:
#   source /opt/stack/devstack/openrc admin admin
#   bash openstack_deploy.sh
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

# =============================================================================
# CONFIGURATION — Edit these values as needed
# =============================================================================
PROJECT_NAME="4k-video-transcoder"
REPO_DIR=$(pwd)                          # Current directory = project root

VM1_NAME="transcoder-api"
VM2_NAME="transcoder-worker"

FLAVOR_API="m1.medium"                   # 2 vCPU, 4GB RAM
FLAVOR_WORKER="m1.large"                 # 4 vCPU, 8GB RAM

IMAGE_NAME="ubuntu-22.04"                # Must match image uploaded to Glance
KEY_NAME="transcoder-key"                # SSH keypair name in OpenStack
KEY_FILE="${HOME}/.ssh/transcoder-key"   # Local path for the private key

NETWORK_NAME="transcoder-net"
SUBNET_NAME="transcoder-subnet"
ROUTER_NAME="transcoder-router"
SUBNET_CIDR="10.10.0.0/24"

SECGROUP_API="transcoder-api-sg"
SECGROUP_WORKER="transcoder-worker-sg"

API_PORT=8000
REDIS_PORT=6379
SSH_PORT=22
# =============================================================================

# ─── 0. Verify OpenStack credentials are sourced ──────────────────────────────
section "Verifying OpenStack credentials"
if ! openstack token issue &>/dev/null; then
    error "OpenStack credentials not found. Run: source /opt/stack/devstack/openrc admin admin"
fi
info "OpenStack credentials OK."

# ─── 1. Upload Ubuntu 22.04 image (if not present) ───────────────────────────
section "Checking VM image"
if openstack image show "${IMAGE_NAME}" &>/dev/null; then
    info "Image '${IMAGE_NAME}' already exists."
else
    warn "Image '${IMAGE_NAME}' not found. Downloading Ubuntu 22.04 cloud image..."
    UBUNTU_IMG_URL="https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
    TMP_IMG="/tmp/ubuntu-22.04-cloud.img"
    curl -L -o "${TMP_IMG}" "${UBUNTU_IMG_URL}"
    openstack image create "${IMAGE_NAME}" \
        --file "${TMP_IMG}" \
        --disk-format qcow2 \
        --container-format bare \
        --public
    rm -f "${TMP_IMG}"
    info "Image '${IMAGE_NAME}' uploaded."
fi

# ─── 2. Create SSH keypair ────────────────────────────────────────────────────
section "Setting up SSH keypair"
if openstack keypair show "${KEY_NAME}" &>/dev/null; then
    info "Keypair '${KEY_NAME}' already exists."
else
    mkdir -p "$(dirname ${KEY_FILE})"
    ssh-keygen -t rsa -b 4096 -f "${KEY_FILE}" -N "" -C "transcoder-deploy"
    openstack keypair create "${KEY_NAME}" --public-key "${KEY_FILE}.pub"
    info "Keypair '${KEY_NAME}' created. Private key: ${KEY_FILE}"
fi

# ─── 3. Create private network ────────────────────────────────────────────────
section "Creating private network"
if openstack network show "${NETWORK_NAME}" &>/dev/null; then
    info "Network '${NETWORK_NAME}' already exists."
else
    openstack network create "${NETWORK_NAME}"
    openstack subnet create "${SUBNET_NAME}" \
        --network "${NETWORK_NAME}" \
        --subnet-range "${SUBNET_CIDR}" \
        --dns-nameserver 8.8.8.8
    info "Network '${NETWORK_NAME}' and subnet '${SUBNET_NAME}' created."
fi

# Attach router to connect private network to external
if openstack router show "${ROUTER_NAME}" &>/dev/null; then
    info "Router '${ROUTER_NAME}' already exists."
else
    EXT_NET=$(openstack network list --external -f value -c Name | head -1)
    if [[ -z "$EXT_NET" ]]; then
        warn "No external network found. Floating IPs may not work."
    else
        openstack router create "${ROUTER_NAME}"
        openstack router set "${ROUTER_NAME}" --external-gateway "${EXT_NET}"
        openstack router add subnet "${ROUTER_NAME}" "${SUBNET_NAME}"
        info "Router '${ROUTER_NAME}' created and connected to '${EXT_NET}'."
    fi
fi

# ─── 4. Create security groups ────────────────────────────────────────────────
section "Creating security groups"

# VM-1 security group (API server — public access on 8000, SSH)
if openstack security group show "${SECGROUP_API}" &>/dev/null; then
    info "Security group '${SECGROUP_API}' already exists."
else
    openstack security group create "${SECGROUP_API}" \
        --description "4K Transcoder API server security group"
    # SSH
    openstack security group rule create "${SECGROUP_API}" \
        --protocol tcp --dst-port ${SSH_PORT} --remote-ip 0.0.0.0/0
    # API port (public)
    openstack security group rule create "${SECGROUP_API}" \
        --protocol tcp --dst-port ${API_PORT} --remote-ip 0.0.0.0/0
    # Redis (internal subnet only)
    openstack security group rule create "${SECGROUP_API}" \
        --protocol tcp --dst-port ${REDIS_PORT} --remote-ip "${SUBNET_CIDR}"
    # ICMP (ping)
    openstack security group rule create "${SECGROUP_API}" \
        --protocol icmp --remote-ip 0.0.0.0/0
    info "Security group '${SECGROUP_API}' created."
fi

# VM-2 security group (worker — SSH only, no public ports)
if openstack security group show "${SECGROUP_WORKER}" &>/dev/null; then
    info "Security group '${SECGROUP_WORKER}' already exists."
else
    openstack security group create "${SECGROUP_WORKER}" \
        --description "4K Transcoder Worker security group"
    openstack security group rule create "${SECGROUP_WORKER}" \
        --protocol tcp --dst-port ${SSH_PORT} --remote-ip 0.0.0.0/0
    openstack security group rule create "${SECGROUP_WORKER}" \
        --protocol icmp --remote-ip 0.0.0.0/0
    info "Security group '${SECGROUP_WORKER}' created."
fi

# ─── 5. Write cloud-init scripts ──────────────────────────────────────────────
section "Preparing cloud-init user-data scripts"

# VM-1 user-data: installs app, copies .env.vm1 BEFORE setup, enables systemd API service
cat > /tmp/vm1-userdata.sh <<'USERDATA'
#!/bin/bash
set -e
apt-get update -qq
apt-get install -y git ffmpeg redis-server python3-venv python3-pip curl

# Clone the repo
cd /home/ubuntu
git clone https://github.com/inz01/4k-video-transcoder.git 4k-video-transcoder || true
cd 4k-video-transcoder

# IMPORTANT: Copy VM-1 env config BEFORE running setup.sh
# setup.sh section 7b reads .env for REDIS_BIND_ALL=true to configure Redis
# for remote access (so VM-2 worker can connect over the private network).
# If .env is not present, Redis will only bind to 127.0.0.1.
cp .env.vm1 .env

# Run setup (installs venv + deps + dirs + configures Redis for remote access)
bash setup.sh

# Install systemd service for API
cp systemd/transcoder-api.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable transcoder-api
systemctl start transcoder-api

echo "VM-1 setup complete" >> /home/ubuntu/setup.log
USERDATA

# VM-2 user-data: installs app, injects VM-1 private IP, enables worker service
# VM1_PRIVATE_IP will be substituted after VM-1 is created
cat > /tmp/vm2-userdata-template.sh <<'USERDATA'
#!/bin/bash
set -e
apt-get update -qq
apt-get install -y git ffmpeg python3-venv python3-pip curl

# Clone the repo
cd /home/ubuntu
git clone https://github.com/inz01/4k-video-transcoder.git 4k-video-transcoder || true
cd 4k-video-transcoder

# IMPORTANT: Copy VM-2 env config BEFORE running setup.sh
# This ensures setup.sh section 8 does not create a default .env
# that would need to be overwritten afterwards.
cp .env.vm2 .env
sed -i "s/<VM1_PRIVATE_IP>/VM1_IP_PLACEHOLDER/" .env

# Run setup (installs venv + deps + dirs)
bash setup.sh

# Install systemd service for worker
cp systemd/transcoder-worker.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable transcoder-worker
systemctl start transcoder-worker

echo "VM-2 setup complete" >> /home/ubuntu/setup.log
USERDATA

info "Cloud-init scripts prepared."

# ─── 6. Launch VM-1 (API + Redis) ────────────────────────────────────────────
section "Launching VM-1: ${VM1_NAME}"
if openstack server show "${VM1_NAME}" &>/dev/null; then
    info "VM '${VM1_NAME}' already exists."
else
    openstack server create "${VM1_NAME}" \
        --flavor "${FLAVOR_API}" \
        --image "${IMAGE_NAME}" \
        --key-name "${KEY_NAME}" \
        --security-group "${SECGROUP_API}" \
        --network "${NETWORK_NAME}" \
        --user-data /tmp/vm1-userdata.sh \
        --wait
    info "VM '${VM1_NAME}' launched."
fi

# Get VM-1 private IP
VM1_PRIVATE_IP=$(openstack server show "${VM1_NAME}" \
    -f value -c addresses | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1)
info "VM-1 private IP: ${VM1_PRIVATE_IP}"

# ─── 7. Allocate and assign floating IP to VM-1 ───────────────────────────────
section "Assigning floating IP to VM-1"
EXT_NET=$(openstack network list --external -f value -c Name | head -1)
FLOATING_IP=""

if [[ -n "$EXT_NET" ]]; then
    # Check if VM-1 already has a floating IP
    EXISTING_FIP=$(openstack floating ip list --fixed-ip-address "${VM1_PRIVATE_IP}" \
        -f value -c "Floating IP Address" 2>/dev/null | head -1)

    if [[ -n "$EXISTING_FIP" ]]; then
        FLOATING_IP="${EXISTING_FIP}"
        info "VM-1 already has floating IP: ${FLOATING_IP}"
    else
        FLOATING_IP=$(openstack floating ip create "${EXT_NET}" -f value -c floating_ip_address)
        openstack server add floating ip "${VM1_NAME}" "${FLOATING_IP}"
        info "Floating IP ${FLOATING_IP} assigned to VM-1."
    fi
else
    warn "No external network found. Skipping floating IP assignment."
fi

# ─── 8. Launch VM-2 (Worker) ─────────────────────────────────────────────────
section "Launching VM-2: ${VM2_NAME}"

# Inject VM-1 private IP into VM-2 user-data
sed "s/VM1_IP_PLACEHOLDER/${VM1_PRIVATE_IP}/" /tmp/vm2-userdata-template.sh > /tmp/vm2-userdata.sh

if openstack server show "${VM2_NAME}" &>/dev/null; then
    info "VM '${VM2_NAME}' already exists."
else
    openstack server create "${VM2_NAME}" \
        --flavor "${FLAVOR_WORKER}" \
        --image "${IMAGE_NAME}" \
        --key-name "${KEY_NAME}" \
        --security-group "${SECGROUP_WORKER}" \
        --network "${NETWORK_NAME}" \
        --user-data /tmp/vm2-userdata.sh \
        --wait
    info "VM '${VM2_NAME}' launched."
fi

VM2_PRIVATE_IP=$(openstack server show "${VM2_NAME}" \
    -f value -c addresses | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1)
info "VM-2 private IP: ${VM2_PRIVATE_IP}"

# ─── 9. Update config.js with floating IP ────────────────────────────────────
section "Updating config.js with VM-1 floating IP"
if [[ -n "$FLOATING_IP" ]]; then
    # Update local copy (for reference / local frontend use)
    sed -i "s|window.API_BASE = \"http://127.0.0.1:8000\"|window.API_BASE = \"http://${FLOATING_IP}:8000\"|" \
        "${REPO_DIR}/config.js"
    info "Local config.js updated: API_BASE = http://${FLOATING_IP}:8000"

    # Update config.js on VM-1 so the frontend served by FastAPI uses the floating IP
    # Wait for VM-1 cloud-init to finish (SSH may not be ready immediately)
    info "Waiting for VM-1 SSH to become available..."
    for i in $(seq 1 30); do
        if ssh -i "${KEY_FILE}" -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
            ubuntu@"${FLOATING_IP}" "echo ready" &>/dev/null; then
            break
        fi
        sleep 10
    done

    ssh -i "${KEY_FILE}" -o StrictHostKeyChecking=no ubuntu@"${FLOATING_IP}" \
        "cd /home/ubuntu/4k-video-transcoder && \
         sed -i 's|window.API_BASE = \"http://127.0.0.1:8000\"|window.API_BASE = \"http://${FLOATING_IP}:8000\"|' config.js" \
        && info "VM-1 config.js updated: API_BASE = http://${FLOATING_IP}:8000" \
        || warn "Could not update config.js on VM-1 via SSH. Update manually after cloud-init completes."
else
    warn "No floating IP available. Update config.js manually with VM-1's IP."
fi

# ─── 10. Cleanup temp files ───────────────────────────────────────────────────
rm -f /tmp/vm1-userdata.sh /tmp/vm2-userdata-template.sh /tmp/vm2-userdata.sh

# ─── 11. Summary ─────────────────────────────────────────────────────────────
section "Deployment Complete"
echo ""
echo -e "${BOLD}Infrastructure Summary:${RESET}"
echo ""
echo "  VM-1 (API + Redis)"
echo "    Name        : ${VM1_NAME}"
echo "    Private IP  : ${VM1_PRIVATE_IP}"
echo "    Floating IP : ${FLOATING_IP:-N/A}"
echo "    API URL     : http://${FLOATING_IP:-<floating-ip>}:${API_PORT}"
echo ""
echo "  VM-2 (Worker)"
echo "    Name        : ${VM2_NAME}"
echo "    Private IP  : ${VM2_PRIVATE_IP}"
echo "    Redis target: ${VM1_PRIVATE_IP}:${REDIS_PORT}"
echo ""
echo -e "${BOLD}Verify deployment:${RESET}"
echo ""
echo "  # Health check (wait ~2 min for cloud-init to finish):"
echo "  curl http://${FLOATING_IP:-<floating-ip>}:${API_PORT}/health"
echo ""
echo "  # SSH into VM-1:"
echo "  ssh -i ${KEY_FILE} ubuntu@${FLOATING_IP:-<floating-ip>}"
echo ""
echo "  # SSH into VM-2 (via VM-1):"
echo "  ssh -i ${KEY_FILE} -J ubuntu@${FLOATING_IP:-<floating-ip>} ubuntu@${VM2_PRIVATE_IP}"
echo ""
echo -e "${BOLD}Frontend:${RESET}"
echo "  Open index.html in your browser."
echo "  config.js now points to: http://${FLOATING_IP:-<floating-ip>}:${API_PORT}"
echo ""
echo -e "${GREEN}OpenStack deployment finished.${RESET}"

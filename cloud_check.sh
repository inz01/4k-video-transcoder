#!/usr/bin/env bash
# =============================================================================
# cloud_check.sh — Post-Deployment Health Check & Verification
# =============================================================================
# Verifies that the OpenStack cloud deployment is healthy:
#   - Both VMs are ACTIVE
#   - SSH is reachable
#   - API and Worker services are running
#   - NFS mounts are active on VM-2
#   - API health endpoint responds
#
# Usage:
#   source /opt/stack/devstack/openrc admin admin
#   bash cloud_check.sh
#
# Options:
#   bash cloud_check.sh --restart    # Restart services on both VMs
#   bash cloud_check.sh --logs       # Show recent service logs
# =============================================================================

set -euo pipefail

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
RESET="\033[0m"

PASS="${GREEN}✓${RESET}"
FAIL="${RED}✗${RESET}"
WARN="${YELLOW}⚠${RESET}"

info()    { echo -e "${GREEN}[INFO]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $*"; }
error()   { echo -e "${RED}[FAIL]${RESET} $*"; }
section() { echo -e "\n${BOLD}${CYAN}── $* ──${RESET}"; }

# Configuration
VM1_NAME="transcoder-api"
VM2_NAME="transcoder-worker"
KEY_FILE="${HOME}/.ssh/transcoder-key"
API_PORT=8000
SSH_OPTS="-i ${KEY_FILE} -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes"

ACTION="${1:-check}"
ERRORS=0

# ─── 0. Verify OpenStack credentials ─────────────────────────────────────────
section "OpenStack Credentials"
if ! openstack token issue &>/dev/null; then
    error "OpenStack credentials not sourced."
    echo "  Run: source /opt/stack/devstack/openrc admin admin"
    exit 1
fi
echo -e "  ${PASS} Credentials OK"

# ─── 1. Check VM status ──────────────────────────────────────────────────────
section "VM Status"

VM1_STATUS=$(openstack server show "${VM1_NAME}" -f value -c status 2>/dev/null || echo "NOT_FOUND")
VM2_STATUS=$(openstack server show "${VM2_NAME}" -f value -c status 2>/dev/null || echo "NOT_FOUND")

if [[ "$VM1_STATUS" == "ACTIVE" ]]; then
    echo -e "  ${PASS} ${VM1_NAME}: ${VM1_STATUS}"
else
    echo -e "  ${FAIL} ${VM1_NAME}: ${VM1_STATUS}"
    ((ERRORS++))
    if [[ "$VM1_STATUS" == "SHUTOFF" ]]; then
        warn "  VM-1 is shut off. Start it: openstack server start ${VM1_NAME}"
    fi
fi

if [[ "$VM2_STATUS" == "ACTIVE" ]]; then
    echo -e "  ${PASS} ${VM2_NAME}: ${VM2_STATUS}"
else
    echo -e "  ${FAIL} ${VM2_NAME}: ${VM2_STATUS}"
    ((ERRORS++))
    if [[ "$VM2_STATUS" == "SHUTOFF" ]]; then
        warn "  VM-2 is shut off. Start it: openstack server start ${VM2_NAME}"
    fi
fi

# ─── 2. Get IPs ──────────────────────────────────────────────────────────────
section "Network"

VM1_PRIVATE_IP=$(openstack server show "${VM1_NAME}" \
    -f value -c addresses 2>/dev/null | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1 || echo "")
FLOATING_IP=$(openstack floating ip list --fixed-ip-address "${VM1_PRIVATE_IP}" \
    -f value -c "Floating IP Address" 2>/dev/null | head -1 || echo "")
VM2_PRIVATE_IP=$(openstack server show "${VM2_NAME}" \
    -f value -c addresses 2>/dev/null | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1 || echo "")

echo "  VM-1 Private IP : ${VM1_PRIVATE_IP:-unknown}"
echo "  VM-1 Floating IP: ${FLOATING_IP:-none}"
echo "  VM-2 Private IP : ${VM2_PRIVATE_IP:-unknown}"

if [[ -z "$FLOATING_IP" ]]; then
    warn "No floating IP assigned to VM-1. API may not be reachable externally."
    ((ERRORS++))
fi

# ─── 3. SSH connectivity ─────────────────────────────────────────────────────
section "SSH Connectivity"

if [[ -n "$FLOATING_IP" ]]; then
    if ssh ${SSH_OPTS} ubuntu@"${FLOATING_IP}" "echo ok" &>/dev/null; then
        echo -e "  ${PASS} VM-1 SSH reachable (${FLOATING_IP})"
        VM1_SSH=true
    else
        echo -e "  ${FAIL} VM-1 SSH unreachable (${FLOATING_IP})"
        VM1_SSH=false
        ((ERRORS++))
    fi

    if [[ "$VM1_SSH" == "true" ]] && [[ -n "$VM2_PRIVATE_IP" ]]; then
        if ssh ${SSH_OPTS} -J ubuntu@"${FLOATING_IP}" ubuntu@"${VM2_PRIVATE_IP}" "echo ok" &>/dev/null; then
            echo -e "  ${PASS} VM-2 SSH reachable via jump (${VM2_PRIVATE_IP})"
            VM2_SSH=true
        else
            echo -e "  ${FAIL} VM-2 SSH unreachable via jump (${VM2_PRIVATE_IP})"
            VM2_SSH=false
            ((ERRORS++))
        fi
    else
        VM2_SSH=false
    fi
else
    VM1_SSH=false
    VM2_SSH=false
    warn "Skipping SSH checks — no floating IP"
fi

# ─── 4. Service status ───────────────────────────────────────────────────────
section "Services"

if [[ "$VM1_SSH" == "true" ]]; then
    API_ACTIVE=$(ssh ${SSH_OPTS} ubuntu@"${FLOATING_IP}" \
        "systemctl is-active transcoder-api 2>/dev/null" || echo "unknown")
    REDIS_ACTIVE=$(ssh ${SSH_OPTS} ubuntu@"${FLOATING_IP}" \
        "systemctl is-active redis-server 2>/dev/null || systemctl is-active redis 2>/dev/null" || echo "unknown")

    if [[ "$API_ACTIVE" == "active" ]]; then
        echo -e "  ${PASS} VM-1 transcoder-api: active"
    else
        echo -e "  ${FAIL} VM-1 transcoder-api: ${API_ACTIVE}"
        ((ERRORS++))
    fi

    if [[ "$REDIS_ACTIVE" == "active" ]]; then
        echo -e "  ${PASS} VM-1 redis-server: active"
    else
        echo -e "  ${FAIL} VM-1 redis-server: ${REDIS_ACTIVE}"
        ((ERRORS++))
    fi
else
    echo -e "  ${WARN} VM-1 services: skipped (SSH unavailable)"
fi

if [[ "$VM2_SSH" == "true" ]]; then
    WORKER_ACTIVE=$(ssh ${SSH_OPTS} -J ubuntu@"${FLOATING_IP}" ubuntu@"${VM2_PRIVATE_IP}" \
        "systemctl is-active transcoder-worker 2>/dev/null" || echo "unknown")

    if [[ "$WORKER_ACTIVE" == "active" ]]; then
        echo -e "  ${PASS} VM-2 transcoder-worker: active"
    else
        echo -e "  ${FAIL} VM-2 transcoder-worker: ${WORKER_ACTIVE}"
        ((ERRORS++))
    fi
else
    echo -e "  ${WARN} VM-2 services: skipped (SSH unavailable)"
fi

# ─── 5. NFS mounts ───────────────────────────────────────────────────────────
section "NFS Shared Storage"

if [[ "$VM2_SSH" == "true" ]]; then
    NFS_COUNT=$(ssh ${SSH_OPTS} -J ubuntu@"${FLOATING_IP}" ubuntu@"${VM2_PRIVATE_IP}" \
        "mount | grep -c nfs4" 2>/dev/null || echo "0")

    if [[ "$NFS_COUNT" -ge 3 ]]; then
        echo -e "  ${PASS} VM-2 NFS mounts: ${NFS_COUNT} active (uploads, outputs, metrics)"
    else
        echo -e "  ${FAIL} VM-2 NFS mounts: only ${NFS_COUNT} (expected 3)"
        ((ERRORS++))
    fi
else
    echo -e "  ${WARN} NFS check: skipped (SSH unavailable)"
fi

# ─── 6. API health check ─────────────────────────────────────────────────────
section "API Health Check"

if [[ -n "$FLOATING_IP" ]]; then
    HEALTH=$(curl -s --connect-timeout 10 "http://${FLOATING_IP}:${API_PORT}/health" 2>/dev/null || echo "")
    if echo "$HEALTH" | grep -q '"status":"ok"'; then
        REDIS_STATUS=$(echo "$HEALTH" | grep -oP '"redis":"[^"]*"' | cut -d'"' -f4)
        echo -e "  ${PASS} http://${FLOATING_IP}:${API_PORT}/health → OK (redis: ${REDIS_STATUS})"
    elif [[ -n "$HEALTH" ]]; then
        echo -e "  ${WARN} http://${FLOATING_IP}:${API_PORT}/health → ${HEALTH}"
        ((ERRORS++))
    else
        echo -e "  ${FAIL} http://${FLOATING_IP}:${API_PORT}/health → no response"
        ((ERRORS++))
    fi
else
    echo -e "  ${WARN} API health check: skipped (no floating IP)"
fi

# ─── 7. Optional: Restart services ───────────────────────────────────────────
if [[ "$ACTION" == "--restart" ]]; then
    section "Restarting Services"

    if [[ "$VM1_SSH" == "true" ]]; then
        info "Restarting transcoder-api on VM-1..."
        ssh ${SSH_OPTS} ubuntu@"${FLOATING_IP}" \
            "sudo systemctl restart redis-server 2>/dev/null || sudo systemctl restart redis 2>/dev/null; sudo systemctl restart transcoder-api"
        echo -e "  ${PASS} VM-1 services restarted"
    fi

    if [[ "$VM2_SSH" == "true" ]]; then
        info "Restarting transcoder-worker on VM-2..."
        ssh ${SSH_OPTS} -J ubuntu@"${FLOATING_IP}" ubuntu@"${VM2_PRIVATE_IP}" \
            "sudo systemctl restart transcoder-worker"
        echo -e "  ${PASS} VM-2 worker restarted"
    fi
fi

# ─── 8. Optional: Show logs ──────────────────────────────────────────────────
if [[ "$ACTION" == "--logs" ]]; then
    section "Recent Logs"

    if [[ "$VM1_SSH" == "true" ]]; then
        echo -e "\n${BOLD}VM-1 API log (last 20 lines):${RESET}"
        ssh ${SSH_OPTS} ubuntu@"${FLOATING_IP}" \
            "tail -20 /home/ubuntu/4k-video-transcoder/logs/api.log 2>/dev/null || echo '  (no log file)'"
    fi

    if [[ "$VM2_SSH" == "true" ]]; then
        echo -e "\n${BOLD}VM-2 Worker log (last 20 lines):${RESET}"
        ssh ${SSH_OPTS} -J ubuntu@"${FLOATING_IP}" ubuntu@"${VM2_PRIVATE_IP}" \
            "tail -20 /home/ubuntu/4k-video-transcoder/logs/worker.log 2>/dev/null || echo '  (no log file)'"
    fi
fi

# ─── 9. Summary ──────────────────────────────────────────────────────────────
section "Summary"
echo ""
if [[ "$ERRORS" -eq 0 ]]; then
    echo -e "  ${GREEN}${BOLD}All checks passed ✓${RESET}"
    echo ""
    echo "  Cloud App UI : http://${FLOATING_IP}:${API_PORT}/"
    echo "  Health API   : http://${FLOATING_IP}:${API_PORT}/health"
else
    echo -e "  ${RED}${BOLD}${ERRORS} issue(s) found${RESET}"
    echo ""
    echo "  Troubleshooting:"
    echo "    bash cloud_check.sh --restart   # Restart all services"
    echo "    bash cloud_check.sh --logs      # View recent logs"
    echo "    See DEVSTACK_DEPLOYMENT.md §11 for detailed troubleshooting"
fi
echo ""

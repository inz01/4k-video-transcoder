# OpenStack DevStack Deployment Guide
## 4K Video Transcoder — Full Manual + Automated Instructions

**Stack:** FastAPI · Redis · RQ · FFmpeg · OpenStack DevStack  
**Topology:** VM-1 (API + Redis) ←private network→ VM-2 (Worker)

---

## Table of Contents

1. [Architecture](#1-architecture)
2. [Prerequisites](#2-prerequisites)
3. [Phase 1 — Install DevStack (Automated)](#3-phase-1--install-devstack-automated)
4. [Phase 1 — Install DevStack (Manual)](#4-phase-1--install-devstack-manual)
5. [Phase 2 — Deploy App to OpenStack (Automated)](#5-phase-2--deploy-app-to-openstack-automated)
6. [Phase 2 — Deploy App to OpenStack (Manual)](#6-phase-2--deploy-app-to-openstack-manual)
7. [Configuration Files Reference](#7-configuration-files-reference)
8. [Verify the Deployment](#8-verify-the-deployment)
9. [KPI Testing on OpenStack](#9-kpi-testing-on-openstack)
10. [Scaling Workers](#10-scaling-workers)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Architecture

```
Internet / Browser
        │
        ▼  HTTP :8000
┌───────────────────────┐
│  VM-1: transcoder-api │  ← Floating IP (public)
│  - FastAPI :8000      │
│  - Redis   :6379      │
└──────────┬────────────┘
           │ private network (10.10.0.0/24)
           ▼
┌───────────────────────┐
│ VM-2: transcoder-wrkr │  ← No public IP
│  - RQ Worker          │
│  - FFmpeg             │
└───────────────────────┘
```

**Why two VMs?**
- Separates API/queue from compute-heavy FFmpeg processing
- Demonstrates distributed OpenStack architecture
- Allows horizontal worker scaling (add VM-3, VM-4 workers)

---

## 2. Prerequisites

### Host machine requirements
- Ubuntu 22.04 LTS (recommended)
- Minimum 8 GB RAM, 4 vCPU, 60 GB disk
- Internet access (to download images and packages)
- Run as a non-root user with `sudo` access

### Software
```bash
sudo apt-get update
sudo apt-get install -y git curl python3 python3-pip net-tools
```

---

## 3. Phase 1 — Install DevStack (Automated)

This is the recommended approach. The script handles everything.

```bash
# From the project root directory:
sudo bash devstack_install.sh
```

**What the script does:**
1. Installs prerequisites (git, python3, curl)
2. Creates the `stack` user (DevStack requirement)
3. Clones DevStack from `https://opendev.org/openstack/devstack`
4. Auto-detects your host IP
5. Writes `local.conf` enabling: Nova, Neutron, Glance, Keystone, Cinder, Horizon
6. Runs `stack.sh` (takes 20–40 minutes)
7. Verifies the installation

**Expected output when complete:**
```
==> DevStack Installation Complete
  Horizon Dashboard : http://<HOST_IP>/dashboard
  Admin credentials : admin / secret
  OpenRC file       : /opt/stack/devstack/openrc
```

---

## 4. Phase 1 — Install DevStack (Manual)

Follow these steps if you prefer manual control.

### Step 1 — Create the stack user

```bash
sudo useradd -s /bin/bash -d /opt/stack -m stack
echo "stack ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/stack
sudo -u stack -i
```

### Step 2 — Clone DevStack

```bash
git clone https://opendev.org/openstack/devstack --branch stable/2024.2
cd devstack
```

### Step 3 — Write local.conf

```bash
cat > local.conf <<'EOF'
[[local|localrc]]
ADMIN_PASSWORD=secret
DATABASE_PASSWORD=secret
RABBIT_PASSWORD=secret
SERVICE_PASSWORD=secret

HOST_IP=<YOUR_HOST_IP>

# Services
enable_service n-api n-cpu n-cond n-sch n-novnc n-api-meta placement-api
# Networking — OVN (stable/2024.2 default; legacy q-agt/q-dhcp/q-l3/q-meta removed)
enable_service neutron q-svc q-ovn-metadata-agent
Q_AGENT=ovn
Q_ML2_PLUGIN_MECHANISM_DRIVERS=ovn
Q_ML2_PLUGIN_TYPE_DRIVERS=local,flat,vlan,geneve

# Image service (g-reg deprecated/removed in 2024.x)
enable_service g-api
enable_service keystone
enable_service cinder c-api c-vol c-sch
enable_service horizon

disable_service tempest
disable_service swift

LOGFILE=$DEST/logs/stack.sh.log
VERBOSE=True
LOG_COLOR=True

IMAGE_URLS="https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
EOF
```

> Replace `<YOUR_HOST_IP>` with your machine's IP:
> ```bash
> ip route get 8.8.8.8 | awk '{print $7}'
> ```

### Step 4 — Run stack.sh

```bash
./stack.sh
```

This takes **20–40 minutes**. Watch the log:
```bash
tail -f /opt/stack/logs/stack.sh.log
```

### Step 5 — Verify

```bash
source /opt/stack/devstack/openrc admin admin
openstack service list
openstack image list
```

---

## 5. Phase 2 — Deploy App to OpenStack (Automated)

### Step 1 — Update the repo URL in openstack_deploy.sh

Edit `openstack_deploy.sh` and replace `YOUR_USERNAME` with your GitHub username:
```bash
# Line ~100 in openstack_deploy.sh:
git clone https://github.com/YOUR_USERNAME/4k-video-transcoder.git
```

### Step 2 — Source OpenStack credentials

```bash
source /opt/stack/devstack/openrc admin admin
```

### Step 3 — Run the deployment script

```bash
bash openstack_deploy.sh
```

**What the script does:**
1. Uploads Ubuntu 22.04 image to Glance (if not present)
2. Creates SSH keypair (`~/.ssh/transcoder-key`)
3. Creates private network `transcoder-net` (10.10.0.0/24)
4. Creates router connecting private net to external network
5. Creates security groups (port 8000 public, 6379 internal, 22 SSH)
6. Launches VM-1 (`m1.medium`: 2 vCPU, 4 GB) with cloud-init
7. Allocates and assigns floating IP to VM-1
8. Launches VM-2 (`m1.large`: 4 vCPU, 8 GB) with cloud-init
9. Updates `config.js` with VM-1's floating IP automatically

---

## 6. Phase 2 — Deploy App to OpenStack (Manual)

### Step 1 — Source credentials

```bash
source /opt/stack/devstack/openrc admin admin
```

### Step 2 — Upload Ubuntu 22.04 image

```bash
curl -L -o /tmp/ubuntu-22.04.img \
  https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img

openstack image create "ubuntu-22.04" \
  --file /tmp/ubuntu-22.04.img \
  --disk-format qcow2 \
  --container-format bare \
  --public
```

### Step 3 — Create SSH keypair

```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/transcoder-key -N ""
openstack keypair create transcoder-key --public-key ~/.ssh/transcoder-key.pub
```

### Step 4 — Create private network

```bash
openstack network create transcoder-net
openstack subnet create transcoder-subnet \
  --network transcoder-net \
  --subnet-range 10.10.0.0/24 \
  --dns-nameserver 8.8.8.8

# Connect to external network via router
EXT_NET=$(openstack network list --external -f value -c Name | head -1)
openstack router create transcoder-router
openstack router set transcoder-router --external-gateway $EXT_NET
openstack router add subnet transcoder-router transcoder-subnet
```

### Step 5 — Create security groups

```bash
# VM-1: API server
openstack security group create transcoder-api-sg
openstack security group rule create transcoder-api-sg --protocol tcp --dst-port 22 --remote-ip 0.0.0.0/0
openstack security group rule create transcoder-api-sg --protocol tcp --dst-port 8000 --remote-ip 0.0.0.0/0
openstack security group rule create transcoder-api-sg --protocol tcp --dst-port 6379 --remote-ip 10.10.0.0/24
openstack security group rule create transcoder-api-sg --protocol icmp --remote-ip 0.0.0.0/0

# VM-2: Worker (SSH only)
openstack security group create transcoder-worker-sg
openstack security group rule create transcoder-worker-sg --protocol tcp --dst-port 22 --remote-ip 0.0.0.0/0
openstack security group rule create transcoder-worker-sg --protocol icmp --remote-ip 0.0.0.0/0
```

### Step 6 — Launch VM-1 (API + Redis)

```bash
openstack server create transcoder-api \
  --flavor m1.medium \
  --image ubuntu-22.04 \
  --key-name transcoder-key \
  --security-group transcoder-api-sg \
  --network transcoder-net \
  --wait
```

### Step 7 — Assign floating IP to VM-1

```bash
FLOATING_IP=$(openstack floating ip create $EXT_NET -f value -c floating_ip_address)
openstack server add floating ip transcoder-api $FLOATING_IP
echo "VM-1 Floating IP: $FLOATING_IP"
```

### Step 8 — Get VM-1 private IP

```bash
VM1_PRIVATE_IP=$(openstack server show transcoder-api \
  -f value -c addresses | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1)
echo "VM-1 Private IP: $VM1_PRIVATE_IP"
```

### Step 9 — Launch VM-2 (Worker)

```bash
openstack server create transcoder-worker \
  --flavor m1.large \
  --image ubuntu-22.04 \
  --key-name transcoder-key \
  --security-group transcoder-worker-sg \
  --network transcoder-net \
  --wait
```

### Step 10 — Set up VM-1 (SSH in)

```bash
ssh -i ~/.ssh/transcoder-key ubuntu@$FLOATING_IP
```

Inside VM-1:
```bash
sudo apt-get update
sudo apt-get install -y git ffmpeg redis-server python3-venv python3-pip

git clone https://github.com/YOUR_USERNAME/4k-video-transcoder.git
cd 4k-video-transcoder

bash setup.sh
cp .env.vm1 .env

# Install and start API as systemd service
sudo cp systemd/transcoder-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable transcoder-api
sudo systemctl start transcoder-api

# Verify
curl http://localhost:8000/health
```

### Step 11 — Set up VM-2 (SSH in via VM-1)

```bash
VM2_PRIVATE_IP=$(openstack server show transcoder-worker \
  -f value -c addresses | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1)

ssh -i ~/.ssh/transcoder-key \
    -J ubuntu@$FLOATING_IP \
    ubuntu@$VM2_PRIVATE_IP
```

Inside VM-2:
```bash
sudo apt-get update
sudo apt-get install -y git ffmpeg python3-venv python3-pip

git clone https://github.com/YOUR_USERNAME/4k-video-transcoder.git
cd 4k-video-transcoder

bash setup.sh
cp .env.vm2 .env

# Set VM-1 private IP
sed -i "s/<VM1_PRIVATE_IP>/$VM1_PRIVATE_IP/" .env

# Install and start worker as systemd service
sudo cp systemd/transcoder-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable transcoder-worker
sudo systemctl start transcoder-worker
```

### Step 12 — Update config.js with floating IP

On your local machine (project root):
```bash
# Edit config.js — replace the API_BASE line:
# window.API_BASE = "http://<FLOATING_IP>:8000";
nano config.js
```

---

## 7. Configuration Files Reference

### `config.js` — Frontend API endpoint

```javascript
window.API_BASE = "http://127.0.0.1:8000";        // local dev
// window.API_BASE = "http://<FLOATING_IP>:8000";  // OpenStack
```

Edit this file to switch between local and OpenStack deployment.

---

### `.env.vm1` — VM-1 environment (API + Redis)

```bash
REDIS_HOST=localhost    # Redis is local on VM-1
REDIS_PORT=6379
REDIS_DB=0
API_HOST=0.0.0.0
API_PORT=8000
```

Copy to `.env` on VM-1: `cp .env.vm1 .env`

---

### `.env.vm2` — VM-2 environment (Worker)

```bash
REDIS_HOST=<VM1_PRIVATE_IP>   # ← Replace with VM-1's private IP
REDIS_PORT=6379
REDIS_DB=0
```

Copy to `.env` on VM-2 and update the IP:
```bash
cp .env.vm2 .env
sed -i "s/<VM1_PRIVATE_IP>/10.10.0.X/" .env
```

---

### `systemd/transcoder-api.service` — API systemd unit

Installed on VM-1. Manages the FastAPI server with auto-restart.

```bash
sudo cp systemd/transcoder-api.service /etc/systemd/system/
sudo systemctl enable --now transcoder-api
sudo systemctl status transcoder-api
```

---

### `systemd/transcoder-worker.service` — Worker systemd unit

Installed on VM-2. Manages the RQ worker with auto-restart.

```bash
sudo cp systemd/transcoder-worker.service /etc/systemd/system/
sudo systemctl enable --now transcoder-worker
sudo systemctl status transcoder-worker
```

---

## 8. Verify the Deployment

### Health check

```bash
curl http://<FLOATING_IP>:8000/health
# Expected: {"status":"ok","redis":"connected"}
```

### End-to-end test

```bash
# Upload a video
JOB=$(curl -s -X POST http://<FLOATING_IP>:8000/upload \
  -F "file=@videos/sample_video_1093662-hd_1920_1080_30fps.mp4" \
  -F "preset=720p")
echo $JOB

JOB_ID=$(echo $JOB | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

# Poll progress
watch -n 2 "curl -s http://<FLOATING_IP>:8000/progress/$JOB_ID"

# Download output
curl -O -J http://<FLOATING_IP>:8000/download/$JOB_ID
```

### Check services on VMs

```bash
# VM-1
sudo systemctl status transcoder-api
sudo journalctl -u transcoder-api -f

# VM-2
sudo systemctl status transcoder-worker
sudo journalctl -u transcoder-worker -f
```

---

## 9. KPI Testing on OpenStack

Run the same video on different configurations and record results.

### Test procedure

```bash
# On VM-1 — run a job and capture metrics
JOB=$(curl -s -X POST http://<FLOATING_IP>:8000/upload \
  -F "file=@videos/sample_video_1093662-hd_1920_1080_30fps.mp4" \
  -F "preset=1080p")
JOB_ID=$(echo $JOB | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

# Wait for completion, then view KPI
curl -s http://<FLOATING_IP>:8000/jobs/$JOB_ID/metrics | python3 -m json.tool
```

### Expected KPI comparison

| Setup                  | Preset | Processing Time | Throughput (j/min) |
|------------------------|--------|----------------|-------------------|
| Local machine          | 1080p  | ~3.7s          | ~16.1             |
| OpenStack VM-1 (1 wkr) | 1080p  | ~90s           | ~0.67             |
| OpenStack VM-1+VM-2    | 1080p  | ~55s           | ~1.09             |

> Note: OpenStack DevStack VMs are slower than bare metal due to nested virtualisation.
> The key demonstration is the distributed architecture, not raw speed.

---

## 10. Scaling Workers

To add more workers (VM-3, VM-4, etc.):

```bash
# Launch additional worker VM
openstack server create transcoder-worker-2 \
  --flavor m1.large \
  --image ubuntu-22.04 \
  --key-name transcoder-key \
  --security-group transcoder-worker-sg \
  --network transcoder-net \
  --wait

# SSH in and set up (same as VM-2 setup)
# Point REDIS_HOST to VM-1's private IP
```

Each worker independently picks jobs from the same Redis queue — no code changes needed.

---

## 11. Troubleshooting

### `[ERROR] The q-agt/neutron-agt service must be disabled with OVN`

**Cause:** `local.conf` enables legacy ML2/OVS agents (`q-agt`, `q-dhcp`, `q-l3`, `q-meta`) alongside OVN networking. These are mutually exclusive in `stable/2024.2`.

**Fix:** Remove all legacy agents from `local.conf` and use OVN services instead:

```ini
# WRONG — causes conflict:
enable_service q-agt q-dhcp q-l3 q-meta

# CORRECT — OVN-compatible:
enable_service q-svc q-ovn-metadata-agent
Q_AGENT=ovn
Q_ML2_PLUGIN_MECHANISM_DRIVERS=ovn
Q_ML2_PLUGIN_TYPE_DRIVERS=local,flat,vlan,geneve
```

Then clean up and re-run:

```bash
sudo bash devstack_install.sh   # auto-cleanup + fresh install
```

---

### `ERROR 1698 (28000): Access denied for user 'root'@'localhost'` (MySQL)

**Cause:** Ubuntu 24.04 Noble uses `auth_socket` plugin for MySQL root by default. DevStack's `configure_database_mysql` sets the password via socket (`mysqladmin -u root password secret`) but then connects via TCP (`mysql -uroot -psecret -h127.0.0.1`), which fails because `auth_socket` ignores passwords on TCP connections.

**Fix (automated):** `devstack_install.sh` now includes a pre-configuration step (step 6b) that switches MySQL root to `mysql_native_password` before `stack.sh` runs. Simply re-run:

```bash
sudo bash devstack_install.sh
```

**Fix (manual):** If running stack.sh directly, pre-configure MySQL first:

```bash
# Install MySQL if not present
sudo apt-get install -y mysql-server
sudo systemctl start mysql

# Switch root to password auth (run as root — no password needed via socket)
sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'secret'; FLUSH PRIVILEGES;"

# Then run stack.sh
cd /opt/stack/devstack && ./stack.sh
```

---

### DevStack stack.sh fails

```bash
# Check the log
tail -100 /opt/stack/logs/stack.sh.log

# Clean up and retry
cd /opt/stack/devstack
./unstack.sh
./clean.sh
./stack.sh
```

### VM stuck in BUILD state

```bash
openstack server show transcoder-api
# Check nova logs on DevStack host:
sudo journalctl -u devstack@n-cpu -f
```

### API health check fails after deployment

```bash
# Wait 2–3 minutes for cloud-init to finish, then:
ssh -i ~/.ssh/transcoder-key ubuntu@$FLOATING_IP
sudo cloud-init status
cat /home/ubuntu/setup.log
sudo systemctl status transcoder-api
```

### Worker not picking up jobs

```bash
# On VM-2 — verify Redis connection
source .venv/bin/activate
python3 -c "from app.job_queue import redis_conn; print(redis_conn.ping())"
# Should print: True

# Check .env has correct VM-1 IP
cat .env

# Restart worker
sudo systemctl restart transcoder-worker
```

### Redis connection refused from VM-2

```bash
# On VM-1 — check Redis is listening on all interfaces
redis-cli config get bind
# Should include 0.0.0.0 or the private IP

# If only bound to 127.0.0.1, edit /etc/redis/redis.conf:
sudo sed -i "s/bind 127.0.0.1/bind 0.0.0.0/" /etc/redis/redis.conf
sudo systemctl restart redis-server

# Verify security group allows port 6379 from subnet
openstack security group rule list transcoder-api-sg
```

### Floating IP not reachable

```bash
# Verify floating IP is associated
openstack floating ip list

# Check security group has port 8000 open
openstack security group rule list transcoder-api-sg

# Verify API is running on VM-1
ssh -i ~/.ssh/transcoder-key ubuntu@$FLOATING_IP
curl http://localhost:8000/health
```

### Reset and redeploy

```bash
# Delete VMs
openstack server delete transcoder-api transcoder-worker

# Delete floating IPs
openstack floating ip list
openstack floating ip delete <id>

# Re-run deployment
bash openstack_deploy.sh

# TODO — 4K Video Transcoder: Local + OpenStack Deployment

---

## Phase 1 — Local App Setup & Testing
- [x] Step 1: Run `setup.sh` to install dependencies, create venv, start Redis
- [x] Step 2: Start the RQ Worker in background
- [x] Step 3: Start the FastAPI server (port 8000)

### API Testing (curl — local)
- [x] `GET /health` → `{"status":"ok","redis":"connected"}`
- [x] `POST /upload` (720p) → Job `6edb309e` queued → completed 100% in 1.8s
- [x] `POST /upload` (480p) → Job `25024635` queued → completed 100%
- [x] `POST /upload` (1080p) → Job `f7e0a205` queued → completed 100%
- [x] `GET /status/{job_id}` → Returns finished status with output path
- [x] `GET /progress/{job_id}` → Returns real-time progress (0-100%)
- [x] `GET /download/{job_id}` → HTTP 200, returns transcoded file (1.7MB for 720p)
- [x] `GET /jobs/{job_id}/metrics` → Returns detailed metrics (processing time, CPU, throughput)
- [x] Error: Invalid preset → HTTP 400 with proper message
- [x] Error: Non-existent download → HTTP 404 "Output not ready"

### Frontend Serving (local)
- [x] `GET /` → HTML 200 (6768 bytes)
- [x] `GET /script.js` → 200 (7145 bytes)
- [x] `GET /styles.css` → 200 (6248 bytes)
- [x] `GET /config.js` → 200 (820 bytes)

### UI Testing (Browser — local)
- [x] Page loads correctly with header, upload area, presets, custom settings
- [x] Preset buttons are interactive (click highlights selected preset)
- [x] "Start Transcoding" button properly disabled when no file selected
- [x] Custom settings (format, resolution, bitrate, codec, frame rate) all visible
- [x] Drag-and-drop upload zone visible and styled
- [ ] File upload via UI (requires native file dialog — tested via curl instead)

---

## Phase 2 — DevStack Installation
- [x] Installed DevStack (`stable/2024.2`) on host machine via `devstack_install.sh`
- [x] DevStack services verified: keystone, nova, neutron, glance, cinder, horizon active
- [x] OpenStack credentials working: `source /opt/stack/devstack/openrc admin admin`
- [x] Ubuntu 22.04 image available in Glance as `jammy-server-cloudimg-amd64`
- [x] Flavors available: `m1.medium` (2vCPU/4GB), `m1.large` (4vCPU/8GB)
- [x] External network `public` available for floating IPs

---

## Phase 3 — OpenStack VM Deployment
- [x] Fixed `IMAGE_NAME` in `openstack_deploy.sh`: `ubuntu-22.04` → `jammy-server-cloudimg-amd64`
- [x] Created SSH keypair: `transcoder-key` → `~/.ssh/transcoder-key`
- [x] Created private network: `transcoder-net` (10.10.0.0/24) + router → public
- [x] Created security groups: `transcoder-api-sg`, `transcoder-worker-sg`
- [x] Added NFS security group rules to `transcoder-api-sg` (TCP/UDP 2049, TCP 111)
- [x] Launched VM-1 `transcoder-api` (m1.medium): Private IP 10.10.0.203, Floating IP 172.24.4.59
- [x] Launched VM-2 `transcoder-worker` (m1.large): Private IP 10.10.0.186
- [x] Updated `config.js`: `API_BASE = http://172.24.4.59:8000`

---

## Phase 4 — NFS Shared Storage (Distributed Filesystem Fix)
- [x] Identified root cause: VM-2 worker could not access VM-1's `uploads/` directory
- [x] Installed `nfs-kernel-server` on VM-1
- [x] Configured `/etc/exports` on VM-1: exports `uploads/`, `outputs/`, `metrics/` to 10.10.0.0/24
- [x] Installed `nfs-common` on VM-2
- [x] Mounted NFS shares on VM-2 via NFSv4 from 10.10.0.203
- [x] Added persistent `/etc/fstab` entries on VM-2
- [x] Verified: `mount | grep nfs4` shows 3 active mounts on VM-2

---

## Phase 5 — Cloud API Testing (via Floating IP 172.24.4.59)
- [x] `GET /health` → `{"status":"ok","redis":"connected"}`
- [x] `GET /` → HTTP 200 (frontend served)
- [x] `POST /upload` (720p) → Job `8111768e` queued → completed 100%
- [x] `GET /progress/8111768e` → 100% completed
- [x] Output file on VM-1: `8111768e_output.mp4` (1.7MB) — visible from VM-2 via NFS ✓
- [x] `GET /download/8111768e` → HTTP 200, 1735740 bytes
- [x] `GET /jobs/8111768e/metrics` → processing_time=3.305s, cpu_after=80.4%
- [x] `POST /upload` (480p) → Job `0e741873` queued
- [x] `POST /upload` (1080p) → Job `7fb05a54` queued
- [x] `POST /upload` (4k) → Job `f4da8a9a` queued
- [x] `transcoder-api.service` active (running) on VM-1
- [x] `transcoder-worker.service` active (running) on VM-2

---

## Phase 6 — Script & Documentation Updates
- [x] Updated `openstack_deploy.sh`:
  - Fixed `IMAGE_NAME` to `jammy-server-cloudimg-amd64`
  - Added NFS security group rules (TCP/UDP 2049, TCP 111) to `transcoder-api-sg`
  - VM-1 cloud-init: added `nfs-kernel-server` + `/etc/exports` + `exportfs -ra`
  - VM-2 cloud-init: added `nfs-common` + NFS wait loop + `mount` + `fstab` persistence
  - Added post-deployment NFS verification step (step 10)
  - Added `exec > setup.log 2>&1` to both cloud-init scripts for full logging
  - Updated summary with NFS info and browser access URL
- [x] Updated `devstack_install.sh`:
  - Added disk space check (≥60 GB warning/error)
  - Added RAM check (≥8 GB warning/error)
  - Added note about Ubuntu image auto-download via `IMAGE_URLS`
- [x] Updated `MANUAL.md`:
  - Updated Section 10 architecture diagram to show NFS layer
  - Added NFS explanation (why shared storage is needed)
  - Added Phase 1 (DevStack install) and Phase 2 (deploy) automated instructions
  - Added "Accessing the Application" table with browser URL
  - Updated security group table with NFS ports (TCP/UDP 2049, TCP 111)
  - Added manual VM-1 and VM-2 setup instructions with NFS
  - Added NFS troubleshooting section
  - Added Redis remote access troubleshooting
  - Added cloud-init log check commands
  - Added reset/redeploy instructions

---

## Access the Running App
- **Web UI (browser):** http://172.24.4.59:8000/
- **Health check:** http://172.24.4.59:8000/health
- **SSH VM-1:** `ssh -i ~/.ssh/transcoder-key ubuntu@172.24.4.59`
- **SSH VM-2:** `ssh -i ~/.ssh/transcoder-key -J ubuntu@172.24.4.59 ubuntu@10.10.0.186`

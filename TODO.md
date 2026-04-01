# TODO — Full Clean Reinstall & Deploy

## Phase 1: Local Machine — Fresh Clone & Verify App
- [x] Step 1: Deactivate venv, delete local project files, fresh git clone
- [x] Step 2: Run setup.sh (installs deps, starts Redis)
- [x] Step 3: Start worker (start_worker.sh)
- [x] Step 4: Start API (start_api.sh)
- [x] Step 5: Verify app works locally (curl /health, open browser)

## Phase 2: Shahzaib's Machine — Clean DevStack
- [x] Step 6: Unstack DevStack (unstack.sh)
- [x] Step 7: Clean DevStack (clean.sh)
- [x] Step 8: Remove /opt/stack/devstack folder
- [x] Step 9: Remove /opt/stack/4k-video-transcoder project folder

## Phase 3: Shahzaib's Machine — Reinstall DevStack
- [x] Step 10: Run devstack_install.sh (20-40 min)
- [x] Step 11: Verify DevStack services active (keystone, nova, neutron, glance all running)

## Phase 4: Shahzaib's Machine — Deploy App to OpenStack
- [x] Step 12: Run openstack_deploy.sh
- [x] Step 13: Verify VM-1 floating IP + health check
- [x] Step 14: Open browser at http://172.24.4.69:8000/

## Phase 5: Bug Fixes & Final Verification
- [x] Fix: VM-1 logs/ permission (chown ubuntu:ubuntu) → transcoder-api.service active
- [x] Fix: VM-2 NFS wait — replaced showmount -e with nc -z port 2049 (reliable check)
- [x] Fix: VM-2 logs/ permission (chown ubuntu:ubuntu) → transcoder-worker.service active
- [x] Fix committed (387e538) and pushed to origin/main
- [x] Remote repo pulled on /opt/stack/4k-video-transcoder

## Deployment Summary (COMPLETE ✅)

| Component              | Status  | Details                                      |
|------------------------|---------|----------------------------------------------|
| DevStack               | ✅ ACTIVE | All OpenStack services running               |
| VM-1 transcoder-api    | ✅ ACTIVE | 10.10.0.178, floating IP 172.24.4.69         |
| VM-2 transcoder-worker | ✅ ACTIVE | 10.10.0.110, internal only                   |
| Redis (VM-1)           | ✅ active | Bound to 0.0.0.0:6379                        |
| transcoder-api.service | ✅ active | FastAPI on port 8000                         |
| transcoder-worker.service | ✅ active | Listening on transcode queue              |
| NFS mounts (VM-2)      | ✅ mounted | uploads/outputs/metrics → VM-1 (NFSv4)     |
| Redis connectivity     | ✅ PONG  | VM-2 → 10.10.0.178:6379                      |
| API health check       | ✅ OK    | {"status":"ok","redis":"connected"}          |
| Frontend               | ✅ served | http://172.24.4.69:8000/                    |

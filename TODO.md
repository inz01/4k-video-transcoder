# TODO — DevStack Deployment Compatibility Fixes

## Completed (Previous Session)
- [x] Setup app locally (setup.sh)
- [x] Start Redis, Worker, API
- [x] Upload sample video via curl — transcoding works
- [x] Verify UI interaction
- [x] Push to GitHub

## Current — Fix Missing Files for OpenStack Deployment
- [x] Step 1: Create `.env.vm1` — API+Redis VM config (Redis on 127.0.0.1, REDIS_BIND_ALL=true)
- [x] Step 2: Create `.env.vm2` — Worker VM config (Redis pointing to VM-1 IP placeholder)
- [x] Step 3: Create `systemd/transcoder-api.service` — Production-ready systemd unit for FastAPI
  - Uses .env vars for API_HOST/API_PORT (not hardcoded)
  - Requires redis-server.service
  - ExecStartPre creates logs dir
  - LimitNOFILE=65536
- [x] Step 4: Create `systemd/transcoder-worker.service` — Production-ready systemd unit for RQ Worker
  - Uses network-online.target (not just network.target)
  - ExecStartPre blocks until Redis is reachable (nc -z)
  - ExecStartPre creates logs dir
  - LimitNOFILE=65536
- [x] Step 5: Update `index.html` — Added `<script src="config.js">` before `script.js`
- [x] Step 6: Update `.gitignore` — Track `.env.vm1`, `.env.vm2` (exclude `.env`)
- [x] Step 7: Update `setup.sh` — Added Redis remote-bind config (REDIS_BIND_ALL), added netcat-openbsd
- [ ] Step 8: Commit and push all changes

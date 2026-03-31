# TODO — Deployment Scripts & Hardcoded IP Cleanup

## Completed
- [x] Step 1: Audit all files for hardcoded IPs (`172.24.4.59`) and paths
- [x] Step 2: Update `kpi_compare.py` — 3-tier auto-detection (env var → OpenStack CLI → fallback)
- [x] Step 3: Update `kpi_report/index.html` — JS auto-detection for cloud link
- [x] Step 4: Update `openstack_deploy.sh` — Step 11 post-deploy KPI config
- [x] Step 5: Update `.gitignore` — ignore generated `kpi_report/*.png`
- [x] Step 6: Create `cloud_check.sh` — post-deployment health check script
- [x] Step 7: Verify all edge cases (env var, CLI, fallback, browser JS, gitignore)
- [x] Step 8: Run `cloud_check.sh` — all checks passed ✓

## Scripts Overview

| Script | Purpose | When to Run |
|--------|---------|-------------|
| `devstack_install.sh` | Install OpenStack DevStack | Once (pre-deployment) |
| `setup.sh` | Local dev environment setup | Once (local dev) |
| `openstack_deploy.sh` | Deploy 2-VM cloud topology | After DevStack install |
| `cloud_check.sh` | Verify cloud deployment health | Post-deployment / anytime |
| `start_api.sh` | Start local API server | Local development |
| `start_worker.sh` | Start local RQ worker | Local development |
| `remote_install.sh` | One-command installer for any Linux machine | Remote deployment |

## Deployment Workflow
```
1. sudo bash devstack_install.sh          # Install DevStack (20-40 min)
2. source /opt/stack/devstack/openrc admin admin
3. bash openstack_deploy.sh               # Deploy VMs + app
4. bash cloud_check.sh                    # Verify everything works
5. Open http://<FLOATING_IP>:8000/        # Access cloud app

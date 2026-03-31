# TODO — DevStack & OpenStack Deploy Compatibility Fixes

- [x] Fix 1 (CRITICAL): Cloud-init ordering in `openstack_deploy.sh` — move `cp .env.vmX .env` BEFORE `bash setup.sh`
- [x] Fix 2 (CRITICAL): Update `config.js` on VM-1 via SSH after floating IP assignment in `openstack_deploy.sh`
- [x] Fix 3 (MINOR): Remove invalid `OPENSTACK_BRANCHES` from `devstack_install.sh` local.conf
- [x] Syntax check both scripts with `bash -n`
- [ ] Commit and push

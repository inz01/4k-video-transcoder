# TODO — Full Clean Reinstall & Deploy

## Phase 1: Local Machine — Fresh Clone & Verify App
- [ ] Step 1: Deactivate venv, delete local project files, fresh git clone
- [ ] Step 2: Run setup.sh (installs deps, starts Redis)
- [ ] Step 3: Start worker (start_worker.sh)
- [ ] Step 4: Start API (start_api.sh)
- [ ] Step 5: Verify app works locally (curl /health, open browser)

## Phase 2: Shahzaib's Machine — Clean DevStack
- [ ] Step 6: Unstack DevStack (unstack.sh)
- [ ] Step 7: Clean DevStack (clean.sh)
- [ ] Step 8: Remove /opt/stack/devstack folder
- [ ] Step 9: Remove /opt/stack/4k-video-transcoder project folder

## Phase 3: Shahzaib's Machine — Reinstall DevStack
- [ ] Step 10: Run devstack_install.sh (20-40 min)
- [ ] Step 11: Verify DevStack services active

## Phase 4: Shahzaib's Machine — Deploy App to OpenStack
- [ ] Step 12: Run openstack_deploy.sh
- [ ] Step 13: Verify VM-1 floating IP + health check
- [ ] Step 14: Open browser at http://<floating-ip>:8000/

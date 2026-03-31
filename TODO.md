# TODO — DevStack Reinstall + Cloud Deployment on Shahzaib's Machine

## Phase 1: Prepare Code
- [ ] Step 1: Change worker flavor to m1.small in openstack_deploy.sh
- [ ] Step 2: Git commit + push all changes to GitHub (origin/main)

## Phase 2: Clean Remote Machine
- [ ] Step 3: Stop local app processes (worker + API) on remote
- [ ] Step 4: Delete existing OpenStack VMs, floating IPs, security groups, networks, keypairs
- [ ] Step 5: Unstack + Clean DevStack on remote

## Phase 3: Fresh DevStack Install
- [ ] Step 6: Pull latest repo on remote (git pull or re-clone)
- [ ] Step 7: Run devstack_install.sh on remote (~20-40 min)
- [ ] Step 8: Verify DevStack services are running

## Phase 4: Deploy App to DevStack Cloud
- [ ] Step 9: Source openrc and run openstack_deploy.sh on remote
- [ ] Step 10: Wait for cloud-init (~3 min), verify VMs are ACTIVE

## Phase 5: Verify & Run
- [ ] Step 11: Health check: curl http://<floating-ip>:8000/health
- [ ] Step 12: SSH into VMs, check setup logs
- [ ] Step 13: Verify NFS mounts on VM-2
- [ ] Step 14: Access frontend via browser at http://<floating-ip>:8000/

## Connection Details
- SSH: `sshpass -p 'vbnm,vbnm,' ssh -o StrictHostKeyChecking=no shahzaib@100.81.231.113`
- Remote repo: ~/4k-video-transcoder
- DevStack: /opt/stack/devstack

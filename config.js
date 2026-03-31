// =============================================================================
// config.js — 4K Video Transcoder Frontend Configuration
// =============================================================================
// Edit this file to point the frontend at the correct API server.
//
// LOCAL DEVELOPMENT (default):
//   window.API_BASE = "http://127.0.0.1:8000";
//
// OPENSTACK DEPLOYMENT:
//   Replace the IP below with your VM-1 floating IP, e.g.:
//   window.API_BASE = "http://192.168.100.50:8000";
// =============================================================================

window.API_BASE = "http://127.0.0.1:8000";

// How often (ms) the frontend polls for job progress
window.PROGRESS_POLL_INTERVAL = 1000;

// How often (ms) the frontend polls for job status
window.STATUS_POLL_INTERVAL = 2000;

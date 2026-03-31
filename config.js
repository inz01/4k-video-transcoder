// =============================================================================
// config.js — 4K Video Transcoder Frontend Configuration
// =============================================================================
// API_BASE is auto-detected based on how the page is accessed:
//
//   - Opened as a local file (file://)  → uses http://127.0.0.1:8000
//   - Served from a remote server       → uses same hostname + port 8000
//
// This means the app works on ANY machine without manual IP changes.
//
// To override manually (e.g. custom port or HTTPS), uncomment and set:
//   window.API_BASE = "http://YOUR_IP_HERE:8000";
// =============================================================================

(function () {
    if (window.location.protocol === "file:") {
        // Opened directly as a local file — API must be on localhost
        window.API_BASE = "http://127.0.0.1:8000";
    } else {
        // Served from a web server — use the same host, port 8000
        window.API_BASE = window.location.protocol + "//" + window.location.hostname + ":8000";
    }
    console.log("[config] API_BASE set to:", window.API_BASE);
})();

// How often (ms) the frontend polls for job progress
window.PROGRESS_POLL_INTERVAL = 1000;

// How often (ms) the frontend polls for job status
window.STATUS_POLL_INTERVAL = 2000;

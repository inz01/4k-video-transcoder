# 4K Video Transcoder — Complete Setup Guide (Beginner-Friendly)

> **Who is this for?** A complete beginner on a fresh Ubuntu laptop who has never set up a Python project before.  
> **Time required:** ~10–15 minutes  
> **OS required:** Ubuntu 22.04 or 24.04 (Linux)

---

## Table of Contents

1. [Overview — What This App Does](#1-overview--what-this-app-does)
2. [What You Need Before Starting](#2-what-you-need-before-starting)
3. [Step 1: Open a Terminal](#step-1-open-a-terminal)
4. [Step 2: Install Git (if not installed)](#step-2-install-git-if-not-installed)
5. [Step 3: Clone the Repository from GitHub](#step-3-clone-the-repository-from-github)
6. [Step 4: Navigate into the Project Directory](#step-4-navigate-into-the-project-directory)
7. [Step 5: Install System Dependencies](#step-5-install-system-dependencies)
8. [Step 6: Run the Automated Setup Script](#step-6-run-the-automated-setup-script)
9. [Step 7: Start Redis Server](#step-7-start-redis-server)
10. [Step 8: Start the Worker (NEW Terminal)](#step-8-start-the-worker-new-terminal)
11. [Step 9: Start the API Server (ANOTHER NEW Terminal)](#step-9-start-the-api-server-another-new-terminal)
12. [Step 10: Verify Everything is Running](#step-10-verify-everything-is-running)
13. [Step 11: Open the Web UI in Your Browser](#step-11-open-the-web-ui-in-your-browser)
14. [Step 12: Upload and Transcode a Video](#step-12-upload-and-transcode-a-video)
15. [Step 13: View KPI Metrics](#step-13-view-kpi-metrics)
16. [Quick Reference — Terminal Cheat Sheet](#quick-reference--terminal-cheat-sheet)
17. [Troubleshooting Common Issues](#troubleshooting-common-issues)

---

## 1. Overview — What This App Does

This application lets you:
- **Upload** a video file through a web browser
- **Transcode** (convert) it to different resolutions (4K, 1080p, 720p, 480p) using FFmpeg
- **Track progress** in real-time with a progress bar
- **Download** the transcoded video
- **View performance metrics (KPIs)** like processing time, CPU usage, and throughput

The app has **3 components** that must all be running at the same time:

| Component | What it does | Port |
|-----------|-------------|------|
| **Redis Server** | Message broker — holds the job queue | 6379 |
| **RQ Worker** | Picks up jobs from Redis and runs FFmpeg to transcode videos | — |
| **FastAPI Server** | Web API — handles uploads, serves the web UI, reports progress | 8000 |

> **Important:** You will need **3 terminal windows** open simultaneously. Each runs one component.

---

## 2. What You Need Before Starting

- A computer running **Ubuntu 22.04 or 24.04** (or similar Debian-based Linux)
- An **internet connection** (to clone the repo and install packages)
- Your **sudo password** (the password you use to log into your computer)
- A **web browser** (Firefox, Chrome, etc.)

---

## Step 1: Open a Terminal

**How to open a terminal on Ubuntu:**
- Press `Ctrl + Alt + T` on your keyboard
- OR: Click "Activities" (top-left corner) → type "Terminal" → click on it

You should see something like:
```
username@computer:~$
```

This is your **command prompt**. You type commands here and press `Enter` to run them.

> 📌 **We'll call this Terminal 1.** Keep it open — you'll use it for setup and Redis.

---

## Step 2: Install Git (if not installed)

Git is a tool to download code from GitHub. Check if it's installed:

```bash
git --version
```

**If you see a version number** (e.g., `git version 2.34.1`), skip to Step 3.

**If you see "command not found"**, install it:

```bash
sudo apt-get update
sudo apt-get install -y git
```

> 💡 **What is `sudo`?** It runs a command with administrator privileges. It will ask for your password. When you type your password, **nothing will appear on screen** — this is normal. Just type it and press `Enter`.

---

## Step 3: Clone the Repository from GitHub

This downloads the project code to your computer.

**In Terminal 1**, run:

```bash
cd ~/Desktop
git clone https://github.com/inz01/4k-video-transcoder.git
```

You should see output like:
```
Cloning into '4k-video-transcoder'...
remote: Enumerating objects: 31, done.
...
Receiving objects: 100% (31/31), done.
```

> 📁 This creates a folder called `4k-video-transcoder` on your Desktop.

---

## Step 4: Navigate into the Project Directory

**In Terminal 1**, run:

```bash
cd ~/Desktop/4k-video-transcoder
```

Verify you're in the right place:

```bash
ls
```

You should see files like: `app/`, `index.html`, `requirements.txt`, `setup.sh`, etc.

> ⚠️ **IMPORTANT:** For ALL remaining commands, make sure you are inside this directory. If you ever get lost, run:
> ```bash
> cd ~/Desktop/4k-video-transcoder
> ```

---

## Step 5: Install System Dependencies

These are programs the app needs that aren't Python packages.

**In Terminal 1**, run:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg redis-server python3-venv python3-pip curl
```

Enter your password when prompted.

**Verify each installation:**

```bash
ffmpeg -version
```
✅ Should show: `ffmpeg version 4.x.x` or similar

```bash
ffprobe -version
```
✅ Should show: `ffprobe version 4.x.x` or similar

```bash
python3 --version
```
✅ Should show: `Python 3.10.x` or higher (3.9+ required)

```bash
redis-cli ping
```
✅ Should show: `PONG`

> If `redis-cli ping` does NOT show `PONG`, start Redis manually:
> ```bash
> sudo systemctl start redis-server
> redis-cli ping
> ```

---

## Step 6: Run the Automated Setup Script

This script does everything for you: creates a Python virtual environment, installs Python packages, creates necessary folders, and configures Redis.

**In Terminal 1**, run:

```bash
bash setup.sh
```

> 💡 **What is a virtual environment (venv)?** It's an isolated Python environment so this project's packages don't interfere with other Python projects on your system. The setup script creates one in a folder called `.venv/`.

You should see output ending with:
```
==> Setup Complete

Next steps:

  1. Start the worker (new terminal):
       bash start_worker.sh

  2. Start the API (new terminal):
       bash start_api.sh
  ...

Setup finished successfully.
```

✅ If you see "Setup finished successfully", proceed to the next step.

---

## Step 7: Start Redis Server

Redis should already be running from Step 5 or Step 6. Verify:

**In Terminal 1**, run:

```bash
redis-cli ping
```

✅ If it shows `PONG`, Redis is running. Move to Step 8.

❌ If it does NOT show `PONG`, start it:

```bash
redis-server --daemonize yes --logfile redis.log
```

Then verify again:
```bash
redis-cli ping
```

> 📌 **Terminal 1 is now free** — Redis runs in the background. You can use Terminal 1 for other commands later.

---

## Step 8: Start the Worker (NEW Terminal)

> ⚠️ **You MUST open a NEW terminal window for this step.** The worker needs to keep running continuously.

**How to open a new terminal:**
- Press `Ctrl + Alt + T`
- OR: Right-click on the desktop → "Open Terminal"

> 📌 **We'll call this Terminal 2.**

**In Terminal 2**, run these commands one by one:

```bash
cd ~/Desktop/4k-video-transcoder
```

```bash
source .venv/bin/activate
```

> 💡 **What does `source .venv/bin/activate` do?** It activates the Python virtual environment. You'll notice your prompt changes to show `(.venv)` at the beginning:
> ```
> (.venv) username@computer:~/Desktop/4k-video-transcoder$
> ```
> This means you're now using the project's isolated Python environment.

Now start the worker:

```bash
python -m app.worker
```

✅ You should see output like:
```
16:43:39 Worker abc123: started with PID 12345, version 2.7.0
16:43:39 *** Listening on transcode...
```

> ⚠️ **DO NOT close this terminal!** The worker must keep running. Leave it open and move to the next step.
> 
> If you accidentally close it, just repeat this step in a new terminal.

---

## Step 9: Start the API Server (ANOTHER NEW Terminal)

> ⚠️ **You MUST open ANOTHER new terminal window.** The API server also needs to keep running continuously.

**Open a third terminal** (`Ctrl + Alt + T`).

> 📌 **We'll call this Terminal 3.**

**In Terminal 3**, run these commands one by one:

```bash
cd ~/Desktop/4k-video-transcoder
```

```bash
source .venv/bin/activate
```

Now start the API server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

✅ You should see output like:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using StatReload
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

> ⚠️ **DO NOT close this terminal!** The API server must keep running.

---

## Step 10: Verify Everything is Running

Go back to **Terminal 1** (or open a new terminal) and run:

```bash
curl http://127.0.0.1:8000/health
```

✅ You should see:
```json
{"status":"ok","redis":"connected"}
```

This confirms:
- ✅ The API server is running on port 8000
- ✅ Redis is connected and responding

**Check all 3 components are running:**

```bash
ps aux | grep -E "uvicorn|app.worker|redis-server" | grep -v grep
```

You should see 3 processes listed (redis-server, app.worker, uvicorn).

---

## Step 11: Open the Web UI in Your Browser

Open your web browser (Firefox, Chrome, etc.) and go to:

```
http://127.0.0.1:8000
```

OR alternatively, you can open the HTML file directly:

```bash
xdg-open ~/Desktop/4k-video-transcoder/index.html
```

You should see the **4K Video Transcoder** web interface with:
- A file upload area
- A preset selector (4K, 1080p, 720p, 480p)
- A "Start Transcoding" button

---

## Step 12: Upload and Transcode a Video

### Option A: Using the Web UI (Recommended for beginners)

1. In the web browser, click **"Choose File"** or the upload area
2. Select any `.mp4` video file from your computer
3. Select a **preset** (e.g., `720p` for a quick test)
4. Click **"Start Transcoding"**
5. Watch the **progress bar** fill up in real-time
6. When it reaches 100%, click **"Download"** to get the transcoded video

### Option B: Using curl (Command Line)

If you don't have a video file, you can create a small test video first:

```bash
cd ~/Desktop/4k-video-transcoder
ffmpeg -f lavfi -i testsrc=duration=5:size=1920x1080:rate=30 -c:v libx264 -pix_fmt yuv420p test_video.mp4
```

Then upload it:

```bash
curl -X POST http://127.0.0.1:8000/upload \
  -F "file=@test_video.mp4" \
  -F "preset=720p"
```

You'll get a response like:
```json
{"job_id": "abc123-def456-...", "status": "queued", "preset": "720p"}
```

**Copy the `job_id` value** and check progress:

```bash
curl http://127.0.0.1:8000/progress/YOUR_JOB_ID_HERE
```

Wait a few seconds and check again until `"status": "completed"` and `"progress": 100.0`.

Download the result:

```bash
curl -O -J http://127.0.0.1:8000/download/YOUR_JOB_ID_HERE
```

---

## Step 13: View KPI Metrics

After transcoding at least one video, you can view performance metrics.

**In Terminal 1** (or any free terminal), run:

```bash
cd ~/Desktop/4k-video-transcoder
source .venv/bin/activate
python kpi_viewer.py
```

This shows a summary including:
- Total jobs completed/failed
- Processing time (min/max/average)
- End-to-end latency
- Queue wait time
- Throughput (jobs per minute)
- CPU usage
- Per-preset breakdown

**Export to CSV:**

```bash
python kpi_viewer.py --csv
```

This creates `metrics/kpi_export.csv` which you can open in Excel or Google Sheets.

**Filter by preset:**

```bash
python kpi_viewer.py --preset 720p
```

---

## Quick Reference — Terminal Cheat Sheet

Here's a summary of which terminal runs what:

| Terminal | Purpose | Command | Can I close it? |
|----------|---------|---------|-----------------|
| **Terminal 1** | Setup + general use | Various commands | ✅ Yes (after setup) |
| **Terminal 2** | RQ Worker | `source .venv/bin/activate && python -m app.worker` | ❌ NO — must stay open |
| **Terminal 3** | API Server | `source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` | ❌ NO — must stay open |

### How to stop the app

- **Stop API Server:** Go to Terminal 3 and press `Ctrl + C`
- **Stop Worker:** Go to Terminal 2 and press `Ctrl + C`
- **Stop Redis:** `redis-cli shutdown` or `sudo systemctl stop redis-server`

### How to restart the app (after a reboot or closing terminals)

```bash
# Terminal 1: Start Redis (if not auto-started)
cd ~/Desktop/4k-video-transcoder
redis-server --daemonize yes --logfile redis.log

# Terminal 2: Start Worker
cd ~/Desktop/4k-video-transcoder
source .venv/bin/activate
python -m app.worker

# Terminal 3: Start API
cd ~/Desktop/4k-video-transcoder
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Troubleshooting Common Issues

### "command not found: uvicorn"

You forgot to activate the virtual environment. Run:
```bash
source .venv/bin/activate
```
Then try the command again.

### "redis-cli: command not found"

Redis is not installed. Run:
```bash
sudo apt-get install -y redis-server
```

### "Address already in use" when starting the API

Another process is using port 8000. Kill it:
```bash
sudo kill $(sudo lsof -t -i:8000)
```
Then start the API again.

### Worker says "*** Listening on transcode..." but nothing happens

- Make sure you uploaded a video through the API (Step 12)
- Check that Redis is running: `redis-cli ping` should return `PONG`
- Check the worker log for errors: look at Terminal 2's output

### Progress stuck at 0%

- Check Terminal 2 (worker) for error messages
- Make sure FFmpeg is installed: `ffmpeg -version`
- Check the log: `cat logs/app.log | tail -20`

### "No module named 'app'" error

You're not in the project directory. Run:
```bash
cd ~/Desktop/4k-video-transcoder
```

### Web UI shows "Failed to fetch" or "Network Error"

- Make sure the API server is running (Terminal 3)
- Make sure you're accessing `http://127.0.0.1:8000` (not `https`)
- Check Terminal 3 for error messages

### Need to start fresh (reset all data)

```bash
cd ~/Desktop/4k-video-transcoder
rm -rf uploads/* outputs/* metrics/* logs/*
redis-cli flushdb
```

---

## Summary of All Commands (Copy-Paste Ready)

```bash
# === ONE-TIME SETUP (do this only once) ===

# 1. Clone the repo
cd ~/Desktop
git clone https://github.com/inz01/4k-video-transcoder.git
cd 4k-video-transcoder

# 2. Install system packages
sudo apt-get update
sudo apt-get install -y ffmpeg redis-server python3-venv python3-pip curl git

# 3. Run setup script
bash setup.sh

# === START THE APP (do this every time) ===

# Terminal 1: Verify Redis
redis-cli ping    # Should show PONG

# Terminal 2: Start Worker
cd ~/Desktop/4k-video-transcoder
source .venv/bin/activate
python -m app.worker

# Terminal 3: Start API
cd ~/Desktop/4k-video-transcoder
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# === USE THE APP ===

# Open browser to: http://127.0.0.1:8000
# Upload a video, select preset, click Start Transcoding

# === VIEW METRICS ===
cd ~/Desktop/4k-video-transcoder
source .venv/bin/activate
python kpi_viewer.py
python kpi_viewer.py --csv

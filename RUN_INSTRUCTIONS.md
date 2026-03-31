# How to Run the 4K Video Transcoder Project

This document provides a step-by-step guide to set up and run the 4K Video Transcoder application locally.

## 1. Prerequisites

Ensure you have the necessary system packages installed. Open a terminal and run:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg redis-server python3-venv python3-pip curl
```

Verify the installations:

```bash
ffmpeg -version
ffprobe -version
redis-cli ping # Should return PONG
python3 --version # Should be Python 3.9+
```

## 2. Installation & Setup

Navigate to your project directory (`4k-video-transcoder/`).

### Automated Setup (Recommended)

Run the provided setup script:

```bash
bash setup.sh
```

This script handles virtual environment creation, dependency installation, directory setup, and Redis startup.

### Manual Setup (Alternative)

If you prefer manual setup:

```bash
# 1. Create and activate a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Create necessary runtime directories
mkdir -p uploads outputs logs metrics

# 4. Start Redis server (if not already running via systemd)
redis-server --daemonize yes --logfile redis.log
```

## 3. Starting the Application

You will need **three separate terminal windows** open in the project directory to run the application components.

### Terminal 1: Start Redis Server (if not using `setup.sh` or systemd)

If `redis-server` is not already running (e.g., if you did not use `setup.sh` or `sudo systemctl start redis-server`), start it:

```bash
redis-server --daemonize yes --logfile redis.log
```

You can verify it's running with `redis-cli ping`.

### Terminal 2: Start the RQ Worker

Open a **new terminal** window, navigate to the project directory, and run:

```bash
source .venv/bin/activate
python -m app.worker
```

You should see output similar to `*** Listening on transcode...`.

### Terminal 3: Start the FastAPI Backend

Open a **third new terminal** window, navigate to the project directory, and run:

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

You should see output indicating that Uvicorn is running, for example: `INFO: Uvicorn running on http://0.0.0.0:8000`.

## 4. Accessing the Web UI

Once all three components (Redis, Worker, API) are running, you can access the web interface:

1.  Open your web browser.
2.  Navigate to the `index.html` file located in your project directory. You can usually do this by double-clicking the file or by using a command like `xdg-open index.html` (on Linux).

The frontend will automatically connect to the FastAPI backend running at `http://127.0.0.1:8000`. You can then upload videos, select presets, and monitor transcoding progress.
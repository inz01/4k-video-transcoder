# TODO — Start App & Sample Video Upload

- [x] Step 1: Run `setup.sh` to install dependencies, create venv, start Redis
- [x] Step 2: Start the RQ Worker in background
- [x] Step 3: Start the FastAPI server
- [x] Step 4: Upload a sample video via `curl`
- [x] Step 5: Check job status/progress via API
- [x] Step 6: Verify frontend config.js loading and UI integration
- [x] Step 7: Test all presets (4k, 1080p, 720p, 480p)
- [x] Step 8: Verify worker log — no errors

## Bugs Found & Fixed

### Bug 1: Missing `/config.js` route in `app/main.py`
- **Problem**: `index.html` references `<script src="config.js">` but `app/main.py` had no route to serve it, returning 404.
- **Fix**: Added `@app.get("/config.js")` route in `app/main.py` to serve `config.js` from the project root.

### Bug 2: Redis config file path detection in `setup.sh`
- **Problem**: `redis-cli INFO server` output contains `\r` (carriage return) which broke the `grep` pipeline for extracting the config file path.
- **Fix**: Added `tr -d '\r'` to the pipeline in `setup.sh`.

### Bug 3: Redis config file permission check in `setup.sh`
- **Problem**: `[[ -f "$REDIS_CONF" ]]` fails without sudo since `/etc/redis/redis.conf` is permission-restricted.
- **Fix**: Changed to `sudo test -f "$REDIS_CONF"` in `setup.sh`.

## Test Results

### API Endpoint Tests
- ✅ `GET /health` — `{"status":"ok","redis":"connected"}`
- ✅ `GET /` — Frontend HTML loads
- ✅ `GET /config.js` — Config served (after bugfix)
- ✅ `GET /script.js` — JavaScript served
- ✅ `GET /styles.css` — CSS served
- ✅ `POST /upload` — Video uploaded, job queued
- ✅ `GET /progress/{job_id}` — Returns progress
- ✅ `GET /status/{job_id}` — Returns job status
- ✅ `GET /download/{job_id}` — Returns output file (200, correct size)
- ✅ `GET /jobs/{job_id}/metrics` — Returns processing metrics

### Preset Tests (all using 1080p source video)
| Preset | Processing Time | Output Size | Status |
|--------|----------------|-------------|--------|
| 4k     | 18.6s          | 26MB        | ✅ OK  |
| 1080p  | 3.7s           | 5.8MB       | ✅ OK  |
| 720p   | 1.9s           | 1.7MB       | ✅ OK  |
| 480p   | 1.1s           | 622KB       | ✅ OK  |

### Worker Log
- ✅ No errors — all jobs completed successfully

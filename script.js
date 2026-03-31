const videoInput = document.getElementById("videoInput");
const transcodeBtn = document.getElementById("transcodeBtn");

const previewSection = document.getElementById("videoPreview");
const previewVideo = document.getElementById("previewVideo");

const fileNameEl = document.getElementById("fileName");
const fileSizeEl = document.getElementById("fileSize");
const durationEl = document.getElementById("duration");
const resolutionEl = document.getElementById("resolution");

const progressSection = document.getElementById("progressSection");
const progressBar = document.getElementById("progressBar");
const progressInfo = document.getElementById("progressInfo");

const downloadSection = document.getElementById("downloadSection");
const downloadBtn = document.getElementById("downloadBtn");

const errorMessage = document.getElementById("errorMessage");

const uploadSection = document.getElementById("uploadSection");
const uploadBtn = document.querySelector(".upload-btn");

let selectedFile = null;

const API_BASE = window.API_BASE || "http://127.0.0.1:8000";


// ==========================
// FILE INPUT TRIGGER
// ==========================
if (uploadBtn) {
    uploadBtn.addEventListener("click", (e) => {
        e.preventDefault();
        videoInput.click();
    });
}


// ==========================
// PRESET BUTTON SELECTION
// ==========================
document.querySelectorAll(".preset-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".preset-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
    });
});


// ==========================
// DRAG AND DROP
// ==========================
if (uploadSection) {
    uploadSection.addEventListener("dragover", (e) => {
        e.preventDefault();
        uploadSection.classList.add("dragover");
    });

    uploadSection.addEventListener("dragleave", (e) => {
        e.preventDefault();
        uploadSection.classList.remove("dragover");
    });

    uploadSection.addEventListener("drop", (e) => {
        e.preventDefault();
        uploadSection.classList.remove("dragover");
        const files = e.dataTransfer.files;
        if (files.length > 0 && files[0].type.startsWith("video/")) {
            selectedFile = files[0];
            handleFileSelected(selectedFile);
        }
    });
}


// ==========================
// FILE SELECT + PREVIEW
// ==========================
videoInput.addEventListener("change", (e) => {
    selectedFile = e.target.files[0];
    if (!selectedFile) return;
    handleFileSelected(selectedFile);
});

function handleFileSelected(file) {
    // Enable button
    transcodeBtn.disabled = false;

    // Show preview
    const videoURL = URL.createObjectURL(file);
    previewVideo.src = videoURL;
    previewSection.style.display = "block";

    // File info
    fileNameEl.innerText = file.name;
    fileSizeEl.innerText = (file.size / (1024 * 1024)).toFixed(2) + " MB";

    // Load metadata
    previewVideo.onloadedmetadata = () => {
        durationEl.innerText = formatTime(previewVideo.duration);
        resolutionEl.innerText = `${previewVideo.videoWidth}x${previewVideo.videoHeight}`;
    };
}


// ==========================
// TRANSCODE BUTTON CLICK
// ==========================
transcodeBtn.addEventListener("click", async () => {
    if (!selectedFile) return;

    resetUI();

    const formData = new FormData();
    formData.append("file", selectedFile);

    const selectedPreset = document.querySelector(".preset-btn.active")?.dataset.preset || "1080p";
    const mappedPreset = mapPreset(selectedPreset);
    formData.append("preset", mappedPreset);

    progressSection.style.display = "block";
    progressInfo.innerText = "Uploading video...";

    try {
        const response = await fetch(`${API_BASE}/upload`, {
            method: "POST",
            body: formData
        });

        if (!response.ok) {
            throw new Error("Upload failed");
        }

        const data = await response.json();
        const jobId = data.job_id;

        progressInfo.innerText = "Processing started...";

        trackRealProgress(jobId);
        checkStatus(jobId);

    } catch (err) {
        showError("Upload failed. Check backend or network.");
        console.error(err);
    }
});


// ==========================
// STATUS POLLING
// ==========================
async function checkStatus(jobId) {
    const interval = setInterval(async () => {
        try {
            const res = await fetch(`${API_BASE}/status/${jobId}`);
            const data = await res.json();

            progressInfo.innerText = `Status: ${data.status}`;

            if (data.status === "finished" || data.status === "completed") {
                clearInterval(interval);

                progressBar.style.width = "100%";
                progressBar.innerText = "100%";

                progressInfo.innerText = "Transcoding complete";

                showDownload(jobId);
            }

            if (data.status === "failed") {
                clearInterval(interval);
                showError("Transcoding failed");
            }

        } catch (err) {
            console.error(err);
        }
    }, 2000);
}


// ==========================
// DOWNLOAD HANDLER
// ==========================
function showDownload(jobId) {
    downloadSection.style.display = "block";

    downloadBtn.onclick = () => {
        window.location.href = `${API_BASE}/download/${jobId}`;
    };
}


// ==========================
// FAKE PROGRESS (UI ONLY)
// ==========================
async function trackRealProgress(jobId) {
    const interval = setInterval(async () => {
        try {
            const res = await fetch(`${API_BASE}/progress/${jobId}`);
            const data = await res.json();

            const percent = Math.min(Number(data.progress || 0), 100);
            progressBar.style.width = percent + "%";
            progressBar.innerText = Math.floor(percent) + "%";

            if (data.status === "completed" || percent >= 100) {
                clearInterval(interval);
            }

            if (data.status === "failed") {
                clearInterval(interval);
                showError("Transcoding failed during processing");
            }
        } catch (err) {
            console.error(err);
        }
    }, 1000);
}


// ==========================
// HELPERS
// ==========================
function mapPreset(preset) {
    if (preset === "4k-high" || preset === "4k-balanced") return "4k";
    if (preset === "1080p") return "1080p";
    if (preset === "720p") return "720p";
    if (preset === "480p") return "480p";
    return "1080p";
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
}

function showError(msg) {
    errorMessage.style.display = "block";
    errorMessage.innerText = msg;
}

function resetUI() {
    progressBar.style.width = "0%";
    progressBar.innerText = "0%";
    downloadSection.style.display = "none";
    errorMessage.style.display = "none";
}

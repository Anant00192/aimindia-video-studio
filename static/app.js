document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const connectionStatus = document.getElementById('connectionStatus');
    const connectionText = document.getElementById('connectionText');
    const dot = connectionStatus.querySelector('.dot');

    const activeUsernameDisplay = document.getElementById('activeUsernameDisplay');
    const accountTagBadge = document.getElementById('accountTagBadge');
    const toggleCredsBtn = document.getElementById('toggleCredsBtn');
    const credsForm = document.getElementById('credsForm');
    const kaggleUsernameInput = document.getElementById('kaggleUsername');
    const kaggleKeyInput = document.getElementById('kaggleKey');
    const resetDefaultCredsBtn = document.getElementById('resetDefaultCredsBtn');

    const videoDropzone = document.getElementById('videoDropzone');
    const videoFileInput = document.getElementById('videoFileInput');
    const videoList = document.getElementById('videoList');

    const activeLogoImg = document.getElementById('activeLogoImg');
    const activeLogoTitle = document.getElementById('activeLogoTitle');
    const activeLogoMeta = document.getElementById('activeLogoMeta');
    const uploadLogoBtn = document.getElementById('uploadLogoBtn');
    const logoFileInput = document.getElementById('logoFileInput');
    const resetLogoBtn = document.getElementById('resetLogoBtn');

    // Sliders
    const sliderTrimSec = document.getElementById('sliderTrimSec');
    const valTrimSec = document.getElementById('valTrimSec');
    const sliderZoomPct = document.getElementById('sliderZoomPct');
    const valZoomPct = document.getElementById('valZoomPct');
    const sliderLogoWidth = document.getElementById('sliderLogoWidth');
    const valLogoWidth = document.getElementById('valLogoWidth');
    const sliderXOffset = document.getElementById('sliderXOffset');
    const valXOffset = document.getElementById('valXOffset');
    const sliderYOffset = document.getElementById('sliderYOffset');
    const valYOffset = document.getElementById('valYOffset');

    const previewBtn = document.getElementById('previewBtn');
    const previewStage = document.getElementById('previewStage');
    const previewImg = document.getElementById('previewImg');
    const previewPlaceholder = document.getElementById('previewPlaceholder');

    const launchBtn = document.getElementById('launchBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const progressStatusText = document.getElementById('progressStatusText');
    const progressPctText = document.getElementById('progressPctText');

    const terminalBody = document.getElementById('terminalBody');
    const downloadBox = document.getElementById('downloadBox');
    const downloadFilename = document.getElementById('downloadFilename');

    let pollInterval = null;
    let seenLogsCount = 0;

    // --- Slider Value Sync ---
    sliderTrimSec.addEventListener('input', () => valTrimSec.textContent = `${parseFloat(sliderTrimSec.value).toFixed(1)}s`);
    sliderZoomPct.addEventListener('input', () => valZoomPct.textContent = `${sliderZoomPct.value}%`);
    sliderLogoWidth.addEventListener('input', () => valLogoWidth.textContent = `${sliderLogoWidth.value}px`);
    sliderXOffset.addEventListener('input', () => valXOffset.textContent = `${sliderXOffset.value}px`);
    sliderYOffset.addEventListener('input', () => valYOffset.textContent = `${sliderYOffset.value}px`);

    // --- Credentials Form Toggle ---
    toggleCredsBtn.addEventListener('click', () => {
        credsForm.classList.toggle('hidden');
    });

    credsForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = kaggleUsernameInput.value.trim();
        const key = kaggleKeyInput.value.trim();
        if (!username || !key) {
            alert('Please provide both Kaggle Username and API Key.');
            return;
        }

        try {
            const res = await fetch('/api/credentials', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, key })
            });
            const data = await res.json();
            if (data.success) {
                credsForm.classList.add('hidden');
                fetchState();
            } else {
                alert(`Error: ${data.error || 'Failed to authenticate Kaggle account'}`);
            }
        } catch (err) {
            alert(`Network error: ${err.message}`);
        }
    });

    resetDefaultCredsBtn.addEventListener('click', async () => {
        if (!confirm('Reset Kaggle credentials to default @rathinnew?')) return;
        try {
            const res = await fetch('/api/reset_credentials', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                credsForm.classList.add('hidden');
                fetchState();
            }
        } catch (err) {
            alert(`Failed to reset: ${err.message}`);
        }
    });

    // --- State Fetching ---
    async function fetchState() {
        try {
            const res = await fetch('/api/state');
            const data = await res.json();

            // 1. Credentials
            if (data.credentials && data.credentials.configured) {
                dot.className = 'dot connected';
                connectionText.textContent = `Connected: @${data.credentials.username}`;
                activeUsernameDisplay.textContent = `@${data.credentials.username}`;
                accountTagBadge.textContent = data.credentials.is_default ? 'Default' : 'Custom';
                kaggleUsernameInput.value = data.credentials.username || '';
            } else {
                dot.className = 'dot disconnected';
                connectionText.textContent = 'Disconnected';
                activeUsernameDisplay.textContent = 'None';
            }

            // 2. Videos
            renderVideoList(data.videos || []);

            // 3. Logo
            if (data.logo) {
                activeLogoImg.src = data.logo.url;
                if (data.logo.type === 'custom') {
                    activeLogoTitle.textContent = 'Custom Logo Active';
                    activeLogoMeta.textContent = `${data.logo.filename} (${data.logo.size_kb} KB)`;
                    resetLogoBtn.classList.remove('hidden');
                } else {
                    activeLogoTitle.textContent = 'AimIndia Transparent Logo';
                    activeLogoMeta.textContent = 'Bundled Default (PNG)';
                    resetLogoBtn.classList.add('hidden');
                }
            }

            // 4. Pipeline State
            const state = data.app_state || {};
            updateProgress(state);

            if (state.status === 'syncing' || state.status === 'pushing' || state.status === 'running') {
                startPolling();
            } else if (state.status === 'complete' && state.output_available) {
                showDownloadBox(state.output_file || 'FINAL_VIDEO_CLEAN.mp4');
            }
        } catch (err) {
            console.error('Error fetching state:', err);
        }
    }

    function renderVideoList(videos) {
        if (!videos.length) {
            videoList.innerHTML = '<span class="text-muted" style="font-size:12px; padding:4px;">No videos uploaded yet.</span>';
            return;
        }

        videoList.innerHTML = videos.map(v => `
            <div class="file-item">
                <div class="file-item-info">
                    <span>🎬</span>
                    <span class="file-name" title="${v.original_name}">${v.original_name}</span>
                    <span class="file-size">(${v.size_mb} MB)</span>
                </div>
                <button type="button" class="btn btn-outline-danger btn-sm" onclick="deleteVideo('${v.filename}')">🗑️</button>
            </div>
        `).join('');
    }

    window.deleteVideo = async (filename) => {
        try {
            const res = await fetch(`/api/delete_video/${encodeURIComponent(filename)}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) fetchState();
        } catch (err) {
            alert(`Failed to delete: ${err.message}`);
        }
    };

    // --- Video Dropzone & Upload ---
    videoDropzone.addEventListener('click', () => videoFileInput.click());
    videoDropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        videoDropzone.classList.add('dragover');
    });
    videoDropzone.addEventListener('dragleave', () => videoDropzone.classList.remove('dragover'));
    videoDropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        videoDropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length) uploadVideoFile(e.dataTransfer.files[0]);
    });
    videoFileInput.addEventListener('change', () => {
        if (videoFileInput.files.length) uploadVideoFile(videoFileInput.files[0]);
    });

    async function uploadVideoFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        const origText = videoDropzone.querySelector('p').innerHTML;
        videoDropzone.querySelector('p').innerHTML = `⏳ Uploading <strong>${file.name}</strong>...`;

        try {
            const res = await fetch('/api/upload_video', { method: 'POST', body: formData });
            const data = await res.json();
            if (data.success) {
                fetchState();
            } else {
                alert(`Upload failed: ${data.error}`);
            }
        } catch (err) {
            alert(`Network error during upload: ${err.message}`);
        } finally {
            videoDropzone.querySelector('p').innerHTML = origText;
            videoFileInput.value = '';
        }
    }

    // --- Logo Upload & Reset ---
    uploadLogoBtn.addEventListener('click', () => logoFileInput.click());
    logoFileInput.addEventListener('change', async () => {
        if (!logoFileInput.files.length) return;
        const file = logoFileInput.files[0];
        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch('/api/upload_logo', { method: 'POST', body: formData });
            const data = await res.json();
            if (data.success) fetchState();
            else alert(`Logo upload failed: ${data.error}`);
        } catch (err) {
            alert(`Error: ${err.message}`);
        } finally {
            logoFileInput.value = '';
        }
    });

    resetLogoBtn.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/delete_logo', { method: 'DELETE' });
            const data = await res.json();
            if (data.success) fetchState();
        } catch (err) {
            alert(`Error resetting logo: ${err.message}`);
        }
    });

    // --- Fast Position Preview ---
    previewBtn.addEventListener('click', async () => {
        previewBtn.disabled = true;
        previewBtn.textContent = '⏳ Rendering Preview Frame...';

        try {
            const res = await fetch('/api/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    zoom_pct: parseInt(sliderZoomPct.value),
                    logo_width: parseInt(sliderLogoWidth.value),
                    x_offset: parseInt(sliderXOffset.value),
                    y_offset: parseInt(sliderYOffset.value)
                })
            });
            const data = await res.json();
            if (data.success && data.preview_url) {
                previewImg.src = data.preview_url;
                previewImg.classList.remove('hidden');
                previewPlaceholder.classList.add('hidden');
            } else {
                alert(data.error || 'Failed to generate frame preview.');
            }
        } catch (err) {
            alert(`Preview error: ${err.message}`);
        } finally {
            previewBtn.disabled = false;
            previewBtn.textContent = '👁️ Generate Fast 1-Frame Preview';
        }
    });

    // --- Pipeline Execution ---
    launchBtn.addEventListener('click', async () => {
        launchBtn.disabled = true;
        launchBtn.textContent = 'Submitting to Kaggle...';
        downloadBox.classList.add('hidden');
        progressContainer.classList.remove('hidden');
        cancelBtn.classList.remove('hidden');

        try {
            const res = await fetch('/api/launch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    trim_sec: parseFloat(sliderTrimSec.value),
                    zoom_pct: parseInt(sliderZoomPct.value),
                    logo_width: parseInt(sliderLogoWidth.value),
                    x_offset: parseInt(sliderXOffset.value),
                    y_offset: parseInt(sliderYOffset.value)
                })
            });
            const data = await res.json();
            if (data.success) {
                startPolling();
            } else {
                alert(`Launch failed: ${data.error}`);
                launchBtn.disabled = false;
                launchBtn.textContent = '🚀 Process on Kaggle GPU';
            }
        } catch (err) {
            alert(`Error: ${err.message}`);
            launchBtn.disabled = false;
            launchBtn.textContent = '🚀 Process on Kaggle GPU';
        }
    });

    cancelBtn.addEventListener('click', async () => {
        if (!confirm('Cancel the current Kaggle GPU job?')) return;
        try {
            await fetch('/api/cancel', { method: 'POST' });
            stopPolling();
            fetchState();
        } catch (err) {
            console.error('Cancel failed:', err);
        }
    });

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);
        pollLogs();
        pollInterval = setInterval(pollLogs, 3000);
    }

    function stopPolling() {
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
        }
        launchBtn.disabled = false;
        launchBtn.textContent = '🚀 Process on Kaggle GPU';
        cancelBtn.classList.add('hidden');
    }

    async function pollLogs() {
        try {
            const res = await fetch('/api/logs');
            const data = await res.json();
            updateProgress(data);

            const logs = data.logs || [];
            if (logs.length > seenLogsCount) {
                for (let i = seenLogsCount; i < logs.length; i++) {
                    const line = document.createElement('div');
                    line.className = 'log-line';
                    line.textContent = logs[i];
                    terminalBody.appendChild(line);
                }
                seenLogsCount = logs.length;
                terminalBody.scrollTop = terminalBody.scrollHeight;
            }

            if (data.status === 'complete') {
                stopPolling();
                showDownloadBox('FINAL_VIDEO_CLEAN.mp4');
            } else if (data.status === 'error') {
                stopPolling();
                alert(`Pipeline stopped with error: ${data.message}`);
            }
        } catch (err) {
            console.error('Log polling error:', err);
        }
    }

    function updateProgress(state) {
        if (!state) return;
        const pct = state.progress || 0;
        progressBar.style.width = `${pct}%`;
        progressPctText.textContent = `${pct}%`;
        progressStatusText.textContent = state.message || 'Processing...';

        if (pct > 0) {
            progressContainer.classList.remove('hidden');
        }
    }

    function showDownloadBox(filename) {
        downloadFilename.textContent = `${filename} is ready for download.`;
        downloadBox.classList.remove('hidden');
    }

    // Initial Load
    fetchState();
});

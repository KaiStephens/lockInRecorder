document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const startRecordingBtn = document.getElementById('start-recording');
    const stopRecordingBtn = document.getElementById('stop-recording');
    const applySettingsBtn = document.getElementById('apply-settings');
    const fpsRange = document.getElementById('fps-range');
    const fpsValue = document.getElementById('fps-value');
    const resolutionSelect = document.getElementById('resolution-select');
    const convertToggle = document.getElementById('convert-toggle');
    const outputDirectory = document.getElementById('output-directory');
    const recordingInfo = document.getElementById('recording-info');
    const recordingsList = document.getElementById('recordings-list');
    const recordingIndicator = document.getElementById('recording-indicator');
    const recordingTime = document.getElementById('recording-time');
    const toastElement = document.getElementById('toast');
    const toastTitle = document.getElementById('toast-title');
    const toastMessage = document.getElementById('toast-message');

    // Bootstrap Toast
    const toast = new bootstrap.Toast(toastElement);

    // Global variables
    let isRecording = false;
    let recordingStartTime = null;
    let recordingTimer = null;
    let recentRecordings = [];

    // Update FPS value display
    fpsRange.addEventListener('input', function() {
        fpsValue.textContent = this.value;
    });

    // Apply settings
    applySettingsBtn.addEventListener('click', function() {
        const fps = parseInt(fpsRange.value);
        const [width, height] = resolutionSelect.value.split('x').map(val => parseInt(val));
        const convertToOneMinute = convertToggle.checked;
        const outputDir = outputDirectory.value.trim();

        if (!outputDir) {
            showToast('Error', 'Output directory cannot be empty!', 'error');
            return;
        }

        // Send settings to server
        fetch('/update_settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                fps: fps,
                width: width,
                height: height,
                convert_to_one_minute: convertToOneMinute,
                output_directory: outputDir
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showToast('Success', 'Settings applied successfully!', 'success');
            } else {
                showToast('Error', data.message, 'error');
            }
        })
        .catch(error => {
            showToast('Error', 'Failed to apply settings: ' + error, 'error');
        });
    });

    // Start recording
    startRecordingBtn.addEventListener('click', function() {
        const fps = parseInt(fpsRange.value);
        const [width, height] = resolutionSelect.value.split('x').map(val => parseInt(val));
        const convertToOneMinute = convertToggle.checked;
        const outputDir = outputDirectory.value.trim();

        if (!outputDir) {
            showToast('Error', 'Output directory cannot be empty!', 'error');
            return;
        }

        // Send start recording request
        fetch('/start_recording', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                fps: fps,
                width: width,
                height: height,
                convert_to_one_minute: convertToOneMinute,
                output_directory: outputDir
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                isRecording = true;
                recordingStartTime = Date.now();
                updateUI(true);
                startTimer();
                showToast('Recording Started', 'Recording to ' + data.filename, 'success');
                updateRecordingInfo('Recording in progress...', data.filename);
            } else {
                showToast('Error', data.message, 'error');
            }
        })
        .catch(error => {
            showToast('Error', 'Failed to start recording: ' + error, 'error');
        });
    });

    // Stop recording
    stopRecordingBtn.addEventListener('click', function() {
        fetch('/stop_recording', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                isRecording = false;
                stopTimer();
                updateUI(false);
                
                // Add to recent recordings list
                const recordingItem = {
                    filename: data.filename,
                    duration: getElapsedTimeFormatted(recordingStartTime, Date.now()),
                    timestamp: new Date().toLocaleString(),
                    converted: data.converted
                };
                
                recentRecordings.unshift(recordingItem);
                if (recentRecordings.length > 10) {
                    recentRecordings.pop();
                }
                
                updateRecordingsList();
                updateRecordingInfo('Recording completed!', data.filename);
                
                if (data.converted) {
                    showToast('Recording Complete', 'Video converted to 1 minute duration!', 'success');
                } else {
                    showToast('Recording Complete', 'Recording saved!', 'success');
                }
            } else {
                showToast('Error', data.message, 'error');
            }
        })
        .catch(error => {
            showToast('Error', 'Failed to stop recording: ' + error, 'error');
        });
    });

    // Helper Functions
    function updateUI(isRecording) {
        startRecordingBtn.disabled = isRecording;
        stopRecordingBtn.disabled = !isRecording;
        applySettingsBtn.disabled = isRecording;
        fpsRange.disabled = isRecording;
        resolutionSelect.disabled = isRecording;
        convertToggle.disabled = isRecording;
        outputDirectory.disabled = isRecording;
        
        if (isRecording) {
            recordingIndicator.classList.remove('d-none');
        } else {
            recordingIndicator.classList.add('d-none');
        }
    }

    function startTimer() {
        recordingTimer = setInterval(() => {
            const elapsedTime = getElapsedTimeFormatted(recordingStartTime, Date.now());
            recordingTime.textContent = elapsedTime;
        }, 1000);
    }

    function stopTimer() {
        if (recordingTimer) {
            clearInterval(recordingTimer);
            recordingTimer = null;
        }
    }

    function getElapsedTimeFormatted(startTime, endTime) {
        const elapsed = Math.floor((endTime - startTime) / 1000);
        const minutes = Math.floor(elapsed / 60).toString().padStart(2, '0');
        const seconds = (elapsed % 60).toString().padStart(2, '0');
        return `${minutes}:${seconds}`;
    }

    function updateRecordingInfo(status, filename) {
        recordingInfo.innerHTML = `
            <p><strong>Status:</strong> ${status}</p>
            ${filename ? `<p><strong>File:</strong> ${filename}</p>` : ''}
        `;
    }

    function updateRecordingsList() {
        recordingsList.innerHTML = '';
        if (recentRecordings.length === 0) {
            recordingsList.innerHTML = '<li class="list-group-item">No recordings yet</li>';
            return;
        }
        
        recentRecordings.forEach(recording => {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            li.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <div class="recording-name">${getFilenameFromPath(recording.filename)}</div>
                        <div class="recording-info">
                            <span>Duration: ${recording.duration}</span>
                            ${recording.converted ? '<span class="badge bg-success ms-2">Converted</span>' : ''}
                        </div>
                    </div>
                    <span class="text-muted small">${recording.timestamp}</span>
                </div>
            `;
            recordingsList.appendChild(li);
        });
    }

    function getFilenameFromPath(path) {
        return path.split('/').pop();
    }

    function showToast(title, message, type = 'info') {
        toastTitle.textContent = title;
        toastMessage.textContent = message;
        
        // Remove previous classes
        toastElement.classList.remove('bg-success', 'bg-danger', 'bg-info');
        
        // Add appropriate class based on type
        if (type === 'success') {
            toastElement.classList.add('bg-success', 'text-white');
        } else if (type === 'error') {
            toastElement.classList.add('bg-danger', 'text-white');
        } else {
            toastElement.classList.add('bg-info', 'text-white');
        }
        
        toast.show();
    }

    // Initialize with default UI state
    updateUI(false);
    updateRecordingInfo('No recording in progress');
    updateRecordingsList();
}); 
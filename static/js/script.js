$(document).ready(function() {
    // Elements
    const startRecordingBtn = document.getElementById('start-recording');
    const stopRecordingBtn = document.getElementById('stop-recording');
    const applySettingsBtn = document.getElementById('apply-settings');
    const fpsRange = document.getElementById('fps-range');
    const fpsValue = document.getElementById('fps-value');
    const resolutionSelect = document.getElementById('resolution-select');
    const convertToggle = document.getElementById('convert-toggle');
    const outputDirectory = document.getElementById('output-directory');
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

    // Load saved settings
    loadSettings();
    
    // Load recent recordings
    loadRecordings();

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

        // Save settings locally
        saveSettings();

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

    // Settings persistence functions
    function saveSettings() {
        const settings = {
            fps: parseInt(fpsRange.value),
            resolution: resolutionSelect.value,
            convertToOneMinute: convertToggle.checked,
            outputDirectory: outputDirectory.value
        };
        
        localStorage.setItem('lockInRecorderSettings', JSON.stringify(settings));
        
        // Also save to server
        fetch('/save_settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
        })
        .catch(error => {
            console.error('Failed to save settings to server:', error);
        });
    }
    
    function loadSettings() {
        // Try to load from localStorage first
        const savedSettings = localStorage.getItem('lockInRecorderSettings');
        
        if (savedSettings) {
            const settings = JSON.parse(savedSettings);
            fpsRange.value = settings.fps || 2;
            fpsValue.textContent = settings.fps || 2;
            
            if (settings.resolution) {
                // Find the option with this value
                const options = Array.from(resolutionSelect.options);
                const option = options.find(opt => opt.value === settings.resolution);
                if (option) {
                    option.selected = true;
                }
            }
            
            convertToggle.checked = settings.convertToOneMinute !== undefined ? settings.convertToOneMinute : true;
            outputDirectory.value = settings.outputDirectory || 'recordings';
        }
        
        // Then try to load from server
        fetch('/load_settings')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success' && data.settings) {
                    const settings = data.settings;
                    fpsRange.value = settings.fps || 2;
                    fpsValue.textContent = settings.fps || 2;
                    
                    if (settings.resolution) {
                        // Find the option with this value
                        const options = Array.from(resolutionSelect.options);
                        const option = options.find(opt => opt.value === settings.resolution);
                        if (option) {
                            option.selected = true;
                        }
                    }
                    
                    convertToggle.checked = settings.convertToOneMinute !== undefined ? settings.convertToOneMinute : true;
                    outputDirectory.value = settings.outputDirectory || 'recordings';
                    
                    // Also update localStorage
                    localStorage.setItem('lockInRecorderSettings', JSON.stringify(settings));
                }
            })
            .catch(error => {
                console.error('Failed to load settings from server:', error);
            });
    }

    function loadRecordings() {
        // Fetch recordings from the server
        $.ajax({
            url: '/get_recordings',
            type: 'GET',
            success: function(response) {
                if (response.status === 'success') {
                    displayRecordings(response.recordings);
                }
            },
            error: function(error) {
                console.error('Error loading recordings:', error);
            }
        });
    }

    function displayRecordings(recordings) {
        const recordingsList = $('#recordings-list');
        recordingsList.empty();
        
        if (recordings.length === 0) {
            recordingsList.append('<div class="list-group-item">No recordings found</div>');
            return;
        }
        
        // Add each recording to the list
        recordings.forEach(function(recording) {
            const recordingItem = `
                <div class="list-group-item">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <div class="recording-name">${recording.name}</div>
                            <div class="recording-info">${recording.modified} - ${recording.size}</div>
                        </div>
                    </div>
                </div>
            `;
            recordingsList.append(recordingItem);
        });
    }

    // Initialize with default UI state
    updateUI(false);
    updateRecordingsList();
}); 
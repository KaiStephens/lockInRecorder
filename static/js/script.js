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
    const recordingsList = document.getElementById('recordings-list');
    const recordingIndicator = document.getElementById('recording-indicator');
    const recordingTime = document.getElementById('recording-time');
    const currentTimeDisplay = document.getElementById('current-time');
    const toastElement = document.getElementById('toast');
    const toastTitle = document.getElementById('toast-title');
    const toastMessage = document.getElementById('toast-message');

    // Bootstrap Toast
    const toast = new bootstrap.Toast(toastElement);

    // Global variables - initialize with default values
    let isRecording = false;
    let recordingStartTime = null;
    let recordingTimer = null;
    let recentRecordings = [];
    let clockTimer = null;

    // Start the clock
    startClock();

    // Load recent recordings from localStorage
    loadRecentRecordings();

    // Fetch recordings from the server
    fetchRecordingsFromServer();

    // Check current recording state with the server
    checkRecordingStatus();

    // Function to start the clock
    function startClock() {
        updateClock(); // Update immediately
        clockTimer = setInterval(updateClock, 1000); // Then update every second
    }

    function updateClock() {
        const now = new Date();
        const hours = now.getHours().toString().padStart(2, '0');
        const minutes = now.getMinutes().toString().padStart(2, '0');
        const seconds = now.getSeconds().toString().padStart(2, '0');
        currentTimeDisplay.textContent = `${hours}:${minutes}:${seconds}`;
    }

    // Function to check the current recording status with the server
    function checkRecordingStatus() {
        console.log('Checking recording status with server...');
        // Add a simple ping to make sure the UI state matches server state
        fetch('/stop_recording', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        })
        .then(response => response.json())
        .then(data => {
            console.log('Initial recording status check:', data);
            // If we get "Not recording" error, that's good - we want to start in non-recording state
            isRecording = (data.status === 'success');
            updateUI(isRecording);
        })
        .catch(error => {
            console.error('Error checking recording status:', error);
            // Default to not recording in case of error
            isRecording = false;
            updateUI(false);
        });
    }

    // Load saved settings
    loadSettings();

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
        // Add debugging
        console.log('Stop recording button clicked');

        // Show immediate UI feedback
        isRecording = false;
        stopTimer();
        updateUI(false);
        showToast('Processing', 'Stopping recording...', 'info');
        
        // Set a timeout as a failsafe - if the server doesn't respond in 10 seconds,
        // we'll assume recording has stopped anyway
        const failsafeTimeout = setTimeout(() => {
            console.log('Failsafe timeout triggered');
            if (isRecording) {
                isRecording = false;
                updateUI(false);
                showToast('Warning', 'Recording may have stopped, but server did not respond.', 'error');
            }
        }, 10000);
        
        fetch('/stop_recording', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        })
        .then(response => {
            console.log('Stop recording response received:', response);
            clearTimeout(failsafeTimeout);
            return response.json();
        })
        .then(data => {
            console.log('Stop recording data:', data);
            if (data.status === 'success') {
                // We already updated UI immediately for better responsiveness
                
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
                
                // Save the updated recordings list
                saveRecentRecordings();
                
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
            console.error('Stop recording error:', error);
            clearTimeout(failsafeTimeout);
            showToast('Error', 'Failed to stop recording: ' + error, 'error');
        });
    });

    // Helper Functions
    function updateUI(isRecording) {
        console.log('Updating UI, isRecording:', isRecording);
        
        // Make sure the buttons are properly enabled/disabled
        startRecordingBtn.disabled = isRecording;
        stopRecordingBtn.disabled = !isRecording;
        
        // Update other UI elements
        applySettingsBtn.disabled = isRecording;
        fpsRange.disabled = isRecording;
        resolutionSelect.disabled = isRecording;
        convertToggle.disabled = isRecording;
        outputDirectory.disabled = isRecording;
        
        if (isRecording) {
            recordingIndicator.classList.remove('d-none');
            // Also ensure the stop button is visible and enabled
            stopRecordingBtn.classList.remove('d-none');
            stopRecordingBtn.disabled = false;
        } else {
            recordingIndicator.classList.add('d-none');
        }
        
        // Debug button states
        console.log('Start button disabled:', startRecordingBtn.disabled);
        console.log('Stop button disabled:', stopRecordingBtn.disabled);
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
        const hours = Math.floor(elapsed / 3600).toString().padStart(2, '0');
        const minutes = Math.floor((elapsed % 3600) / 60).toString().padStart(2, '0');
        const seconds = (elapsed % 60).toString().padStart(2, '0');
        return `${hours}:${minutes}:${seconds}`;
    }

    function updateRecordingsList() {
        recordingsList.innerHTML = '';
        if (recentRecordings.length === 0) {
            recordingsList.innerHTML = '<li class="list-group-item">No recordings yet</li>';
            return;
        }
        
        recentRecordings.forEach((recording, index) => {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            
            // Create a more visually appealing recording item
            li.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <div class="recording-name">${getFilenameFromPath(recording.filename)}</div>
                        <div class="recording-info">
                            <span>Duration: ${recording.duration}</span>
                            ${recording.converted ? '<span class="badge bg-success ms-2">Converted</span>' : ''}
                        </div>
                    </div>
                    <div>
                        <button class="btn btn-sm btn-outline-primary play-recording" data-index="${index}">
                            <i class="fas fa-play"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger delete-recording" data-index="${index}">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `;
            recordingsList.appendChild(li);
        });
        
        // Add event listeners for play and delete buttons
        document.querySelectorAll('.play-recording').forEach(button => {
            button.addEventListener('click', function() {
                const index = parseInt(this.getAttribute('data-index'));
                const recording = recentRecordings[index];
                if (recording) {
                    // Open recording in a new tab/window
                    window.open(recording.filename, '_blank');
                }
            });
        });
        
        document.querySelectorAll('.delete-recording').forEach(button => {
            button.addEventListener('click', function() {
                const index = parseInt(this.getAttribute('data-index'));
                if (confirm('Are you sure you want to delete this recording?')) {
                    recentRecordings.splice(index, 1);
                    saveRecentRecordings();
                    updateRecordingsList();
                }
            });
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

    // Save and load recent recordings
    function saveRecentRecordings() {
        localStorage.setItem('lockInRecorderRecordings', JSON.stringify(recentRecordings));
    }
    
    function loadRecentRecordings() {
        const savedRecordings = localStorage.getItem('lockInRecorderRecordings');
        if (savedRecordings) {
            recentRecordings = JSON.parse(savedRecordings);
            updateRecordingsList();
        }
    }

    function fetchRecordingsFromServer() {
        fetch('/get_recordings')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    // Only overwrite local recordings if we got valid data from server
                    if (data.recordings && data.recordings.length > 0) {
                        // Convert server recordings to our format
                        const serverRecordings = data.recordings.map(recording => {
                            // Calculate duration in HH:MM:SS format
                            const duration = formatDuration(recording.duration);
                            
                            return {
                                filename: recording.path,
                                duration: duration,
                                timestamp: new Date(recording.created * 1000).toLocaleString(),
                                converted: recording.converted
                            };
                        });
                        
                        // Merge with local recordings but avoid duplicates
                        const mergedRecordings = [...serverRecordings];
                        
                        // Save and update the UI
                        recentRecordings = mergedRecordings;
                        saveRecentRecordings();
                        updateRecordingsList();
                    }
                } else {
                    console.error('Failed to fetch recordings:', data.message);
                }
            })
            .catch(error => {
                console.error('Error fetching recordings:', error);
            });
    }

    function formatDuration(seconds) {
        seconds = Math.round(seconds);
        const hours = Math.floor(seconds / 3600).toString().padStart(2, '0');
        const minutes = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
        const secs = (seconds % 60).toString().padStart(2, '0');
        return `${hours}:${minutes}:${secs}`;
    }

    // Add a refresh button to the recordings list header
    document.addEventListener('DOMContentLoaded', function() {
        // Find the Recent Recordings header
        const recordingsHeaders = document.querySelectorAll('.card-header');
        for (const header of recordingsHeaders) {
            if (header.textContent.includes('Recent Recordings')) {
                const refreshBtn = document.createElement('button');
                refreshBtn.className = 'btn btn-sm btn-outline-secondary float-end';
                refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i>';
                refreshBtn.title = 'Refresh recordings';
                refreshBtn.addEventListener('click', fetchRecordingsFromServer);
                
                header.appendChild(refreshBtn);
                break;
            }
        }
    });

    // Initialize with default UI state
    updateUI(false);
    updateRecordingsList();
}); 
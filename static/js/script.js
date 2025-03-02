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
        if (!recordingsList) return;
        
        // Clear the list
        recordingsList.innerHTML = '';
        
        if (recentRecordings.length === 0) {
            const emptyMessage = document.createElement('li');
            emptyMessage.className = 'list-group-item text-center';
            emptyMessage.textContent = 'No recordings yet';
            recordingsList.appendChild(emptyMessage);
            return;
        }
        
        // Add each recording to the list
        recentRecordings.forEach(recording => {
            const item = document.createElement('li');
            item.className = 'list-group-item';

            // Format date
            const date = new Date(recording.created * 1000);
            const dateString = recording.created_formatted || date.toLocaleString();
            
            // Create recording item with details
            item.innerHTML = `
                <div class="d-flex justify-content-between align-items-start">
                    <div class="recording-info">
                        <div class="fw-bold">${recording.filename}</div>
                        <div class="small text-muted">
                            <span title="Duration">${recording.duration_formatted || formatDuration(recording.duration)}</span> • 
                            <span title="Size">${recording.size_formatted || formatFileSize(recording.size)}</span> • 
                            <span title="Created">${dateString}</span>
                        </div>
                    </div>
                    <div class="btn-group">
                        <button class="btn btn-sm btn-primary play-recording" data-path="${recording.path}" data-filename="${recording.filename}">
                            <i class="fas fa-play"></i>
                        </button>
                        <button class="btn btn-sm btn-danger delete-recording" data-filename="${recording.filename}">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `;
            
            recordingsList.appendChild(item);
        });
        
        // Add event listeners for play buttons
        document.querySelectorAll('.play-recording').forEach(button => {
            button.addEventListener('click', function() {
                const filename = this.getAttribute('data-filename');
                playRecording(filename);
            });
        });
        
        // Add event listeners for delete buttons
        document.querySelectorAll('.delete-recording').forEach(button => {
            button.addEventListener('click', function() {
                const filename = this.getAttribute('data-filename');
                if (confirm(`Are you sure you want to delete ${filename}?`)) {
                    deleteRecording(filename);
                }
            });
        });
    }

    function playRecording(filename) {
        console.log(`Playing recording: ${filename}`);
        
        // Create a video player modal if it doesn't exist
        let playerModal = document.getElementById('videoPlayerModal');
        
        if (!playerModal) {
            // Create modal HTML
            const modalHTML = `
                <div class="modal fade" id="videoPlayerModal" tabindex="-1" aria-labelledby="videoPlayerModalLabel" aria-hidden="true">
                    <div class="modal-dialog modal-lg">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title" id="videoPlayerModalLabel">Video Player</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                            </div>
                            <div class="modal-body">
                                <div class="ratio ratio-16x9">
                                    <video id="videoPlayer" controls>
                                        Your browser does not support the video tag.
                                    </video>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            // Add modal to body
            const modalContainer = document.createElement('div');
            modalContainer.innerHTML = modalHTML;
            document.body.appendChild(modalContainer);
            
            playerModal = document.getElementById('videoPlayerModal');
        }
        
        // Set the video source
        const videoPlayer = document.getElementById('videoPlayer');
        videoPlayer.src = `/recordings/${filename}`;
        
        // Show the modal
        const modal = new bootstrap.Modal(playerModal);
        modal.show();
        
        // Play the video when modal is shown
        playerModal.addEventListener('shown.bs.modal', function () {
            videoPlayer.play().catch(e => {
                console.error('Error playing video:', e);
                showToast('Error', 'Failed to play video: ' + e, 'error');
            });
        });
        
        // Stop the video when modal is hidden
        playerModal.addEventListener('hidden.bs.modal', function () {
            videoPlayer.pause();
            videoPlayer.currentTime = 0;
        });
    }

    function deleteRecording(filename) {
        console.log(`Deleting recording: ${filename}`);
        
        fetch('/delete_recording', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                filename: filename
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showToast('Success', `${filename} deleted successfully`, 'success');
                
                // Update the recordings list
                fetchRecordingsFromServer();
            } else {
                showToast('Error', data.message, 'error');
            }
        })
        .catch(error => {
            console.error('Error deleting recording:', error);
            showToast('Error', 'Failed to delete recording: ' + error, 'error');
        });
    }

    function formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        else if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
        else return (bytes / 1073741824).toFixed(1) + ' GB';
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
        console.log('Fetching recordings from server...');
        fetch('/get_recordings')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    console.log('Received recordings:', data.recordings);
                    recentRecordings = data.recordings;
                    updateRecordingsList();
                } else {
                    console.error('Error fetching recordings:', data.message);
                    showToast('Error', 'Failed to fetch recordings: ' + data.message, 'error');
                }
            })
            .catch(error => {
                console.error('Error fetching recordings:', error);
                showToast('Error', 'Failed to fetch recordings: ' + error, 'error');
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
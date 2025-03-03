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
    const videoFeed = document.getElementById('video-feed');
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
    let statusCheckTimer = null;
    let videoFeedRetryCount = 0;
    const maxVideoFeedRetries = 3;

    // Initialize settings
    loadSettings();

    // Update FPS value display when slider moves
    fpsRange.addEventListener('input', function() {
        fpsValue.textContent = this.value;
    });

    // Apply settings button click
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

    // Handle video feed errors
    if (videoFeed) {
        videoFeed.onerror = function() {
            console.error('Video feed error detected');
            if (videoFeedRetryCount < maxVideoFeedRetries) {
                videoFeedRetryCount++;
                console.log(`Retrying video feed (${videoFeedRetryCount}/${maxVideoFeedRetries})...`);
                
                // Add a timestamp parameter to force reload
                const timestamp = new Date().getTime();
                videoFeed.src = `/video_feed?t=${timestamp}`;
            } else {
                console.error('Max video feed retries reached');
                showToast('Error', 'Video feed failed to load. Please refresh the page.', 'error');
            }
        };
        
        videoFeed.onload = function() {
            console.log('Video feed loaded successfully');
            videoFeedRetryCount = 0;
        };
    }

    // Load recent recordings from localStorage
    loadRecentRecordings();

    // Fetch recordings from the server
    fetchRecordingsFromServer();

    // Check current recording state with the server
    checkRecordingStatus();
    
    // Set up periodic status checks - every 3 seconds
    statusCheckTimer = setInterval(checkRecordingStatus, 3000);
    
    // Function to check the current recording status with the server
    function checkRecordingStatus() {
        fetch('/check_recording_status')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Status check failed: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.status === 'success') {
                    const wasRecording = isRecording;
                    isRecording = data.recording;
                    
                    // Only update UI if recording state changed
                    if (wasRecording !== isRecording) {
                        console.log('Recording status changed:', isRecording ? 'Recording' : 'Not recording');
                        
                        if (isRecording) {
                            // Server is recording, update UI
                            recordingStartTime = new Date() - (data.elapsed * 1000);
                            startTimer();
                        } else {
                            // Server is not recording
                            stopTimer();
                            recordingStartTime = null;
                            
                            // Refresh recordings list when recording stops
                            fetchRecordingsFromServer();
                        }
                        
                        updateUI(isRecording);
                    } else {
                        // Still update timer if recording
                        if (isRecording && recordingStartTime) {
                            updateRecordingTimer();
                        }
                    }
                }
            })
            .catch(error => {
                console.error('Error checking recording status:', error);
            });
    }

    // Start recording
    startRecordingBtn.addEventListener('click', function() {
        console.log('Start recording button clicked');
        
        const fps = parseInt(fpsRange.value);
        const [width, height] = resolutionSelect.value.split('x').map(val => parseInt(val));
        const convertToOneMinute = convertToggle.checked;
        const outputDir = outputDirectory.value.trim();

        if (!outputDir) {
            showToast('Error', 'Output directory cannot be empty!', 'error');
            return;
        }

        // Disable the button to prevent double clicks
        startRecordingBtn.disabled = true;
        
        // Show feedback to user
        showToast('Processing', 'Starting recording...', 'info');

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
        .then(response => {
            if (!response.ok) {
                throw new Error(`Request failed: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'success') {
                isRecording = true;
                recordingStartTime = new Date();
                updateUI(true);
                startTimer();
                showToast('Success', 'Recording started!', 'success');
            } else {
                // Re-enable button if there was an error
                startRecordingBtn.disabled = false;
                showToast('Error', data.message, 'error');
            }
        })
        .catch(error => {
            console.error('Failed to start recording:', error);
            // Re-enable button if there was an error
            startRecordingBtn.disabled = false;
            showToast('Error', 'Failed to start recording: ' + error, 'error');
        });
    });

    // Stop recording
    stopRecordingBtn.addEventListener('click', function() {
        // Disable the button to prevent multiple clicks
        stopRecordingBtn.disabled = true;
        
        // Show feedback to user
        showToast('Processing', 'Stopping recording and processing video...', 'info');
        
        fetch('/stop_recording', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Request failed: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'success') {
                isRecording = false;
                updateUI(false);
                stopTimer();
                
                // Refresh the recordings list
                setTimeout(fetchRecordingsFromServer, 1000);
                showToast('Success', 'Recording completed successfully!', 'success');
            } else {
                // Re-enable the button if there was an error
                stopRecordingBtn.disabled = false;
                showToast('Error', data.message, 'error');
            }
        })
        .catch(error => {
            console.error('Failed to stop recording:', error);
            // Re-enable the button if there was an error
            stopRecordingBtn.disabled = false;
            showToast('Error', 'Failed to stop recording: ' + error, 'error');
        });
    });

    function updateUI(isRecording) {
        if (isRecording) {
            startRecordingBtn.disabled = true;
            stopRecordingBtn.disabled = false;
            applySettingsBtn.disabled = true;
            fpsRange.disabled = true;
            resolutionSelect.disabled = true;
            convertToggle.disabled = true;
            outputDirectory.disabled = true;
            
            recordingIndicator.classList.remove('d-none');
        } else {
            startRecordingBtn.disabled = false;
            stopRecordingBtn.disabled = true;
            applySettingsBtn.disabled = false;
            fpsRange.disabled = false;
            resolutionSelect.disabled = false;
            convertToggle.disabled = false;
            outputDirectory.disabled = false;
            
            recordingIndicator.classList.add('d-none');
        }
    }

    function startTimer() {
        if (recordingTimer) {
            clearInterval(recordingTimer);
        }
        recordingTimer = setInterval(updateRecordingTimer, 1000);
        updateRecordingTimer(); // Update immediately
    }

    function stopTimer() {
        if (recordingTimer) {
            clearInterval(recordingTimer);
            recordingTimer = null;
        }
    }

    function updateRecordingTimer() {
        if (!recordingTime || !recordingStartTime) return;
        
        const elapsed = Math.floor((new Date() - recordingStartTime) / 1000);
        const minutes = Math.floor(elapsed / 60).toString().padStart(2, '0');
        const seconds = (elapsed % 60).toString().padStart(2, '0');
        recordingTime.textContent = `${minutes}:${seconds}`;
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
        
        // Set the video source with a timestamp to prevent caching
        const timestamp = new Date().getTime();
        const videoPlayer = document.getElementById('videoPlayer');
        videoPlayer.src = `/recordings/${filename}?t=${timestamp}`;
        
        // Show the modal
        const modal = new bootstrap.Modal(playerModal);
        modal.show();
        
        // Set up error handling
        videoPlayer.onerror = function() {
            console.error('Error playing video:', videoPlayer.error);
            showToast('Error', `Failed to play video: ${videoPlayer.error ? videoPlayer.error.message : 'Unknown error'}`, 'error');
        };
        
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
            videoPlayer.src = ''; // Clear the source to fully unload the video
        });
    }

    function fetchRecordingsFromServer() {
        console.log('Fetching recordings from server...');
        fetch('/get_recordings')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Request failed: ${response.status}`);
                }
                return response.json();
            })
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
            try {
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
            } catch (e) {
                console.error('Error parsing saved settings:', e);
            }
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
            try {
                recentRecordings = JSON.parse(savedRecordings);
                updateRecordingsList();
            } catch (e) {
                console.error('Error parsing saved recordings:', e);
            }
        }
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

    function formatDuration(seconds) {
        seconds = Math.round(seconds);
        const hours = Math.floor(seconds / 3600).toString().padStart(2, '0');
        const minutes = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
        const secs = (seconds % 60).toString().padStart(2, '0');
        return `${hours}:${minutes}:${secs}`;
    }

    function getFilenameFromPath(path) {
        return path.split(/[\/\\]/).pop();
    }

    // Show a toast notification
    function showToast(title, message, type = 'info') {
        toastTitle.textContent = title;
        toastMessage.textContent = message;
        
        // Remove existing classes
        toastElement.classList.remove('bg-success', 'bg-danger', 'bg-info', 'bg-warning');
        
        // Add appropriate class
        switch(type) {
            case 'success':
                toastElement.classList.add('bg-success', 'text-white');
                break;
            case 'error':
                toastElement.classList.add('bg-danger', 'text-white');
                break;
            case 'warning':
                toastElement.classList.add('bg-warning');
                break;
            case 'info':
            default:
                toastElement.classList.add('bg-info', 'text-white');
                break;
        }
        
        toast.show();
    }

    // Clean up intervals when page is unloaded
    window.addEventListener('beforeunload', function() {
        if (statusCheckTimer) {
            clearInterval(statusCheckTimer);
        }
        if (recordingTimer) {
            clearInterval(recordingTimer);
        }
    });

    // Initialize with default UI state
    updateUI(false);
}); 
import os
import cv2
import time
import datetime
import numpy as np
import json
from flask import Flask, render_template, Response, request, jsonify
import threading
import subprocess
import argparse
import signal
import sys

app = Flask(__name__)

# Global variables
camera = None
output_frame = None
lock = threading.Lock()
recording = False
output_path = "recordings"
recording_filename = ""
start_time = 0
frame_count = 0
recording_fps = 2
recording_resolution = (1920, 1080)  # Changed default to 1920x1080
headless_mode = False  # New variable for headless mode
convert_to_one_minute = True
standalone_mode = False
video_writer = None
settings_file = "settings.json"
exit_event = threading.Event()

def cleanup_resources():
    """Clean up all resources before exiting"""
    global camera, video_writer
    
    # Stop recording if active
    if recording:
        try:
            stop_recording_func()
        except Exception as e:
            print(f"Error stopping recording during cleanup: {e}")
    
    # Release video writer if it exists
    if video_writer is not None:
        try:
            video_writer.release()
        except Exception as e:
            print(f"Error releasing video writer: {e}")
    
    # Release camera if it exists
    if camera is not None:
        try:
            camera.release()
        except Exception as e:
            print(f"Error releasing camera: {e}")
    
    # Close all OpenCV windows if not in headless mode
    if not headless_mode:
        try:
            cv2.destroyAllWindows()
        except Exception as e:
            print(f"Error closing windows: {e}")
    
    print("All resources cleaned up")

def signal_handler(sig, frame):
    """Handle Ctrl+C to gracefully exit the program"""
    print("\nReceived signal to shutdown...")
    exit_event.set()
    
    # Give threads a moment to notice the exit event
    time.sleep(0.5)
    
    # Clean up resources
    cleanup_resources()
    
    print("LockIn Recorder shutdown complete")
    sys.exit(0)

# Register the signal handler
signal.signal(signal.SIGINT, signal_handler)

def init_camera():
    """Initialize the camera with the current resolution settings"""
    global camera, recording_resolution
    
    try:
        # Release any existing camera first
        if camera is not None:
            camera.release()
            time.sleep(1)  # Give the camera time to properly release
        
        # Try to open the camera
        camera = cv2.VideoCapture(0)
        
        if not camera.isOpened():
            print("Warning: Could not open camera with index 0")
            # Try an alternative camera index
            camera.release()
            camera = cv2.VideoCapture(1)
            
            if not camera.isOpened():
                print("Error: Could not initialize any camera!")
                return None
        
        # Set camera properties
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, recording_resolution[0])
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, recording_resolution[1])
        
        # Verify if camera is working by trying to read a frame
        success, _ = camera.read()
        if not success:
            print("Error: Camera opened but could not read frame")
            camera.release()
            return None
            
        print(f"Camera initialized successfully with resolution {recording_resolution[0]}x{recording_resolution[1]}")
        return camera
        
    except Exception as e:
        print(f"Error initializing camera: {e}")
        if camera is not None:
            try:
                camera.release()
            except:
                pass
        return None

def generate_frames():
    global output_frame, camera, recording, video_writer, frame_count
    
    if camera is None or not camera.isOpened():
        try:
            camera = init_camera()
            if not camera.isOpened():
                print("Error: Could not initialize camera!")
                # Return a blank frame with error message
                blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(blank_frame, "Camera Error!", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                ret, buffer = cv2.imencode('.jpg', blank_frame)
                error_frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + error_frame + b'\r\n')
                return
        except Exception as e:
            print(f"Camera error: {e}")
            blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(blank_frame, "Camera Error!", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            ret, buffer = cv2.imencode('.jpg', blank_frame)
            error_frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + error_frame + b'\r\n')
            return
    
    while True:
        success, frame = camera.read()
        if not success:
            print("Failed to get frame from camera")
            # Return error frame
            blank_frame = np.zeros(recording_resolution + (3,), dtype=np.uint8)
            cv2.putText(blank_frame, "No Camera Signal", (recording_resolution[0]//4, recording_resolution[1]//2), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            ret, buffer = cv2.imencode('.jpg', blank_frame)
            frame = buffer.tobytes()
            
            with lock:
                output_frame = frame
            
            yield (b'--frame\r\n'
                  b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            
            # Try to reinitialize camera
            try:
                if camera is not None:
                    camera.release()
                time.sleep(1)  # Wait before retrying
                camera = init_camera()
            except Exception as e:
                print(f"Failed to reinitialize camera: {e}")
                
            continue
        else:
            # Only save frames at the specified FPS when recording
            current_time = time.time()
            if recording:
                elapsed_time = current_time - start_time
                # Calculate if we should capture this frame based on FPS
                if frame_count == 0 or elapsed_time >= (frame_count / recording_fps):
                    # Save frame without adding timestamp
                    with lock:
                        if video_writer is not None:
                            video_writer.write(frame)
                            frame_count += 1
            
            # For display, resize to the recording resolution
            frame = cv2.resize(frame, recording_resolution)
            
            # No longer adding timestamp to frames
            
            # Add recording indicator
            if recording:
                cv2.putText(frame, "REC", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 
                            1, (0, 0, 255), 2)
                # Add elapsed time
                elapsed = time.time() - start_time
                cv2.putText(frame, f"Time: {int(elapsed)}s", (20, 90), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # Convert to jpg for streaming
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            
            with lock:
                output_frame = frame
            
            yield (b'--frame\r\n'
                  b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            
            # Control the streaming frame rate (independent of recording fps)
            time.sleep(0.03)  # ~30fps for the stream

def add_timestamp_to_frame(frame):
    """Add current timestamp to the bottom right of the frame"""
    # Removed so we don't add the timestamp to the recorded frames
    return frame

def process_video(input_file, output_file, target_duration=60):
    """Convert the recorded video to be exactly one minute"""
    global frame_count, recording_fps
    
    # Get the recorded video info
    cap = cv2.VideoCapture(input_file)
    original_fps = recording_fps
    original_frame_count = frame_count
    
    # Calculate actual duration in seconds
    actual_duration = original_frame_count / original_fps
    
    # Calculate the speed multiplier needed
    speed_multiplier = actual_duration / target_duration
    
    # Calculate the new fps for the output
    output_fps = original_fps * speed_multiplier
    
    # Use ffmpeg for converting with improved quality
    cmd = [
        "ffmpeg", "-i", input_file,
        "-filter:v", f"setpts={1/speed_multiplier}*PTS",
        "-r", str(output_fps),
        "-c:v", "libx264",
        "-preset", "slow",  # Better quality, slower encoding
        "-crf", "18",       # Lower value = higher quality (18 is high quality)
        "-pix_fmt", "yuv420p",  # Ensure compatibility
        output_file
    ]
    
    # Run the command
    subprocess.run(cmd)
    
    return output_file

def load_settings():
    """Load settings from file"""
    global recording_fps, recording_resolution, convert_to_one_minute, output_path
    
    try:
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                settings = json.load(f)
                
                recording_fps = settings.get('fps', recording_fps)
                
                resolution = settings.get('resolution', None)
                if resolution:
                    width, height = resolution.split('x')
                    recording_resolution = (int(width), int(height))
                
                convert_to_one_minute = settings.get('convertToOneMinute', convert_to_one_minute)
                output_path = settings.get('outputDirectory', output_path)
                
                return settings
    except Exception as e:
        print(f"Error loading settings: {e}")
    
    return {
        'fps': recording_fps,
        'resolution': f"{recording_resolution[0]}x{recording_resolution[1]}",
        'convertToOneMinute': convert_to_one_minute,
        'outputDirectory': output_path
    }

def save_settings(settings):
    """Save settings to file"""
    try:
        with open(settings_file, 'w') as f:
            json.dump(settings, f)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

def start_recording_func(output_dir=None, fps=None, width=None, height=None, convert=None):
    """Functional version of start_recording for standalone mode"""
    global recording, output_path, recording_filename, start_time, frame_count
    global video_writer, recording_fps, recording_resolution, convert_to_one_minute
    
    if recording:
        print("Already recording")
        return False
    
    # Use provided parameters or defaults
    output_dir = output_dir if output_dir is not None else output_path
    recording_fps = fps if fps is not None else recording_fps
    width = width if width is not None else recording_resolution[0]
    height = height if height is not None else recording_resolution[1]
    recording_resolution = (width, height)
    convert_to_one_minute = convert if convert is not None else convert_to_one_minute
    
    try:
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        recording_filename = os.path.join(output_dir, f"lockin-{timestamp}.mp4")
        
        # Initialize the video writer with H.264 codec
        fourcc = cv2.VideoWriter_fourcc(*'avc1')  # Use avc1 (H.264) codec which is more compatible
        video_writer = cv2.VideoWriter(recording_filename, fourcc, recording_fps, recording_resolution)
        
        if not video_writer.isOpened():
            # Fallback to another codec if avc1 fails
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            video_writer = cv2.VideoWriter(recording_filename, fourcc, recording_fps, recording_resolution)
            
            if not video_writer.isOpened():
                print("Failed to initialize video writer with both avc1 and mp4v codecs")
                return False
        
        # Reset frame count and start time
        frame_count = 0
        start_time = time.time()
        
        # Start recording
        recording = True
        
        print(f"Recording started: {recording_filename}")
        return True
    except Exception as e:
        print(f"Failed to start recording: {str(e)}")
        return False

def stop_recording_func():
    """Functional version of stop_recording for standalone mode"""
    global recording, video_writer, recording_filename, convert_to_one_minute
    
    if not recording:
        print("Not recording")
        return None
    
    # Store filename before setting recording to false
    current_filename = recording_filename
    
    # Update recording state
    recording = False
    
    # Close the video writer
    if video_writer is not None:
        video_writer.release()
        video_writer = None
    
    # Default output file is the original recording
    output_file = current_filename
    
    # Convert video to be exactly one minute if requested and file exists
    if convert_to_one_minute and os.path.exists(current_filename):
        try:
            base, ext = os.path.splitext(current_filename)
            output_file = f"{base}_1min{ext}"
            process_video(current_filename, output_file)
        except Exception as e:
            print(f"Error converting video: {e}")
            # If conversion fails, use the original file
            output_file = current_filename
    
    print(f"Recording stopped: {output_file}")
    return output_file

@app.route('/start_recording', methods=['POST'])
def start_recording():
    data = request.get_json()
    output_dir = data.get('output_directory', output_path)
    fps = int(data.get('fps', recording_fps))
    width = int(data.get('width', recording_resolution[0]))
    height = int(data.get('height', recording_resolution[1]))
    convert = data.get('convert_to_one_minute', convert_to_one_minute)
    
    success = start_recording_func(output_dir, fps, width, height, convert)
    
    if success:
        return jsonify({"status": "success", "message": "Recording started", "filename": recording_filename})
    else:
        return jsonify({"status": "error", "message": "Failed to start recording"})

@app.route('/stop_recording', methods=['POST'])
def stop_recording():
    output_file = stop_recording_func()
    
    if output_file:
        return jsonify({
            "status": "success", 
            "message": "Recording stopped", 
            "filename": output_file,
            "converted": convert_to_one_minute and os.path.exists(output_file) and output_file != recording_filename
        })
    else:
        return jsonify({"status": "error", "message": "Not recording"})

@app.route('/update_settings', methods=['POST'])
def update_settings():
    global recording_fps, recording_resolution, convert_to_one_minute, camera, output_path
    
    if recording:
        return jsonify({"status": "error", "message": "Cannot change settings while recording"})
    
    data = request.get_json()
    
    # Update settings
    recording_fps = int(data.get('fps', recording_fps))
    width = int(data.get('width', recording_resolution[0]))
    height = int(data.get('height', recording_resolution[1]))
    recording_resolution = (width, height)
    convert_to_one_minute = data.get('convert_to_one_minute', convert_to_one_minute)
    output_path = data.get('output_directory', output_path)
    
    # Update camera settings
    if camera is not None:
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, recording_resolution[0])
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, recording_resolution[1])
    
    return jsonify({
        "status": "success", 
        "message": "Settings updated",
        "settings": {
            "fps": recording_fps,
            "resolution": f"{recording_resolution[0]}x{recording_resolution[1]}",
            "convert_to_one_minute": convert_to_one_minute,
            "output_directory": output_path
        }
    })

@app.route('/save_settings', methods=['POST'])
def save_settings_route():
    """API endpoint to save settings"""
    if recording:
        return jsonify({"status": "error", "message": "Cannot save settings while recording"})
    
    settings = request.get_json()
    success = save_settings(settings)
    
    if success:
        return jsonify({"status": "success", "message": "Settings saved"})
    else:
        return jsonify({"status": "error", "message": "Failed to save settings"})

@app.route('/load_settings', methods=['GET'])
def load_settings_route():
    """API endpoint to load settings"""
    settings = load_settings()
    return jsonify({"status": "success", "settings": settings})

@app.route('/get_recordings', methods=['GET'])
def get_recordings():
    """API endpoint to get a list of recordings"""
    try:
        recordings_dir = request.args.get('directory', output_path)
        
        if not os.path.exists(recordings_dir):
            return jsonify({"status": "error", "message": f"Directory {recordings_dir} does not exist"})
        
        recordings = []
        
        # Get all mp4 files in the directory
        for file in os.listdir(recordings_dir):
            if file.endswith('.mp4'):
                file_path = os.path.join(recordings_dir, file)
                
                # Get file stats
                stats = os.stat(file_path)
                
                # Get video duration using OpenCV
                try:
                    cap = cv2.VideoCapture(file_path)
                    if cap.isOpened():
                        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        fps = cap.get(cv2.CAP_PROP_FPS)
                        duration = frame_count / fps if fps > 0 else 0
                        cap.release()
                    else:
                        duration = 0
                except Exception as e:
                    print(f"Error getting video duration: {e}")
                    duration = 0
                
                recordings.append({
                    "filename": file,
                    "path": file_path,
                    "size": stats.st_size,
                    "created": stats.st_ctime,
                    "duration": duration,
                    "converted": "_1min" in file
                })
        
        # Sort by creation time, newest first
        recordings.sort(key=lambda x: x["created"], reverse=True)
        
        return jsonify({
            "status": "success", 
            "recordings": recordings
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to get recordings: {str(e)}"})

def run_standalone_mode(args):
    """Run the application in standalone mode without web UI"""
    global recording_fps, recording_resolution, convert_to_one_minute, output_path, standalone_mode, headless_mode
    
    standalone_mode = True
    headless_mode = args.headless  # Set headless mode from command line arg
    
    # Load settings
    load_settings()
    
    # Override settings with command-line arguments if provided
    if args.fps:
        recording_fps = args.fps
    if args.resolution:
        width, height = map(int, args.resolution.split('x'))
        recording_resolution = (width, height)
    if args.convert is not None:
        convert_to_one_minute = args.convert
    if args.output:
        output_path = args.output
    
    print(f"LockIn Recorder - Standalone Mode")
    print(f"FPS: {recording_fps}")
    print(f"Resolution: {recording_resolution[0]}x{recording_resolution[1]}")
    print(f"Convert to 1 minute: {convert_to_one_minute}")
    print(f"Output directory: {output_path}")
    print(f"Headless mode: {headless_mode}")
    
    # Initialize camera
    if init_camera() is None or not camera.isOpened():
        print("Error: Could not initialize camera!")
        return
    
    # Start the camera thread
    camera_thread = threading.Thread(target=standalone_camera_loop)
    camera_thread.daemon = True
    camera_thread.start()
    
    # Print controls
    print("\nControls:")
    if not headless_mode:
        print("- Press Space in camera window to start/stop recording")
        print("- Press ESC in camera window to quit")
    print("- Type 'r' and press Enter to start recording")
    print("- Press Enter to stop recording when prompted")
    print("- Type 'q' and press Enter to quit")
    
    # Main command loop
    while not exit_event.is_set():
        try:
            if recording:
                command = input("\nRecording... Press Enter to stop, or 'q' to quit: ")
                if command.lower() == 'q':
                    if recording:
                        stop_recording_func()
                    break
                else:
                    output_file = stop_recording_func()
                    if output_file:
                        print(f"Recording saved to: {output_file}")
            else:
                command = input("\nEnter 'r' to start recording, 's' for settings, or 'q' to quit: ")
                if command.lower() == 'q':
                    break
                elif command.lower() == 'r':
                    success = start_recording_func()
                    if success:
                        print(f"Recording started!")
                elif command.lower() == 's':
                    show_and_update_settings()
        except Exception as e:
            print(f"Error: {e}")
    
    # Clean up
    exit_event.set()
    time.sleep(0.5)  # Give threads time to exit
    cleanup_resources()
    
    print("LockIn Recorder exited.")

def show_and_update_settings():
    """Show and update settings in the terminal"""
    global recording_fps, recording_resolution, convert_to_one_minute, output_path
    
    print("\nCurrent Settings:")
    print(f"1. FPS: {recording_fps}")
    print(f"2. Resolution: {recording_resolution[0]}x{recording_resolution[1]}")
    print(f"3. Convert to 1 minute: {convert_to_one_minute}")
    print(f"4. Output directory: {output_path}")
    print("0. Back to main menu")
    
    try:
        choice = input("\nEnter number to change setting (0-4): ")
        if choice == '1':
            new_fps = input(f"Enter new FPS (current: {recording_fps}): ")
            recording_fps = int(new_fps)
            print(f"FPS updated to {recording_fps}")
        elif choice == '2':
            print("Available resolutions:")
            print("1. 640x480")
            print("2. 1280x720")
            print("3. 1920x1080")
            res_choice = input("Choose resolution (1-3): ")
            if res_choice == '1':
                recording_resolution = (640, 480)
            elif res_choice == '2':
                recording_resolution = (1280, 720)
            elif res_choice == '3':
                recording_resolution = (1920, 1080)
            print(f"Resolution updated to {recording_resolution[0]}x{recording_resolution[1]}")
        elif choice == '3':
            new_value = input(f"Convert to 1 minute? (y/n, current: {'y' if convert_to_one_minute else 'n'}): ")
            convert_to_one_minute = new_value.lower() == 'y'
            print(f"Convert to 1 minute set to {convert_to_one_minute}")
        elif choice == '4':
            new_dir = input(f"Enter new output directory (current: {output_path}): ")
            if new_dir:
                output_path = new_dir
                os.makedirs(output_path, exist_ok=True)
                print(f"Output directory updated to {output_path}")
        
        # Save settings
        settings = {
            'fps': recording_fps,
            'resolution': f"{recording_resolution[0]}x{recording_resolution[1]}",
            'convertToOneMinute': convert_to_one_minute,
            'outputDirectory': output_path
        }
        save_settings(settings)
        print("Settings saved")
        
    except Exception as e:
        print(f"Error updating settings: {e}")

def standalone_camera_loop():
    """Camera processing loop for standalone mode"""
    global camera, recording, video_writer, frame_count, headless_mode
    
    # Keep track of consecutive errors
    error_count = 0
    max_errors = 5
    
    # Create a window if not in headless mode
    window_created = False
    if not headless_mode:
        try:
            cv2.namedWindow('LockIn Recorder', cv2.WINDOW_NORMAL)
            window_created = True
        except Exception as e:
            print(f"Warning: Could not create window: {e}")
            print("Falling back to headless mode")
            headless_mode = True
    
    # Record last frame save time for periodic status updates in headless mode
    last_status_time = time.time()
    
    while not exit_event.is_set():
        try:
            # Check if camera is properly initialized
            if camera is None or not camera.isOpened():
                print("Camera disconnected, attempting to reconnect...")
                
                # Properly release camera if it exists but is not opened
                if camera is not None:
                    camera.release()
                    camera = None
                
                # Wait before trying to reconnect
                time.sleep(2)
                
                # Try to initialize the camera
                camera = init_camera()
                if camera is None or not camera.isOpened():
                    print("Failed to initialize camera. Retrying in 5 seconds...")
                    time.sleep(5)
                continue
            
            # Reset error count if we successfully get here
            error_count = 0
            
            # Read frame with timeout protection
            success, frame = camera.read()
            if not success:
                print("Failed to get frame from camera")
                time.sleep(0.5)
                continue
            
            current_time = time.time()
            
            # If recording, save frames at specified FPS
            if recording:
                try:
                    elapsed_time = current_time - start_time
                    if frame_count == 0 or elapsed_time >= (frame_count / recording_fps):
                        with lock:
                            if video_writer is not None:
                                video_writer.write(frame)
                                frame_count += 1
                    
                    # Print status update in headless mode
                    if headless_mode and (current_time - last_status_time) >= 5:
                        elapsed_sec = int(elapsed_time)
                        hours = elapsed_sec // 3600
                        minutes = (elapsed_sec % 3600) // 60
                        seconds = elapsed_sec % 60
                        print(f"Recording: {hours:02d}:{minutes:02d}:{seconds:02d} ({frame_count} frames captured)")
                        last_status_time = current_time
                        
                except Exception as e:
                    print(f"Error saving frame: {e}")
            
            # Only process display logic if not in headless mode
            if not headless_mode and window_created:
                try:
                    # Make a copy of the frame for display to avoid modifying the original
                    display_frame = frame.copy()
                
                    # Add time display at the bottom left
                    try:
                        cv2.putText(
                            display_frame,
                            datetime.datetime.now().strftime("%H:%M:%S"),
                            (20, display_frame.shape[0] - 20),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1.2,
                            (255, 255, 255),
                            2,
                            cv2.LINE_AA
                        )
                    except Exception as e:
                        print(f"Error adding time text: {e}")
                    
                    # Add recording indicator if recording
                    if recording:
                        try:
                            # Add recording indicator
                            cv2.putText(
                                display_frame,
                                "REC",
                                (20, 50),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                1,
                                (0, 0, 255),
                                2
                            )
                            
                            # Add elapsed time
                            elapsed_time = current_time - start_time
                            elapsed_sec = int(elapsed_time)
                            hours = elapsed_sec // 3600
                            minutes = (elapsed_sec % 3600) // 60
                            seconds = elapsed_sec % 60
                            cv2.putText(
                                display_frame,
                                f"{hours:02d}:{minutes:02d}:{seconds:02d}",
                                (20, 90),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.7,
                                (0, 0, 255),
                                2
                            )
                        except Exception as e:
                            print(f"Error adding recording indicator: {e}")
                    
                    # Display the frame
                    try:
                        cv2.imshow('LockIn Recorder', display_frame)
                    except Exception as e:
                        print(f"Error displaying frame: {e}")
                        # If display fails consistently, switch to headless mode
                        error_count += 1
                        if error_count > 5:
                            print("Persistent display errors. Switching to headless mode.")
                            headless_mode = True
                            try:
                                cv2.destroyAllWindows()
                            except:
                                pass
                            window_created = False
                        continue
                    
                    # Check for key press with a short timeout
                    try:
                        key = cv2.waitKey(30) & 0xFF
                        if key == 27:  # ESC key
                            exit_event.set()
                            break
                        elif key == 32:  # Space key
                            if recording:
                                stop_recording_func()
                                print("Recording stopped via keyboard.")
                            else:
                                success = start_recording_func()
                                if success:
                                    print("Recording started via keyboard.")
                    except Exception as e:
                        print(f"Error handling keyboard input: {e}")
                
                except Exception as e:
                    print(f"Error in display processing: {e}")
            
            # Small delay to reduce CPU usage
            time.sleep(0.01)
            
        except Exception as e:
            error_count += 1
            print(f"Error in camera loop: {e}")
            
            # If we have too many consecutive errors, try to reinitialize the camera
            if error_count > max_errors:
                print("Too many consecutive errors. Reinitializing camera...")
                try:
                    if camera is not None:
                        camera.release()
                        camera = None
                    time.sleep(2)
                    camera = init_camera()
                    error_count = 0
                except Exception as reinit_error:
                    print(f"Error reinitializing camera: {reinit_error}")
                
            time.sleep(0.5)
    
    # Make sure to clean up resources
    if not headless_mode and window_created:
        try:
            cv2.destroyAllWindows()
        except:
            pass
    
    try:
        if camera is not None:
            camera.release()
    except:
        pass

if __name__ == '__main__':
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='LockIn Recorder')
    parser.add_argument('--web', action='store_true', help='Run in web UI mode')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode (no GUI)')
    parser.add_argument('--fps', type=int, help='Frames per second for recording')
    parser.add_argument('--resolution', type=str, help='Resolution in format WIDTHxHEIGHT (e.g., 1920x1080)')
    parser.add_argument('--convert', type=bool, help='Convert recordings to 1 minute')
    parser.add_argument('--output', type=str, help='Output directory for recordings')
    
    args = parser.parse_args()
    
    try:
        # Load settings before starting
        load_settings()
        
        if args.web:
            # Web UI mode
            init_camera()
            app.run(debug=True, threaded=True)
        else:
            # Standalone mode
            run_standalone_mode(args)
    except KeyboardInterrupt:
        # This will catch Ctrl+C if the signal handler doesn't
        print("\nKeyboard interrupt detected. Shutting down...")
        exit_event.set()
    except Exception as e:
        print(f"Unhandled exception: {e}")
    finally:
        # Always clean up resources
        cleanup_resources() 
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
client_connected = False  # Track if any client is connected

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
        
        # Try multiple camera indices (0, 1, 2) to find an available camera
        for cam_index in range(3):
            camera = cv2.VideoCapture(cam_index)
            if camera.isOpened():
                print(f"Successfully opened camera with index {cam_index}")
                
                # Try to set the resolution (but don't fail if it doesn't work)
                camera.set(cv2.CAP_PROP_FRAME_WIDTH, recording_resolution[0])
                camera.set(cv2.CAP_PROP_FRAME_HEIGHT, recording_resolution[1])
                
                # Check what resolution we actually got
                actual_width = camera.get(cv2.CAP_PROP_FRAME_WIDTH)
                actual_height = camera.get(cv2.CAP_PROP_FRAME_HEIGHT)
                print(f"Camera resolution set to: {actual_width}x{actual_height}")
                
                return camera
                
        # If we get here, no camera was successfully opened
        print("Warning: Could not open any camera")
        return None
            
    except Exception as e:
        print(f"Error initializing camera: {e}")
        return None

def add_timestamp_to_frame(frame):
    """Add timestamp to the frame"""
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    
    # Get frame dimensions
    height, width = frame.shape[:2]
    
    # Create semi-transparent background for the timestamp
    overlay = frame.copy()
    
    # Draw black rectangle as background for timestamp
    cv2.rectangle(overlay, (10, height - 50), (350, height - 10), (0, 0, 0), -1)
    
    # Add text with timestamp
    cv2.putText(
        overlay,
        timestamp,
        (20, height - 20),
        cv2.FONT_HERSHEY_SIMPLEX, 
        0.8,  # Font scale
        (255, 255, 255),  # White color
        2,  # Thickness
        cv2.LINE_AA
    )
    
    # Add recording indicator if recording
    if recording:
        elapsed = time.time() - start_time
        elapsed_sec = int(elapsed)
        hours = elapsed_sec // 3600
        minutes = (elapsed_sec % 3600) // 60
        seconds = elapsed_sec % 60
        
        # Draw a red circle and REC text
        cv2.circle(overlay, (width - 120, 30), 10, (0, 0, 255), -1)
        cv2.putText(
            overlay,
            f"REC {hours:02d}:{minutes:02d}:{seconds:02d}",
            (width - 100, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
            cv2.LINE_AA
        )
    
    # Blend the overlay with the original frame
    alpha = 0.7  # Transparency factor
    frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
    
    return frame

def generate_frames():
    global output_frame, camera, recording, video_writer, frame_count, recording_resolution, client_connected
    
    error_count = 0
    max_errors = 5  # Maximum number of consecutive errors before reinitializing camera
    
    while True:
        try:
            # Check if camera is initialized and open
            if camera is None or not camera.isOpened():
                print("Camera not available, trying to initialize...")
                camera = init_camera()
                
                # If still not available, return error frame
                if camera is None or not camera.isOpened():
                    error_count += 1
                    if error_count > max_errors:
                        print(f"Failed to initialize camera after {max_errors} attempts")
                        # Create an error message frame
                        blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                        cv2.putText(blank_frame, "Camera Not Available", (120, 240), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                        ret, buffer = cv2.imencode('.jpg', blank_frame)
                        frame_bytes = buffer.tobytes()
                        
                        # Set client as connected when they receive frames
                        client_connected = True
                        
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                        
                        # Reset error count and sleep to avoid busy loop
                        error_count = 0
                        time.sleep(1)
                    continue
            
            # Read frame from camera
            success, frame = camera.read()
            
            if not success:
                error_count += 1
                print(f"Failed to read frame, error {error_count}/{max_errors}")
                
                if error_count > max_errors:
                    # Try to reinitialize camera
                    print("Reinitializing camera due to consecutive read failures")
                    if camera is not None:
                        camera.release()
                    camera = init_camera()
                    error_count = 0
                
                # Create a blank frame with error message
                blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(blank_frame, "Camera Signal Lost", (150, 240), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                ret, buffer = cv2.imencode('.jpg', blank_frame)
                frame_bytes = buffer.tobytes()
                
                # Set client as connected when they receive frames
                client_connected = True
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                continue
            
            # Reset error count when successful
            error_count = 0
            
            # Add timestamp to frame
            frame = add_timestamp_to_frame(frame)
            
            # If recording, write frame to video
            if recording and video_writer is not None:
                video_writer.write(frame)
                frame_count += 1
                
            # Convert to JPEG and yield to web client
            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            
            with lock:
                output_frame = frame_bytes
            
            # Set client as connected when they receive frames
            client_connected = True
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                   
        except Exception as e:
            print(f"Error in generate_frames: {e}")
            # Return an error frame
            blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(blank_frame, f"Error: {str(e)[:30]}", (100, 240), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            ret, buffer = cv2.imencode('.jpg', blank_frame)
            frame_bytes = buffer.tobytes()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            # Avoid busy loop on error
            time.sleep(0.5)

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
    """Video streaming route. Get this in an img src attribute."""
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/check_recording_status')
def check_recording_status():
    """Check if recording is active and update client_connected status"""
    global client_connected
    
    # Mark client as connected
    client_connected = True
    
    return jsonify({
        "status": "success",
        "recording": recording,
        "elapsed": time.time() - start_time if recording else 0
    })

def start_recording_func(output_dir=None, fps=None, width=None, height=None, convert=None):
    """Start recording video"""
    global recording, output_path, start_time, frame_count, recording_fps, recording_resolution
    global video_writer, recording_filename, convert_to_one_minute
    
    if recording:
        return {"status": "error", "message": "Already recording"}
    
    # Use provided parameters or defaults
    if output_dir is not None:
        output_path = output_dir
    if fps is not None:
        recording_fps = fps
    if width is not None and height is not None:
        recording_resolution = (width, height)
    if convert is not None:
        convert_to_one_minute = convert
    
    # Ensure output directory exists
    os.makedirs(output_path, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    recording_filename = f"{output_path}/recording_{timestamp}.mp4"
    
    try:
        # Create VideoWriter object with MP4 format
        if sys.platform == 'darwin':  # macOS
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # mp4v for Mac
        else:
            # For other platforms, try H264 or fallback to XVID
            try:
                fourcc = cv2.VideoWriter_fourcc(*'H264')
            except:
                fourcc = cv2.VideoWriter_fourcc(*'XVID')
                # Change extension if we're using XVID
                recording_filename = recording_filename.replace('.mp4', '.avi')
                
        video_writer = cv2.VideoWriter(
            recording_filename, 
            fourcc, 
            recording_fps, 
            recording_resolution
        )
        
        if not video_writer.isOpened():
            return {"status": "error", "message": "Failed to create video writer"}
        
        # Reset frame count and start time
        start_time = time.time()
        frame_count = 0
        recording = True
        
        print(f"Recording started: {recording_filename}")
        print(f"FPS: {recording_fps}, Resolution: {recording_resolution}")
        
        return {"status": "success", "filename": recording_filename}
    
    except Exception as e:
        error_msg = f"Error starting recording: {str(e)}"
        print(error_msg)
        return {"status": "error", "message": error_msg}

def stop_recording_func():
    """Stop recording video"""
    global recording, video_writer, recording_filename
    
    if not recording:
        return {"status": "error", "message": "Not recording"}
    
    try:
        recording = False
        
        if video_writer is not None:
            video_writer.release()
            video_writer = None
        
        print(f"Recording stopped: {recording_filename}")
        
        # Convert the video if needed
        if convert_to_one_minute and os.path.exists(recording_filename):
            output_file = recording_filename.replace('.mp4', '_1min.mp4')
            if recording_filename.endswith('.avi'):
                output_file = recording_filename.replace('.avi', '_1min.mp4')
                
            print(f"Converting {recording_filename} to 1 minute...")
            
            try:
                process_video(recording_filename, output_file)
                print(f"Conversion complete: {output_file}")
                
                # For AVI files, we can optionally convert them to MP4
                if recording_filename.endswith('.avi'):
                    print(f"Converting AVI to MP4...")
                    convert_to_mp4(recording_filename)
                
            except Exception as e:
                print(f"Error during conversion: {e}")
        
        return {"status": "success", "filename": recording_filename}
    
    except Exception as e:
        error_msg = f"Error stopping recording: {str(e)}"
        print(error_msg)
        return {"status": "error", "message": error_msg}

# New function to convert AVI to MP4
def convert_to_mp4(input_file):
    """Convert an AVI file to MP4 format"""
    if not input_file.endswith('.avi'):
        return
        
    try:
        output_file = input_file.replace('.avi', '.mp4')
        
        # Check if ffmpeg is available
        try:
            subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            has_ffmpeg = True
        except:
            has_ffmpeg = False
            
        if has_ffmpeg:
            # Use ffmpeg for conversion
            cmd = [
                'ffmpeg',
                '-i', input_file,
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '22',
                '-y',
                output_file
            ]
            
            print(f"Running ffmpeg conversion: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            print(f"Converted {input_file} to {output_file}")
            
            # Optionally delete the original file
            # os.remove(input_file)
        else:
            print("ffmpeg not found, using OpenCV for conversion")
            # Use OpenCV for conversion
            cap = cv2.VideoCapture(input_file)
            if not cap.isOpened():
                raise Exception("Could not open input file")
                
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(output_file, fourcc, fps, (width, height))
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                out.write(frame)
                
            cap.release()
            out.release()
            print(f"Converted {input_file} to {output_file}")
            
            # Optionally delete the original file
            # os.remove(input_file)
    except Exception as e:
        print(f"Error converting to MP4: {e}")

@app.route('/start_recording', methods=['POST'])
def start_recording():
    data = request.get_json()
    output_dir = data.get('output_directory', output_path)
    fps = int(data.get('fps', recording_fps))
    width = int(data.get('width', recording_resolution[0]))
    height = int(data.get('height', recording_resolution[1]))
    convert = data.get('convert_to_one_minute', convert_to_one_minute)
    
    success = start_recording_func(output_dir, fps, width, height, convert)
    
    if success['status'] == 'success':
        return jsonify({"status": "success", "message": "Recording started", "filename": success['filename']})
    else:
        return jsonify({"status": "error", "message": success['message']})

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
    """Get list of recordings"""
    try:
        recordings = []
        
        if not os.path.exists(output_path):
            return jsonify({"status": "success", "recordings": []})
        
        # List all video files in the output directory
        for filename in os.listdir(output_path):
            if filename.endswith(('.mp4', '.avi')):
                file_path = os.path.join(output_path, filename)
                
                if os.path.isfile(file_path):
                    file_stats = os.stat(file_path)
                    created_time = file_stats.st_ctime
                    size_bytes = file_stats.st_size
                    
                    # Get video duration if possible
                    duration = 0
                    try:
                        cap = cv2.VideoCapture(file_path)
                        if cap.isOpened():
                            # Get fps and frame count
                            fps = cap.get(cv2.CAP_PROP_FPS)
                            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                            
                            if fps > 0 and frame_count > 0:
                                duration = frame_count / fps
                        cap.release()
                    except Exception as e:
                        print(f"Error getting duration for {filename}: {e}")
                    
                    recordings.append({
                        "filename": filename,
                        "path": file_path,
                        "created": created_time,
                        "created_formatted": datetime.datetime.fromtimestamp(created_time).strftime("%Y-%m-%d %H:%M:%S"),
                        "size": size_bytes,
                        "size_formatted": format_file_size(size_bytes),
                        "duration": duration,
                        "duration_formatted": format_duration(duration)
                    })
        
        # Sort by creation time (newest first)
        recordings.sort(key=lambda x: x["created"], reverse=True)
        
        return jsonify({"status": "success", "recordings": recordings})
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/delete_recording', methods=['POST'])
def delete_recording():
    """Delete a recording file"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        
        if not filename:
            return jsonify({"status": "error", "message": "No filename provided"})
        
        # Security check - ensure no path traversal
        if '..' in filename or '/' in filename:
            return jsonify({"status": "error", "message": "Invalid filename"})
        
        file_path = os.path.join(output_path, filename)
        
        if not os.path.exists(file_path):
            return jsonify({"status": "error", "message": "File not found"})
        
        os.remove(file_path)
        
        return jsonify({"status": "success", "message": f"File {filename} deleted successfully"})
    
    except Exception as e:
        error_message = f"Error deleting file: {str(e)}"
        print(error_message)
        return jsonify({"status": "error", "message": error_message})

def format_file_size(size_bytes):
    """Format file size in human-readable form"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes/(1024*1024):.1f} MB"
    else:
        return f"{size_bytes/(1024*1024*1024):.1f} GB"

def format_duration(duration):
    """Format duration in human-readable form"""
    if duration < 60:
        return f"{duration:.2f} seconds"
    elif duration < 3600:
        minutes = int(duration / 60)
        seconds = int(duration % 60)
        return f"{minutes} minutes {seconds} seconds"
    else:
        hours = int(duration / 3600)
        minutes = int((duration % 3600) / 60)
        seconds = int(duration % 60)
        return f"{hours} hours {minutes} minutes {seconds} seconds"

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
                    if success['status'] == 'success':
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
                
                    # Add time display at the bottom left using the timestamp function
                    display_frame = add_timestamp_to_frame(display_frame)
                    
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
                                if success['status'] == 'success':
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

@app.route('/recordings/<filename>')
def serve_recording(filename):
    """Serve a recording file"""
    # Security check to prevent directory traversal
    if '..' in filename or '/' in filename:
        return "Invalid filename", 400
    
    # Check if file exists
    file_path = os.path.join(output_path, filename)
    if not os.path.exists(file_path):
        return "File not found", 404
    
    # Determine the correct MIME type
    mime_type = 'video/mp4'
    if filename.endswith('.avi'):
        mime_type = 'video/x-msvideo'
    
    # Serve the file
    return Response(
        open(file_path, 'rb'),
        mimetype=mime_type,
        headers={
            "Content-Disposition": f"inline; filename={filename}",
            "Accept-Ranges": "bytes"  # Enable seeking in video player
        }
    )

if __name__ == '__main__':
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='LockIn Recorder - Record and convert videos')
    parser.add_argument('--standalone', action='store_true', help='Run in standalone mode (no web interface)')
    parser.add_argument('--headless', action='store_true', help='Run without GUI (for standalone mode)')
    parser.add_argument('--output', type=str, default='recordings', help='Output directory for recordings')
    parser.add_argument('--fps', type=int, default=2, help='Recording FPS')
    parser.add_argument('--width', type=int, default=1920, help='Recording width')
    parser.add_argument('--height', type=int, default=1080, help='Recording height')
    parser.add_argument('--no-convert', action='store_true', help="Don't convert recordings to 1 minute")
    parser.add_argument('--port', type=int, default=5000, help='Port for web interface')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host for web interface')
    args = parser.parse_args()
    
    # Update global settings
    output_path = args.output
    recording_fps = args.fps
    recording_resolution = (args.width, args.height)
    convert_to_one_minute = not args.no_convert
    headless_mode = args.headless
    
    # Create output directory
    os.makedirs(output_path, exist_ok=True)
    
    # Initialize camera once at startup
    init_camera()
        
    try:
        # Run in either standalone or web mode
        if args.standalone:
            standalone_mode = True
            print("LockIn Recorder - Standalone Mode")
            print(f"FPS: {recording_fps}")
            print(f"Resolution: {recording_resolution[0]}x{recording_resolution[1]}")
            print(f"Convert to 1 minute: {convert_to_one_minute}")
            print(f"Output directory: {output_path}")
            print(f"Headless mode: {headless_mode}")
            run_standalone_mode(args)
        else:
            # Web mode
            print("LockIn Recorder - Web Mode")
            print(f"FPS: {recording_fps}")
            print(f"Resolution: {recording_resolution[0]}x{recording_resolution[1]}")
            print(f"Convert to 1 minute: {convert_to_one_minute}")
            print(f"Output directory: {output_path}")
            print(f"Access the web interface at http://localhost:{args.port}")
            app.run(debug=False, host=args.host, port=args.port, threaded=True)
    except KeyboardInterrupt:
        print("\nReceived interrupt, shutting down...")
    except Exception as e:
        print(f"Error in main: {e}")
    finally:
        # Clean up resources
        cleanup_resources()
        print("LockIn Recorder shutdown complete") 
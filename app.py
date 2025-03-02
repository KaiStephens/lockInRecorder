import os
import cv2
import time
import datetime
import numpy as np
import json
from flask import Flask, render_template, Response, request, jsonify
import threading
import subprocess

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
convert_to_one_minute = True
video_writer = None
settings_file = "settings.json"

def init_camera():
    global camera
    camera = cv2.VideoCapture(0)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, recording_resolution[0])
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, recording_resolution[1])
    return camera

def generate_frames():
    global output_frame, camera, recording, video_writer, frame_count
    
    if camera is None:
        camera = init_camera()
    
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            # Only save frames at the specified FPS when recording
            current_time = time.time()
            if recording:
                elapsed_time = current_time - start_time
                # Calculate if we should capture this frame based on FPS
                if frame_count == 0 or elapsed_time >= (frame_count / recording_fps):
                    # Add timestamp to frame before saving
                    timestamp_frame = frame.copy()
                    add_timestamp_to_frame(timestamp_frame)
                    
                    with lock:
                        if video_writer is not None:
                            video_writer.write(timestamp_frame)
                            frame_count += 1
            
            # For display, resize to the recording resolution
            frame = cv2.resize(frame, recording_resolution)
            
            # Add timestamp to the bottom right corner
            add_timestamp_to_frame(frame)
            
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
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    height, width = frame.shape[:2]
    
    # Calculate position (bottom left with padding)
    x = width // 2 - 200  # Move to the middle-left of the frame
    y = height - 30  # 30px from bottom
    
    # Add a semi-transparent background for better visibility
    overlay = frame.copy()
    cv2.rectangle(overlay, (x-20, y-40), (x + 380, height-10), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
    
    # Add text with larger font
    cv2.putText(
        frame, 
        current_time, 
        (x, y), 
        cv2.FONT_HERSHEY_SIMPLEX, 
        1.2,  # Increased font scale from 0.7 to 1.2
        (255, 255, 255),  # White color
        2,  # Increased thickness from 1 to 2
        cv2.LINE_AA
    )

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
    
    # Use ffmpeg for converting
    cmd = [
        "ffmpeg", "-i", input_file,
        "-filter:v", f"setpts={1/speed_multiplier}*PTS",
        "-r", str(output_fps),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
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

@app.route('/start_recording', methods=['POST'])
def start_recording():
    global recording, output_path, recording_filename, start_time, frame_count
    global video_writer, recording_fps, recording_resolution, convert_to_one_minute
    
    if recording:
        return jsonify({"status": "error", "message": "Already recording"})
    
    # Get parameters from the request
    data = request.get_json()
    output_dir = data.get('output_directory', output_path)
    recording_fps = int(data.get('fps', recording_fps))
    width = int(data.get('width', recording_resolution[0]))
    height = int(data.get('height', recording_resolution[1]))
    recording_resolution = (width, height)
    convert_to_one_minute = data.get('convert_to_one_minute', convert_to_one_minute)
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    recording_filename = os.path.join(output_dir, f"lockin-{timestamp}.mp4")  # Changed to .mp4
    
    # Initialize the video writer
    fourcc = cv2.VideoWriter_fourcc(*'avc1')  # Changed to AVC1 codec for better compatibility
    video_writer = cv2.VideoWriter(recording_filename, fourcc, recording_fps, recording_resolution)
    
    # Reset frame count and start time
    frame_count = 0
    start_time = time.time()
    
    # Start recording
    recording = True
    
    return jsonify({"status": "success", "message": "Recording started", "filename": recording_filename})

@app.route('/stop_recording', methods=['POST'])
def stop_recording():
    global recording, video_writer, recording_filename, convert_to_one_minute
    
    if not recording:
        return jsonify({"status": "error", "message": "Not recording"})
    
    recording = False
    
    # Close the video writer
    if video_writer is not None:
        video_writer.release()
        video_writer = None
    
    output_file = recording_filename
    
    # Convert video to be exactly one minute if requested
    if convert_to_one_minute:
        base, ext = os.path.splitext(recording_filename)
        output_file = f"{base}_1min{ext}"
        process_video(recording_filename, output_file)
    
    return jsonify({
        "status": "success", 
        "message": "Recording stopped", 
        "filename": output_file,
        "converted": convert_to_one_minute
    })

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
    """API endpoint to get list of recent recordings"""
    global output_path
    recordings = []
    
    try:
        if os.path.exists(output_path):
            # Get all mp4 files in the recordings directory
            files = [f for f in os.listdir(output_path) if f.endswith('.mp4')]
            
            # Sort by modification time (newest first)
            files.sort(key=lambda x: os.path.getmtime(os.path.join(output_path, x)), reverse=True)
            
            # Get file information
            for file in files:
                file_path = os.path.join(output_path, file)
                timestamp = os.path.getmtime(file_path)
                size = os.path.getsize(file_path) / (1024 * 1024)  # Convert to MB
                
                recordings.append({
                    "name": file,
                    "path": file_path,
                    "modified": datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                    "size": f"{size:.2f} MB"
                })
    except Exception as e:
        print(f"Error getting recordings: {e}")
    
    return jsonify({"status": "success", "recordings": recordings})

if __name__ == '__main__':
    try:
        # Load settings before starting
        load_settings()
        init_camera()
        app.run(debug=True, threaded=True)
    finally:
        if camera is not None:
            camera.release() 
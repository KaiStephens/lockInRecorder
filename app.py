import os
import cv2
import time
import datetime
import numpy as np
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
recording_resolution = (640, 480)
convert_to_one_minute = True
video_writer = None

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
                    with lock:
                        if video_writer is not None:
                            video_writer.write(frame)
                            frame_count += 1
            
            # For display, resize to the recording resolution
            frame = cv2.resize(frame, recording_resolution)
            
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
    recording_filename = os.path.join(output_dir, f"lockin-{timestamp}.avi")
    
    # Initialize the video writer
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
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
    global recording_fps, recording_resolution, convert_to_one_minute, camera
    
    if recording:
        return jsonify({"status": "error", "message": "Cannot change settings while recording"})
    
    data = request.get_json()
    
    # Update settings
    recording_fps = int(data.get('fps', recording_fps))
    width = int(data.get('width', recording_resolution[0]))
    height = int(data.get('height', recording_resolution[1]))
    recording_resolution = (width, height)
    convert_to_one_minute = data.get('convert_to_one_minute', convert_to_one_minute)
    
    # Update camera settings
    if camera is not None:
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, recording_resolution[0])
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, recording_resolution[1])
    
    return jsonify({
        "status": "success", 
        "message": "Settings updated",
        "settings": {
            "fps": recording_fps,
            "resolution": recording_resolution,
            "convert_to_one_minute": convert_to_one_minute
        }
    })

if __name__ == '__main__':
    try:
        init_camera()
        app.run(debug=True, threaded=True)
    finally:
        if camera is not None:
            camera.release() 
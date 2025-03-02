# LockIn Recorder

A Flask-based web application that allows you to record videos from your camera at a specified frame rate and optionally convert them to exactly 1 minute duration.

## Features

- Live camera preview in the browser
- Record video at customizable FPS (default: 2fps)
- Select from multiple resolution options
- Set custom output directory for recordings
- Videos are saved with timestamp in the format "lockin-{time}.avi"
- Option to automatically convert videos to exactly 1-minute duration
- Modern, responsive web interface
- Real-time recording status and timer
- Recent recordings list

## Requirements

- Python 3.6+
- OpenCV
- Flask
- FFmpeg (for video conversion)

## Installation

1. Clone the repository:
```
git clone https://github.com/yourusername/lockInRecorder.git
cd lockInRecorder
```

2. Install the required dependencies:
```
pip install -r requirements.txt
```

3. Install FFmpeg (if not already installed):
   - On macOS: `brew install ffmpeg`
   - On Ubuntu/Debian: `sudo apt-get install ffmpeg`
   - On Windows: Download from [FFmpeg website](https://ffmpeg.org/download.html)

## Usage

1. Run the application:
```
python app.py
```

2. Open your web browser and navigate to:
```
http://127.0.0.1:5000
```

3. Configure your recording settings:
   - FPS: Adjust the frames per second (1-30)
   - Resolution: Select from predefined options (640x480, 1280x720, 1920x1080)
   - Output Directory: Specify where recordings should be saved
   - Convert to 1 Minute: Toggle whether to automatically convert recordings to exactly 1 minute

4. Click "Apply Settings" to save your configuration

5. Click "Start Recording" to begin recording from your camera

6. Click "Stop Recording" when finished

## How It Works

- The application captures frames at the specified FPS during recording
- When recording is stopped:
  - If "Convert to 1 Minute" is enabled, the application calculates the speed multiplier needed to make the video exactly 1 minute
  - FFmpeg is used for the video conversion process
  - Both the original and the converted video are saved (if conversion is enabled)

## Troubleshooting

- If the camera doesn't work, ensure your browser has permission to access your camera
- If video conversion fails, ensure FFmpeg is properly installed and accessible in your system PATH
- Check the console output for any error messages

## License

MIT License 
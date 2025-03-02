# LockIn Recorder

A Flask-based web application that allows you to record videos from your camera at a specified frame rate and optionally convert them to exactly 1 minute duration.

Exmaple of usage: https://x.com/kaiostephens/status/1895316070199672837

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

### Web UI Mode

1. Run the application in web UI mode:
```
python app.py --web
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

### Standalone Mode (No Web UI)

1. Run the application in standalone mode (default):
```
python app.py
```

2. The application will open a camera window with time displayed in the bottom left

3. Controls:
   - Press `Space` in the camera window to start/stop recording
   - Press `ESC` in the camera window to exit the application
   - In the terminal, enter `r` to start recording
   - Type `s` to access settings menu
   - Press Enter to stop recording when prompted
   - Type `q` to quit the application

4. Command-line options:
```
python app.py [options]

Options:
  --web              Run in web UI mode
  --headless         Run without GUI (useful for servers or remote environments)
  --fps FPS          Frames per second for recording
  --resolution RES   Resolution in format WIDTHxHEIGHT (e.g., 1920x1080)
  --convert BOOL     Convert recordings to 1 minute (True/False)
  --output DIR       Output directory for recordings
```

Examples:
```
# Run with web UI
python app.py --web

# Run in headless mode (no GUI)
python app.py --headless

# Run with custom settings
python app.py --fps 5 --resolution 1280x720 --output my_recordings
```

### Headless Mode

For environments without display support (like servers or remote terminals), you can use headless mode:

```
python app.py --headless
```

In headless mode:
- No camera window is displayed
- All interaction happens through the terminal
- Recording status updates are printed periodically
- All functionality works the same as regular standalone mode

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
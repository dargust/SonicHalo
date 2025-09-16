# Audio Visualizer

This project is a real-time audio visualizer built using Python. It utilizes the qt5 library and opengl for the graphical user interface (GUI) and the SoundDevice library for audio input processing. The visualizer displays audio data in the form of animated bars, providing a dynamic representation of sound.

## Project Structure

```
audio_visualizer
├── src
│   ├── pyqt5_audio_visualiser_optimise.py  # Main application code for the audio visualizer
├── requirements.txt                  # Project dependencies
└── README.md                         # Documentation for the project
```

## Installation

To set up the project, follow these steps:

1. Clone the repository:
   ```
   git clone <repository-url>
   cd audio_visualizer
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

To run the audio visualizer, execute the following command:

```
python src/pyqt5_audio_visualiser_optimise.py
```

Hotkeys and their effects are listed in the command line

## Features

- Real-time audio visualization with animated bars.
- Key-bind interface for dynamic control of the visualizer.
- Adjustable settings for audio processing and visualization.
- Saved settings and window positions in user %localappdata%

## Contributing

Contributions are welcome! If you have suggestions or improvements, please open an issue or submit a pull request.
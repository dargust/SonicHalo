# Audio Visualizer

This project is a real-time audio visualizer built using Python. It utilizes the Tkinter library for the graphical user interface (GUI) and the SoundDevice library for audio input processing. The visualizer displays audio data in the form of animated bars, providing a dynamic representation of sound.

## Project Structure

```
audio_visualizer
├── src
│   ├── tkinter_audio_visualiser.py  # Main application code for the audio visualizer
│   └── cli_thread.py                 # Command line input processing in a separate thread
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
python src/tkinter_audio_visualiser.py
```

While the application is running, you can input commands in the command line to modify the visualizer's behavior. The command line input processing runs in a separate thread, allowing for real-time interaction.

## Features

- Real-time audio visualization with animated bars.
- Command line interface for dynamic control of the visualizer.
- Adjustable settings for audio processing and visualization.

## Contributing

Contributions are welcome! If you have suggestions or improvements, please open an issue or submit a pull request.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
#!/bin/bash
# Linux setup script for Sonic Halo Audio Visualizer

echo "==================================="
echo "Sonic Halo - Linux Setup"
echo "==================================="

# Update package manager
echo "Updating package manager..."
if command -v apt-get &> /dev/null; then
    sudo apt-get update
elif command -v dnf &> /dev/null; then
    sudo dnf check-update
elif command -v pacman &> /dev/null; then
    sudo pacman -Sy
fi

# Install system dependencies
echo "Installing system dependencies..."

if command -v apt-get &> /dev/null; then
    # Debian/Ubuntu
    sudo apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
        pulseaudio \
        pulseaudio-utils \
        libasound2-dev \
        portaudio19-dev \
        python3-pyqt5 \
        python3-opengl \
        git
elif command -v dnf &> /dev/null; then
    # Fedora/CentOS/RHEL
    sudo dnf install -y \
        python3 \
        python3-pip \
        pulseaudio \
        pulseaudio-utils \
        alsa-lib-devel \
        portaudio-devel \
        python3-PyQt5 \
        python3-pyopengl \
        git
elif command -v pacman &> /dev/null; then
    # Arch Linux
    sudo pacman -S --noconfirm \
        python \
        python-pip \
        pulseaudio \
        pulseaudio-alsa \
        alsa-lib \
        portaudio \
        python-pyqt5 \
        python-pyopengl \
        git
else
    echo "Unsupported package manager. Please install dependencies manually:"
    echo "- Python 3.8+"
    echo "- PulseAudio"
    echo "- PortAudio"
    echo "- PyQt5"
    echo "- PyOpenGL"
fi

# Create virtual environment
echo "Creating Python virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Set up PulseAudio for system audio capture
echo "Setting up PulseAudio for system audio capture..."
echo "Loading null sink module..."
pactl load-module module-null-sink sink_name=sonic_halo_null sink_properties=device.description="Sonic_Halo_Virtual_Sink" || echo "Module may already be loaded"

echo "Loading loopback module..."
pactl load-module module-loopback source=sonic_halo_null.monitor latency_msec=1 || echo "Loopback may already be configured"

# Create desktop entry
echo "Creating desktop entry..."
cat > ~/.local/share/applications/sonic-halo.desktop << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Sonic Halo
Comment=Real-Time Audio Visualizer
Exec=$(pwd)/venv/bin/python $(pwd)/sonic_halo_launcher.py
Icon=$(pwd)/media/sonic_halo_2.ico
Terminal=false
Categories=AudioVideo;Audio;
StartupNotify=true
EOF

# Make launcher executable
chmod +x sonic_halo_launcher.py

echo "==================================="
echo "Setup complete!"
echo ""
echo "To run Sonic Halo:"
echo "1. Activate the virtual environment: source venv/bin/activate"
echo "2. Run: python sonic_halo_launcher.py"
echo ""
echo "For system audio capture:"
echo "1. Set your audio output to 'Sonic_Halo_Virtual_Sink'"
echo "2. The visualizer will capture system audio automatically"
echo ""
echo "Desktop shortcut created in Applications menu"
echo "==================================="
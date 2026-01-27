#!/bin/bash
# macOS setup script for Sonic Halo Audio Visualizer

echo "==================================="
echo "Sonic Halo - macOS Setup"
echo "==================================="

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# Install system dependencies
echo "Installing system dependencies..."
brew install python3 portaudio pkg-config

# Install BlackHole for system audio capture
echo "Would you like to install BlackHole for system audio capture? (y/n)"
read -r response
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo "Installing BlackHole..."
    brew install blackhole-2ch
    echo "BlackHole installed. You may need to restart your audio system."
else
    echo "Skipping BlackHole installation."
    echo "You can install it later from: https://github.com/ExistentialAudio/BlackHole"
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

# Create application bundle directory structure
echo "Creating application bundle..."
mkdir -p "Sonic Halo.app/Contents/MacOS"
mkdir -p "Sonic Halo.app/Contents/Resources"

# Create Info.plist
cat > "Sonic Halo.app/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDisplayName</key>
    <string>Sonic Halo</string>
    <key>CFBundleExecutable</key>
    <string>sonic_halo_launcher</string>
    <key>CFBundleIconFile</key>
    <string>sonic_halo_2.icns</string>
    <key>CFBundleIdentifier</key>
    <string>com.dacus.sonichalo</string>
    <key>CFBundleName</key>
    <string>Sonic Halo</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>0.9.3</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.14</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>This app needs microphone access for audio visualization.</string>
</dict>
</plist>
EOF

# Create launcher script
cat > "Sonic Halo.app/Contents/MacOS/sonic_halo_launcher" << EOF
#!/bin/bash
cd "\$(dirname "\$0")/../../.."
source venv/bin/activate
python sonic_halo_launcher.py
EOF

chmod +x "Sonic Halo.app/Contents/MacOS/sonic_halo_launcher"

# Copy icon if it exists
if [ -f "media/sonic_halo_2.ico" ]; then
    # Convert ICO to ICNS if needed (requires ImageMagick)
    if command -v convert &> /dev/null; then
        convert "media/sonic_halo_2.ico" "Sonic Halo.app/Contents/Resources/sonic_halo_2.icns"
    else
        echo "Note: Install ImageMagick to convert the icon: brew install imagemagick"
    fi
fi

# Make launcher executable
chmod +x sonic_halo_launcher.py

echo "==================================="
echo "Setup complete!"
echo ""
echo "To run Sonic Halo:"
echo "1. Activate the virtual environment: source venv/bin/activate"
echo "2. Run: python sonic_halo_launcher.py"
echo "   OR double-click the 'Sonic Halo.app' bundle"
echo ""
echo "For system audio capture:"
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo "1. Go to Audio MIDI Setup"
    echo "2. Create a Multi-Output Device"
    echo "3. Include your speakers and BlackHole 2ch"
    echo "4. Set this Multi-Output Device as your system output"
    echo "5. In Sonic Halo, select BlackHole 2ch as input"
else
    echo "1. Install BlackHole: brew install blackhole-2ch"
    echo "2. Follow the setup instructions above"
fi
echo "==================================="
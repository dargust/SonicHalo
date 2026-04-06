#!/usr/bin/env python3
"""
Cross-platform startup script for Sonic Halo Audio Visualizer
"""
import sys
import os
import logging
import subprocess

# Add src directory to path if needed
src_dir = os.path.join(os.path.dirname(__file__), 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# Platform detection
ON_WINDOWS = sys.platform.startswith('win')
ON_LINUX = sys.platform.startswith('linux')
ON_MACOS = sys.platform.startswith('darwin')

def check_dependencies():
    """Check and report on platform-specific dependencies"""
    missing_deps = []
    warnings = []
    
    # Check core dependencies
    try:
        import numpy
        import sounddevice
        from PyQt5 import QtWidgets
        from OpenGL import GL
    except ImportError as e:
        missing_deps.append(f"Core dependency missing: {e}")
    
    # Check platform-specific dependencies
    if ON_WINDOWS:
        try:
            import pyaudiowpatch
            print("✓ PyAudioWPatch available for Windows WASAPI loopback")
        except ImportError:
            warnings.append("PyAudioWPatch not available - system audio capture disabled")
        
        try:
            import winsdk
            print("✓ Windows SDK available for media control")
        except ImportError:
            warnings.append("Windows SDK not available - song detection disabled")
            
        try:
            import win32api
            print("✓ Win32 API available for system tray")
        except ImportError:
            warnings.append("Win32 API not available - system tray disabled")
    
    elif ON_LINUX:
        # Check for pactl (works for both PulseAudio and PipeWire via compat layer)
        try:
            subprocess.run(['pactl', '--version'],
                          capture_output=True, text=True, check=True)
            # Also detect whether the backend is PipeWire or PulseAudio
            try:
                info = subprocess.run(['pactl', 'info'], capture_output=True, text=True)
                if 'PipeWire' in info.stdout:
                    print("✓ PipeWire audio server detected (PulseAudio compat active)")
                else:
                    print("✓ PulseAudio available")
            except Exception:
                print("✓ pactl available")
        except (subprocess.CalledProcessError, FileNotFoundError):
            warnings.append("pactl not found - monitor source auto-detection disabled")
    
    elif ON_MACOS:
        warnings.append("macOS: Install BlackHole or Soundflower for system audio capture")
        warnings.append("BlackHole: https://github.com/ExistentialAudio/BlackHole")
    
    # Report results
    if missing_deps:
        print("❌ Critical dependencies missing:")
        for dep in missing_deps:
            print(f"   {dep}")
        print("\nInstall missing dependencies with:")
        print("   pip install -r requirements.txt")
        return False
    
    if warnings:
        print("\n⚠️  Warnings:")
        for warning in warnings:
            print(f"   {warning}")
    
    print(f"\n✓ Platform: {sys.platform}")
    return True

def setup_audio_system():
    """Set up audio system for the current platform"""
    if ON_LINUX:
        print("Linux audio system: using existing monitor sources")
        print("   PulseAudio/PipeWire monitor sources are used passively - no new sinks created")
    
    elif ON_MACOS:
        print("macOS audio system:")
        print("   Make sure BlackHole or Soundflower is installed for system audio")
    
    elif ON_WINDOWS:
        print("Windows audio system ready")

def main():
    """Main startup function"""
    print("=" * 60)
    print("Sonic Halo: Real-Time Audio Visualizer")
    print("Cross-Platform Startup")
    print("=" * 60)
    
    # Check dependencies
    if not check_dependencies():
        print("\n❌ Cannot start due to missing dependencies")
        return 1
    
    # Setup audio system
    setup_audio_system()
    
    print("\n🚀 Starting Sonic Halo...")
    print("=" * 60)
    
    # Import and run the main application
    try:
        from pyqt5_audio_visualiser_optimise import MainWindow
        from PyQt5 import QtWidgets, QtGui
        import sys
        
        fmt = QtGui.QSurfaceFormat()
        fmt.setAlphaBufferSize(8)
        QtGui.QSurfaceFormat.setDefaultFormat(fmt)
        app = QtWidgets.QApplication(sys.argv)
        window = MainWindow()
        window.show()
        return app.exec_()
        
    except Exception as e:
        print(f"❌ Failed to start application: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
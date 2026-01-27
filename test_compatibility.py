#!/usr/bin/env python3
"""
Test script to verify cross-platform functionality
"""
import sys
import os

# Add src directory to path
src_dir = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, src_dir)

def test_platform_detection():
    """Test platform detection"""
    print("Testing platform detection...")
    
    ON_WINDOWS = sys.platform.startswith('win')
    ON_LINUX = sys.platform.startswith('linux')
    ON_MACOS = sys.platform.startswith('darwin')
    
    print(f"Platform: {sys.platform}")
    print(f"Windows: {ON_WINDOWS}")
    print(f"Linux: {ON_LINUX}")
    print(f"macOS: {ON_MACOS}")
    return True

def test_cross_platform_modules():
    """Test importing cross-platform modules"""
    print("\nTesting cross-platform module imports...")
    
    try:
        from cross_platform_tray import CrossPlatformTrayIcon
        print("✓ Cross-platform tray icon module imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import cross-platform tray: {e}")
        return False
    
    try:
        from cross_platform_audio import get_system_audio_devices
        print("✓ Cross-platform audio module imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import cross-platform audio: {e}")
        return False
    
    return True

def test_core_dependencies():
    """Test core dependencies"""
    print("\nTesting core dependencies...")
    
    try:
        import numpy
        print("✓ NumPy available")
    except ImportError:
        print("❌ NumPy not available")
        return False
    
    try:
        import sounddevice
        print("✓ SoundDevice available")
    except ImportError:
        print("❌ SoundDevice not available")
        return False
    
    try:
        from PyQt5 import QtWidgets, QtCore, QtGui
        print("✓ PyQt5 available")
    except ImportError:
        print("❌ PyQt5 not available")
        return False
    
    try:
        from OpenGL import GL
        print("✓ PyOpenGL available")
    except ImportError:
        print("❌ PyOpenGL not available")
        return False
    
    return True

def test_platform_specific():
    """Test platform-specific functionality"""
    print("\nTesting platform-specific functionality...")
    
    ON_WINDOWS = sys.platform.startswith('win')
    
    if ON_WINDOWS:
        try:
            import pyaudiowpatch
            print("✓ PyAudioWPatch available (Windows system audio)")
        except ImportError:
            print("⚠️  PyAudioWPatch not available (system audio will use fallback)")
        
        try:
            import winsdk
            print("✓ Windows SDK available (media control)")
        except ImportError:
            print("⚠️  Windows SDK not available (song detection disabled)")
        
        try:
            import win32api
            print("✓ Win32 API available (system tray)")
        except ImportError:
            print("⚠️  Win32 API not available (system tray will use PyQt5)")
    
    return True

def test_audio_device_detection():
    """Test audio device detection"""
    print("\nTesting audio device detection...")
    
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        print(f"✓ Found {len(devices)} audio devices")
        
        input_devices = [d for d in devices if d['max_input_channels'] > 0]
        print(f"✓ Found {len(input_devices)} input devices")
        
        if input_devices:
            print("Sample input devices:")
            for i, device in enumerate(input_devices[:3]):  # Show first 3
                print(f"  {i}: {device['name']} ({device['max_input_channels']} channels)")
        
        return True
    except Exception as e:
        print(f"❌ Audio device detection failed: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("Sonic Halo - Cross-Platform Compatibility Test")
    print("=" * 60)
    
    tests = [
        test_platform_detection,
        test_core_dependencies,
        test_cross_platform_modules,
        test_platform_specific,
        test_audio_device_detection
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            failed += 1
        print()
    
    print("=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed! Sonic Halo should work on this platform.")
    else:
        print("⚠️  Some tests failed. Check the output above for issues.")
        print("You may need to install additional dependencies.")
    
    print("=" * 60)
    
    return failed == 0

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
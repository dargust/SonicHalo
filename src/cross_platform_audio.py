"""
Cross-platform audio capture utilities
"""
import logging
import sys
import subprocess

ON_WINDOWS = sys.platform.startswith('win')
ON_LINUX = sys.platform.startswith('linux')
ON_MACOS = sys.platform.startswith('darwin')

class LinuxAudioCapture:
    """Linux-specific audio capture utilities"""
    
    @staticmethod
    def get_pulseaudio_monitor_devices():
        """Get PulseAudio monitor devices for system audio capture"""
        devices = []
        try:
            # Run pactl to list sources
            result = subprocess.run(['pactl', 'list', 'short', 'sources'], 
                                  capture_output=True, text=True, check=True)
            
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        device_name = parts[1]
                        # Monitor devices end with .monitor
                        if device_name.endswith('.monitor'):
                            devices.append({
                                'name': device_name,
                                'description': parts[3] if len(parts) > 3 else device_name,
                                'type': 'monitor'
                            })
            
            logging.info(f"Found {len(devices)} PulseAudio monitor devices")
            return devices
            
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logging.warning(f"Could not get PulseAudio devices: {e}")
            return []
    
    @staticmethod
    def get_alsa_loopback_devices():
        """Get ALSA loopback devices"""
        devices = []
        try:
            # Check if snd-aloop module is loaded
            result = subprocess.run(['lsmod'], capture_output=True, text=True, check=True)
            if 'snd_aloop' not in result.stdout:
                logging.info("ALSA loopback module (snd-aloop) not loaded")
                return devices
            
            # Look for loopback devices in /proc/asound/cards
            with open('/proc/asound/cards', 'r') as f:
                content = f.read()
                
            for line in content.split('\n'):
                if 'Loopback' in line:
                    # Extract card number and name
                    parts = line.split()
                    if len(parts) >= 3:
                        card_num = parts[0]
                        devices.append({
                            'name': f'hw:{card_num}',
                            'description': f'ALSA Loopback {card_num}',
                            'type': 'loopback'
                        })
            
            logging.info(f"Found {len(devices)} ALSA loopback devices")
            return devices
            
        except (subprocess.CalledProcessError, FileNotFoundError, IOError) as e:
            logging.warning(f"Could not get ALSA loopback devices: {e}")
            return []
    
    @staticmethod
    def setup_pulseaudio_loopback():
        """Set up PulseAudio loopback if not present"""
        try:
            # Load null sink for loopback
            subprocess.run(['pactl', 'load-module', 'module-null-sink', 
                          'sink_name=sonic_halo_null', 'sink_properties=device.description="Sonic_Halo_Null"'], 
                         check=True, capture_output=True)
            
            # Load loopback from null sink monitor to default sink
            subprocess.run(['pactl', 'load-module', 'module-loopback', 
                          'source=sonic_halo_null.monitor', 'latency_msec=1'], 
                         check=True, capture_output=True)
            
            logging.info("PulseAudio loopback set up successfully")
            return True
            
        except subprocess.CalledProcessError as e:
            logging.warning(f"Could not set up PulseAudio loopback: {e}")
            return False

class MacOSAudioCapture:
    """macOS-specific audio capture utilities"""
    
    @staticmethod
    def get_blackhole_devices():
        """Get BlackHole virtual audio devices"""
        devices = []
        try:
            import sounddevice as sd
            all_devices = sd.query_devices()
            
            for i, device in enumerate(all_devices):
                if ('blackhole' in device['name'].lower() and 
                    device['max_input_channels'] > 0):
                    devices.append({
                        'index': i,
                        'name': device['name'],
                        'description': device['name'],
                        'type': 'virtual'
                    })
            
            logging.info(f"Found {len(devices)} BlackHole devices")
            return devices
            
        except Exception as e:
            logging.warning(f"Could not get BlackHole devices: {e}")
            return []
    
    @staticmethod
    def get_soundflower_devices():
        """Get Soundflower virtual audio devices"""
        devices = []
        try:
            import sounddevice as sd
            all_devices = sd.query_devices()
            
            for i, device in enumerate(all_devices):
                if ('soundflower' in device['name'].lower() and 
                    device['max_input_channels'] > 0):
                    devices.append({
                        'index': i,
                        'name': device['name'],
                        'description': device['name'],
                        'type': 'virtual'
                    })
            
            logging.info(f"Found {len(devices)} Soundflower devices")
            return devices
            
        except Exception as e:
            logging.warning(f"Could not get Soundflower devices: {e}")
            return []

def get_system_audio_devices():
    """Get system audio capture devices for the current platform"""
    devices = []
    
    if ON_LINUX:
        # Get PulseAudio monitor devices
        devices.extend(LinuxAudioCapture.get_pulseaudio_monitor_devices())
        # Get ALSA loopback devices
        devices.extend(LinuxAudioCapture.get_alsa_loopback_devices())
        
    elif ON_MACOS:
        # Get BlackHole devices
        devices.extend(MacOSAudioCapture.get_blackhole_devices())
        # Get Soundflower devices
        devices.extend(MacOSAudioCapture.get_soundflower_devices())
        
    elif ON_WINDOWS:
        # Windows system audio is handled by WASAPI in the main code
        pass
    
    return devices

def setup_system_audio_capture():
    """Set up system audio capture for the current platform"""
    if ON_LINUX:
        return LinuxAudioCapture.setup_pulseaudio_loopback()
    elif ON_MACOS:
        logging.info("macOS system audio capture requires BlackHole or Soundflower to be installed")
        return True
    elif ON_WINDOWS:
        logging.info("Windows system audio capture uses WASAPI loopback")
        return True
    else:
        logging.warning("System audio capture not supported on this platform")
        return False
# refactored_audio_visualizer.py
import sys
import numpy as np
import sounddevice as sd
# Add PyAudioWPatch for WASAPI loopback support
try:
    import pyaudiowpatch as pyaudio
    WASAPI_AVAILABLE = True
except ImportError:
    WASAPI_AVAILABLE = False
    import pyaudio
    
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import QOpenGLWidget
from OpenGL.GL import *
import ctypes, logging, json, os
import platformdirs.windows
import time
import asyncio
from winnotifyicon import TaskbarIcon


# --- Custom logging level for SETTINGS ---
SETTINGS_LEVEL = 15  # Between INFO (20) and WARNING (30)
logging.addLevelName(SETTINGS_LEVEL, "SETTINGS")

def settings_log(self, message, *args, **kwargs):
    if self.isEnabledFor(SETTINGS_LEVEL):
        self._log(SETTINGS_LEVEL, message, args, **kwargs)
logging.Logger.settings = settings_log

logging.basicConfig(level=SETTINGS_LEVEL,
                    format="{levelname} - {message}",
                    style="{")

logger = logging.getLogger()

ON_WINDOWS = sys.platform.startswith('win')
ON_LINUX = sys.platform.startswith('linux')

if ON_WINDOWS:
    try:
        from winsdk.windows.media.control import \
            GlobalSystemMediaTransportControlsSessionManager as MediaManager
    except ImportError:
        MediaManager = None
else:
    MediaManager = None

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

DEBUG = True

logging.info("Sonic Halo: Real-Time Audio Visualizer by Dacus")
# Major.Minor.Patch.Build
VERSION = "0.9.3.1"
logging.info(f"Version: {VERSION}")
logging.info(f"System platform: {sys.platform}")

# === Constants === #
class SettingsManager:
    def __init__(self):
        self.settings = {
            "WINDOW_WIDTH": 400,
            "WINDOW_HEIGHT": 400,
            "WINDOW_POS_X": 100,
            "WINDOW_POS_Y": 100,
            "BAR_COUNT": 28,
            "SAMPLE_RATE": 48000,
            "CHUNK": 2048,
            "UPDATE_INTERVAL": 16,
            "BAR_THICKNESS": 0.04,
            "MIN_BAR_HEIGHT": 0.03,
            "MIN_FREQ": 50,
            "MAX_FREQ": 12000,
            "VOCAL_MIN": 200,
            "VOCAL_MAX": 2200,
            "HARMONIC_THRESHOLD": 0.1,
            "MIN_MAX_SEEN": 10.0,
            "ROUNDED_CAPS": False,
            "MAX_OPACITY": 0.4,
            "OUTLINE_SCALE": 0.0,
            "ARC_POINT_COUNT": 3,
            "MARKER_OFFSET": 0.3,
            "LOW_COLOUR": (0.00, 0.15, 0.31),
            "MID_COLOUR": (0.08, 0.41, 0.63),
            "HIGH_COLOUR": (0.99, 0.81, 0.63),
            "USER_AUDIO_DEVICE": None,  # e.g. "CABLE Output (VB-Audio Virtual Cable)"
            "BPM_DETECTION_ENABLED": False,  # Toggle for BPM detection feature
            "USE_SYSTEM_AUDIO": True,  # Use WASAPI loopback to capture system audio output
            "SQUARE_MODE": False,  # Toggle between circular and linear bottom display
            "BAR_MAX_HEIGHT": 0.5,  # Maximum height bars can reach (0.1-1.0)
            "HEIGHT_SENSITIVITY": 0.5,  # Multiplier for bar height sensitivity (0.1-5.0)
            "BASE_ROTATION_SPEED": 0.001,  # Base rotation speed (constant rotation)
            "AUDIO_ROTATION_SPEED": 0.8,  # Audio reactive rotation speed multiplier
            "INCLUDE_MIC_INPUT": False,
            "MIC_DEVICE": None,
            }
        self.default_settings = self.settings.copy()

        self.settings_file_dir = platformdirs.user_data_dir("Sonic Halo", "Dacus")

        # Load settings from file or use defaults
        self.settings = self.load_settings_from_file()
        logger.settings("settings:")
        for k,v in self.settings.items():
            logger.settings(f"    {k} = {v}")

    def save_settings_to_file(self, settings, filename="settings.json"):
        try:
            if not os.path.exists(self.settings_file_dir):
                os.makedirs(self.settings_file_dir)
            filename = os.path.join(self.settings_file_dir, filename)

            with open(filename, "w") as f:
                json.dump(settings, f, indent=4)
            logging.info(f"Settings saved to {filename}")
        except Exception as e:
            logging.error(f"Failed to save settings: {e}")

    def load_settings_from_file(self, filename="settings.json"):
        filename = os.path.join(self.settings_file_dir, filename)
        if not os.path.exists(filename):
            logging.warning(f"Settings file {filename} not found. Using defaults.")
            return self.settings
        try:
            with open(filename, "r") as f:
                loaded = json.load(f)
            self.settings.update(loaded)
            logging.info(f"Settings loaded from {filename}")
        except Exception as e:
            logging.error(f"Failed to load settings: {e}")
        return self.settings

# === Utility Functions === #
def get_weighted_band_edges(min_freq, max_freq, band_count, low_bias=2.5):
    t = np.linspace(0, 1, band_count + 1)
    t_weighted = t ** low_bias
    return min_freq * (max_freq / min_freq) ** t_weighted

def make_window_clickthrough(window):
    try:
        hwnd = int(window.winId())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        style |= 0x80000 | 0x20
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
    except Exception as e:
        logging.error(f"Failed to make window clickthrough: {e}")


def make_window_clickable(window):
    try:
        hwnd = int(window.winId())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        style &= ~(0x80000 | 0x20)
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
    except Exception as e:
        logging.error(f"Failed to make window clickable: {e}")


def pid_controller(setpoint, pv, kp, ki, kd, previous_error, integral, dt):
    try:
        error = setpoint - pv
        integral += error * dt
        derivative = (error - previous_error) / dt
        control = kp * error + ki * integral + kd *derivative
        return control, error, integral
    except ValueError:
        return 0.0, 0.0, 0.0

class SongPoller(QtCore.QThread):
    song_changed = QtCore.pyqtSignal(str)

    def __init__(self, poll_interval=2.0, parent=None):
        super().__init__(parent)
        self.poll_interval = poll_interval
        self._running = True
        self._last_song = None
        self._loop = None
        self._session_manager = None
        self._session = None

    def run(self):
        if ON_WINDOWS and MediaManager is not None:
            import asyncio
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._session_manager = self._loop.run_until_complete(MediaManager.request_async())
                self._session = self._session_manager.get_current_session()
            except Exception as e:
                logging.debug(f"SongPoller: Failed to get session manager: {e}")
                self._session_manager = None
                self._session = None

        while self._running:
            song = self.get_current_song()
            if song and song != self._last_song:
                self._last_song = song
                self.song_changed.emit(song)
            self.msleep(int(self.poll_interval * 1000))

    def stop(self):
        self._running = False

    def get_current_song(self):
        if ON_WINDOWS and MediaManager is not None and self._loop:
            try:
                # Always get the current session (it may change)
                if self._session_manager is not None:
                    self._session = self._session_manager.get_current_session()
                if self._session:
                    info = self._loop.run_until_complete(self._session.try_get_media_properties_async())
                    artist = getattr(info, "artist", "")
                    title = getattr(info, "title", "")
                    if title:
                        return f"{artist} - {title}" if artist else title
            except Exception as e:
                logging.debug(f"Song poll error: {e}")
                self._session = None
        return None

class DevicesMap:
    VIRTUAL_CABLE = "CABLE Output (VB-Audio Virtual Cable)"
    STEREO_MIX = "Stereo Mix"
    device_priority = [STEREO_MIX, VIRTUAL_CABLE]
    def __init__(self, user_device=None):
        self.user_device = user_device
        self.device_priority = [user_device] + self.device_priority if user_device else self.device_priority

class AudioProcessor:
    init_bar_count = 64 # settings["BAR_COUNT"]
    def __init__(self, settings=None):
        logging.info("Initialising AudioProcessor")
        self.settings = settings if settings else {}
        self.amps = np.zeros(self.init_bar_count)
        self.smoothed_amps = np.zeros(self.init_bar_count)
        self.fall_velocity = np.zeros(self.init_bar_count)
        
        # buffers for optional mixing of WASAPI + mic
        self.wasapi_buffer = None
        self.mic_buffer = None
        self.last_wasapi_ts = 0.0
        self.last_mic_ts = 0.0

        # Initialize audio capture based on settings
        if self.settings.get("USE_SYSTEM_AUDIO", False):
            self.device_index, self.use_wasapi = self.find_wasapi_loopback_device()
        else:
            self.device_index = self.find_device()
            self.use_wasapi = False
            
        self.max_seen = 10.0
        self.highlighted_idx = None
        self.highlighted_freq = []
        self.is_harmonic = False
        self.control = 0
        self.error = 0
        self.integral = 0
        self.delta = 16
        self.bpm_peak_direction = 0
        self.bpm_timestamps = []
        self.bpm = 0.0
        
        # PyAudio stream for WASAPI loopback
        self.pyaudio_instance = None
        self.pyaudio_stream = None

    def find_wasapi_loopback_device(self):
        """Find WASAPI loopback device for system audio capture"""
        if not WASAPI_AVAILABLE:
            logging.warning("PyAudioWPatch not available. Falling back to regular microphone input.")
            return self.find_device(), False
            
        try:
            p = pyaudio.PyAudio()
            
            # Try to get default WASAPI loopback device
            try:
                wasapi_info = p.get_default_wasapi_loopback()
                if wasapi_info:
                    logging.info(f"Found WASAPI loopback device: {wasapi_info['name']}")
                    p.terminate()
                    return wasapi_info['index'], True
            except:
                pass
                
            # Fallback: look for loopback devices manually
            logging.info("Searching for WASAPI loopback devices...")
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if (info['maxInputChannels'] > 0 and 
                    "loopback" in info['name'].lower()):
                    logging.info(f"Found loopback device: {info['name']}")
                    p.terminate()
                    return i, True
                    
            # Try output devices for loopback
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if (info['maxOutputChannels'] > 0 and 
                    'wasapi' in info['name'].lower() and
                    ('speakers' in info['name'].lower() or 
                     'headphones' in info['name'].lower() or
                     'audio' in info['name'].lower())):
                    logging.info(f"Trying output device for loopback: {info['name']}")
                    p.terminate()
                    return i, True
                    
            p.terminate()
            logging.warning("No WASAPI loopback device found. Falling back to regular input.")
            return self.find_device(), False
            
        except Exception as e:
            logging.error(f"Error finding WASAPI device: {e}")
            return self.find_device(), False

    def find_device(self):
        logging.info("Attempting to find audio input device, use settings USER_AUDIO_DEVICE to specify")
        devices = sd.query_devices()
        # Try priority devices first
        device_map = DevicesMap()
        for preferred in device_map.device_priority:
            for i, dev in enumerate(devices):
                if preferred in dev['name'] and dev['max_input_channels'] > 0:
                    logging.info(f"Using audio device: {dev['name']}")
                    return i
        # Fallback: first device with input channels
        #for i, dev in enumerate(devices):
        #    if dev['max_input_channels'] > 0:
        #        return i

        # Fallback: return None
        return None

    def analyze_chunk(self, indata, frames, time_info, status, source='mic'):
        """
        Unified analysis entry. 'source' may be 'wasapi' or 'mic'.
        When both buffers are available and settings allow, mix them.
        """
        try:
            # Convert incoming data to mono numpy array regardless of origin
            if source == 'wasapi' and isinstance(indata, (bytes, bytearray)):
                samples = np.frombuffer(indata, dtype=np.int16).astype(np.float32) / 32768.0
                if len(samples) % 2 == 0:
                    mono = np.mean(samples.reshape(-1, 2), axis=1)
                else:
                    mono = samples
            else:
                arr = np.array(indata)
                mono = np.mean(arr, axis=1) if arr.ndim > 1 else arr

            now = time.time()
            if source == 'wasapi':
                self.wasapi_buffer = mono
                self.last_wasapi_ts = now
            elif source == 'mic':
                self.mic_buffer = mono
                self.last_mic_ts = now

            mixed = None
            mix_allowed = self.settings.get("INCLUDE_MIC_INPUT", False)
            if mix_allowed and self.wasapi_buffer is not None and self.mic_buffer is not None:
                minlen = min(len(self.wasapi_buffer), len(self.mic_buffer))
                if minlen > 0:
                    mixed = (self.wasapi_buffer[:minlen] + self.mic_buffer[:minlen]) * 0.5

            if mixed is None:
                mono_for_analysis = self.wasapi_buffer if source == 'wasapi' else self.mic_buffer
            else:
                mono_for_analysis = mixed

            if mono_for_analysis is None or len(mono_for_analysis) == 0:
                return

            mono = mono_for_analysis
            N = 4096 * 2
            if len(mono) < N:
                mono = np.pad(mono, (0, N - len(mono)))
            else:
                mono = mono[:N]

            fft = np.abs(np.fft.rfft(mono, n=N))
            freqs = np.fft.rfftfreq(N, d=1 / self.settings["SAMPLE_RATE"])
        except Exception as e:
            logging.debug(f"analyze_chunk error: {e}")
            return

        #band_edges = get_weighted_band_edges(settings["MIN_FREQ"], settings["MAX_FREQ"], chunk_bar_count, low_bias=0.8)
        band_edges = get_weighted_band_edges(self.settings["MIN_FREQ"], self.settings["MAX_FREQ"], self.init_bar_count, low_bias=0.8)
        band_centers = np.sqrt(band_edges[:-1] * band_edges[1:])
        bin_indices = np.digitize(freqs, band_edges) - 1

        #amps = np.array([
        #    np.mean(fft[bin_indices == i]) if np.any(bin_indices == i) else 0
        #    for i in range(self.init_bar_count) # chunk_bar_count)
        #])
        valid_bins = (bin_indices >= 0) & (bin_indices < self.init_bar_count)
        amps_sum = np.bincount(bin_indices[valid_bins], weights=fft[valid_bins], minlength=self.init_bar_count)
        amps_count = np.bincount(bin_indices[valid_bins], minlength=self.init_bar_count)
        amps = np.divide(amps_sum, amps_count, out=np.zeros_like(amps_sum), where=amps_count != 0)

        amps *= np.sqrt(band_centers / band_centers[0])

        if np.max(amps) < 1e-4:
            amps = np.zeros(self.init_bar_count) # chunk_bar_count)

        max_fft = np.max(amps)
        proportional = 2.0 # if max_fft > self.max_seen else 2.0
        self.control, self.error, self.integral = pid_controller(max_fft, self.max_seen, proportional, 0.0, 0.02, self.error, self.integral, self.delta/1000)
        self.max_seen += self.control * self.delta/1000 # max_fft
        self.max_seen = max(self.max_seen, self.settings["MIN_MAX_SEEN"])
        self.min_seen = np.min(amps)

        # Apply height sensitivity and max height controls
        amps = np.clip(amps / self.max_seen, 0, 1)
        # Apply sensitivity scaling, the higher the amps the harder it is to increase
        amps = amps * self.settings["HEIGHT_SENSITIVITY"] if self.settings["HEIGHT_SENSITIVITY"] >= 1.0 else amps ** (2.0 - self.settings["HEIGHT_SENSITIVITY"])
        amps = np.clip(amps, 0, self.settings["BAR_MAX_HEIGHT"])
        
        vocal_indices = np.where((band_centers >= self.settings["VOCAL_MIN"]) & (band_centers <= self.settings["VOCAL_MAX"]))[0]

        if len(vocal_indices) and np.max(amps[vocal_indices]) > 0.1:
            self.detect_harmonics(amps, band_centers)
            self.highlighted_idx = vocal_indices[np.argmax(amps[vocal_indices])]
        else:
            self.highlighted_idx = None

        if self.settings.get("BPM_DETECTION_ENABLED", True):
            self.bpm_detect()
        else:
            # Reset BPM when detection is disabled
            self.bpm = 0

        self.amps = amps.copy()
        #self.highlighted_freq, self.peak_conf = self.hps_pitch_detection_with_confidence(fft, SAMPLE_RATE, N, 4)
        #self.highlighted_freq = self.find_peak_frequency(fft, freqs, band_edges, band_centers)
        #self.detect_harmonics(amps, band_centers)

    def bpm_detect(self):
        # Enhanced BPM detection that tries to identify downbeats and bar structure
        deadzone = 32  # Sensitivity for peak detection
        now = time.time()

        if not hasattr(self, "locked_bpm"):
            self.locked_bpm = None
            self.locked_bpm_time = 0
            self.beat_strengths = []  # Track the strength of each detected beat
            self.downbeat_candidates = []  # Track potential downbeats

        if self.bpm_peak_direction == 0:
            if self.error > deadzone:  # rising edge
                self.bpm_peak_direction = 1
                self.bpm_timestamps.append(now)
                self.beat_strengths.append(self.error)  # Store beat strength
                
                # Keep lists manageable
                if len(self.bpm_timestamps) > 16:
                    self.bpm_timestamps.pop(0)
                    self.beat_strengths.pop(0)
                
                if len(self.bpm_timestamps) < 6:
                    return 0

                # Identify potential downbeats (stronger beats)
                self.identify_downbeats()
                
                # Calculate intervals using both all beats and downbeat candidates
                all_intervals = np.diff(self.bpm_timestamps)
                downbeat_intervals = np.diff(self.downbeat_candidates) if len(self.downbeat_candidates) > 1 else []
                
                # Try downbeat intervals first (they should give us bar-level tempo)
                detected_bpm = 0
                if len(downbeat_intervals) >= 2:
                    detected_bpm = self.calculate_bpm_from_intervals(downbeat_intervals, "downbeats")
                
                # Fallback to all beats if downbeat detection fails
                if detected_bpm == 0 and len(all_intervals) >= 3:
                    detected_bpm = self.calculate_bpm_from_intervals(all_intervals, "all_beats")
                
                if detected_bpm == 0:
                    return 0

                # --- BPM Locking Logic ---
                def is_multiple_or_submultiple(new_bpm, locked_bpm, tol=0.05):
                    ratio = new_bpm / locked_bpm
                    for factor in [0.25, 0.5, 1, 2, 3, 4]:  # Added 0.25 for bar-level detection
                        if abs(ratio - factor) < tol:
                            return factor
                    return None

                if self.locked_bpm is None or (now - self.locked_bpm_time > 12):
                    self.locked_bpm = detected_bpm
                    self.locked_bpm_time = now
                    self.bpm = detected_bpm
                else:
                    factor = is_multiple_or_submultiple(detected_bpm, self.locked_bpm)
                    if factor is not None:
                        # If detecting bar-level tempo, multiply to get beat-level
                        if factor == 0.25:
                            self.bpm = self.locked_bpm
                        elif factor == 0.5:
                            self.bpm = self.locked_bpm  
                        else:
                            self.bpm = self.locked_bpm
                        self.locked_bpm_time = now
                    else:
                        if now - self.locked_bpm_time > 12:
                            self.locked_bpm = detected_bpm
                            self.locked_bpm_time = now
                            self.bpm = detected_bpm
                        else:
                            self.bpm = self.locked_bpm

        elif self.bpm_peak_direction == 1:
            if self.error < -deadzone / 8:  # falling edge
                self.bpm_peak_direction = 0

    def identify_downbeats(self):
        """Identify beats that are likely to be downbeats based on strength"""
        if len(self.beat_strengths) < 4:
            return
        
        self.downbeat_candidates = []
        
        # Look for beats that are significantly stronger than their neighbors
        for i in range(2, len(self.beat_strengths) - 1):
            current_strength = self.beat_strengths[i]
            
            # Compare with neighbors
            prev_avg = np.mean(self.beat_strengths[max(0, i-2):i])
            next_avg = np.mean(self.beat_strengths[i+1:min(len(self.beat_strengths), i+3)])
            neighbor_avg = (prev_avg + next_avg) / 2
            
            # If this beat is significantly stronger, it might be a downbeat
            if current_strength > neighbor_avg * 1.25:  # 25% stronger threshold
                self.downbeat_candidates.append(self.bpm_timestamps[i])

    def calculate_bpm_from_intervals(self, intervals, source_type):
        """Calculate BPM from a set of intervals with improved filtering"""
        # Filter realistic intervals
        if source_type == "downbeats":
            # Downbeats represent bars, so intervals should be longer
            intervals = intervals[(intervals > 1.0) & (intervals < 8.0)]
        else:
            # Regular beats
            intervals = intervals[(intervals > 0.3) & (intervals < 2.0)]
            
        if len(intervals) < 2:
            return 0

        # Use median instead of mode for more stable results
        median_interval = np.median(intervals)
        
        # Also check if intervals cluster around the median
        close_to_median = np.abs(intervals - median_interval) < 0.1
        if np.sum(close_to_median) < max(2, len(intervals) * 0.6):
            return 0  # Not enough consistent intervals
        
        # Calculate BPM
        if source_type == "downbeats":
            # Downbeats represent bars in 4/4 time, so multiply by 4
            detected_bpm = (60.0 / median_interval) * 4
        else:
            detected_bpm = 60.0 / median_interval
            
        # Realistic BPM range
        if detected_bpm < 60 or detected_bpm > 180:
            return 0
            
        return detected_bpm


    def find_peak_frequency(self, fft, freqs, band_edges, band_centers):
        if self.highlighted_idx is None:
            return None
        start, end = band_edges[self.highlighted_idx:self.highlighted_idx + 2]
        bins = np.where((freqs >= start) & (freqs < end))[0]
        if bins.size:
            return freqs[bins[np.argmax(fft[bins])]]
        return band_centers[self.highlighted_idx]

    def detect_harmonics(self, amps, band_centers):
        vocal_range = (band_centers >= self.settings["VOCAL_MIN"]) & (band_centers <= self.settings["VOCAL_MAX"])
        candidates = np.where((amps > 0.1) & vocal_range)[0]

        best_score = 0
        best_f0 = None
        self.highlighted_freq = []
        for idx in candidates:
            f0 = band_centers[idx]
            harmonics_found = 0
            total_strength = 0

            for h in range(2, 4):  # check 2nd–4th harmonics
                harmonic_freq = f0 / h
                if harmonic_freq < self.settings["VOCAL_MIN"] / 5:
                    continue
                harmonic_idx = np.argmin(np.abs(band_centers - harmonic_freq))
                if amps[harmonic_idx] > 0.1:
                    if amps[harmonic_idx] > amps[idx]: # discard if harmonic is more than candidate
                        continue
                    harmonics_found += 1
                    total_strength += amps[harmonic_idx]

            score = harmonics_found + total_strength # blend quantity + intensity
            if harmonics_found >= 2 and score > best_score and score > 2.0:
                best_score = score
                best_f0 = f0

        # Set result
        if best_f0:
            self.is_harmonic = True
        else:
            self.is_harmonic = False

    def hps_pitch_detection_with_confidence(self, magnitude_spectrum, sampling_rate, fft_size, num_harmonics=4, fmin=80, fmax=400):
        hps_spec = magnitude_spectrum.copy()
        for h in range(2, num_harmonics + 1):
            decimated = magnitude_spectrum[::h]
            hps_spec[:len(decimated)] *= decimated

        freqs = np.fft.rfftfreq(fft_size, 1.0 / sampling_rate)
        valid = (freqs >= fmin) & (freqs <= fmax)

        hps_valid = hps_spec[valid]
        if len(hps_valid) < 2:
            return None, 0.0

        peak_index = np.argmax(hps_valid)
        peak_freq = freqs[valid][peak_index]

        # Confidence as ratio of top two peaks
        sorted_vals = np.sort(hps_valid)[::-1]
        ratio = sorted_vals[0] / (sorted_vals[1] + 1e-6)
        confidence = np.clip((ratio - 1) / 2.0, 0.0, 1.0)

        return peak_freq, confidence


    def update_smoothed(self):
        for i in range(self.settings["BAR_COUNT"]):
            if self.amps[i] > self.smoothed_amps[i]:
                self.smoothed_amps[i] = self.amps[i]
                self.fall_velocity[i] = 0
            else:
                self.fall_velocity[i] += 0.003
                fall_amount = max(0.005, self.fall_velocity[i])
                self.smoothed_amps[i] = max(0, self.smoothed_amps[i] - fall_amount)

class GLVisualizer(QOpenGLWidget):
    def __init__(self, processor, parent=None, settings=None):
        logging.info("Initialising Visualiser")
        super().__init__(parent)
        self.settings = settings if settings else {}
        self.processor = processor
        self.rotation_offset = 0.0
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.timer = QtCore.QTimer(timeout=self.update)
        self.timer.start(settings["UPDATE_INTERVAL"])
        self.bar_opacity = settings["MAX_OPACITY"]
        self.peak_marker_angle = None
        self.peak_marker_opacity = 0.0
        self.elapsed_time = QtCore.QTime.currentTime()
        self.animated_bar_count = settings["BAR_COUNT"]
        self.animation_counter = 0
        self.debug_print_delay = 0 # int(1000 / UPDATE_INTERVAL)
        self.control = 0
        self.error = 0
        self.integral = 0
        self.max_radius = 0.2
        self.arc_point_count = settings["ARC_POINT_COUNT"]
        self.actual_col = 0.1
        self.min_max_error = [0.0, 0.0]
        self.peak_pid = 0.0
        self.current_song = ""
        self.song_show_time = 0
        self.song_fade_duration = 3.0  # seconds to show
        self.song_fade_steps = 20
        self.song_fade_step = 0
        self.song_fade_hold_steps = 20  # Number of steps to hold at full opacity
        self.song_fade_hold_step = 0
        self.song_fade_timer = QtCore.QTimer(self)
        self.song_fade_timer.timeout.connect(self._fade_song)

        # Load pixel font once - FIXED VERSION
        try:
            font_path = resource_path("media/Px437_IBM_VGA_8x14.ttf")  # Use forward slashes
            logging.debug(f"Loading font from {font_path}")
            font_id = QtGui.QFontDatabase.addApplicationFont(font_path)
            if font_id != -1:
                family = QtGui.QFontDatabase.applicationFontFamilies(font_id)[0]
                self.song_font = QtGui.QFont(family, 32)
            else:
                logging.error(f"Failed to load font from {font_path}")
                self.song_font = QtGui.QFont("Consolas", 32)  # Fallback font
        except Exception as e:
            logging.error(f"Error loading font: {e}")
            self.song_font = QtGui.QFont("Consolas", 32)  # Fallback font
        
        logging.debug(f"Using font: {self.song_font.family()}")

    def initializeGL(self):
        glEnable(GL_LINE_SMOOTH)
        glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        aspect = w / h if h != 0 else 1.0
        glOrtho(-aspect, aspect, -1.0, 1.0, -1.0, 1.0)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        paint_bar_count = self.settings["BAR_COUNT"]
        self.debug_print_delay += 1
        new_time = QtCore.QTime.currentTime()
        delta = self.elapsed_time.msecsTo(new_time)
        self.processor.delta = delta
        self.elapsed_time = new_time
        # to do later: if show_fps: print fps
        #if self.debug_print_delay >= int(1000 / self.settings["UPDATE_INTERVAL"]):
        #    print(f" ~fps: {int(1000 / delta):02d}"+" "*20, end="\r")
        #    self.debug_print_delay = 0
        self.processor.update_smoothed()
        glClearColor(0, 0, 0, 0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        amps = self.processor.smoothed_amps

        # Choose display mode based on SQUARE_MODE setting
        if self.settings["SQUARE_MODE"]:
            self.draw_linear_bars(amps, paint_bar_count)
            ring_bar_count = paint_bar_count  # Use same count for BPM indicator
        else:
            # Original circular display
            min_radius = 0.175 # 0.22
            outer_radius = min_radius+(self.processor.max_seen / 300) * (0.5 - min_radius)
            inner_radius = outer_radius - 0.02 # min_radius+(self.processor.max_seen / 300) * (0.5 - min_radius)
            performance_offset = 0 # min(delta - 16, 0)
            self.arc_point_count = max(self.settings["ARC_POINT_COUNT"] - performance_offset, 2)
            ring_bar_count = self.settings["ARC_POINT_COUNT"] * 2 # (BAR_COUNT * 2) - performance_offset
            if self.settings["OUTLINE_SCALE"] > 0.1:
                self.draw_ring(inner_radius-self.settings["OUTLINE_SCALE"]*0.01, outer_radius+0.03+self.settings["OUTLINE_SCALE"]*0.01, ring_bar_count*2, amps, outline=True)
            self.draw_ring(inner_radius, outer_radius+0.03, ring_bar_count*2, amps)

        bass_energy = np.prod(amps[:min(4, paint_bar_count)])
        # Calculate rotation with configurable speeds
        base_rotation = self.settings["BASE_ROTATION_SPEED"]
        audio_reactive_rotation = (self.processor.error/40000 + min(bass_energy * 0.1, 0.01)) * self.settings["AUDIO_ROTATION_SPEED"]
        self.rotation_offset += base_rotation + audio_reactive_rotation
        self.rotation_offset %= 2 * np.pi

        min_value = np.max(amps)

        peak_index = self.processor.highlighted_idx
        if peak_index:
            proportional = 2.0
            self.control, self.error, self.integral = pid_controller(peak_index, self.peak_pid, proportional, 0.0, 0.02, self.error, self.integral, delta/1000)
            self.peak_pid += self.control * delta/1000 # max_fft

        # Draw bars for circular mode or handle rotation for square mode
        if not self.settings["SQUARE_MODE"]:
            for i in range(self.animated_bar_count):
                shifted_index = (i + (self.rotation_offset * paint_bar_count / (2 * np.pi))) % paint_bar_count

                idx0 = int(np.floor(shifted_index))
                idx1 = (idx0 + 1) % paint_bar_count
                frac = shifted_index - idx0
                value = np.interp(frac, [0, 1], [amps[idx0], amps[idx1]]) * 1.00
                value = max(value, self.settings["MIN_BAR_HEIGHT"])
                min_value = max(value, min_value)
                angle = (2 * np.pi * i) / paint_bar_count + 1.5 * np.pi + self.rotation_offset

                # Scale color value based on the actual displayable range (0 to BAR_MAX_HEIGHT)
                # This ensures colors reach full range even when max height is limited
                color_value = min(value / self.settings["BAR_MAX_HEIGHT"], 1.0)
                
                r, g, b = self.interpolate_hsv_3stop(color_value, self.settings["LOW_COLOUR"], self.settings["MID_COLOUR"], self.settings["HIGH_COLOUR"], self.hsv_to_rgb)
                if peak_index and self.processor.is_harmonic:
                    blue_offset = 0
                    if abs(shifted_index - self.peak_pid) < 2:
                        blue_offset = (2 - abs(shifted_index - self.peak_pid)) / 3
                    #blue_offset = max(0,((abs(shifted_index - peak_index)/BAR_COUNT*2)))
                    b += blue_offset
                if self.settings["OUTLINE_SCALE"] > 0.1:
                    self.draw_rounded_polys(angle, value, (0.0, 0.0, 0.0, self.bar_opacity), (self.settings["BAR_THICKNESS"] / 2) + self.settings["OUTLINE_SCALE"] * 0.01)
                self.draw_rounded_polys(angle, value, (r*self.bar_opacity, g*self.bar_opacity, b*self.bar_opacity, self.bar_opacity), self.settings["BAR_THICKNESS"] / 2)
                #self.draw_bar(angle, value, (r*self.bar_opacity, g*self.bar_opacity, b*self.bar_opacity, self.bar_opacity))
        lowering = False
        #print(f"min_value: {min_value:.4f}, bar_opacity: {self.bar_opacity:.4f}, animated_bar_count: {self.animated_bar_count}/{paint_bar_count}    ", end="\r")
        if min_value > self.settings["MIN_BAR_HEIGHT"]:
            self.bar_opacity = self.settings["MAX_OPACITY"]
            self.last_valid_bar = QtCore.QTime.currentTime()
        else:
            if hasattr(self, 'last_valid_bar'):
                elapsed = self.last_valid_bar.msecsTo(QtCore.QTime.currentTime()) / 1000.0
                lowering = True
                fade_duration = 4
                if elapsed < fade_duration and elapsed > 4:
                    #self.bar_opacity = MAX_OPACITY * (1 - (elapsed / fade_duration))
                    self.bar_opacity = self.settings["MAX_OPACITY"] * (1 - max(0, elapsed - fade_duration / 2) / (fade_duration / 2))
                    self.animated_bar_count = int(paint_bar_count * (1 - max(0, (elapsed - fade_duration / 2) / (fade_duration / 2))))
                elif 0 <= elapsed <= 4:
                    pass
                else:
                    self.animated_bar_count = 0
                    self.bar_opacity = 0.0
            else:
                pass
        # Draw BPM indicator (adjust count based on mode)
        bpm_indicator_count = paint_bar_count if self.settings["SQUARE_MODE"] else ring_bar_count * 2
        self.draw_bpm_indicator(bpm_indicator_count)
        if not lowering or np.min(amps) > self.settings["MIN_BAR_HEIGHT"] / 10:
            if self.animated_bar_count < paint_bar_count:
                self.animation_counter += 1
                if self.animation_counter >= 4:
                    self.animation_counter = 0
                    self.animated_bar_count += 1
                #print(self.animated_bar_count / BAR_COUNT)
                self.bar_opacity = (self.animated_bar_count / paint_bar_count) * self.settings["MAX_OPACITY"]
            else:
                self.animation_counter = 0
        #print(f"{self.animated_bar_count}, {self.animation_counter}, {min_value}, {np.min(amps)}")
        #self.draw_peak_circle()
        # Draw song overlay if needed
        if self.current_song:
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            # Dynamically scale font size based on window height (or width)
            base_size = 12
            scale = self.height() / 400  # 400 is your default window height
            font_size = max(12, int(base_size * scale))
            font = QtGui.QFont(self.song_font.family(), font_size)
            painter.setFont(font)
            # ...existing code for fading...
            alpha = 255
            if self.song_fade_step > 0:
                alpha = int(255 * (1 - self.song_fade_step / self.song_fade_steps))
            rect = self.rect()
            # Draw black outline by drawing text multiple times with offset
            outline_color = QtGui.QColor(0, 0, 0, alpha)
            for dx in [-2, -1, 0, 1, 2]:
                for dy in [-2, -1, 0, 1, 2]:
                    if dx == 0 and dy == 0:
                        continue
                    painter.setPen(outline_color)
                    painter.drawText(rect.translated(dx, dy), QtCore.Qt.AlignCenter, self.current_song)
            # Draw main text in white
            color = QtGui.QColor(255, 255, 255, alpha)
            painter.setPen(color)
            painter.drawText(rect, QtCore.Qt.AlignCenter, self.current_song)
            painter.end()
    
    def draw_bpm_indicator(self, segments):
        bpm = self.processor.bpm
        if bpm > 0:
            beat_interval = 60.0 / bpm

            # --- Smooth phase reset logic ---
            # Initialize persistent attributes
            if not hasattr(self, "bpm_pulse_phase"):
                self.bpm_pulse_phase = 0.0
            if not hasattr(self, "bpm_pulse_phase_target"):
                self.bpm_pulse_phase_target = 0.0
            if not hasattr(self, "last_bpm"):
                self.last_bpm = bpm

            # If BPM changes, set a new target phase (reset to 0)
            if bpm != self.last_bpm:
                self.last_bpm = bpm
                # reset at a quarter phase
                self.bpm_pulse_phase_target = 1  # Target phase is reset

            # Advance both phases by frame time
            delta_sec = self.processor.delta / 1000.0
            self.bpm_pulse_phase += delta_sec
            self.bpm_pulse_phase_target += delta_sec

            # Wrap phases
            while self.bpm_pulse_phase > beat_interval:
                self.bpm_pulse_phase -= beat_interval
            while self.bpm_pulse_phase_target > beat_interval:
                self.bpm_pulse_phase_target -= beat_interval

            # Smoothly interpolate phase toward target (lerp)
            interp_speed = 0.15  # 0=instant, 1=never; lower is faster
            self.bpm_pulse_phase += (self.bpm_pulse_phase_target - self.bpm_pulse_phase) * interp_speed

            # Pulse value: 0 at start, 1 at beat, back to 0
            pulse = 0.5 * (1 - np.cos(2 * np.pi * self.bpm_pulse_phase / beat_interval))

            # Draw a pulsing polygon (hexagon) using OpenGL
            center_x, center_y = 0.0, 0.0  # OpenGL center
            base_radius = 0.1  # relative to OpenGL coordinates
            pulse_radius = base_radius * (1 + 0.25 * pulse)
            sides = segments  # Hexagon

            # Outline
            if self.settings["OUTLINE_SCALE"] >= 0.1:
                glColor4f(0.0, 0.0, 0.0, self.bar_opacity)
                glBegin(GL_POLYGON)
                for i in range(sides):
                    angle = 2 * np.pi * i / sides
                    x = center_x + (pulse_radius + self.settings["OUTLINE_SCALE"] * 0.01) * np.cos(angle)
                    y = center_y + (pulse_radius + self.settings["OUTLINE_SCALE"] * 0.01) * np.sin(angle)
                    glVertex2f(x, y)
                glEnd()

            # Set color and alpha (match bar_opacity)
            r, g, b = self.interpolate_hsv_3stop(self.actual_col, self.settings["LOW_COLOUR"], self.settings["MID_COLOUR"], self.settings["HIGH_COLOUR"], self.hsv_to_rgb)
            glColor4f(r*self.bar_opacity, g*self.bar_opacity, b*self.bar_opacity, self.bar_opacity)
            glLineWidth(2)
            glBegin(GL_POLYGON)
            for i in range(sides):
                angle = 2 * np.pi * i / sides
                x = center_x + pulse_radius * np.cos(angle)
                y = center_y + pulse_radius * np.sin(angle)
                glVertex2f(x, y)
            glEnd()


    def draw_ring(self, inner_radius, outer_radius, segments, amps, outline=False):
        ring_bar_count = self.settings["BAR_COUNT"]
        glBegin(GL_TRIANGLE_STRIP)
        #print(self.processor.error)
        if self.processor.error > self.min_max_error[1]:
            self.min_max_error[1] = self.processor.error
        elif self.processor.error < self.min_max_error[0]:
            self.min_max_error[0] = self.processor.error
        self.min_max_error = [self.min_max_error[0]*0.999, self.min_max_error[1]*0.999]
        target_col =  np.interp(self.processor.error, self.min_max_error, [0,1])
        delta = self.actual_col - target_col
        reaction = 0.02 if delta > 0 else 0.3
        self.actual_col -= delta * reaction
        #print(target_col, self.actual_col)
        #r, g, b = self.hsv_to_rgb(self.actual_col, 1.0, 1.0) if not outline else (0.0, 0.0, 0.0)
        r, g, b = self.interpolate_hsv_3stop(self.actual_col, self.settings["LOW_COLOUR"], self.settings["MID_COLOUR"], self.settings["HIGH_COLOUR"], self.hsv_to_rgb)
        if outline:
            glColor4f(0.0, 0.0, 0.0, self.bar_opacity)
        else:
            glColor4f(r*self.bar_opacity, g*self.bar_opacity, b*self.bar_opacity, self.bar_opacity)
        for i in range(segments + 1):
            if i == segments:
                i = 0
            angle = -(2 * np.pi * i / segments) + np.pi
            x = np.cos(angle)
            y = np.sin(angle)
            frac = (ring_bar_count / (segments + 1)) * i
            l_interp = np.sqrt(np.interp(frac, np.arange(len(amps)), amps))
            l_interp = max(l_interp, self.settings["MIN_BAR_HEIGHT"])
            # Outer edge vertex
            glVertex2f(x * (outer_radius + l_interp / 30), y * (outer_radius + l_interp / 30))
            # Inner edge vertex
            glVertex2f(x * (inner_radius + l_interp / 30), y * (inner_radius + l_interp / 30))
        glEnd()

    def draw_bar(self, angle, value, color):
        base = 0.3 - value * 0.05
        tip = base + value * 0.5
        x0, y0 = np.sin(angle) * base, np.cos(angle) * base
        x1, y1 = np.sin(angle) * tip, np.cos(angle) * tip
        outline_x0, outline_y0 = np.sin(angle) * base * 0.98, np.cos(angle) * base * 0.98
        outline_x1, outline_y1 = np.sin(angle) * tip * 1.02, np.cos(angle) * tip * 1.010
        xtip, ytip = np.sin(angle) * (tip + 0.025), np.cos(angle) * (tip + 0.025)
        outline_xtip, outline_ytip = np.sin(angle) * (tip + 0.03), np.cos(angle) * (tip + 0.035) 
        
        if self.settings["ROUNDED_CAPS"]:
            self.draw_rounded_bar(x0, y0, x1, y1, angle, color, value)
        else:
            dx, dy = self.settings["BAR_THICKNESS"] / 2 * np.cos(-angle), self.settings["BAR_THICKNESS"] / 2 * np.sin(-angle)
            outline_dx, outline_dy = (self.settings["BAR_THICKNESS"] / 2 * np.cos(-angle)) * self.settings["OUTLINE_SCALE"], (self.settings["BAR_THICKNESS"] / 2 * np.sin(-angle)) * self.settings["OUTLINE_SCALE"]
            #outline_dx, outline_dy = BAR_THICKNESS / 2 * np.cos(-angle) * OUTLINE_SCALE, BAR_THICKNESS / 2 * np.sin(-angle) * OUTLINE_SCALE

            vertices = [
                (x0 - dx, y0 - dy), (x0 + dx, y0 + dy),
                (x1 + dx, y1 + dy), (xtip, ytip), (x1 - dx, y1 - dy),
                
            ]
            outline_vertices = [
                (outline_x0 - outline_dx, outline_y0 - outline_dy), (outline_x0 + outline_dx, outline_y0 + outline_dy),
                (outline_x1 + outline_dx, outline_y1 + outline_dy), (outline_xtip, outline_ytip), (outline_x1 - outline_dx, outline_y1 - outline_dy),
            ]

            if self.settings["OUTLINE_SCALE"] >= 1:
                glBegin(GL_POLYGON)
                glColor4f(0.0, 0.0, 0.0, self.bar_opacity)
                for x, y in outline_vertices:
                    glVertex2f(x, y)
                glEnd()

            glBegin(GL_POLYGON)
            glColor4f(*color)
            for x, y in vertices:
                glVertex2f(x, y)
            glEnd()

    def draw_rounded_polys(self, angle, value, color, radius):
        base = 0.3 - value * 0.05
        tip = base + value * 0.5
        dx = radius * np.cos(-angle)
        dy = radius * np.sin(-angle)
        peak_dx = radius * np.cos(-angle) * (1+value*2.25)
        peak_dy = radius * np.sin(-angle) * (1+value*2.25)
        peak_radius = radius * (1+value*2)
        x0, y0 = np.sin(angle) * base, np.cos(angle) * base
        x1, y1 = np.sin(angle) * tip, np.cos(angle) * tip
        bottom_left = (x0 - dx, y0 - dy)
        bottom_right = (x0 + dx, y0 + dy)
        top_right = (x1 + peak_dx, y1 + peak_dy)
        top_left = (x1 - peak_dx, y1 - peak_dy)
        vertices = [bottom_left]
        for i in range(1,self.arc_point_count-1):
            theta = np.pi * i / (self.arc_point_count - 1) + np.pi
            x = x0 + radius * np.cos(theta - angle)
            y = y0 + radius * np.sin(theta - angle)
            vertices.append((x,y))
        vertices.append(bottom_right)
        vertices.append(top_right)
        for i in range(1,self.arc_point_count-1):
            theta = np.pi * i / (self.arc_point_count - 1)
            x = x1 + (peak_radius) * np.cos(theta - angle)
            y = y1 + (peak_radius) * np.sin(theta - angle)
            vertices.append((x,y))
        vertices.append(top_left)

        glBegin(GL_POLYGON)
        glColor4f(*color)
        for x, y in vertices:
            glVertex2f(x, y)
        glEnd()

    def draw_peak_circle(self, optional_marker_freq=None):
        peak_bar_count = self.settings["BAR_COUNT"]
        held_freq = self.processor.highlighted_freq
        conf = self.processor.peak_conf
        if conf > 0.5:
            centers = np.sqrt(
                    get_weighted_band_edges(self.settings["MIN_FREQ"], self.settings["MAX_FREQ"], peak_bar_count, 0.8)[:-1] *
                    get_weighted_band_edges(self.settings["MIN_FREQ"], self.settings["MAX_FREQ"], peak_bar_count, 0.8)[1:]
                )
            idx = np.argmin(np.abs(centers - held_freq))
            target_angle = (2 * np.pi * idx) / peak_bar_count + 1.5 * np.pi

            x = np.sin(target_angle) * self.settings["MARKER_OFFSET"]
            y = np.cos(target_angle) * self.settings["MARKER_OFFSET"]
            marker_radius = self.settings["BAR_THICKNESS"] / 2

            if self.settings["OUTLINE_SCALE"] > 1:
                glBegin(GL_POLYGON)
                glColor4f(0.0, 0.0, 0.0, self.peak_marker_opacity)#self.peak_marker_opacity)
                for j in range(self.arc_point_count * 2):
                    theta = 2 * np.pi * j / (self.arc_point_count * 2)
                    glVertex2f(x + marker_radius * self.settings["OUTLINE_SCALE"] * np.cos(theta), y + marker_radius * self.settings["OUTLINE_SCALE"] * np.sin(theta))
                glEnd()

            glBegin(GL_POLYGON)
            r,g,b = self.hsv_to_rgb(self.peak_hue, 1, 1)
            glColor4f(r*self.peak_marker_opacity, g*self.peak_marker_opacity, b*self.peak_marker_opacity, self.peak_marker_opacity)
            #glColor4f(0.3 * self.peak_marker_opacity, 0.6 * self.peak_marker_opacity, 1 * self.peak_marker_opacity, self.peak_marker_opacity)
            for j in range(self.arc_point_count * 2):
                theta = 2 * np.pi * j / (self.arc_point_count * 2)
                glVertex2f(x + marker_radius * np.cos(theta), y + marker_radius * np.sin(theta))
            glEnd()

    def pause_rendering(self):
        if self.timer.isActive():
            self.timer.stop()

    def resume_rendering(self):
        if not self.timer.isActive():
            self.timer.start(self.settings["UPDATE_INTERVAL"])


    @staticmethod
    def hsv_to_rgb(h, s, v):
        if h:
            i = int(h * 6)
            f = h * 6 - i
            p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
            i %= 6
            return [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]
        else:

            return (1.0, 0.0, 0.0)
        
    def interpolate_hsv_3stop(self, value, low_hsv, mid_hsv, high_hsv, hsv_to_rgb):
        """
        Interpolates between three HSV color stops (h, s, v) where h ∈ [0, 1] and value ∈ [0, 1].

        Args:
            value (float): Input value in [0, 1]
            low_hsv (tuple): HSV at value = 0
            mid_hsv (tuple): HSV at value = 0.5
            high_hsv (tuple): HSV at value = 1
            hsv_to_rgb (function): A function that takes (h, s, v) and returns (r, g, b)

        Returns:
            tuple: Interpolated RGB tuple from your hsv_to_rgb()
        """
        def interpolate_hsv(a, b, t):
            h1, s1, v1 = a
            h2, s2, v2 = b

            # Hue interpolation with circular wraparound
            if abs(h2 - h1) > 0.5:
                if h1 > h2:
                    h2 += 1
                else:
                    h1 += 1
            h = (1 - t) * h1 + t * h2
            h = h % 1.0  # Wrap hue into [0, 1]

            s = (1 - t) * s1 + t * s2
            v = (1 - t) * v1 + t * v2

            return (h, s, v)

        if value <= 0.5:
            t = value / 0.5
            hsv = interpolate_hsv(low_hsv, mid_hsv, t)
        else:
            t = (value - 0.5) / 0.5
            hsv = interpolate_hsv(mid_hsv, high_hsv, t)

        return hsv_to_rgb(*hsv)
    
    def draw_linear_bars(self, amps, bar_count):
        """Draw bars in a line across the bottom of the window"""
        aspect = self.width() / self.height() if self.height() > 0 else 1.0
        margin = 0.02  # Distance from bottom edge
        bar_spacing = (2 * aspect) / bar_count  # Total width divided by number of bars
        bar_width = bar_spacing * 0.8  # Leave some space between bars
        max_bar_height = 0.6  # Maximum height bars can reach
        
        # Start position (leftmost)
        start_x = -aspect + bar_spacing / 2
        
        for i in range(min(self.animated_bar_count, bar_count)):
            # Get amplitude value without rotation offset for bottom line display
            value = amps[i] if i < len(amps) else 0
            value = max(value, self.settings["MIN_BAR_HEIGHT"])
            
            # Scale color value based on the actual displayable range (0 to BAR_MAX_HEIGHT)
            # This ensures colors reach full range even when max height is limited
            color_value = min(value / self.settings["BAR_MAX_HEIGHT"], 1.0)
            
            # Calculate colors using the scaled value
            r, g, b = self.interpolate_hsv_3stop(color_value, self.settings["LOW_COLOUR"], 
                                               self.settings["MID_COLOUR"], self.settings["HIGH_COLOUR"], self.hsv_to_rgb)
            
            # Calculate bar position and dimensions
            x = start_x + i * bar_spacing
            bar_height = value * max_bar_height * 2
            y_bottom = -1.0 + margin
            y_top = y_bottom + bar_height
            
            # Draw the bar
            color_with_opacity = (r*self.bar_opacity, g*self.bar_opacity, b*self.bar_opacity, self.bar_opacity)
            
            # Draw outline if enabled
            if self.settings["OUTLINE_SCALE"] > 0.1:
                outline_width = bar_width/2 + self.settings["OUTLINE_SCALE"] * 0.01
                if self.settings["ROUNDED_CAPS"]:
                    self.draw_rounded_rectangle(x - outline_width, y_bottom, x + outline_width, y_top, outline_width/2, (0.0, 0.0, 0.0, self.bar_opacity))
                else:
                    self.draw_rectangle(x - outline_width, y_bottom, x + outline_width, y_top, (0.0, 0.0, 0.0, self.bar_opacity))
            
            # Draw main bar
            if self.settings["ROUNDED_CAPS"]:
                self.draw_rounded_rectangle(x - bar_width/2, y_bottom, x + bar_width/2, y_top, bar_width/4, color_with_opacity)
            else:
                self.draw_rectangle(x - bar_width/2, y_bottom, x + bar_width/2, y_top, color_with_opacity)
    
    def draw_rectangle(self, x1, y1, x2, y2, color):
        """Helper method to draw a filled rectangle"""
        glBegin(GL_QUADS)
        glColor4f(*color)
        glVertex2f(x1, y1)
        glVertex2f(x2, y1)
        glVertex2f(x2, y2)
        glVertex2f(x1, y2)
        glEnd()
    
    def draw_rounded_rectangle(self, x1, y1, x2, y2, radius, color):
        """Helper method to draw a filled rectangle with rounded corners"""
        glBegin(GL_TRIANGLES)
        glColor4f(*color)
        
        # Draw main rectangle body (without corners)
        # Top rectangle
        glVertex2f(x1 + radius, y2)
        glVertex2f(x2 - radius, y2)
        glVertex2f(x1 + radius, y2 - radius)
        
        glVertex2f(x2 - radius, y2)
        glVertex2f(x2 - radius, y2 - radius)
        glVertex2f(x1 + radius, y2 - radius)
        
        # Bottom rectangle  
        glVertex2f(x1 + radius, y1 + radius)
        glVertex2f(x2 - radius, y1 + radius)
        glVertex2f(x1 + radius, y1)
        
        glVertex2f(x2 - radius, y1 + radius)
        glVertex2f(x2 - radius, y1)
        glVertex2f(x1 + radius, y1)
        
        # Middle rectangle
        glVertex2f(x1, y1 + radius)
        glVertex2f(x2, y1 + radius)
        glVertex2f(x1, y2 - radius)
        
        glVertex2f(x2, y1 + radius)
        glVertex2f(x2, y2 - radius)
        glVertex2f(x1, y2 - radius)
        
        glEnd()
        
        # Draw rounded corners using triangle fans
        segments = 8
        
        # Top-left corner
        glBegin(GL_TRIANGLE_FAN)
        glColor4f(*color)
        glVertex2f(x1 + radius, y2 - radius)  # Center
        for i in range(segments + 1):
            angle = np.pi + i * (np.pi / 2) / segments
            px = (x1 + radius) + radius * np.cos(angle)
            py = (y2 - radius) + radius * np.sin(angle)
            glVertex2f(px, py)
        glEnd()
        
        # Top-right corner
        glBegin(GL_TRIANGLE_FAN)
        glColor4f(*color)
        glVertex2f(x2 - radius, y2 - radius)  # Center
        for i in range(segments + 1):
            angle = np.pi / 2 + i * (np.pi / 2) / segments
            px = (x2 - radius) + radius * np.cos(angle)
            py = (y2 - radius) + radius * np.sin(angle)
            glVertex2f(px, py)
        glEnd()
        
        # Bottom-right corner
        glBegin(GL_TRIANGLE_FAN)
        glColor4f(*color)
        glVertex2f(x2 - radius, y1 + radius)  # Center
        for i in range(segments + 1):
            angle = i * (np.pi / 2) / segments
            px = (x2 - radius) + radius * np.cos(angle)
            py = (y1 + radius) + radius * np.sin(angle)
            glVertex2f(px, py)
        glEnd()
        
        # Bottom-left corner
        glBegin(GL_TRIANGLE_FAN)
        glColor4f(*color)
        glVertex2f(x1 + radius, y1 + radius)  # Center
        for i in range(segments + 1):
            angle = 3 * np.pi / 2 + i * (np.pi / 2) / segments
            px = (x1 + radius) + radius * np.cos(angle)
            py = (y1 + radius) + radius * np.sin(angle)
            glVertex2f(px, py)
        glEnd()
    
    def show_song(self, song):
        # Truncate if too long
        max_chars = 48  # or base on widget width
        if len(song) > max_chars:
            song = song[:max_chars - 3] + "..."
        self.current_song = song
        self.song_show_time = time.time()
        self.song_fade_step = 0
        self.song_fade_hold_step = 0  # Reset hold counter
        self.song_fade_timer.start(int(self.song_fade_duration * 1000 / self.song_fade_steps))
        logging.info(f"Now playing: {song}")
        self.update()

    def _fade_song(self):
        if self.song_fade_hold_step < self.song_fade_hold_steps:
            self.song_fade_hold_step += 1
            # Keep full opacity, don't increment fade step yet
        else:
            self.song_fade_step += 1
            if self.song_fade_step >= self.song_fade_steps:
                self.current_song = ""
                self.song_fade_timer.stop()
        self.update()
        

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings_manager = SettingsManager()
        self.processor = AudioProcessor(self.settings_manager.settings)
        device_idx = self.processor.device_index
        if device_idx is None:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                "No suitable audio input device found.\nPlease ensure you have 'Stereo Mix' or 'VB-Audio Virtual Cable' installed and enabled."
                )
            QtCore.QTimer.singleShot(0, self.close)
            return
        self.visualizer = GLVisualizer(self.processor, settings=self.settings_manager.settings)
        self.setCentralWidget(self.visualizer)
        
        # Add BPM label overlay
        self.bpm_label = QtWidgets.QLabel(self)
        self.bpm_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 180);
                background-color: transparent;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        self.bpm_label.setGeometry(10, 10, 100, 30)
        self.bpm_label.setText("BPM: --")
        self.bpm_label.show()

        icon_path = resource_path(r"media/sonic_halo_2.ico")
        self.tray_icon = TaskbarIcon(icon_path, {"Window mode": self.window_mode, "Display mode": self.display_mode, "Quit": self.close}, "Sonic Halo", left_click_callback=self.window_mode)

        # Timer for updating BPM display
        self.bpm_update_timer = QtCore.QTimer()
        self.bpm_update_timer.timeout.connect(self.update_bpm_display)
        self.bpm_update_timer.start(100)  # Update every 100ms
        
        self.setWindowTitle("Sonic Halo: Real-Time Audio Visualizer")
        self.resize(self.settings_manager.settings["WINDOW_WIDTH"], self.settings_manager.settings["WINDOW_HEIGHT"])
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self.max_bar_count = self.visualizer.processor.init_bar_count

        self.song_poller = SongPoller(poll_interval=2.0)
        self.song_poller.song_changed.connect(self.visualizer.show_song)
        self.song_poller.start()

        self.move(self.settings_manager.settings["WINDOW_POS_X"], self.settings_manager.settings["WINDOW_POS_Y"])

        # Initialize audio stream based on processor settings
        self.initialize_audio_stream()

    def initialize_audio_stream(self):
        """Initialize audio stream - either WASAPI loopback or regular input"""
        if self.processor.use_wasapi:
            self.setup_wasapi_stream()
        else:
            self.setup_sounddevice_stream()

    def setup_wasapi_stream(self):
        """Setup WASAPI loopback stream using PyAudio"""
        try:
            self.processor.pyaudio_instance = pyaudio.PyAudio()
            
            device_info = self.processor.pyaudio_instance.get_device_info_by_index(self.processor.device_index)
            sample_rate = int(device_info['defaultSampleRate'])
            channels = device_info['maxInputChannels'] if device_info['maxInputChannels'] > 0 else 2
            
            logging.info(f"Setting up WASAPI stream: {device_info['name']}")
            logging.info(f"Sample rate: {sample_rate}, Channels: {channels}")
            
            def pyaudio_callback(in_data, frame_count, time_info, status):
                # Tag source so analyze_chunk can mix when needed
                self.processor.analyze_chunk(in_data, frame_count, time_info, status, source='wasapi')
                return (None, pyaudio.paContinue)
            
            self.processor.pyaudio_stream = self.processor.pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=sample_rate,
                input=True,
                input_device_index=self.processor.device_index,
                frames_per_buffer=self.settings_manager.settings["CHUNK"],
                stream_callback=pyaudio_callback
            )
            
            self.processor.pyaudio_stream.start_stream()
            logging.info("WASAPI loopback stream started successfully")
            # Optionally start a microphone stream alongside WASAPI
            if self.settings_manager.settings.get("INCLUDE_MIC_INPUT", False):
                try:
                    mic_device = self.settings_manager.settings.get("MIC_DEVICE", None)
                    self.mic_stream = sd.InputStream(device=mic_device,
                                                     channels=2,
                                                     samplerate=self.settings_manager.settings["SAMPLE_RATE"],
                                                     blocksize=self.settings_manager.settings["CHUNK"],
                                                     callback=lambda indata, f, t, s: self.processor.analyze_chunk(indata, f, t, s, source='mic'))
                    self.mic_stream.start()
                    logging.info("Microphone input stream started alongside WASAPI")
                except Exception as e:
                    logging.error(f"Failed to start mic stream alongside WASAPI: {e}")
            
        except Exception as e:
            logging.error(f"Failed to setup WASAPI stream: {e}")
            logging.info("Falling back to SoundDevice input stream")
            self.processor.use_wasapi = False
            self.setup_sounddevice_stream()

    def setup_sounddevice_stream(self):
        """Setup regular SoundDevice input stream"""
        # When only using sounddevice, tag the source as 'mic' for consistency
        self.stream = sd.InputStream(device=self.processor.device_index,
                       channels=2,
                       samplerate=self.settings_manager.settings["SAMPLE_RATE"],
                       blocksize=self.settings_manager.settings["CHUNK"],
                       callback=lambda indata, f, t, s: self.processor.analyze_chunk(indata, f, t, s, source='mic'))
        self.stream.start()
        logging.info("SoundDevice input stream started")

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_P:
            if self.windowFlags() & QtCore.Qt.FramelessWindowHint:
                self.window_mode()
                logger.info("Showing window")
            else:
                self.display_mode()
                logger.info("Hiding window border, making trasparent to mouse events")
        elif event.key() == QtCore.Qt.Key_Down:
            if self.settings_manager.settings["BAR_COUNT"] > 1:
                self.settings_manager.settings["BAR_COUNT"] -= 1
                printed_bar_count = self.settings_manager.settings["BAR_COUNT"]
                logger.settings(f"Updated BAR_COUNT: {printed_bar_count}")
        elif event.key() == QtCore.Qt.Key_Up:
            if self.settings_manager.settings["BAR_COUNT"] < self.max_bar_count:
                self.settings_manager.settings["BAR_COUNT"] += 1
                printed_bar_count = self.settings_manager.settings["BAR_COUNT"]
                logger.settings(f"Updated BAR_COUNT: {printed_bar_count}")
        elif event.key() == QtCore.Qt.Key_Left:
            if self.settings_manager.settings["BAR_THICKNESS"] > 0.001:
                self.settings_manager.settings["BAR_THICKNESS"] = round(self.settings_manager.settings["BAR_THICKNESS"] - 0.001, 3)
                printed_bar_thickness = self.settings_manager.settings["BAR_THICKNESS"]
                logger.settings(f"Updated BAR_THICKNESS: {printed_bar_thickness}")
        elif event.key() == QtCore.Qt.Key_Right:
            if self.settings_manager.settings["BAR_THICKNESS"] < 100.0:
                self.settings_manager.settings["BAR_THICKNESS"] = round(self.settings_manager.settings["BAR_THICKNESS"] + 0.001, 3)
                printed_bar_thickness = self.settings_manager.settings["BAR_THICKNESS"]
                logger.settings(f"Updated BAR_THICKNESS: {printed_bar_thickness}")
        elif event.key() == QtCore.Qt.Key_0:
            rounded_opacity = round(self.settings_manager.settings["MAX_OPACITY"], 1)
            if rounded_opacity > 0.1:
                self.settings_manager.settings["MAX_OPACITY"] = round(self.settings_manager.settings["MAX_OPACITY"] - 0.1, 1)
                rounded_opacity = self.settings_manager.settings["MAX_OPACITY"]
                logger.settings(f"Updated MAX_OPACITY: {rounded_opacity}")
        elif event.key() == QtCore.Qt.Key_1:
            rounded_opacity = round(self.settings_manager.settings["MAX_OPACITY"], 1)
            if rounded_opacity < 1.0:
                self.settings_manager.settings["MAX_OPACITY"] = round(self.settings_manager.settings["MAX_OPACITY"] + 0.1, 1)
                rounded_opacity = round(self.settings_manager.settings["MAX_OPACITY"], 1)
                logger.settings(f"Updated MAX_OPACITY: {rounded_opacity}")
        elif event.key() == QtCore.Qt.Key_I:
            if self.settings_manager.settings["OUTLINE_SCALE"] < 10.0:
                self.settings_manager.settings["OUTLINE_SCALE"] = round(self.settings_manager.settings["OUTLINE_SCALE"] + 0.1, 2)
                printed_outline_scale = self.settings_manager.settings["OUTLINE_SCALE"]
                logger.settings(f"Updated OUTLINE_SCALE: {printed_outline_scale}")
        elif event.key() == QtCore.Qt.Key_K:
            if self.settings_manager.settings["OUTLINE_SCALE"] > 0.0:
                self.settings_manager.settings["OUTLINE_SCALE"] = round(self.settings_manager.settings["OUTLINE_SCALE"] - 0.1, 2)
                printed_outline_scale = self.settings_manager.settings["OUTLINE_SCALE"]
                logger.settings(f"Updated OUTLINE_SCALE: {printed_outline_scale}")
        elif event.key() == QtCore.Qt.Key_R:
            self.settings_manager.settings = self.settings_manager.default_settings.copy()
        elif event.key() == QtCore.Qt.Key_Escape:
            self.close()
        elif event.key() == QtCore.Qt.Key_W:
            self.settings_manager.settings["ARC_POINT_COUNT"] += 1
            printed_arc_point_count = self.settings_manager.settings["ARC_POINT_COUNT"]
            logger.settings(f"Updated ARC_POINT_COUNT: {printed_arc_point_count}")
        elif event.key() == QtCore.Qt.Key_S:
            self.settings_manager.settings["ARC_POINT_COUNT"] -= 1 if self.settings_manager.settings["ARC_POINT_COUNT"] > 1 else 0
            printed_arc_point_count = self.settings_manager.settings["ARC_POINT_COUNT"]
            logger.settings(f"Updated ARC_POINT_COUNT: {printed_arc_point_count}")
        elif event.key() == QtCore.Qt.Key_F12:
            # Save current frame as PNG
            image = self.visualizer.grabFramebuffer()
            save_path = os.path.join(os.path.expanduser("~"), "sonic_halo_frame.png")
            image.save(save_path, "PNG")
            logger.info(f"Frame saved to {save_path}")
        elif event.key() == QtCore.Qt.Key_T:
            # Increase UPDATE_INTERVAL (slower updates)
            if self.settings_manager.settings["UPDATE_INTERVAL"] < 1000:
                self.settings_manager.settings["UPDATE_INTERVAL"] += 1
                logger.settings(f"Updated UPDATE_INTERVAL: {self.settings_manager.settings['UPDATE_INTERVAL']}")
                self.visualizer.timer.setInterval(self.settings_manager.settings["UPDATE_INTERVAL"])
        elif event.key() == QtCore.Qt.Key_G:
            # Decrease UPDATE_INTERVAL (faster updates)
            if self.settings_manager.settings["UPDATE_INTERVAL"] > 1:
                self.settings_manager.settings["UPDATE_INTERVAL"] -= 1
                logger.settings(f"Updated UPDATE_INTERVAL: {self.settings_manager.settings['UPDATE_INTERVAL']}")
                self.visualizer.timer.setInterval(self.settings_manager.settings["UPDATE_INTERVAL"])
        elif event.key() == QtCore.Qt.Key_B:
            # Toggle BPM detection
            self.settings_manager.settings["BPM_DETECTION_ENABLED"] = not self.settings_manager.settings["BPM_DETECTION_ENABLED"]
            bpm_status = "ENABLED" if self.settings_manager.settings["BPM_DETECTION_ENABLED"] else "DISABLED"
            logger.settings(f"BPM Detection: {bpm_status}")
            # Save settings immediately when toggled
            self.settings_manager.save_settings_to_file(self.settings_manager.settings)
        elif event.key() == QtCore.Qt.Key_L:
            # Toggle logging level
            if logger.level == logging.INFO:
                logger.setLevel(SETTINGS_LEVEL)
                logger.info("Logging level set to SETTINGS (settings logs enabled)")
            else:
                logger.setLevel(logging.INFO)
                logger.info("Logging level set to INFO (settings logs disabled)")
        elif event.key() == QtCore.Qt.Key_Q:
            # Toggle square mode
            self.settings_manager.settings["SQUARE_MODE"] = not self.settings_manager.settings["SQUARE_MODE"]
            mode_status = "LINEAR" if self.settings_manager.settings["SQUARE_MODE"] else "CIRCULAR"
            logger.settings(f"Display mode: {mode_status}")
            self.settings_manager.save_settings_to_file(self.settings_manager.settings)
        elif event.key() == QtCore.Qt.Key_Plus or event.key() == QtCore.Qt.Key_Equal:
            # Increase height sensitivity
            if self.settings_manager.settings["HEIGHT_SENSITIVITY"] < 5.0:
                self.settings_manager.settings["HEIGHT_SENSITIVITY"] = round(self.settings_manager.settings["HEIGHT_SENSITIVITY"] + 0.1, 1)
                logger.settings(f"Updated HEIGHT_SENSITIVITY: {self.settings_manager.settings['HEIGHT_SENSITIVITY']}")
        elif event.key() == QtCore.Qt.Key_Minus:
            # Decrease height sensitivity
            if self.settings_manager.settings["HEIGHT_SENSITIVITY"] > 0.1:
                self.settings_manager.settings["HEIGHT_SENSITIVITY"] = round(self.settings_manager.settings["HEIGHT_SENSITIVITY"] - 0.1, 1)
                logger.settings(f"Updated HEIGHT_SENSITIVITY: {self.settings_manager.settings['HEIGHT_SENSITIVITY']}")
        elif event.key() == QtCore.Qt.Key_BracketRight:
            # Increase max bar height
            if self.settings_manager.settings["BAR_MAX_HEIGHT"] < 1.0:
                self.settings_manager.settings["BAR_MAX_HEIGHT"] = round(self.settings_manager.settings["BAR_MAX_HEIGHT"] + 0.05, 2)
                logger.settings(f"Updated BAR_MAX_HEIGHT: {self.settings_manager.settings['BAR_MAX_HEIGHT']}")
        elif event.key() == QtCore.Qt.Key_BracketLeft:
            # Decrease max bar height
            if self.settings_manager.settings["BAR_MAX_HEIGHT"] > 0.1:
                self.settings_manager.settings["BAR_MAX_HEIGHT"] = round(self.settings_manager.settings["BAR_MAX_HEIGHT"] - 0.05, 2)
                logger.settings(f"Updated BAR_MAX_HEIGHT: {self.settings_manager.settings['BAR_MAX_HEIGHT']}")
        elif event.key() == QtCore.Qt.Key_Comma:
            # Decrease base rotation speed
            if self.settings_manager.settings["BASE_ROTATION_SPEED"] > 0.0:
                self.settings_manager.settings["BASE_ROTATION_SPEED"] = round(max(0.0, self.settings_manager.settings["BASE_ROTATION_SPEED"] - 0.001), 4)
                logger.settings(f"Updated BASE_ROTATION_SPEED: {self.settings_manager.settings['BASE_ROTATION_SPEED']}")
        elif event.key() == QtCore.Qt.Key_Period:
            # Increase base rotation speed
            if self.settings_manager.settings["BASE_ROTATION_SPEED"] < 0.1:
                self.settings_manager.settings["BASE_ROTATION_SPEED"] = round(self.settings_manager.settings["BASE_ROTATION_SPEED"] + 0.001, 4)
                logger.settings(f"Updated BASE_ROTATION_SPEED: {self.settings_manager.settings['BASE_ROTATION_SPEED']}")
        elif event.key() == QtCore.Qt.Key_Semicolon:
            # Decrease audio reactive rotation speed
            if self.settings_manager.settings["AUDIO_ROTATION_SPEED"] > 0.0:
                self.settings_manager.settings["AUDIO_ROTATION_SPEED"] = round(max(0.0, self.settings_manager.settings["AUDIO_ROTATION_SPEED"] - 0.1), 1)
                logger.settings(f"Updated AUDIO_ROTATION_SPEED: {self.settings_manager.settings['AUDIO_ROTATION_SPEED']}")
        elif event.key() == QtCore.Qt.Key_Apostrophe:
            # Increase audio reactive rotation speed
            if self.settings_manager.settings["AUDIO_ROTATION_SPEED"] < 5.0:
                self.settings_manager.settings["AUDIO_ROTATION_SPEED"] = round(self.settings_manager.settings["AUDIO_ROTATION_SPEED"] + 0.1, 1)
                logger.settings(f"Updated AUDIO_ROTATION_SPEED: {self.settings_manager.settings['AUDIO_ROTATION_SPEED']}")

    def update_bpm_display(self):
        """Update the BPM label display"""
        if self.settings_manager.settings["BPM_DETECTION_ENABLED"] and self.processor.bpm > 0:
            self.bpm_label.setText(f"BPM: {self.processor.bpm:.1f}")
            self.bpm_label.setVisible(True)
        elif self.settings_manager.settings["BPM_DETECTION_ENABLED"]:
            self.bpm_label.setText("BPM: --")
            self.bpm_label.setVisible(True)
        else:
            self.bpm_label.setVisible(False)

    def display_mode(self):
        pos = self.pos()
        self.visualizer.pause_rendering()
        self.close_audio_streams()
        #time.sleep(0.5)

        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.show()
        pos.setY(pos.y() - 1)
        self.move(pos)

        # Delay Win32 manipulation until Qt stabilizes
        #QtCore.QTimer.singleShot(50, lambda: make_window_clickthrough(self))
        #QtCore.QTimer.singleShot(500, lambda: self.visualizer.resume_rendering())
        make_window_clickthrough(self)
        self.visualizer.resume_rendering()
        self.start_audio_streams()

    def window_mode(self):
        pos = self.pos()
        self.visualizer.pause_rendering()
        self.close_audio_streams()
        #time.sleep(0.5)

        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self.show()
        pos.setX(pos.x() - 8)
        pos.setY(pos.y() - 30)
        self.move(pos)

        #QtCore.QTimer.singleShot(50, lambda: make_window_clickable(self))
        #QtCore.QTimer.singleShot(500, lambda: self.visualizer.resume_rendering())
        make_window_clickable(self)
        self.visualizer.resume_rendering()
        self.start_audio_streams()

    def start_audio_streams(self):
        """Start audio streams properly based on type"""
        try:
            if self.processor.use_wasapi:
                # For WASAPI, we need to check if stream is closed and reinitialize if needed
                if (self.processor.pyaudio_stream is None or 
                    not self.processor.pyaudio_stream.is_active()):
                    logging.info("Reinitializing WASAPI stream")
                    self.setup_wasapi_stream()
                else:
                    self.processor.pyaudio_stream.start_stream()
                    logging.info("WASAPI stream started")
            else:
                if hasattr(self, 'stream'):
                    if self.stream.closed:
                        logging.info("Reinitializing SoundDevice stream")
                        self.setup_sounddevice_stream()
                    else:
                        self.stream.start()
                        logging.info("SoundDevice stream started")
                else:
                    logging.info("Initializing SoundDevice stream")
                    self.setup_sounddevice_stream()
        except Exception as e:
            logging.error(f"Error starting audio streams: {e}")
            # Try to reinitialize the stream
            try:
                logging.info("Attempting to reinitialize audio stream")
                self.initialize_audio_stream()
            except Exception as e2:
                logging.error(f"Failed to reinitialize audio stream: {e2}")


    def centered_setText(self, text):
        def update():
            self.label.setText(text)
            self.label.adjustSize()
            label_width = self.label.width()
            label_height = self.label.height()
            win_width = self.width()
            win_height = self.height()
            self.label.move((win_width - label_width) // 2, (win_height - label_height) // 2)
        QtCore.QMetaObject.invokeMethod(self, update, QtCore.Qt.QueuedConnection)
    
    def closeEvent(self, event):
        logging.info("Closing application")

        self.song_poller.stop()
        self.song_poller.wait()
        # Check if in display mode (frameless)
        if self.windowFlags() & QtCore.Qt.FramelessWindowHint:
            self.window_mode()
        self.visualizer.pause_rendering()
        
        # Fully close audio streams on app exit
        self.close_audio_streams()
        
        self.settings_manager.settings["WINDOW_POS_X"] = self.x()
        self.settings_manager.settings["WINDOW_POS_Y"] = self.y()
        self.settings_manager.settings["WINDOW_WIDTH"] = self.width()
        self.settings_manager.settings["WINDOW_HEIGHT"] = self.height()
        self.settings_manager.save_settings_to_file(self.settings_manager.settings)
        event.accept()

    def close_audio_streams(self):
        """Fully close and cleanup audio streams on app exit"""
        try:
            if self.processor.use_wasapi:
                if self.processor.pyaudio_stream:
                    if self.processor.pyaudio_stream.is_active():
                        self.processor.pyaudio_stream.stop_stream()
                    self.processor.pyaudio_stream.close()
                if self.processor.pyaudio_instance:
                    self.processor.pyaudio_instance.terminate()
                # close optional mic stream
                if hasattr(self, 'mic_stream') and self.mic_stream is not None:
                    try:
                        if not self.mic_stream.closed:
                            self.mic_stream.stop()
                            self.mic_stream.close()
                    except Exception:
                        pass
                logging.info("WASAPI streams closed")
            else:
                if hasattr(self, 'stream') and not self.stream.closed:
                    self.stream.stop()
                    self.stream.close()
                logging.info("SoundDevice stream closed")
        except Exception as e:
            logging.error(f"Error closing audio streams: {e}")
    
    def log_keybinds():
        keybinds = {
            "P": "Toggle between windowed and display (frameless/clickthrough) mode",
            "Down Arrow": "Decrease BAR_COUNT (number of bars)",
            "Up Arrow": "Increase BAR_COUNT (number of bars)",
            "Left Arrow": "Decrease BAR_THICKNESS",
            "Right Arrow": "Increase BAR_THICKNESS",
            "0": "Decrease MAX_OPACITY",
            "1": "Increase MAX_OPACITY",
            "I": "Increase OUTLINE_SCALE",
            "K": "Decrease OUTLINE_SCALE",
            "R": "Reset settings to defaults",
            "Escape": "Close the application",
            "W": "Increase ARC_POINT_COUNT (bar roundness)",
            "S": "Decrease ARC_POINT_COUNT (bar roundness)",
            "F12": "Save current frame as PNG",
            "T": "Increase UPDATE_INTERVAL (slower updates)",
            "G": "Decrease UPDATE_INTERVAL (faster updates)",
            "B": "Toggle BPM detection on/off",
            "Q": "Toggle between circular and linear bottom display mode",
            "+/=": "Increase HEIGHT_SENSITIVITY (bars require more volume)",
            "-": "Decrease HEIGHT_SENSITIVITY (bars require less volume)",
            "]": "Increase BAR_MAX_HEIGHT (maximum bar height)",
            "[": "Decrease BAR_MAX_HEIGHT (maximum bar height)",
            ",": "Decrease BASE_ROTATION_SPEED (constant rotation)",
            ".": "Increase BASE_ROTATION_SPEED (constant rotation)",
            ";": "Decrease AUDIO_ROTATION_SPEED (audio reactive rotation)",
            "'": "Increase AUDIO_ROTATION_SPEED (audio reactive rotation)"
        }
        logging.info("Keybinds:")
        for key, desc in keybinds.items():
            logging.info(f"    {key}: {desc}")
        
    # Call this after window is initialized
    log_keybinds()

if __name__ == '__main__':
    fmt = QtGui.QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    QtGui.QSurfaceFormat.setDefaultFormat(fmt)
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

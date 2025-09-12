# refactored_audio_visualizer.py
import sys
import numpy as np
import sounddevice as sd
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import QOpenGLWidget
from OpenGL.GL import *
import ctypes, logging, json, os
import platformdirs.windows

logging.basicConfig(level=logging.DEBUG,
                    format="{levelname} - {message}",
                    style="{")

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

DEBUG = True

logging.info("Sonic Halo: Real-Time Audio Visualizer by Dacus")
# Major.Minor.Patch.Build
VERSION = "0.6.1.4"
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
            }
        self.default_settings = self.settings.copy()

        self.settings_file_dir = platformdirs.user_data_dir("Sonic Halo", "Dacus")

        # Load settings from file or use defaults
        self.settings = self.load_settings_from_file()
        logging.info("settings:")
        for k,v in self.settings.items():
            logging.info(f"    {k} = {v}")

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
    
class DevicesMap:
    VIRTUAL_CABLE = "CABLE Output (VB-Audio Virtual Cable)"
    STEREO_MIX = "Stereo Mix"
    device_priority = [STEREO_MIX, VIRTUAL_CABLE]
    def __init__(self, user_device=None):
        self.user_device = user_device
        self.device_priority = [user_device] + self.device_priority if user_device else self.device_priority

class AudioProcessor:
    init_bar_count = 28 # settings["BAR_COUNT"]
    def __init__(self, settings=None):
        logging.info("Initialising AudioProcessor")
        self.settings = settings if settings else {}
        self.amps = np.zeros(self.init_bar_count)
        self.smoothed_amps = np.zeros(self.init_bar_count)
        self.fall_velocity = np.zeros(self.init_bar_count)
        self.device_index = self.find_device()
        self.max_seen = 10.0
        self.highlighted_idx = None
        self.highlighted_freq = []
        self.is_harmonic = False
        self.control = 0
        self.error = 0
        self.integral = 0
        self.delta = 16

    def find_device(self):
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

    def analyze_chunk(self, indata, frames, time_info, status):
        mono = np.mean(indata, axis=1)
        N = 4096 * 2
        fft = np.abs(np.fft.rfft(mono, n=N))
        freqs = np.fft.rfftfreq(N, d=1 / self.settings["SAMPLE_RATE"])

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

        amps = np.clip(amps / self.max_seen, 0, 1)
        vocal_indices = np.where((band_centers >= self.settings["VOCAL_MIN"]) & (band_centers <= self.settings["VOCAL_MAX"]))[0]

        if len(vocal_indices) and np.max(amps[vocal_indices]) > 0.1:
            self.detect_harmonics(amps, band_centers)
            self.highlighted_idx = vocal_indices[np.argmax(amps[vocal_indices])]
        else:
            self.highlighted_idx = None

        self.amps = amps.copy()
        #self.highlighted_freq, self.peak_conf = self.hps_pitch_detection_with_confidence(fft, SAMPLE_RATE, N, 4)
        #self.highlighted_freq = self.find_peak_frequency(fft, freqs, band_edges, band_centers)
        #self.detect_harmonics(amps, band_centers)

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

        min_radius = 0.175 # 0.22
        outer_radius = min_radius+(self.processor.max_seen / 300) * (0.5 - min_radius)
        inner_radius = outer_radius - 0.02 # min_radius+(self.processor.max_seen / 300) * (0.5 - min_radius)
        performance_offset = 0 # min(delta - 16, 0)
        self.arc_point_count = max(self.settings["ARC_POINT_COUNT"] - performance_offset, 2)
        ring_bar_count = self.settings["ARC_POINT_COUNT"] * 2 # (BAR_COUNT * 2) - performance_offset
        if self.settings["OUTLINE_SCALE"] > 0.1:
            self.draw_ring(inner_radius-self.settings["OUTLINE_SCALE"]*0.01, outer_radius+0.03+self.settings["OUTLINE_SCALE"]*0.01, ring_bar_count, amps, outline=True)
        self.draw_ring(inner_radius, outer_radius+0.03, ring_bar_count, amps)

        bass_energy = np.prod(amps[:min(4, paint_bar_count)])
        self.rotation_offset += 0.003 + self.processor.error/40000 + min(bass_energy * 0.1, 0.01)
        self.rotation_offset %= 2 * np.pi

        min_value = np.max(amps)

        peak_index = self.processor.highlighted_idx
        if peak_index:
            proportional = 2.0
            self.control, self.error, self.integral = pid_controller(peak_index, self.peak_pid, proportional, 0.0, 0.02, self.error, self.integral, delta/1000)
            self.peak_pid += self.control * delta/1000 # max_fft

        for i in range(self.animated_bar_count):
            shifted_index = (i + (self.rotation_offset * paint_bar_count / (2 * np.pi))) % paint_bar_count

            idx0 = int(np.floor(shifted_index))
            idx1 = (idx0 + 1) % paint_bar_count
            frac = shifted_index - idx0
            value = np.interp(frac, [0, 1], [amps[idx0], amps[idx1]]) * 1.00
            value = max(value, self.settings["MIN_BAR_HEIGHT"])
            min_value = max(value, min_value)
            angle = (2 * np.pi * i) / paint_bar_count + 1.5 * np.pi + self.rotation_offset

            r, g, b = self.interpolate_hsv_3stop(value, self.settings["LOW_COLOUR"], self.settings["MID_COLOUR"], self.settings["HIGH_COLOUR"], self.hsv_to_rgb)
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
                if elapsed < fade_duration and elapsed > 0.4:
                    #self.bar_opacity = MAX_OPACITY * (1 - (elapsed / fade_duration))
                    self.bar_opacity = self.settings["MAX_OPACITY"] * (1 - max(0, elapsed - fade_duration / 2) / (fade_duration / 2))
                    self.animated_bar_count = int(paint_bar_count * (1 - max(0, (elapsed - fade_duration / 2) / (fade_duration / 2))))
                elif 0 <= elapsed <= 0.4:
                    pass
                else:
                    self.animated_bar_count = 0
                    self.bar_opacity = 0.0
            else:
                pass
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
        self.setWindowTitle("Sonic Halo: Real-Time Audio Visualizer")
        self.resize(self.settings_manager.settings["WINDOW_WIDTH"], self.settings_manager.settings["WINDOW_HEIGHT"])
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self.max_bar_count = self.visualizer.processor.init_bar_count

        self.move(self.settings_manager.settings["WINDOW_POS_X"], self.settings_manager.settings["WINDOW_POS_Y"])


        self.stream = sd.InputStream(device=self.processor.device_index,
                       channels=2,
                       samplerate=self.settings_manager.settings["SAMPLE_RATE"],
                       blocksize=self.settings_manager.settings["CHUNK"],
                       callback=self.processor.analyze_chunk)
        self.stream.start()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_P:
            if self.windowFlags() & QtCore.Qt.FramelessWindowHint:
                self.window_mode()
                logging.info("Showing window")
            else:
                self.display_mode()
                logging.info("Hiding window border, making trasparent to mouse events")
        elif event.key() == QtCore.Qt.Key_Down:
            if self.settings_manager.settings["BAR_COUNT"] > 1:
                self.settings_manager.settings["BAR_COUNT"] -= 1
                printed_bar_count = self.settings_manager.settings["BAR_COUNT"]
                logging.info(f"Updated BAR_COUNT: {printed_bar_count}")
        elif event.key() == QtCore.Qt.Key_Up:
            if self.settings_manager.settings["BAR_COUNT"] < self.max_bar_count:
                self.settings_manager.settings["BAR_COUNT"] += 1
                printed_bar_count = self.settings_manager.settings["BAR_COUNT"]
                logging.info(f"Updated BAR_COUNT: {printed_bar_count}")
        elif event.key() == QtCore.Qt.Key_Left:
            if self.settings_manager.settings["BAR_THICKNESS"] > 0.001:
                self.settings_manager.settings["BAR_THICKNESS"] = round(self.settings_manager.settings["BAR_THICKNESS"] - 0.001, 3)
                printed_bar_thickness = self.settings_manager.settings["BAR_THICKNESS"]
                logging.info(f"Updated BAR_THICKNESS: {printed_bar_thickness}")
        elif event.key() == QtCore.Qt.Key_Right:
            if self.settings_manager.settings["BAR_THICKNESS"] < 100.0:
                self.settings_manager.settings["BAR_THICKNESS"] = round(self.settings_manager.settings["BAR_THICKNESS"] + 0.001, 3)
                printed_bar_thickness = self.settings_manager.settings["BAR_THICKNESS"]
                logging.info(f"Updated BAR_THICKNESS: {printed_bar_thickness}")
        elif event.key() == QtCore.Qt.Key_0:
            rounded_opacity = round(self.settings_manager.settings["MAX_OPACITY"], 1)
            if rounded_opacity > 0.1:
                self.settings_manager.settings["MAX_OPACITY"] = round(self.settings_manager.settings["MAX_OPACITY"] - 0.1, 1)
                rounded_opacity = self.settings_manager.settings["MAX_OPACITY"]
                logging.info(f"Updated MAX_OPACITY: {rounded_opacity}")
        elif event.key() == QtCore.Qt.Key_1:
            rounded_opacity = round(self.settings_manager.settings["MAX_OPACITY"], 1)
            if rounded_opacity < 1.0:
                self.settings_manager.settings["MAX_OPACITY"] = round(self.settings_manager.settings["MAX_OPACITY"] + 0.1, 1)
                rounded_opacity = round(self.settings_manager.settings["MAX_OPACITY"], 1)
                logging.info(f"Updated MAX_OPACITY: {rounded_opacity}")
        elif event.key() == QtCore.Qt.Key_I:
            if self.settings_manager.settings["OUTLINE_SCALE"] < 10.0:
                self.settings_manager.settings["OUTLINE_SCALE"] = round(self.settings_manager.settings["OUTLINE_SCALE"] + 0.1, 2)
                printed_outline_scale = self.settings_manager.settings["OUTLINE_SCALE"]
                logging.info(f"Updated OUTLINE_SCALE: {printed_outline_scale}")
        elif event.key() == QtCore.Qt.Key_K:
            if self.settings_manager.settings["OUTLINE_SCALE"] > 0.0:
                self.settings_manager.settings["OUTLINE_SCALE"] = round(self.settings_manager.settings["OUTLINE_SCALE"] - 0.1, 2)
                printed_outline_scale = self.settings_manager.settings["OUTLINE_SCALE"]
                logging.info(f"Updated OUTLINE_SCALE: {printed_outline_scale}")
        elif event.key() == QtCore.Qt.Key_R:
            self.settings_manager.settings = self.settings_manager.default_settings.copy()
        elif event.key() == QtCore.Qt.Key_Escape:
            self.close()
        elif event.key() == QtCore.Qt.Key_W:
            self.settings_manager.settings["ARC_POINT_COUNT"] += 1
            printed_arc_point_count = self.settings_manager.settings["ARC_POINT_COUNT"]
            logging.info(f"Updated ARC_POINT_COUNT: {printed_arc_point_count}")
        elif event.key() == QtCore.Qt.Key_S:
            self.settings_manager.settings["ARC_POINT_COUNT"] -= 1 if self.settings_manager.settings["ARC_POINT_COUNT"] > 1 else 0
            printed_arc_point_count = self.settings_manager.settings["ARC_POINT_COUNT"]
            logging.info(f"Updated ARC_POINT_COUNT: {printed_arc_point_count}")
        elif event.key() == QtCore.Qt.Key_F12:
            # Save current frame as PNG
            image = self.visualizer.grabFramebuffer()
            save_path = os.path.join(os.path.expanduser("~"), "sonic_halo_frame.png")
            image.save(save_path, "PNG")
            logging.info(f"Frame saved to {save_path}")
        elif event.key() == QtCore.Qt.Key_T:
            # Increase UPDATE_INTERVAL (slower updates)
            if self.settings_manager.settings["UPDATE_INTERVAL"] < 1000:
                self.settings_manager.settings["UPDATE_INTERVAL"] += 1
                logging.info(f"Updated UPDATE_INTERVAL: {self.settings_manager.settings['UPDATE_INTERVAL']}")
                self.visualizer.timer.setInterval(self.settings_manager.settings["UPDATE_INTERVAL"])
        elif event.key() == QtCore.Qt.Key_G:
            # Decrease UPDATE_INTERVAL (faster updates)
            if self.settings_manager.settings["UPDATE_INTERVAL"] > 1:
                self.settings_manager.settings["UPDATE_INTERVAL"] -= 1
                logging.info(f"Updated UPDATE_INTERVAL: {self.settings_manager.settings['UPDATE_INTERVAL']}")
                self.visualizer.timer.setInterval(self.settings_manager.settings["UPDATE_INTERVAL"])

    def display_mode(self):
        pos = self.pos()
        self.visualizer.pause_rendering()
        self.stream.stop()
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
        self.stream.start()


    def window_mode(self):
        pos = self.pos()
        self.visualizer.pause_rendering()
        self.stream.stop()
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
        self.stream.start()


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
        # Check if in display mode (frameless)
        if self.windowFlags() & QtCore.Qt.FramelessWindowHint:
            self.window_mode()
        self.visualizer.pause_rendering()
        self.stream.stop()
        self.settings_manager.settings["WINDOW_POS_X"] = self.x()
        self.settings_manager.settings["WINDOW_POS_Y"] = self.y()
        self.settings_manager.settings["WINDOW_WIDTH"] = self.width()
        self.settings_manager.settings["WINDOW_HEIGHT"] = self.height()
        self.settings_manager.save_settings_to_file(self.settings_manager.settings)
        event.accept()
    
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
            "G": "Decrease UPDATE_INTERVAL (faster updates)"
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

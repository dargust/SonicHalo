import sys
import numpy as np
import sounddevice as sd
from PyQt5 import QtWidgets, QtGui, QtCore, QtOpenGL
from OpenGL.GL import *
from PyQt5.QtWidgets import QOpenGLWidget
import ctypes

def make_window_clickthrough(window):
    hwnd = int(window.winId())  # Native HWND
    style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
    style |= 0x80000 | 0x20  # WS_EX_LAYERED | WS_EX_TRANSPARENT
    ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)

def make_window_clickable(window):
    hwnd = int(window.winId())  # Native HWND
    style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
    style &= ~(0x80000 | 0x20)  # WS_EX_LAYERED | WS_EX_TRANSPARENT
    ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)

BAR_COUNT = 36
SAMPLE_RATE = 44100
CHUNK = 512
UPDATE_INTERVAL = 16
BAR_THICKNESS = 0.048
MIN_BAR_HEIGHT = 0.03

def get_weighted_band_edges(min_freq, max_freq, band_count, low_bias=2.5):
    """
    Returns band edges with more density in the lows.
    low_bias > 1.0 means more bands in the lows, 1.0 is pure logspace.
    """
    t = np.linspace(0, 1, band_count + 1)
    # bias toward low frequencies
    t_weighted = t ** low_bias
    band_edges = min_freq * (max_freq / min_freq) ** t_weighted
    return band_edges

class AudioProcessor:
    def __init__(self):
        self.amps = np.zeros(BAR_COUNT)
        self.smoothed_amps = np.zeros(BAR_COUNT)
        self.fall_velocity = np.zeros(BAR_COUNT)
        self.band_centers = None
        self.highlighted_idx = None
        self.highlighted_freq = None
        self.device_index = self.find_device()
        self.max_seen = [10.0]
        self.is_harmonic = False

    def find_device(self):
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if 'CABLE Output' in dev['name'] and dev['max_input_channels'] == 16:
                return i
        return None

    def get_weighted_band_edges(self, min_freq, max_freq, band_count, low_bias=2.5):
        t = np.linspace(0, 1, band_count + 1)
        t_weighted = t ** low_bias
        return min_freq * (max_freq / min_freq) ** t_weighted

    def process_audio(self, indata, frames, time_info, status):
        mono = np.mean(indata, axis=1)
        N = 4096*2
        fft = np.abs(np.fft.rfft(mono, n=N))
        freqs = np.fft.rfftfreq(N, d=1/SAMPLE_RATE)

        min_freq = 50
        max_freq = 12000
        band_edges = get_weighted_band_edges(min_freq, max_freq, BAR_COUNT, low_bias=0.8)
        amps = np.zeros(BAR_COUNT)
        band_centers = np.sqrt(band_edges[:-1] * band_edges[1:])

        bin_indices = np.digitize(freqs, band_edges) - 1
        for i in range(BAR_COUNT):
            bins_in_band = np.where(bin_indices == i)[0]
            if len(bins_in_band) > 0:
                amps[i] = np.mean(fft[bins_in_band])
            else:
                amps[i] = 0

        gain = np.sqrt(band_centers / band_centers[0])
        amps *= gain

        noise_threshold = 1e-4
        if np.max(amps) < noise_threshold:
            amps = np.zeros(BAR_COUNT)

        max_fft = np.max(amps)
        decay_rate = 0.995
        MIN_MAX_SEEN = 10.0

        if max_fft > self.max_seen[0]:
            self.max_seen[0] = max_fft
        else:
            self.max_seen[0] *= decay_rate
            if self.max_seen[0] < MIN_MAX_SEEN:
                self.max_seen[0] = MIN_MAX_SEEN

        vocal_min = 155
        vocal_max = 1100
        vocal_band_indices = np.where((band_centers >= vocal_min) & (band_centers <= vocal_max))[0]
        if self.max_seen[0] < 1e-3 or len(vocal_band_indices) == 0:
            amps = np.zeros(BAR_COUNT)
            self.highlighted_idx = None
        else:
            amps = np.clip(amps / self.max_seen[0], 0, 1)
            vocal_amps = amps[vocal_band_indices]
            if np.max(vocal_amps) > 0.1:
                self.highlighted_idx = vocal_band_indices[np.argmax(vocal_amps)]
            else:
                self.highlighted_idx = None
        self.amps = amps
        
        # Find the true FFT peak frequency in the vocal range
        if self.highlighted_idx is not None:
            # Get the frequency range for the loudest band
            band_start = band_edges[self.highlighted_idx]
            band_end = band_edges[self.highlighted_idx + 1]
            # Find FFT bins within this band
            bins_in_band = np.where((freqs >= band_start) & (freqs < band_end))[0]
            if len(bins_in_band) > 0:
                peak_bin = bins_in_band[np.argmax(fft[bins_in_band])]
                self.highlighted_freq = freqs[peak_bin]
            else:
                self.highlighted_freq = band_centers[self.highlighted_idx]
        else:
            self.highlighted_freq = None
        
        self.is_harmonic = False
        if self.highlighted_idx is not None:
            f0 = band_centers[self.highlighted_idx]
            harmonics_found = 0
            for h in range(2, 5):
                harmonic_freq = f0 * h
                if harmonic_freq > band_centers[-1]:
                    break
                harmonic_idx = np.argmin(np.abs(band_centers - harmonic_freq))
                if amps[harmonic_idx] > 0.15:
                    harmonics_found += 1
            self.is_harmonic = harmonics_found >= 1
        else:
            self.is_harmonic = False

    def update_smoothed(self):
        for i in range(BAR_COUNT):
            if self.amps[i] > self.smoothed_amps[i]:
                self.smoothed_amps[i] = self.amps[i]
                self.fall_velocity[i] = 0
            else:
                self.fall_velocity[i] += 0.003
                fall_amount = max(0.005, self.fall_velocity[i])
                self.smoothed_amps[i] = max(0, self.smoothed_amps[i] - fall_amount)


class GLVisualizer(QOpenGLWidget):
    def __init__(self, processor, parent=None):
        super().__init__(parent)
        self.processor = processor
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(UPDATE_INTERVAL)
        self.rotation_offset = 0.0
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.peak_marker_angle = None
        self.peak_marker_speed = 0.06
        self.peak_marker_opacity = 0.0
        self.peak_marker_fade_speed = 0.005
        self.x_center = None
        self.y_center = None

    def initializeGL(self):
        glClearColor(0.0, 0.0, 0.0, 1.0)
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
        BAR_COUNT_F = float(BAR_COUNT)
        glClearColor(0.0, 0.0, 0.0, 0.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()


        self.processor.update_smoothed()
        amps = self.processor.smoothed_amps

        # Use bass energy to drive rotation speed
        bass_indices = np.arange(0, min(4, BAR_COUNT))
        selected_values = amps[bass_indices]
        self.rotation_speed = min(np.prod(selected_values)*0.2, 0.02) + 0.003
        #self.rotation_speed = min(np.mean(selected_values)*0.05, 0.02) + 0.003
        #glRotatef(np.degrees(-self.rotation), 0, 0, 1)
        self.rotation_offset += self.rotation_speed
        if self.rotation_offset > 2 * np.pi:
            self.rotation_offset -= 2 * np.pi
        # Smooth the wrap by averaging the first and second-to-last bar for the last bar
        if BAR_COUNT > 2:
            amps[-1] = (amps[0] + amps[-2]) / 2
        for i in range(BAR_COUNT):
            shift = (self.rotation_offset * BAR_COUNT_F / (2 * np.pi)) - 3*np.pi
            shifted_index = (i + shift) % BAR_COUNT_F
            idx0 = int(np.floor(shifted_index))
            idx1 = (idx0 + 1) % BAR_COUNT
            frac = shifted_index - idx0

            # Linear interpolation
            value = (1 - frac) * amps[idx0] + frac * amps[idx1]
            value = min(max(value, MIN_BAR_HEIGHT), 1)
            angle = (2 * np.pi * i) / BAR_COUNT + np.pi + self.rotation_offset

            base_radius = 0.3
            tip_radius = base_radius + value * 0.5

            x0 = np.sin(angle) * base_radius
            y0 = np.cos(angle) * base_radius
            x1 = np.sin(angle) * tip_radius
            y1 = np.cos(angle) * tip_radius

            # Draw polygons instead of lines for the bars, use the base point (x0, y0) and tip point (x1, y1) and create a rectangle extending from the base to the tip there should be two vertices at the base and two at the tip

            # Color gradient based on amplitude
            hue = 0.33 * (1 - value)
            r, g, b = self.hsv_to_rgb(hue, 1, 1)
            if self.processor.highlighted_idx is not None:
                dist = abs(shifted_index - self.processor.highlighted_idx)
                b = max(0.0, 1.0 - dist * 0.4)
                #b = min(1.0, b + 0.5)

            x_bottom_left = x0 - BAR_THICKNESS / 2 * np.cos(-angle)
            y_bottom_left = y0 - BAR_THICKNESS / 2 * np.sin(-angle)
            x_bottom_right = x0 + BAR_THICKNESS / 2 * np.cos(-angle)
            y_bottom_right = y0 + BAR_THICKNESS / 2 * np.sin(-angle)
            x_top_left = x1 - BAR_THICKNESS / 2 * np.cos(-angle)
            y_top_left = y1 - BAR_THICKNESS / 2 * np.sin(-angle)
            x_top_right = x1 + BAR_THICKNESS / 2 * np.cos(-angle)
            y_top_right = y1 + BAR_THICKNESS / 2 * np.sin(-angle)

            glBegin(GL_POLYGON)

            glColor4f(r/5, g/5, b/5, 0.2)

            glVertex2f(x_bottom_left, y_bottom_left)
            glVertex2f(x_bottom_right, y_bottom_right)
            glVertex2f(x_top_right, y_top_right)
            glVertex2f(x_top_left, y_top_left)

            glEnd()

        offset_from_center = 0.25
        radius = 0.02 # + (self.processor.amps[highlighted_idx] * 0.1)

        # Draw a circle at the peak frequency if it exists
        if self.processor.highlighted_freq is not None and self.processor.is_harmonic:
            freq = self.processor.highlighted_freq
            band_edges = get_weighted_band_edges(50, 12000, BAR_COUNT, low_bias=0.8)
            band_centers = np.sqrt(band_edges[:-1] * band_edges[1:])
            highlighted_idx = np.argmin(np.abs(band_centers - freq))
            peak_marker_angle_target = (2 * np.pi * highlighted_idx) / BAR_COUNT + 1.5 * np.pi # + self.rotation_offset
            if self.peak_marker_angle == None:
                self.peak_marker_angle = peak_marker_angle_target
            self.peak_marker_angle += (peak_marker_angle_target - self.peak_marker_angle) * self.peak_marker_speed

            self.x_center = np.sin(self.peak_marker_angle) * offset_from_center
            self.y_center = np.cos(self.peak_marker_angle) * offset_from_center
            if self.peak_marker_opacity < 0.2:
                self.peak_marker_opacity = 0.2
        else:
            if self.peak_marker_opacity > 0.0:
                self.peak_marker_opacity -= self.peak_marker_fade_speed
        
        if self.x_center:
            glBegin(GL_POLYGON)
            # Set line thickness
            glColor4f(0.3*self.peak_marker_opacity, 0.6*self.peak_marker_opacity, 1*self.peak_marker_opacity, self.peak_marker_opacity)

            for j in range(100):
                theta = 2 * np.pi * j / 100
                x = self.x_center + radius * np.cos(theta)
                y = self.y_center + radius * np.sin(theta)
                glVertex2f(x, y)

            glEnd()
            
            #glLineWidth(BAR_THICKNESS)
            #glBegin(GL_LINES)
            #glVertex2f(x0, y0)
            #glVertex2f(x1, y1)

    def hsv_to_rgb(self, h, s, v):
        i = int(h * 6)
        f = h * 6 - i
        p = v * (1 - s)
        q = v * (1 - f * s)
        t = v * (1 - (1 - f) * s)
        i = i % 6
        if i == 0:
            return v, t, p
        if i == 1:
            return q, v, p
        if i == 2:
            return p, v, t
        if i == 3:
            return p, q, v
        if i == 4:
            return t, p, v
        if i == 5:
            return v, p, q


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self):
        super().__init__()
        self.processor = AudioProcessor()
        self.visualizer = GLVisualizer(self.processor)
        self.setCentralWidget(self.visualizer)
        self.setWindowTitle("Raw OpenGL Audio Visualizer")
        self.resize(800, 800)
        # Make the window always on top
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)

        sd.InputStream(device=self.processor.device_index,
                       channels=2,
                       samplerate=SAMPLE_RATE,
                       blocksize=CHUNK,
                       callback=self.processor.process_audio
                       ).start()
    
    def display_mode(self):
        # Make the window frameless
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        # Make the window transparent using the alpha channel
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        # Let the cursor pass through the window
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.show()
        make_window_clickthrough(self)

    def window_mode(self):
        # Reset the window flags to default
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self.show()
        make_window_clickable(self)

    def keyPressEvent(self, event):
        key = event.key()
        if key == QtCore.Qt.Key_P:
            if self.windowFlags() & QtCore.Qt.FramelessWindowHint:
                self.window_mode()
            else:
                self.display_mode()
        elif key == QtCore.Qt.Key_Escape:
            self.close()

if __name__ == '__main__':
    fmt = QtGui.QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    QtGui.QSurfaceFormat.setDefaultFormat(fmt)
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

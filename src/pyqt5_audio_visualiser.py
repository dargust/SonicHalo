# refactored_audio_visualizer.py
import sys
import numpy as np
import sounddevice as sd
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import QOpenGLWidget
from OpenGL.GL import *
import ctypes

# === Constants === #
BAR_COUNT = 36
SAMPLE_RATE = 44100
CHUNK = 512
UPDATE_INTERVAL = 16
BAR_THICKNESS = 0.040
MIN_BAR_HEIGHT = 0.03
MIN_FREQ = 50
MAX_FREQ = 12000
VOCAL_MIN = 155
VOCAL_MAX = 1100
HARMONIC_THRESHOLD = 0.15
MIN_MAX_SEEN = 10.0

# === Utility Functions === #
def get_weighted_band_edges(min_freq, max_freq, band_count, low_bias=2.5):
    t = np.linspace(0, 1, band_count + 1)
    t_weighted = t ** low_bias
    return min_freq * (max_freq / min_freq) ** t_weighted

def make_window_clickthrough(window):
    hwnd = int(window.winId())
    style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
    style |= 0x80000 | 0x20
    ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)

def make_window_clickable(window):
    hwnd = int(window.winId())
    style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
    style &= ~(0x80000 | 0x20)
    ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)

class AudioProcessor:
    def __init__(self):
        self.amps = np.zeros(BAR_COUNT)
        self.smoothed_amps = np.zeros(BAR_COUNT)
        self.fall_velocity = np.zeros(BAR_COUNT)
        self.device_index = self.find_device()
        self.max_seen = 10.0
        self.highlighted_idx = None
        self.highlighted_freq = None
        self.is_harmonic = False

    def find_device(self):
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if 'CABLE Output' in dev['name'] and dev['max_input_channels'] == 16:
                return i
        return None

    def analyze_chunk(self, indata, frames, time_info, status):
        mono = np.mean(indata, axis=1)
        N = 4096 * 2
        fft = np.abs(np.fft.rfft(mono, n=N))
        freqs = np.fft.rfftfreq(N, d=1 / SAMPLE_RATE)

        band_edges = get_weighted_band_edges(MIN_FREQ, MAX_FREQ, BAR_COUNT, low_bias=0.8)
        band_centers = np.sqrt(band_edges[:-1] * band_edges[1:])
        bin_indices = np.digitize(freqs, band_edges) - 1

        amps = np.array([
            np.mean(fft[bin_indices == i]) if np.any(bin_indices == i) else 0
            for i in range(BAR_COUNT)
        ])

        amps *= np.sqrt(band_centers / band_centers[0])

        if np.max(amps) < 1e-4:
            amps = np.zeros(BAR_COUNT)

        max_fft = np.max(amps)
        if max_fft > self.max_seen:
            self.max_seen = max_fft
        else:
            self.max_seen = max(self.max_seen * 0.995, MIN_MAX_SEEN)

        amps = np.clip(amps / self.max_seen, 0, 1)
        vocal_indices = np.where((band_centers >= VOCAL_MIN) & (band_centers <= VOCAL_MAX))[0]

        if len(vocal_indices) and np.max(amps[vocal_indices]) > 0.1:
            self.highlighted_idx = vocal_indices[np.argmax(amps[vocal_indices])]
        else:
            self.highlighted_idx = None

        self.amps = amps
        self.highlighted_freq = self.find_peak_frequency(fft, freqs, band_edges, band_centers)
        self.is_harmonic = self.detect_harmonics(amps, band_centers)

    def find_peak_frequency(self, fft, freqs, band_edges, band_centers):
        if self.highlighted_idx is None:
            return None
        start, end = band_edges[self.highlighted_idx:self.highlighted_idx + 2]
        bins = np.where((freqs >= start) & (freqs < end))[0]
        if bins.size:
            return freqs[bins[np.argmax(fft[bins])]]
        return band_centers[self.highlighted_idx]

    def detect_harmonics(self, amps, band_centers):
        if self.highlighted_idx is None:
            return False
        f0 = band_centers[self.highlighted_idx]
        for h in range(2, 5):
            harmonic_freq = f0 * h
            if harmonic_freq > band_centers[-1]:
                break
            idx = np.argmin(np.abs(band_centers - harmonic_freq))
            if amps[idx] > HARMONIC_THRESHOLD:
                return True
        return False

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
        self.rotation_offset = 0.0
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.timer = QtCore.QTimer(timeout=self.update)
        self.timer.start(UPDATE_INTERVAL)
        self.peak_marker_angle = None
        self.peak_marker_opacity = 0.0

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
        self.processor.update_smoothed()
        glClearColor(0, 0, 0, 0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        amps = self.processor.smoothed_amps
        bass_energy = np.prod(amps[:min(4, BAR_COUNT)])
        self.rotation_offset += min(bass_energy * 0.2, 0.02) + 0.003
        self.rotation_offset %= 2 * np.pi

        for i in range(BAR_COUNT):
            shifted_index = (i + (self.rotation_offset * BAR_COUNT / (2 * np.pi))) % BAR_COUNT
            idx0 = int(np.floor(shifted_index))
            idx1 = (idx0 + 1) % BAR_COUNT
            frac = shifted_index - idx0
            value = np.interp(frac, [0, 1], [amps[idx0], amps[idx1]])
            value = max(value, MIN_BAR_HEIGHT)
            angle = (2 * np.pi * i) / BAR_COUNT + 1.5 * np.pi + self.rotation_offset

            hue = 0.33 * (1 - value)
            r, g, b = self.hsv_to_rgb(hue, 1, 1)
            self.draw_bar(angle, value, (r/5, g/5, b/5))

        self.draw_peak_circle()

    def draw_bar(self, angle, value, color):
        base = 0.3 - value * 0.05
        tip = base + value * 0.5
        x0, y0 = np.sin(angle) * base, np.cos(angle) * base
        x1, y1 = np.sin(angle) * tip, np.cos(angle) * tip
        dx, dy = BAR_THICKNESS / 2 * np.cos(-angle), BAR_THICKNESS / 2 * np.sin(-angle)

        vertices = [
            (x0 - dx, y0 - dy), (x0 + dx, y0 + dy),
            (x1 + dx, y1 + dy), (x1 - dx, y1 - dy)
        ]

        glBegin(GL_POLYGON)
        glColor4f(*color, 0.2)
        for x, y in vertices:
            glVertex2f(x, y)
        glEnd()

    def draw_peak_circle(self):
        if self.processor.highlighted_freq and self.processor.is_harmonic:
            centers = np.sqrt(
                get_weighted_band_edges(MIN_FREQ, MAX_FREQ, BAR_COUNT, 0.8)[:-1] *
                get_weighted_band_edges(MIN_FREQ, MAX_FREQ, BAR_COUNT, 0.8)[1:]
            )
            idx = np.argmin(np.abs(centers - self.processor.highlighted_freq))
            target_angle = (2 * np.pi * idx) / BAR_COUNT + 1.5 * np.pi

            if self.peak_marker_angle is None:
                self.peak_marker_angle = target_angle
            self.peak_marker_angle += (target_angle - self.peak_marker_angle) * 0.06
            self.peak_marker_opacity = 0.2
            self.last_valid_marker = (self.peak_marker_angle, QtCore.QTime.currentTime())
        else:
            if hasattr(self, 'last_valid_marker'):
                elapsed = self.last_valid_marker[1].msecsTo(QtCore.QTime.currentTime()) / 1000.0
                fade_duration = 1.5  # seconds
                if elapsed < fade_duration:
                    self.peak_marker_angle = self.last_valid_marker[0]
                    self.peak_marker_opacity = 0.2 * (1 - (elapsed / fade_duration))
                else:
                    self.peak_marker_opacity = 0.0
                    return
            else:
                self.peak_marker_opacity = max(0.0, self.peak_marker_opacity - 0.005)
                return

        x = np.sin(self.peak_marker_angle) * 0.22
        y = np.cos(self.peak_marker_angle) * 0.22

        glBegin(GL_POLYGON)
        glColor4f(0.3 * self.peak_marker_opacity, 0.6 * self.peak_marker_opacity, 1 * self.peak_marker_opacity, self.peak_marker_opacity)
        for j in range(24):
            theta = 2 * np.pi * j / 24
            glVertex2f(x + 0.02 * np.cos(theta), y + 0.02 * np.sin(theta))
        glEnd()


    @staticmethod
    def hsv_to_rgb(h, s, v):
        i = int(h * 6)
        f = h * 6 - i
        p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
        i %= 6
        return [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.processor = AudioProcessor()
        self.visualizer = GLVisualizer(self.processor)
        self.setCentralWidget(self.visualizer)
        self.setWindowTitle("OpenGL Audio Visualizer")
        self.resize(800, 800)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)

        sd.InputStream(device=self.processor.device_index,
                       channels=2,
                       samplerate=SAMPLE_RATE,
                       blocksize=CHUNK,
                       callback=self.processor.analyze_chunk).start()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_P:
            if self.windowFlags() & QtCore.Qt.FramelessWindowHint:
                self.window_mode()
            else:
                self.display_mode()
        elif event.key() == QtCore.Qt.Key_Escape:
            self.close()

    def display_mode(self):
        '''self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.show()
        make_window_clickthrough(self)'''
        pos = self.pos()  # Save position
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.show()
        # offset pos to correct the movement
        pos.setX(pos.x() - 0)
        pos.setY(pos.y() - 1)
        self.move(pos)  # Restore position
        make_window_clickthrough(self)

    def window_mode(self):
        '''
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self.show()
        make_window_clickable(self)'''
        pos = self.pos()
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self.show()
        # offset pos to correct the movement
        pos.setX(pos.x() - 8)
        pos.setY(pos.y() - 30)
        self.move(pos)
        make_window_clickable(self)

if __name__ == '__main__':
    fmt = QtGui.QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    QtGui.QSurfaceFormat.setDefaultFormat(fmt)
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

import sys
import numpy as np
import sounddevice as sd
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import QOpenGLWidget
from OpenGL.GL import *
import ctypes

# === Constants === #
BAR_COUNT = 32
SAMPLE_RATE = 44100
CHUNK = 2048
UPDATE_INTERVAL = 16
BAR_THICKNESS = 0.036
MIN_BAR_HEIGHT = 0.03
MIN_FREQ = 50
MAX_FREQ = 12000
MAX_OPACITY = 0.2

# === Utility Functions === #
def get_weighted_band_edges(min_freq, max_freq, band_count, low_bias=2.5):
    t = np.linspace(0, 1, band_count + 1)
    t_weighted = t ** low_bias
    return min_freq * (max_freq / min_freq) ** t_weighted

class AudioProcessor:
    def __init__(self):
        self.amps = np.zeros(BAR_COUNT)
        self.smoothed_amps = np.zeros(BAR_COUNT)
        self.fall_velocity = np.zeros(BAR_COUNT)
        self.device_index = None

    def analyze_chunk(self, indata, frames, time_info, status):
        mono = np.mean(indata, axis=1)
        N = 4096 * 2
        fft = np.abs(np.fft.rfft(mono, n=N))
        freqs = np.fft.rfftfreq(N, d=1 / SAMPLE_RATE)

        band_edges = get_weighted_band_edges(MIN_FREQ, MAX_FREQ, BAR_COUNT, 0.8)
        bin_indices = np.digitize(freqs, band_edges) - 1

        amps = np.array([
            np.mean(fft[bin_indices == i]) if np.any(bin_indices == i) else 0
            for i in range(BAR_COUNT)
        ])

        amps = np.clip(amps / (np.max(amps) + 1e-6), 0, 1)
        self.amps = amps

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
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.timer = QtCore.QTimer(timeout=self.update)
        self.timer.start(UPDATE_INTERVAL)
        self.bar_opacity = MAX_OPACITY
        self.round_segments = 12
        self.angle_array = np.linspace(0, np.pi, self.round_segments)

    def initializeGL(self):
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_COLOR_ARRAY)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

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

        amps = np.maximum(self.processor.smoothed_amps, MIN_BAR_HEIGHT)
        angles = (2 * np.pi * np.arange(BAR_COUNT) / BAR_COUNT) + 1.5 * np.pi
        sines = np.sin(angles)
        cosines = np.cos(angles)
        bases = 0.3 - amps * 0.05
        tips = bases + amps * 0.5
        dxs = BAR_THICKNESS / 2 * cosines
        dys = BAR_THICKNESS / 2 * sines

        quads = []
        colors = []

        for i in range(BAR_COUNT):
            x0 = sines[i] * bases[i]
            y0 = cosines[i] * bases[i]
            x1 = sines[i] * tips[i]
            y1 = cosines[i] * tips[i]
            dx = -dxs[i]
            dy = dys[i]
            peak_dx = -dxs[i] * (1 + amps[i] * 2.2)
            peak_dy = dys[i] * (1 + amps[i] * 2.2)

            quad = [
                (x0 - dx, y0 - dy), (x0 + dx, y0 + dy),
                (x1 + peak_dx, y1 + peak_dy), (x1 - peak_dx, y1 - peak_dy)
            ]
            quads.extend(quad)

            hue = 0.33 * (1 - amps[i])
            r, g, b = self.hsv_to_rgb(hue, 1, 1)
            colors.extend([(r, g, b, self.bar_opacity)] * 4)

        vertex_array = np.array(quads, dtype=np.float32)
        color_array = np.array(colors, dtype=np.float32)
        glVertexPointer(2, GL_FLOAT, 0, vertex_array)
        glColorPointer(4, GL_FLOAT, 0, color_array)
        glDrawArrays(GL_QUADS, 0, BAR_COUNT * 4)
        glDrawArrays(GL_POLYGON, BAR_COUNT * 4, len(vertex_array) - BAR_COUNT * 4)

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
        self.setWindowTitle("OpenGL Audio Visualizer (Fully Optimized)")
        self.resize(800, 800)

        sd.InputStream(
            channels=2,
            samplerate=SAMPLE_RATE,
            blocksize=CHUNK,
            callback=self.processor.analyze_chunk
        ).start()

if __name__ == '__main__':
    fmt = QtGui.QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    QtGui.QSurfaceFormat.setDefaultFormat(fmt)
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

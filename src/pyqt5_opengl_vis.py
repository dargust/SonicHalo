# Fully integrated optimized version of the visualizer
import sys
import numpy as np
import sounddevice as sd
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import QOpenGLWidget
from OpenGL.GL import *
import ctypes
import logging

# === Constants === #
WINDOW_WIDTH = 600
WINDOW_HEIGHT = WINDOW_WIDTH
BAR_COUNT = 28
SAMPLE_RATE = 44100
CHUNK = 2048
UPDATE_INTERVAL = 16  # Reduced to ~30 FPS
MIN_FREQ = 50
MAX_FREQ = 12000
MIN_MAX_SEEN = 10.0
BAR_THICKNESS = 0.04
MAX_OPACITY = 0.4

# === PID Controller === #
def pid_controller(setpoint, pv, kp, ki, kd, previous_error, integral, dt):
    error = setpoint - pv
    integral += error * dt
    derivative = (error - previous_error) / dt if dt > 0 else 0
    control = kp * error + ki * integral + kd * derivative
    return control, error, integral

# === Audio Processor === #
class AudioProcessor:
    def __init__(self):
        self.amps = np.zeros(BAR_COUNT)
        self.smoothed_amps = np.zeros(BAR_COUNT)
        self.fall_velocity = np.zeros(BAR_COUNT)
        self.device_index = self.find_device()
        self.max_seen = 10.0
        self.error = 0
        self.integral = 0
        self.delta = 16

    def find_device(self):
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if 'CABLE Output' in dev['name'] and dev['max_input_channels'] == 16:
                return i
        return None

    def analyze_chunk(self, indata, frames, time_info, status):
        mono = np.mean(indata, axis=1)
        N = 2048
        fft = np.abs(np.fft.rfft(mono, n=N))
        freqs = np.fft.rfftfreq(N, d=1 / SAMPLE_RATE)

        band_edges = np.geomspace(MIN_FREQ, MAX_FREQ, BAR_COUNT + 1)
        band_centers = np.sqrt(band_edges[:-1] * band_edges[1:])
        bin_indices = np.digitize(freqs, band_edges) - 1

        amps = np.zeros(BAR_COUNT)
        for i in range(BAR_COUNT):
            idxs = np.where(bin_indices == i)[0]
            if idxs.size > 0:
                amps[i] = np.mean(fft[idxs])

        amps *= np.sqrt(band_centers / band_centers[0])

        if np.max(amps) < 1e-4:
            amps = np.zeros(BAR_COUNT)

        max_fft = np.max(amps)
        control, error, integral = pid_controller(max_fft, self.max_seen, 2.0, 0.0, 0.02, self.error, self.integral, self.delta / 1000)
        self.max_seen += control * self.delta / 1000
        self.max_seen = max(self.max_seen, MIN_MAX_SEEN)
        self.error = error
        self.integral = integral

        amps = np.clip(amps / self.max_seen, 0, 1)
        self.amps = amps

    def update_smoothed(self):
        faster = self.amps > self.smoothed_amps
        self.fall_velocity = np.where(faster, 0, self.fall_velocity + 0.003)
        fall_amounts = np.where(faster, 0, np.maximum(0.005, self.fall_velocity))
        self.smoothed_amps = np.where(faster, self.amps, self.smoothed_amps - fall_amounts)
        self.smoothed_amps = np.clip(self.smoothed_amps, 0, 1)

# === OpenGL Visualizer === #
class GLVisualizer(QOpenGLWidget):
    def __init__(self, processor, parent=None):
        super().__init__(parent)
        self.processor = processor
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.timer = QtCore.QTimer(timeout=self.update)
        self.timer.start(UPDATE_INTERVAL)

    def initializeGL(self):
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
        amps = self.processor.smoothed_amps
        for i in range(BAR_COUNT):
            angle = (2 * np.pi * i) / BAR_COUNT
            height = amps[i] * 0.5
            if height < 0.01:
                continue
            x0 = np.sin(angle) * 0.3
            y0 = np.cos(angle) * 0.3
            x1 = np.sin(angle) * (0.3 + height)
            y1 = np.cos(angle) * (0.3 + height)
            self.draw_bar(x0, y0, x1, y1, angle, amps[i])

    def draw_bar(self, x0, y0, x1, y1, angle, value):
        dx = BAR_THICKNESS * np.cos(-angle) / 2
        dy = BAR_THICKNESS * np.sin(-angle) / 2
        glBegin(GL_QUADS)
        glColor4f(1.0 - value, value, 0.2, MAX_OPACITY)
        glVertex2f(x0 - dx, y0 - dy)
        glVertex2f(x0 + dx, y0 + dy)
        glVertex2f(x1 + dx, y1 + dy)
        glVertex2f(x1 - dx, y1 - dy)
        glEnd()

# === Main Window === #
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.processor = AudioProcessor()
        self.visualizer = GLVisualizer(self.processor)
        self.setCentralWidget(self.visualizer)
        self.setWindowTitle("Optimized Audio Visualizer")
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        sd.InputStream(device=self.processor.device_index,
                       channels=2,
                       samplerate=SAMPLE_RATE,
                       blocksize=CHUNK,
                       callback=self.processor.analyze_chunk).start()

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    fmt = QtGui.QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    QtGui.QSurfaceFormat.setDefaultFormat(fmt)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

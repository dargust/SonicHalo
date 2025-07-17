import sys
import numpy as np
import sounddevice as sd
from PyQt5 import QtWidgets, QtGui, QtCore, QtOpenGL
from OpenGL.GL import *
from PyQt5.QtOpenGL import QGLWidget

BAR_COUNT = 36
SAMPLE_RATE = 44100
CHUNK = 512
UPDATE_INTERVAL = 16

class AudioProcessor:
    def __init__(self):
        self.amps = np.zeros(BAR_COUNT)
        self.band_centers = None
        self.highlighted_idx = None
        self.device_index = self.find_device()

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
        N = 4096 * 2
        fft = np.abs(np.fft.rfft(mono, n=N))
        freqs = np.fft.rfftfreq(N, d=1/SAMPLE_RATE)

        min_freq = 50
        max_freq = 12000
        band_edges = self.get_weighted_band_edges(min_freq, max_freq, BAR_COUNT, 0.8)
        amps = np.zeros(BAR_COUNT)
        self.band_centers = np.sqrt(band_edges[:-1] * band_edges[1:])
        bin_indices = np.digitize(freqs, band_edges) - 1

        for i in range(BAR_COUNT):
            bins = np.where(bin_indices == i)[0]
            if len(bins) > 0:
                amps[i] = np.mean(fft[bins])

        amps *= np.sqrt(self.band_centers / self.band_centers[0])
        amps = np.clip(amps / np.max(amps + 1e-6), 0, 1)
        self.amps = amps

        vocal_min = 155
        vocal_max = 1100
        vocal_band_indices = np.where((self.band_centers >= vocal_min) & (self.band_centers <= vocal_max))[0]
        if len(vocal_band_indices) > 0:
            vocal_amps = amps[vocal_band_indices]
            if np.max(vocal_amps) > 0.1:
                self.highlighted_idx = vocal_band_indices[np.argmax(vocal_amps)]
            else:
                self.highlighted_idx = None
        else:
            self.highlighted_idx = None

    def start(self):
        sd.InputStream(device=self.device_index, channels=2, samplerate=SAMPLE_RATE, blocksize=CHUNK,
                       callback=self.process_audio).start()


class GLVisualizer(QGLWidget):
    def __init__(self, processor, parent=None):
        super().__init__(parent)
        self.processor = processor
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(UPDATE_INTERVAL)

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
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        amps = self.processor.amps

        glColor3f(0.2, 1.0, 0.5)
        glLineWidth(2.0)
        glBegin(GL_LINES)
        for i in range(BAR_COUNT):
            angle = 2 * np.pi * i / BAR_COUNT + np.pi
            base_radius = 0.4
            tip_radius = base_radius + amps[i] * 0.5
            x0 = np.cos(angle) * base_radius
            y0 = np.sin(angle) * base_radius
            x1 = np.cos(angle) * tip_radius
            y1 = np.sin(angle) * tip_radius
            glVertex2f(x0, y0)
            glVertex2f(x1, y1)
        glEnd()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.processor = AudioProcessor()
        self.visualizer = GLVisualizer(self.processor)
        self.setCentralWidget(self.visualizer)
        self.setWindowTitle("Raw OpenGL Audio Visualizer")
        self.resize(800, 800)
        self.processor.start()

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

# PyQt6 + GPU Shader Audio Visualizer (Modern OpenGL)
import sys
import numpy as np
import sounddevice as sd
from PyQt6 import QtWidgets, QtGui, QtCore, QtOpenGL
from PyQt6.QtGui import QSurfaceFormat, QOpenGLShader, QOpenGLShaderProgram, QMatrix4x4
from PyQt6.QtWidgets import QOpenGLWidget
from PyQt6.QtOpenGL import QOpenGLFunctions
from OpenGL.GL import *

BAR_COUNT = 28
SAMPLE_RATE = 48000
CHUNK = 2048
UPDATE_INTERVAL = 16

VERTEX_SHADER = """
#version 330 core
layout(location = 0) in float index;
uniform float amplitudes[""" + str(BAR_COUNT) + """];
uniform float rotation_offset;
uniform float opacity;
uniform int bar_count;
uniform float bar_thickness;
uniform mat4 projection;

out float amp;

void main() {
    float i = index;
    float angle = (6.283185 * i / float(bar_count)) + 4.712388 + rotation_offset;
    float radius = 0.3 + amplitudes[int(i)] * 0.5;
    gl_Position = projection * vec4(sin(angle) * radius, cos(angle) * radius, 0.0, 1.0);
    amp = amplitudes[int(i)];
}
"""

FRAGMENT_SHADER = """
#version 330 core
in float amp;
uniform float opacity;
out vec4 fragColor;

vec3 hsv2rgb(float h, float s, float v) {
    float c = v * s;
    float x = c * (1.0 - abs(mod(h * 6.0, 2.0) - 1.0));
    float m = v - c;
    vec3 rgb;
    if (h < 1.0/6.0) rgb = vec3(c, x, 0.0);
    else if (h < 2.0/6.0) rgb = vec3(x, c, 0.0);
    else if (h < 3.0/6.0) rgb = vec3(0.0, c, x);
    else if (h < 4.0/6.0) rgb = vec3(0.0, x, c);
    else if (h < 5.0/6.0) rgb = vec3(x, 0.0, c);
    else rgb = vec3(c, 0.0, x);
    return rgb + vec3(m);
}

void main() {
    float hue = amp;
    float sat = 1.0;
    float val = 1.0;
    vec3 rgb = hsv2rgb(hue, sat, val);
    fragColor = vec4(rgb, opacity);
}
"""

class AudioProcessor:
    def __init__(self):
        self.amps = np.zeros(BAR_COUNT)
        self.max_seen = 10.0
        self.device_index = self.find_device()

    def find_device(self):
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if 'CABLE Output' in dev['name'] and dev['max_input_channels'] >= 2:
                return i
        return None

    def analyze_chunk(self, indata, frames, time_info, status):
        mono = np.mean(indata, axis=1)
        N = 4096 * 2
        fft = np.abs(np.fft.rfft(mono, n=N))
        freqs = np.fft.rfftfreq(N, d=1/SAMPLE_RATE)
        band_edges = np.logspace(np.log10(50), np.log10(12000), BAR_COUNT + 1)
        bin_indices = np.digitize(freqs, band_edges) - 1
        amps = np.array([
            np.mean(fft[bin_indices == i]) if np.any(bin_indices == i) else 0
            for i in range(BAR_COUNT)
        ])
        amps /= np.max(amps) + 1e-8
        self.amps = amps

class GLVisualizer(QOpenGLWidget, QOpenGLFunctions):
    def __init__(self, processor):
        super().__init__()
        self.processor = processor
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(400, 400)
        self.program = None
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(UPDATE_INTERVAL)
        self.rotation_offset = 0.0

    def initializeGL(self):
        self.initializeOpenGLFunctions()
        self.program = QOpenGLShaderProgram()
        self.program.addShaderFromSourceCode(QOpenGLShader.ShaderType.Vertex, VERTEX_SHADER)
        self.program.addShaderFromSourceCode(QOpenGLShader.ShaderType.Fragment, FRAGMENT_SHADER)
        self.program.link()

        self.vbo = glGenBuffers(1)
        indices = np.arange(BAR_COUNT, dtype=np.float32)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

    def paintGL(self):
        glClearColor(0, 0, 0, 0)
        glClear(GL_COLOR_BUFFER_BIT)
        self.program.bind()
        glEnableVertexAttribArray(0)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glVertexAttribPointer(0, 1, GL_FLOAT, GL_FALSE, 0, None)

        amps = self.processor.amps.astype(np.float32)
        self.program.setUniformValueArray("amplitudes", amps.tolist(), 1)
        self.rotation_offset += 0.005
        self.program.setUniformValue("rotation_offset", self.rotation_offset)
        self.program.setUniformValue("opacity", 0.4)
        self.program.setUniformValue("bar_count", BAR_COUNT)
        self.program.setUniformValue("bar_thickness", 0.05)

        proj = QMatrix4x4()
        proj.ortho(-1, 1, -1, 1, -1, 1)
        self.program.setUniformValue("projection", proj)

        glDrawArrays(GL_POINTS, 0, BAR_COUNT)
        glDisableVertexAttribArray(0)
        self.program.release()

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.processor = AudioProcessor()
        self.visualizer = GLVisualizer(self.processor)
        self.setCentralWidget(self.visualizer)
        self.setWindowTitle("Shader-Based Audio Visualizer (PyQt6)")
        self.resize(400, 400)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.WindowStaysOnTopHint)

        sd.InputStream(device=self.processor.device_index,
                       channels=2,
                       samplerate=SAMPLE_RATE,
                       blocksize=CHUNK,
                       callback=self.processor.analyze_chunk).start()

if __name__ == '__main__':
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

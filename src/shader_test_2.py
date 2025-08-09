import numpy as np
import moderngl
from moderngl_window import WindowConfig, run_window_config
from moderngl_window.geometry import quad_fs
import sounddevice as sd

# === Audio Constants === #
BAR_COUNT = 32
SAMPLE_RATE = 44100
CHUNK = 2048
MIN_FREQ = 40
MAX_FREQ = 12000
MIN_MAX_SEEN = 10.0
VOCAL_MIN = 180
VOCAL_MAX = 1200


def get_weighted_band_edges(min_freq, max_freq, band_count, low_bias=2.5):
    t = np.linspace(0, 1, band_count + 1)
    t_weighted = t ** low_bias
    return min_freq * (max_freq / min_freq) ** t_weighted

# === Audio Processing === #
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
        self.detect_harmonics(amps, band_centers)

    def find_peak_frequency(self, fft, freqs, band_edges, band_centers):
        if self.highlighted_idx is None:
            return None
        start, end = band_edges[self.highlighted_idx:self.highlighted_idx + 2]
        bins = np.where((freqs >= start) & (freqs < end))[0]
        if bins.size:
            return freqs[bins[np.argmax(fft[bins])]]
        return band_centers[self.highlighted_idx]

    def detect_harmonics(self, amps, band_centers):
        vocal_range = (band_centers >= VOCAL_MIN) & (band_centers <= VOCAL_MAX)
        candidates = np.where((amps > 0.1) & vocal_range)[0]

        best_score = 0
        best_f0 = None

        for idx in candidates:
            f0 = band_centers[idx]
            harmonics_found = 0
            total_strength = 0

            for h in range(2, 4):  # check 2nd–4th harmonics
                harmonic_freq = f0 / h
                if harmonic_freq < VOCAL_MIN / 5:
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
            self.highlighted_freq = best_f0
            self.is_harmonic = True
        else:
            self.highlighted_freq = None
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

# === Visualizer === #
class ModernGLVisualizer(WindowConfig):
    window_size = (800, 800)
    resource_dir = 'src/shaders'
    title = "ModernGL Audio Visualizer"
    aspect_ratio = 1.0
    gl_version = (3, 3)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.quad = quad_fs()
        self.processor = AudioProcessor()
        import os
        print("Shader dir contents:", os.listdir(self.resource_dir))
        self.visualizer_shader = self.load_program(vertex_shader="visualizer.vert", fragment_shader="visualizer.frag")
        self.bloom_shader = self.load_program(vertex_shader="bloom.vert", fragment_shader="bloom.frag")

        self.offscreen_tex = self.ctx.texture(self.window_size, 4)
        self.offscreen_fbo = self.ctx.framebuffer(color_attachments=[self.offscreen_tex])

        sd.InputStream(
            channels=2,
            samplerate=SAMPLE_RATE,
            blocksize=CHUNK,
            callback=self.processor.analyze_chunk
        ).start()

    def on_render(self, time: float, frame_time: float):
        self.processor.update_smoothed()
        self.visualizer_shader['amps'].write(self.processor.smoothed_amps.astype('f4').tobytes())

        # Render to offscreen texture
        self.offscreen_fbo.use()
        self.ctx.clear(0.0, 0.0, 0.0)
        self.quad.render(self.visualizer_shader)

        self.ctx.screen.use()
        self.offscreen_tex.use(location=0)
        self.quad.render(self.bloom_shader)

if __name__ == '__main__':
    run_window_config(ModernGLVisualizer)

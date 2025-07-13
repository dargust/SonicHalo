import tkinter as tk
import numpy as np
import math
import colorsys
from scipy.stats import gmean

# === PARAMETERS ===
N_BINS = 64
N_FRAMES = 5

# === ANALYSIS FUNCTION ===
def analyze_fft_frames(fft_frames: np.ndarray, freqs: np.ndarray = None):
    magnitudes = np.mean(fft_frames, axis=0)
    prev_magnitudes = fft_frames[-2] if fft_frames.shape[0] >= 2 else magnitudes

    total_energy = np.sum(magnitudes)
    spectral_centroid = (np.sum(freqs * magnitudes) / np.sum(magnitudes)) if freqs is not None else None

    N = len(magnitudes)
    low = np.sum(magnitudes[:N//3])
    mid = np.sum(magnitudes[N//3:2*N//3])
    high = np.sum(magnitudes[2*N//3:])

    total = low + mid + high + 1e-6
    low_ratio = low / total
    mid_ratio = mid / total
    high_ratio = high / total

    flatness = gmean(magnitudes + 1e-6) / (np.mean(magnitudes) + 1e-6)
    flux = np.sum((magnitudes - prev_magnitudes) ** 2)

    peak_idx = np.argmax(magnitudes)
    peak_freq = freqs[peak_idx] if freqs is not None else peak_idx

    shape_params = {
        'radius': np.clip(total_energy / 1, 0.1, 2.0),
        'spikiness': np.clip(high_ratio * 5 + flux * 10, 0, 2),
        'roundness': 1.0 - flatness,
        'rotation_speed': np.clip(peak_freq / 1000, 0.1, 0.2),
        'color_hue': (spectral_centroid or peak_freq) % 360,
        'bass_bulge': low_ratio,
        'mid_wave': mid_ratio,
        'treble_twist': high_ratio,
        'flux': flux,
        'flatness': flatness,
        'dominant_freq': peak_freq
    }

    return shape_params

# === DRAW FUNCTION ===
def draw_audio_shape(canvas, shape_params, center_x, center_y, base_radius=100, num_points=128, rotation_angle=0):
    canvas.delete("visual")

    # Parameters with smoothing
    radius_scale = shape_params.get('radius', 1.0)
    spikiness = min(shape_params.get('spikiness', 0.0), 1.5)  # Cap it
    roundness = shape_params.get('roundness', 0.8)            # More round
    hue = shape_params.get('color_hue', 0) / 360
    rotation_speed = shape_params.get('rotation_speed', 0.0)

    low = shape_params.get('bass_bulge', 0.3)
    mid = shape_params.get('mid_wave', 0.3)
    high = shape_params.get('treble_twist', 0.3)

    # Color
    rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    fill_color = '#%02x%02x%02x' % tuple(int(c * 255) for c in rgb)

    points = []
    for i in range(num_points):
        angle = (2 * math.pi * i / num_points) + rotation_angle

        # Remove random noise, smooth wave patterns
        low_mod  = math.sin(i * 0.7 + rotation_angle) * low
        mid_mod  = math.sin(i * 1.5 + rotation_angle * 1.2) * mid
        high_mod = math.sin(i * 3.5 + rotation_angle * 2.0) * high

        combined_mod = (low_mod + mid_mod + high_mod)

        # Damp overall deformation
        deformation_strength = 0.5  # Try lowering this (e.g., 0.3) for smoother
        radius = base_radius * radius_scale * (1.0 + combined_mod * deformation_strength * (1.0 - roundness))

        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        points.extend([x, y])

    canvas.create_polygon(points, fill=fill_color, outline="", tags="visual")
    return (rotation_angle + rotation_speed * 0.03) % (2 * math.pi)

# === SIMULATION + LOOP ===
def update_visual():
    global rotation_angle, fft_frames

    # Simulate new FFT data (replace with real FFT later)
    new_frame = np.abs(np.random.randn(N_BINS)) * np.hanning(N_BINS)
    fft_frames.pop(0)
    fft_frames.append(new_frame)
    frames_np = np.vstack(fft_frames)

    freqs = np.linspace(20, 2000, N_BINS)  # Simulated frequency bins
    shape_params = analyze_fft_frames(frames_np, freqs)

    rotation_angle = draw_disconnected_shapes(canvas, shape_params, 100, 100)
    root.after(33, update_visual)

if __name__ == "__main__":
    # === MAIN SETUP ===
    root = tk.Tk()
    root.title("Audio Visualizer Shape (Simulated)")
    canvas = tk.Canvas(root, width=500, height=500, bg="black")
    canvas.pack()

    rotation_angle = 0.0
    fft_frames = [np.zeros(N_BINS) for _ in range(N_FRAMES)]

    update_visual()
    root.mainloop()

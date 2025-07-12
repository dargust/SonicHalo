import tkinter as tk
import numpy as np
import sounddevice as sd
import threading
import time
import colorsys
import asyncio
import sys
import cli_thread
import ctypes

print(f"System platform: {sys.platform}")
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

# Params
BAR_COUNT = 36
BAR_WIDTH = 16
BAR_SPACING = 5
BAR_MAX_HEIGHT = 200
UPDATE_INTERVAL = 16  # ms
SAMPLE_RATE = 44100
CHUNK = 512
USE_HARMONIC_CHECK = True

# Automatically select the desired audio device
def find_cable_output_device():
    if ON_WINDOWS:
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            print(f"Device {i}: {device['name']} - Inputs: {device['max_input_channels']}, Outputs: {device['max_output_channels']}")
            if 'CABLE Output' in device['name'] and device['max_input_channels'] == 16 and device['max_output_channels'] == 0:
                print(f"Found usable device: {device['name']} (Index: {i})")
                return i
    return None

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

DEVICE_INDEX = find_cable_output_device()
if DEVICE_INDEX is None:
    raise RuntimeError("Could not find 'CABLE Output ... (16 in, 0 out)' audio device.")

class AudioVisualizer(tk.Canvas):
    def __init__(self, master, **kwargs):
        self.ring_radius = 65  # Size of the ring
        self.bar_length_max = 100  # How far bars can extend from the ring
        self.bar_width = 10
        self.center_x = self.ring_radius + self.bar_length_max + 30
        self.center_y = self.ring_radius + self.bar_length_max + 30
        width = self.center_x * 2
        height = self.center_y * 2
        super().__init__(
            master,
            width=width,
            height=height,
            bg='black',
            highlightthickness=0,
            **kwargs
        )
        self.pack()
        self.running = True
        self.after(UPDATE_INTERVAL, self.update_bars)
        self.amps = np.zeros(BAR_COUNT)
        self.display_amps = np.zeros(BAR_COUNT)
        self.fall_velocity = np.zeros(BAR_COUNT)
        self.fall_acceleration = 0.006
        self.fall_speed_min = 0.01
        self.highlighted_bar = None
        self.highlighted_bar_pos = None
        self.highlighted_bar_target = None
        self.highlighted_bar_speed = 0.10
        self.is_harmonic = False
        self.band_centers = None
        # Create bar objects (lines)
        self.bars = [self.create_line(0,0,0,0, width=self.bar_width, fill='lime') for _ in range(BAR_COUNT)]
        # Draw the ring
        #self.ring_id = self.create_oval(
        #    self.center_x - self.ring_radius, self.center_y - self.ring_radius,
        #    self.center_x + self.ring_radius, self.center_y + self.ring_radius,
        #    outline="#444", width=6
        #)
        self.freq_marker_id = None
        self.freq_marker_angle = None
        self.freq_marker_target_angle = None
        self.freq_marker_speed = 0.12

    def set_amplitudes(self, amps):
        self.amps = amps

    def set_band_centers(self, band_centers):
        self.band_centers = band_centers

    def set_highlighted_bar(self, index):
        self.highlighted_bar_target = index
        if self.highlighted_bar_pos is None and index is not None:
            self.highlighted_bar_pos = float(index)

    def set_harmonic(self, value):
        self.is_harmonic = value

    def set_highlighted_freq(self, freq):
        if self.band_centers is None or freq is None:
            self.freq_marker_target_angle = None
            return
        # Map freq to angle
        min_freq = self.band_centers[0]
        max_freq = self.band_centers[-1]
        low_bias = 0.8
        log_ratio = np.log(max_freq / min_freq)
        t = np.log(freq / min_freq) / log_ratio
        t_weighted = t ** (1 / low_bias)
        angle = t_weighted * 2 * np.pi + np.pi  # Start from left side
        self.freq_marker_target_angle = angle
        if self.freq_marker_angle is None:
            self.freq_marker_angle = angle

    def update_bars(self):
        # Animate highlighted bar
        if self.highlighted_bar_target is not None:
            if self.highlighted_bar_pos is None:
                self.highlighted_bar_pos = float(self.highlighted_bar_target)
            else:
                self.highlighted_bar_pos += (
                    self.highlighted_bar_target - self.highlighted_bar_pos
                ) * self.highlighted_bar_speed
        elif self.highlighted_bar_pos is not None:
            self.highlighted_bar_pos = None

        # Animate amplitudes
        MIN_BAR_VALUE = 0.05  # Minimum bar amplitude (0-1 scale)
        for i, target in enumerate(self.amps):
            current = self.display_amps[i]
            if target > current:
                self.display_amps[i] = max(target, MIN_BAR_VALUE)
                self.fall_velocity[i] = 0.00
            else:
                self.fall_velocity[i] += self.fall_acceleration
                fall_amount = max(self.fall_speed_min, self.fall_velocity[i])
                self.display_amps[i] = max(MIN_BAR_VALUE if current > 0 else 0, current - fall_amount)

        # Draw bars around the ring
        # Smooth the wrap by averaging the first and second-to-last bar for the last bar
        if BAR_COUNT > 2:
            self.display_amps[-1] = (self.display_amps[0] + self.display_amps[-2]) / 2

        for i in range(BAR_COUNT):
            value = min(max(self.display_amps[i], 0), 1)
            angle = (2 * np.pi * i) / BAR_COUNT + np.pi  # Start from left side
            x0 = self.center_x + self.ring_radius * np.cos(angle)
            y0 = self.center_y + self.ring_radius * np.sin(angle)
            x1 = self.center_x + (self.ring_radius + value * self.bar_length_max) * np.cos(angle)
            y1 = self.center_y + (self.ring_radius + value * self.bar_length_max) * np.sin(angle)
            # Color logic
            hue = 0.33 * (1 - value)
            rgb = colorsys.hsv_to_rgb(hue, 1.0, 0.7)
            base_r, base_g, base_b = [int(255 * c) for c in rgb]
            blue_strength = 0
            if self.is_harmonic and self.highlighted_bar_pos is not None:
                dist = abs(i - self.highlighted_bar_pos)
                if dist < 1.5:
                    blue_strength = int(255 * (1 - dist / 1.5))
            r = min(base_r, 255)
            g = min(base_g, 255)
            b = min(base_b + blue_strength, 255)
            hex_color = f'#{r:02x}{g:02x}{b:02x}'
            self.coords(self.bars[i], x0, y0, x1, y1)
            self.itemconfig(self.bars[i], fill=hex_color)

        # --- Frequency marker update ---
        if self.freq_marker_target_angle is not None:
            if self.freq_marker_angle is None:
                self.freq_marker_angle = self.freq_marker_target_angle
            else:
                self.freq_marker_angle += (self.freq_marker_target_angle - self.freq_marker_angle) * self.freq_marker_speed
            angle = self.freq_marker_angle
            x = self.center_x + (self.ring_radius + 15) * np.cos(angle) # + self.bar_length_max + 15) * np.cos(angle)
            y = self.center_y + (self.ring_radius + 15) * np.sin(angle) # + self.bar_length_max + 15) * np.sin(angle)
            r = 8
            if self.freq_marker_id is None:
                self.freq_marker_id = self.create_oval(x - r, y - r, x + r, y + r, fill="#fff", outline="#222", width=2)
            else:
                self.coords(self.freq_marker_id, x - r, y - r, x + r, y + r)
                self.itemconfig(self.freq_marker_id, state="normal")
        else:
            if self.freq_marker_id is not None:
                self.itemconfig(self.freq_marker_id, state="hidden")

        if self.running:
            self.after(UPDATE_INTERVAL, self.update_bars)

    def stop(self):
        self.running = False

def audio_thread(visualizer):
    max_seen = [1e-3]
    last_process = [0]
    MIN_INTERVAL = 1/60

    def callback(indata, frames, time_info, status):
        if status:
            return
        now = time.time()
        if now - last_process[0] < MIN_INTERVAL:
            return
        last_process[0] = now

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

        if max_fft > max_seen[0]:
            max_seen[0] = max_fft
        else:
            max_seen[0] *= decay_rate
            if max_seen[0] < MIN_MAX_SEEN:
                max_seen[0] = MIN_MAX_SEEN

        vocal_min = 155
        vocal_max = 1100
        vocal_band_indices = np.where((band_centers >= vocal_min) & (band_centers <= vocal_max))[0]
        if max_seen[0] < 1e-3 or len(vocal_band_indices) == 0:
            amps = np.zeros(BAR_COUNT)
            loudest_idx = None
        else:
            amps = np.clip(amps / max_seen[0], 0, 1)
            vocal_amps = amps[vocal_band_indices]
            if np.max(vocal_amps) > 0.1:
                loudest_idx = vocal_band_indices[np.argmax(vocal_amps)]
            else:
                loudest_idx = None
        visualizer.set_amplitudes(amps)
        visualizer.set_highlighted_bar(loudest_idx)
        visualizer.set_band_centers(band_centers)

        # Find the true FFT peak frequency in the vocal range
        if loudest_idx is not None:
            # Get the frequency range for the loudest band
            band_start = band_edges[loudest_idx]
            band_end = band_edges[loudest_idx + 1]
            # Find FFT bins within this band
            bins_in_band = np.where((freqs >= band_start) & (freqs < band_end))[0]
            if len(bins_in_band) > 0:
                peak_bin = bins_in_band[np.argmax(fft[bins_in_band])]
                highlighted_freq = freqs[peak_bin]
            else:
                highlighted_freq = band_centers[loudest_idx]
        else:
            highlighted_freq = None

        visualizer.set_highlighted_freq(highlighted_freq)

        if USE_HARMONIC_CHECK:
            if loudest_idx is not None:
                f0 = band_centers[loudest_idx]
                harmonics_found = 0
                for h in range(2, 5):
                    harmonic_freq = f0 * h
                    if harmonic_freq > band_centers[-1]:
                        break
                    harmonic_idx = np.argmin(np.abs(band_centers - harmonic_freq))
                    if amps[harmonic_idx] > 0.15:
                        harmonics_found += 1
                is_harmonic = harmonics_found >= 1
            else:
                is_harmonic = False
        else:
            is_harmonic = True
        visualizer.set_harmonic(is_harmonic)

    with sd.InputStream(device=DEVICE_INDEX, channels=2, samplerate=SAMPLE_RATE, blocksize=CHUNK, callback=callback):
        while visualizer.running:
            sd.sleep(UPDATE_INTERVAL)

async def poll_song_change(callback, poll_interval=2):
    last_song = None
    if MediaManager is None:
        return
    EXCLUDED_APPS = {"chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe"}
    while True:
        sessions = await MediaManager.request_async()
        for session in sessions.get_sessions():
            app_id = session.source_app_user_model_id
            if app_id and app_id.lower() in EXCLUDED_APPS:
                continue
            info = await session.try_get_media_properties_async()
            artist = info.artist
            title = info.title
            if title:
                song = f"{artist} - {title}"
                if song != last_song:
                    last_song = song
                    callback(song)
        await asyncio.sleep(poll_interval)

def main():
    root = tk.Tk()
    root.title("Live Audio Visualizer")
    root.config(bg='black')
    root.wm_attributes('-topmost', True)
    visualizer = AudioVisualizer(root)

    song_var = tk.StringVar()
    song_label = tk.Label(root, textvariable=song_var, fg="white", bg="black", font=("Fixedsys", 17))
    song_label.place(relx=0.5, rely=0.7, anchor="center")
    song_label.lower()

    dacus_label = tk.Label(root, text="Dacus", fg="white", bg="black", font=("Fixedsys", 12), borderwidth=0, padx=0, pady=0)
    dacus_label.place(relx=0.0125, rely=0.97, anchor="sw")
    dacus_label.lift()

    def show_song(song):
        max_chars = 40
        song_label.update_idletasks()
        label_width = song_label.winfo_width()
        window_width = root.winfo_width()
        display_song = song
        if len(song) > max_chars:
            display_song = song[:max_chars - 3] + "..."
        song_var.set(display_song)
        song_label.lift()
        hide_job = getattr(song_label, "_hide_job", None)
        if hide_job is not None:
            try:
                song_label.after_cancel(hide_job)
            except Exception:
                pass
        song_label.config(fg="white")
        job = song_label.after(3000, song_label.lower)
        song_label._hide_job = job

    def fade_out_label(label, delay, step=0):
        if step > 20:
            label.lower()
            return
        gray = int(255 * (1 - step / 20))
        color = f"#{gray:02x}{gray:02x}{gray:02x}"
        label.config(fg=color)
        job = label.after(delay, fade_out_label, label, delay, step + 1)
        label._fade_job = job

    def start_song_polling():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(poll_song_change(lambda song: root.after(0, show_song, song)))

    threading.Thread(target=start_song_polling, daemon=True).start()

    transparent = {"state": False}
    TRANSPARENT_OFFSET_X = 8
    TRANSPARENT_OFFSET_Y = 30

    def make_window_clickthrough(root):
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        styles = 0x80000 | 0x20
        old_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, old_style | styles)

    def remove_window_clickthrough(root):
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        old_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, old_style & ~0x20)

    def make_transparent(event=None):
        x, y = root.winfo_x(), root.winfo_y()
        if not transparent["state"]:
            root.overrideredirect(True)
            root.wm_attributes('-transparentcolor', 'black')
            root.config(bg='black')
            visualizer.config(bg='black')
            root.geometry(f"+{x + TRANSPARENT_OFFSET_X}+{y + TRANSPARENT_OFFSET_Y}")
            make_window_clickthrough(root)
            transparent["state"] = True
        else:
            root.overrideredirect(False)
            root.wm_attributes('-transparentcolor', '')
            root.config(bg='black')
            visualizer.config(bg='black')
            root.geometry(f"+{x - TRANSPARENT_OFFSET_X}+{y - TRANSPARENT_OFFSET_Y}")
            remove_window_clickthrough(root)
            transparent["state"] = False

    def on_close():
        visualizer.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.bind("<p>", make_transparent)
    t = threading.Thread(target=audio_thread, args=(visualizer,), daemon=True)
    t.start()

    # Start the CLI thread for command input
    cli_thread.start_command_line_thread(visualizer, root)

    root.mainloop()

if __name__ == "__main__":
    main()
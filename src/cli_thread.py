import threading
import sys
import difflib
import pygetwindow as gw
import ctypes

COMMANDS = ['exit', 'help', 'status', 'hide', 'show', 'windows', 'attach', 'mid', 'set']

def command_line_input(visualizer, root):
    while visualizer.running:
        command = input("Enter command: ")
        process_command(command, visualizer, root)

def process_command(command, visualizer, root):
    command = command.strip().lower()
    if command == "exit":
        try:
            visualizer.stop()
            root.quit()
        except Exception as e:
            print(f"Error stopping visualizer: {e}")
        finally:
            print("Exiting the visualizer.")
            sys.exit(0)
    elif command == "help":
        print("Available commands:")
        print("  exit - Stop the visualizer and exit the application.")
        print("  help - Show this help message.")
        print("  status - show config and running status")
        print("  hide - Hide the visualizer window.")
        print("  show - Show the visualizer window.")
        print("  windows - List all open windows.")
        print("  attach <window_name> - Attach the visualizer to a specific window by name.")
        
    elif command == "status":
        print(f"""Visualizer settings:
    Running: {visualizer.running}
    Bar Fall Acceleration: {visualizer.fall_acceleration}
    Bar Fall Speed Min: {visualizer.fall_speed_min}
    Highlighted Bar Speed: {visualizer.highlighted_bar_speed}
    """)
    elif command == "hide":
        TRANSPARENT_OFFSET_X = 8
        TRANSPARENT_OFFSET_Y = 30
        x, y = root.winfo_x(), root.winfo_y()
        root.overrideredirect(True)
        root.wm_attributes('-transparentcolor', 'black')
        root.config(bg='black')
        visualizer.config(bg='black')
        root.geometry(f"+{x + TRANSPARENT_OFFSET_X}+{y + TRANSPARENT_OFFSET_Y}")
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        styles = 0x80000 | 0x20
        old_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, old_style | styles)
    elif command == "show":
        TRANSPARENT_OFFSET_X = 8
        TRANSPARENT_OFFSET_Y = 30
        x, y = root.winfo_x(), root.winfo_y()
        root.overrideredirect(False)
        root.wm_attributes('-transparentcolor', '')
        root.config(bg='black')
        visualizer.config(bg='black')
        root.geometry(f"+{x - TRANSPARENT_OFFSET_X}+{y - TRANSPARENT_OFFSET_Y}")
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        old_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, old_style & ~0x20)
    elif command == "windows":
        windows = gw.getAllWindows()
        print("Open windows:")
        for i, win in enumerate(windows):
            if win.visible and not win.isMinimized and win.title.strip():
                print(f"  {i}: {win.title}")
    elif command.startswith("attach "):
        window_name = command[7:].strip()
        matches = [w for w in gw.getAllWindows() if window_name.lower() in w.title.lower()]
        if not matches:
            print(f"No window found matching '{window_name}'.")
            return
        win = matches[0]
        try:
            win.activate()
            wx, wy, ww, wh = win.left, win.top, win.width, win.height
            # Center visualizer in the target window
            vis_width = root.winfo_width()
            vis_height = root.winfo_height()
            center_x = wx + (ww - vis_width) // 2
            center_y = wy + (wh - vis_height) // 2
            print(f"Attaching to window: '{win.title}' at position ({center_x}, {center_y})")
            root.geometry(f"+{center_x}+{center_y}")
            print(f"Visualizer centered in window: '{win.title}'")
        except Exception as e:
            print(f"Error attaching to window: {e}")
    elif command.startswith("set "):
        parts = command.split()
        if len(parts) != 3:
            print("Usage: set <parameter> <value>")
            return
        param, value = parts[1], parts[2]
        try:
            if param == "fall_acceleration":
                visualizer.fall_acceleration = float(value)
                print(f"Set fall_acceleration to {value}")
            elif param == "fall_speed_min":
                visualizer.fall_speed_min = float(value)
                print(f"Set fall_speed_min to {value}")
            elif param == "highlighted_bar_speed":
                visualizer.highlighted_bar_speed = float(value)
                print(f"Set highlighted_bar_speed to {value}")
            elif param == "bar_count":
                from tkinter_audio_visualiser import BAR_WIDTH, BAR_SPACING, BAR_MAX_HEIGHT
                # Recreate bars (simple approach, may need to restart for full effect)
                try:
                    new_count = int(value)
                    visualizer.delete("all")
                    visualizer.bar_positions = [
                        (i * (BAR_WIDTH + BAR_SPACING), i * (BAR_WIDTH + BAR_SPACING) + BAR_WIDTH)
                        for i in range(new_count)
                    ]
                    visualizer.bars = [visualizer.create_rectangle(
                        x0, BAR_MAX_HEIGHT + 20, x1, BAR_MAX_HEIGHT + 20,
                        fill='lime', outline='') for x0, x1 in visualizer.bar_positions]
                    visualizer.amps = np.zeros(new_count)
                    visualizer.display_amps = np.zeros(new_count)
                    visualizer.fall_velocity = np.zeros(new_count)
                    print(f"Set bar_count to {new_count} (restart may be required for full effect)")
                except Exception as e:
                    print(f"Error setting bar_count: {e}")
            elif param == "bar_max_height":
                from tkinter_audio_visualiser import BAR_COUNT
                visualizer.config(height=int(value) + 20)
                print(f"Set bar_max_height to {value}")
            elif param == "log_bias":
                # You must store and use this value in your get_weighted_band_edges call!
                visualizer.log_bias = float(value)
                print(f"Set log_bias to {value} (restart may be required for full effect)")
            else:
                print(f"Unknown parameter: {param}")
        except Exception as e:
            print(f"Error setting {param}: {e}")
    elif command == "mid":
        # Move the visualizer window to coordinates (1925, 665)
        root.geometry("+1925+665")
        print("Visualizer moved to (1925, 665)")
    else:
        print(f"Unknown command: {command}")
        matches = difflib.get_close_matches(command, COMMANDS, n=1, cutoff=0.6)
        if matches:
            print(f"Did you mean: '{matches[0]}'?")

def start_command_line_thread(visualizer, root):
    thread = threading.Thread(target=command_line_input, args=(visualizer, root,), daemon=True)
    thread.start()
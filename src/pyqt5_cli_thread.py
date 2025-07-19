import threading
import sys
import difflib
import pygetwindow as gw
import ctypes
import pyqt5_audio_visualiser

COMMANDS = ['exit', 'help', 'status', 'hide', 'show', 'windows', 'attach', 'mid', 'set']

def command_line_input(app, window):
    while True:
        command = input("Enter command: ")
        process_command(command, app, window)

def process_command(command, app, window):
    command = command.strip().lower()
    if command == "exit":
        try:
            window.close()
        except Exception as e:
            print(f"Error stopping visualizer: {e}")
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
    Running: "True"
    """)
    elif command == "windows":
        try:
            windows = gw.getAllWindows()
            print("Open windows:")
            for i, win in enumerate(windows):
                if win.visible and not win.isMinimized and win.title.strip():
                    print(f"  {i}: {win.title}")
        except Exception as e:
            print(f"Error listing windows: {e}")
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
            vis_width, vis_height = window.get_window_size()
            center_x = wx + (ww - vis_width) // 2
            center_y = wy + (wh - vis_height) // 2
            print(f"Attaching to window: '{win.title}' at position ({center_x}, {center_y})")
            window.center_window_from_thread(center_x, center_y)
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
    # delay starting the command line thread to ensure the visualizer is initialized
    import time
    time.sleep(1)  # Wait for the visualizer to initialize
    thread = threading.Thread(target=command_line_input, args=(visualizer, root,), daemon=True)
    print("Starting command line input thread...")
    thread.start()
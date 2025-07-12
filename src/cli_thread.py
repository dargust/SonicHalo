import threading
import sys
import difflib

COMMANDS = ['exit', 'help', 'status', 'hide', 'show']

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
    elif command == "show":
        TRANSPARENT_OFFSET_X = 8
        TRANSPARENT_OFFSET_Y = 30
        x, y = root.winfo_x(), root.winfo_y()
        root.overrideredirect(False)
        root.wm_attributes('-transparentcolor', '')
        root.config(bg='black')
        visualizer.config(bg='black')
        root.geometry(f"+{x - TRANSPARENT_OFFSET_X}+{y - TRANSPARENT_OFFSET_Y}")
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
    else:
        print(f"Unknown command: {command}")
        matches = difflib.get_close_matches(command, COMMANDS, n=1, cutoff=0.6)
        if matches:
            print(f"Did you mean: '{matches[0]}'?")

def start_command_line_thread(visualizer, root):
    thread = threading.Thread(target=command_line_input, args=(visualizer, root,), daemon=True)
    thread.start()
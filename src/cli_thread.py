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
    else:
        print(f"Unknown command: {command}")
        matches = difflib.get_close_matches(command, COMMANDS, n=1, cutoff=0.6)
        if matches:
            print(f"Did you mean: '{matches[0]}'?")

def start_command_line_thread(visualizer, root):
    thread = threading.Thread(target=command_line_input, args=(visualizer, root,), daemon=True)
    thread.start()
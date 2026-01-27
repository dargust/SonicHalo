"""
Cross-platform system tray icon implementation
"""
import sys
import logging

# Platform detection
ON_WINDOWS = sys.platform.startswith('win')
ON_LINUX = sys.platform.startswith('linux')
ON_MACOS = sys.platform.startswith('darwin')

class CrossPlatformTrayIcon:
    """Cross-platform wrapper for system tray functionality"""
    
    def __init__(self, icon_path, menu_dict, tooltip="Tray Icon", left_click_callback=None):
        self.icon_path = icon_path
        self.menu_dict = menu_dict
        self.tooltip = tooltip
        self.left_click_callback = left_click_callback
        self.tray_icon = None
        
        # Try to initialize platform-specific tray icon
        self._initialize_tray()
    
    def _initialize_tray(self):
        """Initialize the appropriate tray icon for the current platform"""
        try:
            if ON_WINDOWS:
                self._init_windows_tray()
            elif ON_LINUX:
                self._init_linux_tray()
            elif ON_MACOS:
                self._init_macos_tray()
            else:
                logging.warning("System tray not supported on this platform")
        except Exception as e:
            logging.error(f"Failed to initialize system tray: {e}")
            self.tray_icon = None
    
    def _init_windows_tray(self):
        """Initialize Windows tray icon using winnotifyicon"""
        try:
            from winnotifyicon import TaskbarIcon
            self.tray_icon = TaskbarIcon(
                self.icon_path, 
                self.menu_dict, 
                self.tooltip, 
                left_click_callback=self.left_click_callback
            )
            logging.info("Windows taskbar icon initialized")
        except ImportError:
            logging.warning("winnotifyicon not available, tray icon disabled")
        except Exception as e:
            logging.error(f"Failed to create Windows tray icon: {e}")
    
    def _init_linux_tray(self):
        """Initialize Linux tray icon using PyQt5 QSystemTrayIcon"""
        try:
            from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction
            from PyQt5.QtGui import QIcon
            from PyQt5.QtCore import QTimer
            
            # Check if system tray is available
            if not QSystemTrayIcon.isSystemTrayAvailable():
                logging.warning("System tray not available on this Linux system")
                return
                
            self.tray_icon = QSystemTrayIcon()
            self.tray_icon.setIcon(QIcon(self.icon_path))
            self.tray_icon.setToolTip(self.tooltip)
            
            # Create context menu
            menu = QMenu()
            for item_name, callback in self.menu_dict.items():
                action = QAction(item_name, menu)
                action.triggered.connect(callback)
                menu.addAction(action)
            
            self.tray_icon.setContextMenu(menu)
            
            # Handle left click if callback provided
            if self.left_click_callback:
                self.tray_icon.activated.connect(self._handle_tray_activation)
            
            self.tray_icon.show()
            logging.info("Linux system tray icon initialized")
            
        except ImportError as e:
            logging.warning(f"PyQt5 system tray not available: {e}")
        except Exception as e:
            logging.error(f"Failed to create Linux tray icon: {e}")
    
    def _init_macos_tray(self):
        """Initialize macOS tray icon using PyQt5 QSystemTrayIcon"""
        # macOS can use the same PyQt5 implementation as Linux
        self._init_linux_tray()
        if self.tray_icon:
            logging.info("macOS system tray icon initialized")
    
    def _handle_tray_activation(self, reason):
        """Handle tray icon activation on Linux/macOS"""
        from PyQt5.QtWidgets import QSystemTrayIcon
        if (reason == QSystemTrayIcon.Trigger and  # Left click
            self.left_click_callback):
            self.left_click_callback()
    
    def show_balloon(self, title, msg, timeout=10):
        """Show balloon notification (cross-platform)"""
        if not self.tray_icon:
            logging.warning("Cannot show balloon: tray icon not available")
            return
            
        try:
            if ON_WINDOWS and hasattr(self.tray_icon, 'show_balloon'):
                # Use Windows-specific balloon
                self.tray_icon.show_balloon(title, msg, timeout)
            elif hasattr(self.tray_icon, 'showMessage'):
                # Use PyQt5 system tray message
                from PyQt5.QtWidgets import QSystemTrayIcon
                self.tray_icon.showMessage(title, msg, QSystemTrayIcon.Information, timeout * 1000)
            else:
                logging.warning("Balloon notifications not supported")
        except Exception as e:
            logging.error(f"Failed to show balloon notification: {e}")
    
    def is_available(self):
        """Check if tray icon is available and working"""
        return self.tray_icon is not None


# Convenience function for backward compatibility
def TaskbarIcon(icon_path, menu_dict, tooltip="Tray Icon", left_click_callback=None):
    """Backward compatibility wrapper"""
    return CrossPlatformTrayIcon(icon_path, menu_dict, tooltip, left_click_callback)
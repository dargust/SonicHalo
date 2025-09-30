# ...existing code...

import os
import sys
import win32api
import win32con
import win32gui
import win32gui_struct

class TaskbarIcon:
	def __init__(self, icon_path, menu_dict, tooltip="Tray Icon", left_click_callback=None):
		self.icon_path = icon_path
		self.menu_dict = menu_dict
		self.tooltip = tooltip
		self.left_click_callback = left_click_callback
		self.hwnd = None
		self.notify_id = None
		self._register_class()
		self._create_window()
		self._add_icon()

	def _register_class(self):
		wc = win32gui.WNDCLASS()
		hinst = wc.hInstance = win32api.GetModuleHandle(None)
		wc.lpszClassName = "TaskbarIconClass"
		wc.lpfnWndProc = self._wnd_proc
		try:
			win32gui.RegisterClass(wc)
		except win32gui.error:
			pass

	def _create_window(self):
		hinst = win32api.GetModuleHandle(None)
		self.hwnd = win32gui.CreateWindow(
			"TaskbarIconClass",
			"",
			0,
			0,
			0,
			win32con.CW_USEDEFAULT,
			win32con.CW_USEDEFAULT,
			0,
			0,
			hinst,
			None
		)

	def _add_icon(self):
		icon_flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
		hicon = win32gui.LoadImage(
			0,
			self.icon_path,
			win32con.IMAGE_ICON,
			0,
			0,
			icon_flags
		)
		flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
		nid = (self.hwnd, 0, flags, win32con.WM_USER+20, hicon, self.tooltip)
		win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
		self.notify_id = nid

	def _wnd_proc(self, hwnd, msg, wparam, lparam):
		if lparam == win32con.WM_RBUTTONUP:
			self._show_menu()
		elif lparam == win32con.WM_LBUTTONDBLCLK:
			self._on_menu_select(list(self.menu_dict.keys())[0])
		elif lparam == win32con.WM_LBUTTONUP:
			if self.left_click_callback:
				self.left_click_callback()
		elif msg == win32con.WM_DESTROY:
			self._remove_icon()
			win32gui.PostQuitMessage(0)
		return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

	def _show_menu(self):
		menu = win32gui.CreatePopupMenu()
		for idx, item in enumerate(self.menu_dict.keys()):
			win32gui.AppendMenu(menu, win32con.MF_STRING, idx+1, item)
		pos = win32gui.GetCursorPos()
		win32gui.SetForegroundWindow(self.hwnd)
		sel = win32gui.TrackPopupMenu(
			menu,
			win32con.TPM_LEFTALIGN | win32con.TPM_RETURNCMD,
			pos[0],
			pos[1],
			0,
			self.hwnd,
			None
		)
		if sel:
			item = list(self.menu_dict.keys())[sel-1]
			self._on_menu_select(item)

	def _on_menu_select(self, item):
		callback = self.menu_dict.get(item)
		if callback:
			callback()

	def show_balloon(self, title, msg, timeout=10):
		info_flags = win32gui.NIIF_INFO
		nid = list(self.notify_id)
		nid[5] = self.tooltip
		win32gui.Shell_NotifyIcon(
			win32gui.NIM_MODIFY,
			(nid[0], nid[1], win32gui.NIF_INFO, nid[3], nid[4], nid[5], msg, timeout, title, info_flags)
		)

	def _remove_icon(self):
		if self.notify_id:
			win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, self.notify_id)

	def run(self):
		win32gui.PumpMessages()
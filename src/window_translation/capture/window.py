"""Window identity, DPI-aware bounds, and WGC frames (never desktop fallback)."""
from __future__ import annotations
import ctypes
from ctypes import wintypes as wt
import os
import threading
import time
from dataclasses import dataclass
from .screen import Region


def _user32():
    u = ctypes.WinDLL('user32', use_last_error=True)
    u.GetForegroundWindow.restype = wt.HWND
    u.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    u.IsWindow.argtypes = u.IsWindowVisible.argtypes = u.IsIconic.argtypes = [wt.HWND]
    u.GetWindowTextLengthW.argtypes = [wt.HWND]
    u.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    u.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    u.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
    u.MonitorFromWindow.restype = wt.HANDLE
    return u


@dataclass(frozen=True)
class WindowTarget:
    hwnd: int
    pid: int
    title: str

    def valid(self):
        if os.name != 'nt':
            return False
        u = _user32()
        pid = wt.DWORD()
        u.GetWindowThreadProcessId(self.hwnd, ctypes.byref(pid))
        return bool(u.IsWindow(self.hwnd)) and pid.value == self.pid

    def foreground(self):
        return self.valid() and _user32().GetForegroundWindow() == self.hwnd

    def minimized(self):
        return not self.valid() or bool(_user32().IsIconic(self.hwnd))

    def bounds(self):
        if not self.valid() or self.minimized():
            raise RuntimeError('선택한 앱이 닫혔거나 최소화되어 있습니다.')
        u = _user32()
        rect = wt.RECT()
        dwm = ctypes.WinDLL('dwmapi')
        dwm.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]
        if dwm.DwmGetWindowAttribute(self.hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)):
            if not u.GetWindowRect(self.hwnd, ctypes.byref(rect)):
                raise RuntimeError('앱 위치를 확인할 수 없습니다.')
        # Qt screen origins are logical; native monitor bounds are physical.
        from PySide6.QtWidgets import QApplication
        class MonitorInfo(ctypes.Structure):
            _fields_ = [('size', wt.DWORD), ('monitor', wt.RECT), ('work', wt.RECT),
                        ('flags', wt.DWORD), ('device', wt.WCHAR * 32)]
        info = MonitorInfo(); info.size = ctypes.sizeof(info)
        u.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.POINTER(MonitorInfo)]
        if not u.GetMonitorInfoW(u.MonitorFromWindow(self.hwnd, 2), ctypes.byref(info)):
            raise RuntimeError('모니터 정보를 확인할 수 없습니다.')
        screen = next((s for s in QApplication.screens() if s.name() == info.device), None)
        if screen is None:
            screen = QApplication.primaryScreen()
        dpr = screen.devicePixelRatio()
        origin = screen.geometry()
        return Region(round(origin.x() + (rect.left-info.monitor.left)/dpr),
                      round(origin.y() + (rect.top-info.monitor.top)/dpr),
                      round((rect.right-rect.left)/dpr), round((rect.bottom-rect.top)/dpr))


def list_windows():
    if os.name != 'nt':
        return []
    u = _user32(); found = []
    callback_type = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def visit(hwnd, _):
        pid = wt.DWORD(); u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if u.IsWindowVisible(hwnd) and pid.value != os.getpid():
            n = u.GetWindowTextLengthW(hwnd)
            if n:
                title = ctypes.create_unicode_buffer(n+1)
                u.GetWindowTextW(hwnd, title, n+1)
                found.append(WindowTarget(int(hwnd), pid.value, title.value))
        return True
    callback = callback_type(visit)
    u.EnumWindows.argtypes = [callback_type, wt.LPARAM]
    u.EnumWindows(callback, 0)
    return sorted(found, key=lambda w: w.title.casefold())


class WindowCapture:
    """One latest owned frame; native callbacks never access Qt widgets."""
    def __init__(self, target):
        from windows_capture import WindowsCapture
        self.target = target
        self._lock = threading.Lock()
        self._image = None
        self._last_time = 0.0
        self.closed = False
        self.capture = WindowsCapture(window_hwnd=target.hwnd, cursor_capture=False)
        @self.capture.event
        def on_frame_arrived(frame, control):
            if self.closed:
                control.stop(); return
            now = time.monotonic()
            from PIL import Image
            # Own the memory before returning from the native callback.
            image = Image.fromarray(frame.frame_buffer[:, :, [2, 1, 0]].copy())
            with self._lock:
                self._image = image
                self._last_time = now
        @self.capture.event
        def on_closed():
            self.closed = True
        self.control = self.capture.start_free_threaded()

    def image(self, crop=(0, 0, 1, 1)):
        if self.closed or not self.target.valid():
            raise RuntimeError('선택한 앱의 캡처가 종료됐습니다. 앱을 다시 선택해주세요.')
        if self.target.minimized():
            return None
        with self._lock:
            if self._image is None:
                return None
            image = self._image
            x, y, w, h = crop
            return image.crop((round(x*image.width), round(y*image.height),
                               round((x+w)*image.width), round((y+h)*image.height)))

    def stop(self):
        self.closed = True
        # Native stop can join: do not block the UI, retain self until complete.
        threading.Thread(target=self.control.stop, daemon=True).start()


def relative_crop(region, bounds):
    l, t = max(region.left, bounds.left), max(region.top, bounds.top)
    r, b = min(region.right, bounds.right), min(region.bottom, bounds.bottom)
    if r <= l or b <= t:
        raise ValueError('선택한 앱 안에서 영역을 지정해주세요.')
    return ((l-bounds.left)/bounds.width, (t-bounds.top)/bounds.height,
            (r-l)/bounds.width, (b-t)/bounds.height)


def crop_region(bounds, crop):
    x, y, w, h = crop
    return Region(round(bounds.left+x*bounds.width), round(bounds.top+y*bounds.height),
                  max(1, round(w*bounds.width)), max(1, round(h*bounds.height)))

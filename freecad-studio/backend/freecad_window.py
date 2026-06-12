"""FreeCAD window control on Windows."""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from contextlib import contextmanager

SW_RESTORE = 9
SW_MINIMIZE = 6
SW_SHOWNA = 8

_MINIMIZE_DEBOUNCE_SEC = 15.0
_minimize_timer: threading.Timer | None = None


def _find_freecad_hwnds() -> list[int]:
    """Find FreeCAD main windows, including minimized."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes

        user32 = ctypes.windll.user32
        found: list[int] = []

        def _callback(hwnd: int, _lparam: int) -> bool:
            length = user32.GetWindowTextLengthW(hwnd) + 1
            if length <= 1:
                return True
            buf = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hwnd, buf, length)
            title = buf.value.lower()
            if "freecad" in title and "cursor" not in title:
                found.append(hwnd)
            return True

        enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)(_callback)
        user32.EnumWindows(enum_proc, 0)
        return found
    except Exception:
        return []


def cancel_background_minimize() -> None:
    """Cancel a pending background minimize (e.g. user clicked Show FreeCAD)."""
    global _minimize_timer
    if _minimize_timer is not None:
        _minimize_timer.cancel()
        _minimize_timer = None


def _schedule_background_minimize(delay: float = _MINIMIZE_DEBOUNCE_SEC) -> None:
    """Minimize FreeCAD after a quiet period — avoids open/close flashing on every capture."""
    global _minimize_timer
    cancel_background_minimize()

    def _go() -> None:
        minimize_freecad_window()

    _minimize_timer = threading.Timer(delay, _go)
    _minimize_timer.daemon = True
    _minimize_timer.start()


def focus_freecad_window() -> bool:
    if sys.platform != "win32":
        return False
    cancel_background_minimize()
    try:
        import ctypes

        user32 = ctypes.windll.user32
        found = _find_freecad_hwnds()
        if not found:
            return False
        hwnd = found[0]
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.15)
        return True
    except Exception:
        return False


def restore_freecad_for_capture() -> bool:
    """Restore FreeCAD for rendering without stealing desktop focus."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        found = _find_freecad_hwnds()
        if not found:
            return False
        hwnd = found[0]
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            user32.ShowWindow(hwnd, SW_SHOWNA)
        time.sleep(0.25)
        return True
    except Exception:
        return False


def minimize_freecad_window() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        found = _find_freecad_hwnds()
        if not found:
            return False
        user32.ShowWindow(found[0], SW_MINIMIZE)
        return True
    except Exception:
        return False


@contextmanager
def freecad_visible_for_capture(restore_after: bool = False, *, activate: bool = False):
    """Restore FreeCAD so the 3D view can render; optionally minimize again after a delay."""
    was_minimized = False
    if sys.platform == "win32":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            found = _find_freecad_hwnds()
            if found:
                was_minimized = bool(user32.IsIconic(found[0]))
        except Exception:
            pass

    if activate:
        focus_freecad_window()
    else:
        restore_freecad_for_capture()
    time.sleep(0.2)
    try:
        yield
    finally:
        if restore_after and was_minimized:
            _schedule_background_minimize()


def launch_freecad_gui(
    exe: str,
    macro: str | None = None,
    *,
    focus: bool = True,
    minimize: bool = False,
) -> None:
    args = [exe]
    if macro:
        args.append(macro)
    subprocess.Popen(args, shell=False)
    if sys.platform != "win32":
        return
    time.sleep(2.5)
    if minimize:
        minimize_freecad_window()
    elif focus:
        focus_freecad_window()
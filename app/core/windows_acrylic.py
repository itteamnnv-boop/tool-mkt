"""Real background blur (Windows Acrylic) for the main window — QSS alone cannot blur
whatever is behind the app (no backdrop-filter equivalent in Qt style sheets); Windows only
exposes that effect through an undocumented user32.dll call. Windows-only, best-effort: if the
call fails (non-Windows, or Microsoft changes/removes the undocumented API in a future
Windows build), the app still runs fine with the plain translucent-panel look from style.qss.
"""
from __future__ import annotations

import ctypes
import sys


def _abgr(r: int, g: int, b: int, a: int) -> int:
    return (a << 24) | (b << 16) | (g << 8) | r


class _ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_int),
        ("AnimationId", ctypes.c_int),
    ]


class _WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.POINTER(_ACCENT_POLICY)),
        ("SizeOfData", ctypes.c_size_t),
    ]


def disable_window_blur(hwnd: int) -> bool:
    """Remove the whole-window backdrop so unpainted margins stay fully clear."""
    if sys.platform != "win32":
        return False
    try:
        accent = _ACCENT_POLICY()
        accent.AccentState = 0
        data = _WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = 19
        data.Data = ctypes.pointer(accent)
        data.SizeOfData = ctypes.sizeof(accent)
        return bool(ctypes.windll.user32.SetWindowCompositionAttribute(
            ctypes.c_void_p(hwnd), ctypes.pointer(data)
        ))
    except (AttributeError, OSError):
        return False


def enable_window_blur(hwnd: int, r: int = 0x6d, g: int = 0x6d, b: int = 0x68, alpha: int = 155) -> bool:
    """Turns on Windows' Acrylic blur-behind for the given native window handle, tinted with
    the given RGB + alpha (0-255). Returns False (never raises) if unsupported."""
    if sys.platform != "win32":
        return False
    try:
        ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
        ACCENT_ENABLE_BLURBEHIND = 3
        WCA_ACCENT_POLICY = 19

        accent = _ACCENT_POLICY()
        # Untinted blur uses state 3: Acrylic with a zero-alpha tint may go blank.
        accent.AccentState = ACCENT_ENABLE_BLURBEHIND if alpha == 0 else ACCENT_ENABLE_ACRYLICBLURBEHIND
        accent.AccentFlags = 0
        accent.GradientColor = _abgr(r, g, b, alpha)
        accent.AnimationId = 0

        data = _WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = WCA_ACCENT_POLICY
        data.Data = ctypes.pointer(accent)
        data.SizeOfData = ctypes.sizeof(accent)

        set_window_composition_attribute = ctypes.windll.user32.SetWindowCompositionAttribute
        return bool(set_window_composition_attribute(ctypes.c_void_p(hwnd), ctypes.pointer(data)))
    except (AttributeError, OSError):
        # Undocumented API — missing entirely on some Windows builds/editions.
        return False

from __future__ import annotations

from pathlib import Path
from typing import Any

from computer_use_cli import capture


def gw():
    import pygetwindow

    return pygetwindow


def serialize_window(window: Any, index: int | None = None) -> dict[str, object]:
    data: dict[str, object] = {
        "title": window.title,
        "left": int(window.left),
        "top": int(window.top),
        "width": int(window.width),
        "height": int(window.height),
        "right": int(window.right),
        "bottom": int(window.bottom),
        "isActive": bool(window.isActive),
        "isMinimized": bool(window.isMinimized),
        "isMaximized": bool(window.isMaximized),
    }
    if index is not None:
        data["index"] = index
    return data


def list_windows(include_empty: bool = False, include_minimized: bool = True) -> list[dict[str, object]]:
    all_windows = gw().getAllWindows()
    serialized: list[dict[str, object]] = []
    for index, window in enumerate(all_windows):
        if not include_empty and not window.title.strip():
            continue
        if not include_minimized and window.isMinimized:
            continue
        serialized.append(serialize_window(window, index=index))
    return serialized


def active_window() -> dict[str, object] | None:
    window = gw().getActiveWindow()
    if window is None:
        return None
    return serialize_window(window)


def find_windows(title: str, include_minimized: bool = True) -> list[Any]:
    needle = title.casefold()
    return [
        window
        for window in gw().getAllWindows()
        if needle in window.title.casefold() and (include_minimized or not window.isMinimized)
    ]


def focus_window(title: str) -> dict[str, object]:
    matches = find_windows(title)
    if not matches:
        raise LookupError(f"no windows match title substring: {title!r}")
    window = matches[0]
    if window.isMinimized:
        window.restore()
    window.activate()
    return serialize_window(window)


def window_region(title: str) -> tuple[int, int, int, int]:
    matches = find_windows(title, include_minimized=False)
    if not matches:
        raise LookupError(f"no non-minimized windows match title substring: {title!r}")
    window = matches[0]
    width = int(window.width)
    height = int(window.height)
    if width <= 0 or height <= 0:
        raise ValueError("matched window has invalid size")
    return int(window.left), int(window.top), width, height


def screenshot_window(
    title: str,
    path: Path,
    backend: capture.Backend = "mss",
) -> dict[str, object]:
    region = window_region(title)
    shot = capture.capture_screen(path, region=region, backend=backend)
    return {**shot, "windowTitleQuery": title, "windowRegion": region}

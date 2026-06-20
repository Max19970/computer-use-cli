from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from computer_use_cli import automation, capture, uia, windows


def _safe_call(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return {"ok": True, "value": fn(*args, **kwargs)}
    except Exception as exc:  # noqa: BLE001 - observe must degrade partially.
        return {"ok": False, "error": str(exc), "type": exc.__class__.__name__}


def observe_state(
    screenshot_path: Path = Path("observe-screen.png"),
    backend: capture.Backend = "mss",
    monitor: int = 0,
    include_screenshot: bool = True,
    include_windows: bool = True,
    include_uia: bool = False,
    uia_depth: int = 2,
    uia_title: str | None = None,
    uia_backend: uia.Backend = "uia",
    include_minimized: bool = False,
) -> dict[str, Any]:
    """Collect a single agent-friendly snapshot of local desktop state."""
    state: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "cursor": _safe_call(automation.mouse_position),
        "activeWindow": _safe_call(windows.active_window),
        "screen": _safe_call(capture.screen_size, backend, monitor),
    }

    if include_screenshot:
        state["screenshot"] = _safe_call(capture.capture_screen, screenshot_path, None, backend, monitor)

    if include_windows:
        state["windows"] = _safe_call(windows.list_windows, False, include_minimized)

    if include_uia:
        state["uia"] = _safe_call(
            uia.element_tree,
            uia_title,
            max(uia_depth, 0),
            uia_backend,
            False,
        )

    return state

from __future__ import annotations

import math
import time
from typing import Literal


def pg():
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.08
    return pyautogui


def mouse_position() -> dict[str, int]:
    pyautogui = pg()
    x, y = pyautogui.position()
    return {"x": int(x), "y": int(y)}


Button = Literal["left", "middle", "right"]


def _duration_from_speed(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration: float | None,
    speed: float | None,
) -> float:
    if duration is not None:
        return max(float(duration), 0.0)
    if speed is None:
        return 0.0
    if speed <= 0:
        raise ValueError("speed must be greater than 0 pixels per second")
    distance = math.hypot(end_x - start_x, end_y - start_y)
    return distance / speed


def move(
    x: int,
    y: int,
    duration: float | None = None,
    speed: float | None = None,
) -> dict[str, object]:
    pyautogui = pg()
    current_x, current_y = pyautogui.position()
    actual_duration = _duration_from_speed(
        int(current_x),
        int(current_y),
        x,
        y,
        duration,
        speed,
    )
    pyautogui.moveTo(x, y, duration=actual_duration)
    return {"x": x, "y": y, "duration": actual_duration, "speed": speed}


def move_between(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration: float | None = None,
    speed: float | None = None,
    hold: bool = False,
    button: Button = "left",
) -> dict[str, object]:
    pyautogui = pg()
    actual_duration = _duration_from_speed(start_x, start_y, end_x, end_y, duration, speed)
    pyautogui.moveTo(start_x, start_y, duration=0)
    if hold:
        pyautogui.mouseDown(button=button)
    try:
        pyautogui.moveTo(end_x, end_y, duration=actual_duration)
    finally:
        if hold:
            pyautogui.mouseUp(button=button)
    pos = mouse_position()
    return {
        "fromX": start_x,
        "fromY": start_y,
        "x": pos["x"],
        "y": pos["y"],
        "duration": actual_duration,
        "speed": speed,
        "hold": hold,
        "button": button,
    }


def click(
    x: int | None = None,
    y: int | None = None,
    button: Button = "left",
    clicks: int = 1,
    interval: float = 0.0,
) -> dict[str, object]:
    pyautogui = pg()
    pyautogui.click(x=x, y=y, button=button, clicks=max(clicks, 1), interval=max(interval, 0.0))
    pos = mouse_position()
    return {
        "x": pos["x"],
        "y": pos["y"],
        "button": button,
        "clicks": clicks,
        "interval": interval,
    }


def drag(
    x: int,
    y: int,
    duration: float | None = None,
    button: Button = "left",
    start_x: int | None = None,
    start_y: int | None = None,
    speed: float | None = None,
) -> dict[str, object]:
    pyautogui = pg()
    effective_duration = 0.2 if duration is None and speed is None else duration
    if start_x is not None or start_y is not None:
        if start_x is None or start_y is None:
            raise ValueError("drag start coordinates require both start_x and start_y")
        return move_between(
            start_x,
            start_y,
            x,
            y,
            effective_duration,
            speed,
            hold=True,
            button=button,
        )
    current_x, current_y = pyautogui.position()
    actual_duration = _duration_from_speed(
        int(current_x),
        int(current_y),
        x,
        y,
        effective_duration,
        speed,
    )
    pyautogui.dragTo(x, y, duration=actual_duration, button=button)
    pos = mouse_position()
    return {
        "x": pos["x"],
        "y": pos["y"],
        "duration": actual_duration,
        "speed": speed,
        "button": button,
    }


def _scroll_chunks(clicks: int, steps: int | None) -> list[int]:
    if clicks == 0:
        return []
    if steps is None:
        return [clicks]
    step_count = max(int(steps), 1)
    magnitude = abs(clicks)
    sign = 1 if clicks > 0 else -1
    base, remainder = divmod(magnitude, step_count)
    chunks = [sign * (base + (1 if index < remainder else 0)) for index in range(step_count)]
    return [chunk for chunk in chunks if chunk]


def scroll(
    clicks: int,
    x: int | None = None,
    y: int | None = None,
    steps: int | None = None,
    interval: float = 0.0,
) -> dict[str, object]:
    pyautogui = pg()
    chunks = _scroll_chunks(clicks, steps)
    for index, chunk in enumerate(chunks):
        pyautogui.scroll(chunk, x=x, y=y)
        if interval > 0 and index < len(chunks) - 1:
            time.sleep(interval)
    pos = mouse_position()
    return {
        "clicks": clicks,
        "x": pos["x"],
        "y": pos["y"],
        "steps": len(chunks),
        "interval": interval,
    }


def type_text(text: str, interval: float = 0.0) -> dict[str, object]:
    pyautogui = pg()
    pyautogui.write(text, interval=max(interval, 0.0))
    return {"length": len(text), "interval": interval}


def press_key(key: str, presses: int = 1, interval: float = 0.0) -> dict[str, object]:
    pyautogui = pg()
    pyautogui.press(key, presses=max(presses, 1), interval=max(interval, 0.0))
    return {"key": key, "presses": presses, "interval": interval}


def hotkey(keys: tuple[str, ...]) -> dict[str, object]:
    if len(keys) < 2:
        raise ValueError("hotkey requires at least two keys")
    pyautogui = pg()
    pyautogui.hotkey(*keys)
    return {"keys": list(keys)}

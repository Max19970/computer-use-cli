from __future__ import annotations

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


def move(x: int, y: int, duration: float = 0.0) -> dict[str, object]:
    pyautogui = pg()
    pyautogui.moveTo(x, y, duration=max(duration, 0.0))
    return {"x": x, "y": y, "duration": duration}


def click(
    x: int | None = None,
    y: int | None = None,
    button: Literal["left", "middle", "right"] = "left",
    clicks: int = 1,
    interval: float = 0.0,
) -> dict[str, object]:
    pyautogui = pg()
    pyautogui.click(x=x, y=y, button=button, clicks=max(clicks, 1), interval=max(interval, 0.0))
    pos = mouse_position()
    return {"x": pos["x"], "y": pos["y"], "button": button, "clicks": clicks, "interval": interval}


def drag(x: int, y: int, duration: float = 0.2, button: Literal["left", "middle", "right"] = "left") -> dict[str, object]:
    pyautogui = pg()
    pyautogui.dragTo(x, y, duration=max(duration, 0.0), button=button)
    pos = mouse_position()
    return {"x": pos["x"], "y": pos["y"], "duration": duration, "button": button}


def scroll(clicks: int, x: int | None = None, y: int | None = None) -> dict[str, object]:
    pyautogui = pg()
    pyautogui.scroll(clicks, x=x, y=y)
    pos = mouse_position()
    return {"clicks": clicks, "x": pos["x"], "y": pos["y"]}


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

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

from PIL import Image

Region = tuple[int, int, int, int]
Backend = Literal["pyautogui", "mss", "ffmpeg"]


def normalize_region(
    x: int | None,
    y: int | None,
    width: int | None,
    height: int | None,
) -> Region | None:
    parts = (x, y, width, height)
    if all(value is None for value in parts):
        return None
    if any(value is None for value in parts):
        raise ValueError("region requires x, y, width, and height together")
    if width is None or height is None or width <= 0 or height <= 0:
        raise ValueError("region width and height must be positive")
    return int(x), int(y), int(width), int(height)  # type: ignore[arg-type]


def save_image(image: Image.Image, path: Path) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return {
        "path": str(path.resolve()),
        "size": {"width": int(image.width), "height": int(image.height)},
    }


def capture_pyautogui(path: Path, region: Region | None = None) -> dict[str, object]:
    from computer_use_cli.automation import pg

    image = pg().screenshot(region=region)
    data = save_image(image, path)
    return {**data, "backend": "pyautogui", "region": region}


def _mss_monitor_spec(region: Region | None, monitor: int) -> dict[str, int]:
    import mss

    with mss.mss() as sct:
        monitors = sct.monitors
        if region is not None:
            x, y, width, height = region
            return {"left": x, "top": y, "width": width, "height": height}
        if monitor < 0 or monitor >= len(monitors):
            raise ValueError(f"monitor must be in range 0..{len(monitors) - 1}")
        return dict(monitors[monitor])


def capture_mss(path: Path, region: Region | None = None, monitor: int = 0) -> dict[str, object]:
    import mss

    spec = _mss_monitor_spec(region, monitor)
    with mss.mss() as sct:
        shot = sct.grab(spec)
        image = Image.frombytes("RGB", shot.size, shot.rgb)
    data = save_image(image, path)
    return {**data, "backend": "mss", "monitor": monitor, "region": region, "captureRect": spec}


def capture_ffmpeg(path: Path, region: Region | None = None) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "gdigrab"]
    if region is not None:
        x, y, width, height = region
        command.extend(["-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{width}x{height}"])
    command.extend(["-i", "desktop", "-frames:v", "1", str(path)])
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "ffmpeg screenshot failed").strip()
        raise RuntimeError(message)
    with Image.open(path) as image:
        size = {"width": int(image.width), "height": int(image.height)}
    return {"path": str(path.resolve()), "size": size, "backend": "ffmpeg", "region": region}


def capture_screen(
    path: Path,
    region: Region | None = None,
    backend: Backend = "mss",
    monitor: int = 0,
) -> dict[str, object]:
    if backend == "pyautogui":
        return capture_pyautogui(path, region)
    if backend == "mss":
        return capture_mss(path, region, monitor)
    if backend == "ffmpeg":
        return capture_ffmpeg(path, region)
    raise ValueError("backend must be one of: pyautogui, mss, ffmpeg")


def screen_size(backend: Backend = "pyautogui", monitor: int = 0) -> dict[str, object]:
    if backend == "mss":
        spec = _mss_monitor_spec(None, monitor)
        return {
            "backend": "mss",
            "monitor": monitor,
            "width": int(spec["width"]),
            "height": int(spec["height"]),
            "left": int(spec["left"]),
            "top": int(spec["top"]),
        }
    from computer_use_cli.automation import pg

    width, height = pg().size()
    return {"backend": "pyautogui", "width": int(width), "height": int(height)}


def list_monitors() -> list[dict[str, object]]:
    import mss

    serialized: list[dict[str, object]] = []
    with mss.mss() as sct:
        for index, monitor in enumerate(sct.monitors):
            item: dict[str, object] = {"index": index}
            for key, value in monitor.items():
                item[key] = int(value) if isinstance(value, int) else value
            serialized.append(item)
    return serialized

from __future__ import annotations

import time
from pathlib import Path

from PIL import Image

from computer_use_cli import capture


def _cv2():
    import cv2

    return cv2


def match_image(
    image_path: Path,
    template_path: Path,
    threshold: float = 0.85,
    method: str = "TM_CCOEFF_NORMED",
) -> dict[str, object]:
    cv2 = _cv2()
    method_value = getattr(cv2, method, None)
    if method_value is None:
        raise ValueError(f"unknown OpenCV template matching method: {method}")

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"image not found or unsupported: {image_path}")
    if template is None:
        raise FileNotFoundError(f"template not found or unsupported: {template_path}")

    ih, iw = image.shape[:2]
    th, tw = template.shape[:2]
    if th > ih or tw > iw:
        raise ValueError("template must not be larger than image")

    result = cv2.matchTemplate(image, template, method_value)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
    lower_is_better = method in {"TM_SQDIFF", "TM_SQDIFF_NORMED"}
    score = 1.0 - float(min_val) if lower_is_better else float(max_val)
    top_left = min_loc if lower_is_better else max_loc
    x, y = int(top_left[0]), int(top_left[1])
    center = {"x": x + tw // 2, "y": y + th // 2}
    return {
        "found": score >= threshold,
        "score": score,
        "threshold": threshold,
        "method": method,
        "box": {"left": x, "top": y, "width": int(tw), "height": int(th)},
        "center": center,
        "image": str(image_path.resolve()),
        "template": str(template_path.resolve()),
    }


def wait_image(
    template_path: Path,
    timeout: float = 10.0,
    interval: float = 0.5,
    threshold: float = 0.85,
    output: Path = Path("screen.png"),
    backend: capture.Backend = "mss",
    monitor: int = 0,
    region: capture.Region | None = None,
) -> dict[str, object]:
    started = time.monotonic()
    attempts = 0
    last: dict[str, object] | None = None
    while True:
        attempts += 1
        shot = capture.capture_screen(output, region=region, backend=backend, monitor=monitor)
        last = match_image(Path(shot["path"]), template_path, threshold=threshold)
        if bool(last["found"]):
            return {"found": True, "attempts": attempts, "elapsed": time.monotonic() - started, "match": last, "screenshot": shot}
        if time.monotonic() - started >= timeout:
            return {"found": False, "attempts": attempts, "elapsed": time.monotonic() - started, "lastMatch": last, "screenshot": shot}
        time.sleep(max(interval, 0.05))


def crop_image(image_path: Path, output: Path, region: capture.Region) -> dict[str, object]:
    x, y, width, height = region
    with Image.open(image_path) as image:
        crop = image.crop((x, y, x + width, y + height))
        data = capture.save_image(crop, output)
    return {**data, "source": str(image_path.resolve()), "region": region}


def ocr_image(image_path: Path, language: str = "eng") -> dict[str, object]:
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pytesseract is not installed") from exc

    with Image.open(image_path) as image:
        try:
            text = pytesseract.image_to_string(image, lang=language)
        except Exception as exc:  # noqa: BLE001 - expose missing Tesseract as JSON error.
            raise RuntimeError(
                "OCR failed. Make sure Tesseract OCR is installed and available in PATH, "
                "or set pytesseract.pytesseract.tesseract_cmd in code."
            ) from exc
    return {"image": str(image_path.resolve()), "language": language, "text": text, "length": len(text)}

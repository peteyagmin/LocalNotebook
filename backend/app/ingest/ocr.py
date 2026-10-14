"""OCR through the Tesseract program (FR-2.2)."""

from __future__ import annotations

import shutil

OCR_MISSING_MESSAGE = (
    "Tesseract (OCR) is not installed, so text in images and scanned pages cannot be read."
)


class OCRUnavailable(Exception):
    pass


def available() -> bool:
    return shutil.which("tesseract") is not None


def ocr_image(image) -> str:
    """Text found in a PIL image. Raises OCRUnavailable if Tesseract is not installed."""
    import pytesseract

    if not available():
        raise OCRUnavailable(OCR_MISSING_MESSAGE)
    try:
        return pytesseract.image_to_string(image)
    except pytesseract.TesseractNotFoundError as e:
        raise OCRUnavailable(OCR_MISSING_MESSAGE) from e

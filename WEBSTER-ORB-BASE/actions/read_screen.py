"""G5.51: explicit, local OCR of the primary display."""
ACTION_ID = "read_screen"
DESCRIPTION = "Capture the primary display on request and read visible text locally with Tesseract OCR."

def run():
    try:
        import mss
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        return f"Screen reading needs optional packages: pip install mss pillow pytesseract. Missing: {exc.name}"
    import io
    with mss.mss() as capture:
        shot = capture.grab(capture.monitors[1])
        image = Image.frombytes("RGB", shot.size, shot.rgb)
    try:
        text = pytesseract.image_to_string(image, timeout=15).strip()
    except Exception as exc:
        return f"OCR failed. Install the Tesseract OCR application and configure its path if needed. Details: {exc}"
    return ("Text visible on the primary display:\n" + text[:3500]) if text else "No readable text detected. This capture was processed locally."

"""G5.53: local image inspection and optional OCR; not an AI caption model."""
ACTION_ID = "analyse_image"
DESCRIPTION = "Inspect a user-supplied image locally and extract visible text when local OCR is installed."

def run():
    from pathlib import Path
    path = Path(ACTION_ARGUMENTS.strip().strip('"')).expanduser()
    if not path.is_file():
        return "Supply the full path to an existing image file."
    try:
        from PIL import Image
        with Image.open(path) as image:
            report = [f"Format: {image.format}", f"Dimensions: {image.width} x {image.height}", f"Mode: {image.mode}"]
            try:
                import pytesseract
                text = pytesseract.image_to_string(image, timeout=15).strip()
                if text:
                    report.append("Detected text:\n" + text[:2500])
                else:
                    report.append("No readable text detected.")
            except ImportError:
                report.append("OCR unavailable. Install pytesseract and the Tesseract application to extract text.")
            except Exception as exc:
                report.append(f"OCR unavailable: {exc}")
            return "Local image inspection (no cloud upload):\n" + "\n".join(report)
    except ImportError:
        return "Image inspection requires Pillow: pip install pillow"
    except Exception as exc:
        return f"Could not inspect image: {exc}"

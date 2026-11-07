"""G5.55: build a local slideshow video from user-selected images."""
ACTION_ID = "generate_video"
DESCRIPTION = "Create a short local slideshow video from image files; this is not AI video generation."

def run():
    try:
        import cv2
        from PIL import Image
    except ImportError:
        return "Video slideshow needs OpenCV and Pillow: pip install opencv-python pillow"
    from pathlib import Path
    from datetime import datetime
    raw = ACTION_ARGUMENTS.strip().strip('"')
    paths = [Path(part.strip().strip('"')).expanduser() for part in raw.split("|") if part.strip()]
    if not paths or len(paths) > 30 or any(not p.is_file() for p in paths):
        return 'Supply 1–30 existing image paths separated by |. Example: "C:\\Pics\\a.jpg | C:\\Pics\\b.png"'
    folder = Path.home() / "Videos" / "WEBSTER"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ("slideshow_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".avi")
    size = (1280, 720)
    writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*"XVID"), 2.0, size)
    if not writer.isOpened():
        return "Could not initialise the local video writer."
    try:
        for path in paths:
            with Image.open(path) as im:
                frame = im.convert("RGB")
                frame.thumbnail(size)
                canvas = Image.new("RGB", size, "#071426")
                canvas.paste(frame, ((size[0]-frame.width)//2, (size[1]-frame.height)//2))
                import numpy as np
                bgr = cv2.cvtColor(np.array(canvas), cv2.COLOR_RGB2BGR)
                for _ in range(4):
                    writer.write(bgr)
    except Exception as exc:
        writer.release()
        target.unlink(missing_ok=True)
        return f"Slideshow creation failed: {exc}"
    writer.release()
    return f"Created a local slideshow video (not AI-generated): {target}"

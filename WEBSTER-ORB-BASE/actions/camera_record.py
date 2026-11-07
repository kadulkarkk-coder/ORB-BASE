"""G5.52: user-visible, fixed-duration camera recording."""
ACTION_ID = "camera_record"
DESCRIPTION = "Record a visible camera session for a fixed duration (1–30 seconds), then stop automatically."

def run():
    try:
        import cv2
    except ImportError:
        return "Camera recording requires OpenCV: pip install opencv-python"
    from pathlib import Path
    from datetime import datetime
    args = ACTION_ARGUMENTS.strip()
    try:
        seconds = int(args or "10")
    except ValueError:
        return "Supply a duration in seconds, from 1 to 30."
    if not 1 <= seconds <= 30:
        return "Recording duration must be between 1 and 30 seconds."
    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        return "Could not open the default camera. Check camera permissions and whether another app is using it."
    fps = 20.0
    width = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
    height = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
    output_dir = Path.home() / "Videos" / "WEBSTER"
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / ("camera_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".avi")
    writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*"XVID"), fps, (width, height))
    if not writer.isOpened():
        camera.release()
        return "Could not create the recording file."
    import time
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            ok, frame = camera.read()
            if not ok:
                break
            cv2.putText(frame, "WEBSTER CAMERA - RECORDING", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            cv2.imshow("WEBSTER Camera Recording - press Q to stop", frame)
            writer.write(frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        writer.release()
        camera.release()
        cv2.destroyAllWindows()
    return f"Camera session stopped. Recording saved to: {target}"

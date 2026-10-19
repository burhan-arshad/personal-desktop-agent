
import ctypes
from pathlib import Path
try:
    result = ctypes.windll.shcore.SetProcessDpiAwareness(2)

    if result == 0:
        print("DPI awareness: Per-monitor aware")
    else:
        print(f"DPI awareness pehle se set ho sakti hai. HRESULT: {result:#010x}")

except (AttributeError, OSError):
    print("Per-monitor DPI API available nahi; fallback try kar rahe hain.")

    try:
        ctypes.windll.user32.SetProcessDPIAware()
        print("DPI awareness: System aware")
    except (AttributeError, OSError) as error:
        print(f"DPI awareness set nahi hui: {error}")
import mss
import pyautogui
from PIL import Image


def main():
    output_path = Path(__file__).resolve().parent / "test_screenshot.png"

    with mss.MSS() as screen:
        monitor = screen.monitors[1]
        screenshot = screen.grab(monitor)
        image = Image.frombytes(
            "RGB",
            screenshot.size,
            screenshot.rgb
        )

        image.save(output_path)

        print("\n--- Screenshot Test Results ---")
        print(f"Saved image: {output_path}")
        print(f"MSS monitor dimensions: {screenshot.width} x {screenshot.height}")
        print(f"Saved image dimensions: {image.width} x {image.height}")
        print(f"PyAutoGUI screen size: {pyautogui.size()}")
        print(f"Monitor information: {monitor}")


if __name__ == "__main__":
    main()

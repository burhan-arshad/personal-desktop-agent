
import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except (AttributeError, OSError):
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass

import time
import pyautogui
from PIL import Image, ImageDraw

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3


def main():
    width, height = pyautogui.size()

    center_x = width // 2
    center_y = height // 2

    print(f"Screen dimensions: {width} x {height}")
    print(f"Center coordinates: ({center_x}, {center_y})")

    screenshot = pyautogui.screenshot()

    draw = ImageDraw.Draw(screenshot)
    radius = 12

    draw.ellipse(
        (
            center_x - radius,
            center_y - radius,
            center_x + radius,
            center_y + radius
        ),
        outline="red",
        width=4
    )

    draw.text(
        (center_x + 16, center_y + 12),
        f"Center ({center_x}, {center_y})",
        fill="red"
    )

    output_path = "phase0_sanity/coordinate_test.png"
    screenshot.save(output_path)

    print(f"Marked screenshot saved: {output_path}")
    print("Mouse will move to the center of the screen in 5 seconds.")

    time.sleep(5)

    pyautogui.moveTo(center_x, center_y, duration=1)

    print("Coordinate test complete.")
    print("compare the marked screenshot with the actual mouse position to verify accuracy.")


if __name__ == "__main__":
    main()

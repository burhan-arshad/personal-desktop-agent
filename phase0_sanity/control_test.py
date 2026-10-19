
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

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3


def main():
    print("Screen size:", pyautogui.size())
    print("Mouse will start moving to the center of the screen in 5 seconds.")
    print("Emergency stop: Move the mouse to the top-left corner of the screen to abort.")

    time.sleep(5)

    x = pyautogui.size().width // 2
    y = pyautogui.size().height // 2

    print(f"Mouse move kar rahe hain: ({x}, {y})")

    pyautogui.moveTo(x, y, duration=1)

    print("Mouse move successful.")
    print("Open Notepad and focus on it for the typing test.")
    print("Typing will Start in 5 seconds")

    time.sleep(5)

    pyautogui.write("Hello from Phase 0!", interval=0.08)

    print("Keyboard typing command complete.")


if __name__ == "__main__":
    main()

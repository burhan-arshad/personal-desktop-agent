
import time
import string

import pyautogui
from PIL import Image


pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3

VALID_CELLS = {
    f"{column}{row}"
    for column in string.ascii_uppercase[:16]
    for row in range(1, 17)
}

ALLOWED_KEYS = {
    "enter", "tab", "esc", "space", "backspace",
    "delete", "up", "down", "left", "right",
    "home", "end", "pageup", "pagedown",
}

def cell_to_screen_coordinates(grid_cell, grid_image):
    if grid_cell not in VALID_CELLS:
        raise ValueError(f"Grid cell is not Valid: {grid_cell}")

    if isinstance(grid_image, (str, bytes)):
        with Image.open(grid_image) as image:
            image_width, image_height=image.size
    elif isinstance(grid_image, (Image.Image)):
        image_width, image_height=grid_image.size
    else:
        raise TypeError("Image is not PIL type")

    screen_width, screen_height=pyautogui.size()
    column_index = string.ascii_uppercase.index(grid_cell[0])
    row_index = int(grid_cell[1:]) - 1

    cell_width = image_width / 16
    cell_height = image_height / 16

    image_x = (column_index + 0.5) * cell_width
    image_y = (row_index + 0.5) * cell_height
    
    screen_x = round(image_x * screen_width / image_width)
    screen_y = round(image_y * screen_height / image_height)
    
    return screen_x, screen_y

def normalized_to_screen_coordinates(x, y):
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise TypeError("Coordinates must be numeric.")

    if not (0 <= x <= 1 and 0 <= y <= 1):
        raise ValueError("Normalized coordinates must be between 0 and 1.")

    screen_width, screen_height = pyautogui.size()

    screen_x = round(x * (screen_width - 1))
    screen_y = round(y * (screen_height - 1))

    return screen_x, screen_y

def validate_screen_coordinates(x, y):
    """
    Validate absolute screen pixel coordinates.
    """

    if (
        not isinstance(x, int)
        or not isinstance(y, int)
        or isinstance(x, bool)
        or isinstance(y, bool)
    ):
        raise TypeError(
            "Screen coordinates must be integers."
        )

    screen_width, screen_height = pyautogui.size()

    if not (0 <= x < screen_width):
        raise ValueError("X coordinate is outside the screen.")

    if not (0 <= y < screen_height):
        raise ValueError("Y coordinate is outside the screen.")

    return x, y

def execute_action(action_data, grid_image, confirm=False):

    if not isinstance(action_data, dict):
        raise ValueError("Action data must be a dictionary.")

    action = action_data.get("action")

    if action == "done":
        print("Action Done, No execution Needed")
        return

    if action == "wait":
        time.sleep(1)
        print("Wait is Done")
        return

    if action not in {"click", "type", "press", "scroll"}:
        raise ValueError(f"Action is not Supported: {action}")

    if not confirm:
        raise PermissionError(
            "Action blocked. Review the proposed action and pass confirm=True."
        )

    if action == "click":

        grid_cell = action_data.get("grid_cell")
        coordinates = action_data.get("coordinates")
        screen_coordinates = action_data.get("screen_coordinates")

        coordinate_sources = [
            grid_cell is not None,
            coordinates is not None,
            screen_coordinates is not None,
        ]

        if sum(coordinate_sources) != 1:
            raise ValueError(
                "Click requires exactly one coordinate source: "
                "grid_cell, coordinates, or screen_coordinates."
            )

        if grid_cell is not None:
            x, y = cell_to_screen_coordinates(
                grid_cell,
                grid_image
            )

            print(f"Grid click: {grid_cell} -> ({x}, {y})")

        elif coordinates is not None:
            x, y = normalized_to_screen_coordinates(
                coordinates["x"],
                coordinates["y"]
            )

            print(
                f"Normalized coordinate click: "
                f"{coordinates} -> ({x}, {y})"
            )

        else:
            x, y = validate_screen_coordinates(
                screen_coordinates["x"],
                screen_coordinates["y"]
            )

            print(
                f"UIA pixel click: "
                f"({x}, {y})"
            )

        pyautogui.click(x, y)
    elif action == "type":

        text = action_data.get("text")

        if not isinstance(text, str) or not text:
            raise ValueError("Type action requires non-empty text.")

        pyautogui.write(text)

    elif action == "press":

        key = action_data.get("key")

        if key not in ALLOWED_KEYS:
            raise ValueError(f"Keyboard key is not allowed: {key}")

        pyautogui.press(key)

    elif action == "scroll":

        direction = action_data.get("scroll_direction")

        if direction not in {"up", "down"}:
            raise ValueError("Scroll must be up or down.")

        pyautogui.scroll(
            5 if direction == "up" else -5
        )

    time.sleep(0.7)
    print(f"Action '{action}' Executed")

if __name__ == "__main__":

    test_action = {
        "action": "click",
        "grid_cell": None,
        "coordinates": {"x": 0.75, "y": 0.25},
        "text": "",
        "key": "",
        "scroll_direction": "",
        "target": "Small test button",
        "risk_level": "safe",
        "reason": "Testing exact coordinate conversion."
    }

    print("\nTesting exact coordinate click:")

    x, y = normalized_to_screen_coordinates(
        test_action["coordinates"]["x"],
        test_action["coordinates"]["y"]
    )

    print(f"Normalized coordinates: {test_action['coordinates']}")
    print(f"Screen coordinates: ({x}, {y})")

    print("\nTesting actuator without execution:")

    try:
        execute_action(test_action, None, confirm=False)
    except PermissionError as error:
        print("Safety check passed:", error)
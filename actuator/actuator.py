
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

def execute_action(action_data, grid_image, confirm=False):
    if not isinstance(action_data, (dict)):
        raise ValueError(f"Action Data is not in Valid Format {action_data}")

    action=action_data.get("action")

    if action=="done":
        print("Action Done, No execution Needed")
        return
    
    if action=="wait":
        time.sleep(1)
        print("Wait is Done")
        return

    if action not in {"click", "type", "press", "scroll"}:
        raise ValueError(f"Action is not Supported {action}")

    
    if not confirm:
        raise PermissionError(
                    "Action blocked. Review the proposed action and pass confirm=True."
                )

    if action=="click":
        cell=action_data.get("grid_cell")
        x,y =cell_to_screen_coordinates(cell,grid_image)

        print(f"Click target: {cell} -> screen coordinates ({x}, {y})")
        pyautogui.click(x,y)
    elif action=="type":
        text=action_data.get("text")
        if not isinstance(text, str) or not text:
            raise ValueError("Type action requires non-empty text")
        pyautogui.write(text)

    elif action=="press":
        key= action_data.get("key")
        if key not in ALLOWED_KEYS:
            raise ValueError(f"Keyboard key is not allowed: {key}")

        pyautogui.press(key)

    elif action=="scroll":
        direction=action_data.get("scroll_direction")
        if direction not in {"up", "down"}:
            raise ValueError("Scroll Must be Up or Down")
        pyautogui.scroll(5 if direction=="up" else -5)

    time.sleep(0.7)
    print(f"Action '{action}' Executed")
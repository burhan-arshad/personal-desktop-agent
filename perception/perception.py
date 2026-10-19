import ctypes
from io import BytesIO
from pathlib import Path
import string

import mss
import pyautogui
from PIL import Image, ImageDraw, ImageFont

MAX_IMAGE_WIDTH=1024
GRID_COLS=8
GRID_ROWS=8

PROJECT_ROOT=Path(__file__).resolve().parent.parent
OUTPUT_DIR=PROJECT_ROOT/"phase0_sanity"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except (AttributeError, OSError):
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass

def taking_screenshot():
    """Taking Screenshot and Returning Image in the form of PIL"""
    with mss.MSS() as screen:
        monitor=screen.monitors[1]
        screenshot=screen.grab(monitor)
        image = Image.frombytes(
            "RGB",
            screenshot.size,
            screenshot.rgb
        )
    return image

def resize_screenshot(image):
    original_width, original_height= image.size
    if original_width<=MAX_IMAGE_WIDTH:
        return image.copy()
    
    scale=original_width/MAX_IMAGE_WIDTH
    new_width=MAX_IMAGE_WIDTH
    new_height=round(original_height*scale)

    return image.resize(
        (new_width,new_height),
        Image.Resampling.LANCZOS
    )

def draw_grid(image):
    """Drawing Grid on Image like spreadsheet A1-H8"""
    image=image.copy()
    draw=ImageDraw.Draw(image, "RGBA")

    width, height=image.size
    cell_width=width/GRID_COLS
    cell_height=height/GRID_ROWS
    try:
            font = ImageFont.truetype("arial.ttf", 14)
    except OSError:
            font = ImageFont.load_default()

    for col in range(GRID_COLS+1):
        x=round(col*cell_width)
        draw.line(
            [(x,0),(x,height)],
            fill=(0, 220, 255, 190),
            width=1
        )

    for row in range(GRID_ROWS+1):
        y=round(row*cell_height)
        draw.line(
            [(0,y),(width,y)],
            fill=(0, 220, 255, 190),
            width=1
        )

    columns=string.ascii_uppercase[:GRID_COLS]

    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            label=f"{columns[col]},{row+1}"
            x=round(col*cell_width)+4
            y=round(row*cell_height)+4
            text_box=draw.textbbox((x,y), label, font=font)
            draw.rounded_rectangle(
                (
                    text_box[0]-3,
                    text_box[1]-2,
                    text_box[2]+3,
                    text_box[3]+2
                ),
                radius=3,
                fill=(0, 0, 0, 190)
            )
            draw.text(
                (x,y),
                label,
                font=font,
                fill=(255, 255, 255, 255)
            )
    return image

def capture_grid(save_image=True):
    """
    Will Capture image and Draw Grid on Image to Show it to AI.
    """
    original_image=taking_screenshot()
    resized_image=resize_screenshot(original_image)
    grid_image=draw_grid(resized_image)

    if save_image:
        output_path=OUTPUT_DIR/"phase1_grid.png"
        grid_image.save(output_path)
        print(f"Original screen size: {original_image.size}")
        print(f"Grid image size: {grid_image.size}")
        print(f"Grid screenshot saved: {output_path}")

    return grid_image




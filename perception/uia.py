from pywinauto import Desktop


def find_taskbar_element(app_name: str):
    """
    Find an application button in the Windows taskbar
    and return its bounding rectangle.
    """

    if not app_name or not app_name.strip():
        return {
            "found": False,
            "reason": "Application name cannot be empty."
        }

    try:
        desktop = Desktop(backend="uia")
        taskbar = desktop.window(class_name="Shell_TrayWnd")

        buttons = taskbar.descendants(control_type="Button")

        for button in buttons:
            try:
                name = button.window_text().strip()

                if name.lower() == app_name.strip().lower():
                    rect = button.rectangle()

                    return {
                        "found": True,
                        "target": name,
                        "automation_id": button.element_info.automation_id,
                        "bbox": {
                            "left": rect.left,
                            "top": rect.top,
                            "right": rect.right,
                            "bottom": rect.bottom
                        },
                        "center": {
                            "x": (rect.left + rect.right) // 2,
                            "y": (rect.top + rect.bottom) // 2
                        }
                    }

            except Exception:
                continue

        return {
            "found": False,
            "reason": f"{app_name} not found in taskbar."
        }

    except Exception as error:
        return {
            "found": False,
            "reason": str(error)
        }


def prepare_taskbar_click(app_name: str):
    """
    Locate a taskbar application and prepare a click action.
    Does not execute the click.
    """

    result = find_taskbar_element(app_name)

    if not result["found"]:
        return {
            "found": False,
            "reason": result["reason"]
        }

    center = result["center"]

    action = {
        "action": "click",
        "grid_cell": None,
        "coordinates": None,
        "screen_coordinates": {
            "x": center["x"],
            "y": center["y"]
        },
        "text": "",
        "key": "",
        "scroll_direction": "",
        "target": result["target"],
        "reason": (
            f"Located {result['target']} "
            "in the Windows taskbar using UI Automation."
        ),
        "risk_level": "safe"
    }

    return {
        "found": True,
        "action": action,
        "element": result
    }
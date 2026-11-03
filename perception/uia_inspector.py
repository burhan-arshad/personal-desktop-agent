import ctypes
from pywinauto import Desktop
import json


def inspect_active_window():
    """
    Inspect the currently active window using Windows UI Automation.
    Read-only: does not perform any interaction.
    """

    try:
        foreground_handle = ctypes.windll.user32.GetForegroundWindow()

        if not foreground_handle:
            return {
                "success": False,
                "reason": "No active window found."
            }

        desktop = Desktop(backend="uia")

        window = desktop.window(handle=foreground_handle)

        if not window.exists():
            return {
                "success": False,
                "reason": "Active window could not be accessed through UIA."
            }

        window_info = {
            "title": window.window_text(),
            "class_name": window.class_name(),
            "process_id": window.process_id(),
            "elements": []
        }

        for element in window.descendants():

            try:
                info = element.element_info
                rect = element.rectangle()

                window_info["elements"].append({
                    "name": info.name,
                    "control_type": info.control_type,
                    "automation_id": info.automation_id,
                    "class_name": info.class_name,
                    "enabled": element.is_enabled(),
                    "visible": element.is_visible(),
                    "bbox": {
                        "left": rect.left,
                        "top": rect.top,
                        "right": rect.right,
                        "bottom": rect.bottom
                    }
                })

            except Exception:
                continue

        return {
            "success": True,
            "window": window_info
        }

    except Exception as error:
        return {
            "success": False,
            "reason": str(error)
        }


if __name__ == "__main__":

    result = inspect_active_window()

    if result["success"]:

        window = result["window"]

        print("\n========== ACTIVE WINDOW ==========")
        print(f"Title: {window['title']}")
        print(f"Class: {window['class_name']}")
        print(f"Process ID: {window['process_id']}")

        print("\n========== UI ELEMENTS ==========")

        for index, element in enumerate(window["elements"], start=1):

            print(f"\nElement #{index}")
            print(f"Name: {element['name']}")
            print(f"Type: {element['control_type']}")
            print(f"Automation ID: {element['automation_id']}")
            print(f"Bounding Box: {element['bbox']}")

        print(f"\nTotal elements found: {len(window['elements'])}")

    else:
        print("\n[ERROR]", result["reason"])

def get_interactive_elements():
    result = inspect_active_window()

    if not result["success"]:
        return result

    elements = result["window"]["elements"]

    allowed_types = {
        "Button",
        "Edit",
        "ComboBox",
        "Tab",
        "TabItem",
        "MenuItem",
        "CheckBox",
        "RadioButton"
    }

    filtered = []

    for index, element in enumerate(elements):

        if element["control_type"] not in allowed_types:
            continue

        if not element["visible"]:
            continue

        if not element["enabled"]:
            continue

        if not element["name"].strip() and not element["automation_id"].strip():
            continue

        filtered.append({
            "index": index,
            "name": element["name"],
            "control_type": element["control_type"],
            "automation_id": element["automation_id"],
            "bbox": element["bbox"]
        })

    return {
        "success": True,
        "window_title": result["window"]["title"],
        "elements": filtered
    }




def find_active_window_element(
    name: str = None,
    control_type: str = None,
    automation_id: str = None
):
    """
    Find an element inside the currently active window.
    Read-only: does not click or interact with the element.
    """

    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()

        if not hwnd:
            return {
                "found": False,
                "reason": "No active window found."
            }

        desktop = Desktop(backend="uia")
        window = desktop.window(handle=hwnd)

        if not window.exists():
            return {
                "found": False,
                "reason": "Active window could not be accessed."
            }

        matches = []

        for element in window.descendants():
            try:
                info = element.element_info

                if name and info.name.strip().lower() != name.strip().lower():
                    continue

                if control_type and info.control_type != control_type:
                    continue

                if automation_id and info.automation_id != automation_id:
                    continue

                if not element.is_visible() or not element.is_enabled():
                    continue

                rect = element.rectangle()

                if rect.width() <= 0 or rect.height() <= 0:
                    continue

                matches.append({
                    "name": info.name,
                    "control_type": info.control_type,
                    "automation_id": info.automation_id,
                    "bbox": {
                        "left": rect.left,
                        "top": rect.top,
                        "right": rect.right,
                        "bottom": rect.bottom
                    }
                })

            except Exception:
                continue

        return {
            "found": len(matches) > 0,
            "count": len(matches),
            "matches": matches
        }

    except Exception as error:
        return {
            "found": False,
            "reason": str(error)
        }


if __name__ == "__main__":

    result = get_interactive_elements()

    if result["success"]:

        print(f"\nWindow: {result['window_title']}")

        for element in result["elements"]:
            print(element)

        print(f"\nTotal interactive elements: {len(result['elements'])}")

    else:
        print("[ERROR]", result["reason"])
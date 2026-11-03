
import ctypes
from ctypes import wintypes
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

def _check_expected_window(current_window, expected_window):
    """Prevent UIA interaction with a different foreground window."""

    if not expected_window:
        return True

    if not isinstance(expected_window, dict):
        return False

    expected_handle = expected_window.get("handle")

    if expected_handle is not None:
        return int(current_window["handle"]) == int(expected_handle)

    expected_title = expected_window.get("title")

    if expected_title:
        return current_window["title"] == expected_title

    return False


def discover_active_window_elements(max_elements: int = 250):
    """
    Read visible and enabled UIA elements from the active window.
    Read-only: does not click, type, or modify anything.
    """

    if (
        isinstance(max_elements, bool)
        or not isinstance(max_elements, int)
        or max_elements < 1
    ):
        return {
            "success": False,
            "reason": "max_elements must be a positive integer."
        }

    try:
        window, result = _get_active_window()

        if not result["success"]:
            return result

        elements = []
        truncated = False

        for element in window.descendants():

            try:
                if len(elements) >= max_elements:
                    truncated = True
                    break

                info = element.element_info

                if not element.is_visible() or not element.is_enabled():
                    continue

                rect = element.rectangle()

                if rect.width() <= 0 or rect.height() <= 0:
                    continue

                elements.append({
                    "name": info.name or "",
                    "control_type": info.control_type or "",
                    "automation_id": info.automation_id or "",
                    "class_name": info.class_name or "",
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
            "window": result["window"],
            "count": len(elements),
            "truncated": truncated,
            "elements": elements
        }

    except Exception as error:
        return {
            "success": False,
            "reason": str(error)
        }


def find_active_window_element(
    name: str = None,
    control_type: str = None,
    automation_id: str = None,
    max_elements: int = 250
):
    """
    Find matching elements in the active window.
    Read-only: does not interact with the UI.
    """

    result = discover_active_window_elements(max_elements=max_elements)

    if not result["success"]:
        return {
            "found": False,
            "reason": result["reason"]
        }

    matches = []

    for element in result["elements"]:

        element_name = element["name"].strip()
        element_type = element["control_type"]
        element_id = element["automation_id"]

        if name and name.strip().lower() not in element_name.lower():
            continue

        if control_type and element_type != control_type:
            continue

        if automation_id and element_id != automation_id:
            continue

        matches.append(element)

    return {
        "found": len(matches) > 0,
        "count": len(matches),
        "matches": matches,
        "window": result["window"],
        "truncated": result["truncated"]
    }


def click_uia_element(
    name: str = None,
    control_type: str = None,
    automation_id: str = None,
    expected_window: dict = None
):
    """
    Click exactly one matching UIA element.
    Rejects zero or multiple matches.
    Optionally verifies the expected foreground window.
    """

    try:
        window, result = _get_active_window()

        if not result["success"]:
            return result

        if not _check_expected_window(
            result["window"],
            expected_window
        ):
            return {
                "success": False,
                "reason": "Active window changed since action preparation."
            }

        matches = []

        for element in window.descendants():

            try:
                info = element.element_info

                if (
                    name
                    and name.strip().lower()
                    not in (info.name or "").strip().lower()
                ):
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

                matches.append(element)

            except Exception:
                continue

        if len(matches) == 0:
            return {
                "success": False,
                "reason": "No matching element found."
            }

        if len(matches) > 1:
            return {
                "success": False,
                "reason": (
                    f"Ambiguous target: {len(matches)} "
                    "matching elements found."
                )
            }

        element = matches[0]

        try:
            element.invoke()
        except Exception:
            element.click_input()

        return {
            "success": True,
            "message": "UIA element clicked successfully."
        }

    except Exception as error:
        return {
            "success": False,
            "reason": str(error)
        }


def type_uia_text(
    text: str,
    name: str = None,
    automation_id: str = None,
    expected_window: dict = None
):
    """
    Enter text into exactly one matching editable UIA element.
    Does not submit the form or press Enter.
    Optionally verifies the expected foreground window.
    """

    if not isinstance(text, str) or not text:
        return {
            "success": False,
            "reason": "Text cannot be empty."
        }

    try:
        window, result = _get_active_window()

        if not result["success"]:
            return result

        if not _check_expected_window(
            result["window"],
            expected_window
        ):
            return {
                "success": False,
                "reason": "Active window changed since action preparation."
            }

        matches = []

        for element in window.descendants():

            try:
                info = element.element_info

                if (
                    name
                    and name.strip().lower()
                    != (info.name or "").strip().lower()
                ):
                    continue

                if automation_id and info.automation_id != automation_id:
                    continue

                if info.control_type not in {"Edit", "ComboBox"}:
                    continue

                if not element.is_visible() or not element.is_enabled():
                    continue

                rect = element.rectangle()

                if rect.width() <= 0 or rect.height() <= 0:
                    continue

                matches.append(element)

            except Exception:
                continue

        if len(matches) == 0:
            return {
                "success": False,
                "reason": "No matching editable element found."
            }

        if len(matches) > 1:
            return {
                "success": False,
                "reason": (
                    f"Ambiguous input: {len(matches)} "
                    "matching elements found."
                )
            }

        element = matches[0]

        element.set_focus()
        element.set_edit_text(text)

        return {
            "success": True,
            "message": "Text entered successfully."
        }

    except Exception as error:
        return {
            "success": False,
            "reason": str(error)
        }


def prepare_uia_click(
    name: str,
    control_type: str = None,
    automation_id: str = None
):
    """
    Prepare a UIA click action without executing it.
    """

    result = find_active_window_element(
        name=name,
        control_type=control_type,
        automation_id=automation_id
    )

    if not result["found"]:
        return {
            "success": False,
            "reason": result.get("reason", "Element not found.")
        }

    if result["count"] != 1:
        return {
            "success": False,
            "reason": "Multiple matching elements found."
        }

    if result["truncated"]:
        return {
            "success": False,
            "reason": "Discovery was truncated; increase max_elements."
        }

    element = result["matches"][0]

    return {
        "success": True,
        "action": {
            "action": "uia_click",
            "target": element["name"],
            "control_type": element["control_type"],
            "automation_id": element["automation_id"],
            "text": "",
            "risk_level": "risky",
            "reason": f"Click UI element: {element['name']}"
        },
        "window": result["window"]
    }


def prepare_uia_type(
    text: str,
    name: str,
    automation_id: str = None
):
    """
    Prepare a UIA typing action without executing it.
    """

    if not isinstance(text, str) or not text:
        return {
            "success": False,
            "reason": "Text cannot be empty."
        }

    result = find_active_window_element(
        name=name,
        automation_id=automation_id
    )

    if not result["found"]:
        return {
            "success": False,
            "reason": result.get("reason", "Input field not found.")
        }

    if result["truncated"]:
        return {
            "success": False,
            "reason": "Discovery was truncated; increase max_elements."
        }

    editable_matches = [
        element
        for element in result["matches"]
        if element["control_type"] in {"Edit", "ComboBox"}
    ]

    if len(editable_matches) == 0:
        return {
            "success": False,
            "reason": "No matching editable element found."
        }

    if len(editable_matches) > 1:
        return {
            "success": False,
            "reason": "Multiple matching input fields found."
        }

    element = editable_matches[0]

    return {
        "success": True,
        "action": {
            "action": "uia_type",
            "target": element["name"],
            "control_type": element["control_type"],
            "automation_id": element["automation_id"],
            "text": text,
            "risk_level": "risky",
            "reason": f"Enter text into: {element['name']}"
        },
        "window": result["window"]
    }

def validate_active_window(expected_window: dict) -> dict:
    """
    Verify that the foreground window is the same window
    in which the UIA action was originally prepared.
    """

    if not isinstance(expected_window, dict):
        return {
            "success": False,
            "reason": "Expected window metadata is missing or invalid."
        }

    expected_handle = expected_window.get("handle")
    expected_pid = expected_window.get("process_id")
    expected_title = expected_window.get("title", "")

    if not expected_handle:
        return {
            "success": False,
            "reason": "Expected window handle is missing."
        }

    user32 = ctypes.windll.user32

    actual_handle = user32.GetForegroundWindow()

    if actual_handle != int(expected_handle):
        return {
            "success": False,
            "reason": (
                "Foreground window changed after action preparation. "
                "Execution cancelled."
            ),
            "expected_handle": int(expected_handle),
            "actual_handle": actual_handle
        }

    actual_pid = wintypes.DWORD()

    user32.GetWindowThreadProcessId(
        actual_handle,
        ctypes.byref(actual_pid)
    )

    if (
        expected_pid is not None
        and actual_pid.value != int(expected_pid)
    ):
        return {
            "success": False,
            "reason": "Foreground window process ID does not match.",
            "expected_pid": int(expected_pid),
            "actual_pid": actual_pid.value
        }

    title_buffer = ctypes.create_unicode_buffer(512)

    user32.GetWindowTextW(
        actual_handle,
        title_buffer,
        len(title_buffer)
    )

    actual_title = title_buffer.value

    if expected_title and actual_title != expected_title:
        return {
            "success": False,
            "reason": "Foreground window title does not match.",
            "expected_title": expected_title,
            "actual_title": actual_title
        }

    return {
        "success": True,
        "message": "Foreground window verified successfully.",
        "window": {
            "handle": actual_handle,
            "process_id": actual_pid.value,
            "title": actual_title
        }
    }
import os
import re
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

from perception.perception import capture_grid
from brain.brain import classify_skill



PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = PROJECT_ROOT / "memory" / "screenshots"


SKILL_DEFINITIONS = {
    "open_app": {
        "description": "Launch a supported installed desktop application.",
        "risk_level": "safe",
    },
    "search_web": {
        "description": "Search the web for a specific query.",
        "risk_level": "safe",
    },
    "send_whatsapp_message": {
        "description": "Send a WhatsApp message to a specified phone number or name.",
        "risk_level": "risky",
    },
    "open_file_explorer": {
        "description": "Open an existing folder in Windows File Explorer.",
        "risk_level": "safe",
    },
    "take_screenshot": {
        "description": "Capture and save a screenshot using the perception module.",
        "risk_level": "safe",
    },
}


APP_ALIASES = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "command prompt": "cmd.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "task manager": "taskmgr.exe",
}

def _remove_prefix(text, prefixes):
    result = text.strip()

    for prefix in prefixes:
        result = re.sub(
            rf"^\s*{re.escape(prefix)}\s*",
            "",
            result,
            flags=re.IGNORECASE,
        )

    return result.strip(" \t\r\n\"'")

def prepare_open_app(instruction):
    app_name=_remove_prefix(
        instruction,
        [
                    "please open the app",
                    "please open",
                    "open the app",
                    "open app",
                    "launch the app",
                    "launch",
                    "app kholo",
                    "application kholo",
                    "kholo",
                    "open",
                ],
    ).lower()

    if app_name not in APP_ALIASES:
        raise ValueError(f"{app_name} is not Supported Currently, While" + ", ".join(APP_ALIASES))

    return {"app_name": app_name}

def open_app(payload):
    executable=APP_ALIASES[payload["app_name"]]
    subprocess.Popen([executable])
    return f"{payload["app_name"]} is Opened"

def prepare_search_web(instruction):
    query=_remove_prefix(
        instruction,
        [
            "search the web for",
            "search google for",
            "google search for",
            "search for",
            "google",
            "search",
        ],
    ).lower()

    query = re.sub(
        r"^\s*browser kholo\s*",
        "",
        query,
        flags=re.IGNORECASE,
    ).strip()

    if not query:
        raise ValueError("Please Specify What are you trying to seacrh")

    return {"query":query}

def search_web(payload):
    query=payload["query"].strip()
    if not query:
        raise ValueError("Query Cannot be empty")

    url = "https://www.google.com/search?q=" + quote_plus(query)
    webbrowser.open(url)

    return f"Opened browser search for: {query}"

def prepare_send_whatsapp_message(instruction):
    phone_match = re.search(
        r"(?<!\w)(\+\d{10,15})(?!\w)",
        instruction,
    )

    if not phone_match:
        raise ValueError(
            "Include the recipient's international phone number, "
            "for example +923001234567."
        )

    message_match = re.search(
        r"\bmessage\s*:\s*(.+)$",
        instruction,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not message_match:
        raise ValueError(
            'Add the message after "message:", '
            'for example: message: Assalam o Alaikum'
        )

    message = message_match.group(1).strip().strip("\"'")

    if not message:
        raise ValueError("WhatsApp message cannot be empty.")

    return {
        "phone": phone_match.group(1),
        "message": message,
    }

def send_whatsapp_message(payload):
    try:
        import pywhatkit
    except ImportError as error:
        raise RuntimeError(
            "pywhatkit is not installed. Run: "
            "python -m pip install pywhatkit"
        ) from error

    pywhatkit.sendwhatmsg_instantly(
        phone_no=payload["phone"],
        message=payload["message"],
        wait_time=20,
        tab_close=False
    )
    return "Whatsapp Message request send"

def prepare_open_file_explorer(instruction):
    text = instruction.strip()

    path_match = re.search(r'"([^"]+)"', text)

    if path_match:
        folder = Path(path_match.group(1)).expanduser()
    else:
        folder = Path.home()

        cleaned = _remove_prefix(
            text,
            [
                "open file explorer at",
                "open file explorer",
                "open folder",
                "folder kholo",
                "file explorer kholo",
            ],
        )

        if cleaned and cleaned.lower() not in {
            "this pc",
            "my computer",
            "file explorer",
        }:
            candidate = Path(cleaned).expanduser()

            if candidate.is_absolute():
                folder = candidate

    if not folder.exists() or not folder.is_dir():
        raise ValueError(
            f"Folder does not exist or is not a directory: {folder}"
        )

    return {"path": str(folder.resolve())}


def open_file_explorer(payload):
    os.startfile(payload["path"])

    return f"Opened folder: {payload['path']}"


def prepare_take_screenshot(instruction):
    return {}


def take_screenshot(payload):
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    screenshot = capture_grid(save_image=False)

    destination = (
        SCREENSHOT_DIR
        / "skill_screenshot.png"
    )

    screenshot.save(destination, format="PNG")

    return f"Screenshot saved to {destination}"

SKILL_REGISTRY = {
    "open_app": {
        "description": SKILL_DEFINITIONS["open_app"]["description"],
        "risk_level": SKILL_DEFINITIONS["open_app"]["risk_level"],
        "prepare": prepare_open_app,
        "execute": open_app,
    },
    "search_web": {
        "description": SKILL_DEFINITIONS["search_web"]["description"],
        "risk_level": SKILL_DEFINITIONS["search_web"]["risk_level"],
        "prepare": prepare_search_web,
        "execute": search_web,
    },
    "send_whatsapp_message": {
        "description": SKILL_DEFINITIONS["send_whatsapp_message"]["description"],
        "risk_level": SKILL_DEFINITIONS["send_whatsapp_message"]["risk_level"],
        "prepare": prepare_send_whatsapp_message,
        "execute": send_whatsapp_message,
    },
    "open_file_explorer": {
        "description": SKILL_DEFINITIONS["open_file_explorer"]["description"],
        "risk_level": SKILL_DEFINITIONS["open_file_explorer"]["risk_level"],
        "prepare": prepare_open_file_explorer,
        "execute": open_file_explorer,
    },
    "take_screenshot": {
        "description": SKILL_DEFINITIONS["take_screenshot"]["description"],
        "risk_level": SKILL_DEFINITIONS["take_screenshot"]["risk_level"],
        "prepare": prepare_take_screenshot,
        "execute": take_screenshot,
    },
}

def match_skill(instruction):
    """
    Match common user instructions to a skill using keywords.
    Returns a skill name or None.
    """

    if not isinstance(instruction, str) or not instruction.strip():
        return None

    text = instruction.lower().strip()

    patterns = {
        "send_whatsapp_message": [
            "send whatsapp message",
            "send a whatsapp message",
            "whatsapp message to",
            "message on whatsapp",
        ],
        "open_file_explorer": [
            "open file explorer",
            "open folder",
            "file explorer kholo",
            "folder kholo",
        ],
        "take_screenshot": [
            "take a screenshot",
            "take screenshot",
            "capture screenshot",
            "screenshot of my desktop",
        ],
        "search_web": [
            "search the web for",
            "search google for",
            "google search for",
            "search for",
        ],
        "open_app": [
            "open app",
            "open the app",
            "launch app",
            "launch the app",
            "open notepad",
            "open calculator",
            "open paint",
            "open powershell",
            "open command prompt",
        ],
    }

    matches = [
        skill_name
        for skill_name, phrases in patterns.items()
        if any(phrase in text for phrase in phrases)
    ]

    if len(matches) != 1:
        return None

    return matches[0]


def resolve_skill(instruction):
    """
    Try keyword matching first.
    If no keyword match exists, use the text-only LLM classifier.
    Returns a skill name or None.
    """

    skill_name = match_skill(instruction)

    if skill_name:
        print(f"[SKILL MATCHER] Matched: {skill_name}")
        return skill_name

    print("[SKILL MATCHER] No keyword match. Trying LLM...")

    skill_name = classify_skill(instruction)

    if skill_name:
        print(f"[SKILL RESOLVER] Selected: {skill_name}")
        return skill_name

    print("[SKILL RESOLVER] No suitable skill found.")
    return None
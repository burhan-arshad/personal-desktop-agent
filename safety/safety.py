
import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR=Path(__file__).resolve().parent.parent
AUDIT_LOG=PROJECT_DIR/"safety_audit.jsonl"

RISKY_KEYWORDS = {
    "send",
    "delete",
    "submit",
    "purchase",
    "pay",
    "payment",
    "confirm",
    "remove",
    "password",
    "credentials",
}

BLOCKED_PATTERNS = [
    "format c:",
    "format c drive",
    "format the c drive",
    "delete system32",
    "delete windows folder",
    "delete system files",
    "kill all processes",
    "disable security",
]

def action_text(action: dict) -> str:
    fields = (
        "action",
        "target",
        "text",
        "reason",
        "reasoning",
    )

    return " ".join(
        str(action.get(field, ""))
        for field in fields
    ).lower()

def classify_risk(action: dict)->str:
    if not isinstance(action, dict):
        return "blocked"

    text=action_text(action)
    if any(pattern in text for pattern in BLOCKED_PATTERNS):
        return "blocked"

    model_risk = str(action.get("risky_level","")).lower()
    if model_risk=="risky":
        return "risky"

    if model_risk!="safe":
        return "risky"

    words=set(text.replace('/',' ').replace('-',' ').split())
    if words.intersaction(RISKY_KEYWORDS):
        return "risky"

    allowed_actions = {
        "click",
        "type",
        "press",
        "scroll",
        "wait",
        "done",
    }

    if action.get("action") not in allowed_actions:
        return "blocked"

    return "safe"

def confirm_with_human(action: dict) -> bool:
    print("\n[HUMAN REVIEW REQUIRED]")
    print(f"Action: {action.get('action', 'unknown')}")
    print(f"Target: {action.get('target', 'unspecified')}")
    print(f"Text: {action.get('text', 'unspecified')}")
    print(f"Reason: {action.get('reason', 'unspecified')}")

    response = input("Approve this action? (yes/no): ").strip().lower()

    return response in {"yes", "y"}


def log_decision(
    action: dict,
    risk_level: str,
    user_response: str,
) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "risk_level": risk_level,
        "user_response": user_response,
    }

    with AUDIT_LOG.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(record, ensure_ascii=False) + "\n"
        )

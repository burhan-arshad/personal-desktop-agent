import json
import re
from datetime import datetime, timezone
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
AUDIT_LOG = PROJECT_DIR / "safety_audit.jsonl"


ALLOWED_ACTIONS = {
    "click",
    "type",
    "press",
    "scroll",
    "wait",
    "done",
}


RISKY_KEYWORDS = {
    "send",
    "sends",
    "sending",
    "delete",
    "deletes",
    "deleting",
    "deleted",
    "submit",
    "submits",
    "submitting",
    "purchase",
    "purchases",
    "purchasing",
    "pay",
    "pays",
    "paying",
    "payment",
    "payments",
    "confirm",
    "confirms",
    "confirming",
    "remove",
    "removes",
    "removing",
    "removed",
    "password",
    "passwords",
    "credential",
    "credentials",
}


BLOCKED_PATTERNS = {
    "windows system32",
    "delete system32",
    "delete the windows system32 folder",
    "format c",
    "format the c drive",
    "format c drive",
    "format the system drive",
    "delete system files",
    "delete windows folder",
    "delete the windows folder",
    "delete windows system files",
    "erase system files",
    "wipe the system drive",
    "wipe c drive",
    "destroy system files",
}


def normalize_text(value: str) -> str:
    """Normalize text to make phrase checks less sensitive to punctuation."""
    value = str(value).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def action_text(action: dict) -> str:
    """Combine relevant action fields for safety analysis."""
    fields = (
        "action",
        "target",
        "text",
        "reason",
        "reasoning",
    )

    return normalize_text(
        " ".join(
            str(action.get(field, ""))
            for field in fields
        )
    )


def classify_risk(action: dict) -> str:
    """Return safe, risky, or blocked for a proposed action."""

    if not isinstance(action, dict):
        return "blocked"

    action_name = str(action.get("action", "")).strip().lower()

    # Reject unknown actions before considering execution.
    if action_name not in ALLOWED_ACTIONS:
        return "blocked"

    text = action_text(action)

    # Block known destructive system-operation patterns.
    if any(
        normalize_text(pattern) in text
        for pattern in BLOCKED_PATTERNS
    ):
        return "blocked"

    # Respect the model's risk assessment conservatively.
    model_risk = str(
        action.get("risk_level", "")
    ).strip().lower()

    if model_risk == "risky":
        return "risky"

    if model_risk != "safe":
        return "risky"

    # Require approval for known sensitive actions.
    words = set(text.split())

    if words.intersection(RISKY_KEYWORDS):
        return "risky"

    return "safe"


def confirm_with_human(action: dict) -> bool:
    """Ask for explicit approval in terminal-based workflows."""
    print("\n[HUMAN REVIEW REQUIRED]")
    print(f"Action: {action.get('action', 'unknown')}")
    print(f"Target: {action.get('target', 'unspecified')}")
    print(f"Text: {action.get('text', 'unspecified')}")
    print(f"Reason: {action.get('reason', 'unspecified')}")

    response = input(
        "Approve this action? (yes/no): "
    ).strip().lower()

    return response in {"yes", "y"}


def log_decision(
    action: dict,
    risk_level: str,
    user_response: str,
) -> None:
    """Append a safety decision to the JSON Lines audit log."""
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
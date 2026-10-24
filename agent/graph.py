from typing import TypedDict
from uuid import uuid4
from io import BytesIO
from PIL import Image

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from perception.perception import capture_grid
from brain.brain import decide_action
from actuator.actuator import execute_action
from safety.safety import classify_risk, log_decision


MAX_STEPS = 8


class AgentState(TypedDict):
    instruction: str
    current_image: bytes
    last_action: dict
    history: list
    step_count: int
    is_done: bool
    risk_level: str
    human_approved: bool


def summarize_recent(history):
    if not history:
        return "No previous actions."

    lines = []

    for item in history[-3:]:
        lines.append(
            f"Action: {item.get('action', '')}, "
            f"target: {item.get('target', '')}, "
            f"cell: {item.get('grid_cell')}, "
            f"reason: {item.get('reason', '')}, "
            f"result: {item.get('result', 'unknown')}"
        )

    return "\n".join(lines)


def update_latest_history(state, result):
    history = list(state["history"])

    if history:
        history[-1] = {
            **history[-1],
            "result": result,
        }

    return history


def capture_node(state: AgentState) -> dict:
    print("\n[CAPTURE] Taking a fresh screenshot...")

    grid_image = capture_grid(save_image=True)

    image_buffer = BytesIO()
    grid_image.save(image_buffer, format="PNG")

    return {
        "current_image": image_buffer.getvalue()
    }


def think_node(state: AgentState) -> dict:
    print("\n[THINK] Asking the Brain for the next action...")

    current_image = Image.open(
        BytesIO(state["current_image"])
    ).convert("RGB")

    history_summary = summarize_recent(state["history"])

    action = decide_action(
        state["instruction"],
        current_image,
        history_summary,
    )

    print(f"Proposed action: {action}")

    # Stop immediately if the Brain cannot identify a clear next action.
    if action.get("action") == "wait":
        reason = action.get(
            "reason",
            "The next action or target is unclear.",
        )

        print("[STOP] Brain cannot identify a clear next action.")
        print(f"[REASON] {reason}")

        history_entry = {
            **action,
            "result": "stopped_unclear_target",
        }

        return {
            "last_action": {
                **action,
                "action": "done",
                "grid_cell": None,
            },
            "history": state["history"] + [history_entry],
            "is_done": True,
            "human_approved": False,
        }

    # Detect an action that repeats the previous two actions.
    if len(state["history"]) >= 2:
        previous_actions = state["history"][-2:]

        repeated = all(
            item.get("action") == action.get("action")
            and item.get("target") == action.get("target")
            and item.get("grid_cell") == action.get("grid_cell")
            and item.get("scroll_direction")
            == action.get("scroll_direction")
            for item in previous_actions
        )

        if repeated:
            print(
                "[STOP] Repeated action detected. "
                "Stopping to prevent unnecessary actions."
            )

            return {
                "last_action": {
                    "action": "done",
                    "grid_cell": None,
                    "text": "",
                    "key": "",
                    "scroll_direction": "",
                    "target": "",
                    "risk_level": "safe",
                    "reason": "Repeated action detected.",
                },
                "is_done": True,
                "human_approved": False,
                "history": state["history"] + [{
                    **action,
                    "result": "stopped_repeated_action",
                }],
            }

    history_entry = {
        **action,
        "result": "proposed",
    }

    return {
        "last_action": action,
        "history": state["history"] + [history_entry],
        "is_done": action.get("action") == "done",
        "human_approved": False,
    }


def should_continue(state: AgentState):
    if state["is_done"]:
        print("\n[ROUTER] Task stopped or marked complete.")
        return END

    if state["step_count"] >= MAX_STEPS:
        print("\n[ROUTER] Maximum attempt limit reached.")
        return END

    return "safety_check"


def safety_check_node(state: AgentState) -> dict:
    action = state["last_action"]
    risk = classify_risk(action)

    print(f"\n[SAFETY] Risk classification: {risk.upper()}")

    if risk == "blocked":
        print("[SAFETY] Blocked action will NOT be executed.")

        log_decision(action, risk, "blocked")

        return {
            "risk_level": risk,
            "human_approved": False,
            "history": update_latest_history(
                state,
                "blocked; not executed",
            ),
            "step_count": state["step_count"] + 1,
        }

    if risk == "safe":
        print("[SAFETY] Safe action; no human approval required.")

        log_decision(action, risk, "auto-approved")

        return {
            "risk_level": risk,
            "human_approved": True,
            "history": update_latest_history(
                state,
                "classified safe; proceeding",
            ),
        }

    print("[SAFETY] Human approval is required.")

    return {
        "risk_level": risk,
        "human_approved": False,
    }


def route_after_safety(state: AgentState):
    if state["risk_level"] == "blocked":
        return END

    if state["risk_level"] == "risky":
        return "human_review"

    return "act"


def human_review_node(state: AgentState) -> dict:
    action = state["last_action"]

    decision = interrupt({
        "message": "A risky action requires your approval.",
        "action": action,
        "risk_level": state["risk_level"],
        "instruction": state["instruction"],
    })

    approved = str(decision).strip().lower() in {"yes", "y"}

    response = "approved" if approved else "denied"

    log_decision(
        action,
        state["risk_level"],
        response,
    )

    if approved:
        print("\n[HUMAN REVIEW] Action approved.")

        return {
            "human_approved": True,
            "history": update_latest_history(
                state,
                "human approved; proceeding",
            ),
        }

    print("\n[HUMAN REVIEW] Action denied. Skipping execution.")

    return {
        "human_approved": False,
        "history": update_latest_history(
            state,
            "user denied this action; not executed",
        ),
        "step_count": state["step_count"] + 1,
    }


def route_after_human(state: AgentState):
    if state["human_approved"]:
        return "act"

    if state["step_count"] >= MAX_STEPS:
        return END

    return "capture"


def act_node(state: AgentState) -> dict:
    action = state["last_action"]
    risk = state["risk_level"]

    # Final safety checks before any desktop interaction.
    if risk == "blocked":
        raise RuntimeError("Blocked action cannot be executed.")

    if risk not in {"safe", "risky"}:
        raise RuntimeError(f"Invalid risk level: {risk}")

    if not state["human_approved"]:
        raise RuntimeError(
            "Action cannot execute without approval."
        )

    if risk == "risky" and not state["human_approved"]:
        raise RuntimeError(
            "Risky action requires explicit approval."
        )

    print("\n[ACT] Executing the approved or safe action.")
    print(f"Action: {action['action']}")
    print(f"Target: {action.get('target', '')}")

    current_image = Image.open(
        BytesIO(state["current_image"])
    ).convert("RGB")

    execute_action(
        action,
        current_image,
        confirm=True,
    )

    return {
        "history": update_latest_history(
            state,
            "executed; awaiting visual verification",
        ),
        "step_count": state["step_count"] + 1,
    }


def after_act(state: AgentState):
    if state["step_count"] >= MAX_STEPS:
        print("\n[ROUTER] Maximum attempt limit reached.")
        return END

    return "capture"


graph = StateGraph(AgentState)

graph.add_node("capture", capture_node)
graph.add_node("think", think_node)
graph.add_node("safety_check", safety_check_node)
graph.add_node("human_review", human_review_node)
graph.add_node("act", act_node)

graph.add_edge(START, "capture")
graph.add_edge("capture", "think")

graph.add_conditional_edges(
    "think",
    should_continue,
    {
        "safety_check": "safety_check",
        END: END,
    },
)

graph.add_conditional_edges(
    "safety_check",
    route_after_safety,
    {
        "act": "act",
        "human_review": "human_review",
        END: END,
    },
)

graph.add_conditional_edges(
    "human_review",
    route_after_human,
    {
        "act": "act",
        "capture": "capture",
        END: END,
    },
)

graph.add_conditional_edges(
    "act",
    after_act,
    {
        "capture": "capture",
        END: END,
    },
)

checkpointer = MemorySaver()
app = graph.compile(checkpointer=checkpointer)


def run_agent(instruction: str):
    initial_state: AgentState = {
        "instruction": instruction,
        "current_image": b"",
        "last_action": {},
        "history": [],
        "step_count": 0,
        "is_done": False,
        "risk_level": "",
        "human_approved": False,
    }

    config = {
        "configurable": {
            "thread_id": str(uuid4()),
        }
    }

    print("\nStarting Desktop AI Agent...")

    payload = initial_state

    while True:
        interrupted = False

        for update in app.stream(
            payload,
            config=config,
            stream_mode="updates",
        ):
            for node_name, changes in update.items():
                if node_name == "__interrupt__":
                    interrupted = True

                    interrupt_info = changes[0].value
                    risky_action = interrupt_info["action"]

                    print("\n" + "=" * 45)
                    print("[HUMAN REVIEW REQUIRED]")
                    print(f"Risk: {interrupt_info['risk_level']}")
                    print(f"Action: {risky_action}")
                    print(f"Target: {risky_action.get('target', '')}")
                    print(f"Text: {risky_action.get('text', '')}")
                    print(f"Reason: {risky_action.get('reason', '')}")
                    print("=" * 45)

                    response = input(
                        "Approve this exact action? (yes/no): "
                    ).strip().lower()

                    payload = Command(resume=response)

                else:
                    print(
                        f"\n[GRAPH] Node: {node_name} | "
                        f"Updated fields: {list(changes.keys())}"
                    )

        if not interrupted:
            break

    print("\nAgent run finished.")


if __name__ == "__main__":
    task = input("What should the AI do? ").strip()

    if task:
        run_agent(task)
    else:
        print("Please enter a task.")
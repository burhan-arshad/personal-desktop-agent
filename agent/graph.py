from typing import TypedDict
from uuid import uuid4
from io import BytesIO
from pathlib import Path
import sys

from PIL import Image
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
from voice.voice import listen

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from perception.perception import capture_grid
from perception.verification import verify_screen_change
from brain.brain import decide_action, classify_skill
from actuator.actuator import execute_action
from safety.safety import classify_risk, log_decision
from memory.memory import (
    init_db,
    start_session,
    end_session,
    log_step,
    log_confirmation,
)
from skills.skills import SKILL_REGISTRY


MAX_STEPS = 4
MAX_UNCHANGED_ATTEMPTS = 1

SCREENSHOT_DIR = PROJECT_ROOT / "memory" / "screenshots"


class AgentState(TypedDict):
    instruction: str
    current_image: bytes
    pre_action_image: bytes
    last_action: dict
    history: list
    step_count: int
    is_done: bool
    risk_level: str
    human_approved: bool
    session_id: int
    current_step_id: int
    skill_name: str
    skill_payload: dict
    execution_mode: str
    skill_error: str
    unchanged_count: int
    verification_feedback: str
    last_verification: dict
    api_error: str


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


def skill_match_node(state: AgentState) -> dict:
    print("\n[SKILL MATCH] Resolving user instruction...")

    skill_name = classify_skill(state["instruction"])

    if not skill_name:
        print("[SKILL MATCH] No skill matched. Using vision loop.")

        return {
            "skill_name": "",
            "skill_payload": {},
            "execution_mode": "vision",
            "skill_error": "",
        }

    skill = SKILL_REGISTRY.get(skill_name)

    if skill is None:
        print("[SKILL MATCH] Unknown skill. Using vision loop.")

        return {
            "skill_name": "",
            "skill_payload": {},
            "execution_mode": "vision",
            "skill_error": "",
        }

    try:
        payload = skill["prepare"](state["instruction"])

        if not isinstance(payload, dict):
            raise TypeError(
                "Skill preparation must return a dictionary."
            )

    except Exception as error:
        message = str(error)
        print(f"[SKILL PREPARATION ERROR] {message}")

        return {
            "skill_name": skill_name,
            "skill_payload": {},
            "execution_mode": "skill",
            "skill_error": message,
            "is_done": True,
            "human_approved": False,
            "last_action": {
                "action": "done",
                "grid_cell": None,
                "text": "",
                "key": "",
                "scroll_direction": "",
                "target": skill_name,
                "risk_level": "safe",
                "reason": f"Skill preparation failed: {message}",
            },
        }

    action = {
        "action": skill_name,
        "skill_name": skill_name,
        "target": skill["description"],
        "text": payload.get(
            "message",
            payload.get("query", ""),
        ),
        "reason": "Prepared skill for the user's instruction.",
        "risk_level": skill["risk_level"],
        "payload": payload,
        "instruction": state["instruction"],
    }

    print(f"[SKILL MATCH] Selected: {skill_name}")

    if skill_name == "send_whatsapp_message":
        print("[SKILL MATCH] WhatsApp message prepared.")
        print(f"Recipient: {payload.get('phone', '')}")
        print(f"Message: {payload.get('message', '')}")
    else:
        print(f"[SKILL MATCH] Prepared payload: {payload}")

    return {
        "skill_name": skill_name,
        "skill_payload": payload,
        "execution_mode": "skill",
        "skill_error": "",
        "last_action": action,
        "history": state["history"] + [
            {
                **action,
                "result": "proposed",
            }
        ],
        "is_done": False,
        "human_approved": False,
    }


def route_after_skill_match(state: AgentState):
    if state["skill_error"] or state["is_done"]:
        return END

    if state["skill_name"]:
        return "safety_check"

    return "capture"


def capture_node(state: AgentState) -> dict:
    print("\n[CAPTURE] Taking a fresh screenshot...")

    grid_image = capture_grid(save_image=True)

    image_buffer = BytesIO()
    grid_image.save(image_buffer, format="PNG")

    print("[CAPTURE] Screenshot captured.")

    return {
        "current_image": image_buffer.getvalue(),
    }


def route_after_capture(state: AgentState):
    if state["pre_action_image"]:
        return "verify"

    return "think"


def think_node(state: AgentState) -> dict:
    print("\n[THINK] Asking the Brain for the next action...")

    instruction = state["instruction"].strip().lower()

    # Simple click tasks should not trigger repeated exploratory clicks.
    is_simple_click_task = (
        instruction.startswith("click ")
        or instruction.startswith("click inside ")
        or instruction.startswith("click on ")
    )

    # If a click was already executed for a simple click task,
    # stop rather than asking the vision model for another click.
    if (
        is_simple_click_task
        and state["step_count"] >= 1
    ):
        message = (
            "A click action has already been executed for this "
            "simple click task. Stopping to avoid repeated clicks. "
            "Visual verification does not establish task completion."
        )

        print(f"\n[STOP] {message}")

        return {
            "last_action": {
                "action": "done",
                "grid_cell": None,
                "text": "",
                "key": "",
                "scroll_direction": "",
                "target": "",
                "risk_level": "safe",
                "reason": message,
            },
            "is_done": True,
            "human_approved": False,
            "verification_feedback": message,
        }

    try:
        current_image = Image.open(
            BytesIO(state["current_image"])
        ).convert("RGB")

        history_summary = summarize_recent(state["history"])

        if state["verification_feedback"]:
            history_summary += (
                "\n\nLatest visual verification feedback: "
                f"{state['verification_feedback']}"
            )

        action = decide_action(
            state["instruction"],
            current_image,
            history_summary,
        )

    except Exception as error:
        error_text = str(error)
        error_lower = error_text.lower()

        is_rate_limit = (
            "429" in error_text
            or "rate limit" in error_lower
            or "too many requests" in error_lower
            or "tokens per minute" in error_lower
            or "requests per minute" in error_lower
        )

        if not is_rate_limit:
            raise

        message = (
            "Groq rate limit reached. Agent stopped without "
            "retrying to conserve API quota."
        )

        print(f"\n[RATE LIMIT] {message}")
        print(f"[RATE LIMIT DETAILS] {error_text[:400]}")

        return {
            "api_error": message,
            "is_done": True,
            "human_approved": False,
            "last_action": {
                "action": "done",
                "grid_cell": None,
                "text": "",
                "key": "",
                "scroll_direction": "",
                "target": "",
                "risk_level": "safe",
                "reason": message,
            },
            "verification_feedback": message,
        }

    print(f"Proposed action: {action}")

    if action.get("action") in {"wait", "done"}:
        reason = action.get(
            "reason",
            "The task is complete or the next action is unclear.",
        )

        print(f"[STOP] {reason}")

        return {
            "last_action": {
                **action,
                "action": "done",
                "grid_cell": None,
            },
            "history": state["history"] + [
                {
                    **action,
                    "result": "stopped_or_completed",
                }
            ],
            "is_done": True,
            "human_approved": False,
            "verification_feedback": "",
        }

    previous = state["last_action"]

    if (
        state["unchanged_count"] > 0
        and previous
        and action.get("action") == previous.get("action")
        and action.get("grid_cell") == previous.get("grid_cell")
        and action.get("target") == previous.get("target")
    ):
        message = (
            "Repeated action rejected locally after unchanged "
            "verification. Stopping to conserve API quota."
        )

        print(f"[STOP] {message}")

        return {
            "last_action": {
                "action": "done",
                "grid_cell": None,
                "text": "",
                "key": "",
                "scroll_direction": "",
                "target": "",
                "risk_level": "safe",
                "reason": message,
            },
            "is_done": True,
            "human_approved": False,
            "verification_feedback": message,
        }

    history_entry = {
        **action,
        "result": "proposed",
    }

    return {
        "last_action": action,
        "history": state["history"] + [history_entry],
        "is_done": False,
        "human_approved": False,
        "verification_feedback": "",
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

    if risk not in {"safe", "risky", "blocked"}:
        raise ValueError(
            f"Invalid risk classification: {risk}"
        )

    conn = init_db()

    try:
        step_id = log_step(
            conn=conn,
            session_id=state["session_id"],
            step_number=state["step_count"] + 1,
            action=action,
            risk_level=risk,
            screenshot_bytes=(
                state["current_image"]
                if (
                    risk in {"risky", "blocked"}
                    and state["current_image"]
                )
                else None
            ),
        )
    finally:
        conn.close()

    if risk == "blocked":
        print("[SAFETY] Blocked action will NOT be executed.")
        log_decision(action, risk, "blocked")

        return {
            "risk_level": risk,
            "current_step_id": step_id,
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
            "current_step_id": step_id,
            "human_approved": True,
            "history": update_latest_history(
                state,
                "classified safe; proceeding",
            ),
        }

    print("[SAFETY] Human approval is required.")

    return {
        "risk_level": risk,
        "current_step_id": step_id,
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

    decision = interrupt(
        {
            "message": "A risky action requires your approval.",
            "action": action,
            "risk_level": state["risk_level"],
            "instruction": state["instruction"],
        }
    )

    approved = str(decision).strip().lower() in {"yes", "y"}
    response = "approved" if approved else "denied"

    log_decision(action, state["risk_level"], response)

    conn = init_db()
    try:
        log_confirmation(
            conn,
            state["current_step_id"],
            "yes" if approved else "no",
        )
    finally:
        conn.close()

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
        "is_done": True,
    }

def route_after_human(state: AgentState):
    if state["human_approved"]:
        return "act"

    return END


def record_action_failure(
    state: AgentState,
    error: Exception,
):
    """Record action execution failure and save its screenshot."""

    screenshot_path = None
    error_details = f"\nExecution failed: {error}"

    if state["current_image"]:
        try:
            SCREENSHOT_DIR.mkdir(
                parents=True,
                exist_ok=True,
            )

            screenshot_file = (
                f"session_{state['session_id']}"
                f"_step_{state['current_step_id']}_failed.png"
            )

            destination = SCREENSHOT_DIR / screenshot_file
            destination.write_bytes(state["current_image"])

            screenshot_path = str(
                destination.relative_to(PROJECT_ROOT)
            )

        except OSError as screenshot_error:
            error_details += (
                "\nFailure screenshot could not be saved: "
                f"{screenshot_error}"
            )

    conn = init_db()

    try:
        conn.execute(
            """
            UPDATE steps
            SET reasoning = COALESCE(reasoning, '') || ?,
                screenshot_path = COALESCE(?, screenshot_path)
            WHERE step_id = ?
            """,
            (
                error_details,
                screenshot_path,
                state["current_step_id"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def act_node(state: AgentState) -> dict:
    action = state["last_action"]
    risk = state["risk_level"]

    if risk == "blocked":
        raise RuntimeError("Blocked action cannot be executed.")

    if risk not in {"safe", "risky"}:
        raise RuntimeError(f"Invalid risk level: {risk}")

    if not state["human_approved"]:
        raise RuntimeError(
            "Action cannot execute without approval."
        )

    print("\n[ACT] Executing the approved or safe action.")
    print(f"Action: {action['action']}")
    print(f"Target: {action.get('target', '')}")

    try:
        if state["execution_mode"] == "skill":
            skill_name = state["skill_name"]
            skill = SKILL_REGISTRY.get(skill_name)

            if skill is None:
                raise RuntimeError(
                    f"Skill is not registered: {skill_name}"
                )

            result = skill["execute"](state["skill_payload"])

            print(f"[SKILL RESULT] {result}")

            return {
                "history": update_latest_history(
                    state,
                    f"skill execution returned: {result}",
                ),
                "step_count": state["step_count"] + 1,
                "is_done": True,
            }

        if not state["current_image"]:
            raise RuntimeError(
                "Vision action requires a screenshot."
            )

        current_image = Image.open(
            BytesIO(state["current_image"])
        ).convert("RGB")

        execute_action(
            action,
            current_image,
            confirm=True,
        )

    except Exception as error:
        record_action_failure(state, error)
        raise

    return {
        "pre_action_image": state["current_image"],
        "history": update_latest_history(
            state,
            "executed; awaiting visual verification",
        ),
        "step_count": state["step_count"] + 1,
    }


def verify_node(state: AgentState) -> dict:
    print("\n[VERIFY] Comparing before and after screenshots...")

    before = state["pre_action_image"]
    after = state["current_image"]

    if not before or not after:
        feedback = (
            "Visual verification unavailable. "
            "The action may have succeeded, but its outcome "
            "cannot be confirmed."
        )

        print(f"[VERIFY] {feedback}")

        return {
            "pre_action_image": b"",
            "verification_feedback": feedback,
            "last_verification": {"status": "unavailable"},
            "history": update_latest_history(
                state,
                "verification unavailable; outcome uncertain",
            ),
        }

    try:
        result = verify_screen_change(before, after)

    except Exception as error:
        feedback = (
            f"Visual verification failed: {error}. "
            "The action outcome is uncertain."
        )

        print(f"[VERIFY] {feedback}")

        return {
            "pre_action_image": b"",
            "verification_feedback": feedback,
            "last_verification": {
                "status": "error",
                "error": str(error),
            },
            "history": update_latest_history(
                state,
                "verification error; outcome uncertain",
            ),
        }

    difference = result["difference"]

    if result["screen_changed"]:
        unchanged_count = 0
        feedback = (
            f"Screen changed (difference={difference}), "
            "but task completion is not confirmed."
        )
        history_result = (
            f"verification: screen changed (difference={difference}); "
            "task success not confirmed"
        )

    else:
        unchanged_count = state["unchanged_count"] + 1
        feedback = (
            f"No significant screen change "
            f"(difference={difference}). "
            "The action may still have succeeded. "
            "Stopping to avoid unnecessary repeated actions."
        )
        history_result = (
            f"verification: screen unchanged "
            f"(difference={difference}); outcome uncertain"
        )

    print(f"[VERIFY] {feedback}")

    return {
        "pre_action_image": b"",
        "unchanged_count": unchanged_count,
        "verification_feedback": feedback,
        "last_verification": result,
        "history": update_latest_history(
            state,
            history_result,
        ),
    }

def route_after_verify(state: AgentState):
    verification = state.get("last_verification", {})
    status = verification.get("status")

    if status in {"unchanged", "error", "unavailable"}:
        print(
            "\n[VERIFY] Outcome could not be confirmed. "
            "Stopping without another Groq call."
        )
        return END

    if state["unchanged_count"] >= MAX_UNCHANGED_ATTEMPTS:
        print(
            "\n[VERIFY] Unchanged screen limit reached. "
            "Stopping without another Groq call."
        )
        return END

    if state["step_count"] >= MAX_STEPS:
        print("\n[ROUTER] Maximum attempt limit reached.")
        return END

    return "think"


def after_act(state: AgentState):
    if state["is_done"]:
        return END

    if state["step_count"] >= MAX_STEPS:
        print("\n[ROUTER] Maximum attempt limit reached.")
        return END

    if state["execution_mode"] == "skill":
        return END

    return "capture"


graph = StateGraph(AgentState)

graph.add_node("skill_match", skill_match_node)
graph.add_node("capture", capture_node)
graph.add_node("think", think_node)
graph.add_node("safety_check", safety_check_node)
graph.add_node("human_review", human_review_node)
graph.add_node("act", act_node)
graph.add_node("verify", verify_node)

graph.add_edge(START, "skill_match")

graph.add_conditional_edges(
    "skill_match",
    route_after_skill_match,
    {
        "safety_check": "safety_check",
        "capture": "capture",
        END: END,
    },
)

graph.add_conditional_edges(
    "capture",
    route_after_capture,
    {
        "think": "think",
        "verify": "verify",
    },
)

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

graph.add_conditional_edges(
    "verify",
    route_after_verify,
    {
        "think": "think",
        END: END,
    },
)

checkpointer = MemorySaver()
app = graph.compile(checkpointer=checkpointer)


def run_agent(instruction: str):
    conn = init_db()
    session_id = None
    final_status = "error"

    try:
        session_id = start_session(conn, instruction)

        initial_state: AgentState = {
            "instruction": instruction,
            "current_image": b"",
            "pre_action_image": b"",
            "last_action": {},
            "history": [],
            "step_count": 0,
            "is_done": False,
            "risk_level": "",
            "human_approved": False,
            "session_id": session_id,
            "current_step_id": 0,
            "skill_name": "",
            "skill_payload": {},
            "execution_mode": "vision",
            "skill_error": "",
            "unchanged_count": 0,
            "verification_feedback": "",
            "last_verification": {},
            "api_error": "",
        }

        config = {
            "configurable": {
                "thread_id": str(uuid4()),
            }
        }

        print("\nStarting Desktop AI Agent...")
        print(f"Session ID: {session_id}")

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
                        print(
                            f"Target: {risky_action.get('target', '')}"
                        )
                        print(
                            f"Text: {risky_action.get('text', '')}"
                        )
                        print(
                            f"Payload: {risky_action.get('payload', {})}"
                        )
                        print(
                            f"Reason: {risky_action.get('reason', '')}"
                        )
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

        final_state = app.get_state(config).values

        verification = final_state.get("last_verification", {})
        verification_status = verification.get("status")

        if final_state.get("api_error"):
            final_status = "error"
            display_status = "api_rate_limited"

        elif final_state.get("skill_error"):
            final_status = "error"
            display_status = "error"

        elif final_state.get("risk_level") == "blocked":
            final_status = "error"
            display_status = "blocked"

        elif (
            verification_status in {
                "unchanged",
                "error",
                "unavailable",
            }
            or verification.get("screen_changed") is False
        ):
            final_status = "error"
            display_status = "verification_failed"

        elif final_state.get("step_count", 0) >= MAX_STEPS:
            final_status = "max_steps_reached"
            display_status = "max_steps_reached"
        elif (
            final_state.get("human_approved") is False
            and final_state.get("history")
            and "user denied this action; not executed"
            in final_state["history"][-1]
        ):
            final_status = "completed"
            display_status = "denied"

        elif final_state.get("is_done"):
            final_status = "completed"
            display_status = "completed"

        else:
            final_status = "error"
            display_status = "error"

        print("\nAgent run finished.")
        print(f"Session status: {display_status}")

        if final_state.get("api_error"):
            print(f"API error: {final_state['api_error']}")

        if final_state.get("skill_error"):
            print(f"Skill error: {final_state['skill_error']}")

        if final_state.get("verification_feedback"):
            print(
                "Verification feedback: "
                f"{final_state['verification_feedback']}"
            )

        if verification:
            print(f"Last verification: {verification}")

    except Exception as error:
        final_status = "error"
        print(f"\n[ERROR] Agent run failed: {error}")
        raise

    finally:
        try:
            if session_id is not None:
                end_session(conn, session_id, final_status)

                print(
                    f"[MEMORY] Session {session_id} "
                    f"saved as '{final_status}'."
                )
        finally:
            conn.close()

if __name__ == "__main__":

    import json

    from conversation.understanding import understand_message
    from conversation.memory import (
        get_active_conversation,
        get_recent_history,
        save_message,
    )

    conversation_id = get_active_conversation()

    print("\n" + "=" * 45)
    print("       PERSONAL DESKTOP AI AGENT")
    print("=" * 45)

    print("\nConversation Mode Started")
    print("You can talk naturally with your AI Agent.")
    print("Type 'exit' to stop.\n")

    while True:

        print("\nSelect Input Mode:")
        print("1. Text Input")
        print("2. Voice Input")

        choice = input("\nEnter your choice (1/2): ").strip()

        user_message = ""

        if choice == "1":

            user_message = input("\nYou: ").strip()

        elif choice == "2":

            print("\n[VOICE MODE] Speak your message.")

            user_message = listen()

            if user_message:
                print(f"\nYou: {user_message}")
            else:
                print("\n[VOICE MODE] No command recognized.")
                continue

        else:

            print("\nInvalid choice. Please select 1 or 2.")
            continue

        if not user_message:
            continue

        if user_message.lower() == "exit":
            print("\nConversation paused.")
            break

        history = get_recent_history(
            conversation_id,
            limit=8
        )

        save_message(
            conversation_id,
            "user",
            user_message
        )

        try:

            result = understand_message(
                user_message=user_message,
                history=history
            )

            save_message(
                conversation_id,
                "assistant",
                json.dumps(result, ensure_ascii=False)
            )

            if result["type"] == "conversation":

                print(f"\nAgent: {result['response']}")

                continue

            elif result["type"] == "clarification":

                print(
                    f"\nAgent: {result['clarification_question']}"
                )

                continue

            elif result["type"] == "action":

                task = result["instruction"]

                print(f"\n[UNDERSTOOD TASK] {task}")

                confirmation = input(
                    "\nShould I perform this action? (yes/no): "
                ).strip().lower()

                if confirmation in ["yes", "y"]:

                    run_agent(task)

                else:

                    print("\nAction cancelled by user.")

        except Exception as error:

            print(f"\n[CONVERSATION ERROR] {error}")
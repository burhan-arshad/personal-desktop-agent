import threading
from uuid import uuid4

from langgraph.types import Command

from agent.graph import app as agent_graph, MAX_STEPS

from memory.memory import (
    init_db,
    start_session,
    end_session,
)

from conversation.memory import save_message


_runs = {}
_registry_lock = threading.RLock()
_execution_lock = threading.Lock()
_active_thread_id = None


def _initial_state(instruction: str, session_id: int) -> dict:
    return {
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
        "is_scheduled": False,
        "scheduled_task_id": 0,
        "scheduled_abort_reason": "",
    }


def _save_conversation_result(run: dict, status: str, result: dict) -> None:
    """
    Save the final agent outcome in the same conversation.
    A conversation-memory failure must not change the agent's execution status.
    """
    conversation_id = run.get("conversation_id")

    if not conversation_id:
        return

    action = result.get("last_action") or {}
    target = action.get("target") or run.get("instruction", "requested task")
    reason = action.get("reason")

    if status == "completed":
        message = f"I completed the desktop task: {target}."
    elif status == "denied":
        message = f"The desktop task was not executed because approval was denied: {target}."
    elif status == "blocked":
        message = f"I blocked the requested desktop task for safety: {target}."
    elif status == "verification_failed":
        message = f"I executed the desktop task, but could not verify its success: {target}."
    elif status == "max_steps_reached":
        message = f"The task stopped because it reached the maximum action limit: {target}."
    elif status == "api_rate_limited":
        message = "The task stopped because the AI provider rate limit was reached."
    else:
        message = f"The desktop task ended with status '{status}': {target}."

    if reason:
        message += f" Details: {reason}"

    try:
        save_message(conversation_id, "assistant", message)
        run["conversation_message_saved"] = True
    except Exception as exc:
        # Do not turn a successful desktop task into a failed task
        # just because conversation history could not be updated.
        run["conversation_message_saved"] = False
        run["conversation_history_error"] = str(exc)


def _close_run_as_error(thread_id: str) -> None:
    """Close a failed run and record its failure in conversation history."""
    global _active_thread_id

    run = _runs[thread_id]

    conn = init_db()
    try:
        end_session(conn, run["session_id"], "error")
    finally:
        conn.close()

    result = {
        "status": "error",
        "step_count": 0,
        "last_action": {},
        "last_verification": {},
        "history": [],
    }

    run.update({
        "status": "error",
        "approval_required": False,
        "result": result,
    })

    _save_conversation_result(run, "error", result)
    _active_thread_id = None


def _finish_run(thread_id: str, state: dict) -> dict:
    global _active_thread_id

    verification = state.get("last_verification") or {}
    history = state.get("history") or []

    denied = (
        not state.get("human_approved", False)
        and any(
            "user denied this action; not executed" in str(item)
            for item in history
        )
    )

    if state.get("api_error"):
        status = "api_rate_limited"
        db_status = "error"

    elif state.get("skill_error"):
        status = "error"
        db_status = "error"

    elif state.get("risk_level") == "blocked":
        status = "blocked"
        db_status = "error"

    elif denied:
        status = "denied"
        db_status = "completed"

    elif verification.get("status") in {
        "error", "unavailable", "unchanged"
    } or verification.get("screen_changed") is False:
        status = "verification_failed"
        db_status = "error"

    elif state.get("step_count", 0) >= MAX_STEPS:
        status = "max_steps_reached"
        db_status = "max_steps_reached"

    elif state.get("is_done"):
        status = "completed"
        db_status = "completed"

    else:
        status = "error"
        db_status = "error"

    run = _runs[thread_id]

    conn = init_db()
    try:
        end_session(conn, run["session_id"], db_status)
    finally:
        conn.close()

    result = {
        "status": status,
        "step_count": state.get("step_count", 0),
        "last_action": state.get("last_action", {}),
        "last_verification": verification,
        "history": history,
    }

    run.update({
        "status": status,
        "approval_required": False,
        "result": result,
    })

    # Save the outcome after the run has reached its final status.
    _save_conversation_result(run, status, result)

    _active_thread_id = None
    return run


def _consume_graph(thread_id: str, payload) -> dict:
    run = _runs[thread_id]
    config = run["config"]
    interrupt_info = None

    for update in agent_graph.stream(
        payload,
        config=config,
        stream_mode="updates",
    ):
        if "__interrupt__" in update:
            changes = update["__interrupt__"]

            if changes:
                interrupt_info = changes[0].value

    if interrupt_info is not None:
        run.update({
            "status": "approval_required",
            "approval_required": True,
            "approval": interrupt_info,
        })

        return {
            "thread_id": thread_id,
            "status": "approval_required",
            "approval_required": True,
            "approval": interrupt_info,
        }

    state = agent_graph.get_state(config).values
    result = _finish_run(thread_id, state)

    return {
        "thread_id": thread_id,
        "status": result["status"],
        "approval_required": False,
        "result": result["result"],
    }


def start_agent(
    instruction: str,
    conversation_id: str | None = None,
) -> dict:
    global _active_thread_id

    instruction = instruction.strip()

    if not instruction:
        raise ValueError("Instruction cannot be empty.")

    with _registry_lock:
        if _active_thread_id is not None:
            raise RuntimeError(
                "Another agent task is active or awaiting approval."
            )

        thread_id = str(uuid4())
        conn = init_db()

        try:
            session_id = start_session(conn, instruction)
        finally:
            conn.close()

        config = {
            "configurable": {
                "thread_id": thread_id,
            }
        }

        _runs[thread_id] = {
            "thread_id": thread_id,
            "session_id": session_id,
            "instruction": instruction,
            "conversation_id": conversation_id,
            "config": config,
            "status": "running",
            "approval_required": False,
            "conversation_message_saved": False,
        }

        _active_thread_id = thread_id

    try:
        with _execution_lock:
            return _consume_graph(
                thread_id,
                _initial_state(instruction, session_id),
            )

    except Exception:
        with _registry_lock:
            run = _runs[thread_id]

            if run["status"] == "running":
                _close_run_as_error(thread_id)

        raise


def respond_to_approval(thread_id: str, approved: bool) -> dict:
    global _active_thread_id

    with _registry_lock:
        run = _runs.get(thread_id)

        if run is None:
            raise ValueError("Agent run not found.")

        if run["status"] != "approval_required":
            raise RuntimeError(
                f"This run is not awaiting approval. "
                f"Current status: {run['status']}"
            )

        run["status"] = "running"
        run["approval_required"] = False

    try:
        with _execution_lock:
            return _consume_graph(
                thread_id,
                Command(resume="yes" if approved else "no"),
            )

    except Exception:
        with _registry_lock:
            run = _runs[thread_id]

            if run["status"] == "running":
                _close_run_as_error(thread_id)

        raise


def get_run(thread_id: str) -> dict:
    run = _runs.get(thread_id)

    if run is None:
        raise ValueError("Agent run not found.")

    return {
        "thread_id": thread_id,
        "instruction": run["instruction"],
        "status": run["status"],
        "approval_required": run["approval_required"],
        "approval": run.get("approval"),
        "result": run.get("result"),
        "conversation_message_saved": run.get(
            "conversation_message_saved",
            False,
        ),
    }

def get_runtime_status() -> dict:
    with _registry_lock:
        active_run = (
            _runs.get(_active_thread_id)
            if _active_thread_id
            else None
        )

        registered_runs = [
            {
                "thread_id": run["thread_id"],
                "instruction": run["instruction"],
                "status": run["status"],
                "approval_required": run.get(
                    "approval_required",
                    False,
                ),
            }
            for run in _runs.values()
        ]

        return {
            "active_thread_id": _active_thread_id,
            "active_run": (
                {
                    "thread_id": active_run["thread_id"],
                    "instruction": active_run["instruction"],
                    "status": active_run["status"],
                    "approval_required": active_run.get(
                        "approval_required",
                        False,
                    ),
                }
                if active_run
                else None
            ),
            "registered_runs": registered_runs,
            "total_runs": len(_runs),
        }
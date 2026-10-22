
import time
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from perception.perception import capture_grid
from brain.brain import decide_action
from actuator.actuator import execute_action


MAX_STEPS = 8


class AgentState(TypedDict):
    instruction: str
    current_image: object
    last_action: dict
    history: list
    step_count: int
    is_done: bool


def summarize_recent(history):
    if not history:
        return "No previous actions."

    recent = history[-3:]
    lines = []

    for index, item in enumerate(recent, start=1):
        lines.append(
            f"Action: {item['action']}, "
            f"cell: {item.get('grid_cell')}, "
            f"reason: {item.get('reason', '')}, "
            f"result: {item.get('result', 'unknown')}"
        )

    return "\n".join(lines)


def capture_node(state: AgentState) -> dict:
    print("\n[CAPTURE] Taking a fresh screenshot...")

    grid_image = capture_grid(save_image=True)

    return {"current_image": grid_image}


def think_node(state: AgentState) -> dict:
    print("\n[THINK] Asking the Brain for the next action...")

    history_summary = summarize_recent(state["history"])

    action = decide_action(
        state["instruction"],
        state["current_image"],
        history_summary,
    )

    print(f"Proposed action: {action}")

    history_entry = {
        **action,
        "result": "proposed",
    }

    return {
        "last_action": action,
        "history": state["history"] + [history_entry],
        "is_done": action["action"] == "done",
    }


def should_continue(state: AgentState):
    if state["is_done"]:
        print("\n[ROUTER] Brain reported task complete.")
        return END

    if state["step_count"] >= MAX_STEPS:
        print("\n[ROUTER] Maximum action limit reached.")
        return END

    return "act"


def act_node(state: AgentState) -> dict:
    action = state["last_action"]
    action_type = action["action"]

    print("\n[ACT] Reviewing the proposed action.")
    print(f"Action: {action_type}")
    print(f"Reason: {action.get('reason', '')}")

    approval = input("Execute this action? (y/n): ").strip().lower()

    if approval != "y":
        print("[ACT] Action rejected. Stopping the agent.")

        history = list(state["history"])
        history[-1] = {
            **history[-1],
            "result": "rejected",
        }

        return {
            "history": history,
            "is_done": True,
        }

    execute_action(
        action,
        state["current_image"],
        confirm=True,
    )

    history = list(state["history"])
    history[-1] = {
        **history[-1],
        "result": "executed; awaiting visual verification",
    }

    return {
        "history": history,
        "step_count": state["step_count"] + 1,
    }


def after_act(state: AgentState):
    if state["is_done"]:
        return END

    if state["step_count"] >= MAX_STEPS:
        print("\n[ROUTER] Maximum action limit reached.")
        return END

    return "capture"


graph = StateGraph(AgentState)

graph.add_node("capture", capture_node)
graph.add_node("think", think_node)
graph.add_node("act", act_node)

graph.add_edge(START, "capture")
graph.add_edge("capture", "think")

graph.add_conditional_edges(
    "think",
    should_continue,
    {
        "act": "act",
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

app = graph.compile()


def run_agent(instruction: str):
    initial_state: AgentState = {
        "instruction": instruction,
        "current_image": None,
        "last_action": {},
        "history": [],
        "step_count": 0,
        "is_done": False,
    }

    print("\nStarting Desktop AI Agent...")

    for update in app.stream(initial_state, stream_mode="updates"):
        for node_name, changes in update.items():
            print(
                f"\n[GRAPH] Node: {node_name} | "
                f"Updated fields: {list(changes.keys())}"
            )

    print("\nAgent run finished.")


if __name__ == "__main__":
    task = input("What should the AI do? ").strip()

    if task:
        run_agent(task)
    else:
        print("Please enter a task.")

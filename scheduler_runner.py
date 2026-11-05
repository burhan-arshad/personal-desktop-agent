import sys
import time
from datetime import datetime
from pathlib import Path

import schedule

from memory.memory import (
    init_db,
    add_scheduled_task,
    get_scheduled_tasks,
    update_scheduled_task_run,
    disable_scheduled_task,
)
from safety.safety import (
    RISKY_KEYWORDS,
    BLOCKED_PATTERNS,
    normalize_text,
)
from agent.graph import run_scheduled_agent


def validate_schedule_time(value: str) -> str:
    value = value.strip()

    if value.startswith("daily@"):
        clock = value.split("@", 1)[1]
        datetime.strptime(clock, "%H:%M")
        return value

    if value.startswith("once@"):
        date_time = value.split("@", 1)[1]
        target = datetime.fromisoformat(date_time)

        if target <= datetime.now():
            raise ValueError("One-time schedule must be in the future.")

        return value

    # Plain HH:MM means daily.
    datetime.strptime(value, "%H:%M")
    return f"daily@{value}"


def scheduling_guard(instruction: str) -> bool:
    normalized = normalize_text(instruction)
    words = set(normalized.split())

    risky_matches = words.intersection(RISKY_KEYWORDS)

    blocked_matches = [
        pattern
        for pattern in BLOCKED_PATTERNS
        if normalize_text(pattern) in normalized
    ]

    if blocked_matches:
        print("\n[GUARD] This instruction contains a blocked operation.")
        print("[GUARD] It cannot be scheduled.")
        return False

    if risky_matches:
        print("\n[GUARD WARNING] Potentially risky instruction detected.")
        print("Matched keywords:", ", ".join(sorted(risky_matches)))
        print(
            "Runtime safety will still abort any RISKY or BLOCKED action."
        )

        response = input(
            "Schedule anyway? (yes/no): "
        ).strip().lower()

        return response in {"yes", "y"}

    return True


def add_task(instruction: str, schedule_time: str):
    if not scheduling_guard(instruction):
        print("[SCHEDULER] Task was not added.")
        return

    schedule_time = validate_schedule_time(schedule_time)

    conn = init_db()

    try:
        task_id = add_scheduled_task(
            conn,
            instruction,
            schedule_time,
        )

        print(f"\n[SCHEDULER] Task added successfully.")
        print(f"Task ID: {task_id}")
        print(f"Instruction: {instruction}")
        print(f"Schedule: {schedule_time}")

    finally:
        conn.close()


def list_tasks():
    conn = init_db()

    try:
        tasks = get_scheduled_tasks(
            conn,
            enabled_only=False,
        )

        if not tasks:
            print("No scheduled tasks found.")
            return

        print("\n========== SCHEDULED TASKS ==========")

        for task in tasks:
            task_id, instruction, schedule_time, enabled, last_run = task

            print(f"\nID: {task_id}")
            print(f"Instruction: {instruction}")
            print(f"Schedule: {schedule_time}")
            print(f"Enabled: {'Yes' if enabled else 'No'}")
            print(f"Last run: {last_run or 'Never'}")

    finally:
        conn.close()


def disable_task(task_id: int):
    conn = init_db()

    try:
        success = disable_scheduled_task(conn, task_id)

        if success:
            print(f"[SCHEDULER] Task {task_id} disabled.")
        else:
            print(f"[SCHEDULER] Task {task_id} not found.")

    finally:
        conn.close()


def execute_task(task):
    task_id, instruction, schedule_time, enabled, last_run = task

    print("\n" + "=" * 45)
    print(f"[SCHEDULER] Executing task {task_id}")
    print("=" * 45)

    try:
        result = run_scheduled_agent(
            instruction=instruction,
            task_id=task_id,
        )

        print(f"[SCHEDULER] Execution result: {result}")

    except Exception as error:
        print(f"[SCHEDULER ERROR] {error}")

    finally:
        conn = init_db()

        try:
            update_scheduled_task_run(conn, task_id)

            if schedule_time.startswith("once@"):
                disable_scheduled_task(conn, task_id)

        finally:
            conn.close()


def run_scheduler():
    conn = init_db()

    try:
        tasks = get_scheduled_tasks(
            conn,
            enabled_only=True,
        )
    finally:
        conn.close()

    if not tasks:
        print("[SCHEDULER] No enabled tasks found.")
        return

    print("\n========== SCHEDULER STARTED ==========")

    for task in tasks:
        task_id, instruction, schedule_time, enabled, last_run = task

        try:
            if schedule_time.startswith("once@"):
                print(
                    f"[SCHEDULER] One-time task loaded: {task_id}"
                )
                continue

            clock = (
                schedule_time.split("@", 1)[1]
                if schedule_time.startswith("daily@")
                else schedule_time
            )

            schedule.every().day.at(clock).do(
                execute_task,
                task,
            )

            print(
                f"[SCHEDULER] Daily task {task_id} "
                f"scheduled at {clock}"
            )

        except ValueError as error:
            print(
                f"[SCHEDULER] Invalid schedule for task "
                f"{task_id}: {error}"
            )

    print("\nScheduler is running. Press CTRL+C to stop.")

    try:
        while True:
            schedule.run_pending()

            # Check one-time tasks.
            conn = init_db()

            try:
                current_tasks = get_scheduled_tasks(
                    conn,
                    enabled_only=True,
                )
            finally:
                conn.close()

            now = datetime.now()

            for task in current_tasks:
                task_id, instruction, schedule_time, enabled, last_run = task

                if not schedule_time.startswith("once@"):
                    continue

                try:
                    target = datetime.fromisoformat(
                        schedule_time.split("@", 1)[1]
                    )
                except ValueError:
                    continue

                if now >= target and not last_run:
                    execute_task(task)

            time.sleep(5)

    except KeyboardInterrupt:
        print("\n[SCHEDULER] Stopped by user.")


def main():
    if len(sys.argv) < 2:
        print(
            """
Commands:

  Add daily task:
  python scheduler_runner.py add "Open Notepad" "daily@09:00"

  Add one-time task:
  python scheduler_runner.py add "Open Notepad" "once@2026-11-05T15:30"

  List tasks:
  python scheduler_runner.py list

  Disable task:
  python scheduler_runner.py disable 1

  Start scheduler:
  python scheduler_runner.py run
"""
        )
        return

    command = sys.argv[1].lower()

    if command == "add":
        if len(sys.argv) != 4:
            print("Usage: add \"instruction\" \"schedule_time\"")
            return

        try:
            add_task(sys.argv[2], sys.argv[3])
        except ValueError as error:
            print(f"[ERROR] {error}")

    elif command == "list":
        list_tasks()

    elif command == "disable":
        if len(sys.argv) != 3:
            print("Usage: disable TASK_ID")
            return

        disable_task(int(sys.argv[2]))

    elif command == "run":
        run_scheduler()

    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
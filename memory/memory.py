
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "agent_memory.db"
SCREENSHOT_DIR = PROJECT_ROOT / "memory" / "screenshots"

SESSION_STATUSES = {
    "running",
    "completed",
    "max_steps_reached",
    "error",
}

def current_timestamp():
    return datetime.now(timezone.utc).isoformat()

def init_db(db_path=None):
    path=Path(db_path) if db_path else DEFAULT_DB_PATH
    if not path.is_absolute():
        path=PROJECT_ROOT/path

    path.parent.mkdir(exist_ok=True, parents=True)

    conn=sqlite3.connect(path,timeout=10)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            instruction TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            status TEXT NOT NULL DEFAULT 'running'
                CHECK (
                    status IN (
                        'running',
                        'completed',
                        'max_steps_reached',
                        'error'
                    )
                )
        );

                CREATE TABLE IF NOT EXISTS steps (
            step_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            step_number INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            action_type TEXT NOT NULL,
            reasoning TEXT,
            risk_level TEXT NOT NULL
                CHECK (
                    risk_level IN ('safe', 'risky', 'blocked')
                ),
            screenshot_path TEXT,
            FOREIGN KEY (session_id)
                REFERENCES sessions(session_id)
                ON DELETE CASCADE,
            UNIQUE (session_id, step_number)
        );

        CREATE TABLE IF NOT EXISTS confirmations (
            confirmation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            step_id INTEGER NOT NULL,
            user_response TEXT NOT NULL
                CHECK (user_response IN ('yes', 'no')),
            timestamp TEXT NOT NULL,
            FOREIGN KEY (step_id)
                REFERENCES steps(step_id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_steps_session
            ON steps(session_id);

        CREATE INDEX IF NOT EXISTS idx_confirmations_step
            ON confirmations(step_id);
    """)

    conn.commit()
    return conn

def start_session(conn, instruction:str)->int:
    cursor = conn.execute(
        """
        INSERT INTO sessions (
            instruction,
            start_time,
            status
        )
        VALUES (?, ?, ?)
        """,
        (instruction, current_timestamp(), "running"),
    )
    conn.commit()
    return cursor.lastrowid

def end_session(conn, session_id: int, status: str):
    if status not in SESSION_STATUSES - {"running"}:
        raise ValueError(f"Invalid final session status: {status}")

    cursor = conn.execute(
        """
        UPDATE sessions
        SET end_time = ?, status = ?
        WHERE session_id = ?
        """,
        (current_timestamp(), status, session_id),
    )

    if cursor.rowcount == 0:
        raise ValueError(f"Session not found: {session_id}")

    conn.commit()

def log_step(
    conn,
    session_id: int,
    step_number: int,
    action: dict,
    risk_level: str,
    screenshot_bytes: bytes = None,
    failed: bool = False,
) -> int:
    if risk_level not in {"safe", "risky", "blocked"}:
        raise ValueError(f"Invalid risk level: {risk_level}")

    screenshot_path = None

    should_save_screenshot = (
        risk_level in {"risky", "blocked"} or failed
    )

    if should_save_screenshot and screenshot_bytes:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

        screenshot_file = (
            f"session_{session_id}_step_{step_number}.png"
        )
        destination = SCREENSHOT_DIR / screenshot_file

        destination.write_bytes(screenshot_bytes)
        screenshot_path = str(destination.relative_to(PROJECT_ROOT))

    cursor = conn.execute(
        """
        INSERT INTO steps (
            session_id,
            step_number,
            timestamp,
            action_type,
            reasoning,
            risk_level,
            screenshot_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            step_number,
            current_timestamp(),
            action.get("action", "unknown"),
            action.get("reason", action.get("reasoning", "")),
            risk_level,
            screenshot_path,
        ),
    )

    conn.commit()
    return cursor.lastrowid

def log_confirmation(conn, step_id: int, user_response: str):
    response = str(user_response).strip().lower()

    if response in {"yes", "y", "approved"}:
        response = "yes"
    elif response in {"no", "n", "denied"}:
        response = "no"
    else:
        raise ValueError("Confirmation must be yes or no.")

    conn.execute(
        """
        INSERT INTO confirmations (
            step_id,
            user_response,
            timestamp
        )
        VALUES (?, ?, ?)
        """,
        (step_id, response, current_timestamp()),
    )

    conn.commit()

def get_most_denied_actions(conn, limit=5):
    if not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer.")

    return conn.execute(
        """
        SELECT
            steps.action_type,
            COUNT(*) AS denial_count
        FROM confirmations
        JOIN steps
            ON confirmations.step_id = steps.step_id
        WHERE confirmations.user_response = 'no'
        GROUP BY steps.action_type
        ORDER BY denial_count DESC, steps.action_type ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def get_session_success_rate(conn):
    return conn.execute(
        """
        SELECT status, COUNT(*) AS session_count
        FROM sessions
        GROUP BY status
        ORDER BY status
        """
    ).fetchall()

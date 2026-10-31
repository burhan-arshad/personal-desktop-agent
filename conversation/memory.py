import sqlite3
import uuid

from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DB_PATH = PROJECT_ROOT / "conversation" / "conversations.db"

VALID_ROLES = {
    "user",
    "assistant",
}


def current_timestamp():

    return datetime.now(timezone.utc).isoformat()


def get_connection():

    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    conn = sqlite3.connect(
        DB_PATH,
        timeout=10
    )

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def init_conversation_db():

    conn = get_connection()

    conn.executescript("""

        CREATE TABLE IF NOT EXISTS conversations (

            conversation_id TEXT PRIMARY KEY,

            created_at TEXT NOT NULL,

            updated_at TEXT NOT NULL,

            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'closed'))

        );


        CREATE TABLE IF NOT EXISTS messages (

            message_id INTEGER PRIMARY KEY AUTOINCREMENT,

            conversation_id TEXT NOT NULL,

            role TEXT NOT NULL
                CHECK (role IN ('user', 'assistant')),

            content TEXT NOT NULL,

            timestamp TEXT NOT NULL,

            FOREIGN KEY (conversation_id)
                REFERENCES conversations(conversation_id)
                ON DELETE CASCADE

        );


        CREATE INDEX IF NOT EXISTS idx_messages_conversation

        ON messages(conversation_id, message_id);

    """)

    conn.commit()
    conn.close()


def start_conversation():

    init_conversation_db()

    conversation_id = str(uuid.uuid4())

    timestamp = current_timestamp()

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO conversations (
            conversation_id,
            created_at,
            updated_at,
            status
        )
        VALUES (?, ?, ?, 'active')
        """,
        (
            conversation_id,
            timestamp,
            timestamp
        )
    )

    conn.commit()
    conn.close()

    return conversation_id


def get_active_conversation():

    init_conversation_db()

    conn = get_connection()

    row = conn.execute(
        """
        SELECT conversation_id
        FROM conversations
        WHERE status = 'active'
        ORDER BY updated_at DESC
        LIMIT 1
        """
    ).fetchone()

    conn.close()

    if row:
        return row["conversation_id"]

    return start_conversation()


def save_message(conversation_id, role, content):

    if role not in VALID_ROLES:

        raise ValueError(
            "Role must be 'user' or 'assistant'."
        )

    if not isinstance(content, str) or not content.strip():

        raise ValueError(
            "Message content cannot be empty."
        )

    timestamp = current_timestamp()

    conn = get_connection()

    conversation = conn.execute(
        """
        SELECT status
        FROM conversations
        WHERE conversation_id = ?
        """,
        (conversation_id,)
    ).fetchone()

    if not conversation:

        conn.close()

        raise ValueError(
            "Conversation does not exist."
        )

    if conversation["status"] != "active":

        conn.close()

        raise ValueError(
            "Cannot add messages to a closed conversation."
        )

    conn.execute(
        """
        INSERT INTO messages (
            conversation_id,
            role,
            content,
            timestamp
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            conversation_id,
            role,
            content.strip(),
            timestamp
        )
    )

    conn.execute(
        """
        UPDATE conversations
        SET updated_at = ?
        WHERE conversation_id = ?
        """,
        (
            timestamp,
            conversation_id
        )
    )

    conn.commit()
    conn.close()


def get_recent_history(conversation_id, limit=8):

    if not isinstance(limit, int) or limit < 1:

        raise ValueError(
            "History limit must be a positive integer."
        )

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT role, content
        FROM messages
        WHERE conversation_id = ?
        ORDER BY message_id DESC
        LIMIT ?
        """,
        (
            conversation_id,
            limit
        )
    ).fetchall()

    conn.close()

    history = [
        {
            "role": row["role"],
            "content": row["content"]
        }
        for row in reversed(rows)
    ]

    return history


def end_conversation(conversation_id):

    conn = get_connection()

    cursor = conn.execute(
        """
        UPDATE conversations
        SET status = 'closed',
            updated_at = ?
        WHERE conversation_id = ?
          AND status = 'active'
        """,
        (
            current_timestamp(),
            conversation_id
        )
    )

    conn.commit()
    conn.close()

    if cursor.rowcount == 0:

        raise ValueError(
            "Active conversation not found."
        )
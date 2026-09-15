import sqlite3
from datetime import datetime

DB_PATH = "chat_history.db"

def init_db():
    """Initialize the SQLite database table for chat history if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            origin TEXT,
            destination TEXT,
            from_date TEXT,
            to_date TEXT,
            duration_days INTEGER,
            calculated_cost_inr REAL,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_chat(user_id: str, origin: str, destination: str, from_date: str, to_date: str, duration_days: int, cost: float):
    """Save a chat turn to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO history_v2 (user_id, origin, destination, from_date, to_date, duration_days, calculated_cost_inr, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, origin, destination, from_date, to_date, duration_days, cost, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_history(user_id: str):
    """Retrieve history records for a given user ID."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM history_v2 WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Run table initialization on import
init_db()
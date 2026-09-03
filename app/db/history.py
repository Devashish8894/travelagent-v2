import sqlite3
from datetime import datetime

DB_PATH = "chat_history.db"

def init_db():
    """Initialize the SQLite database table for chat history if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            user_input TEXT,
            itinerary TEXT,
            estimated_cost REAL,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_chat(user_id: str, prompt: str, itinerary: str, cost: float):
    """Save a chat turn to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO history (user_id, user_input, itinerary, estimated_cost, timestamp) VALUES (?, ?, ?, ?, ?)",
        (user_id, prompt, itinerary, cost, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_history(user_id: str):
    """Retrieve history records for a given user ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_input, itinerary, estimated_cost, timestamp FROM history WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

# Run table initialization on import
init_db()
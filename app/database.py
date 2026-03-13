"""SQLite persistence layer for satellite analysis results."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_DIR = Path("database")
DB_PATH = DB_DIR / "okavango.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS analyses (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT    NOT NULL,
    latitude          REAL    NOT NULL,
    longitude         REAL    NOT NULL,
    zoom              INTEGER NOT NULL,
    image_path        TEXT,
    image_description TEXT,
    image_prompt      TEXT,
    image_model       TEXT,
    text_description  TEXT,
    text_prompt       TEXT,
    text_model        TEXT,
    danger_level      INTEGER,
    danger_label      TEXT,
    danger_reason     TEXT
);
"""


def init_db() -> None:
    """Create the database directory and table if they do not exist."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(_CREATE_TABLE)
        conn.commit()


def insert_analysis(
    latitude: float,
    longitude: float,
    zoom: int,
    image_path: str,
    analysis: dict,
) -> bool:
    """Insert one analysis row. Returns True on success."""
    try:
        init_db()
        timestamp = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO analyses (
                    timestamp, latitude, longitude, zoom, image_path,
                    image_description, image_prompt, image_model,
                    text_description, text_prompt, text_model,
                    danger_level, danger_label, danger_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    latitude,
                    longitude,
                    zoom,
                    image_path,
                    analysis.get("description"),
                    analysis.get("image_prompt"),
                    analysis.get("image_model"),
                    analysis.get("text_description"),
                    analysis.get("text_prompt"),
                    analysis.get("text_model"),
                    analysis.get("danger_level"),
                    analysis.get("danger_label"),
                    analysis.get("danger_reason"),
                ),
            )
            conn.commit()
        return True
    except sqlite3.Error:
        return False


def lookup_analysis(
    latitude: float,
    longitude: float,
    zoom: int,
) -> dict | None:
    """Return the most recent stored result for (latitude, longitude, zoom), or None.
        A stored analysis is reused when latitude/longitude match at 3 decimal
        places and zoom matches exactly."""
    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT *
                FROM analyses
                                WHERE ROUND(latitude, 3) = ROUND(?, 3)
                                    AND ROUND(longitude, 3) = ROUND(?, 3)
                                    AND zoom = ?
                ORDER BY id DESC LIMIT 1
                """,
                                (latitude, longitude, zoom),
            ).fetchone()

    except sqlite3.Error:
        return None

    if row is None:
        return None

    return {
        "image_path": row["image_path"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "zoom": row["zoom"],
        "analysis": {
            "description": row["image_description"],
            "image_prompt": row["image_prompt"],
            "image_model": row["image_model"],
            "text_description": row["text_description"],
            "text_prompt": row["text_prompt"],
            "text_model": row["text_model"],
            "danger_level": row["danger_level"] or 0,
            "danger_label": row["danger_label"] or "Unknown",
            "danger_reason": row["danger_reason"] or "",
        },
    }

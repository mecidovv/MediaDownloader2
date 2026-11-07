from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import database_path

DEFAULT_SETTINGS: dict[str, Any] = {
    "downloadFolder": str(Path.home() / "Videos" / "MediaDownloader"),
    "defaultFormat": "MP4",
    "defaultQuality": "Kaynağın en iyisi",
    "fileNameTemplate": "{title} - {quality}",
    "ledEnabled": True,
    "ledSpeed": 4.5,
    "ledBrightness": 75,
    "ledDensity": 65,
    "reduceMotion": False,
    "accentColor": "#E0142B",
    "recentColors": [],
    "clipboardDetection": True,
    "openFolderAfterDownload": False,
    "saveThumbnail": False,
    "includeSubtitles": False,
    "notificationsEnabled": True,
    "soundEnabled": True,
    "soundVolume": 45,
    "maxDownloads": 2,
    "speedLimit": 0,
    "retryCount": 2,
    "downloadLogs": True,
    "startWithWindows": False,
    "minimizeToTray": False,
    "httpsOnly": True,
    "externalContent": True,
    "language": "tr",
    "schemaVersion": 1,
}


class Storage:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or database_path()
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS settings ("
                "key TEXT PRIMARY KEY, value_json TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS history ("
                "id TEXT PRIMARY KEY, downloaded_at TEXT NOT NULL, "
                "title TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            existing = {
                row["key"] for row in connection.execute("SELECT key FROM settings")
            }
            connection.executemany(
                "INSERT INTO settings (key, value_json) VALUES (?, ?)",
                [
                    (key, json.dumps(value, ensure_ascii=False))
                    for key, value in DEFAULT_SETTINGS.items()
                    if key not in existing
                ],
            )

    def get_settings(self) -> dict[str, Any]:
        with self._lock, self._connection() as connection:
            stored = {
                row["key"]: json.loads(row["value_json"])
                for row in connection.execute("SELECT key, value_json FROM settings")
            }
        return {**DEFAULT_SETTINGS, **stored}

    def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._connection() as connection:
            connection.executemany(
                "INSERT INTO settings (key, value_json) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                [
                    (key, json.dumps(value, ensure_ascii=False))
                    for key, value in settings.items()
                    if key in DEFAULT_SETTINGS
                ],
            )
        return self.get_settings()

    def get_history(self) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM history ORDER BY downloaded_at DESC"
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def add_history(self, item: dict[str, Any]) -> dict[str, Any]:
        record = dict(item)
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO history (id, downloaded_at, title, payload_json) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET downloaded_at = excluded.downloaded_at, "
                "title = excluded.title, payload_json = excluded.payload_json",
                (
                    str(record["id"]),
                    str(record["downloadedAt"]),
                    str(record["title"]),
                    json.dumps(record, ensure_ascii=False),
                ),
            )
        return record

    def clear_history(self) -> None:
        with self._lock, self._connection() as connection:
            connection.execute("DELETE FROM history")

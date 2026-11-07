from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "MediaDownloader"


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "frontend"
    return Path(__file__).resolve().parents[1]


def data_directory() -> Path:
    override = os.environ.get("MEDIADOWNLOADER_DATA_DIR")
    if override:
        location = Path(override).expanduser()
    elif os.name == "nt":
        location = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
    else:
        location = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME
    location.mkdir(parents=True, exist_ok=True)
    return location


def database_path() -> Path:
    return data_directory() / "app.sqlite3"


def downloads_directory() -> Path:
    location = Path.home() / "Videos" / APP_NAME
    location.mkdir(parents=True, exist_ok=True)
    return location

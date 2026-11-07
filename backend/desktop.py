from __future__ import annotations

import asyncio
import logging
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import uvicorn
import webview

from .api import create_app
from .config import downloads_directory, project_root

LOGGER = logging.getLogger("media_downloader")


class DesktopBridge:
    """Small allow-listed bridge for folder actions (the window uses the native Windows frame)."""

    def __init__(self) -> None:
        self.window: Any = None

    def open_download_folder(self, path: str | None = None) -> str:
        folder = Path(path).expanduser() if path else downloads_directory()
        folder.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(folder))
        else:
            import webbrowser

            webbrowser.open(folder.as_uri())
        return str(folder)

    def choose_folder(self) -> str | None:
        window = self._require_window()
        selection = window.create_file_dialog(
            webview.FileDialog.FOLDER,
            directory=str(downloads_directory()),
        )
        return str(selection[0]) if selection else None

    def _require_window(self) -> Any:
        if self.window is None:
            raise RuntimeError("The desktop window has not been initialized.")
        return self.window


def _find_listener() -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    return listener


def _wait_until_ready(url: str, server: uvicorn.Server, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.started:
            try:
                with urllib.request.urlopen(url, timeout=0.5) as response:
                    if response.status == 200:
                        return
            except (OSError, urllib.error.URLError):
                pass
        if server.should_exit:
            break
        time.sleep(0.05)
    raise RuntimeError("The local API did not become ready in time.")


def run() -> None:
    frontend = project_root()
    if not (frontend / "index.html").is_file():
        raise FileNotFoundError(f"Frontend not found: {frontend}")

    listener = _find_listener()
    port = listener.getsockname()[1]
    app = create_app(frontend=frontend)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)

    def serve() -> None:
        asyncio.run(server.serve(sockets=[listener]))

    server_thread = threading.Thread(target=serve, name="MediaDownloaderAPI", daemon=True)
    server_thread.start()
    url = f"http://127.0.0.1:{port}/"

    try:
        _wait_until_ready(f"{url}api/v1/health", server)
        bridge = DesktopBridge()
        bridge.window = webview.create_window(
            "Video Downloader",
            url,
            js_api=bridge,
            width=1280,
            height=800,
            min_size=(760, 600),
            resizable=True,
            text_select=True,
        )
        webview.start(debug=False, private_mode=False)
    finally:
        server.should_exit = True
        server_thread.join(timeout=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()

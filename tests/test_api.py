from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import uvicorn

from backend.api import create_app
from backend.storage import Storage


class LocalApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(__file__).resolve().parents[1]
        cls.storage = Storage(Path(cls.temporary_directory.name) / "test.sqlite3")
        cls.app = create_app(storage=cls.storage, frontend=root)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        cls.port = listener.getsockname()[1]
        cls.server = uvicorn.Server(
            uvicorn.Config(cls.app, log_level="critical", access_log=False)
        )

        def serve() -> None:
            import asyncio

            asyncio.run(cls.server.serve(sockets=[listener]))

        cls.thread = threading.Thread(target=serve, daemon=True)
        cls.thread.start()
        deadline = time.monotonic() + 10
        while not cls.server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        if not cls.server.started:
            raise RuntimeError("The test API server did not start.")
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.should_exit = True
        cls.thread.join(timeout=10)
        if cls.thread.is_alive():
            cls.server.force_exit = True
            cls.thread.join(timeout=5)
        if cls.thread.is_alive():
            raise RuntimeError("The test API server did not stop.")
        cls.temporary_directory.cleanup()

    def request(self, path: str, method: str = "GET", data: dict | None = None):
        body = json.dumps(data).encode("utf-8") if data is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as error:
            try:
                return error.code, error.read().decode("utf-8")
            finally:
                error.close()
        with response:
            content = response.read().decode("utf-8")
            return response.status, content

    def test_health_and_frontend_are_served(self) -> None:
        status_code, body = self.request("/api/v1/health")
        self.assertEqual(status_code, 200)
        self.assertEqual(json.loads(body)["status"], "ok")

        status_code, body = self.request("/")
        self.assertEqual(status_code, 200)
        self.assertIn("Video Downloader", body)

    def test_settings_are_persistent(self) -> None:
        status_code, _ = self.request(
            "/api/v1/settings",
            "PUT",
            {"settings": {"accentColor": "#3366FF", "maxDownloads": 4}},
        )
        self.assertEqual(status_code, 200)
        settings = self.storage.get_settings()
        self.assertEqual(settings["accentColor"], "#3366FF")
        self.assertEqual(settings["maxDownloads"], 4)
        self.storage.save_settings({"externalContent": True})
        settings = self.storage.save_settings({"httpsOnly": False})
        self.assertTrue(settings["externalContent"])
        self.assertFalse(settings["httpsOnly"])

    def test_history_can_be_saved_loaded_and_cleared(self) -> None:
        status_code, body = self.request(
            "/api/v1/history",
            "POST",
            {
                "id": "test-item",
                "downloadedAt": "2026-11-06T00:00:00Z",
                "title": "Authorized sample",
                "format": "MP4",
            },
        )
        self.assertEqual(status_code, 201)
        self.assertEqual(json.loads(body)["id"], "test-item")
        self.assertEqual(len(self.storage.get_history()), 1)

        status_code, _ = self.request("/api/v1/history", "DELETE")
        self.assertEqual(status_code, 204)
        self.assertEqual(self.storage.get_history(), [])

    def test_video_metadata_requires_external_content_permission(self) -> None:
        self.storage.save_settings({"externalContent": False})
        status_code, body = self.request(
            "/api/v1/videos/info",
            "POST",
            {"url": "https://example.com/video"},
        )
        self.assertEqual(status_code, 403)
        self.assertIn("Harici içerik yükleme", body)

    def test_downloads_are_queued_and_progress_can_be_read(self) -> None:
        self.storage.save_settings({"externalContent": True})
        with (
            patch.object(
                self.app.state.downloads,
                "start_download",
                return_value={"id": "test-download", "status": "queued", "progress": 0},
            ),
            patch.object(
                self.app.state.downloads,
                "get_download",
                return_value={"id": "test-download", "status": "downloading", "progress": 42.5},
            ),
        ):
            status_code, body = self.request(
                "/api/v1/downloads",
                "POST",
                {
                    "url": "https://example.com/video",
                    "format": "MP4",
                    "quality": "720p",
                },
            )
            progress_code, progress_body = self.request("/api/v1/downloads/test-download")
        self.assertEqual(status_code, 202)
        self.assertEqual(json.loads(body)["status"], "queued")
        self.assertEqual(progress_code, 200)
        self.assertEqual(json.loads(progress_body)["progress"], 42.5)

    def test_download_url_validation_rejects_non_https_by_default(self) -> None:
        self.storage.save_settings({"externalContent": True, "httpsOnly": True})
        status_code, body = self.request(
            "/api/v1/videos/info",
            "POST",
            {"url": "http://example.com/video"},
        )
        self.assertEqual(status_code, 422)
        self.assertIn("HTTPS", body)


if __name__ == "__main__":
    unittest.main()

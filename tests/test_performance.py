from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

import uvicorn

from backend.api import create_app
from backend.storage import Storage

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])


class PerformanceRegressionTests(unittest.TestCase):
    def test_app_creation_defers_ytdlp_in_isolation(self) -> None:
        """Backend kurulumu islemciyi yormadan ve yt-dlp yuklemeden bitmeli."""
        code = (
            "import sys, time; "
            "sys.path.insert(0, %r); "
            "from backend.api import create_app; "
            "t0 = time.monotonic(); app = create_app(); t1 = time.monotonic(); "
            "print(('yt_dlp' in sys.modules), (t1 - t0))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code % PROJECT_ROOT],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=PROJECT_ROOT,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        in_modules, elapsed = completed.stdout.strip().split()
        self.assertEqual(in_modules, "False", "yt_dlp backend yuklenirken yuklenmemeli")
        self.assertLess(float(elapsed), 2.0, "Backend kurulumu cok yavas: %s sn" % elapsed)

    def test_importing_api_module_does_not_build_default_app(self) -> None:
        """Import etmek ikinci bir Storage/DownloadManager olusturmamali."""
        code = (
            "import sys; sys.path.insert(0, %r); "
            "import backend.api as api; "
            "print('app' in vars(api), api._default_app is None)"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code % PROJECT_ROOT],
            capture_output=True, text=True, timeout=120, cwd=PROJECT_ROOT,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "False True")

    def test_bootstrap_endpoint_responds_quickly(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        try:
            storage = Storage(Path(temporary_directory.name) / "perf.sqlite3")
            app = create_app(storage=storage)
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            port = listener.getsockname()[1]
            server = uvicorn.Server(
                uvicorn.Config(app, log_level="critical", access_log=False)
            )

            def serve() -> None:
                import asyncio

                asyncio.run(server.serve(sockets=[listener]))

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            deadline = time.monotonic() + 10
            while not server.started and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(server.started, "Test sunucusu baslatilamadi")
            try:
                base_url = "http://127.0.0.1:%d/" % port
                started = time.monotonic()
                with urllib.request.urlopen(base_url + "api/v1/bootstrap", timeout=5) as response:
                    status = response.status
                    body = response.read().decode("utf-8")
                elapsed = time.monotonic() - started
            finally:
                server.should_exit = True
                thread.join(timeout=10)
        finally:
            temporary_directory.cleanup()
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertIn("settings", payload)
        self.assertIn("history", payload)
        self.assertLess(elapsed, 2.0, "Bootstrap istek cok yavas: %.3fs" % elapsed)


if __name__ == "__main__":
    unittest.main()

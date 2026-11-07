from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from backend.downloads import DownloadManager
from backend.storage import Storage


class ProbeStorage(Storage):
    """Records whether the manager lock is held while a download worker reads settings."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.manager: DownloadManager | None = None
        self.worker_reads = 0
        self.lock_was_held: list[bool] = []

    def get_settings(self):
        manager = self.manager
        if manager is not None and threading.current_thread().name.startswith("MediaDownload"):
            self.worker_reads += 1
            outcome: list[bool] = []

            def try_lock() -> None:
                acquired = manager._lock.acquire(timeout=0.5)
                outcome.append(acquired)
                if acquired:
                    manager._lock.release()

            helper = threading.Thread(target=try_lock)
            helper.start()
            helper.join()
            self.lock_was_held.append(not outcome[0])
        return super().get_settings()


class DownloadLockingTests(unittest.TestCase):
    def test_worker_does_not_hold_poll_lock_while_reading_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = ProbeStorage(Path(directory) / "app.sqlite3")
            storage.save_settings({"externalContent": True, "maxDownloads": 1})
            manager = DownloadManager(storage)
            storage.manager = manager
            try:
                done = threading.Event()

                def fake_download(job_id: str) -> None:
                    with manager._lock:
                        manager._jobs[job_id]["status"] = "completed"
                    done.set()

                with mock.patch.object(DownloadManager, "_download", side_effect=fake_download):
                    task = manager.start_download(
                        url="https://example.com/video",
                        format_name="MP4",
                        quality="720p",
                        folder=str(Path(directory) / "out"),
                        save_thumbnail=False,
                        subtitles=False,
                    )
                    self.assertTrue(done.wait(5), "Download worker did not run")
                    self.assertEqual(manager.get_download(task["id"])["status"], "completed")
            finally:
                manager.close()
        self.assertGreater(storage.worker_reads, 0)
        self.assertFalse(any(storage.lock_was_held), "SQLite okuması kilit tutulurken yapıldı")

    def test_queued_job_can_be_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory) / "app.sqlite3")
            storage.save_settings({"externalContent": True, "maxDownloads": 1})
            manager = DownloadManager(storage)
            release = threading.Event()
            try:
                def slow_download(job_id: str) -> None:
                    release.wait(5)
                    with manager._lock:
                        manager._jobs[job_id]["status"] = "completed"

                with mock.patch.object(DownloadManager, "_download", side_effect=slow_download):
                    kwargs = dict(
                        url="https://example.com/video", format_name="MP4", quality="720p",
                        folder=str(Path(directory) / "out"), save_thumbnail=False, subtitles=False,
                    )
                    first = manager.start_download(**kwargs)
                    second = manager.start_download(**kwargs)
                    manager.cancel_download(second["id"])
                    release.set()
                    deadline = threading.Event()
                    for _ in range(50):
                        states = (manager.get_download(first["id"])["status"],
                                  manager.get_download(second["id"])["status"])
                        if states == ("completed", "cancelled"):
                            break
                        deadline.wait(0.1)
                    self.assertEqual(states, ("completed", "cancelled"))
            finally:
                release.set()
                manager.close()


if __name__ == "__main__":
    unittest.main()

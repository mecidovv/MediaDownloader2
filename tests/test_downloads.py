from __future__ import annotations

import functools
import subprocess
import threading
import time
import tempfile
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import sleep
from unittest.mock import patch

import imageio_ffmpeg

from backend.downloads import DownloadManager, _safe_info, validate_video_url
from backend.storage import Storage


class DownloadEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temporary_directory.name) / "settings.sqlite3")
        self.storage.save_settings(
            {
                "externalContent": True,
                "downloadFolder": self.temporary_directory.name,
            }
        )
        self.manager = DownloadManager(self.storage)

    def tearDown(self) -> None:
        self.manager.close()
        self.temporary_directory.cleanup()

    def test_video_details_only_expose_real_source_qualities(self) -> None:
        details = _safe_info(
            {
                "id": "sample-id",
                "title": "Sample video",
                "extractor_key": "Test",
                "duration": 96,
                "formats": [
                    {"height": 720, "vcodec": "h264", "acodec": "none"},
                    {"height": 720, "vcodec": "h264", "acodec": "aac"},
                    {"height": 480, "vcodec": "h264", "acodec": "none"},
                    {"height": 1080, "vcodec": "none", "acodec": "aac"},
                ],
            }
        )
        self.assertEqual(details["qualities"], ["720p", "480p"])
        self.assertEqual(details["durationLabel"], "01:36")
        self.assertTrue(details["hasVideo"])
        self.assertTrue(details["hasAudio"])

    def test_video_details_report_audio_only_sources(self) -> None:
        details = _safe_info(
            {
                "title": "Audio sample",
                "formats": [{"vcodec": "none", "acodec": "opus"}],
            }
        )
        self.assertEqual(details["qualities"], [])
        self.assertFalse(details["hasVideo"])
        self.assertTrue(details["hasAudio"])

    def test_metadata_uses_ytdlp_and_returns_actual_source_metadata(self) -> None:
        source = {
            "id": "source-id",
            "title": "Source title",
            "webpage_url": "https://example.com/watch/1",
            "extractor_key": "Example",
            "formats": [{"height": 360, "vcodec": "h264", "acodec": "aac"}],
        }
        with patch("yt_dlp.YoutubeDL") as youtube_dl:
            youtube_dl.return_value.__enter__.return_value.extract_info.return_value = source
            result = self.manager.get_video_info("https://example.com/watch/1")
        self.assertEqual(result["title"], "Source title")
        self.assertEqual(result["qualities"], ["360p"])
        youtube_dl.return_value.__enter__.return_value.extract_info.assert_called_once_with(
            "https://example.com/watch/1", download=False
        )

    def test_https_policy_and_local_links_are_enforced(self) -> None:
        with self.assertRaises(ValueError):
            validate_video_url("http://example.com/video")
        with self.assertRaises(ValueError):
            validate_video_url("https://localhost/video", https_only=False)
        self.assertEqual(
            validate_video_url("http://example.com/video", https_only=False),
            "http://example.com/video",
        )

    def test_quality_selection_never_exceeds_requested_height(self) -> None:
        selector = self.manager._format_selector("MP4", "720p")
        self.assertIn("height<=720", selector)
        self.assertEqual(self.manager._format_selector("MP3", "audio"), "bestaudio/best")

    def test_temporary_file_cleanup_only_removes_downloader_artifacts(self) -> None:
        folder = Path(self.temporary_directory.name) / "cleanup"
        folder.mkdir()
        partial = folder / "clip.mp4.part"
        unrelated = folder / "notes.txt"
        partial.write_bytes(b"partial")
        unrelated.write_text("keep", encoding="utf-8")
        self.assertEqual(self.manager.cleanup_temporary_files(str(folder)), 1)
        self.assertFalse(partial.exists())
        self.assertTrue(unrelated.exists())

    def test_download_request_rejects_quality_not_in_the_expected_shape(self) -> None:
        with self.assertRaises(ValueError):
            self.manager.start_download(
                url="https://example.com/video",
                format_name="MP4",
                quality="8K",
                folder=self.temporary_directory.name,
                save_thumbnail=False,
                subtitles=False,
            )
        self.assertEqual(self.manager.list_downloads(), [])

    def test_mp3_download_is_converted_saved_and_added_to_history(self) -> None:
        source_folder = Path(self.temporary_directory.name) / "source"
        output_folder = Path(self.temporary_directory.name) / "output"
        source_folder.mkdir()
        output_folder.mkdir()
        source_path = source_folder / "tone.wav"
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=880:duration=10",
                "-c:a",
                "pcm_s16le",
                str(source_path),
            ],
            check=True,
        )

        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, _format: str, *args: object) -> None:
                pass

            def copyfile(self, source, outputfile) -> None:
                try:
                    while True:
                        chunk = source.read(16384)
                        if not chunk:
                            break
                        outputfile.write(chunk)
                        outputfile.flush()
                        sleep(0.01)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    return

        handler = functools.partial(QuietHandler, directory=str(source_folder))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        self.storage.save_settings({"httpsOnly": False})
        try:
            saw_transfer_progress = False
            job = self.manager.start_download(
                url=f"http://127.0.0.1:{server.server_port}/tone.wav",
                format_name="MP3",
                quality="audio",
                folder=str(output_folder),
                save_thumbnail=False,
                subtitles=False,
            )
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                job = self.manager.get_download(job["id"])
                if job["status"] == "downloading" and job["progress"] > 0:
                    saw_transfer_progress = True
                if job["status"] in {"completed", "failed", "cancelled"}:
                    break
                time.sleep(0.05)
            self.assertEqual(job["status"], "completed", job)
            self.assertTrue(saw_transfer_progress, "The downloader did not report measured transfer progress.")
            downloaded_file = Path(job["filepath"])
            self.assertEqual(downloaded_file.suffix.lower(), ".mp3")
            self.assertGreater(downloaded_file.stat().st_size, 1000)
            self.assertEqual(len(self.storage.get_history()), 1)
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()

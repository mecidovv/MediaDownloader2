from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from .config import downloads_directory
from .storage import Storage

LOGGER = logging.getLogger("media_downloader")
MAX_CONCURRENT_DOWNLOADS = 5


def validate_video_url(url: str, *, https_only: bool = True) -> str:
    parsed = urlsplit(url.strip())
    allowed_schemes = {"https"} if https_only else {"http", "https"}
    if parsed.scheme.lower() not in allowed_schemes:
        expected = "HTTPS" if https_only else "HTTP veya HTTPS"
        raise ValueError(f"Güvenlik ayarınıza göre {expected} video bağlantısı kullanın.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Kullanıcı adı veya parola içermeyen geçerli bir video bağlantısı girin.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("Yerel ağ bağlantıları desteklenmiyor.")
    return parsed.geturl()


def _duration_label(duration: Any) -> str | None:
    if duration is None:
        return None
    seconds = max(0, int(duration))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def _available_heights(info: dict[str, Any]) -> list[int]:
    heights = {
        int(item["height"])
        for item in info.get("formats", [])
        if item.get("height")
        and item.get("vcodec") not in (None, "none")
        and str(item.get("height")).isdigit()
    }
    if info.get("height") and info.get("vcodec") not in (None, "none"):
        heights.add(int(info["height"]))
    return sorted(heights, reverse=True)


def _has_audio(info: dict[str, Any]) -> bool:
    return any(item.get("acodec") not in (None, "none") for item in info.get("formats", [])) or (
        info.get("acodec") not in (None, "none")
    )


def _safe_info(info: dict[str, Any]) -> dict[str, Any]:
    heights = _available_heights(info)
    extractor = str(info.get("extractor_key") or info.get("extractor") or "Web")
    return {
        "id": str(info.get("id") or ""),
        "url": str(info.get("webpage_url") or info.get("original_url") or ""),
        "title": str(info.get("title") or "Video"),
        "description": str(info.get("description") or "")[:1000],
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "durationLabel": _duration_label(info.get("duration")),
        "channel": str(info.get("channel") or info.get("uploader") or ""),
        "platform": extractor.removesuffix("IE").replace("_", " "),
        "extractor": extractor,
        "qualities": [f"{height}p" for height in heights],
        "hasVideo": bool(heights),
        "hasAudio": _has_audio(info),
    }


class DownloadManager:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self._executor = ThreadPoolExecutor(
            max_workers=MAX_CONCURRENT_DOWNLOADS,
            thread_name_prefix="MediaDownload",
        )
        self._lock = threading.RLock()
        self._capacity = threading.Condition(self._lock)
        self._jobs: dict[str, dict[str, Any]] = {}
        self._futures: dict[str, Future[None]] = {}
        self._active_downloads = 0

    def close(self) -> None:
        with self._capacity:
            for job in self._jobs.values():
                if job["status"] not in {"completed", "failed", "cancelled"}:
                    job["cancelRequested"] = True
            self._capacity.notify_all()
        self._executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _external_content_enabled(storage: Storage) -> bool:
        return bool(storage.get_settings().get("externalContent"))

    def _ytdlp_options(self, *, download: bool = False) -> dict[str, Any]:
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 20,
            "retries": 2,
            "extractor_retries": 1,
        }
        if not download:
            options["skip_download"] = True
        try:
            import imageio_ffmpeg

            ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
            if ffmpeg.is_file():
                options["ffmpeg_location"] = str(ffmpeg)
        except (ImportError, RuntimeError, OSError):
            LOGGER.warning("Bundled FFmpeg is unavailable.", exc_info=True)
        return options

    def get_video_info(self, url: str) -> dict[str, Any]:
        settings = self.storage.get_settings()
        if not self._external_content_enabled(self.storage):
            raise PermissionError("Video bilgilerini almak için Gelişmiş ayarlarda “Harici içerik yükleme” iznini açın.")
        safe_url = validate_video_url(url, https_only=bool(settings.get("httpsOnly", True)))
        options = self._ytdlp_options()
        options["logger"] = _QuietYtDlpLogger()
        import yt_dlp

        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(safe_url, download=False)
        if not info or not isinstance(info, dict):
            raise ValueError("Video sağlayıcısı bilgi döndürmedi.")
        if info.get("_type") == "playlist" and info.get("entries"):
            info = next((entry for entry in info["entries"] if entry), None)
            if not info:
                raise ValueError("Bu bağlantıda video bulunamadı.")
        return _safe_info(info)

    def start_download(
        self,
        *,
        url: str,
        format_name: str,
        quality: str,
        folder: str | None,
        save_thumbnail: bool,
        subtitles: bool,
    ) -> dict[str, Any]:
        settings = self.storage.get_settings()
        if not self._external_content_enabled(self.storage):
            raise PermissionError("İndirme için Gelişmiş ayarlarda “Harici içerik yükleme” iznini açın.")
        safe_url = validate_video_url(url, https_only=bool(settings.get("httpsOnly", True)))
        normalized_format = format_name.upper()
        if normalized_format not in {"MP4", "MP3"}:
            raise ValueError("MP4 veya MP3 çıktı biçimini seçin.")
        if normalized_format == "MP4" and not re.fullmatch(r"\d{1,5}p|best", quality, re.IGNORECASE):
            raise ValueError("Kaynağın sunduğu video kalitelerinden birini seçin.")
        if normalized_format == "MP3" and quality not in {"audio", "best"}:
            raise ValueError("Geçersiz ses kalitesi seçimi.")
        destination = Path(folder).expanduser() if folder else Path(settings["downloadFolder"])
        destination.mkdir(parents=True, exist_ok=True)
        if not destination.is_dir():
            raise ValueError("Seçilen indirme konumu bir klasör değil.")

        job_id = str(uuid4())
        job = {
            "id": job_id,
            "url": safe_url,
            "format": normalized_format,
            "quality": quality,
            "folder": str(destination.resolve()),
            "saveThumbnail": bool(save_thumbnail),
            "subtitles": bool(subtitles),
            "status": "queued",
            "progress": 0.0,
            "speed": None,
            "eta": None,
            "filepath": None,
            "error": None,
            "title": None,
            "platform": None,
            "duration": None,
            "thumbnail": None,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "cancelRequested": False,
        }
        with self._lock:
            self._jobs[job_id] = job
            self._futures[job_id] = self._executor.submit(self._run_download, job_id)
        return self._public_job(job)

    def get_download(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError("Download task not found.")
            return self._public_job(job)

    def list_downloads(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._public_job(job) for job in self._jobs.values()]

    def cleanup_temporary_files(self, folder: str | None = None) -> int:
        settings = self.storage.get_settings()
        directory = Path(folder).expanduser() if folder else Path(settings["downloadFolder"])
        if not directory.exists():
            return 0
        directory = directory.resolve()
        with self._lock:
            if any(
                Path(job["folder"]).resolve() == directory
                and job["status"] in {"queued", "downloading", "processing"}
                for job in self._jobs.values()
            ):
                raise RuntimeError("İndirme sürerken bu klasörün geçici dosyaları temizlenemez.")
        temporary_files = {
            path
            for pattern in ("*.part", "*.ytdl", "*.partial.*")
            for path in directory.glob(pattern)
            if path.is_file()
        }
        removed = 0
        for path in temporary_files:
            path.unlink()
            removed += 1
        return removed

    def cancel_download(self, job_id: str) -> dict[str, Any]:
        with self._capacity:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError("Download task not found.")
            if job["status"] in {"completed", "failed", "cancelled"}:
                return self._public_job(job)
            job["cancelRequested"] = True
            if job["status"] == "queued":
                future = self._futures.get(job_id)
                if future and future.cancel():
                    job["status"] = "cancelled"
                    job["error"] = "Download cancelled."
            self._capacity.notify_all()
            return self._public_job(job)

    def _max_downloads(self) -> int:
        return max(1, min(MAX_CONCURRENT_DOWNLOADS, int(self.storage.get_settings().get("maxDownloads", 2))))

    def _run_download(self, job_id: str) -> None:
        job = self._jobs[job_id]
        while True:
            # SQLite is read outside the lock so status polls are never blocked by disk I/O.
            maximum = self._max_downloads()
            with self._capacity:
                if job["cancelRequested"]:
                    job["status"] = "cancelled"
                    job["error"] = "Download cancelled."
                    self._capacity.notify_all()
                    return
                if self._active_downloads < maximum:
                    self._active_downloads += 1
                    job["status"] = "downloading"
                    break
                self._capacity.wait(timeout=0.25)

        try:
            self._download(job_id)
        except _DownloadCancelled:
            with self._lock:
                self._jobs[job_id]["status"] = "cancelled"
                self._jobs[job_id]["error"] = "Download cancelled."
        except Exception as error:
            LOGGER.warning("Download %s failed: %s", job_id, error, exc_info=True)
            with self._lock:
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = _friendly_error(error)
        finally:
            with self._capacity:
                self._active_downloads = max(0, self._active_downloads - 1)
                self._capacity.notify_all()

    def _download(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            snapshot = dict(job)
        settings = self.storage.get_settings()
        filename_template = str(settings.get("fileNameTemplate") or "{title} - {quality}")
        template_values = {
            "title": "%(title)s",
            "platform": "%(extractor_key)s",
            "date": "%(upload_date)s",
            "quality": snapshot["quality"],
        }
        filename_template = re.sub(
            r"\{(title|platform|date|quality)\}",
            lambda match: template_values[match.group(1)],
            filename_template,
        )
        options = self._ytdlp_options(download=True)
        options.update(
            {
                "format": self._format_selector(snapshot["format"], snapshot["quality"]),
                "outtmpl": str(Path(snapshot["folder"]) / f"{filename_template}.%(ext)s"),
                "progress_hooks": [lambda data: self._progress_hook(job_id, data)],
                "postprocessor_hooks": [lambda data: self._postprocessor_hook(job_id, data)],
                "retries": max(0, min(10, int(settings.get("retryCount", 2)))),
                "fragment_retries": max(0, min(10, int(settings.get("retryCount", 2)))),
                "ratelimit": max(0, int(settings.get("speedLimit", 0))) * 1024 or None,
                "writethumbnail": snapshot["format"] == "MP4" and snapshot["saveThumbnail"],
                "writesubtitles": snapshot["format"] == "MP4" and snapshot["subtitles"],
                "writeautomaticsub": snapshot["format"] == "MP4" and snapshot["subtitles"],
            }
        )
        if snapshot["format"] == "MP4":
            options["merge_output_format"] = "mp4"
        else:
            if not options.get("ffmpeg_location"):
                raise RuntimeError("MP3 dönüştürmek için FFmpeg gerekli ancak kullanılamıyor.")
            options["format"] = "bestaudio/best"
        options["logger"] = _QuietYtDlpLogger()
        import yt_dlp

        with yt_dlp.YoutubeDL(options) as downloader:
            result = downloader.extract_info(snapshot["url"], download=True)
            filepath = self._result_path(downloader, result, snapshot["format"])
        if not filepath or not Path(filepath).is_file():
            raise RuntimeError("İndirme tamamlandı ancak medya dosyası kaydedilmedi.")
        if snapshot["format"] == "MP3":
            filepath = self._convert_media(job_id, filepath, "mp3", audio_only=True)
        else:
            filepath = self._convert_media(job_id, filepath, "mp4", audio_only=False)

        with self._lock:
            current = self._jobs[job_id]
            if current["cancelRequested"]:
                try:
                    Path(filepath).unlink(missing_ok=True)
                except OSError:
                    LOGGER.warning("Could not remove cancelled download %s.", filepath, exc_info=True)
                raise _DownloadCancelled()
            current.update(
                {
                    "status": "completed",
                    "progress": 100.0,
                    "filepath": str(Path(filepath).resolve()),
                    "title": str(result.get("title") or Path(filepath).stem),
                    "platform": str(result.get("extractor_key") or result.get("extractor") or "Web"),
                    "duration": _duration_label(result.get("duration")),
                    "thumbnail": result.get("thumbnail"),
                    "speed": None,
                    "eta": None,
                }
            )
            completed = dict(current)
        self.storage.add_history(
            {
                "id": completed["id"],
                "downloadedAt": datetime.now(timezone.utc).isoformat(),
                "title": completed["title"],
                "platform": completed["platform"],
                "format": completed["format"],
                "quality": completed["quality"],
                "duration": completed["duration"],
                "thumbnail": completed["thumbnail"],
                "url": completed["url"],
                "filepath": completed["filepath"],
                "folder": str(Path(completed["filepath"]).parent),
            }
        )

    def _convert_media(self, job_id: str, source: str, output_format: str, *, audio_only: bool) -> str:
        ffmpeg = self._ytdlp_options().get("ffmpeg_location")
        if not ffmpeg:
            if audio_only:
                raise RuntimeError("MP3 dönüştürmek için FFmpeg gerekli ancak kullanılamıyor.")
            return source
        source_path = Path(source)
        target_path = source_path.with_suffix(f".{output_format}")
        temporary_path = target_path.with_name(f"{target_path.stem}.partial.{output_format}")
        args = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-i", str(source_path)]
        if audio_only:
            args.extend(["-map", "0:a:0", "-vn", "-codec:a", "libmp3lame", "-b:a", "192k"])
        else:
            args.extend(["-map", "0", "-c", "copy", "-movflags", "+faststart", "-f", "mp4"])
        args.append(str(temporary_path))
        with self._lock:
            self._jobs[job_id]["status"] = "processing"
        process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            while True:
                try:
                    _, stderr = process.communicate(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    with self._lock:
                        cancelled = self._jobs[job_id]["cancelRequested"]
                    if cancelled:
                        process.terminate()
                        try:
                            process.communicate(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.communicate()
                        raise _DownloadCancelled()
            if process.returncode:
                message = (stderr or "").strip().splitlines()
                detail = message[-1] if message else "FFmpeg bu medyayı dönüştüremedi."
                raise RuntimeError(detail[:400])
            if not temporary_path.is_file() or temporary_path.stat().st_size == 0:
                raise RuntimeError("FFmpeg istenen medya dosyasını oluşturmadı.")
            temporary_path.replace(target_path)
            if source_path.resolve() != target_path.resolve():
                source_path.unlink(missing_ok=True)
            return str(target_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _format_selector(format_name: str, quality: str) -> str:
        if format_name == "MP3":
            return "bestaudio/best"
        match = re.fullmatch(r"(\d{1,5})p", quality, re.IGNORECASE)
        if not match:
            return "bestvideo+bestaudio/best"
        height = int(match.group(1))
        return (
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"best[height<={height}][ext=mp4]/best[height<={height}]"
        )

    def _progress_hook(self, job_id: str, data: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job["cancelRequested"]:
                raise _DownloadCancelled()
            status_name = data.get("status")
            if status_name == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                downloaded = data.get("downloaded_bytes") or 0
                progress = min(99.9, downloaded * 100 / total) if total else job["progress"]
                job.update(
                    {
                        "status": "downloading",
                        "progress": round(progress, 1),
                        "speed": data.get("speed"),
                        "eta": data.get("eta"),
                        "filepath": data.get("filename") or job["filepath"],
                    }
                )
            elif status_name == "finished":
                job.update({"status": "processing", "progress": max(job["progress"], 99.0)})

    def _postprocessor_hook(self, job_id: str, data: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job["cancelRequested"]:
                raise _DownloadCancelled()
            info = data.get("info_dict") or {}
            filepath = info.get("filepath") or info.get("_filename")
            if filepath:
                job["filepath"] = filepath
            job["status"] = "processing"

    @staticmethod
    def _result_path(downloader: Any, result: dict[str, Any], format_name: str) -> str | None:
        candidates: list[str] = []
        if isinstance(result, dict):
            if result.get("filepath"):
                candidates.append(str(result["filepath"]))
            for item in result.get("requested_downloads") or []:
                if item.get("filepath"):
                    candidates.append(str(item["filepath"]))
            if result.get("_filename"):
                candidates.append(str(result["_filename"]))
            try:
                candidates.append(downloader.prepare_filename(result))
            except (KeyError, TypeError, ValueError):
                pass
        for candidate in candidates:
            path = Path(candidate)
            if path.is_file() and path.suffix.lower() == f".{format_name.lower()}":
                return str(path)
        return next((candidate for candidate in candidates if Path(candidate).is_file()), None)

    @staticmethod
    def _public_job(job: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in job.items() if key not in {"cancelRequested"}}


class _DownloadCancelled(Exception):
    pass


class _QuietYtDlpLogger:
    def debug(self, message: str) -> None:
        if message.startswith("[debug]"):
            return
        LOGGER.debug("%s", message)

    def warning(self, message: str) -> None:
        LOGGER.warning("%s", message)

    def error(self, message: str) -> None:
        LOGGER.error("%s", message)


def _friendly_error(error: Exception) -> str:
    text = str(error).strip()
    if "unable to obtain file audio codec" in text.lower() or "does not contain any stream" in text.lower():
        return "Bu kaynakta MP3 olarak kaydedilebilecek bir ses parçası yok."
    if "ffmpeg" in text.lower():
        return "Bu biçimi birleştirmek veya dönüştürmek için FFmpeg gerekli. Uyumlu bir kalite seçin."
    if "private" in text.lower() or "members-only" in text.lower() or "login" in text.lower():
        return "Bu video oturum açma veya izin gerektiriyor; anonim olarak erişilemiyor."
    if "unsupported url" in text.lower():
        return "Bu bağlantı yt-dlp tarafından desteklenmiyor."
    return f"İşlem başarısız: {text[:450]}" if text else "İndirme başarısız oldu. Bağlantıyı kontrol edip yeniden deneyin."

from __future__ import annotations

import json
import logging
import re
import time
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .clipboard import read_text
from .config import project_root
from .downloads import DownloadManager
from .storage import Storage

LOGGER = logging.getLogger("media_downloader")
APP_VERSION = "1.0.0"


def _ytdlp_version() -> str:
    try:
        from yt_dlp.version import __version__

        return str(__version__)
    except Exception:
        return ""


def _ffmpeg_version() -> str:
    try:
        import imageio_ffmpeg

        return str(imageio_ffmpeg.get_ffmpeg_version())
    except Exception:
        return ""


def _version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value))


class SettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    settings: dict[str, Any]


class HistoryPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: str(uuid4()))
    downloadedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    title: str = Field(min_length=1, max_length=1000)


class VideoInfoPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=4096)


class DownloadPayload(VideoInfoPayload):
    format: str = Field(pattern=r"(?i)^(mp4|mp3)$")
    quality: str = Field(min_length=1, max_length=16)
    folder: str | None = Field(default=None, max_length=4096)
    saveThumbnail: bool = False
    subtitles: bool = False


class CleanupPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder: str | None = Field(default=None, max_length=4096)


def create_app(storage: Storage | None = None, frontend: Path | None = None) -> FastAPI:
    database = storage or Storage()
    downloads = DownloadManager(database)
    static_root = frontend or project_root()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if not (static_root / "index.html").is_file():
            raise RuntimeError(f"Frontend index.html not found: {static_root}")
        try:
            yield
        finally:
            downloads.close()

    app = FastAPI(title="MediaDownloader Local API", version="1.0.0", lifespan=lifespan)
    app.state.storage = database
    app.state.downloads = downloads

    @app.middleware("http")
    async def restrict_to_local_clients(request: Request, call_next):
        client = request.client
        if client is None or client.host not in {"127.0.0.1", "::1", "localhost"}:
            return JSONResponse(
                status_code=403,
                content={"detail": "Local application access only."},
            )
        return await call_next(request)

    @app.middleware("http")
    async def log_slow_requests(request: Request, call_next):
        started = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - started
        if duration > 1.0:
            LOGGER.warning(
                "Yavaş istek: %s %s %.3fs",
                request.method,
                request.url.path,
                duration,
            )
        return response

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/api/v1/bootstrap")
    def bootstrap() -> dict[str, Any]:
        return {"settings": database.get_settings(), "history": database.get_history()}

    @app.get("/api/v1/settings")
    def get_settings() -> dict[str, Any]:
        return database.get_settings()

    @app.put("/api/v1/settings")
    def save_settings(payload: SettingsPayload) -> dict[str, Any]:
        unknown = set(payload.settings) - set(database.get_settings())
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Unknown setting keys: {', '.join(sorted(unknown))}",
            )
        return database.save_settings(payload.settings)

    @app.get("/api/v1/history")
    def get_history() -> list[dict[str, Any]]:
        return database.get_history()

    @app.post("/api/v1/history", status_code=status.HTTP_201_CREATED)
    def add_history(payload: HistoryPayload) -> dict[str, Any]:
        record = payload.model_dump(mode="json")
        return database.add_history(record)

    @app.delete("/api/v1/history", status_code=status.HTTP_204_NO_CONTENT)
    def clear_history() -> None:
        database.clear_history()

    @app.get("/api/v1/downloads")
    def get_downloads() -> list[dict[str, Any]]:
        return downloads.list_downloads()

    @app.post("/api/v1/videos/info")
    def get_video_info(payload: VideoInfoPayload) -> dict[str, Any]:
        try:
            return downloads.get_video_info(payload.url)
        except PermissionError as error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Video bilgileri alınamadı: {str(error)[:400]}",
            ) from error

    @app.post("/api/v1/downloads", status_code=status.HTTP_202_ACCEPTED)
    def start_download(payload: DownloadPayload) -> dict[str, Any]:
        try:
            return downloads.start_download(
                url=payload.url,
                format_name=payload.format,
                quality=payload.quality,
                folder=payload.folder,
                save_thumbnail=payload.saveThumbnail,
                subtitles=payload.subtitles,
            )
        except PermissionError as error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    @app.get("/api/v1/downloads/{download_id}")
    def get_download(download_id: str) -> dict[str, Any]:
        try:
            return downloads.get_download(download_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    @app.delete("/api/v1/downloads/{download_id}")
    def cancel_download(download_id: str) -> dict[str, Any]:
        try:
            return downloads.cancel_download(download_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    @app.post("/api/v1/downloads/cleanup")
    def cleanup_temporary_files(payload: CleanupPayload) -> dict[str, int]:
        try:
            return {"removed": downloads.cleanup_temporary_files(payload.folder)}
        except RuntimeError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    @app.get("/api/v1/clipboard")
    def clipboard() -> dict[str, str]:
        return {"text": read_text()}

    @app.get("/api/v1/about")
    def about() -> dict[str, str]:
        return {"version": APP_VERSION, "ytDlp": _ytdlp_version(), "ffmpeg": _ffmpeg_version()}

    @app.get("/api/v1/about/updates")
    def check_updates() -> dict[str, Any]:
        current = _ytdlp_version()
        try:
            request = urllib.request.Request(
                "https://pypi.org/pypi/yt-dlp/json", headers={"User-Agent": "MediaDownloader"}
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                latest = str(json.load(response)["info"]["version"])
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="Update check failed."
            ) from error
        up_to_date = bool(current) and _version_key(current) >= _version_key(latest)
        return {"current": current, "latest": latest, "upToDate": up_to_date}

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_root / "index.html")

    for asset_directory in ("css", "js", "assets"):
        asset_path = static_root / asset_directory
        if asset_path.is_dir():
            app.mount(
                f"/{asset_directory}",
                StaticFiles(directory=asset_path),
                name=asset_directory,
            )
    return app


_default_app: FastAPI | None = None


def __getattr__(name: str) -> Any:
    # `backend.api:app` stays available for `uvicorn backend.api:app`, but the app
    # (SQLite + thread pool) is only built on first access, not on every import.
    global _default_app
    if name == "app":
        if _default_app is None:
            _default_app = create_app()
        return _default_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

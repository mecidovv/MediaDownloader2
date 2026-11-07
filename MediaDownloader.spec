# PyInstaller uses this spec to package the frontend and dynamically-loaded
# PyWebView backends with the local API, so the built app needs no source tree.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH)
data_files = [
    (str(root / "index.html"), "frontend"),
    (str(root / "css"), "frontend/css"),
    (str(root / "js"), "frontend/js"),
    (str(root / "assets"), "frontend/assets"),
]
webview_datas, webview_binaries, webview_hiddenimports = collect_all("webview")
yt_dlp_datas, yt_dlp_binaries, yt_dlp_hiddenimports = collect_all("yt_dlp")
ffmpeg_datas, ffmpeg_binaries, ffmpeg_hiddenimports = collect_all("imageio_ffmpeg")

a = Analysis(
    [str(root / "run_desktop.py")],
    pathex=[str(root)],
    binaries=webview_binaries + yt_dlp_binaries + ffmpeg_binaries,
    datas=data_files + webview_datas + yt_dlp_datas + ffmpeg_datas,
    hiddenimports=(
        webview_hiddenimports
        + yt_dlp_hiddenimports
        + ffmpeg_hiddenimports
        + ["uvicorn.logging", "uvicorn.loops.auto"]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MediaDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(root / "assets" / "icons" / "app.ico"),
)
bundle = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MediaDownloader",
)

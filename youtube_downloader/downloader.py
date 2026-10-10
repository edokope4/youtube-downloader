"""Descarga de videos de YouTube mediante yt-dlp."""

from __future__ import annotations

import re
import shutil
import threading
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from youtube_downloader.version import project_dir, resource_dir

ProgressCallback = Callable[[float | None, str], None]
LogCallback = Callable[[str], None]

_YOUTUBE_HOSTS = {
    "youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
    "youtu.be",
}
_FINAL_EXTENSIONS = {".mp3": 0, ".m4a": 1, ".mp4": 2, ".mkv": 3, ".webm": 4}
_INTERMEDIATE_FILE = re.compile(r"\.f\d+$")


class DownloaderError(Exception):
    """Error que se puede mostrar en la interfaz."""


class UserCancelled(DownloaderError):
    """El usuario cancelo la descarga."""


@dataclass(frozen=True)
class QualityOption:
    label: str
    height: int | None


@dataclass(frozen=True)
class VideoInfo:
    video_id: str
    title: str
    duration: int | None
    qualities: list[QualityOption]


def default_download_dir() -> Path:
    downloads = Path.home() / "Downloads"
    if downloads.is_dir():
        return downloads
    return Path.home()


def validate_youtube_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        raise DownloaderError("Ingresa el enlace de un video de YouTube.")
    try:
        parsed = urllib.parse.urlparse(cleaned)
    except ValueError as exc:
        raise DownloaderError("El enlace no es válido.") from exc
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if parsed.scheme not in {"http", "https"} or host not in _YOUTUBE_HOSTS:
        raise DownloaderError("El enlace tiene que ser de YouTube (youtube.com o youtu.be).")
    return cleaned


def resolve_ffmpeg_dir() -> Path | None:
    candidates: list[Path] = []
    app_dir = project_dir()
    candidates.append(app_dir)
    candidates.append(app_dir / "ffmpeg")
    candidates.append(resource_dir() / "vendor" / "ffmpeg")
    candidates.append(project_dir() / "vendor" / "ffmpeg")
    for folder in candidates:
        if (folder / "ffmpeg.exe").is_file() or (folder / "ffmpeg").is_file():
            return folder
    found = shutil.which("ffmpeg")
    if found:
        return Path(found).resolve().parent
    return None


def ffmpeg_executable() -> Path | None:
    folder = resolve_ffmpeg_dir()
    if folder is None:
        return None
    for name in ("ffmpeg.exe", "ffmpeg"):
        candidate = folder / name
        if candidate.is_file():
            return candidate
    return None


def fetch_video_info(url: str, on_log: LogCallback | None = None) -> VideoInfo:
    cleaned = validate_youtube_url(url)
    yt_dlp, yt_download_error = _load_yt_dlp()
    options = _base_options(on_log)
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(cleaned, download=False)
    except yt_download_error as exc:
        raise DownloaderError(_clean_yt_error(exc)) from exc
    if not info:
        raise DownloaderError("No se pudo leer la información del video.")
    if info.get("_type") == "playlist":
        entries = [entry for entry in info.get("entries") or [] if entry]
        if len(entries) != 1:
            raise DownloaderError("El enlace corresponde a una lista. Pega el enlace de un solo video.")
        info = entries[0]
    return VideoInfo(
        video_id=str(info.get("id") or ""),
        title=str(info.get("title") or "Video sin título"),
        duration=_as_int(info.get("duration")),
        qualities=_qualities_from_info(info),
    )


def download_video(
    url: str,
    destination: Path,
    *,
    audio_only: bool,
    height: int | None,
    on_progress: ProgressCallback | None = None,
    on_log: LogCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    cleaned = validate_youtube_url(url)
    target = _prepare_destination(destination)
    ffmpeg_dir = resolve_ffmpeg_dir()
    if ffmpeg_dir is None:
        raise DownloaderError(
            "No se encontró FFmpeg. Hace falta para unir imagen y audio, y para guardar MP3. "
            "Ejecuta build.bat para generar el programa con FFmpeg incluido, "
            "o instala FFmpeg y agregalo al PATH."
        )

    state: dict[str, str | None] = {"final": None}

    def progress_hook(data: dict) -> None:
        _raise_if_cancelled(cancel_event)
        fraction, text = _progress_text(data)
        if data.get("status") == "finished" and data.get("filename"):
            state["final"] = data["filename"]
        _report(on_progress, fraction, text)

    def postprocessor_hook(data: dict) -> None:
        _raise_if_cancelled(cancel_event)
        status = data.get("status")
        info_dict = data.get("info_dict") or {}
        filepath = info_dict.get("filepath")
        if filepath:
            state["final"] = filepath
        if status == "started":
            _report(on_progress, None, "Convirtiendo el archivo...")
        elif status == "finished":
            _report(on_progress, 1.0, "Procesamiento terminado.")

    yt_dlp, yt_download_error = _load_yt_dlp()
    options = _base_options(on_log)
    options.update(
        {
            "ffmpeg_location": str(ffmpeg_dir),
            "outtmpl": "%(title)s [%(id)s].%(ext)s",
            "paths": {"home": str(target)},
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
            "retries": 10,
            "fragment_retries": 10,
            "concurrent_fragment_downloads": 4,
            "windowsfilenames": True,
            "continuedl": True,
        }
    )
    if audio_only:
        options["format"] = "bestaudio/best"
        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        options["merge_output_format"] = "mp4"
        if height is None:
            options["format"] = "bestvideo+bestaudio/best"
        else:
            options["format"] = (
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}]/best"
            )

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(cleaned, download=True)
    except UserCancelled:
        raise
    except yt_download_error as exc:
        if cancel_event is not None and cancel_event.is_set():
            raise UserCancelled("Descarga cancelada.") from exc
        raise DownloaderError(_clean_yt_error(exc)) from exc
    except Exception as exc:
        if cancel_event is not None and cancel_event.is_set():
            raise UserCancelled("Descarga cancelada.") from exc
        raise

    if not info:
        raise DownloaderError("La descarga terminó sin información del archivo.")
    return _resolve_output_file(target, info, state["final"])


def format_duration(seconds: int | None) -> str:
    if not seconds:
        return ""
    remaining = int(seconds)
    hours, remaining = divmod(remaining, 3600)
    minutes, secs = divmod(remaining, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _load_yt_dlp():
    try:
        import yt_dlp
        from yt_dlp.utils import DownloadError
    except ImportError as exc:
        raise DownloaderError(
            "Falta la dependencia yt-dlp. Instálala con: pip install -r requirements.txt"
        ) from exc
    return yt_dlp, DownloadError


def _base_options(on_log: LogCallback | None) -> dict:
    return {
        "quiet": True,
        "no_warnings": False,
        "noplaylist": True,
        "noprogress": True,
        "no_color": True,
        "logger": _CallbackLogger(on_log),
        "socket_timeout": 30,
    }


def _prepare_destination(destination: Path) -> Path:
    if not str(destination).strip():
        raise DownloaderError("Selecciona la carpeta de destino.")
    try:
        target = destination.expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DownloaderError(f"No se pudo usar la carpeta de destino: {exc}") from exc
    if not target.is_dir():
        raise DownloaderError("La ruta de destino no es una carpeta.")
    return target


def _qualities_from_info(info: dict) -> list[QualityOption]:
    duration = info.get("duration")
    best_by_height: dict[int, tuple[float, float | None, float]] = {}
    for fmt in info.get("formats") or []:
        vcodec = fmt.get("vcodec")
        if vcodec in (None, "none", "images"):
            continue
        if fmt.get("format_note") == "storyboard" or fmt.get("ext") == "mhtml":
            continue
        height = _as_int(fmt.get("height"))
        if not height:
            continue
        tbr = float(fmt.get("tbr") or 0)
        fps = float(fmt.get("fps") or 0)
        previous = best_by_height.get(height)
        if previous is not None and tbr <= previous[0]:
            continue
        has_audio = fmt.get("acodec") not in (None, "none")
        size = None
        if tbr and duration:
            audio_extra = 0 if has_audio else 128
            size = (tbr + audio_extra) * 1000 / 8 * float(duration)
        best_by_height[height] = (tbr, size, fps)

    options = [QualityOption("Mejor disponible", None)]
    for height in sorted(best_by_height, reverse=True):
        _tbr, size, fps = best_by_height[height]
        name = f"{height}p{int(round(fps))}" if fps >= 50 else f"{height}p"
        label = f"{name} · ~{_format_size(size)}" if size else name
        options.append(QualityOption(label, height))
    return options


def _resolve_output_file(destination: Path, info: dict, fallback: str | None) -> Path:
    candidates: list[Path] = []
    if fallback:
        candidates.append(Path(fallback))
    for item in info.get("requested_downloads") or []:
        filepath = item.get("filepath") or item.get("filename")
        if filepath:
            candidates.append(Path(filepath))
    prepared = info.get("filepath") or info.get("filename")
    if prepared:
        candidates.append(Path(prepared))
    video_id = info.get("id")
    if video_id:
        candidates.extend(destination.glob(f"*[{video_id}].*"))
        candidates.extend(destination.glob(f"*[{video_id}]*"))

    existing = [path for path in candidates if path.is_file() and not _is_intermediate(path)]
    if not existing:
        raise DownloaderError("La descarga terminó, pero no se encontró el archivo en la carpeta de destino.")
    existing.sort(key=lambda path: (_FINAL_EXTENSIONS.get(path.suffix.lower(), 9), -path.stat().st_mtime))
    return existing[0]


def _is_intermediate(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith((".part", ".ytdl", ".temp")) or ".part" in name:
        return True
    return _INTERMEDIATE_FILE.search(path.stem) is not None


def _progress_text(data: dict) -> tuple[float | None, str]:
    status = data.get("status")
    if status == "finished":
        return 1.0, "Procesando el archivo..."
    if status != "downloading":
        return None, "Descargando..."

    downloaded = float(data.get("downloaded_bytes") or 0)
    total = data.get("total_bytes") or data.get("total_bytes_estimate")
    fraction = None
    parts = ["Descargando"]
    if total:
        fraction = max(0.0, min(1.0, downloaded / float(total)))
        parts.append(f"{fraction * 100:.1f}%")
    speed = data.get("speed")
    if speed:
        parts.append(_format_speed(float(speed)))
    eta = data.get("eta")
    if isinstance(eta, (int, float)) and eta >= 0:
        parts.append(f"queda {_format_eta(int(eta))}")
    return fraction, " · ".join(parts)


def _format_speed(speed: float) -> str:
    if speed >= 1024 * 1024:
        return f"{speed / (1024 * 1024):.1f} MB/s"
    if speed >= 1024:
        return f"{speed / 1024:.0f} KB/s"
    return f"{speed:.0f} B/s"


def _format_eta(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_size(num_bytes: float) -> str:
    gib = 1024**3
    mib = 1024**2
    if num_bytes >= gib:
        return f"{num_bytes / gib:.1f} GB"
    if num_bytes >= 10 * mib:
        return f"{num_bytes / mib:.0f} MB"
    return f"{num_bytes / mib:.1f} MB"


def _raise_if_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise UserCancelled("Descarga cancelada.")


def _report(callback: ProgressCallback | None, fraction: float | None, text: str) -> None:
    if callback is not None:
        callback(fraction, text)


def _clean_yt_error(exc: Exception) -> str:
    message = str(exc).strip() or "Error desconocido de la descarga."
    message = re.sub(r"^ERROR:\s*", "", message)
    return message


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


class _CallbackLogger:
    def __init__(self, callback: LogCallback | None) -> None:
        self._callback = callback

    def debug(self, msg: str) -> None:
        return None

    def info(self, msg: str) -> None:
        return None

    def warning(self, msg: str) -> None:
        self._emit(msg)

    def error(self, msg: str) -> None:
        self._emit(msg)

    def _emit(self, msg: str) -> None:
        text = str(msg).strip()
        if self._callback is not None and text and not text.startswith("[debug]"):
            self._callback(text)

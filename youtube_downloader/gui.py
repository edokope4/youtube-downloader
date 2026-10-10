"""Interfaz grafica del descargador."""

from __future__ import annotations

import ctypes
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from youtube_downloader.downloader import (
    DownloaderError,
    QualityOption,
    UserCancelled,
    VideoInfo,
    default_download_dir,
    download_video,
    fetch_video_info,
    ffmpeg_executable,
    format_duration,
    validate_youtube_url,
)
from youtube_downloader.version import get_version

_BG = "#f3f4f6"
_CARD = "#ffffff"
_INK = "#111827"
_MUTED = "#6b7280"
_ACCENT = "#c4302b"
_ACCENT_ACTIVE = "#a52824"
_CANCEL = "#374151"
_HELP = """Uso:
  python main.py              Abre la interfaz
  python main.py --version    Muestra la versión del proyecto
  python main.py --check      Muestra la versión y si FFmpeg está disponible
"""


def main() -> None:
    _prepare_frozen_stdio()
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command in {"-h", "--help"}:
            print(_HELP)
            return
        if command in {"-v", "--version"}:
            print(get_version())
            return
        if command == "--check":
            _print_check()
            return
        print(_HELP, file=sys.stderr)
        raise SystemExit(2)

    _enable_windows_dpi()
    try:
        app = App()
    except tk.TclError as exc:
        print(f"No se pudo abrir la interfaz grafica: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    app.mainloop()


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self._version = get_version()
        self.title(f"YouTube Downloader {self._version}")
        self.configure(bg=_BG)
        self.minsize(640, 560)
        self._center(680, 620)

        self._messages: queue.Queue[tuple] = queue.Queue()
        self._cancel = threading.Event()
        self._busy = False
        self._qualities: dict[str, QualityOption] = {}
        self._last_file: Path | None = None

        self.url_var = tk.StringVar()
        self.dest_var = tk.StringVar(value=str(default_download_dir()))
        self.quality_var = tk.StringVar()
        self.audio_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Pega un enlace de YouTube para empezar.")
        self.video_var = tk.StringVar()

        self._build_styles()
        self._build_layout()
        self._set_qualities([QualityOption("Mejor disponible", None)])
        self.url_var.trace_add("write", self._on_url_changed)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_messages)
        self._log(self._ffmpeg_status_text())

    def _center(self, width: int, height: int) -> None:
        self.update_idletasks()
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("TButton", font=("Segoe UI", 10))

    def _label(self, parent: tk.Widget, text: str, muted: bool = False) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            bg=_CARD,
            fg=_MUTED if muted else _INK,
            font=("Segoe UI", 10),
            anchor="w",
        )

    def _build_layout(self) -> None:
        header = tk.Frame(self, bg="#1f1f1f")
        header.pack(fill="x")
        tk.Label(
            header,
            text="YouTube Downloader",
            bg="#1f1f1f",
            fg="white",
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left", padx=16, pady=14)
        tk.Label(
            header,
            text=f"v{self._version}",
            bg="#1f1f1f",
            fg="#d1d5db",
            font=("Segoe UI", 10),
        ).pack(side="right", padx=16)

        body = tk.Frame(self, bg=_BG)
        body.pack(fill="both", expand=True, padx=16, pady=16)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        card = tk.Frame(body, bg=_CARD, highlightthickness=1, highlightbackground="#e5e7eb")
        card.grid(row=0, column=0, sticky="ew")
        card.columnconfigure(0, weight=1)

        self._label(card, "Enlace del video").grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 0))
        url_row = tk.Frame(card, bg=_CARD)
        url_row.grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 8))
        url_row.columnconfigure(0, weight=1)
        self.url_entry = ttk.Entry(url_row, textvariable=self.url_var, font=("Segoe UI", 11))
        self.url_entry.grid(row=0, column=0, sticky="ew")
        self.url_entry.bind("<Return>", lambda _event: self._on_load_qualities())
        self.load_btn = ttk.Button(url_row, text="Cargar calidades", command=self._on_load_qualities)
        self.load_btn.grid(row=0, column=1, padx=(8, 0))

        self.video_label = tk.Label(
            card,
            textvariable=self.video_var,
            bg=_CARD,
            fg=_MUTED,
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.video_label.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))

        self._label(card, "Calidad").grid(row=3, column=0, sticky="ew", padx=16)
        self.quality_combo = ttk.Combobox(
            card,
            textvariable=self.quality_var,
            state="readonly",
            font=("Segoe UI", 10),
        )
        self.quality_combo.grid(row=4, column=0, sticky="ew", padx=16, pady=(4, 8))

        self.audio_check = tk.Checkbutton(
            card,
            text="Descargar solo el audio (MP3)",
            variable=self.audio_var,
            command=self._refresh_quality_state,
            bg=_CARD,
            fg=_INK,
            activebackground=_CARD,
            activeforeground=_INK,
            selectcolor=_CARD,
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.audio_check.grid(row=5, column=0, sticky="w", padx=12, pady=(0, 10))

        self._label(card, "Carpeta de destino").grid(row=6, column=0, sticky="ew", padx=16)
        dest_row = tk.Frame(card, bg=_CARD)
        dest_row.grid(row=7, column=0, sticky="ew", padx=16, pady=(4, 10))
        dest_row.columnconfigure(0, weight=1)
        self.dest_entry = ttk.Entry(dest_row, textvariable=self.dest_var, font=("Segoe UI", 10))
        self.dest_entry.grid(row=0, column=0, sticky="ew")
        self.browse_btn = ttk.Button(dest_row, text="Examinar", command=self._on_browse)
        self.browse_btn.grid(row=0, column=1, padx=(8, 0))

        progress_row = tk.Frame(card, bg=_CARD)
        progress_row.grid(row=8, column=0, sticky="ew", padx=16)
        progress_row.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progress_row, mode="determinate", maximum=1)
        self.progress.grid(row=0, column=0, sticky="ew")
        self.status_label = tk.Label(
            card,
            textvariable=self.status_var,
            bg=_CARD,
            fg=_MUTED,
            font=("Segoe UI", 10),
            anchor="w",
            justify="left",
            wraplength=600,
        )
        self.status_label.grid(row=9, column=0, sticky="ew", padx=16, pady=(6, 10))

        actions = tk.Frame(card, bg=_CARD)
        actions.grid(row=10, column=0, sticky="ew", padx=16, pady=(0, 16))
        actions.columnconfigure(0, weight=1)
        self.download_btn = tk.Button(
            actions,
            text="Descargar",
            command=self._on_download,
            bg=_ACCENT,
            fg="white",
            activebackground=_ACCENT_ACTIVE,
            activeforeground="white",
            relief="flat",
            bd=0,
            font=("Segoe UI", 11, "bold"),
            padx=12,
            pady=8,
            cursor="hand2",
        )
        self.download_btn.grid(row=0, column=0, sticky="ew")
        self.open_btn = ttk.Button(actions, text="Abrir carpeta", command=self._on_open_folder)
        self.open_btn.grid(row=0, column=1, padx=(8, 0))

        log_frame = tk.Frame(body, bg=_CARD, highlightthickness=1, highlightbackground="#e5e7eb")
        log_frame.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log = tk.Text(
            log_frame,
            height=8,
            wrap="word",
            state="disabled",
            bg=_CARD,
            fg=_INK,
            relief="flat",
            font=("Segoe UI", 9),
            padx=8,
            pady=8,
        )
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

    def _on_url_changed(self, *_args: object) -> None:
        self.video_var.set("")
        if not self._busy:
            self._set_qualities([QualityOption("Mejor disponible", None)])

    def _on_browse(self) -> None:
        current = self.dest_var.get().strip()
        initial = current if current and Path(current).is_dir() else str(default_download_dir())
        selected = filedialog.askdirectory(title="Carpeta de destino", initialdir=initial)
        if selected:
            self.dest_var.set(selected)

    def _on_load_qualities(self) -> None:
        if self._busy:
            return
        try:
            url = validate_youtube_url(self.url_var.get())
        except DownloaderError as exc:
            self._set_status(str(exc))
            messagebox.showerror("Enlace", str(exc), parent=self)
            return
        self._start_worker("Buscando calidades...", self._load_worker, url)

    def _on_download(self) -> None:
        if self._busy:
            return
        try:
            url = validate_youtube_url(self.url_var.get())
        except DownloaderError as exc:
            self._set_status(str(exc))
            messagebox.showerror("Enlace", str(exc), parent=self)
            return
        destination = self.dest_var.get().strip()
        if not destination:
            messagebox.showerror("Destino", "Selecciona la carpeta de destino.", parent=self)
            return
        audio_only = bool(self.audio_var.get())
        quality = self._qualities.get(self.quality_var.get(), QualityOption("Mejor disponible", None))
        self._log(f"Destino: {destination}")
        if audio_only:
            self._log("Modo: solo audio (MP3)")
        else:
            self._log(f"Calidad: {quality.label}")
        self._start_worker(
            "Preparando la descarga...",
            self._download_worker,
            url,
            Path(destination),
            audio_only,
            quality.height,
            download=True,
        )

    def _on_cancel(self) -> None:
        self._cancel.set()
        self._set_status("Cancelando...")
        self._log("Cancelando la descarga...")

    def _on_open_folder(self) -> None:
        target = self._last_file if self._last_file and self._last_file.exists() else None
        folder = Path(self.dest_var.get().strip() or default_download_dir())
        try:
            if target is not None:
                subprocess.run(["explorer", "/select,", str(target)], check=False)
                return
            if folder.is_dir():
                os.startfile(folder)  # type: ignore[attr-defined]
                return
        except OSError as exc:
            messagebox.showerror("Carpeta", f"No se pudo abrir la carpeta: {exc}", parent=self)
            return
        messagebox.showinfo("Carpeta", "La carpeta de destino todavía no existe.", parent=self)

    def _on_close(self) -> None:
        self._cancel.set()
        self.destroy()

    def _load_worker(self, url: str) -> None:
        info = fetch_video_info(url, on_log=self._enqueue_log)
        self._messages.put(("info", info))

    def _download_worker(self, url: str, destination: Path, audio_only: bool, height: int | None) -> None:
        path = download_video(
            url,
            destination,
            audio_only=audio_only,
            height=height,
            on_progress=self._enqueue_progress,
            on_log=self._enqueue_log,
            cancel_event=self._cancel,
        )
        self._messages.put(("done", path))

    def _start_worker(self, status: str, target, *args, download: bool = False) -> None:
        self._cancel.clear()
        self._set_busy(True, download=download)
        self._set_progress(None)
        self._set_status(status)
        thread = threading.Thread(target=self._run_worker, args=(target, args), daemon=True)
        thread.start()

    def _run_worker(self, target, args: tuple) -> None:
        try:
            target(*args)
        except UserCancelled as exc:
            self._messages.put(("cancelled", str(exc)))
        except DownloaderError as exc:
            self._messages.put(("error", str(exc)))
        except Exception as exc:
            self._messages.put(("error", f"Error inesperado: {exc}"))
        finally:
            self._messages.put(("idle",))

    def _poll_messages(self) -> None:
        if not self.winfo_exists():
            return
        try:
            while True:
                self._handle_message(self._messages.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self._poll_messages)

    def _handle_message(self, message: tuple) -> None:
        kind = message[0]
        if kind == "progress":
            _fraction, text = message[1], message[2]
            self._set_progress(message[1])
            self._set_status(text)
        elif kind == "log":
            self._log(message[1])
        elif kind == "info":
            self._show_video_info(message[1])
        elif kind == "done":
            path = message[1]
            self._last_file = path
            self._set_progress(1)
            self._set_status(f"Listo: {path}")
            self._log(f"Archivo guardado: {path}")
        elif kind == "cancelled":
            self._set_progress(0)
            self._set_status(message[1])
            self._log(message[1])
        elif kind == "error":
            self._set_progress(0)
            self._set_status(message[1])
            self._log(message[1])
            messagebox.showerror("YouTube Downloader", message[1], parent=self)
        elif kind == "idle":
            self._set_busy(False)

    def _show_video_info(self, info: VideoInfo) -> None:
        duration = format_duration(info.duration)
        self.video_var.set(f"{info.title} · {duration}" if duration else info.title)
        self._set_qualities(info.qualities)
        self._set_status("Calidades cargadas. Elige una y pulsa Descargar.")
        self._log(f"Video: {info.title}")

    def _set_qualities(self, qualities: list[QualityOption]) -> None:
        self._qualities = {item.label: item for item in qualities}
        labels = list(self._qualities)
        self.quality_combo.configure(values=labels)
        self.quality_var.set(labels[0] if labels else "")

    def _set_busy(self, busy: bool, download: bool = False) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.url_entry.configure(state=state)
        self.dest_entry.configure(state=state)
        self.load_btn.configure(state=state)
        self.browse_btn.configure(state=state)
        self.audio_check.configure(state=state)
        self.open_btn.configure(state=state)
        if busy and download:
            self.download_btn.configure(
                text="Cancelar",
                bg=_CANCEL,
                activebackground="#1f2937",
                command=self._on_cancel,
                state="normal",
            )
        elif busy:
            self.download_btn.configure(text="Descargar", state="disabled")
        else:
            self.download_btn.configure(
                text="Descargar",
                bg=_ACCENT,
                activebackground=_ACCENT_ACTIVE,
                command=self._on_download,
                state="normal",
            )
        self._refresh_quality_state()

    def _refresh_quality_state(self) -> None:
        if self._busy or self.audio_var.get():
            self.quality_combo.configure(state="disabled")
        else:
            self.quality_combo.configure(state="readonly")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _set_progress(self, fraction: float | None) -> None:
        if fraction is None:
            if str(self.progress.cget("mode")) != "indeterminate":
                self.progress.configure(mode="indeterminate", maximum=100)
                self.progress.start(12)
            return
        if str(self.progress.cget("mode")) != "determinate":
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=1)
        self.progress["value"] = max(0.0, min(1.0, fraction))

    def _log(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{stamp}] {text}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _enqueue_progress(self, fraction: float | None, text: str) -> None:
        self._messages.put(("progress", fraction, text))

    def _enqueue_log(self, text: str) -> None:
        self._messages.put(("log", text))

    def _ffmpeg_status_text(self) -> str:
        executable = ffmpeg_executable()
        if executable is None:
            return "FFmpeg no está disponible. Ejecuta build.bat o instálalo en el PATH antes de descargar."
        return f"FFmpeg: {executable}"


def _print_check() -> None:
    print(f"version={get_version()}")
    executable = ffmpeg_executable()
    if executable is None:
        print("ffmpeg=no encontrado")
        return
    print(f"ffmpeg={executable}")


def _prepare_frozen_stdio() -> None:
    """PyInstaller en modo ventana deja stdout y stderr en None."""
    if not getattr(sys, "frozen", False):
        return
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _enable_windows_dpi() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            return


if __name__ == "__main__":
    main()

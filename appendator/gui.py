"""Interfaz gráfica de Appendator (tkinter)."""

from __future__ import annotations

import logging
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from . import APP_NAME, __version__
from .merge import IMAGE_EXTENSIONS, MD_EXTENSIONS, PDF_EXTENSIONS, SUPPORTED_EXTENSIONS, Cancelled, Options, merge, target_dpi
from .paths import downloads_dir, load_settings, open_in_explorer, output_path_for, save_settings

log = logging.getLogger(__name__)

# Los puntos de Tk en macOS se ven más pequeños que en Windows.
_FONT_SCALE = 1.3 if sys.platform == "darwin" else 1.0


def _pt(size: int) -> int:
    return round(size * _FONT_SCALE)


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / name


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.files: list[Path] = []
        self.output: Path | None = None
        self.out_dir = downloads_dir()
        self.settings = load_settings()

        self._setup_window()
        self._setup_style()
        self._build()
        self._enable_drag_and_drop()
        self._set_running(False)
        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_reqwidth(), self.root.winfo_reqheight())
        self.root.after(100, self._poll_events)

    # ------------------------------------------------------------------ UI
    def _setup_window(self) -> None:
        self.root.title(APP_NAME)
        try:
            if sys.platform == "win32":
                self.root.iconbitmap(default=str(resource_path("icon.ico")))
            else:
                self.root.iconphoto(True, tk.PhotoImage(file=str(resource_path("icon.png"))))
        except Exception:
            pass
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        for theme in ("aqua", "vista", "clam"):  # nativo en macOS y Windows
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        family = "Segoe UI" if sys.platform == "win32" else tkfont.nametofont("TkDefaultFont").actual("family")
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            tkfont.nametofont(name).configure(family=family, size=_pt(10))
        self.font_family = family
        style.configure("Title.TLabel", font=(family, _pt(20), "bold"), foreground="#1f4e79")
        style.configure("Subtitle.TLabel", font=(family, _pt(10)), foreground="#555555")
        style.configure("Section.TLabelframe.Label", font=(family, _pt(11), "bold"),
                        foreground="#1f4e79")
        style.configure("Hint.TLabel", foreground="#666666")
        style.configure("Status.TLabel", font=(family, _pt(10), "italic"), foreground="#444444")
        style.configure("Primary.TButton", font=(family, _pt(11), "bold"), padding=(18, 8))
        style.configure("TButton", padding=(10, 4))
        style.configure("Horizontal.TProgressbar", thickness=22)

    def _build(self) -> None:
        main = ttk.Frame(self.root, padding=(16, 12, 16, 12))
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)

        header = ttk.Frame(main)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(header, text="📎  " + APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Une PDF, Markdown e imágenes en un único PDF, en tu propio equipo "
                 "y sin enviar nada a Internet.",
            style="Subtitle.TLabel",
        ).pack(anchor="w")

        # 1. Archivos -------------------------------------------------------
        files = ttk.LabelFrame(main, text=" 1. Archivos (en el orden en que se unirán) ",
                               style="Section.TLabelframe", padding=10)
        files.grid(row=1, column=0, sticky="nsew", pady=4)
        main.rowconfigure(1, weight=1)
        files.columnconfigure(0, weight=1)
        files.rowconfigure(0, weight=1)
        list_frame = ttk.Frame(files)
        list_frame.grid(row=0, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(list_frame, height=10, width=70, selectmode="extended",
                                  activestyle="none", borderwidth=1, relief="solid",
                                  highlightthickness=0, font=(self.font_family, _pt(10)),
                                  background="#ffffff", foreground="#222222")
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.bind("<Double-Button-1>", lambda _e: self._add_files())
        self.listbox.bind("<Delete>", lambda _e: self._remove_selected())
        self.listbox.bind("<BackSpace>", lambda _e: self._remove_selected())

        buttons = ttk.Frame(files)
        buttons.grid(row=0, column=1, sticky="n", padx=(10, 0))
        self.list_buttons = []
        for text, command in (("➕ Añadir archivos…", self._add_files),
                              ("▲ Subir", lambda: self._move(-1)),
                              ("▼ Bajar", lambda: self._move(1)),
                              ("Quitar", self._remove_selected),
                              ("Vaciar lista", self._clear_files)):
            button = ttk.Button(buttons, text=text, command=command)
            button.pack(fill="x", pady=(0, 4))
            self.list_buttons.append(button)
        self.files_hint = ttk.Label(
            files, style="Hint.TLabel",
            text="Añade PDF, Markdown (.md) o imágenes (PNG, JPG, SVG, WebP…). "
                 "Sin límite de tamaño.")
        self.files_hint.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # 2. Opciones -------------------------------------------------------
        opts = ttk.LabelFrame(main, text=" 2. Opciones ", style="Section.TLabelframe",
                              padding=10)
        opts.grid(row=2, column=0, sticky="ew", pady=4)
        opts.columnconfigure(1, weight=1)
        s = self.settings
        self.separators_var = tk.BooleanVar(value=s.get("separators", True))
        self.compress_var = tk.BooleanVar(value=s.get("compress", False))
        self.quality_var = tk.IntVar(value=s.get("quality", 60))
        self.check_separators = ttk.Checkbutton(
            opts, variable=self.separators_var,
            text="Página con el nombre del archivo antes de cada uno "
                 "(ayuda a una IA a distinguirlos)")
        self.check_separators.grid(row=0, column=0, columnspan=3, sticky="w")
        self.check_compress = ttk.Checkbutton(opts, text="Comprimir imágenes",
                                              variable=self.compress_var,
                                              command=self._update_quality)
        self.check_compress.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.lbl_quality = ttk.Label(opts, width=34)
        self.lbl_quality.grid(row=1, column=2, sticky="w", pady=(8, 0))
        self.scale = ttk.Scale(opts, from_=10, to=95, orient="horizontal",
                               command=lambda v: self._update_quality(round(float(v))))
        self.scale.set(self.quality_var.get())
        self.scale.grid(row=1, column=1, sticky="ew", padx=10, pady=(8, 0))
        self._update_quality()

        dest = ttk.Frame(main)
        dest.grid(row=3, column=0, sticky="ew", pady=(6, 4))
        ttk.Label(dest, text="📁 El PDF combinado se guardará en:").pack(side="left")
        ttk.Label(dest, text=str(self.out_dir), font=(self.font_family, _pt(10), "bold")).pack(
            side="left", padx=6)
        ttk.Button(dest, text="Abrir carpeta",
                   command=lambda: open_in_explorer(self.out_dir)).pack(side="right")

        # 3. Progreso -------------------------------------------------------
        prog = ttk.LabelFrame(main, text=" 3. Progreso ", style="Section.TLabelframe",
                              padding=10)
        prog.grid(row=4, column=0, sticky="ew", pady=4)
        prog.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(prog, maximum=1000)
        self.progress.grid(row=0, column=0, sticky="ew")
        self.lbl_status = ttk.Label(prog, style="Status.TLabel", text="Esperando archivos…")
        self.lbl_status.grid(row=1, column=0, sticky="w", pady=(6, 0))

        bottom = ttk.Frame(main)
        bottom.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        self.btn_open = ttk.Button(bottom, text="Abrir PDF", command=self._open_output)
        self.btn_open.pack(side="left")
        ttk.Label(bottom, text=f"v{__version__}", style="Hint.TLabel").pack(side="left", padx=10)
        self.btn_start = ttk.Button(bottom, text="▶  Combinar", style="Primary.TButton",
                                    command=self._start)
        self.btn_start.pack(side="right")
        self.btn_cancel = ttk.Button(bottom, text="Cancelar", command=self._cancel)
        self.btn_cancel.pack(side="right", padx=8)

    def _update_quality(self, value: int | None = None) -> None:
        if value is not None:
            self.quality_var.set(value)
        q = self.quality_var.get()
        self.lbl_quality.configure(text=f"Calidad {q} %  ·  JPEG {q}, máx. {target_dpi(q)} ppp")
        state = "normal" if self.compress_var.get() and self.worker is None else "disabled"
        self.scale.state(["!disabled"] if state == "normal" else ["disabled"])
        self.lbl_quality.configure(foreground="#222222" if state == "normal" else "#999999")

    def _enable_drag_and_drop(self) -> None:
        if sys.platform != "win32":
            return
        try:
            import windnd

            def dropped(paths):
                # Se difiere al bucle de Tk para no bloquear el mensaje de Windows.
                decoded = [p.decode("mbcs") if isinstance(p, bytes) else p for p in paths]
                self.root.after(0, lambda: self._add_paths([Path(p) for p in decoded]))

            windnd.hook_dropfiles(self.root, func=dropped, force_unicode=True)
            self.files_hint.configure(
                text="Arrastra aquí archivos o carpetas, o pulsa «Añadir archivos…» "
                     "(PDF, Markdown e imágenes). Sin límite de tamaño.")
        except Exception:
            log.info("Arrastrar y soltar no disponible", exc_info=True)

    # ------------------------------------------------------------ archivos
    def _add_files(self) -> None:
        if self.worker is not None:
            return
        selected = filedialog.askopenfilenames(
            parent=self.root,
            title="Selecciona PDF, Markdown o imágenes",
            initialdir=self.settings.get("last_dir") or str(Path.home()),
            filetypes=[
                ("PDF, Markdown e imágenes", " ".join("*" + e for e in SUPPORTED_EXTENSIONS)),
                ("PDF", " ".join("*" + e for e in PDF_EXTENSIONS)),
                ("Markdown", " ".join("*" + e for e in MD_EXTENSIONS)),
                ("Imágenes", " ".join("*" + e for e in IMAGE_EXTENSIONS)),
            ],
        )
        if selected:
            self.settings["last_dir"] = str(Path(selected[0]).parent)
            self._add_paths([Path(p) for p in selected])

    def _add_paths(self, paths: list[Path]) -> None:
        if self.worker is not None:
            return
        expanded: list[Path] = []
        for p in paths:
            if p.is_dir():
                expanded += sorted(f for f in p.rglob("*")
                                   if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS)
            elif p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                expanded.append(p)
        for p in expanded:
            if p not in self.files:
                self.files.append(p)
        self._refresh_list()

    def _refresh_list(self, selected: list[int] | None = None) -> None:
        self.listbox.delete(0, "end")
        for i, p in enumerate(self.files, 1):
            self.listbox.insert("end", f"{i}.  {p.name}   ({_human_size(p.stat().st_size)})")
        for i in selected or []:
            self.listbox.selection_set(i)
        n = len(self.files)
        self.lbl_status.configure(
            text="Esperando archivos…" if n == 0 else
            f"{n} archivo{'s' if n != 1 else ''} listo{'s' if n != 1 else ''} para combinar")

    def _move(self, step: int) -> None:
        indices = list(self.listbox.curselection())
        if self.worker is not None or not indices:
            return
        if (step < 0 and indices[0] == 0) or (step > 0 and indices[-1] == len(self.files) - 1):
            return
        for i in (indices if step < 0 else reversed(indices)):
            self.files[i], self.files[i + step] = self.files[i + step], self.files[i]
        self._refresh_list([i + step for i in indices])

    def _remove_selected(self) -> None:
        if self.worker is not None:
            return
        for index in reversed(self.listbox.curselection()):
            del self.files[index]
        self._refresh_list()

    def _clear_files(self) -> None:
        if self.worker is not None:
            return
        self.files.clear()
        self._refresh_list()

    # ------------------------------------------------------------- trabajo
    def _start(self) -> None:
        if self.worker is not None:
            return
        missing = [p for p in self.files if not p.exists()]
        if missing:
            messagebox.showerror(APP_NAME, "Estos archivos ya no existen:\n\n" +
                                 "\n".join(f"• {p}" for p in missing), parent=self.root)
            return
        if not self.files:
            messagebox.showinfo(APP_NAME, "Añade al menos un archivo.", parent=self.root)
            return
        options = Options(separators=self.separators_var.get(),
                          compress=self.compress_var.get(), quality=self.quality_var.get())
        output = output_path_for(self.files[0], self.out_dir)
        self.cancel_event.clear()
        self.progress["value"] = 0
        files = list(self.files)

        def work() -> None:
            try:
                pages = merge(files, output, options,
                              lambda fraction, text: self.events.put(("progress", fraction, text)),
                              self.cancel_event)
                self.events.put(("done", output, pages))
            except Cancelled:
                self.events.put(("cancelled",))
            except Exception as exc:
                log.exception("Error al combinar")
                self.events.put(("error", str(exc) or type(exc).__name__))

        self.worker = threading.Thread(target=work, daemon=True)
        self._set_running(True)
        self.worker.start()

    def _cancel(self) -> None:
        if self.worker is not None:
            self.cancel_event.set()
            self.lbl_status.configure(text="Cancelando…")

    def _set_running(self, running: bool) -> None:
        state = ["disabled"] if running else ["!disabled"]
        for widget in (*self.list_buttons, self.check_separators, self.check_compress,
                       self.btn_start):
            widget.state(state)
        self.btn_cancel.state(["!disabled"] if running else ["disabled"])
        self.btn_open.state(["!disabled"] if self.output and not running else ["disabled"])
        self._update_quality()

    def _poll_events(self) -> None:
        try:
            while True:
                kind, *data = self.events.get_nowait()
                if kind == "progress":
                    fraction, text = data
                    self.lbl_status.configure(text=text)
                    if fraction is None:  # guardado final: qpdf no informa del avance
                        self.progress.configure(mode="indeterminate")
                        self.progress.start(12)
                    else:
                        self.progress["value"] = fraction * 1000
                        self.root.title(f"{fraction:.0%} · {APP_NAME}")
                else:
                    self._on_finished(kind, *data)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _on_finished(self, kind: str, *data) -> None:
        self.worker = None
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress["value"] = 1000 if kind == "done" else 0
        self.root.title(APP_NAME)
        if kind == "done":
            self.output, pages = data
            self._set_running(False)
            self.lbl_status.configure(text=f"Completado: {self.output.name} ({pages} páginas)")
            if messagebox.askyesno(
                    APP_NAME, f"PDF guardado en Descargas:\n\n{self.output.name}\n"
                              f"{pages} páginas, {_human_size(self.output.stat().st_size)}"
                              "\n\n¿Quieres abrirlo ahora?", parent=self.root):
                self._open_output()
            return
        self._set_running(False)
        if kind == "cancelled":
            self.lbl_status.configure(text="Cancelado. No se ha guardado nada.")
        else:
            self.lbl_status.configure(text="Error: no se ha guardado nada.")
            messagebox.showerror(APP_NAME, f"No se pudo combinar:\n\n{data[0]}", parent=self.root)

    def _open_output(self) -> None:
        if self.output and self.output.exists():
            open_in_explorer(self.output)

    def _on_close(self) -> None:
        if self.worker is not None and not messagebox.askyesno(
                APP_NAME, "Hay una combinación en curso. ¿Quieres cancelarla y salir?",
                parent=self.root):
            return
        self.cancel_event.set()
        self.settings.update(separators=self.separators_var.get(),
                             compress=self.compress_var.get(), quality=self.quality_var.get())
        save_settings(self.settings)
        self.root.destroy()


def _human_size(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def run() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()

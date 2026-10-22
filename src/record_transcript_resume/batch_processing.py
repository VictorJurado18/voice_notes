"""Selection planning and a compact review before committing a processing batch."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
import customtkinter as ctk

from record_transcript_resume.jobs import QueueRequest
from record_transcript_resume.library import BrowserEntry, MEDIA_SUFFIXES
from record_transcript_resume.meeting_naming import is_meeting_folder


def browser_requests(entries: list[BrowserEntry], library_root: Path) -> tuple[list[QueueRequest], int]:
    requests, skipped, seen = [], 0, set()
    library_root = library_root.resolve()
    for entry in entries:
        try:
            if entry.kind == "audio":
                media = [entry.path]
            elif entry.kind in {"folder", "recording"} and not entry.path.is_symlink() and not entry.path.is_junction():
                media = sorted((path for path in entry.path.iterdir()
                                if path.is_file() and not path.is_symlink() and path.suffix.casefold() in MEDIA_SUFFIXES),
                               key=lambda path: path.name.casefold())
            else:
                media = []
        except OSError:
            media = []
        if not media:
            skipped += 1
        for audio in media:
            key = str(audio.resolve()).casefold()
            if key not in seen:
                seen.add(key)
                requests.append(QueueRequest(audio, audio.parent,
                                             reuse_source_folder=audio.parent.resolve() != library_root))
    return requests, skipped


@dataclass(frozen=True)
class BatchCandidate:
    request: QueueRequest
    unavailable: str = ""
    has_results: bool = False


def has_saved_results(request: QueueRequest) -> bool:
    if request.preserve_source or not request.reuse_source_folder or not is_meeting_folder(request.audio):
        return False
    return any((request.audio.parent / name).is_file() for name in ("transcription.md", "summary.md"))


class BatchReview(ctk.CTkToplevel):
    def __init__(self, parent, *, candidates: list[BatchCandidate], colors, options_text: str,
                 output_mode: str, skipped: int, submit):
        super().__init__(parent)
        self.title("Adicionar áudios à fila")
        parent._fit_dialog(self, 650, 650, 600, 570)
        self.configure(fg_color=colors["bg"])
        self.transient(parent)
        self.grab_set()
        self.candidates = candidates
        self.selected = {index for index, item in enumerate(candidates) if not item.unavailable and not item.has_results}
        self.page = 0
        self.page_size = 20
        self._colors = colors
        self._submit = submit
        self.output = tk.StringVar(value="Só transcrição" if output_mode == "transcription" else "Transcrição e resumo")
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(10, 18))
        ctk.CTkButton(footer, text="Cancelar", width=100, height=36, command=self.destroy,
                      fg_color=colors["surface_button"], hover_color=colors["surface_button_hover"],
                      text_color=colors["text"]).pack(side=tk.RIGHT)
        self.add_button = ctk.CTkButton(footer, text="Adicionar à fila", width=185, height=36,
                                        command=self.submit, fg_color=colors["accent"], hover_color=colors["accent_hover"],
                                        text_color=colors["accent_text"])
        self.add_button.pack(side=tk.RIGHT, padx=(0, 8))
        self.add_button._help_text = "Salva os áudios marcados na fila. Cada áudio será processado individualmente e a fila continuará após uma falha."
        shell = ctk.CTkFrame(self, fg_color=colors["surface"], corner_radius=12)
        shell.pack(fill=tk.BOTH, expand=True, padx=14, pady=(14, 0))
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(4, weight=1)
        ctk.CTkLabel(shell, text="Processar vários áudios", anchor="w", font=("Segoe UI", 18, "bold"),
                     text_color=colors["text"]).grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 4))
        ctk.CTkLabel(shell, text="Confira a seleção. A fila executa um áudio por vez e continua após uma falha.",
                     anchor="w", justify=tk.LEFT, wraplength=520, font=("Segoe UI", 11),
                     text_color=colors["muted"]).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        controls = ctk.CTkFrame(shell, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        for label, checked in (("Marcar todos", True), ("Desmarcar todos", False)):
            ctk.CTkButton(controls, text=label, width=120, height=28,
                          command=lambda value=checked: self.select_all(value), fg_color=colors["surface_button"],
                          hover_color=colors["surface_button_hover"], text_color=colors["text"]).pack(side=tk.LEFT, padx=(0, 6))
        self.count = ctk.CTkLabel(shell, text="", anchor="w", font=("Segoe UI", 11), text_color=colors["text"])
        self.count.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 7))
        self.rows = ctk.CTkScrollableFrame(shell, fg_color=colors["surface_deep"], height=240)
        self.rows.grid(row=4, column=0, sticky="nsew", padx=14)
        pages = ctk.CTkFrame(shell, fg_color="transparent")
        pages.grid(row=5, column=0, sticky="ew", padx=16, pady=(6, 8))
        self.page_label = ctk.CTkLabel(pages, text="", text_color=colors["muted"], font=("Segoe UI", 10))
        self.page_label.pack(side=tk.LEFT)
        self.next = ctk.CTkButton(pages, text="Próxima", width=78, height=26,
                                  command=lambda: self.move_page(1), fg_color=colors["surface_button"], text_color=colors["text"])
        self.next.pack(side=tk.RIGHT)
        self.previous = ctk.CTkButton(pages, text="Anterior", width=78, height=26,
                                      command=lambda: self.move_page(-1), fg_color=colors["surface_button"], text_color=colors["text"])
        self.previous.pack(side=tk.RIGHT, padx=(0, 6))
        settings = ctk.CTkFrame(shell, fg_color="transparent")
        settings.grid(row=6, column=0, sticky="ew", pady=(0, 14))
        ctk.CTkLabel(settings, text="Resultado para os áudios selecionados", anchor="w", font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"]).pack(fill=tk.X, padx=16)
        ctk.CTkOptionMenu(settings, variable=self.output, values=["Transcrição e resumo", "Só transcrição"],
                          fg_color=colors["surface_button"], button_color=colors["surface_button_hover"],
                          text_color=colors["text"], height=34).pack(fill=tk.X, padx=16, pady=(3, 6))
        ctk.CTkLabel(settings, text=options_text, anchor="w", justify=tk.LEFT, wraplength=520,
                     font=("Segoe UI", 10), text_color=colors["muted"]).pack(fill=tk.X, padx=16, pady=(0, 8))
        note = "Áudios já processados começam desmarcados. Marque-os somente para reprocessar."
        if skipped:
            note += f"\nItens sem áudio direto ignorados: {skipped}."
        ctk.CTkLabel(settings, text=note, anchor="w", justify=tk.LEFT, wraplength=520, font=("Segoe UI", 10),
                     text_color=colors["muted"]).pack(fill=tk.X, padx=16)
        self.render()
        self.after(100, self.focus_force)

    def select_all(self, checked):
        self.selected = {index for index, candidate in enumerate(self.candidates) if not candidate.unavailable} if checked else set()
        self.render()

    def move_page(self, direction):
        self.page += direction
        self.render()
        self.rows._parent_canvas.yview_moveto(0)

    def render(self):
        for widget in self.rows.winfo_children():
            widget.destroy()
        start = self.page * self.page_size
        self._variables = []
        for index in range(start, min(start + self.page_size, len(self.candidates))):
            candidate = self.candidates[index]
            row = ctk.CTkFrame(self.rows, fg_color="transparent")
            row.pack(fill=tk.X, padx=8, pady=6)
            value = tk.BooleanVar(value=index in self.selected)
            self._variables.append(value)
            def select(i=index, variable=value):
                if variable.get():
                    self.selected.add(i)
                else:
                    self.selected.discard(i)
                self.refresh_count()
            checkbox = ctk.CTkCheckBox(row, text="", variable=value, command=select, width=24,
                                       checkbox_width=18, checkbox_height=18, fg_color=self._colors["accent"],
                                       state=tk.DISABLED if candidate.unavailable else tk.NORMAL)
            checkbox.pack(side=tk.LEFT, padx=(0, 7))
            text = ctk.CTkFrame(row, fg_color="transparent")
            text.pack(side=tk.LEFT, fill=tk.X, expand=True)
            ctk.CTkLabel(text, text=candidate.request.audio.name, anchor="w", justify=tk.LEFT, wraplength=450,
                         font=("Segoe UI", 11, "bold"), text_color=self._colors["text"]).pack(fill=tk.X)
            detail = candidate.unavailable or ("Já possui resultado · incluir para reprocessar" if candidate.has_results else "Pronto para entrar na fila")
            ctk.CTkLabel(text, text=detail, anchor="w", justify=tk.LEFT, wraplength=450,
                         font=("Segoe UI", 10), text_color=self._colors["muted"]).pack(fill=tk.X)
        self.previous.configure(state=tk.NORMAL if self.page else tk.DISABLED)
        self.next.configure(state=tk.NORMAL if start+self.page_size < len(self.candidates) else tk.DISABLED)
        self.page_label.configure(text=f"{start+1 if self.candidates else 0}–{min(start+self.page_size,len(self.candidates))} de {len(self.candidates)} áudios")
        self.refresh_count()

    def refresh_count(self):
        count = len(self.selected)
        self.count.configure(text="1 áudio selecionado" if count == 1 else f"{count} áudios selecionados")
        self.add_button.configure(text=f"Adicionar {len(self.selected)} à fila", state=tk.NORMAL if self.selected else tk.DISABLED)

    def submit(self):
        selected = [candidate.request for index, candidate in enumerate(self.candidates)
                    if index in self.selected and not candidate.unavailable]
        mode = "transcription" if self.output.get() == "Só transcrição" else "both"
        if selected and self._submit(selected, mode):
            self.destroy()

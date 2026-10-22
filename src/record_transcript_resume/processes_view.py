"""One queue table for focus and full-screen windows."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tkinter as tk
import customtkinter as ctk
from record_transcript_resume.navigation_view import NavigationScrollFrame

LABELS = {"running": "Processando", "queued": "Na fila", "failed": "Falhou",
          "needs_attention": "Atenção", "warning": "Com aviso", "cancelled": "Cancelado", "completed": "Concluído"}


class ProcessActionButton(ctk.CTkButton):
    """Quiet, theme-aware line icons without font-dependent Unicode glyphs."""

    def __init__(self, parent, *, operation, label, help_text, **kwargs):
        self.operation = operation
        self.action_label = label
        self._help_text = help_text
        super().__init__(parent, text="", width=32, height=32, corner_radius=7,
                         border_width=0, fg_color="transparent", **kwargs)
        self._canvas.configure(takefocus=1 if self.cget("state") == tk.NORMAL else 0)
        self._canvas.bind("<Return>", lambda _event: self.invoke(), add="+")
        self._canvas.bind("<space>", lambda _event: self.invoke(), add="+")
        self._canvas.bind("<FocusIn>", lambda _event: self._draw(), add="+")
        self._canvas.bind("<FocusOut>", lambda _event: self._draw(), add="+")

    def _draw(self, no_color_updates=False):
        super()._draw(no_color_updates)
        canvas = self._canvas
        canvas.delete("process_icon")
        ink = self._apply_appearance_mode(
            self._text_color_disabled if self._state == tk.DISABLED else self._text_color,
        )
        scale = self._apply_widget_scaling
        # 24-unit geometry, rendered at 18 logical pixels and centered in a
        # 32-pixel target. Redrawing uses current theme roles and DPI scaling.
        def points(*coordinates):
            return tuple(scale((self._current_width if i % 2 == 0 else self._current_height) / 2
                               + (value - 12) * .75) for i, value in enumerate(coordinates))
        stroke = dict(fill=ink, width=scale(1.5), tags="process_icon")
        def line(*coordinates):
            canvas.create_line(*points(*coordinates), capstyle=tk.ROUND, joinstyle=tk.ROUND, **stroke)
        def oval(*coordinates):
            canvas.create_oval(*points(*coordinates), outline=ink, width=scale(1.5), tags="process_icon")
        if self.operation == "open":
            line(3, 19, 3, 5, 9, 5, 12, 8, 21, 8, 21, 19, 3, 19)
            line(3, 10, 21, 10)
        elif self.operation == "retry":
            canvas.create_arc(*points(4, 4, 20, 20), start=35, extent=290, style=tk.ARC,
                              outline=ink, width=scale(1.5), tags="process_icon")
            line(20, 3, 20, 9, 14, 9)
        elif self.operation == "details":
            oval(3, 3, 21, 21)
            line(12, 11, 12, 17)
            line(12, 7, 12, 7.5)
        elif self.operation == "cancel":
            oval(3, 3, 21, 21)
            line(9, 9, 15, 15)
            line(15, 9, 9, 15)
        elif self.operation == "remove":
            line(4, 7, 20, 7)
            line(9, 7, 9, 4, 15, 4, 15, 7)
            line(6, 7, 7, 21, 17, 21, 18, 7)
            line(10, 11, 10, 17)
            line(14, 11, 14, 17)
        if canvas.focus_get() == canvas:
            canvas.create_rectangle(scale(2), scale(2), scale(self._current_width-2),
                                    scale(self._current_height-2), outline=ink,
                                    width=scale(1), tags="process_icon")


class ProcessTable(ctk.CTkFrame):
    def __init__(self, parent, *, colors, color, action, clear, refresh, forecast, can_cancel):
        super().__init__(parent, fg_color=color("#0D1525"), corner_radius=12)
        self.colors, self.color = colors, color
        self.action, self.forecast = action, forecast
        self.can_cancel = can_cancel
        self.jobs, self.rows = [], []
        self.desktop = False
        self.page = 0
        self._signature = None
        self.choice = tk.StringVar(value="Todos")
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill=tk.X, padx=16, pady=(18, 8))
        ctk.CTkLabel(header, text="Processos", font=("Segoe UI", 22, "bold"),
                     anchor="w", text_color=colors["text"]).pack(side=tk.LEFT)
        ctk.CTkButton(header, text="Atualizar", width=88, height=34, command=refresh,
                      fg_color=color("#263550")).pack(side=tk.RIGHT)
        self.clear_button = ctk.CTkButton(header, text="Limpar concluídos", width=148, height=34,
                                         command=clear, fg_color=color("#263550"))
        self.clear_button.pack(side=tk.RIGHT, padx=(0, 8))
        self.overview = ctk.CTkLabel(self, text="", anchor="w", justify=tk.LEFT,
                                    font=("Segoe UI", 11), text_color=colors["muted"], wraplength=630)
        self.overview.pack(fill=tk.X, padx=18, pady=(0, 12))
        filters = ctk.CTkFrame(self, fg_color="transparent")
        filters.pack(fill=tk.X, padx=18, pady=(0, 12))
        self.filter_buttons = {}
        for name in ("Todos", "Em andamento", "Aguardando", "Atenção", "Concluídos"):
            button = ctk.CTkButton(filters, text=name, width=110, height=32,
                                   command=lambda n=name: self.select_filter(n),
                                   font=("Segoe UI", 10), fg_color=color("#263550"))
            button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
            self.filter_buttons[name] = button
        self.heading = ctk.CTkFrame(self, fg_color="transparent", height=32)
        self.heading.pack(fill=tk.X, padx=(22, 28), pady=(0, 5))
        self.headings = []
        for index, text in enumerate(("Áudio", "Estado / etapa", "Tempo", "Ações")):
            label = ctk.CTkLabel(self.heading, text=text, anchor="w", text_color=colors["muted"],
                                 font=("Segoe UI", 11, "bold"))
            label.grid(row=0, column=index, sticky="ew", padx=6)
            self.headings.append(label)
        self.body = NavigationScrollFrame(self, fg_color="transparent", height=400,
                                          scrollbar_button_color=color("#34445F"))
        self.body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 14))
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=18, pady=(0, 12), before=self.body._parent_frame)
        self.page_label = ctk.CTkLabel(footer, text="", text_color=colors["muted"], anchor="w")
        self.page_label.pack(side=tk.LEFT)
        self.next_button = ctk.CTkButton(footer, text="Próxima", width=85, height=28,
                                        command=lambda:self.change_page(1), fg_color=color("#263550"))
        self.next_button.pack(side=tk.RIGHT)
        self.previous_button = ctk.CTkButton(footer, text="Anterior", width=85, height=28,
                                            command=lambda:self.change_page(-1), fg_color=color("#263550"))
        self.previous_button.pack(side=tk.RIGHT, padx=(0,6))

    def select_filter(self, name):
        self.choice.set(name)
        self.page = 0
        self.render(self.jobs)

    def change_page(self, direction):
        self.page = max(0, self.page + direction)
        self.render(self.jobs)
        self.body._parent_canvas.yview_moveto(0)

    def layout(self, desktop: bool):
        if self.desktop != desktop:
            self.desktop = desktop
            self.render(self.jobs)
        self._columns(self.heading)

    def _columns(self, frame):
        widths = (0, 150, 190, 192) if self.desktop else (0, 100, 100, 192)
        for index, width in enumerate(widths):
            frame.grid_columnconfigure(index, weight=1 if index == 0 else 0,
                                        minsize=width, uniform="" if index else "audio")

    def render(self, jobs):
        signature = (tuple(jobs), self.choice.get(), self.desktop, self.page,
                     tuple(self.can_cancel(j) for j in jobs))
        if signature == self._signature:
            return
        self._signature = signature
        position = self.body._parent_canvas.yview()[0]
        self.jobs = list(jobs)
        counts = {"Todos": len(jobs), "Em andamento": sum(j.status == "running" for j in jobs),
                  "Aguardando": sum(j.status == "queued" for j in jobs),
                  "Atenção": sum(j.status in {"failed", "warning", "needs_attention", "cancelled"} for j in jobs),
                  "Concluídos": sum(j.status == "completed" for j in jobs)}
        choice = self.choice.get()
        for name, button in self.filter_buttons.items():
            button.configure(text=f"{name}  {counts[name]}",
                             fg_color=self.color("#314B70") if choice == name else self.color("#263550"))
        self.clear_button.configure(state=tk.NORMAL if counts["Concluídos"] else tk.DISABLED)
        self.overview.configure(text=(f"{counts['Em andamento']} processando · {counts['Aguardando']} na fila · "
                                      f"{counts['Atenção']} exigem atenção. Você pode gravar enquanto processa."))
        visible = [j for j in jobs if choice == "Todos" or
                   choice == "Em andamento" and j.status == "running" or
                   choice == "Aguardando" and j.status == "queued" or
                   choice == "Atenção" and j.status in {"failed", "warning", "needs_attention", "cancelled"} or
                   choice == "Concluídos" and j.status == "completed"]
        visible.sort(key=lambda j: (0 if j.status == "running" else 1 if j.status == "queued" else 2,
                                   j.created_at if j.status in {"queued", "running"} else ""))
        # Keep finished records recent first, without hiding any successful jobs.
        active = [j for j in visible if j.status in {"running", "queued"}]
        finished = sorted((j for j in visible if j.status not in {"running", "queued"}), key=lambda j:j.updated_at, reverse=True)
        ordered = [*active, *finished]
        self.page = min(self.page, max(0, (len(ordered)-1)//25))
        start = self.page * 25
        self.page_label.configure(text=f"{start+1 if ordered else 0}–{min(start+25,len(ordered))} de {len(ordered)} processos")
        self.previous_button.configure(state=tk.NORMAL if self.page else tk.DISABLED)
        self.next_button.configure(state=tk.NORMAL if start+25 < len(ordered) else tk.DISABLED)
        for child in self.body.winfo_children():
            child.destroy()
        self.rows = []
        for job in ordered[start:start+25]:
            row = ctk.CTkFrame(self.body, fg_color=self.color("#17213A"), corner_radius=8)
            row.pack(fill=tk.X, pady=(0, 8))
            self._columns(row)
            name = ctk.CTkFrame(row, fg_color="transparent")
            name.grid(row=0, column=0, sticky="nsew", padx=(10, 6), pady=12)
            title = ctk.CTkLabel(name, text=job.audio_path.name, anchor="w", justify=tk.LEFT,
                                 font=("Segoe UI", 12, "bold"), text_color=self.colors["text"], wraplength=180)
            title.pack(fill=tk.X)
            def wrap(event, label=title):
                width = max(80, event.width - 8)
                if abs(int(label.cget("wraplength"))-width) > 10:
                    label.configure(wraplength=width)
            name.bind("<Configure>", wrap)
            try:
                when = datetime.fromisoformat(job.created_at).astimezone().strftime("%d/%m %H:%M")
            except ValueError:
                when = ""
            duration = f"{max(1,round(job.audio_seconds/60))} min de áudio · " if job.audio_seconds else ""
            ctk.CTkLabel(name, text=duration+when, anchor="w", font=("Segoe UI", 10),
                         text_color=self.colors["muted"]).pack(fill=tk.X)
            state = ctk.CTkFrame(row, fg_color="transparent")
            state.grid(row=0, column=1, sticky="ew", padx=6, pady=10)
            state_color = self.colors["success"] if job.status == "completed" else self.colors["danger"] if job.status == "failed" else self.colors["warning"] if job.status in {"warning", "needs_attention"} else self.colors["muted"]
            ctk.CTkLabel(state, text=LABELS.get(job.status, job.status), anchor="w",
                         text_color=state_color, font=("Segoe UI", 11, "bold")).pack(fill=tk.X)
            ctk.CTkLabel(state, text=job.stage, anchor="w", justify=tk.LEFT,
                         wraplength=138 if self.desktop else 90, font=("Segoe UI", 10),
                         text_color=self.colors["muted"]).pack(fill=tk.X)
            ctk.CTkLabel(row, text=self.forecast(job), anchor="w", justify=tk.LEFT,
                         wraplength=175 if self.desktop else 88, font=("Segoe UI", 10),
                         text_color=self.colors["muted"]).grid(row=0,column=2,sticky="ew",padx=6,pady=10)
            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.grid(row=0, column=3, sticky="e", padx=8, pady=10)
            retry = job.status in {"failed", "needs_attention", "cancelled"} and job.audio_path.is_file()
            retry = retry or job.summary_failed and (Path(job.output_dir)/"transcription.md").is_file()
            enabled = (Path(job.output_dir).is_dir(), retry, bool(job.error), self.can_cancel(job), job.status != "running")
            descriptions = (
                ("open", "Pasta", "Abrir a pasta deste processo.", "A pasta deste processo não está disponível."),
                ("retry", "Repetir", "Tentar novamente o processamento que falhou.", "Não há uma falha para repetir ou o arquivo de origem está indisponível."),
                ("details", "Detalhes", "Ver os detalhes do erro ou aviso deste processo.", "Este processo não possui erros ou avisos registrados."),
                ("cancel", "Cancelar", "Cancelar o processamento em andamento. O áudio salvo será preservado.", "O cancelamento não está disponível para este processo neste momento."),
                ("remove", "Remover", "Remover apenas este processo da lista. O áudio e os documentos serão mantidos.", "Aguarde o processamento terminar antes de removê-lo da lista."),
            )
            for index, ((code, label, help_text, unavailable), active_button) in enumerate(zip(descriptions, enabled)):
                if code == "retry" and job.summary_failed and active_button:
                    help_text = "Tentar gerar novamente o resumo a partir da transcrição salva."
                button = ProcessActionButton(
                    actions, operation=code, label=label,
                    help_text=help_text if active_button else unavailable,
                    state=tk.NORMAL if active_button else tk.DISABLED,
                    text_color=self.colors["muted"], text_color_disabled=self.color("#53647F"),
                    hover_color=self.color("#263550"),
                    command=lambda op=code, jid=job.id:self.action(op,jid),
                )
                button.grid(row=0, column=index, padx=(0,4) if index < 4 else 0, pady=3)
            self.rows.append(row)
        if not visible:
            ctk.CTkLabel(self.body, text="Nenhum processo nesta visão.", text_color=self.colors["muted"],
                         font=("Segoe UI",12)).pack(anchor="w", padx=10,pady=24)
        self.after_idle(lambda:self.body._parent_canvas.yview_moveto(position))

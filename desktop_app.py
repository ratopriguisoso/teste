"""Analisador de SEO para Windows (e qualquer PC com Python).

Escaneia um site como um antivírus: mostra a nota, os problemas encontrados,
o código para corrigir cada um e pode vigiar o site continuamente, avisando
quando surgir um problema novo.

Rodar pelo código-fonte:  python desktop_app.py
Gerar o .exe:             pyinstaller --onefile --windowed --name AnalisadorSEO desktop_app.py
"""

import asyncio
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import httpx

import seo_audit

BG = "#0f1115"
PANEL = "#171a21"
PANEL_2 = "#1f232c"
TEXT = "#e6e8ee"
MUTED = "#8b93a7"
ACCENT = "#7c5cff"
COLORS = {"ok": "#16a34a", "aviso": "#ca8a04", "erro": "#ef4444"}
STATUS_TEXT = {"ok": "✓ OK", "aviso": "! Aviso", "erro": "✕ Erro"}


def scan_worker(url: str, keyword: str, events: queue.Queue) -> None:
    async def consume() -> None:
        async for event in seo_audit.scan(url, keyword):
            events.put(event)

    try:
        asyncio.run(consume())
    except seo_audit.AuditError as exc:
        events.put({"type": "error", "message": str(exc)})
    except (httpx.HTTPError, OSError) as exc:
        events.put({"type": "error", "message": f"Erro inesperado: {exc}"})


class ScanButton(tk.Canvas):
    SIZE = 170

    def __init__(self, master: tk.Misc, command) -> None:
        super().__init__(
            master,
            width=self.SIZE,
            height=self.SIZE,
            bg=PANEL,
            highlightthickness=0,
            cursor="hand2",
        )
        self.command = command
        self.enabled = True
        pad = 8
        end = self.SIZE - pad
        self.create_oval(pad, pad, end, end, outline=PANEL_2, width=10)
        self.arc = self.create_arc(
            pad,
            pad,
            end,
            end,
            start=90,
            extent=0,
            style="arc",
            outline=ACCENT,
            width=10,
        )
        self.face = self.create_oval(
            22, 22, self.SIZE - 22, self.SIZE - 22, fill=ACCENT, outline=""
        )
        self.label = self.create_text(
            self.SIZE / 2,
            self.SIZE / 2,
            text="ESCANEAR",
            fill="white",
            font=("Segoe UI", 12, "bold"),
        )
        self.bind("<Button-1>", lambda _: self.enabled and self.command())

    def set_progress(self, value: int | None, label: str = "ESCANEAR") -> None:
        self.enabled = value is None
        self.itemconfigure(self.arc, extent=-3.6 * (value or 0))
        self.itemconfigure(self.face, fill=ACCENT if value is None else BG)
        self.itemconfigure(
            self.label,
            text=label if value is None else f"{value}%",
            font=("Segoe UI", 12 if value is None else 26, "bold"),
        )
        self.configure(cursor="hand2" if value is None else "watch")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Analisador de SEO")
        self.geometry("980x760")
        self.minsize(820, 620)
        self.configure(bg=BG)
        self.events: queue.Queue = queue.Queue()
        self.scanning = False
        self.report: dict | None = None
        self.previous: dict | None = None
        self.monitor_job: str | None = None
        self.from_monitor = False
        self.setup_style()
        self.build()
        self.after(60, self.poll_events)

    def setup_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            ".",
            background=PANEL,
            foreground=TEXT,
            fieldbackground=BG,
            font=("Segoe UI", 10),
        )
        style.configure("TFrame", background=PANEL)
        style.configure("Bg.TFrame", background=BG)
        style.configure("TLabel", background=PANEL, foreground=TEXT)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Result.TLabel", font=("Segoe UI", 15, "bold"))
        style.configure(
            "TEntry",
            fieldbackground=BG,
            foreground=TEXT,
            insertcolor=TEXT,
            bordercolor=PANEL_2,
        )
        style.configure(
            "TButton",
            background=PANEL_2,
            foreground=TEXT,
            bordercolor=PANEL_2,
            padding=(12, 6),
        )
        style.map("TButton", background=[("active", ACCENT), ("disabled", PANEL)])
        style.configure("Accent.TButton", background=ACCENT)
        style.configure("TCheckbutton", background=PANEL, foreground=TEXT)
        style.configure(
            "TSpinbox", fieldbackground=BG, foreground=TEXT, arrowcolor=TEXT
        )
        style.configure(
            "Horizontal.TProgressbar",
            background=ACCENT,
            troughcolor=PANEL_2,
            bordercolor=PANEL_2,
        )
        style.configure(
            "Treeview",
            background=BG,
            fieldbackground=BG,
            foreground=TEXT,
            rowheight=26,
            bordercolor=PANEL_2,
        )
        style.configure("Treeview.Heading", background=PANEL_2, foreground=TEXT)
        style.map("Treeview", background=[("selected", ACCENT)])

    def build(self) -> None:
        root = ttk.Frame(self, style="Bg.TFrame", padding=14)
        root.pack(fill="both", expand=True)

        top = ttk.Frame(root, padding=16)
        top.pack(fill="x")
        self.scan_button = ScanButton(top, self.start_scan)
        self.scan_button.pack(side="left", padx=(0, 20))
        info = ttk.Frame(top)
        info.pack(side="left", fill="both", expand=True)
        self.title_label = ttk.Label(
            info, text="Seu site aparece no Google?", style="Title.TLabel"
        )
        self.title_label.pack(anchor="w")
        self.subtitle = ttk.Label(
            info,
            text="Digite o endereço e clique em ESCANEAR.",
            style="Muted.TLabel",
        )
        self.subtitle.pack(anchor="w", pady=(0, 8))
        ttk.Label(info, text="Endereço do site").pack(anchor="w")
        self.url = ttk.Entry(info)
        self.url.pack(fill="x", pady=(2, 6))
        self.url.bind("<Return>", lambda _: self.start_scan())
        ttk.Label(info, text="Palavra-chave (opcional)").pack(anchor="w")
        self.keyword = ttk.Entry(info)
        self.keyword.pack(fill="x", pady=(2, 8))
        self.progress = ttk.Progressbar(info, maximum=100)
        self.progress.pack(fill="x")
        self.step = ttk.Label(info, text="", style="Muted.TLabel")
        self.step.pack(anchor="w", pady=(4, 0))

        middle = ttk.Frame(root, padding=16)
        middle.pack(fill="both", expand=True, pady=12)
        head = ttk.Frame(middle)
        head.pack(fill="x")
        self.result = ttk.Label(
            head, text="Nenhum escaneamento ainda.", style="Result.TLabel"
        )
        self.result.pack(side="left")
        self.fix_all_button = ttk.Button(
            head,
            text="🛠 Corrigir todos",
            style="Accent.TButton",
            command=self.fix_all,
            state="disabled",
        )
        self.fix_all_button.pack(side="right")
        self.fix_button = ttk.Button(
            head,
            text="Corrigir selecionado",
            command=self.fix_selected,
            state="disabled",
        )
        self.fix_button.pack(side="right", padx=6)

        table = ttk.Frame(middle)
        table.pack(fill="both", expand=True, pady=(10, 0))
        self.tree = ttk.Treeview(
            table,
            columns=("status", "item", "detail"),
            show="headings",
            selectmode="browse",
        )
        for column, title, width in (
            ("status", "Status", 90),
            ("item", "Item", 260),
            ("detail", "Detalhe", 520),
        ):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, stretch=column == "detail")
        for status, color in COLORS.items():
            self.tree.tag_configure(status, foreground=color)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _: self.fix_selected())

        bottom = ttk.Frame(root, padding=16)
        bottom.pack(fill="x")
        row = ttk.Frame(bottom)
        row.pack(fill="x")
        self.monitoring = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            row,
            text="🛡 Monitorar continuamente a cada",
            variable=self.monitoring,
            command=self.toggle_monitor,
        ).pack(side="left")
        self.interval = tk.IntVar(value=30)
        ttk.Spinbox(
            row, from_=5, to=1440, increment=5, width=6, textvariable=self.interval
        ).pack(side="left", padx=6)
        ttk.Label(
            row,
            text="minutos (deixe o programa aberto ou minimizado)",
            style="Muted.TLabel",
        ).pack(side="left")
        self.monitor_status = ttk.Label(
            bottom, text="Monitoramento desligado.", style="Muted.TLabel"
        )
        self.monitor_status.pack(anchor="w", pady=(6, 4))
        self.alerts = tk.Listbox(
            bottom, height=4, bg=BG, fg=TEXT, borderwidth=0, highlightthickness=0
        )
        self.alerts.pack(fill="x")

    def start_scan(self) -> None:
        url = self.url.get().strip()
        if self.scanning:
            return
        if not url:
            messagebox.showinfo("Analisador de SEO", "Digite o endereço do site.")
            self.url.focus_set()
            return
        self.scanning = True
        self.scan_button.set_progress(1)
        self.progress["value"] = 1
        self.title_label.configure(text="Escaneando…")
        self.subtitle.configure(
            text="Verificando tudo o que o Google avalia no seu site."
        )
        threading.Thread(
            target=scan_worker, args=(url, self.keyword.get(), self.events), daemon=True
        ).start()

    def poll_events(self) -> None:
        try:
            while True:
                self.handle_event(self.events.get_nowait())
        except queue.Empty:
            pass
        self.after(60, self.poll_events)

    def handle_event(self, event: dict) -> None:
        if event["type"] == "step":
            self.progress["value"] = event["progress"]
            self.scan_button.set_progress(event["progress"])
            self.step.configure(text=event["label"])
            return
        self.scanning = False
        self.progress["value"] = 0
        self.step.configure(text="")
        self.scan_button.set_progress(None, "ESCANEAR\nDE NOVO")
        if event["type"] == "error":
            self.title_label.configure(text="Não foi possível escanear")
            self.subtitle.configure(text=event["message"])
            if self.from_monitor:
                self.add_alert(f"Site inacessível: {event['message']}", popup=True)
            else:
                messagebox.showerror("Analisador de SEO", event["message"])
        else:
            self.show_report(event["report"])
        self.from_monitor = False
        self.schedule_monitor()

    def show_report(self, report: dict) -> None:
        if self.from_monitor and self.previous:
            self.compare(self.previous, report)
        self.report = report
        self.previous = report
        problems = [c for c in report["checks"] if c["status"] != "ok"]
        order = {"erro": 0, "aviso": 1, "ok": 2}
        self.tree.delete(*self.tree.get_children())
        for index, c in enumerate(
            sorted(report["checks"], key=lambda c: (order[c["status"]], -c["weight"]))
        ):
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(STATUS_TEXT[c["status"]], c["label"], c["detail"]),
                tags=(c["status"], c["id"]),
            )
        count = len(problems)
        self.result.configure(
            text=(
                f"{count} problema{'s' if count != 1 else ''} encontrado{'s' if count != 1 else ''}"
                f" · Nota {report['score']}/100"
            )
        )
        self.title_label.configure(
            text="Seu site precisa de atenção"
            if problems
            else "Seu site está protegido"
        )
        self.subtitle.configure(
            text=f"{report['url']} · verificado às {time.strftime('%H:%M')}"
        )
        state = "normal" if problems else "disabled"
        self.fix_all_button.configure(state=state)
        self.fix_button.configure(state=state)

    def compare(self, before: dict, after: dict) -> None:
        old = {c["id"]: c["label"] for c in before["checks"] if c["status"] != "ok"}
        new = {c["id"]: c["label"] for c in after["checks"] if c["status"] != "ok"}
        for pid, label in new.items():
            if pid not in old:
                self.add_alert(f"Novo problema: {label}", popup=True)
        for pid, label in old.items():
            if pid not in new:
                self.add_alert(f"Problema resolvido: {label}")
        if after["score"] <= before["score"] - 5:
            self.add_alert(
                f"A nota caiu de {before['score']} para {after['score']}.", popup=True
            )

    def add_alert(self, message: str, popup: bool = False) -> None:
        self.alerts.insert(0, f"{time.strftime('%d/%m %H:%M')}  {message}")
        if popup:
            self.bell()
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.after(500, lambda: self.attributes("-topmost", False))
            messagebox.showwarning("Alerta do Analisador de SEO", message)

    def checks_to_fix(self, only_selected: bool) -> list[dict]:
        if not self.report:
            return []
        problems = [c for c in self.report["checks"] if c["status"] != "ok"]
        if not only_selected:
            return problems
        selected = self.tree.selection()
        if not selected:
            return []
        tags = self.tree.item(selected[0], "tags")
        return [c for c in problems if c["id"] in tags]

    def fix_selected(self) -> None:
        checks = self.checks_to_fix(only_selected=True)
        if not checks:
            messagebox.showinfo(
                "Analisador de SEO", "Selecione um problema (erro ou aviso) na lista."
            )
            return
        self.show_fixes(checks)

    def fix_all(self) -> None:
        self.show_fixes(self.checks_to_fix(only_selected=False))

    def show_fixes(self, checks: list[dict]) -> None:
        window = tk.Toplevel(self)
        window.title("Como corrigir")
        window.geometry("760x560")
        window.configure(bg=BG)
        text = tk.Text(
            window,
            wrap="word",
            bg=BG,
            fg=TEXT,
            insertbackground=TEXT,
            padx=14,
            pady=14,
            borderwidth=0,
        )
        text.tag_configure("title", font=("Segoe UI", 12, "bold"))
        text.tag_configure("code", font=("Consolas", 10), background=PANEL_2)
        for c in checks:
            text.insert("end", f"{STATUS_TEXT[c['status']]} — {c['label']}\n", "title")
            text.insert("end", f"{c['hint']}\n")
            if c["fix"]:
                text.insert("end", f"{c['fix']}\n", "code")
            text.insert("end", "\n")
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)
        content = text.get("1.0", "end")

        def copy() -> None:
            self.clipboard_clear()
            self.clipboard_append(content)
            copy_button.configure(text="Copiado!")

        copy_button = ttk.Button(window, text="Copiar tudo", command=copy)
        copy_button.pack(pady=8)

    def toggle_monitor(self) -> None:
        if self.monitoring.get():
            if not self.url.get().strip():
                self.monitoring.set(False)
                messagebox.showinfo(
                    "Analisador de SEO",
                    "Digite o endereço do site antes de ligar o monitoramento.",
                )
                return
            self.add_alert(f"Monitoramento ligado para {self.url.get().strip()}")
            if not self.scanning:
                self.from_monitor = self.previous is not None
                self.start_scan()
        else:
            if self.monitor_job:
                self.after_cancel(self.monitor_job)
                self.monitor_job = None
            self.monitor_status.configure(text="Monitoramento desligado.")
            self.add_alert("Monitoramento desligado")

    def schedule_monitor(self) -> None:
        if self.monitor_job:
            self.after_cancel(self.monitor_job)
            self.monitor_job = None
        if not self.monitoring.get():
            return
        try:
            minutes = max(5, int(self.interval.get()))
        except (tk.TclError, ValueError):
            minutes = 30
        next_run = time.strftime("%H:%M", time.localtime(time.time() + minutes * 60))
        self.monitor_status.configure(
            text=f"🛡 Vigiando o site. Próxima verificação às {next_run}."
        )
        self.monitor_job = self.after(minutes * 60_000, self.monitor_tick)

    def monitor_tick(self) -> None:
        self.monitor_job = None
        if self.monitoring.get() and not self.scanning:
            self.from_monitor = True
            self.start_scan()


if __name__ == "__main__":
    App().mainloop()

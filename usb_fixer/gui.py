"""The tkinter window. Scan and fixes run in a worker thread; results come back through a queue."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import backup, fixes, report, strings
from .diagnostics import scan
from .system import is_admin, relaunch_as_admin

FONT = ("Tahoma", 10)
UI = strings.UI
SEV_COLOR = {"error": "#b00020", "warn": "#b26a00", "info": "#1565c0"}


class App(tk.Tk):
    def __init__(self, runner, demo: bool = False):
        super().__init__()
        self.runner = runner
        self.demo = demo
        self.admin = demo or is_admin()
        self.result = None
        self.findings: list = []
        self.checked: dict = {}  # tree iid -> bool
        self.jobs: queue.Queue = queue.Queue()

        self.title(UI["app_title"] + (" (دمو)" if demo else ""))
        self.geometry("980x720")
        self.option_add("*Font", FONT)
        self._build()
        self.after(100, self._poll)
        self.start_scan()

    # ---------- layout ----------
    def _build(self) -> None:
        if not self.admin:
            bar = tk.Frame(self, bg="#fff3cd")
            bar.pack(fill="x")
            tk.Button(bar, text=UI["admin_button"], command=self.on_admin).pack(side="left", padx=8, pady=6)
            tk.Label(bar, text=UI["admin_banner"], bg="#fff3cd", anchor="e", justify="right").pack(
                side="right", padx=8, fill="x", expand=True
            )

        tools = tk.Frame(self)
        tools.pack(fill="x", padx=8, pady=6)
        self.btn_scan = tk.Button(tools, text=UI["scan"], command=self.start_scan)
        self.btn_fix = tk.Button(tools, text=UI["fix"], command=self.on_fix)
        self.btn_undo = tk.Button(tools, text=UI["undo"], command=self.on_undo)
        self.btn_save = tk.Button(tools, text=UI["save_report"], command=self.on_save)
        for b in (self.btn_scan, self.btn_fix, self.btn_undo, self.btn_save):
            b.pack(side="right", padx=4)
        self.status = tk.Label(tools, text="", anchor="w")
        self.status.pack(side="left")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8)

        # Findings tab
        tab = tk.Frame(self.nb)
        self.nb.add(tab, text=UI["tab_findings"])
        pane = ttk.PanedWindow(tab, orient="vertical")
        pane.pack(fill="both", expand=True)
        top = tk.Frame(pane)
        self.tree = ttk.Treeview(top, columns=("fix", "sev", "title"), show="headings", height=8, selectmode="browse")
        self.tree.heading("fix", text=UI["col_fix"])
        self.tree.heading("sev", text=UI["col_sev"])
        self.tree.heading("title", text=UI["col_title"])
        self.tree.column("fix", width=50, anchor="center", stretch=False)
        self.tree.column("sev", width=70, anchor="center", stretch=False)
        self.tree.column("title", width=760, anchor="e")
        self.tree.pack(fill="both", expand=True)
        for sev, color in SEV_COLOR.items():
            self.tree.tag_configure(sev, foreground=color)
        self.tree.bind("<ButtonRelease-1>", self.on_tree_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        pane.add(top, weight=1)
        self.detail = self._text(pane, height=10)
        pane.add(self.detail, weight=2)

        # Devices tab
        dev_tab = tk.Frame(self.nb)
        self.nb.add(dev_tab, text=UI["tab_devices"])
        self.dev_tree = ttk.Treeview(dev_tab, columns=("name", "status", "id"), show="headings")
        for col, label, width in (("name", UI["col_name"], 300), ("status", UI["col_status"], 120), ("id", UI["col_id"], 500)):
            self.dev_tree.heading(col, text=label)
            self.dev_tree.column(col, width=width)
        self.dev_tree.pack(fill="both", expand=True)

        # System tab
        self.sys_text = self._text(self.nb)
        self.nb.add(self.sys_text, text=UI["tab_system"])

        self.log_box = self._text(self, height=8)
        self.log_box.pack(fill="x", padx=8, pady=6)

    def _text(self, parent, height=10) -> tk.Text:
        t = tk.Text(parent, height=height, wrap="word", state="disabled", font=FONT)
        t.tag_configure("rtl", justify="right")
        t.tag_configure("h", font=("Tahoma", 10, "bold"), justify="right")
        t.tag_configure("link", foreground="#1565c0", underline=True, justify="right")
        return t

    def _write(self, box: tk.Text, lines: list, clear: bool = True) -> None:
        box.configure(state="normal")
        if clear:
            box.delete("1.0", "end")
        for text, tag in lines:
            box.insert("end", text + "\n", ("rtl", tag) if tag else ("rtl",))
        box.configure(state="disabled")
        box.see("end")

    def log(self, message: str) -> None:
        self._write(self.log_box, [(message, None)], clear=False)

    # ---------- background work ----------
    def _run_bg(self, work, done) -> None:
        def target():
            try:
                self.jobs.put((done, work(), None))
            except Exception as exc:  # shown to the user, not swallowed
                self.jobs.put((done, None, exc))

        self._busy(True)
        threading.Thread(target=target, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                item = self.jobs.get_nowait()
                if item[0] is None:
                    self.log(item[1])
                else:
                    done, value, error = item
                    self._busy(False)
                    done(value, error)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for b in (self.btn_scan, self.btn_fix, self.btn_undo):
            b.configure(state=state)
        self.status.configure(text=UI["scanning"] if busy else "")

    # ---------- scan ----------
    def start_scan(self) -> None:
        self._run_bg(lambda: scan(self.runner), self.on_scan_done)

    def on_scan_done(self, result, error) -> None:
        if error:
            msg = f"{UI['scan_failed']} {error}"
            self.log(msg)
            messagebox.showerror(UI["app_title"], msg)
            return
        self.result = result
        self.findings = result.findings
        self.checked = {}
        self.tree.delete(*self.tree.get_children())
        for i, f in enumerate(self.findings):
            iid = str(i)
            on = bool(f.fix_id) and fixes.DEFAULT_CHECKED.get(f.fix_id, False)
            self.checked[iid] = on
            mark = ("☑" if on else "☐") if f.fix_id else ""
            self.tree.insert("", "end", iid=iid, values=(mark, strings.SEVERITY[f.severity], f.title), tags=(f.severity,))
        if self.findings:
            self.tree.selection_set("0")
        else:
            self._write(self.detail, [(UI["no_findings"], None)])

        self.dev_tree.delete(*self.dev_tree.get_children())
        for d in result.snapshot.devices:
            status = f"خطا {d.error_code}" if d.has_error else ("غایب" if d.is_ghost else d.status)
            self.dev_tree.insert("", "end", values=(d.name, status, d.instance_id))
        self._write(self.sys_text, [(line, None) for line in report.system_lines(result.snapshot)])
        for w in result.snapshot.warnings:
            self.log("⚠ " + w)

    # ---------- findings list ----------
    def on_tree_click(self, event) -> None:
        if self.tree.identify_region(event.x, event.y) != "cell" or self.tree.identify_column(event.x) != "#1":
            return
        iid = self.tree.identify_row(event.y)
        if iid and self.findings[int(iid)].fix_id:
            self.checked[iid] = not self.checked[iid]
            self.tree.set(iid, "fix", "☑" if self.checked[iid] else "☐")

    def on_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        f = self.findings[int(sel[0])]
        lines = [(f.title, "h"), (f.detail, None)]
        if f.fix_id:
            title, desc = strings.FIXES[f.fix_id]
            lines += [("", None), (UI["fix_header"], "h"), (f"{title}؛ {desc}", None)]
        if f.manual:
            lines += [("", None), (UI["manual_header"], "h")] + [("• " + m, None) for m in f.manual_texts]
        self._write(self.detail, lines)
        if f.links:
            self.detail.configure(state="normal")
            for label, url in f.links:
                start = self.detail.index("end-1c")
                self.detail.insert("end", label + "\n", ("rtl", "link"))
                tag = f"url{abs(hash(url))}"
                self.detail.tag_add(tag, start, "end-1c")
                self.detail.tag_bind(tag, "<Button-1>", lambda _e, u=url: webbrowser.open(u))
            self.detail.configure(state="disabled")

    # ---------- actions ----------
    def on_admin(self) -> None:
        if relaunch_as_admin():
            self.destroy()

    def on_fix(self) -> None:
        if not self.admin:
            messagebox.showwarning(UI["app_title"], UI["need_admin"])
            return
        chosen = [f for i, f in enumerate(self.findings) if self.checked.get(str(i)) and f.fix_id]
        steps = fixes.collect_steps(chosen)
        if not steps:
            messagebox.showinfo(UI["app_title"], UI["nothing_selected"])
            return
        shown = "\n".join("• " + s.shown[:160] for s in steps[:40])
        if len(steps) > 40:
            shown += f"\n… و {len(steps) - 40} مورد دیگه"
        if not messagebox.askyesno(UI["confirm_title"], f"{UI['confirm_intro']}\n\n{shown}\n\n{UI['confirm_question']}"):
            return
        self._run_bg(
            lambda: fixes.execute(steps, self.runner, lambda m: self.jobs.put((None, m, None))),
            self.on_fix_done,
        )

    def on_fix_done(self, result, error) -> None:
        if error:
            self.log(f"{UI['scan_failed']} {error}")
            return
        self.log(f"{UI['done']} (موفق: {result.ok}، ناموفق: {result.failed})")
        self.log(f"پشتیبان: {result.backup_dir}")
        self.start_scan()

    def on_undo(self) -> None:
        directory = backup.latest_undo_dir()
        if directory is None:
            messagebox.showinfo(UI["app_title"], UI["undo_none"])
            return
        if not self.admin:
            messagebox.showwarning(UI["app_title"], UI["need_admin"])
            return
        if not messagebox.askyesno(UI["confirm_title"], UI["undo_confirm"]):
            return
        self._run_bg(
            lambda: backup.undo(directory, self.runner, lambda m: self.jobs.put((None, m, None))),
            lambda failed, error: self.log(UI["undone"] if not error else f"{UI['scan_failed']} {error}"),
        )

    def on_save(self) -> None:
        if self.result is None:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt", initialfile="usb-report.txt", filetypes=[("Text", "*.txt")]
        )
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(report.build_report(self.result))
            self.log(f"{UI['report_saved']} {path}")


def run_gui(runner, demo: bool = False) -> None:
    App(runner, demo).mainloop()

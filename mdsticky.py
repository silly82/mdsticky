"""
mdsticky — Windows-Viewer im Sticky-Notes-Stil fuer org-artige TODOs in Markdown.

Eine .md-Datei = eine Haftnotiz. Klick auf die Checkbox schreibt TODO/DONE
zurueck in die Datei, alles andere in der Datei bleibt unveraendert.

    pythonw mdsticky.py                  Ordner aus der Konfiguration
    pythonw mdsticky.py C:\\Users\\ich\\Notizen

Keine Abhaengigkeiten ausser der Python-Standardbibliothek (tkinter).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mdtodo  # noqa: E402
import mdsticky_core  # noqa: E402

APP_NAME = "mdsticky"
POLL_MS = 1500

# --------------------------------------------------------------------------
# Farben — Windows-Sticky-Notes-Palette
# --------------------------------------------------------------------------

PALETTE = {
    "yellow": {"bg": "#FEF7A2", "head": "#FBE96B", "fg": "#1B1B1B", "mut": "#7A7245", "line": "#EBD86A"},
    "green":  {"bg": "#D5F4C4", "head": "#B6E89A", "fg": "#1B1B1B", "mut": "#5B7A4C", "line": "#BFE3A9"},
    "pink":   {"bg": "#FBD4E3", "head": "#F7ADC8", "fg": "#1B1B1B", "mut": "#87566B", "line": "#F0C0D3"},
    "purple": {"bg": "#E3D9FA", "head": "#C7B4F2", "fg": "#1B1B1B", "mut": "#655590", "line": "#D3C6EE"},
    "blue":   {"bg": "#CFE9FB", "head": "#9FD3F5", "fg": "#1B1B1B", "mut": "#4A6B82", "line": "#BCDCF0"},
    "gray":   {"bg": "#E9E9E9", "head": "#D2D2D2", "fg": "#1B1B1B", "mut": "#6A6A6A", "line": "#DCDCDC"},
    "charcoal": {"bg": "#3A3A3A", "head": "#2B2B2B", "fg": "#F2F2F2", "mut": "#A5A5A5", "line": "#4A4A4A"},
}
COLOR_LABELS = {
    "yellow": "Gelb", "green": "Gruen", "pink": "Rosa", "purple": "Lila",
    "blue": "Blau", "gray": "Grau", "charcoal": "Dunkel",
}
COLOR_ORDER = list(PALETTE)

PRIO_COLORS = {"A": "#D6483B", "B": "#E08A1E", "C": "#3E7CB1"}
OVERDUE = "#C4342A"
TODAY = "#B5651D"

MARKS_OPEN = {"TODO": "\u2610", "NEXT": "\u2610", "DOING": "\u25D1", "WAITING": "\u25CB", "SOMEDAY": "\u25CB"}
MARK_DONE = "\u2611"


def palette(name: str) -> dict:
    return PALETTE.get((name or "").lower(), PALETTE["yellow"])


# --------------------------------------------------------------------------
# Konfiguration
# --------------------------------------------------------------------------


def config_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    folder = os.path.join(base, APP_NAME)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "config.json")


def load_config() -> dict:
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    except Exception:
        cfg = {}
    cfg.setdefault("folder", "")
    cfg.setdefault("notes", {})
    cfg.setdefault("launcher_geom", "340x460+60+60")
    cfg.setdefault("launcher_visible", True)
    return cfg


def save_config(cfg: dict) -> None:
    try:
        with open(config_path(), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass


def open_externally(path: str) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def enable_dpi_awareness() -> float:
    """Scharfe Schrift auf HiDPI-Bildschirmen. Gibt den Tk-Scaling-Faktor zurueck."""
    if sys.platform != "win32":
        return 0.0
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
        try:
            dpi = ctypes.windll.user32.GetDpiForSystem()
        except Exception:
            dpi = 96
        return max(1.0, dpi / 72.0)
    except Exception:
        return 0.0


# --------------------------------------------------------------------------
# Notizfenster
# --------------------------------------------------------------------------


class NoteWindow(tk.Toplevel):
    def __init__(self, app: "App", path: str):
        super().__init__(app.root)
        self.app = app
        self.path = path
        self.note: mdtodo.Note | None = None
        self.mtime = -1.0
        self.conflicted = False
        self.editing = False
        self.editor_base = ""
        self.external_changed = False
        self.entry_visible = False
        self._drag = (0, 0)
        self._wrap_target: list[tuple[tk.Label, int]] = []

        state = app.cfg["notes"].setdefault(path, {})
        self.hide_done = bool(state.get("hide_done", True))
        self.topmost = bool(state.get("topmost", True))
        w = int(state.get("w", 320))
        h = int(state.get("h", 380))
        x = int(state.get("x", 120 + 30 * (len(app.windows) % 8)))
        y = int(state.get("y", 120 + 30 * (len(app.windows) % 8)))

        self.overrideredirect(True)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(220, 140)
        self.wm_attributes("-topmost", self.topmost)

        self.pal = palette("yellow")
        self.configure(bg=self.pal["bg"], highlightthickness=1,
                       highlightbackground=self.pal["line"])

        self._build()
        self.reload(force=True)

    # -- Aufbau ------------------------------------------------------------

    def _build(self) -> None:
        f = self.app.fonts

        self.head = tk.Frame(self, bg=self.pal["head"], height=30)
        self.head.pack(side="top", fill="x")
        self.head.pack_propagate(False)

        self.grip_label = tk.Label(self.head, text="\u2261", bg=self.pal["head"], fg=self.pal["mut"],
                                   font=f["icon"], padx=8, cursor="fleur")
        self.grip_label.pack(side="left")

        self.title_label = tk.Label(self.head, text="", bg=self.pal["head"], fg=self.pal["fg"],
                                    font=f["title"], anchor="w", cursor="fleur")
        self.title_label.pack(side="left", fill="x", expand=True)

        self.close_btn = self._head_button("\u2715", self.hide_note, "Notiz ausblenden")
        self.menu_btn = self._head_button("\u22EF", self.show_menu, "Menue")
        self.edit_btn = self._head_button("\u270e", self.toggle_editor, "Markdown bearbeiten")
        self.add_btn = self._head_button("\uFF0B", self.toggle_entry, "Neue Aufgabe")

        for widget in (self.head, self.title_label, self.grip_label):
            widget.bind("<Button-1>", self.start_drag)
            widget.bind("<B1-Motion>", self.do_drag)
            widget.bind("<ButtonRelease-1>", lambda e: self.app.remember(self))
            widget.bind("<Button-3>", self.show_menu)
            widget.bind("<Double-Button-1>", lambda e: self.toggle_collapse())

        # Scrollbarer Inhalt
        self.canvas = tk.Canvas(self, bg=self.pal["bg"], highlightthickness=0, bd=0,
                                width=200, height=80)
        self.canvas.pack(side="top", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=self.pal["bg"])
        self.body_id = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        for target in (self.canvas, self.body):
            target.bind("<MouseWheel>", self._on_wheel)
            target.bind("<Button-4>", self._on_wheel)
            target.bind("<Button-5>", self._on_wheel)

        self.editor = tk.Text(self, bg=self.pal["bg"], fg=self.pal["fg"],
                              insertbackground=self.pal["fg"], relief="flat",
                              wrap="none", undo=True, font=f["body"],
                              padx=10, pady=10)
        self.editor.bind("<Control-s>", self.save_editor)
        self.editor.bind("<Escape>", lambda e: self.cancel_editor())

        # Eingabe fuer neue Aufgaben
        self.entry_frame = tk.Frame(self, bg=self.pal["bg"])
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(self.entry_frame, textvariable=self.entry_var, font=f["body"],
                              bg=self.pal["bg"], fg=self.pal["fg"], relief="flat",
                              insertbackground=self.pal["fg"], highlightthickness=1,
                              highlightbackground=self.pal["line"], highlightcolor=self.pal["mut"])
        self.entry.pack(fill="x", padx=10, pady=(2, 8), ipady=4)
        self.entry.bind("<Return>", self.commit_entry)
        self.entry.bind("<Escape>", lambda e: self.toggle_entry())

        # Groessenanpassung unten rechts
        self.grip = tk.Frame(self, bg=self.pal["bg"], width=14, height=14, cursor="bottom_right_corner")
        self.grip.place(relx=1.0, rely=1.0, anchor="se")
        self.grip.bind("<Button-1>", self.start_resize)
        self.grip.bind("<B1-Motion>", self.do_resize)
        self.grip.bind("<ButtonRelease-1>", lambda e: self.app.remember(self))

    def _head_button(self, glyph: str, command, tooltip: str) -> tk.Label:
        btn = tk.Label(self.head, text=glyph, bg=self.pal["head"], fg=self.pal["mut"],
                       font=self.app.fonts["icon"], padx=8, cursor="hand2")
        btn.pack(side="right")
        btn.bind("<Button-1>", lambda e: command())
        btn.bind("<Enter>", lambda e: btn.configure(fg=self.pal["fg"]))
        btn.bind("<Leave>", lambda e: btn.configure(fg=self.pal["mut"]))
        return btn

    # -- Fensterinteraktion ------------------------------------------------

    def start_drag(self, event) -> None:
        self._drag = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def do_drag(self, event) -> None:
        self.geometry(f"+{event.x_root - self._drag[0]}+{event.y_root - self._drag[1]}")

    def start_resize(self, event) -> None:
        self._drag = (event.x_root - self.winfo_width(), event.y_root - self.winfo_height())

    def do_resize(self, event) -> None:
        w = max(220, event.x_root - self._drag[0])
        h = max(140, event.y_root - self._drag[1])
        self.geometry(f"{w}x{h}")

    def toggle_collapse(self) -> None:
        if self.canvas.winfo_ismapped():
            self._restore_h = self.winfo_height()
            self.canvas.pack_forget()
            self.entry_frame.pack_forget()
            self.grip.place_forget()
            self.geometry(f"{self.winfo_width()}x30")
        else:
            self.canvas.pack(side="top", fill="both", expand=True)
            self.grip.place(relx=1.0, rely=1.0, anchor="se")
            self.geometry(f"{self.winfo_width()}x{getattr(self, '_restore_h', 380)}")

    def hide_note(self) -> None:
        self.app.set_visible(self.path, False)

    def _on_canvas_resize(self, event) -> None:
        self.canvas.itemconfigure(self.body_id, width=event.width)
        for item in list(self._wrap_target):
            label, indent = item
            try:
                label.configure(wraplength=max(90, event.width - 66 - indent))
            except tk.TclError:
                self._wrap_target.remove(item)

    def _on_wheel(self, event) -> str:
        delta = -1 if getattr(event, "num", 0) == 5 or getattr(event, "delta", 0) < 0 else 1
        self.canvas.yview_scroll(-delta * 2, "units")
        return "break"

    def toggle_entry(self) -> None:
        self.entry_visible = not self.entry_visible
        if self.entry_visible:
            self.entry_frame.pack(side="bottom", fill="x", before=self.canvas)
            self.focus_force()
            self.entry.focus_set()
        else:
            self.entry_frame.pack_forget()
            self.entry_var.set("")

    def commit_entry(self, event=None) -> None:
        text = self.entry_var.get().strip()
        if text:
            mdtodo.add_task(self.path, text)
            self.entry_var.set("")
            self.reload(force=True)
        else:
            self.toggle_entry()

    def toggle_editor(self) -> None:
        if self.conflicted and not self.editing:
            messagebox.showwarning(APP_NAME, "Diese Notiz enthält ungelöste Konfliktmarker.")
            return
        if self.editing:
            self.save_editor()
            return
        current = mdsticky_core.load_text(self.path)
        base_path = mdsticky_core.base_path_for(self.path)
        self.editor_base = mdsticky_core.load_text(base_path) or current
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", current)
        self.editing = True
        self.external_changed = False
        self.canvas.pack_forget()
        self.entry_frame.pack_forget()
        self.editor.pack(side="top", fill="both", expand=True)
        self.edit_btn.configure(text="\u2714")
        self.editor.focus_set()

    def cancel_editor(self) -> None:
        if not self.editing:
            return
        self.editing = False
        self.editor.pack_forget()
        self.canvas.pack(side="top", fill="both", expand=True)
        self.edit_btn.configure(text="\u270e")
        self.editor_base = ""

    def save_editor(self, event=None) -> str:
        if not self.editing:
            return "break"
        local = self.editor.get("1.0", "end-1c")
        result = mdsticky_core.save_with_merge(self.path, self.editor_base, local)
        if result.has_conflicts:
            self.conflicted = True
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", result.text)
            messagebox.showwarning(APP_NAME, "Konflikt erkannt. Bitte die Marker im Editor bearbeiten.")
            return "break"
        self.cancel_editor()
        self.reload(force=True)
        return "break"

    # -- Menue -------------------------------------------------------------

    def show_menu(self, event=None) -> None:
        menu = tk.Menu(self, tearoff=0, font=self.app.fonts["body"])
        colors = tk.Menu(menu, tearoff=0, font=self.app.fonts["body"])
        for key in COLOR_ORDER:
            colors.add_command(label=COLOR_LABELS[key], command=lambda k=key: self.set_color(k))
        menu.add_cascade(label="Farbe", menu=colors)
        self._var_hide = tk.BooleanVar(value=self.hide_done)
        self._var_top = tk.BooleanVar(value=self.topmost)
        menu.add_checkbutton(label="Erledigte ausblenden", variable=self._var_hide,
                             command=self.toggle_hide_done)
        menu.add_checkbutton(label="Immer im Vordergrund", variable=self._var_top,
                             command=self.toggle_topmost)
        menu.add_separator()
        menu.add_command(label="Datei oeffnen", command=lambda: open_externally(self.path))
        menu.add_command(label="Ordner oeffnen", command=lambda: open_externally(os.path.dirname(self.path)))
        menu.add_command(label="Neu laden", command=lambda: self.reload(force=True))
        menu.add_separator()
        menu.add_command(label="Uebersicht anzeigen", command=self.app.show_launcher)
        menu.add_command(label="Notiz ausblenden", command=self.hide_note)
        x = event.x_root if event else self.winfo_x() + 40
        y = event.y_root if event else self.winfo_y() + 30
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def set_color(self, key: str) -> None:
        mdtodo.set_meta(self.path, "color", key)
        self.reload(force=True)

    def toggle_hide_done(self) -> None:
        self.hide_done = not self.hide_done
        self.app.cfg["notes"][self.path]["hide_done"] = self.hide_done
        save_config(self.app.cfg)
        self.render()

    def toggle_topmost(self) -> None:
        self.topmost = not self.topmost
        self.wm_attributes("-topmost", self.topmost)
        self.app.cfg["notes"][self.path]["topmost"] = self.topmost
        save_config(self.app.cfg)

    # -- Daten -------------------------------------------------------------

    def reload(self, force: bool = False) -> None:
        if not os.path.exists(self.path):
            self.app.drop(self.path)
            return
        mtime = os.path.getmtime(self.path)
        if not force and mtime == self.mtime:
            return
        if self.editing and not force:
            self.external_changed = True
            return
        self.mtime = mtime
        text = mdsticky_core.load_text(self.path)
        self.conflicted = mdsticky_core.contains_conflict_markers(text)
        base_path = mdsticky_core.base_path_for(self.path)
        if not self.conflicted and not base_path.exists():
            mdsticky_core.write_base_snapshot(self.path, text)
        self.note = mdtodo.parse_note(self.path)
        self.apply_palette(palette(self.note.color))
        self.render()

    def apply_palette(self, pal: dict) -> None:
        self.pal = pal
        self.configure(bg=pal["bg"])
        self.canvas.configure(bg=pal["bg"])
        self.body.configure(bg=pal["bg"])
        self.head.configure(bg=pal["head"])
        self.entry_frame.configure(bg=pal["bg"])
        self.grip.configure(bg=pal["bg"])
        self.entry.configure(bg=pal["bg"], fg=pal["fg"], insertbackground=pal["fg"],
                             highlightbackground=pal["line"], highlightcolor=pal["mut"])
        self.title_label.configure(bg=pal["head"], fg=pal["fg"])
        for btn in (self.grip_label, self.close_btn, self.menu_btn, self.edit_btn, self.add_btn):
            btn.configure(bg=pal["head"], fg=pal["mut"])

    def render(self) -> None:
        try:
            top = self.canvas.yview()[0]
        except tk.TclError:
            top = 0.0
        for child in self.body.winfo_children():
            child.destroy()
        self._wrap_target = []
        if self.note is None:
            return

        pal, f = self.pal, self.app.fonts
        tasks = self.note.tasks
        open_count = len(self.note.open_tasks)
        conflict_title = "   KONFLIKT" if self.conflicted else ""
        self.title_label.configure(text=f"  {self.note.title}   {open_count}/{len(tasks)}{conflict_title}")

        if self.conflicted:
            tk.Label(self.body, text="Konflikt erkannt — bitte Marker im Editor entfernen.",
                     bg="#F4C7C3", fg="#7A1710", font=f["body"], anchor="w",
                     justify="left", wraplength=max(150, self.winfo_width() - 24)).pack(
                         fill="x", padx=10, pady=10)

        shown = self.note.display_order(include_done=not self.hide_done)
        if not shown:
            tk.Label(self.body, text="Nichts offen.", bg=pal["bg"], fg=pal["mut"],
                     font=f["body"], anchor="w").pack(fill="x", padx=16, pady=16)
            return

        last_section = object()
        for task in shown:
            if task.section != last_section:
                last_section = task.section
                if task.section:
                    tk.Label(self.body, text=task.section.upper(), bg=pal["bg"], fg=pal["mut"],
                             font=f["section"], anchor="w").pack(fill="x", padx=14, pady=(10, 2))
            self._render_task(task)

        tk.Frame(self.body, bg=pal["bg"], height=10).pack(fill="x")
        self.after_idle(lambda: self.canvas.yview_moveto(top))

    def _render_task(self, task: mdtodo.Task) -> None:
        pal, f = self.pal, self.app.fonts

        indent = 16 * min(task.level, 4)
        row = tk.Frame(self.body, bg=pal["bg"])
        row.pack(fill="x", padx=(8 + indent, 8), pady=1)

        stripe = tk.Frame(row, bg=PRIO_COLORS.get(task.priority or "", pal["bg"]), width=3)
        stripe.pack(side="left", fill="y", padx=(0, 4))

        mark = MARK_DONE if task.done else MARKS_OPEN.get(task.keyword, "\u2610")
        if task.level:
            tk.Frame(row, bg=pal["line"], width=1).pack(side="left", fill="y", padx=(0, 6))
        box = tk.Label(row, text=mark, bg=pal["bg"], fg=pal["mut"] if task.done else pal["fg"],
                       font=f["box"], cursor="hand2", padx=2)
        box.pack(side="left", anchor="n", pady=1)
        box.bind("<Button-1>", lambda e, t=task: self.on_toggle(t))

        text_col = tk.Frame(row, bg=pal["bg"])
        text_col.pack(side="left", fill="x", expand=True)

        title_font = f["strike"] if task.done else f["body"]
        title = tk.Label(text_col, text=task.title, bg=pal["bg"],
                         fg=pal["mut"] if task.done else pal["fg"], font=title_font,
                         anchor="w", justify="left",
                         wraplength=max(90, self.winfo_width() - 66 - indent))
        title.pack(fill="x")
        self._wrap_target.append((title, indent))

        meta = self._meta_text(task)
        if meta:
            meta_label = tk.Label(text_col, text=meta[0], bg=pal["bg"], fg=meta[1],
                                  font=f["meta"], anchor="w", justify="left")
            meta_label.pack(fill="x")

        for widget in (row, text_col, title):
            widget.bind("<Button-3>", lambda e, t=task: self.task_menu(e, t))
            widget.bind("<MouseWheel>", self._on_wheel)
            widget.bind("<Double-Button-1>", lambda e: open_externally(self.path))

    def _meta_text(self, task: mdtodo.Task) -> tuple[str, str] | None:
        pal = self.pal
        bits: list[str] = []
        color = pal["mut"]

        if task.due and not task.done:
            days = task.days_left()
            label = {0: "heute", 1: "morgen", -1: "gestern"}.get(days)
            if label is None:
                if -7 < days < 0:
                    label = f"{-days} Tage ueberfaellig"
                elif 0 < days < 7:
                    label = task.due.strftime("%a, %d.%m.")
                else:
                    label = task.due.strftime("%d.%m.%Y")
            prefix = "Frist" if task.deadline and task.due == task.deadline else "Geplant"
            bits.append(f"{prefix}: {label}")
            if days is not None and days < 0:
                color = OVERDUE
            elif days == 0:
                color = TODAY
        if task.keyword == "WAITING":
            bits.append("wartet")
        if task.tags:
            bits.append(" ".join("#" + t for t in task.tags))

        return ("   ".join(bits), color) if bits else None

    def task_menu(self, event, task: mdtodo.Task) -> None:
        menu = tk.Menu(self, tearoff=0, font=self.app.fonts["body"])
        menu.add_command(label="Erledigt umschalten", command=lambda: self.on_toggle(task))
        menu.add_command(label="Text kopieren", command=lambda: self._copy(task.title))
        menu.add_separator()
        menu.add_command(label=f"Zeile {task.line_no + 1} in der Datei", state="disabled")
        menu.add_command(label="Datei oeffnen", command=lambda: open_externally(self.path))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _copy(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)

    def on_toggle(self, task: mdtodo.Task) -> None:
        if self.conflicted:
            messagebox.showwarning(APP_NAME, "Diese Notiz enthält ungelöste Konfliktmarker.")
            return
        try:
            base_path = mdsticky_core.base_path_for(self.path)
            base = mdsticky_core.load_text(base_path)
            if not base:
                base = mdsticky_core.load_text(self.path)
            with tempfile.TemporaryDirectory(prefix="mdsticky-toggle-") as temp_dir:
                temp_path = os.path.join(temp_dir, os.path.basename(self.path))
                with open(temp_path, "w", encoding="utf-8", newline="") as handle:
                    handle.write(mdsticky_core.load_text(self.path))
                if not mdtodo.toggle_task(temp_path, task.line_no):
                    return
                local = mdsticky_core.load_text(temp_path)
            result = mdsticky_core.save_with_merge(self.path, base, local)
            if result.has_conflicts:
                self.conflicted = True
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Datei konnte nicht geschrieben werden:\n{exc}")
            return
        self.reload(force=True)


# --------------------------------------------------------------------------
# Uebersichtsfenster
# --------------------------------------------------------------------------


class Launcher:
    def __init__(self, app: "App"):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title(f"{APP_NAME} — Notizen")
        self.win.configure(bg="#F6F6F6")
        self.win.geometry(app.cfg.get("launcher_geom") or "340x460+60+60")
        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        self.vars: dict[str, tk.BooleanVar] = {}

        f = app.fonts
        top = tk.Frame(self.win, bg="#F6F6F6")
        top.pack(fill="x", padx=12, pady=(12, 6))
        self.folder_label = tk.Label(top, text="", bg="#F6F6F6", fg="#555555", font=f["meta"],
                                     anchor="w", wraplength=300, justify="left")
        self.folder_label.pack(fill="x")

        buttons = tk.Frame(self.win, bg="#F6F6F6")
        buttons.pack(fill="x", padx=12, pady=(0, 8))
        for text, cmd in (("Ordner waehlen", self.choose_folder),
                          ("Aktualisieren", lambda: app.refresh(force=True)),
                          ("Alle anzeigen", self.show_all)):
            tk.Button(buttons, text=text, command=cmd, font=f["meta"], relief="flat",
                      bg="#E4E4E4", activebackground="#D4D4D4", padx=8, pady=3,
                      cursor="hand2").pack(side="left", padx=(0, 6))

        self.list_frame = tk.Frame(self.win, bg="#FFFFFF", highlightthickness=1,
                                   highlightbackground="#DDDDDD")
        self.list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        bottom = tk.Frame(self.win, bg="#F6F6F6")
        bottom.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(bottom, text="Uebersicht ausblenden", command=self.hide, font=f["meta"],
                  relief="flat", bg="#E4E4E4", padx=8, pady=3, cursor="hand2").pack(side="left")
        tk.Button(bottom, text="Beenden", command=app.quit, font=f["meta"], relief="flat",
                  bg="#E4E4E4", padx=8, pady=3, cursor="hand2").pack(side="right")

    def hide(self) -> None:
        self.app.cfg["launcher_geom"] = self.win.geometry()
        self.app.cfg["launcher_visible"] = False
        save_config(self.app.cfg)
        self.win.withdraw()

    def show(self) -> None:
        self.app.cfg["launcher_visible"] = True
        save_config(self.app.cfg)
        self.win.deiconify()
        self.win.lift()

    def choose_folder(self) -> None:
        folder = filedialog.askdirectory(title="Notizordner waehlen",
                                         initialdir=self.app.cfg.get("folder") or os.path.expanduser("~"))
        if folder:
            self.app.set_folder(folder)

    def show_all(self) -> None:
        for path in list(self.app.paths):
            self.app.set_visible(path, True)
        self.rebuild()

    def rebuild(self) -> None:
        self.folder_label.configure(text=self.app.cfg.get("folder") or "Kein Ordner gewaehlt")
        for child in self.list_frame.winfo_children():
            child.destroy()
        self.vars.clear()

        if not self.app.paths:
            tk.Label(self.list_frame, text="Keine .md-Datei mit Aufgaben gefunden.",
                     bg="#FFFFFF", fg="#888888", font=self.app.fonts["meta"],
                     wraplength=280, justify="left").pack(padx=14, pady=14, anchor="w")
            return

        for path in self.app.paths:
            note = self.app.summaries.get(path)
            open_count = note[0] if note else 0
            total = note[1] if note else 0
            color = note[2] if note else "yellow"

            row = tk.Frame(self.list_frame, bg="#FFFFFF")
            row.pack(fill="x", padx=2, pady=1)
            tk.Frame(row, bg=palette(color)["head"], width=6).pack(side="left", fill="y")

            var = tk.BooleanVar(value=self.app.is_visible(path))
            self.vars[path] = var
            tk.Checkbutton(row, variable=var, bg="#FFFFFF", activebackground="#FFFFFF",
                           command=lambda p=path: self.app.set_visible(p, self.vars[p].get())
                           ).pack(side="left")

            name = os.path.relpath(path, self.app.cfg.get("folder") or os.path.dirname(path))
            tk.Label(row, text=name, bg="#FFFFFF", fg="#222222", font=self.app.fonts["body"],
                     anchor="w").pack(side="left", fill="x", expand=True)
            tk.Label(row, text=f"{open_count}/{total}", bg="#FFFFFF", fg="#888888",
                     font=self.app.fonts["meta"]).pack(side="right", padx=8)


# --------------------------------------------------------------------------
# Anwendung
# --------------------------------------------------------------------------


class App:
    def __init__(self, folder: str | None = None):
        scaling = enable_dpi_awareness()
        self.root = tk.Tk()
        self.root.withdraw()
        if scaling:
            self.root.tk.call("tk", "scaling", scaling)

        self.cfg = load_config()
        if folder:
            self.cfg["folder"] = os.path.abspath(folder)

        self.fonts = self._build_fonts()
        self.windows: dict[str, NoteWindow] = {}
        self.paths: list[str] = []
        self.summaries: dict[str, tuple[int, int, str]] = {}

        self.launcher = Launcher(self)
        if not self.cfg.get("folder"):
            self.launcher.choose_folder()
        self.refresh(force=True)
        if not self.cfg.get("launcher_visible", True):
            self.launcher.win.withdraw()

        self.root.after(POLL_MS, self.tick)

    def _build_fonts(self) -> dict:
        family = "Segoe UI" if "Segoe UI" in tkfont.families() else "Helvetica"
        symbol = "Segoe UI Symbol" if "Segoe UI Symbol" in tkfont.families() else family
        return {
            "title": tkfont.Font(family=family, size=10, weight="bold"),
            "body": tkfont.Font(family=family, size=10),
            "strike": tkfont.Font(family=family, size=10, overstrike=True),
            "meta": tkfont.Font(family=family, size=8),
            "section": tkfont.Font(family=family, size=8, weight="bold"),
            "icon": tkfont.Font(family=symbol, size=10),
            "box": tkfont.Font(family=symbol, size=13),
        }

    # -- Notizen verwalten -------------------------------------------------

    def is_visible(self, path: str) -> bool:
        return bool(self.cfg["notes"].get(path, {}).get("visible", True))

    def set_visible(self, path: str, visible: bool) -> None:
        state = self.cfg["notes"].setdefault(path, {})
        state["visible"] = visible
        if visible and path not in self.windows:
            self.windows[path] = NoteWindow(self, path)
        elif not visible and path in self.windows:
            self.remember(self.windows[path])
            self.windows.pop(path).destroy()
        save_config(self.cfg)
        self.root.after_idle(self.launcher.rebuild)

    def remember(self, win: NoteWindow) -> None:
        state = self.cfg["notes"].setdefault(win.path, {})
        state.update(x=win.winfo_x(), y=win.winfo_y(),
                     w=win.winfo_width(), h=max(140, win.winfo_height()))
        save_config(self.cfg)

    def drop(self, path: str) -> None:
        win = self.windows.pop(path, None)
        if win:
            win.destroy()
        if path in self.paths:
            self.paths.remove(path)
        self.launcher.rebuild()

    def set_folder(self, folder: str) -> None:
        self.cfg["folder"] = folder
        save_config(self.cfg)
        for win in list(self.windows.values()):
            win.destroy()
        self.windows.clear()
        self.refresh(force=True)

    def refresh(self, force: bool = False) -> None:
        folder = self.cfg.get("folder")
        if not folder or not os.path.isdir(folder):
            self.paths = []
            self.launcher.rebuild()
            return

        found = []
        for found_path in mdsticky_core.scan_markdown_files(folder):
            # Configuration JSON requires string keys; the core deliberately
            # returns Path objects for filesystem-safe operations.
            path = os.fspath(found_path)
            try:
                note = mdtodo.parse_note(path)
            except OSError:
                continue
            found.append(path)
            self.summaries[path] = (len(note.open_tasks), len(note.tasks), note.color or "yellow")

        for path in list(self.windows):
            if path not in found:
                self.windows.pop(path).destroy()

        self.paths = found
        for path in found:
            if self.is_visible(path) and path not in self.windows:
                self.windows[path] = NoteWindow(self, path)
            elif force and path in self.windows:
                self.windows[path].reload(force=True)
        self.launcher.rebuild()

    def tick(self) -> None:
        try:
            for path, win in list(self.windows.items()):
                win.reload()
                if win.note:
                    self.summaries[path] = (len(win.note.open_tasks), len(win.note.tasks),
                                            win.note.color or "yellow")
            self._folder_check = getattr(self, "_folder_check", 0) + 1
            if self._folder_check % 10 == 0:
                self.refresh()
        except Exception:
            pass
        self.root.after(POLL_MS, self.tick)

    def show_launcher(self) -> None:
        self.launcher.show()
        self.launcher.rebuild()

    def quit(self) -> None:
        for win in self.windows.values():
            self.remember(win)
        save_config(self.cfg)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    folder = sys.argv[1] if len(sys.argv) > 1 else None
    app = App(folder)
    if not app.cfg.get("folder"):
        return 1
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

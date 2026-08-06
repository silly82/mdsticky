"""
mdtodo — org-artige TODOs in Markdown-Dateien lesen und schreiben.

Reines Textformat, keine Datenbank, keine Abhaengigkeiten ausser stdlib.
Wird von mdsticky.py (Windows-Viewer) benutzt, funktioniert aber auch
eigenstaendig als CLI:

    python mdtodo.py agenda  ~/Notizen
    python mdtodo.py list    ~/Notizen/arbeit.md
    python mdtodo.py toggle  ~/Notizen/arbeit.md 12
    python mdtodo.py add     ~/Notizen/arbeit.md "[#A] Kabel bestellen"
    python mdtodo.py newnote ~/Notizen                     (Assistent)
    python mdtodo.py newnote ~/Notizen "Zugerberg" -c blue -t "Switch tauschen" -t "- Konfig sichern"
"""

from __future__ import annotations

import datetime as dt
import os
import re
import sys
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Format
# --------------------------------------------------------------------------

OPEN_KEYWORDS = ["TODO", "NEXT", "DOING", "WAITING", "SOMEDAY"]
DONE_KEYWORDS = ["DONE", "CANCELLED"]
ALL_KEYWORDS = OPEN_KEYWORDS + DONE_KEYWORDS

# Aliase, damit org-Gewohnheiten und Logseq-Gewohnheiten beide funktionieren
KEYWORD_ALIASES = {
    "LATER": "TODO",
    "NOW": "DOING",
    "WAIT": "WAITING",
    "CANCELED": "CANCELLED",
    "STARTED": "DOING",
}

_KW_PATTERN = "|".join(sorted(set(ALL_KEYWORDS) | set(KEYWORD_ALIASES), key=len, reverse=True))

ITEM_RE = re.compile(
    r"^(?P<indent>[ \t]*)"
    r"(?P<bullet>[-*+][ \t]+|\#{1,6}[ \t]+)"
    r"(?:\[(?P<box>[ xX~/-])\][ \t]+)?"
    r"(?:(?P<kw>" + _KW_PATTERN + r")\b[ \t]*)?"
    r"(?P<rest>.*)$"
)

HEADING_RE = re.compile(r"^(?P<hashes>\#{1,6})[ \t]+(?P<text>.+?)[ \t]*$")
PRIO_RE = re.compile(r"\[#([ABCabc])\]")
ORG_TAGS_RE = re.compile(r"(?:^|[ \t])(:(?:[\w@%#-]+:)+)[ \t]*$")
HASH_TAGS_RE = re.compile(r"(?:^|\s)#([A-Za-z\u00c0-\u024f][\w\u00c0-\u024f/-]*)")
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
PLANNING_RE = re.compile(
    r"\b(SCHEDULED|DEADLINE|CLOSED)\s*:\s*[<\[](\d{4}-\d{2}-\d{2})[^>\]]*[>\]]"
)

WEEKDAYS_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# Notizfarben — identisch zur Palette des Viewers
COLORS = ["yellow", "green", "pink", "purple", "blue", "gray", "charcoal"]


def _stamp(date: dt.date, active: bool = True) -> str:
    """<2026-08-07 Fr> bzw. [2026-08-07 Fr]"""
    body = f"{date.isoformat()} {WEEKDAYS_DE[date.weekday()]}"
    return f"<{body}>" if active else f"[{body}]"


# --------------------------------------------------------------------------
# Datenmodell
# --------------------------------------------------------------------------


@dataclass
class Task:
    line_no: int  # 0-basiert, Zeile in der Datei
    keyword: str  # TODO / NEXT / DOING / WAITING / SOMEDAY / DONE / CANCELLED
    title: str  # Text ohne Keyword, Prioritaet und Tag-Suffix
    raw: str  # Originalzeile
    indent: str = ""
    bullet: str = "- "
    has_box: bool = False
    priority: str | None = None  # "A" | "B" | "C"
    tags: list[str] = field(default_factory=list)
    section: str | None = None  # naechstliegende Ueberschrift
    scheduled: dt.date | None = None
    deadline: dt.date | None = None
    closed: dt.date | None = None
    body_lines: list[int] = field(default_factory=list)  # Folgezeilen des Eintrags
    level: int = 0  # Einrueckungstiefe, 0 = Hauptpunkt
    parent: int | None = None  # line_no des uebergeordneten Eintrags

    @property
    def done(self) -> bool:
        return self.keyword in DONE_KEYWORDS

    @property
    def due(self) -> dt.date | None:
        if self.deadline and self.scheduled:
            return min(self.deadline, self.scheduled)
        return self.deadline or self.scheduled

    def days_left(self, today: dt.date | None = None) -> int | None:
        today = today or dt.date.today()
        return (self.due - today).days if self.due else None

    def sort_key(self, today: dt.date | None = None) -> tuple:
        today = today or dt.date.today()
        prio = {"A": 0, "B": 1, "C": 2}.get(self.priority or "", 3)
        kw = {"DOING": 0, "NEXT": 1, "TODO": 2, "WAITING": 3, "SOMEDAY": 4}.get(self.keyword, 5)
        days = self.days_left(today)
        overdue = 0 if (days is not None and days <= 0) else 1
        return (int(self.done), overdue, days if days is not None else 9999, prio, kw, self.line_no)


@dataclass
class Note:
    path: str
    title: str
    color: str
    tasks: list[Task]
    lines: list[str]
    mtime: float
    meta: dict = field(default_factory=dict)

    @property
    def open_tasks(self) -> list[Task]:
        return [t for t in self.tasks if not t.done]

    def display_order(self, include_done: bool = True) -> list[Task]:
        """Hauptpunkte sortiert, Unterpunkte in Dateireihenfolge direkt darunter.

        Ein erledigter Eintrag bleibt sichtbar, solange darunter noch etwas
        offen ist — sonst haetten die Unterpunkte keinen Anker mehr.
        """
        children: dict[int | None, list[Task]] = {}
        for task in self.tasks:
            children.setdefault(task.parent, []).append(task)

        result: list[Task] = []

        def has_open(task: Task) -> bool:
            if not task.done:
                return True
            return any(has_open(c) for c in children.get(task.line_no, []))

        def walk(task: Task) -> None:
            if not include_done and not has_open(task):
                return
            result.append(task)
            for child in children.get(task.line_no, []):
                walk(child)

        for root in sorted(children.get(None, []), key=lambda t: t.sort_key()):
            walk(root)
        return result


# --------------------------------------------------------------------------
# Parsen
# --------------------------------------------------------------------------


def _read_lines(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        text = fh.read()
    return text.splitlines()


def _parse_frontmatter(lines: list[str]) -> tuple[dict, int]:
    """Sehr einfaches YAML-artiges Frontmatter: nur key: value."""
    if not lines or lines[0].strip() != "---":
        return {}, 0
    meta: dict = {}
    for i in range(1, min(len(lines), 40)):
        if lines[i].strip() == "---":
            return meta, i + 1
        if ":" in lines[i]:
            k, _, v = lines[i].partition(":")
            meta[k.strip().lower()] = v.strip().strip("\"'")
    return {}, 0


def _extract_planning(text: str, task: Task) -> None:
    for kind, iso in PLANNING_RE.findall(text):
        try:
            date = dt.date.fromisoformat(iso)
        except ValueError:
            continue
        if kind == "SCHEDULED" and task.scheduled is None:
            task.scheduled = date
        elif kind == "DEADLINE" and task.deadline is None:
            task.deadline = date
        elif kind == "CLOSED" and task.closed is None:
            task.closed = date


def parse_note(path: str) -> Note:
    lines = _read_lines(path)
    meta, start = _parse_frontmatter(lines)

    title = meta.get("title") or ""
    color = (meta.get("color") or "").strip().lower()
    tasks: list[Task] = []
    section: str | None = None
    current: Task | None = None

    fence: str | None = None
    stack: list[tuple[int, Task]] = []

    for i in range(start, len(lines)):
        line = lines[i]
        stripped = line.strip()

        # Codebloecke sind Text, keine Aufgaben
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            current = None
            continue

        if not stripped:
            current = None
            continue

        m_item = ITEM_RE.match(line)
        is_task = False
        if m_item:
            kw = m_item.group("kw")
            box = m_item.group("box")
            is_task = bool(kw) or box is not None

        if not is_task:
            m_head = HEADING_RE.match(line)
            if m_head:
                section = m_head.group("text").strip()
                if not title and m_head.group("hashes") == "#":
                    title = section
                current = None
                stack.clear()
                continue
            # Fortsetzungszeile eines Eintrags (eingerueckt oder Planungszeile)
            if current is not None and (line[:1] in " \t" or PLANNING_RE.search(line)):
                current.body_lines.append(i)
                _extract_planning(line, current)
            else:
                current = None
            continue

        rest = m_item.group("rest").strip()
        kw = m_item.group("kw")
        box = m_item.group("box")

        if kw:
            keyword = KEYWORD_ALIASES.get(kw, kw)
        else:
            keyword = "DONE" if box in ("x", "X") else ("DOING" if box == "/" else "TODO")
        if box in ("x", "X") and keyword in OPEN_KEYWORDS:
            keyword = "DONE"

        task = Task(
            line_no=i,
            keyword=keyword,
            title=rest,
            raw=line,
            indent=m_item.group("indent"),
            bullet=m_item.group("bullet"),
            has_box=box is not None,
            section=section,
        )

        m_prio = PRIO_RE.search(rest)
        if m_prio:
            task.priority = m_prio.group(1).upper()
            rest = PRIO_RE.sub("", rest, count=1)

        m_tags = ORG_TAGS_RE.search(rest)
        if m_tags:
            task.tags = [t for t in m_tags.group(1).split(":") if t]
            rest = rest[: m_tags.start()]
        for tag in HASH_TAGS_RE.findall(rest):
            if tag not in task.tags:
                task.tags.append(tag)
        rest = HASH_TAGS_RE.sub(" ", rest)

        _extract_planning(rest, task)
        rest = PLANNING_RE.sub("", rest)
        task.title = " ".join(rest.split()).strip(" -–—")

        width = len(task.indent.expandtabs(4))
        while stack and stack[-1][0] >= width:
            stack.pop()
        if stack:
            task.parent = stack[-1][1].line_no
            task.level = stack[-1][1].level + 1
        stack.append((width, task))

        tasks.append(task)
        current = task

    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0.0

    if not title:
        title = os.path.splitext(os.path.basename(path))[0].replace("-", " ").replace("_", " ")

    return Note(path=path, title=title, color=color, tasks=tasks, lines=lines, mtime=mtime, meta=meta)


def scan_folder(folder: str, recursive: bool = True) -> list[str]:
    """Alle .md-Dateien, die mindestens einen Task enthalten — sortiert."""
    found: list[str] = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "assets")]
        for name in sorted(files):
            if name.lower().endswith((".md", ".markdown")):
                found.append(os.path.join(root, name))
        if not recursive:
            break
    return found


# --------------------------------------------------------------------------
# Schreiben — immer zeilenweise, alles Uebrige bleibt unangetastet
# --------------------------------------------------------------------------


def _detect_newline(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(8192)
        return "\r\n" if b"\r\n" in chunk else "\n"
    except OSError:
        return os.linesep


def _write_lines(path: str, lines: list[str]) -> None:
    nl = _detect_newline(path)
    tmp = path + ".mdsticky.tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(nl.join(lines) + nl)
    os.replace(tmp, path)


def toggle_task(path: str, line_no: int) -> bool:
    """TODO <-> DONE auf genau einer Zeile umschalten. True bei Erfolg."""
    lines = _read_lines(path)
    if not (0 <= line_no < len(lines)):
        return False

    line = lines[line_no]
    m = ITEM_RE.match(line)
    if not m or not (m.group("kw") or m.group("box") is not None):
        return False

    kw = m.group("kw")
    keyword = KEYWORD_ALIASES.get(kw, kw) if kw else None
    box = m.group("box")
    is_done = keyword in DONE_KEYWORDS if keyword else box in ("x", "X")
    today = dt.date.today()

    if kw:
        new_kw = "TODO" if is_done else "DONE"
        line = re.sub(r"\b" + re.escape(kw) + r"\b", new_kw, line, count=1)
    if box is not None:
        line = line.replace(f"[{box}]", "[ ]" if is_done else "[x]", 1)
    lines[line_no] = line

    # CLOSED-Zeile pflegen
    indent = m.group("indent") + "  "
    closed_at = line_no + 1
    has_closed = closed_at < len(lines) and re.search(r"\bCLOSED\s*:", lines[closed_at])
    if is_done:
        if has_closed:
            del lines[closed_at]
    else:
        if has_closed:
            lines[closed_at] = f"{indent}CLOSED: {_stamp(today, active=False)}"
        else:
            lines.insert(closed_at, f"{indent}CLOSED: {_stamp(today, active=False)}")

    _write_lines(path, lines)
    return True


def add_task(path: str, text: str, section: str | None = None) -> None:
    """Neuen TODO-Eintrag anhaengen — optional unter einer bestimmten Ueberschrift."""
    text = text.strip()
    if not text:
        return
    if not any(text.upper().startswith(k) for k in ALL_KEYWORDS):
        text = "TODO " + text

    lines = _read_lines(path) if os.path.exists(path) else []
    insert_at = len(lines)

    if section:
        target = section.strip().lower()
        for i, line in enumerate(lines):
            m = HEADING_RE.match(line)
            if m and m.group("text").strip().lower() == target:
                level = len(m.group("hashes"))
                insert_at = len(lines)
                for j in range(i + 1, len(lines)):
                    m2 = HEADING_RE.match(lines[j])
                    if m2 and len(m2.group("hashes")) <= level:
                        insert_at = j
                        break
                while insert_at > i + 1 and not lines[insert_at - 1].strip():
                    insert_at -= 1
                break

    lines.insert(insert_at, f"- {text}")
    _write_lines(path, lines)


def set_meta(path: str, key: str, value: str) -> None:
    """Frontmatter-Wert setzen (z. B. color) und Datei neu schreiben."""
    lines = _read_lines(path) if os.path.exists(path) else []
    meta, start = _parse_frontmatter(lines)
    entry = f"{key}: {value}"

    if start:
        for i in range(1, start - 1):
            if lines[i].split(":", 1)[0].strip().lower() == key.lower():
                lines[i] = entry
                break
        else:
            lines.insert(start - 1, entry)
    else:
        lines[0:0] = ["---", entry, "---", ""]

    _write_lines(path, lines)


def slugify(text: str) -> str:
    """Titel in einen brauchbaren Dateinamen verwandeln."""
    umlauts = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "à": "a", "á": "a",
               "â": "a", "è": "e", "é": "e", "ê": "e", "ë": "e", "î": "i",
               "ï": "i", "ô": "o", "ù": "u", "û": "u", "ç": "c", "ñ": "n"}
    out = "".join(umlauts.get(c, c) for c in text.lower())
    out = re.sub(r"[^a-z0-9]+", "-", out).strip("-")
    return out or "notiz"


def create_note(
    folder: str,
    title: str,
    color: str | None = None,
    tasks: list[str] | None = None,
    filename: str | None = None,
) -> str:
    """Neue Notizdatei anlegen und ihren Pfad zurueckgeben.

    Ein Eintrag in `tasks`, der mit '-' oder Leerzeichen beginnt, wird zum
    Unterpunkt des vorangehenden Eintrags.
    """
    title = title.strip()
    if not title:
        raise ValueError("Titel fehlt")
    if color:
        color = color.strip().lower()
        if color not in COLORS:
            raise ValueError(f"unbekannte Farbe: {color} (moeglich: {', '.join(COLORS)})")

    os.makedirs(folder, exist_ok=True)
    base = slugify(filename or title)
    path = os.path.join(folder, base + ".md")
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base}-{n}.md")
        n += 1

    lines = ["---", f"title: {title}"]
    if color:
        lines.append(f"color: {color}")
    lines += ["---", ""]

    for raw in tasks or []:
        text = raw.strip()
        if not text:
            continue
        sub = raw[:1] in " \t" or text.startswith("- ") or text.startswith("-\t")
        text = text.lstrip("- \t").strip()
        if not text:
            continue
        if not any(text.upper().startswith(k) for k in ALL_KEYWORDS):
            text = "TODO " + text
        lines.append(("  - " if sub else "- ") + text)

    _write_lines(path, lines)
    return path


def newnote_wizard(folder: str) -> str | None:
    """Kurzer Dialog auf der Konsole: Titel, Farbe, Punkte."""
    print(f"Neue Notiz in {os.path.abspath(folder)}\n")
    try:
        title = input("Titel: ").strip()
        if not title:
            print("Abgebrochen.")
            return None

        color = ""
        while True:
            color = input(f"Farbe [{'/'.join(COLORS)}] (Enter = ohne): ").strip().lower()
            if not color or color in COLORS:
                break
            print(f"  Unbekannt. Moeglich: {', '.join(COLORS)}")

        print("\nPunkte erfassen — leere Zeile beendet.")
        print('Mit "-" oder Leerzeichen davor wird daraus ein Unterpunkt.')
        print('Prioritaet [#A], Tags #tag und "SCHEDULED: <2026-08-07>" duerfen mit.\n')
        tasks: list[str] = []
        while True:
            line = input(f"{len(tasks) + 1:>2}> ")
            if not line.strip():
                break
            tasks.append(line)
    except (EOFError, KeyboardInterrupt):
        print("\nAbgebrochen.")
        return None

    path = create_note(folder, title, color or None, tasks)
    print(f"\\nAngelegt: {path}  ({len(tasks)} Punkte)")
    return path


def assist(target_path: str) -> int:
    """Interaktiver Assistent zum Anlegen oder Ergänzen von Notizen.

    * **Ordner‐Pfad** – Erstellt eine neue Notiz (wie ``newnote_wizard``),
      fragt nach Titel, optionaler Farbe und einer Reihe von Aufgaben.
    * **Datei‑Pfad** – Fügt einer bestehenden Markdown‑Datei neue Aufgaben
      hinzu. Der Assistent fragt nach einer Aufgabenbeschreibung und einem
      optionalen Planungs‑Datum (``SCHEDULED``).
    """
    # Wenn ``target_path`` eine existierende Datei ist, fügen wir eine einzelne
    # Aufgabe zu dieser Notiz hinzu (Add‑Modus). Das optionale Datum wird in die
    # gleiche Zeile eingebettet, sodass ``- TODO Aufgabe SCHEDULED: <2026‑08‑07>``
    # entsteht, anstatt separate ``SCHEDULED``‑Zeilen zu erzeugen.
    if os.path.isfile(target_path):
        print(f"Assistent: Aufgabe zu '{target_path}' hinzufügen\n")
        try:
            line = input("Aufgabe: ").strip()
            if not line:
                print("Abgebrochen – keine Aufgabe.")
                return 1
            date_input = input("   Datum (YYYY-MM-DD) oder leer für keine Planung: ").strip()
            if date_input:
                try:
                    dt.date.fromisoformat(date_input)
                except Exception:
                    print("   Ungültiges Datum – wird ignoriert.")
                    date_input = ""
            task_line = line
            if not any(task_line.upper().startswith(k) for k in ALL_KEYWORDS):
                task_line = f"TODO {task_line}"
            if date_input:
                task_line = f"{task_line} SCHEDULED: <{date_input}>"
            add_task(target_path, task_line)
            print("Aufgabe hinzugefügt.")
            return 0
        except (EOFError, KeyboardInterrupt):
            print("\nAbgebrochen.")
            return 1

    # Andernfalls behandeln wir den Pfad als Verzeichnis (oder als Dateipfad, bei dem
    # das übergeordnete Verzeichnis als Ziel verwendet wird) und erstellen eine neue Notiz.
    folder = target_path
    if os.path.splitext(target_path)[1].lower() in {".md", ".markdown"}:
        # Der Aufruf enthielt einen Dateinamen – wir ignorieren die Datei selbst
        # und legen die Notiz im übergeordneten Verzeichnis an.
        folder = os.path.dirname(target_path) or "."
    print(f"Assistent: Neue Notiz im Ordner {os.path.abspath(folder)}\n")
    try:
        title = input("Titel: ").strip()
        if not title:
            print("Abgebrochen – kein Titel.")
            return 1

        # Farbe auswählen (wie bei newnote_wizard)
        color = ""
        while True:
            col = input(f"Farbe [{'/'.join(COLORS)}] (Enter = ohne): ").strip().lower()
            if not col:
                break
            if col in COLORS:
                color = col
                break
            print(f"  Unbekannt. Möglich: {', '.join(COLORS)}")

        # Aufgaben erfassen
        tasks: list[str] = []
        idx = 1
        while True:
            line = input(f"{idx:>2}> (Leer = Ende): ").strip()
            if not line:
                break
            date_input = input("   Datum (YYYY-MM-DD) oder leer für keine Planung: ").strip()
            if date_input:
                try:
                    dt.date.fromisoformat(date_input)
                except Exception:
                    print("   Ungültiges Datum – wird ignoriert.")
                    date_input = ""
            task_line = line
            if not any(task_line.upper().startswith(k) for k in ALL_KEYWORDS):
                task_line = f"TODO {task_line}"
            # Embed the date in the same line if provided.
            if date_input:
                task_line = f"{task_line} SCHEDULED: <{date_input}>"
            tasks.append(f"- {task_line}")
            idx += 1

        if not tasks:
            print("Keine Aufgaben angegeben – Abbruch.")
            return 1

        # ``create_note`` legt die Datei anhand des Titels an (z. B. "5.md").
        # Wenn der Aufrufer jedoch einen konkreten Dateinamen (z. B.
        # "nd_beispiel_notiz5.md") angegeben hat, soll diese verwendet werden.
        # Wir prüfen, ob ``target_path`` eine nicht‑existierende *.md‑Datei war.
        explicit_path = None
        if os.path.splitext(target_path)[1].lower() in {".md", ".markdown"} and not os.path.isdir(target_path):
            # ``target_path`` ist ein Dateiname, der noch nicht existiert.
            explicit_path = os.path.abspath(target_path)

        path = create_note(folder, title, color or None, tasks)

        # Wenn ein expliziter Zielpfad angegeben wurde, benennen wir die Datei
        # um, sodass der gewünschte Name erhalten bleibt.
        if explicit_path:
            try:
                os.replace(path, explicit_path)
                path = explicit_path
            except OSError as exc:
                print(f"Fehler beim Umbenennen der Datei: {exc}")
                # Weiter mit dem ursprünglich erstellten Pfad.

        print(f"\nAngelegt: {path}  ({len(tasks)} Zeilen)")
        return 0
    except (EOFError, KeyboardInterrupt):
        print("\nAbgebrochen.")
        return 1


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _fmt(task: Task, with_file: str = "") -> str:
    marks = {"TODO": "[ ]", "NEXT": "[>]", "DOING": "[/]", "WAITING": "[~]",
             "SOMEDAY": "[?]", "DONE": "[x]", "CANCELLED": "[-]"}
    prio = f" ({task.priority})" if task.priority else ""
    due = ""
    if task.due:
        d = task.days_left()
        due = f"  {task.due.isoformat()}" + (f" ({d:+d}d)" if d is not None else "")
    tags = "  " + " ".join("#" + t for t in task.tags) if task.tags else ""
    head = f"{with_file}:" if with_file else ""
    return f"{head}{task.line_no + 1:>4}  {marks.get(task.keyword, '[ ]')}{prio} {task.title}{due}{tags}"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd, target = argv[0], argv[1]

    if cmd == "newnote":
        rest = argv[2:]
        if not rest:
            return 0 if newnote_wizard(target) else 1
        title = rest[0]
        color, tasks, i = None, [], 1
        while i < len(rest):
            arg = rest[i]
            if arg in ("-c", "--color") and i + 1 < len(rest):
                color, i = rest[i + 1], i + 2
            elif arg in ("-t", "--task") and i + 1 < len(rest):
                tasks.append(rest[i + 1])
                i += 2
            else:
                tasks.append(arg)
                i += 1
        try:
            path = create_note(target, title, color, tasks)
        except ValueError as exc:
            print(exc)
            return 1
        print(path)
        return 0

    # ----------------------------------------------------------------------
    # Assist – interaktiver Assistent zum Anlegen einer Notiz (neu eingeführt).
    # ----------------------------------------------------------------------
    if cmd == "assist":
        # ``assist`` kann ein Verzeichnis oder eine existierende Datei erhalten.
        # Bei einem Dateipfad nutzen wir das übergeordnete Verzeichnis, weil
        # die neue Notiz dort abgelegt werden soll.
        if os.path.isdir(target):
            folder = target
        elif os.path.isfile(target):
            folder = os.path.dirname(target)
        else:
            # Pfad existiert nicht – wir gehen davon aus, dass es ein neues
            # Verzeichnis sein soll und versuchen, es anzulegen.
            folder = target
        return assist(folder)

    if cmd in ("list", "agenda"):
        paths = scan_folder(target) if os.path.isdir(target) else [target]
        rows: list[tuple] = []
        for p in paths:
            note = parse_note(p)
            for t in note.tasks:
                if cmd == "agenda" and (t.done or t.due is None):
                    continue
                rows.append((t.sort_key(), t, os.path.basename(p)))
        rows.sort(key=lambda r: r[0])
        for _, t, name in rows:
            print(_fmt(t, name if len(paths) > 1 else ""))
        print(f"\n{len(rows)} Eintraege")
        return 0

    if cmd == "toggle":
        ok = toggle_task(target, int(argv[2]) - 1)
        print("ok" if ok else "keine Task-Zeile")
        return 0 if ok else 1

    if cmd == "add":
        add_task(target, " ".join(argv[2:]))
        print("hinzugefuegt")
        return 0

    print(f"unbekanntes Kommando: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

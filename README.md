# mdsticky 0.0.3

Plattformübergreifende TODOs als Markdown-Dateien im org-Stil, plus ein
Windows-Viewer im Sticky-Notes-Look. Eine `.md`-Datei ist eine Haftnotiz.

Als mdsticky-Notizen werden ausschließlich Dateien berücksichtigt, deren Name
mit `nd_` beginnt und auf `.md` endet, zum Beispiel `nd_test.md`.

- `mdtodo.py` — Parser und Writer, reine Standardbibliothek, auch als CLI nutzbar
- `mdsticky.py` — der Viewer (tkinter, randlose Notizfenster)
- `mdsticky_core.py` — getestete Kernfunktionen für Dateisuche, Basis-Snapshots,
  Konflikterkennung, Drei-Wege-Merge und Unified Diff

## Format

Org-Semantik, aber gültiges Markdown, damit Obsidian, Logseq, Markor und jeder
Texteditor die Dateien sauber anzeigen.

```markdown
---
title: Zugerberg Bahn
color: blue
---

## Netzwerk
- TODO [#A] VLAN 73 auf TSW202 prüfen  :netzwerk:sisag:
  SCHEDULED: <2026-08-07 Fr>
- NEXT WireGuard-Peer für Teltonika ergänzen
  DEADLINE: <2026-08-10 Mo>
- WAITING Antwort Westermo Support
- DONE IP-Plan aktualisieren
  CLOSED: [2026-08-01 Sa]

## Vor Ort
- [ ] Patchkabel 5 m mitnehmen
  - [ ] Adapter LC/SC einpacken
- [x] Laptop laden
```

| Element | Schreibweise |
|---|---|
| Zustände | `TODO` `NEXT` `DOING` `WAITING` `SOMEDAY` `DONE` `CANCELLED` |
| Aliase | `LATER`→TODO, `NOW`→DOING, `WAIT`→WAITING (Logseq-kompatibel) |
| Checkboxen | `- [ ]` und `- [x]` funktionieren gleichwertig |
| Priorität | `[#A]` `[#B]` `[#C]` — färbt den Balken links |
| Tags | `:tag:tag:` am Zeilenende oder `#tag` im Text |
| Termine | `SCHEDULED: <2026-08-07 Fr>`, `DEADLINE: <…>`, `CLOSED: [<…>]` |
| Unterpunkte | zwei Leerzeichen einrücken — beliebig tief verschachtelbar |
| Gruppierung | Markdown-Überschriften werden zu Abschnitten in der Notiz |
| Notizfarbe | `color:` im Frontmatter — yellow, green, pink, purple, blue, gray, charcoal |

Geschrieben wird immer nur die eine betroffene Zeile plus die `CLOSED:`-Zeile.
Kommentare, Fliesstext und Formatierung bleiben unangetastet — damit ist die
Ablage git- und Syncthing-tauglich ohne Merge-Konflikte über die ganze Datei.

## Viewer starten

Python 3.10+ von python.org (tkinter ist dabei). Dann:

```
pythonw mdsticky.py C:\Users\dein-name\Notizen
```

Beim ersten Start fragt das Programm nach dem Ordner und merkt ihn sich in
`%APPDATA%\mdsticky\config.json` — inklusive Position, Grösse und Farbe jeder
Notiz.

**Bedienung**

- Titelleiste ziehen: verschieben · Doppelklick: einklappen
- Klick auf die Checkbox: TODO ↔ DONE, wird sofort in die Datei geschrieben
- `＋`: Aufgabe direkt in der Notiz erfassen (`[#A]`, `#tag` etc. dürfen mit)
- `⋯` oder Rechtsklick: Farbe, erledigte ausblenden, immer im Vordergrund, Datei öffnen
- `✕`: Notiz ausblenden — zurückholen über die Übersicht
- Ecke unten rechts: Grösse ändern
- Externe Änderungen an den Dateien erscheinen nach spätestens 1,5 s

**Autostart:** Verknüpfung auf `pythonw.exe mdsticky.py` in
`shell:startup` ablegen (Win+R → `shell:startup`).

Sortiert wird nur auf der obersten Ebene: überfällig, dann nach Termin,
Priorität und Zustand. Unterpunkte bleiben in Dateireihenfolge unter ihrem
Hauptpunkt. Ein erledigter Hauptpunkt bleibt sichtbar, solange darunter noch
etwas offen ist.

## CLI

```
python mdtodo.py agenda ~/Notizen        # alles mit Termin, überfällig zuerst
python mdtodo.py list   arbeit.md        # alle Einträge der Datei
python mdtodo.py toggle arbeit.md 12     # Zeile 12 umschalten
python mdtodo.py add    arbeit.md "[#A] Kabel bestellen"
python mdtodo.py newnote ~/Notizen       # Assistent: Titel, Farbe, Punkte
```

### Neue Notiz

Ohne weitere Argumente fragt `newnote` kurz nach:

```
Neue Notiz in C:\Users\dein-name\Notizen

Titel: Zugerberg Bahn
Farbe [yellow/green/pink/purple/blue/gray/charcoal] (Enter = ohne): blue

Punkte erfassen — leere Zeile beendet.
Mit "-" oder Leerzeichen davor wird daraus ein Unterpunkt.
Priorität [#A], Tags #tag und "SCHEDULED: <2026-08-07>" dürfen mit.

 1> [#A] Switch tauschen
 2> - Konfig sichern
 3> - Ersatzgerät mitnehmen
 4>
```

Der Dateiname entsteht aus dem Titel (Umlaute werden umgeschrieben,
bestehende Dateien nie überschrieben). Alles auf einmal geht auch:

```
python mdtodo.py newnote ~/Notizen "Zugerberg Bahn" -c blue \
    -t "[#A] Switch tauschen" -t "- Konfig sichern" -t "Fotos Bergstation #doku"
```

## Plattformübergreifend

Der Ordner wandert per Syncthing oder Nextcloud, nicht per proprietärer Cloud:

| Gerät | Werkzeug |
|---|---|
| Windows | mdsticky + beliebiger Editor |
| Linux/macOS | Emacs org-mode, Logseq, Obsidian mit Tasks-Plugin — oder `mdtodo.py agenda` im Terminal |
| Android | Markor (Markdown, versteht Checkboxen), Orgzly Revived, Logseq |
| Sailfish OS | jeder Texteditor; `mdtodo.py agenda` läuft direkt auf dem Gerät, Python ist an Bord |

Der Viewer selbst ist reines tkinter und startet auch unter Linux und macOS —
das Sticky-Notes-Aussehen ist aber auf Windows abgestimmt.

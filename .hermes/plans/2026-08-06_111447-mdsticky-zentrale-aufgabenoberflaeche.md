# mdsticky zentrale Aufgabenoberfläche – Umsetzungsplan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** mdsticky wird zu einer plattformübergreifenden Markdown-Aufgabenoberfläche für Windows, Linux, macOS und Android, wobei lokale Markdown-Dateien die führende Datenquelle bleiben und Syncthing/Nextcloud ausschließlich den Ordner synchronisieren.

**Architecture:** Der bestehende Parser/Writer wird in einen testbaren, plattformunabhängigen Python-Kern überführt. Eine PySide/Qt-Oberfläche übernimmt Desktop und Android. Der Kern verwaltet Parsing, zeilenschonendes Schreiben, Dateiüberwachung, synchronisierte `.mdsticky-base`-Dateien, Drei-Wege-Merge, Konfliktmarker und zeilenweisen Diff. Sailfish OS nutzt zunächst CLI und vorhandene Markdown-Apps.

**Tech Stack:** Python 3.10+, PySide6/Qt, Standardbibliothek für Kernlogik, pytest, Qt-Testwerkzeuge bzw. minimale GUI-Integrationstests.

---

## 1. Verbindliche Produktentscheidungen

- Genau ein gewählter lokaler Notizordner pro Profil.
- Alle `.md`-Dateien im Ordner und Unterordnern werden übernommen, auch ohne Aufgaben.
- `.mdsticky-base`-Dateien sind interne Begleitdateien und keine sichtbaren Notizen.
- Die Basisdateien werden mit Syncthing/Nextcloud synchronisiert und auf allen mdsticky-Geräten verwendet.
- Einfache lokale Dateiablage; keine proprietäre Cloud und kein erforderlicher Server.
- Desktop: Windows, Linux, macOS. Android: eigenständige PySide/Qt-App mit Android-System-Dateiauswahldialog. Sailfish: zunächst CLI und externe Markdown-Apps.
- Integrierter einfacher Markdown-Quelltexteditor direkt im Sticky-Fenster; kein Vorschau-Modus in der ersten Version.
- Aufgaben bleiben per Checkbox schnell umschaltbar.
- Externe Änderungen werden überwacht.
- Unterschiedliche Änderungen werden per Drei-Wege-Merge kombiniert.
- Überlappende Änderungen erzeugen klassische Marker `<<<<<<<`, `=======`, `>>>>>>>` in der `.md`-Datei.
- Dateien mit ungelösten Markern öffnen automatisch die Diff-Ansicht und sind für Aufgabenänderungen gesperrt.
- Der Diff ist standardmäßig ein zeilenweiser Markdown-Diff ähnlich Git.
- Bei inkonsistentem `.md`/`.mdsticky-base`-Paar wird nicht überschrieben oder gemergt; die Diff-Ansicht öffnet sich automatisch.

## 2. Aktueller Repository-Befund

- `mdtodo.py`: Parser, Datenmodell, zeilenweiser Writer und CLI sind vorhanden.
- `mdsticky.py`: tkinter-Viewer mit Launcher, Sticky-Fenstern, Farben, Positionsspeicherung, Checkbox-Toggle und Polling ist vorhanden.
- `README.md`: Format und aktuelle Bedienung sind dokumentiert.
- Es gibt keine Git-Historie und aktuell keine Testsammlung im Repository.
- `python -m py_compile mdsticky.py mdtodo.py` war erfolgreich.
- `list` und `agenda` funktionieren mit den Beispielnotizen.
- Der aktuelle Viewer verwirft in `App.refresh()` Dateien ohne Aufgaben, obwohl `scan_folder()` sie findet.
- Es gibt noch keinen allgemeinen Markdown-Editor, keinen Drei-Wege-Merge, keinen Diff-Viewer und keine Konfliktmarker-Erkennung.
- Die tkinter-Oberfläche soll nicht zum langfristigen plattformübergreifenden UI ausgebaut werden.

## 3. Zielstruktur

```text
mdsticky/
├── pyproject.toml
├── src/mdsticky/
│   ├── __init__.py
│   ├── core/
│   │   ├── model.py
│   │   ├── parser.py
│   │   ├── writer.py
│   │   ├── scanner.py
│   │   ├── conflict.py
│   │   ├── merge.py
│   │   ├── diff.py
│   │   └── repository.py
│   ├── ui/
│   │   ├── main.py
│   │   ├── main_window.py
│   │   ├── note_widget.py
│   │   ├── editor.py
│   │   ├── conflict_dialog.py
│   │   └── styles.py
│   └── cli.py
├── tests/
│   ├── test_parser.py
│   ├── test_writer.py
│   ├── test_scanner.py
│   ├── test_conflict.py
│   ├── test_merge.py
│   ├── test_diff.py
│   └── test_repository.py
└── docs/
    ├── concept.md
    ├── synchronization.md
    └── platform-support.md
```

Die bestehenden `mdtodo.py` und `mdsticky.py` bleiben zunächst als Kompatibilitäts- bzw. Referenzdateien erhalten. Eine spätere Migration oder dünne Wrapper erfolgt erst, wenn der neue Kern nachweislich gleichwertig ist.

## 4. Umsetzung in kleinen, verifizierbaren Schritten

### Phase A – Datenmodell und Regressionstests

1. Bestehende Parserregeln und Schreibsemantik in `tests/test_parser.py` und `tests/test_writer.py` als Tests festhalten.
2. Testfixtures für Frontmatter, Überschriften, Aufgaben, Unteraufgaben, Tags, Termine, CLOSED-Zeilen, Codeblöcke, CRLF und UTF-8 anlegen.
3. `pyproject.toml` mit pytest und Paketlayout einführen, ohne das bestehende CLI zunächst zu brechen.
4. `model.py` und `parser.py` aus `mdtodo.py` extrahieren.
5. `writer.py` mit sicherem temporärem Schreiben, Zeilenende-Erkennung und minimalen Zeilenänderungen implementieren.
6. Alle bestehenden Beispiele gegen den neuen Kern prüfen; `list`, `agenda`, `toggle`, `add` und `newnote` über Wrapper weiter anbieten.

Akzeptanz: Alle Regressionstests bestehen; vorhandene Beispielausgaben bleiben semantisch gleich.

### Phase B – Scanner, Dateien ohne Aufgaben und Konflikterkennung

1. `scanner.py` implementieren: genau ein Root-Verzeichnis, rekursive `.md`-Suche, Ausschluss von `.mdsticky-base`, versteckten Systemordnern und temporären Dateien.
2. Dateien ohne Aufgaben als gültige Notes modellieren; Titel aus Frontmatter, erster H1 oder Dateiname ableiten.
3. `.mdsticky-base`-Paare erkennen und nicht als normale Notes anzeigen.
4. Syncthing-Konfliktnamen (`*.sync-conflict-*.md`) erkennen und dem Original zuordnen.
5. `conflict.py` für Merge-Marker, inkonsistente Basispaare und gesperrte Notizen implementieren.
6. Tests für neue, gelöschte, umbenannte, konfliktbehaftete und auf halbem Synchronisationsstand eintreffende Dateien schreiben.

Akzeptanz: Alle Markdown-Dateien erscheinen in der Repository-Liste; interne Begleitdateien erscheinen nicht als Notes; Konfliktzustände werden deterministisch erkannt.

### Phase C – Drei-Wege-Merge und Basisdateien

1. `repository.py` definiert das Speichern einer Note mit Basis-Snapshot, Dateihash und Schreibzeitpunkt.
2. Erstes Öffnen erzeugt nur dann `.mdsticky-base`, wenn noch keine gültige Basis existiert; vorhandene Nutzerdateien werden nicht blind überschrieben.
3. Vor jedem lokalen Speichern wird die aktuelle Datei gegen den geladenen Basis-Hash geprüft.
4. Bei unveränderter externer Datei wird normal gespeichert und die Basis synchron aktualisiert.
5. Bei externer Änderung wird ein Drei-Wege-Merge aus Basis, lokaler Fassung und externer Fassung durchgeführt.
6. Nicht überlappende Änderungen werden kombiniert.
7. Überlappende Änderungen erzeugen Marker mit eindeutigen Labels `LOCAL` und `EXTERNAL`.
8. Änderungen an derselben semantischen Zeile, Frontmatter-Eigenschaft, CLOSED-Zeile oder Aufgabe-vs.-Löschung werden als Konflikt behandelt.
9. Bei inkonsistenter `.mdsticky-base` wird kein Merge versucht; Original und Basis bleiben unverändert und der Konfliktstatus wird gemeldet.
10. Tests für identische Änderungen, getrennte Zeilen, gleiche Zeile, Datei-Löschung, Frontmatter-Konflikte, Basis-Konflikte und CRLF schreiben.

Akzeptanz: Kein fremder Inhalt wird still überschrieben; Merge-Ergebnisse sind reproduzierbar; Konfliktmarker sind gültiges, manuell bearbeitbares Textformat.

### Phase D – Zeilenweiser Diff

1. `diff.py` erzeugt einen stabilen Unified-Diff und strukturierte Zeilenbereiche mit Dateinamen und Zeilennummern.
2. Die Qt-Diff-Ansicht stellt lokale und externe bzw. Basis- und aktuelle Fassung lesbar gegenüber.
3. Hinzugefügte, entfernte und geänderte Zeilen werden farblich markiert.
4. Marker-Konflikte und inkonsistente Basis öffnen die Ansicht automatisch.
5. Ein Recheck-Button lädt Dateien neu, ohne Änderungen zu überschreiben.
6. Tests prüfen Diff-Ausgabe, leere Dateien, Unicode, lange Zeilen und Konfliktmarker.

Akzeptanz: Der Nutzer kann jede problematische Zeile und beide Dateinamen/Zeilennummern erkennen.

### Phase E – PySide/Qt-Oberfläche

1. PySide6-Abhängigkeit und App-Einstieg in `ui/main.py` ergänzen.
2. Root-Ordner-Auswahl über nativen Desktop-Dialog integrieren; auf Android den Android-System-Dateiauswahldialog bzw. Qt-Document-Portal verwenden.
3. Eine Note-Liste/Launcher für alle `.md`-Dateien bauen, einschließlich Notes ohne Aufgaben, Status und Konfliktmarkierung.
4. Sticky-Note-Ansicht mit Titel, freiem Markdown-Editor und Aufgabeninteraktionen bauen.
5. Speichern über `repository.py` routen; bei externen Änderungen zuerst Merge/Conflict-State prüfen.
6. Konflikt-Dialog als nicht-modales bzw. automatisch öffnendes Fenster integrieren.
7. Aufgabenänderungen bei ungelösten Konflikten sperren.
8. Polling bzw. QFileSystemWatcher plus periodischen Recheck für Syncthing-Race-Conditions implementieren.
9. Ein-Profil-Konfiguration mit genau einem Ordner und UI-Einstellungen speichern.
10. Tests für Kern-UI-Modelle und manuelle Smoke-Tests auf Desktop durchführen.

Akzeptanz: Ein Ordner kann gewählt werden; alle `.md`-Dateien sind sichtbar; freie Bearbeitung und Checkbox-Toggle funktionieren; Konflikte öffnen automatisch den Diff und verhindern stille Schreibvorgänge.

### Phase F – CLI, Dokumentation und Plattformpakete

1. CLI auf den neuen Kern umstellen und Sailfish-kompatible Befehle dokumentieren.
2. `docs/concept.md` mit Datenformat, Rollen von `.md` und `.mdsticky-base`, Dateisperren und Konfliktablauf schreiben.
3. `docs/synchronization.md` mit Syncthing/Nextcloud-Empfehlungen und dem Verhalten bei zeitversetzten Dateien schreiben.
4. `docs/platform-support.md` für Desktop, Android und Sailfish pflegen.
5. README um Installation, Ordnerwahl, Basisdateien, Konfliktmarker, Diff und Sicherungshinweise ergänzen.
6. Desktop-Paketierung für Windows, Linux und macOS vorbereiten.
7. Android-Paket mit PySide/Qt-Beschränkungen und Dateizugriffsrechten bauen, sobald eine Qt-for-Android-Buildumgebung verfügbar ist.
8. Reale Smoke-Tests auf jedem verfügbaren Ziel durchführen; nicht verfügbare Geräte ausdrücklich als unvalidiert kennzeichnen.

## 5. Test- und Qualitätsstrategie

- Jede Kernfunktion erhält zuerst einen fehlgeschlagenen Test, dann Implementierung und Regressionstest.
- Keine Merge-Funktion ohne Tests für gleiche und getrennte Änderungen.
- Property-/Fuzz-ähnliche Tests für beliebige Markdown-Zeilen, Unicode und unvollständige Dateien ergänzen.
- Tests für atomisches Schreiben und Wiederherstellung bei Schreibfehlern vorsehen.
- Tests dürfen keine Dateien im Produktordner dauerhaft verändern; `tmp_path` verwenden.
- Vor jedem Release ausführen:

```text
python -m pytest -q
python -m compileall src tests
python -m mdsticky.cli list <testordner>
```

- Zusätzlich manuell prüfen: Syncthing-Konfliktdatei, externe Änderung während Editor-Eingabe, gleichzeitige Checkbox-Änderung, Basisdatei kommt verspätet, Datei ohne Aufgaben, CRLF und Android-System-Dateiauswahl.

## 6. Risiken und Entscheidungen

- PySide6 auf Android ist deutlich anspruchsvoller als Desktop-PySide; Packaging und Dateizugriff müssen früh als Spike validiert werden.
- Eine synchronisierte `.mdsticky-base` kann selbst in einem inkonsistenten Zustand eintreffen. Die festgelegte sichere Reaktion ist Abbruch plus Diff, nicht automatische Reparatur.
- Drei-Wege-Merge auf Textzeilen erkennt semantische Konflikte nur begrenzt. Aufgaben-IDs oder stabile IDs wären technisch hilfreich, sind aber nicht Bestandteil der ersten festgelegten Version.
- Automatisches Öffnen eines Diff-Fensters kann bei häufigen temporären Synchronisationszuständen störend sein; Debouncing und „bereits angezeigt“-Status sind notwendig.
- Die aktuelle Anforderung „alle `.md`-Dateien“ bedeutet, dass auch große Dokumente oder reine Wissensnotizen in der Übersicht erscheinen. Filter und Sortierung sollten vorgesehen, aber nicht vorzeitig überladen werden.
- `.mdsticky-base` enthält möglicherweise sensible Inhalte und muss dieselben Backup-/Datenschutzregeln wie die Notizen erhalten.
- Keine Aussage über Android- oder macOS-Releasefähigkeit, bevor echte Builds und Zieltests erfolgt sind.

## 7. Nicht Bestandteil der ersten Umsetzung

- eigener Sync-Server oder proprietäre Cloud
- automatische semantische Konfliktauflösung mit KI
- Aufgaben-IDs und globale Datenbank
- integrierte Markdown-Vorschau
- mehrere Ordner/Arbeitsbereiche pro Profil
- eigene Sailfish-GUI
- vollwertige mobile Synchronisationsintegration

## 8. Empfohlene Reihenfolge für die tatsächliche Implementierung

Zuerst Kern und Tests, danach Merge/Diff, dann Qt-UI. Vor umfangreicher UI-Arbeit muss ein kurzer PySide6-for-Android-Spike klären, ob die gewünschte gemeinsame Python/Qt-Architektur praktisch paketierbar ist. Die bestehende tkinter-App bleibt bis zu einem funktionierenden Qt-MVP unverändert nutzbar.

**Definition of Done für den MVP:**

- Kern-Parser und Writer regressionsgetestet
- alle `.md`-Dateien einschließlich leerer Aufgabenlisten sichtbar
- integrierter Markdown-Editor vorhanden
- sichere Speicherung mit `.mdsticky-base`
- Drei-Wege-Merge für getrennte Änderungen
- klassische Marker für echte Konflikte
- automatische Diff-Ansicht und Schreibsperre bei Konflikten
- Desktop-Smoke-Test auf mindestens Windows
- Android-Build entweder erfolgreich validiert oder der konkrete technische Blocker dokumentiert
- Dokumentation und CLI aktualisiert

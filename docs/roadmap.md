# mdsticky Roadmap

## Nächster Umsetzungsschritt: integrierter Markdown-Editor

Vormerkung für die nächste Entwicklungsphase nach Version 0.0.4.

### Ziel

Markdown-Text soll direkt innerhalb jeder Sticky Note bearbeitet werden können. Die Markdown-Datei bleibt die führende Datenquelle.

### Anforderungen

- Bearbeitungsmodus direkt im Sticky-Fenster
- vollständiger Markdown-Quelltext in einem Textfeld
- Aktionen: Bearbeiten, Speichern, Abbrechen
- neue Aufgaben weiterhin über `＋` anlegen können
- neue Aufgaben an einer definierten Position einfügen können, nicht nur am Dateiende
- Speichern über die bestehende Drei-Wege-Merge-Logik
- Verwendung der synchronisierten `.mdsticky-base`-Datei
- externe Änderungen während der Bearbeitung erkennen
- unabhängige Änderungen automatisch zusammenführen
- überlappende Änderungen als Konfliktmarker speichern
- bei ungelösten Konflikten Bearbeitung und Aufgabenänderungen sperren
- Konflikt-Diff als nächster Schritt vorbereiten
- Undo/Redo im Editor unterstützen

### Reihenfolge

1. GUI-Fehler bei JSON-Schlüsseln und Pfadtypen dauerhaft testen.
2. Merge-sicheres Anlegen neuer Aufgaben integrieren.
3. Bearbeitungsmodus mit vollständigem Markdown-Textfeld ergänzen.
4. Speichern, Abbrechen und externe Änderungen testen.
5. Konfliktzustand und Diff-Anzeige in den Editorfluss integrieren.
6. Tests ausführen und als eigene Version veröffentlichen.

### Abnahmekriterien

- Eine `nd_*.md`-Datei kann direkt im Sticky bearbeitet werden.
- Speichern verändert nur die betreffende Markdown-Datei und ihre Basisdatei.
- Externe Änderungen werden nicht still überschrieben.
- Bei einem echten Konflikt bleiben beide Seiten in klassischen Konfliktmarkern erhalten.
- Bestehende Aufgaben-, Parser- und Merge-Tests bleiben erfolgreich.

## Bereits festgelegt

- Als Notes gelten ausschließlich Dateien mit dem Muster `nd_*.md`.
- `.mdsticky-base`-Dateien werden synchronisiert und nicht als Notes angezeigt.
- Lokaler Notizordner; Synchronisation erfolgt außerhalb der App über Syncthing oder Nextcloud.
- Eine Arbeitsablage pro Profil.
- Sailfish OS wird zunächst über CLI und vorhandene Markdown-Apps unterstützt.

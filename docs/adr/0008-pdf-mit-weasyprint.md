# 0008: Rechnungs-PDF mit WeasyPrint als PDF/A

- Status: vorgeschlagen
- Datum: 2026-10-21

## Kontext

Finalisierte Rechnungen werden als PDF verschickt und müssen unverändert aufbewahrt werden (GoBD, `docs/domain/gobd.md`). Später sollen sie optional als ZUGFeRD/Factur-X ausgegeben werden. Dafür braucht es PDF/A-3. Die Oberfläche ist bereits HTML mit Jinja (ADR 0004).

## Entscheidung

- PDFs entstehen aus einem Jinja-Template mit **WeasyPrint** (HTML/CSS → PDF), im Format **PDF/A-3b**.
- Der QR-Code für Überweisungen (GiroCode, EPC069-12) wird mit **segno** als SVG erzeugt und eingebettet. Den Inhalt (EPC-Payload) baut eigener, getesteter Code in `app/domain/epc.py`.
- Das PDF wird beim Finalisieren **einmal** erzeugt, mit SHA-256 abgelegt und danach nur noch ausgeliefert, nie neu gerendert. Spätere Änderungen an Template oder Firmendaten ändern alte Rechnungen nicht.

## Verworfene Alternativen

- **reportlab / fpdf2** (reines Python, keine Systembibliotheken): Layout müsste in Python-Code statt HTML/CSS beschrieben werden, PDF/A-3 nur eingeschränkt.
- **Headless Chrome**: schwerer Betrieb, kein PDF/A.
- **PDF bei jedem Abruf neu erzeugen**: verstößt gegen die Unveränderbarkeit.

## Folgen

- WeasyPrint braucht die Systembibliothek **Pango**: macOS `brew install pango`, Debian/Ubuntu `apt install libpango-1.0-0 libpangoft2-1.0-0`. Die CI installiert sie, das Docker-Image später ebenso.
- Schriften müssen im Container vorhanden sein, damit das PDF überall gleich aussieht.
- ZUGFeRD/Factur-X lässt sich später ergänzen, indem die XML-Datei an das PDF/A-3 angehängt wird.

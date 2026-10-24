# 0006: Belege vor der Verbuchung löschbar

- Status: vorgeschlagen
- Datum: 2026-10-21

## Kontext

Harte Regel 5 in `CONTRIBUTING.md` lautet: Belege werden nie überschrieben und nie gelöscht.

Im Alltag landen aber auch Dateien im Tool, die nie Belege der Buchhaltung waren: versehentlich hochgeladene Dateien, Dubletten, private Quittungen, die falsche Seite eines Scans. Für Einsteiger ist es unverständlich, wenn sich solche Fehler nicht beheben lassen. Ohne Löschmöglichkeit füllt sich das Archiv mit Datenmüll.

Die GoBD schützen Unterlagen, auf denen Buchungen beruhen. Eine Datei, die nie verbucht wurde, ist kein Buchungsbeleg.

## Entscheidung

- Ein Beleg darf gelöscht werden, **solange er an keiner festgeschriebenen Buchung hängt**.
- Das Löschen wird im Änderungsprotokoll festgehalten: wer, wann, Originalname, SHA-256. Die Datei selbst wird entfernt.
- Hängt der Beleg an einer festgeschriebenen Buchung, gibt es nur **„Stornieren“**. Das erzeugt nach einem Warnhinweis die Stornobuchung für Beleg und Zahlung (ADR 0002). Die Datei bleibt unverändert erhalten.
- Ausgangsrechnungen mit vergebener Nummer werden nie gelöscht.
- Der DB-Trigger auf `beleg` lässt `DELETE` nur zu, wenn keine Verknüpfung zu einer festgeschriebenen Buchung besteht.
- Harte Regel 5 wird nach Annahme angepasst: „Belege sind unveränderlich. Gelöscht werden dürfen sie nur, solange sie nicht verbucht sind (ADR 0006).“

## Verworfene Alternativen

- **Nie löschen (bisherige Regel):** rechtlich am sichersten, aber für Fehl-Uploads unpraktisch. Private Dokumente blieben dauerhaft im Geschäftsarchiv.
- **Löschen auch nach Verbuchung, mit Warnhinweis und Löschen der Zahlung:** verstößt gegen die GoBD (Unveränderbarkeit festgeschriebener Buchungen). Verworfen.
- **Soft-Delete (nur ausblenden):** löst das Problem privater Dokumente im Archiv nicht.

## Folgen

- Trigger und Tests müssen beide Fälle abdecken: Löschen eines unverbuchten Belegs klappt, Löschen eines verbuchten Belegs scheitert auch per SQL.
- Die Oberfläche zeigt je nach Zustand „Löschen“ oder „Stornieren“, nie beides.
- Das Protokoll enthält Löscheinträge zu Dateien, die nicht mehr existieren. Die Integritätsprüfung muss das berücksichtigen.

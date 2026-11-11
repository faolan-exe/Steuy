"""Prüfprozess: liest das XML von stdin, schreibt die Meldungen als JSON nach stdout."""

import json
import sys
from dataclasses import asdict

from app.domain.erechnung_regeln import pruefe_hier

if __name__ == "__main__":
    meldungen = pruefe_hier(sys.stdin.buffer.read(), xrechnung=sys.argv[1:] == ["x"])
    json.dump([asdict(m) for m in meldungen], sys.stdout)

# finance — XIRR (interner Zinsfuß) für unregelmäßige Cashflows

Ein kleines Python-Tool zum Berechnen des internen Zinsfußes (XIRR) für unregelmäßige Cashflows. Das Projekt enthält ein CLI (main.py), das Cashflows aus einer JSON-Datei liest, den XIRR berechnet und das Ergebnis ausgibt.

Kurz: Du kannst mit --init eine Beispiel-JSON erzeugen und anschließend die Rendite aus dieser Datei berechnen.

## Features
- XIRR-Berechnung für unregelmäßige Zeitpunkte
- Newton-Raphson (schnell) mit Analytischer Ableitung und Fallback auf bracketing/brentq (robust)
- CLI zum Einlesen von Cashflows aus JSON
- Typannotationen und ausführliche Docstrings

## Voraussetzungen
- Python 3.8+
- Abhängigkeiten:
  - scipy

Installation der Abhängigkeiten:
```bash
python -m pip install --upgrade pip
python -m pip install scipy
```

## Dateiformat (JSON)
Die Cashflow-Datei ist eine JSON-Liste von Objekten mit den Feldern:
- `date` — Datum im ISO-Format (z. B. `"2025-03-23"`, Zeitanteil wird ignoriert)
- `amount` — Zahl (Einzahlungen negativ, Auszahlungen positiv)

Beispiel:
```json
[
  { "date": "2025-03-23", "amount": -16000 },
  { "date": "2025-06-01", "amount": 12000 },
  { "date": "2025-08-11", "amount": -700 },
  { "date": "2025-11-18", "amount": 4921 }
]
```

Wichtig: Damit ein sinnvoller IRR existiert, muss die Liste mindestens einen positiven und einen negativen Betrag enthalten (Vorzeichenwechsel).

## CLI - Verwendung
Beispiele:
- Erstelle eine Beispiel-JSON:
  ```bash
  python main.py --init sample_cashflows.json
  ```
- Berechne die Rendite aus einer Datei (default: `cashflows.json`):
  ```bash
  python main.py --file sample_cashflows.json
  ```
- Mit Startschätzung für Newton:
  ```bash
  python main.py --file sample_cashflows.json --guess 0.05
  ```

Exit-Codes (Kurz):
- 0: Erfolg
- 1: Beispiel-Datei existiert bereits (beim --init)
- 2: Eingabedatei nicht gefunden
- 3: Fehler beim Lesen/Parsen der JSON-Datei
- 4: IRR konnte nicht berechnet werden (z. B. kein Vorzeichenwechsel oder konvergierte nicht)

## Implementierungsdetails
- Standard-Zeitzählung: Jahre = Tage / 365.25 (Berücksichtigung von Schaltjahren)
- Konvention: Einzahlungen sind negativ (Geld in das Investment), Auszahlungen/Entnahmen positiv
- Solver-Strategie:
  1. Newton-Raphson mit analytischer Ableitung (schnell, wenn konvergent)
  2. Falls Newton fehlschlägt, Suche nach einem Intervall mit Vorzeichenwechsel und Lösen mit `brentq` (robust)

## Fehlerbehandlung und Hinweise
- Ein Zinssatz <= -1 ist ungültig (division durch null / negatives Diskontieren)
- Falls kein eindeutiger IRR gefunden werden kann (z. B. mehrere Vorzeichenwechsel, keine Wurzel im gescannten Bereich), gibt das Tool einen Fehler zurück und empfiehlt die Prüfung der Cashflows oder eine andere Startschätzung.

## UI-Version coming soon...
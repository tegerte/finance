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

## Automatischer Kurswert-Abruf (fetch_allvest.py)

Ein Playwright-basiertes Skript, das sich automatisch bei Allvest einloggt, den aktuellen Kurswert ausliest, die `cashflows.json` aktualisiert, die Rendite berechnet und optional eine HTML-Mail mit Plot versendet.

### Voraussetzungen

- Python 3.12 (venv `.venv`)
- Playwright mit Chromium
- `.env`-Datei mit Zugangsdaten (siehe `.env.example`)

### Setup

```bash
# Venv und Abhängigkeiten sind bereits eingerichtet:
.venv/bin/python -m playwright install chromium
```

### Verwendung

```bash
# Nur Kurswert anzeigen (nichts speichern):
.venv/bin/python fetch_allvest.py --dry-run

# Kurswert holen + Rendite berechnen:
.venv/bin/python fetch_allvest.py

# Mit E-Mail-Versand:
.venv/bin/python fetch_allvest.py --mail

# Debug-Modus (Browser sichtbar, Screenshots):
.venv/bin/python fetch_allvest.py --debug --mail
```

### Authentifizierung & Troubleshooting

Das Skript nutzt ein **persistentes Browser-Profil** (`.browser-profile/`), um Cookies und Sessions zu speichern. Beim ersten Lauf oder nach Session-Ablauf verlangt Allvest eine 2FA-Verifizierung per E-Mail-Code. In dem Fall mit `--debug` starten, den Code im Browser-Fenster eingeben — danach läuft es wieder automatisch.

Falls die Session abgelaufen ist:
```bash
.venv/bin/python fetch_allvest.py --debug --mail
```
Den E-Mail-Code im sich öffnenden Browser eingeben, danach läuft alles wieder automatisch.

### Automatischer täglicher Lauf (macOS launchd)

Ein macOS **LaunchAgent** sorgt dafür, dass das Skript automatisch einmal pro Tag läuft. Der Agent wird bei jedem Login gestartet und zusätzlich täglich um 9:00 Uhr ausgeführt (auch nach dem Aufwachen aus dem Schlafmodus). Das Wrapper-Skript `fetch_daily.sh` verhindert über ein Lockfile (`/tmp/allvest_last_run`) doppelte Ausführungen am selben Tag.

#### Einrichtung

1. **Plist-Datei kopieren** (falls noch nicht vorhanden):
   ```bash
   cp de.tassilo.allvest-fetch.plist ~/Library/LaunchAgents/
   ```

2. **Agent bei launchd registrieren:**
   ```bash
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/de.tassilo.allvest-fetch.plist
   ```

3. **Prüfen, ob der Agent geladen ist:**
   ```bash
   launchctl list | grep allvest
   ```
   Ausgabe sollte eine Zeile mit `de.tassilo.allvest-fetch` zeigen. Die erste Spalte ist der Exit-Code des letzten Laufs (`0` = erfolgreich, `-` = noch nicht gelaufen).

#### Agent manuell starten / stoppen

```bash
# Sofort ausführen (ohne auf den Zeitplan zu warten):
launchctl kickstart gui/$(id -u)/de.tassilo.allvest-fetch

# Agent entfernen (stoppt den Zeitplan):
launchctl bootout gui/$(id -u)/de.tassilo.allvest-fetch

# Agent neu laden (z. B. nach Änderung der plist):
launchctl bootout gui/$(id -u)/de.tassilo.allvest-fetch
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/de.tassilo.allvest-fetch.plist
```

#### Logs prüfen

```bash
# Ausgabe des Skripts:
tail -f fetch.log

# launchd-spezifische Ausgabe (normalerweise leer):
cat launchd.log
```

#### Hinweise

- **Sleep vs. Login:** `RunAtLoad` triggert nur bei einem echten Login (Neustart, Abmeldung/Anmeldung). Für den täglichen Lauf beim Aufwachen aus dem Schlafmodus sorgt `StartCalendarInterval` — macOS holt verpasste Ausführungen nach.
- **Uhrzeit ändern:** In der Plist die Werte unter `StartCalendarInterval` → `Hour`/`Minute` anpassen und den Agent neu laden.
- Die veralteten Befehle `launchctl load`/`unload` funktionieren noch, Apple empfiehlt aber `bootstrap`/`bootout`.

### Projektstruktur

```
main.py                 # XIRR-Berechnung + Plot (3 Subplots, 7-Tage mit Tagesveränderung)
fetch_allvest.py        # Automatischer Kurswert-Abruf + Mail
fetch_daily.sh          # Wrapper für täglichen Lauf (einmal pro Tag)
cashflows.json          # Cashflow-Daten (Ein-/Auszahlungen + aktueller Wert)
rendite.feather         # Historische Rendite-Ergebnisse (Feather/Arrow)
rendite_plot.png        # Letzter gespeicherter Plot
.env                    # Zugangsdaten (nicht committen!)
.env.example            # Vorlage für .env
.browser-profile/       # Persistentes Chromium-Profil (nicht committen!)
.venv/                  # Python 3.12 venv (alle Abhängigkeiten)
```
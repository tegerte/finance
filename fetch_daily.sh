#!/bin/bash
# Allvest-Kurswert einmal täglich beim Login holen
LOCKFILE="/tmp/allvest_last_run"
TODAY=$(date +%Y-%m-%d)

# Prüfe ob heute schon gelaufen
if [ -f "$LOCKFILE" ] && [ "$(cat "$LOCKFILE")" = "$TODAY" ]; then
    exit 0
fi

# Warte kurz bis Netzwerk verfügbar ist
sleep 10

cd /Users/tassilo/python/Sparvertrag_rendite
.venv-browseruse/bin/python fetch_allvest.py --mail >> fetch.log 2>&1

if [ $? -eq 0 ]; then
    echo "$TODAY" > "$LOCKFILE"
fi

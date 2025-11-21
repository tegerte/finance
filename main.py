#!/usr/bin/env python3
"""
CLI for computing XIRR (interner Zinsfuß) aus einer JSON-Datei mit Cashflows.

Usage examples:
  - Erstelle eine Beispiel-JSON:
      python main.py --init sample_cashflows.json
  - Berechne die Rendite aus einer Datei (default: cashflows.json):
      python main.py --file sample_cashflows.json
  - Mit Start-Schätzung:
      python main.py --file sample_cashflows.json --guess 0.05
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

from scipy.optimize import newton, brentq

DateAmount = Tuple[datetime, float]


def load_cashflows(path: Path) -> List[DateAmount]:
    """
    Lade Cashflows aus einer JSON-Datei.

    Erwartetes JSON-Format: eine Liste von Objekten mit Feldern:
      - date: "YYYY-MM-DD" (oder ISO 8601 Datumsteil)
      - amount: Zahl (Einzahlungen negativ, Auszahlungen positiv)

    :param path: Pfad zur JSON-Datei
    :return: Liste von (datetime, amount)
    :raises ValueError: falls Einträge ungültig sind
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("JSON muss eine Liste von Cashflow-Objekten enthalten.")
    cf: List[DateAmount] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Eintrag #{i} ist kein Objekt.")
        if "date" not in item or "amount" not in item:
            raise ValueError(f"Eintrag #{i} fehlt 'date' oder 'amount'.")
        date_raw = item["date"]
        amt = item["amount"]
        if not isinstance(date_raw, str):
            raise ValueError(f"Datum in Eintrag #{i} muss ein String sein.")
        try:
            # Unterstütze "YYYY-MM-DD" und generelle ISO-Formate (time wird ignoriert)
            dt = datetime.fromisoformat(date_raw)
        except Exception as exc:
            raise ValueError(f"Datum in Eintrag #{i} ist ungültig: {exc}")
        try:
            amount = float(amt)
        except Exception:
            raise ValueError(f"Betrag in Eintrag #{i} ist keine gültige Zahl.")
        cf.append((dt, amount))
    if not cf:
        raise ValueError("Keine Cashflows in der Datei.")
    return cf


def save_sample_json(path: Path) -> None:
    """
    Schreibe eine Beispiel-Cashflow-JSON-Datei zum einfachen Starten.
    """
    sample = [
        {"date": "2025-03-23", "amount": -16000},  # Start Einzahlung
        {"date": "2025-06-01", "amount": 12000},   # Abhebung
        {"date": "2025-08-11", "amount": -700},    # Einzahlung
        {"date": "2025-11-18", "amount": 4921},    # aktueller Wert inkl. Zinsen
    ]
    path.write_text(json.dumps(sample, indent=2, ensure_ascii=False), encoding="utf-8")


def _year_fractions(cashflows: List[DateAmount], day_count: float = 365.25) -> Tuple[List[float], List[float]]:
    """
    Wandelt Datum in Jahre seit dem Startdatum um und extrahiert Beträge.

    :param cashflows: Liste von (datetime, amount)
    :param day_count: Anzahl Tage pro Jahr (default 365.25 für Schaltjahre)
    :return: (times_in_years, amounts)
    """
    start = cashflows[0][0]
    times = [(dt - start).days / day_count for dt, _ in cashflows]
    amounts = [amt for _, amt in cashflows]
    return times, amounts


def xnpv(rate: float, times: List[float], amounts: List[float]) -> float:
    """
    XNPV für unregelmäßige Cashflows bei gegebenem Jahreszinssatz.

    :param rate: Jahreszins (dezimal). Muss > -1.
    :param times: Zeitpunkte in Jahren relativ zum ersten Cashflow.
    :param amounts: Beträge.
    :return: Kapitalwert
    """
    if rate <= -1.0:
        raise ValueError("rate must be greater than -1.0")
    return sum(a / ((1.0 + rate) ** t) for t, a in zip(times, amounts))


def _dxnpv_dr(rate: float, times: List[float], amounts: List[float]) -> float:
    """
    Ableitung von xnpv nach dem Zinssatz (für Newton).
    """
    if rate <= -1.0:
        raise ValueError("rate must be greater than -1.0")
    return sum(-t * a / ((1.0 + rate) ** (t + 1.0)) for t, a in zip(times, amounts))


def xirr(
    cashflows: List[DateAmount],
    guess: float = 0.05,
    tol: float = 1e-9,
    maxiter: int = 100,
    day_count: float = 365.25,
) -> Optional[float]:
    """
    Berechne den internen Zinsfuß (XIRR) für unregelmäßige Cashflows.

    Vorgehen:
      1. Validierung (mind. ein positiver und ein negativer Cashflow).
      2. Versuch mit Newton-Raphson (analytische Ableitung).
      3. Falls Newton fehlschlägt, Suche nach einem Intervall mit Vorzeichenwechsel
         und löse mit brentq (robuster).

    :return: Jahreszins als Dezimal oder None, wenn kein eindeutiger IRR gefunden wurde.
    """
    times, amounts = _year_fractions(cashflows, day_count=day_count)

    if not any(a > 0 for a in amounts) or not any(a < 0 for a in amounts):
        # Kein gültiger IRR möglich ohne mindestens ein Vorzeichenwechsel
        return None

    def f(r: float) -> float:
        return xnpv(r, times, amounts)

    def df(r: float) -> float:
        return _dxnpv_dr(r, times, amounts)

    # 1) Newton-Raphson mit analytischer Ableitung
    try:
        irr = newton(func=f, x0=guess, fprime=df, tol=tol, maxiter=maxiter)
        if irr > -1.0:
            return float(irr)
    except (RuntimeError, OverflowError, ValueError):
        # Fallthrough to bracketed root finder
        pass

    # 2) Bracket + brentq: suche einen Bereich mit Vorzeichenwechsel
    scan_min = -0.999999
    scan_max = 10.0
    n_steps = 200
    step = (scan_max - scan_min) / n_steps
    prev_r = scan_min
    try:
        prev_f = f(prev_r)
    except Exception:
        prev_f = float("inf")
    r = prev_r + step
    bracket: Optional[Tuple[float, float]] = None
    for _ in range(n_steps):
        try:
            curr_f = f(r)
        except Exception:
            curr_f = float("inf")
        if prev_f == 0.0:
            bracket = (prev_r, prev_r)
            break
        if curr_f == 0.0:
            bracket = (r, r)
            break
        if prev_f * curr_f < 0.0:
            bracket = (prev_r, r)
            break
        prev_r, prev_f = r, curr_f
        r += step

    if bracket is None:
        return None

    low, high = bracket
    if low == high:
        return low
    try:
        irr = brentq(f, low, high, xtol=tol)
        return float(irr)
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Berechne XIRR aus einer JSON-Datei mit Cashflows.")
    parser.add_argument("--file", "-f", type=Path, default=Path("cashflows.json"),
                        help="Pfad zur JSON-Datei mit Cashflows (default: cashflows.json)")
    parser.add_argument("--init", action="store_true", help="Erstelle eine Beispiel-JSON-Datei und beende das Programm.")
    parser.add_argument("--guess", type=float, default=0.05, help="Start-Schätzung für das Newton-Verfahren (default: 0.05)")
    args = parser.parse_args()

    path = args.file

    if args.init:
        if path.exists():
            print(f"Datei {path!s} existiert bereits. Überschreibe nicht.")
            return 1
        save_sample_json(path)
        print(f"Beispiel-Cashflows geschrieben nach: {path!s}")
        return 0

    if not path.exists():
        print(f"Datei {path!s} nicht gefunden. Erzeuge eine Beispiel-Datei mit --init {path!s}")
        return 2

    try:
        cashflows = load_cashflows(path)
    except ValueError as exc:
        print(f"Fehler beim Einlesen der Cashflows: {exc}")
        return 3

    irr = xirr(cashflows, guess=args.guess)
    if irr is None:
        print("Die Rendite konnte nicht berechnet werden. Prüfen Sie die Cashflows (müssen mindestens eine positive und eine negative Zahlung enthalten) "
              "oder versuchen Sie eine andere Start-Schätzung (--guess).")
        return 4

    print(f"Die berechnete Rendite (IRR) beträgt: {irr * 100:.6f}% pro Jahr")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
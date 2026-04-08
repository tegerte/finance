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
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import List, Tuple, Optional, Any
import humanfriendly
import pandas as pd
import matplotlib.pyplot as plt
from pandas import DataFrame
import numpy as np

from scipy.optimize import newton, brentq

log = logging.getLogger(__name__)

DateAmount = Tuple[datetime, float]

def prRed(s): log.info("\033[91m %s\033[00m", s)

def display_duration(cfs) ->str:
    """
    Calculates overall timespan 
    """
    _,_,span, end = _year_fractions(cfs)
    formatted=f'Laufzeit bis heute {end.strftime("%A")} den {end.strftime("%d")}. {end.strftime("%B")} {end.strftime("%Y")} : \n{humanfriendly.format_timespan(span, detailed=True)}'
    return formatted


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


def _year_fractions(cashflows: List[DateAmount], day_count: float = 365.25) -> Tuple[List[float], List[float], timedelta, datetime]:
    """
    Wandelt Datum in Jahre seit dem Startdatum um und extrahiert Beträge.

    :param cashflows: Liste von (datetime, amount)
    :param day_count: Anzahl Tage pro Jahr (default 365.25 für Schaltjahre)
    :return: (times_in_years, amounts, runtime, enddate )
    """
    start = cashflows[0][0]
    end = max([date for date,_ in cashflows])
    runtime = end - start
    times = [(dt - start).days / day_count for dt, _ in cashflows]
    amounts = [amt for _, amt in cashflows]
    return times, amounts, runtime,end


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
    times, amounts, _, _ = _year_fractions(cashflows, day_count=day_count)

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

def read_json(filename, supress_new_prompt=False) -> tuple[Any, Any, bool] | tuple[None, None, bool]:
    """
    liest das json und holt den neuesten Eintrag, der dem heutigen Datum entsprechen muss.
    Ist leider in gewisser Weise doppelt zu read_cashflows... egal
    """
    try:
        with open(filename,'r') as json_file:
            data = json.load(json_file)
            max_entry = max(data,key=lambda x: x['date']) # returns the dict from the list with max date
            if max_entry['date'] != datetime.today().strftime('%Y-%m-%d') and not supress_new_prompt:
                log.warning('Ist aktueller Eintrag vorhanden? Neuester Eintrag ist %s.', max_entry["date"])
                return data,max_entry, False

            return data,max_entry,True
    except FileNotFoundError:
        log.error('File %s konnte nicht gefunden werden!', filename)
        return None, None, False

def read_rendite(in_file: Path) -> pd.DataFrame:
    try:
        df = pd.read_feather(in_file)
    except FileNotFoundError:
        df = pd.DataFrame()
    return df

def write_rendite(out_file: Path, df: DataFrame) -> int:
    df.reset_index(drop=True).to_feather(out_file)




def main() -> int:
    parser = argparse.ArgumentParser(description="Berechne XIRR aus einer JSON-Datei mit Cashflows.")
    parser.add_argument("--cashflows", "-c", type=Path, default=Path("cashflows.json"),
                        help="Pfad zur JSON-Datei mit Cashflows (default: cashflows.json)")
    parser.add_argument("--rendite", "-r", type=Path, default=Path("rendite.feather"),
                        help="Pfad zur Feather-Datei mit den bisherigen Rendite-Ergebnissen (default: rendite.feather)")

    parser.add_argument("--init", action="store_true", help="Erstelle eine Beispiel-JSON-Datei und beende das Programm.")
    parser.add_argument("--guess", type=float, default=0.05,
                        help="Start-Schätzung für das Newton-Verfahren (default: 0.05)")
    parser.add_argument("--standalone","-s", action="store_true",
                        help="Schaltet Abfrage des aktuellen Kontostands über Komandozeile ein. ")
    parser.add_argument("--save-plot", type=Path, default=None,
                        help="Plot als Bild speichern statt anzeigen (z.B. --save-plot rendite.png)")

    args = parser.parse_args()

    path_cfs = args.cashflows
    path_rendite = args.rendite

    if args.init:
        if path_cfs.exists():
            log.warning("Datei %s existiert bereits. Überschreibe nicht.", path_cfs)
            return 1
        save_sample_json(path_cfs)
        log.info("Beispiel-Cashflows geschrieben nach: %s", path_cfs)
        return 0

    if not path_cfs.exists():
        log.error("Datei %s nicht gefunden. Erzeuge eine Beispiel-Datei mit --init %s", path_cfs, path_cfs)
        return 2

    previous_results = read_rendite(path_rendite)
    if args.standalone:
        curr_saldo= input('Aktueller Kontostand?')
        data,_,_ = read_json(path_cfs, supress_new_prompt=True)
        new_data =True
        current_data = {'amount': curr_saldo, 'date': str(date.today())}
        data and data[-1].update(current_data)
        with open(path_cfs, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)



    else:
       _, current_data, new_data = read_json(path_cfs)

    try:

        cashflows = load_cashflows(path_cfs)
        log.info(display_duration(cashflows))
    except ValueError as exc:
        log.error("Fehler beim Einlesen der Cashflows: %s", exc)
        return 3



    irr = xirr(cashflows, guess=args.guess)
    if irr is None:
        log.error("Die Rendite konnte nicht berechnet werden. Prüfen Sie die Cashflows (müssen mindestens eine positive und eine negative Zahlung enthalten) "
              "oder versuchen Sie eine andere Start-Schätzung (--guess).")
        return 4
    resultstring = f'{irr * 100:.6f}% pro Jahr'
    log.info("Die berechnete Rendite (IRR) beträgt:")
    prRed(resultstring)
    if new_data :
        new_row = pd.DataFrame({'date': [current_data['date']],'saldo': [current_data['amount']],'rendite': [irr * 100]})
        results = pd.concat([previous_results, new_row], ignore_index=True)
        # noch prüfen ob für den heutigen Tag ein Eintarag vorhanden ist
        write_rendite(path_rendite, results)
    else:
        results = previous_results
    plot_it(results, save_path=args.save_plot)
    return 0


def plot_it(results: DataFrame, save_path: Path | None = None):
    import matplotlib.dates as mdates
    from matplotlib.dates import DateFormatter

    df = results.copy()
    df["date"] = pd.to_datetime(df["date"])

    plt.style.use("seaborn-v0_8-whitegrid")
    fig = plt.figure(figsize=(11, 11))
    gs = fig.add_gridspec(3, 1, height_ratios=[3, 2, 2], hspace=0.35)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2])
    fig.patch.set_facecolor("#fafafa")

    # --- Oberer Plot: Rendite ---
    ax1.set_facecolor("#fafafa")
    ax1.fill_between(df["date"], df["rendite"], alpha=0.15, color="#2196F3")
    ax1.plot(df["date"], df["rendite"], color="#2196F3", linewidth=2.2, label="Rendite", zorder=3)

    rolling = df["rendite"].rolling(window=30, min_periods=1, center=True).mean()
    ax1.plot(df["date"], rolling, color="#FF5722", linestyle="--", linewidth=1.5, alpha=0.8, label="Trend (30d)")

    last = df.iloc[-1]
    ax1.annotate(
        f'{last["rendite"]:.2f} %',
        xy=(last["date"], last["rendite"]),
        xytext=(12, 12), textcoords="offset points",
        fontsize=10, fontweight="bold", color="#2196F3",
        arrowprops=dict(arrowstyle="->", color="#2196F3", lw=1.2),
        zorder=4,
    )

    ax1.set_ylabel("Rendite (%)", fontsize=11, fontweight="medium", color="#333")
    ax1.set_title("Allvest Sparvertrag \u2014 Renditeentwicklung", fontsize=14, fontweight="bold", color="#222", pad=14)
    ax1.legend(frameon=True, fancybox=True, shadow=False, edgecolor="#ddd", fontsize=9, loc="upper left")

    # --- Unterer Plot: Wert ---
    ax2.set_facecolor("#fafafa")
    ax2.fill_between(df["date"], df["saldo"], alpha=0.15, color="#4CAF50")
    ax2.plot(df["date"], df["saldo"], color="#4CAF50", linewidth=2.2, label="Wert (\u20ac)", zorder=3)

    ax2.annotate(
        f'{last["saldo"]:,.0f} \u20ac'.replace(",", "."),
        xy=(last["date"], last["saldo"]),
        xytext=(12, 12), textcoords="offset points",
        fontsize=10, fontweight="bold", color="#4CAF50",
        arrowprops=dict(arrowstyle="->", color="#4CAF50", lw=1.2),
        zorder=4,
    )

    ax2.set_ylabel("Wert (\u20ac)", fontsize=11, fontweight="medium", color="#333")
    ax2.legend(frameon=True, fancybox=True, shadow=False, edgecolor="#ddd", fontsize=9, loc="upper left")

    # --- Dritter Plot: Wert der letzten 7 Tage ---
    df7 = df.tail(7)
    ax3.set_facecolor("#fafafa")
    y_min, y_max = df7["saldo"].min(), df7["saldo"].max()
    y_pad = max((y_max - y_min) * 0.2, 1.0)
    ax3.set_ylim(y_min - y_pad, y_max + y_pad)
    ax3.fill_between(df7["date"], df7["saldo"], y_min - y_pad, alpha=0.15, color="#4CAF50")
    ax3.plot(df7["date"], df7["saldo"], color="#4CAF50", linewidth=2.2,
             marker="o", markersize=5, label="Wert (\u20ac, 7 Tage)", zorder=3)

    last7 = df7.iloc[-1]
    ax3.annotate(
        f'{last7["saldo"]:,.0f} \u20ac'.replace(",", "."),
        xy=(last7["date"], last7["saldo"]),
        xytext=(12, 12), textcoords="offset points",
        fontsize=10, fontweight="bold", color="#4CAF50",
        arrowprops=dict(arrowstyle="->", color="#4CAF50", lw=1.2),
        zorder=4,
    )

    ax3.set_ylabel("Wert (\u20ac)", fontsize=11, fontweight="medium", color="#333")
    ax3.legend(frameon=True, fancybox=True, shadow=False, edgecolor="#ddd", fontsize=9, loc="upper left")
    ax3.xaxis.set_major_locator(mdates.DayLocator())
    ax3.xaxis.set_major_formatter(DateFormatter("%d.%m."))

    # --- Gemeinsames Styling ---
    for ax in (ax1, ax2, ax3):
        ax.yaxis.grid(True, color="#cccccc", linestyle="-", linewidth=0.5, alpha=0.7)
        ax.xaxis.grid(False)
        ax.set_axisbelow(True)
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
        for spine in ["left", "bottom"]:
            ax.spines[spine].set_color("#cccccc")
        ax.tick_params(axis="y", labelsize=9)

    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    ax2.xaxis.set_major_formatter(DateFormatter("%b %Y"))
    ax2.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    ax2.tick_params(axis="x", which="minor", length=3, color="#bbb")
    ax2.tick_params(axis="x", which="major", length=6, labelsize=9)

    fig.autofmt_xdate(rotation=35)

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        log.info("Plot gespeichert: %s", save_path)
    else:
        plt.show()

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    raise SystemExit(main())
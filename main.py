from datetime import datetime
from typing import List, Tuple, Optional
from scipy.optimize import newton

# Eingabedaten: Datum und Betrag (Einzahlungen negativ, Auszahlungen positiv)
CASHFLOWS = [
    (datetime(2025, 3, 23), -16000),  # Start Einzahlung
    (datetime(2025, 6, 1), 12000),  # Abhebung
    (datetime(2025, 8, 11), -700),  # Einzahlung
    (datetime(2025, 11, 18), 4921),  # aktueller Wert inkl. Zinsen
]
# Hilfs-Module-Variablen, werden zur Laufzeit in __main__ befüllt.
times: List[float] = []
amounts: List[float] = []

def npv(rate: float) ->float:
    """
    Net Present Value (NPV) für unregelmäßige Cashflows.

    Diese Funktion diskontiert die globalen Listen `amounts` mit den
    Zeitpunkten `times` (Jahre seit Startdatum) auf den Startzeitpunkt
    und gibt die Summe zurück.

    :param rate: Jahreszinssatz in Dezimalform (z. B. 0.05 für 5%)
                 Muss größer als -1 sein (da (1 + rate) im Nenner steht).
    :raises ValueError: wenn rate <= -1 (diskontierungsbasis ungültig)
    :return: Kapitalwert (float)
    """
    if rate <= -1.0:
        raise ValueError("rate must be greater than -1.0")
    return sum(amounts[i] / (1 + rate) ** times[i] for i in range(len(times)))


# Berechnung des internen Zinsfußes mittels Newton-Verfahren
def xirr(guess: float = 0.05) -> Optional[float]:
    """
    Berechnet den internen Zinsfuß (IRR/XIRR) mittels Newton-Verfahren.

    Es wird das Newton-Raphson-Verfahren (scipy.optimize.newton) auf die
    Funktion `npv` angewandt. Falls das Verfahren nicht konvergiert oder
    numerische Fehler auftreten, wird None zurückgegeben.

    :param guess: Startwert für das Newton-Verfahren (standard 0.05)
    :return: gefundener Jahreszins als Dezimal (z. B. 0.05) oder None bei Fehlern
    """
    try:
        irr = newton(npv, guess)
        return irr
    except (RuntimeError, OverflowError, ValueError):
        # RuntimeError: keine Konvergenz
        # OverflowError: numerische Überläufe
        # ValueError: z. B. invalid operations innerhalb npv (rate <= -1)
        return None


if __name__ == '__main__':

    if __name__ == "__main__":
        # Validierung und Umwandlung: Zeiten in Jahre seit Start und Beträge extrahieren
        if not CASHFLOWS:
            print("Keine Cashflows vorhanden. Fügen Sie mindestens einen Cashflow hinzu.")
            raise SystemExit(1)

        start_date = CASHFLOWS[0][0]
        # Zeiten in Jahren relativ zum Startdatum (365.25 Tage/Jahr zur Schaltjahrsberücksichtigung)
        times = [(cf[0] - start_date).days / 365.25 for cf in CASHFLOWS]
        amounts = [cf[1] for cf in CASHFLOWS]

        # Einfache Plausibilitätsprüfung: es muss mindestens eine positive und eine negative Zahlung geben
        if not any(a > 0 for a in amounts) or not any(a < 0 for a in amounts):
            print(
                "Die Rendite kann nicht berechnet werden: "
                "Die Cashflows müssen mindestens eine Einzahlung (negativ) und eine Auszahlung (positiv) enthalten."
            )
            raise SystemExit(1)

        # Berechnung des IRR
        result = xirr()
        if result is not None:
            print(f"Die berechnete Rendite (IRR) beträgt: {result * 100:.3f}% pro Jahr")
        else:
            print(
                "Die Rendite konnte nicht berechnet werden. "
                "Mögliche Ursachen: das Newton-Verfahren konvergiert nicht mit der aktuellen Schätzung, "
                "numerische Probleme (z. B. rate <= -1), oder die Cashflows erzeugen keinen eindeutigen IRR."
            )
from datetime import datetime
from scipy.optimize import newton

# Eingabedaten: Datum und Betrag (Einzahlungen negativ, Auszahlungen positiv)
CASHFLOWS = [
    (datetime(2025, 3, 23), -16000),  # Start Einzahlung
    (datetime(2025, 6, 1), 12000),  # Abhebung
    (datetime(2025, 8, 11), -700),  # Einzahlung
    (datetime(2025, 11, 18), 4921),  # aktueller Wert inkl. Zinsen
]


def npv(rate):
    """
    Net Present Value. Diese Funktion berechnet den Kapitalwert aller Cashflows bei einem Zinssatz  rate .
    Die Beträge werden mit dem Zinseszinseffekt diskontiert auf den Startzeitpunkt.
    :param rate: Zinssatz
    :return:
    """
    return sum(amounts[i] / (1 + rate) ** times[i] for i in range(len(times)))


# Berechnung des internen Zinsfußes mittels Newton-Verfahren
def xirr(guess=0.05):
    """
    Mit dem Newton-Verfahren wird iterativ die Rendite (interner Zinsfuß) gesucht, bei der der Kapitalwert Null wird.
    :param guess:
    :return:
    """
    try:
        return newton(npv, guess)
    except RuntimeError:
        return None


if __name__ == '__main__':

    start_date = CASHFLOWS[0][0]
    # Umwandlung der Daten in Jahre seit Start und Beträge
    times = [(cf[0] - start_date).days / 365.25 for cf in CASHFLOWS]
    # Für jeden Cashflow wird die Zeitdifferenz zum Startdatum in Jahren berechnet.
    # 365.25 wegen Schaltjahr
    amounts = [cf[1] for cf in CASHFLOWS]
    # Berechnung des Net Present Value
    result = xirr()
    if result is not None:
        print(f"Die berechnete Rendite (IRR) beträgt: {result * 100:.2f}% pro Jahr")
    else:
        print("Die Rendite konnte nicht berechnet werden.")

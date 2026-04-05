#!/usr/bin/env python3
"""
Automatisches Auslesen des Allvest-Kontostands via Playwright.

Voraussetzungen:
  - ALLVEST_USER und ALLVEST_PASSWORD als Umgebungsvariablen (oder in .env)

Usage:
  python fetch_allvest.py              # Kurswert holen und cashflows.json aktualisieren
  python fetch_allvest.py --dry-run    # Nur Kurswert anzeigen, nichts speichern
  python fetch_allvest.py --debug      # Browser sichtbar + Screenshots + Pause
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import smtplib
import subprocess
import sys
from datetime import date
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, TimeoutError as PwTimeout

log = logging.getLogger(__name__)

load_dotenv()

ALLVEST_LOGIN_URL = (
    "https://cim.allianz.de/ui/login/de/allianz/start?goto=https:%2F%2Fcim.allianz.de:443%2Fauth%2Foauth2%2Frealms%2Froot%2Frealms%2Feu1%2Fauthorize%3Fclient_id%3D471tqy1trp3cdba196w50ot74k38sel9ud45lyyg%26state%3Dcockpit,%25252Fcockpit%25252Fdetails%25252Fbff-contract-899f9940-4c43-48fd-93ec-9"
    "abf8da7c767,97ced729-d1da-4ebc-88c1-d7635f17f404%26scope%3Dopenid%2520profile%2520abs_basic%2520az_basic%26redirect_uri%3Dhttps:%2F%2Fwww.allvest.de%2Fgw%2Fsilentlogin%26response_type%3Dcode%26nonce%3DsMmocW3plNUGzTzf&realm=%2Feu1"
)

CASHFLOWS_FILE = Path(__file__).parent / "cashflows.json"
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
BROWSER_PROFILE_DIR = Path(__file__).parent / ".browser-profile"


def parse_german_number(text: str) -> float | None:
    """Parse a German-formatted number like '15.310,42' or '15310,42' to float."""
    cleaned = re.sub(r"[€\s\xa0]", "", text.strip())
    if not cleaned:
        return None
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_value_from_text(text: str) -> float | None:
    """Try to extract a monetary value from page text."""
    patterns = [
        r"(\d{1,3}(?:\.\d{3})*,\d{2})",   # 15.310,42
        r"(\d{4,},\d{2})",                  # 15310,42
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            value = parse_german_number(match.group(1))
            if value and value > 100:
                return value
    return None


def screenshot(page: Page, name: str, debug: bool) -> None:
    """Save a screenshot if in debug mode."""
    if debug:
        SCREENSHOT_DIR.mkdir(exist_ok=True)
        path = SCREENSHOT_DIR / f"{name}.png"
        page.screenshot(path=str(path))
        log.debug("Screenshot: %s", path)


def fetch_kurswert(headless: bool = True, debug: bool = False) -> float:
    """Use Playwright to log into Allvest and extract the current account value."""
    user = os.environ.get("ALLVEST_USER")
    password = os.environ.get("ALLVEST_PASSWORD")

    if not user or not password:
        raise RuntimeError(
            "ALLVEST_USER und ALLVEST_PASSWORD muessen als Umgebungsvariablen gesetzt sein."
        )

    with sync_playwright() as p:
        # Persistenter Browser-Kontext: Cookies/Sessions bleiben erhalten
        BROWSER_PROFILE_DIR.mkdir(exist_ok=True)
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=headless,
            viewport={"width": 1280, "height": 900},
            locale="de-DE",
        )
        page = context.new_page()

        # 1) Login-Seite oeffnen
        log.info("Oeffne Login-Seite...")
        page.goto(ALLVEST_LOGIN_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        screenshot(page, "01_page", debug)

        # Pruefen ob wir bereits eingeloggt sind (persistente Session)
        login_form = page.locator('input[name="usernameInput"]')
        if login_form.count() == 0:
            log.info("Bereits eingeloggt (Session aktiv).")
        else:
            # 2) E-Mail eingeben
            log.info("Gebe Benutzername ein...")
            email_input = page.locator('input[name="usernameInput"]')
            email_input.wait_for(state="visible", timeout=15000)
            email_input.fill(user)

            # 3) Passwort eingeben
            log.info("Gebe Passwort ein...")
            pw_input = page.locator('input[type="password"]')
            pw_input.wait_for(state="visible", timeout=15000)
            pw_input.fill(password)

            # 4) Login-Button klicken
            log.info("Klicke Anmelden...")
            login_btn = page.get_by_role("button", name="Anmelden")
            login_btn.click()
            screenshot(page, "02_after_login", debug)

            # 5) Pruefen ob 2FA-Seite erscheint (E-Mail-Code)
            page.wait_for_timeout(3000)
            if "mail-code" in page.url or "unbekannt" in page.inner_text("body").lower():
                screenshot(page, "03_2fa_page", debug)
                log.warning("2FA-Verifizierung erforderlich!")
                log.info("Allvest hat einen Code an deine E-Mail geschickt.")
                log.info("Bitte gib den Code im Browser-Fenster ein und klicke 'Weiter'.")
                log.info("Warte auf Weiterleitung zum Dashboard...")
                try:
                    page.wait_for_url("**/allvest.de/**", timeout=300000)
                except PwTimeout:
                    log.warning("Timeout - aktuelle URL: %s", page.url)
                    if "mail-code" in page.url:
                        context.close()
                        raise RuntimeError("2FA-Code wurde nicht eingegeben (Timeout).")
            else:
                log.info("Warte auf Dashboard...")
                try:
                    page.wait_for_url("**/allvest.de/**", timeout=30000)
                except PwTimeout:
                    log.warning("Aktuelle URL: %s", page.url)

        # Warte auf allvest.de Dashboard
        log.info("Warte auf Dashboard...")
        try:
            page.wait_for_url("**/www.allvest.de/**", timeout=30000)
        except PwTimeout:
            log.warning("URL nach Timeout: %s", page.url)
        page.wait_for_load_state("networkidle", timeout=30000)
        screenshot(page, "04_dashboard", debug)

        # 6) Kurswert suchen
        log.info("Suche Kurswert...")
        # Warte auf dynamisch geladene Inhalte
        page.wait_for_timeout(8000)
        screenshot(page, "06_dashboard_loaded", debug)

        # Versuche den Wert aus dem Seitentext zu extrahieren
        page_text = page.inner_text("body")

        if debug:
            text_path = SCREENSHOT_DIR / "page_text.txt"
            text_path.write_text(page_text, encoding="utf-8")
            log.debug("Seitentext gespeichert: %s", text_path)

        value = extract_value_from_text(page_text)

        if value is None:
            screenshot(page, "07_value_not_found", True)
            # Im Debug-Modus: Browser offen lassen
            if debug:
                log.error("Kurswert nicht automatisch gefunden.")
                log.info("Browser bleibt offen — schau dir die Seite an.")
                log.info("Seitentext wurde gespeichert in screenshots/page_text.txt")
                input("  Druecke Enter zum Beenden...")
            context.close()
            raise RuntimeError(
                "Kurswert konnte nicht aus der Seite extrahiert werden. "
                "Starte mit --debug um Screenshots zu sehen."
            )

        context.close()
        return value


def update_cashflows(value: float, cashflows_path: Path = CASHFLOWS_FILE) -> None:
    """Update cashflows.json with today's value as the last entry."""
    data = json.loads(cashflows_path.read_text(encoding="utf-8"))
    today = str(date.today())

    last_entry = data[-1]
    if last_entry["date"] == today:
        last_entry["amount"] = value
    else:
        last_entry["date"] = today
        last_entry["amount"] = value

    cashflows_path.write_text(
        json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8"
    )
    log.info("cashflows.json aktualisiert: %s -> %.2f EUR", today, value)


PLOT_FILE = Path(__file__).parent / "rendite_plot.png"


def run_main_py() -> tuple[int, str]:
    """Run the existing main.py to calculate XIRR using its own venv."""
    main_py = Path(__file__).parent / "main.py"
    venv_python = Path(__file__).parent / ".venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable
    result = subprocess.run(
        [python, str(main_py), "--save-plot", str(PLOT_FILE)],
        cwd=str(main_py.parent),
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    log.info("main.py Ausgabe:\n%s", output)
    return result.returncode, output


def build_html_email(today: str, value: float, rendite_str: str, laufzeit: str, plot_path: Path | None) -> str:
    """Build a nice HTML email body."""
    # Kurswert deutsch formatieren (Komma als Dezimaltrennzeichen, kein Tausendertrenner)
    value_str = f"{value:.2f}".replace(".", ",")
    # Rendite deutsch formatieren
    rendite_str = rendite_str.replace(".", ",")
    # Embed plot as inline image if available
    plot_html = ""
    if plot_path and plot_path.exists():
        plot_html = '<img src="cid:rendite_plot" style="max-width:100%;border-radius:8px;margin-top:8px;" />'

    return f"""\
<html>
<body style="margin:0;padding:0;font-family:'Helvetica Neue',Arial,sans-serif;background:#f4f4f7;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f7;padding:24px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#003781,#0070c0);padding:28px 32px;">
            <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:600;">Allvest Active 80</h1>
            <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:14px;">Tagesbericht {today}</p>
          </td>
        </tr>
        <!-- Rendite -->
        <tr>
          <td style="padding:32px 32px 16px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:#f0f7ff;border-radius:10px;padding:24px;text-align:center;">
                  <p style="margin:0 0 4px;font-size:13px;color:#666;text-transform:uppercase;letter-spacing:1px;">Rendite (IRR)</p>
                  <p style="margin:0;font-size:36px;font-weight:700;color:#003781;">{rendite_str} <span style="font-size:18px;color:#666;">p.a.</span></p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <!-- Kurswert & Laufzeit -->
        <tr>
          <td style="padding:0 32px 24px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td width="50%" style="background:#fafafa;border-radius:10px;padding:18px;text-align:center;">
                  <p style="margin:0 0 4px;font-size:12px;color:#888;text-transform:uppercase;letter-spacing:1px;">Kurswert</p>
                  <p style="margin:0;font-size:22px;font-weight:600;color:#222;">{value_str} &euro;</p>
                </td>
                <td width="8"></td>
                <td width="50%" style="background:#fafafa;border-radius:10px;padding:18px;text-align:center;">
                  <p style="margin:0 0 4px;font-size:12px;color:#888;text-transform:uppercase;letter-spacing:1px;">Laufzeit</p>
                  <p style="margin:0;font-size:16px;font-weight:600;color:#222;">{laufzeit}</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <!-- Plot -->
        <tr>
          <td style="padding:0 32px 32px;">
            {plot_html}
          </td>
        </tr>
        <!-- Footer -->
        <tr>
          <td style="padding:16px 32px;border-top:1px solid #eee;">
            <p style="margin:0;font-size:11px;color:#aaa;text-align:center;">DailyAllvestKursAgent</p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_email(subject: str, html_body: str, attachment: Path | None = None) -> None:
    """Send HTML email via 1und1 SMTP with optional inline image."""
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.image import MIMEImage
    from email.utils import formataddr

    smtp_host = os.environ.get("SMTP_HOST", "smtp.1und1.de")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")

    if not smtp_user or not smtp_password:
        raise RuntimeError("SMTP_USER und SMTP_PASSWORD muessen in .env gesetzt sein.")

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = formataddr(("DailyAllvestKursAgent", smtp_user))
    msg["To"] = smtp_user

    msg.attach(MIMEText(html_body, "html"))

    if attachment and attachment.exists():
        img = MIMEImage(attachment.read_bytes(), _subtype="png")
        img.add_header("Content-ID", "<rendite_plot>")
        img.add_header("Content-Disposition", "inline", filename=attachment.name)
        msg.attach(img)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)

    log.info("E-Mail gesendet an %s", smtp_user)


def main() -> int:
    parser = argparse.ArgumentParser(description="Allvest Kurswert automatisch auslesen")
    parser.add_argument(
        "--dry-run", action="store_true", help="Nur Kurswert anzeigen, nichts speichern"
    )
    parser.add_argument(
        "--skip-rendite", action="store_true", help="main.py nicht ausfuehren"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Browser sichtbar, Screenshots speichern, bei Fehler pausieren"
    )
    parser.add_argument(
        "--mail", action="store_true",
        help="Ergebnis per E-Mail senden"
    )
    args = parser.parse_args()

    headless = not args.debug
    log.info("Hole aktuellen Allvest-Kurswert...")
    value = fetch_kurswert(headless=headless, debug=args.debug)
    log.info("Aktueller Kurswert: %.2f EUR", value)

    if args.dry_run:
        log.info("Dry-run: nichts gespeichert")
        return 0

    update_cashflows(value)

    rendite_output = ""
    if not args.skip_rendite:
        log.info("Berechne Rendite...")
        rc, rendite_output = run_main_py()

    if args.mail:
        today = date.today().strftime("%d.%m.%Y")
        # Rendite aus Output parsen
        rendite_match = re.search(r"(\d+\.\d+)%", rendite_output)
        rendite_str = f"{float(rendite_match.group(1)):.2f}%" if rendite_match else "n/a"
        # Laufzeit parsen
        laufzeit_match = re.search(r"([\d]+ year.*)", rendite_output)
        laufzeit = laufzeit_match.group(1).strip() if laufzeit_match else ""

        subject = f"Allvest Report {today}"
        html = build_html_email(today, value, rendite_str, laufzeit, PLOT_FILE)
        plot = PLOT_FILE if PLOT_FILE.exists() else None
        send_email(subject, html, attachment=plot)

    return 0


if __name__ == "__main__":
    # --debug wird vorab geprüft, um Log-Level vor main() zu setzen
    level = logging.DEBUG if "--debug" in sys.argv else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    raise SystemExit(main())

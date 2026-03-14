#!/usr/bin/env python3
"""
update_prices.py
Pobiera aktualne ceny z Yahoo Finance i aktualizuje Analiza_Portfela_2026.html
Uruchamiany przez GitHub Actions codziennie o 17:00 UTC.
"""

import yfinance as yf
import re
from datetime import datetime, timezone
import sys

HTML_FILE = "Analiza_Portfela_2026.html"

# ── Skład portfela ─────────────────────────────────────────────────
# (ticker_yahoo, nazwa_display, wolumen, cena_otwarcia_pozycji, waluta_pl)
PORTFOLIO = [
    ("ASML",   "ASML Holding",      0.7000,   1208.93, False),
    ("FLR",    "Fluor Corp.",       18.6398,     43.39, False),
    ("PLAB",   "Photronics",        20.5209,     33.20, False),
    ("KLAC",   "KLA-Tencor",         0.4493,   1429.49, False),
    ("LBW.WA", "Lubawa SA",         249.0000,     9.415, True),  # PLN
    ("CEG",    "Constellation En.", 2.0199,    320.10, False),
    ("MU",     "Micron Tech.",       0.8528,    406.26, False),
    ("FLS",    "Flowserve",          2.9999,     76.83, False),
]

PLN_USD_RATE = 0.244   # fallback — skrypt próbuje pobrać live


def get_pln_usd():
    """Pobierz aktualny kurs PLN/USD."""
    try:
        t = yf.Ticker("PLN=X")
        hist = t.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return PLN_USD_RATE


def fetch_prices(tickers: list[str]) -> dict[str, float]:
    """Pobierz ostatnie ceny zamknięcia dla listy tickerów."""
    prices = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="2d")
            if not hist.empty:
                prices[ticker] = float(hist["Close"].iloc[-1])
                print(f"  {ticker}: {prices[ticker]:.3f}")
            else:
                print(f"  {ticker}: BRAK DANYCH — pomijam", file=sys.stderr)
        except Exception as e:
            print(f"  {ticker}: błąd ({e})", file=sys.stderr)
    return prices


def fmt_usd(v: float) -> str:
    """Formatuj wartość USD z separatorem tysięcy."""
    return f"${int(round(v)):,}".replace(",", " ")


def fmt_pnl(v: float, pln: bool) -> str:
    """Formatuj P&L z odpowiednim symbolem waluty."""
    sym  = "zł" if pln else "$"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f} {sym}" if pln else f"{sign}${abs(v):.1f}" if v < 0 else f"+${v:.1f}"


def patch_html(html: str, prices: dict, rate: float) -> str:
    """Zaktualizuj kluczowe wartości w HTML."""

    rows_data = []
    total_val  = 0.0
    total_pnl  = 0.0

    for ticker, name, vol, open_price, is_pln in PORTFOLIO:
        if ticker not in prices:
            print(f"  UWAGA: brak ceny dla {ticker}, pomijam aktualizację wiersza")
            continue

        curr = prices[ticker]
        pnl_native = (curr - open_price) * vol          # w natywnej walucie
        pnl_pct    = (curr - open_price) / open_price * 100

        if is_pln:
            val_usd  = curr * vol * rate
            pnl_usd  = pnl_native                        # zostawiamy w PLN do wyświetlenia
        else:
            val_usd  = curr * vol
            pnl_usd  = pnl_native

        total_val += val_usd
        total_pnl += pnl_usd if not is_pln else pnl_native * rate

        rows_data.append({
            "ticker": ticker,
            "name":   name,
            "curr":   curr,
            "val":    val_usd,
            "pnl":    pnl_native,
            "pnl_pct": pnl_pct,
            "is_pln": is_pln,
            "open":   open_price,
        })

    # ── 1. Łączna wartość portfela w KPI ──────────────────────────
    total_str = fmt_usd(total_val).replace("$", "")
    html = re.sub(
        r'(<div class="kpi-val">\$)([\d\s]+)(</div>\s*<div class="kpi-label">Wartość portfela)',
        rf'\g<1>{total_str}\3',
        html
    )

    # ── 2. Wiersz RAZEM w tabeli pozycji ──────────────────────────
    total_pnl_pct = total_pnl / (total_val - total_pnl) * 100 if total_val else 0
    pnl_sign = "+" if total_pnl >= 0 else ""
    pnl_cls  = "green" if total_pnl >= 0 else "red"
    html = re.sub(
        r'(<tr class="tfoot-row">.*?<td><strong>)([\d\s]+)(</strong></td><td class="(?:red|green)"><strong>)([^<]+)(</strong></td><td class="(?:red|green)"><strong>)([^<]+)(</strong></td>)',
        rf'\g<1>{total_str}\3<span class="{pnl_cls}">{pnl_sign}${abs(total_pnl):.1f}</span>\5<span class="{pnl_cls}">{pnl_sign}{total_pnl_pct:.2f}%</span>\7',
        html, flags=re.DOTALL
    )

    # ── 3. Aktualna cena każdej spółki w tabeli pozycji ───────────
    for d in rows_data:
        ticker = d["ticker"]
        curr   = d["curr"]
        val    = d["val"]
        pnl    = d["pnl"]
        pct    = d["pnl_pct"]
        pln    = d["is_pln"]

        pnl_cls = "green" if pnl >= 0 else "red"

        if pln:
            curr_str = f"zł {curr:.3f}"
            pnl_str  = f"{'+' if pnl>=0 else ''}{pnl:.1f} zł"
        else:
            curr_str = f"${curr:.2f}"
            pnl_str  = f"{'+$' if pnl>=0 else '-$'}{abs(pnl):.1f}"

        val_str = fmt_usd(val)
        pct_str = f"{'+' if pct>=0 else ''}{pct:.2f}%"

        # Znajdź wiersz tabeli dla tej spółki po tickerze i zaktualizuj cena akt + wartość + P&L
        # Pattern: <td>curr_price</td><td>value</td><td class="...">pnl$</td><td class="...">pnl%</td>
        pattern = (
            rf'(<td><strong>{re.escape(d["name"])}</strong></td>'
            rf'<td>{re.escape(ticker)}</td>'
            rf'<td>[^<]+</td>'           # wolumen
            rf'<td>[^<]+</td>)'          # cena otw
            rf'<td>[^<]+</td>'           # cena akt — AKTUALIZUJEMY
            rf'<td>[^<]+</td>'           # wartość — AKTUALIZUJEMY
            rf'<td class="(?:red|green)">[^<]+</td>'   # P&L $ — AKTUALIZUJEMY
            rf'<td class="(?:red|green)">[^<]+</td>'   # P&L % — AKTUALIZUJEMY
        )
        replacement = (
            rf'\1'
            rf'<td>{curr_str}</td>'
            rf'<td>{val_str}</td>'
            rf'<td class="{pnl_cls}">{pnl_str}</td>'
            rf'<td class="{pnl_cls}">{pct_str}</td>'
        )
        html_new = re.sub(pattern, replacement, html)
        if html_new != html:
            print(f"  ✓ zaktualizowano wiersz: {d['name']}")
        else:
            print(f"  ✗ nie znaleziono wzorca dla: {d['name']}")
        html = html_new

    # ── 4. Data ostatniej aktualizacji w stopce ───────────────────
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = re.sub(
        r'(Wygenerowano przez Claude \(Anthropic\) · )([^\n<]+)',
        rf'\g<1>Marzec 2026 · Aktualizacja cen: {now}',
        html
    )

    return html


def main():
    print("=== Aktualizacja portfela ===")
    print(f"Plik: {HTML_FILE}")

    tickers = [t for t, *_ in PORTFOLIO]

    print("\n[1/3] Pobieranie kursu PLN/USD...")
    rate = get_pln_usd()
    print(f"  PLN/USD: {rate:.4f}")

    print("\n[2/3] Pobieranie cen akcji...")
    prices = fetch_prices(tickers)

    if not prices:
        print("BŁĄD: Brak cen — przerywam.", file=sys.stderr)
        sys.exit(1)

    print(f"\n[3/3] Aktualizacja {HTML_FILE}...")
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    html_updated = patch_html(html, prices, rate)

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html_updated)

    print(f"\n✅ Gotowe! Zaktualizowano {HTML_FILE}")


if __name__ == "__main__":
    main()

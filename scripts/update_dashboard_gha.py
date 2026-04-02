import yfinance as yf
import re
from datetime import datetime, timezone
import json
import base64
import os
import urllib.request

TOKEN = os.environ.get("GH_PAT")
REPO = "kamilbrzuszczak-ship-it/diracpl"
TARGET = "portfolio-dashboard.html"

def fetch_prices(tickers):
    prices = {}
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            hist = tk.history(period="1d")
            if not hist.empty:
                prices[t] = float(hist["Close"].iloc[-1])
        except Exception as e:
            print(f"Error fetching {t}: {e}")
    return prices

def main():
    if not TOKEN:
        print("Brak GH_PAT")
        return

    # Pobierz aktualny HTML
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/contents/{TARGET}")
    req.add_header("Authorization", f"token {TOKEN}")
    try:
        res = urllib.request.urlopen(req).read()
    except Exception as e:
        print("Nie można pobrać pliku:", e)
        return
        
    data = json.loads(res)
    sha = data["sha"]
    html = base64.b64decode(data["content"]).decode('utf-8')

    prices = fetch_prices(["MU", "SATL", "AVGO", "AMKR", "APH", "AMPX"])
    if not prices:
        print("Brak pobranych cen!")
        return

    
    # Słownik z danymi wejścia z Twojego portfela (z wolumenem do wagi)
    entries = {
        "MU": {"entry": 350.0, "sl": 314.0, "tp": 512.0, "shares": 5.46},
        "SATL": {"entry": 6.00, "sl": 4.80, "tp": 12.0, "shares": 145.0},
        "AVGO": {"entry": 313.94, "sl": 288.0, "tp": 470.0, "shares": 2.42},
        "AMKR": {"entry": 46.80, "sl": 40.30, "tp": 66.30, "shares": 22.92}
    }
,
        "SATL": {"entry": 6.00, "sl": 4.80, "tp": 12.0},
        "AVGO": {"entry": 313.94, "sl": 288.0, "tp": 470.0},
        "AMKR": {"entry": 46.80, "sl": 40.30, "tp": 66.30}
    }

    # Wstaw badge LIVE w nagłówku
    html = re.sub(
        r'(<div class="header-date">[^<]+)(</div>)',
        lambda m: m.group(1) + ('' if 'LIVE' in m.group(1) else ' <span style="color:var(--green);font-weight:bold;">· 🟢 LIVE</span>') + m.group(2),
        html
    )

    
    # Aktualizacja skryptu Chart.js w HTML (Wstrzykiwanie aktualnych wartości portfela USD)
    live_values = {}
    for t in ["MU", "SATL", "AVGO", "AMKR"]:
        if t in prices:
            live_values[t] = round(prices[t] * entries[t]["shares"], 2)
        else:
            live_values[t] = round(entries[t]["entry"] * entries[t]["shares"], 2)

    chart_data_js = f'const liveChartData = {{ "MU": {live_values["MU"]}, "SATL": {live_values["SATL"]}, "AVGO": {live_values["AVGO"]}, "AMKR": {live_values["AMKR"]} }};'
    html = re.sub(r'// CHART_DATA_START.*?// CHART_DATA_END', f'// CHART_DATA_START\n{chart_data_js}\n// CHART_DATA_END', html, flags=re.DOTALL)

    # 1. Aktualizacja KART PORTFELA

    for ticker in ["MU", "SATL", "AVGO", "AMKR"]:
        if ticker not in prices: continue
        price = prices[ticker]
        data = entries[ticker]
        
        # Obliczenia
        pnl_pct = ((price - data["entry"]) / data["entry"]) * 100
        pnl_str = f"{'▲ +' if pnl_pct >= 0 else '▼ '}{pnl_pct:.1f}%"
        pnl_cls = "c-green" if pnl_pct >= 0 else "c-red"
        
        # Pozycja kursora
        sl = data["sl"]
        tp = data["tp"]
        pct = ((price - sl) / (tp - sl)) * 100
        pct = max(0, min(100, pct))
        cursor_style = f"left:{pct:.1f}%;"
        
        # Regex dla karty portfela
        # a) Cena
        html = re.sub(
            rf'(<div class="pos-card {ticker.lower()}".*?<div class="card-price-now [^"]+">)([^<]+)(</div>)',
            rf'\g<1>${price:.2f}\3',
            html,
            flags=re.DOTALL
        )
        # b) P&L
        html = re.sub(
            rf'(<div class="pos-card {ticker.lower()}".*?<div class="card-pnl )([^"]+)(">)([^<]+)(</div>)',
            rf'\g<1>{pnl_cls}\3{pnl_str}\5',
            html,
            flags=re.DOTALL
        )
        # c) Data (zmiana na LIVE)
        html = re.sub(
            rf'(<div class="pos-card {ticker.lower()}".*?<div class="card-price-date">)([^<]+)(</div>)',
            rf'\g<1><span style="color:var(--green);">🟢 LIVE</span>\3',
            html,
            flags=re.DOTALL
        )
        # d) Kursor
        html = re.sub(
            rf'(<div class="pos-card {ticker.lower()}".*?<div class="price-cursor" style=")([^"]+)(" title=")[^"]+("></div>)',
            rf'\g<1>{cursor_style}\3Teraz ${price:.2f}\4',
            html,
            flags=re.DOTALL
        )

    # 2. Aktualizacja KANDYDATÓW
    for ticker in ["APH", "AMPX"]:
        if ticker not in prices: continue
        price = prices[ticker]
        
        html = re.sub(
            rf'(<div class="cand-ticker[^>]+>{ticker}</div>.*?<div class="cand-price">)([^<]+)(</div>)',
            rf'\g<1>${price:.2f} 🟢\3',
            html,
            flags=re.DOTALL
        )

    # Oblicz i uaktualnij Avg P&L w Hero Stats
    # Obliczamy go jako średnią prostą z P&L% dla 4 aktywnych pozycji (jak w pierwotnym HTMLu)
    if all(t in prices for t in ["MU", "SATL", "AVGO", "AMKR"]):
        avg_pnl = sum(((prices[t] - entries[t]["entry"]) / entries[t]["entry"]) * 100 for t in ["MU", "SATL", "AVGO", "AMKR"]) / 4
        avg_pnl_str = f"{'+' if avg_pnl > 0 else ''}{avg_pnl:.1f}%"
        avg_pnl_cls = "c-green" if avg_pnl > 0 else "c-red"
        
        html = re.sub(
            r'(<div class="hero-stat-val )([^"]+)(">)([^<]+)(</div>\s*<div class="hero-stat-lbl">Avg P&amp;L portfela)',
            rf'\g<1>{avg_pnl_cls}\3{avg_pnl_str}\5',
            html
        )
        
        # update the glow color
        html = re.sub(
            r'(Avg P&amp;L portfela</div>\s*<div class="hero-stat-sub">[^<]+</div>\s*<div class="hero-stat-glow" style="background:linear-gradient\(90deg,var\(--)[a-z]+(\),transparent\)"></div>)',
            rf'Avg P&amp;L portfela</div>\n    <div class="hero-stat-sub">aktualizowane LIVE</div>\n    <div class="hero-stat-glow" style="background:linear-gradient(90deg,var(--{"green" if avg_pnl > 0 else "red"}),transparent)"></div>',
            html
        )

    # 3. Aktualizacja Tabela Zbiorcza (Master Table)
    for ticker in ["MU", "SATL", "AVGO", "AMKR"]:
        if ticker not in prices: continue
        price = prices[ticker]
        data = entries[ticker]
        pnl_pct = ((price - data["entry"]) / data["entry"]) * 100
        pnl_str = f"{'▲ +' if pnl_pct >= 0 else '▼ '}{pnl_pct:.1f}%"
        pnl_cls = "c-green" if pnl_pct >= 0 else "c-red"
        
        html = re.sub(
            rf'(<strong class="[a-z-]+" style="[^"]+">{ticker}</strong>.*?<td class="tr[^"]*">)~\$?\d+\.?\d*(</td>\s*<td class="tr )([^"]+)(">)[^<]+(</td>)',
            rf'\g<1>${price:.2f}\2{pnl_cls}\4{pnl_str}\5',
            html,
            flags=re.DOTALL
        )
        
    for ticker in ["APH", "AMPX"]:
        if ticker not in prices: continue
        price = prices[ticker]
        html = re.sub(
            rf'(<strong class="[a-z-]+" style="[^"]+">{ticker}</strong>.*?<td class="tr c-dim">—</td>\s*<td class="tr">)([^<]+)(</td>)',
            rf'\g<1>${price:.2f}\3',
            html,
            flags=re.DOTALL
        )

    # Usuńmy JS Opcji A, żeby nie śmiecił
    html = re.sub(r'<!-- ═══ LIVE DATA SCRIPT ═══ -->.*?</script>\n</body>', '</body>', html, flags=re.DOTALL)

    # Wypchnij
    content_b64 = base64.b64encode(html.encode('utf-8')).decode()
    payload = {
        "message": "Automatyczna aktualizacja cen akcji (GitHub Actions)",
        "content": content_b64,
        "sha": sha
    }
    
    req_put = urllib.request.Request(f"https://api.github.com/repos/{REPO}/contents/{TARGET}", method="PUT")
    req_put.add_header("Authorization", f"token {TOKEN}")
    req_put.add_header("Content-Type", "application/json")
    try:
        res_put = urllib.request.urlopen(req_put, data=json.dumps(payload).encode('utf-8')).read()
        print("OK - zapisano w repo.")
    except Exception as e:
        print("Błąd zapisu w repo:", e)

if __name__ == "__main__":
    main()

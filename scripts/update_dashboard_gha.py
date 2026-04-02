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

    entries = {
        "MU": {"entry": 350.0, "sl": 314.0, "tp": 512.0, "shares": 5.46},
        "SATL": {"entry": 6.00, "sl": 4.80, "tp": 12.0, "shares": 145.0},
        "AVGO": {"entry": 313.94, "sl": 288.0, "tp": 470.0, "shares": 2.42},
        "AMKR": {"entry": 46.80, "sl": 40.30, "tp": 66.30, "shares": 22.92}
    }

    html = re.sub(
        r'(<div class="header-date">[^<]+)(</div>)',
        lambda m: m.group(1) + ('' if 'LIVE' in m.group(1) else ' <span style="color:var(--green);font-weight:bold;">· 🟢 LIVE</span>') + m.group(2),
        html
    )

    live_values = {}
    total_invested = 0.0
    total_current_val = 0.0

    for t in ["MU", "SATL", "AVGO", "AMKR"]:
        invested = entries[t]["entry"] * entries[t]["shares"]
        total_invested += invested
        if t in prices:
            live_val = prices[t] * entries[t]["shares"]
            live_values[t] = round(live_val, 2)
            total_current_val += live_val
        else:
            live_values[t] = round(invested, 2)
            total_current_val += invested

    chart_data_js = f'const liveChartData = {{ "MU": {live_values["MU"]}, "SATL": {live_values["SATL"]}, "AVGO": {live_values["AVGO"]}, "AMKR": {live_values["AMKR"]} }};'
    html = re.sub(r'// CHART_DATA_START.*?// CHART_DATA_END', f'// CHART_DATA_START\n{chart_data_js}\n// CHART_DATA_END', html, flags=re.DOTALL)

    for ticker in ["MU", "SATL", "AVGO", "AMKR"]:
        if ticker not in prices: continue
        price = prices[ticker]
        data = entries[ticker]
        
        pnl_pct = ((price - data["entry"]) / data["entry"]) * 100
        pnl_str = f"{'▲ +' if pnl_pct >= 0 else '▼ '}{pnl_pct:.1f}%"
        pnl_cls = "c-green" if pnl_pct >= 0 else "c-red"
        
        sl = data["sl"]
        tp = data["tp"]
        pct = ((price - sl) / (tp - sl)) * 100
        pct = max(0, min(100, pct))
        cursor_style = f"left:{pct:.1f}%;"
        
        html = re.sub(
            rf'(<div class="pos-card {ticker.lower()}".*?<div class="card-price-now [^"]+">)([^<]+)(</div>)',
            rf'\g<1>${price:.2f}',
            html, flags=re.DOTALL
        )
        html = re.sub(
            rf'(<div class="pos-card {ticker.lower()}".*?<div class="card-pnl )([^"]+)(">)([^<]+)(</div>)',
            rf'\g<1>{pnl_cls}{pnl_str}',
            html, flags=re.DOTALL
        )
        html = re.sub(
            rf'(<div class="pos-card {ticker.lower()}".*?<div class="card-price-date">)([^<]+)(</div>)',
            rf'\g<1><span style="color:var(--green);">🟢 LIVE</span>',
            html, flags=re.DOTALL
        )
        html = re.sub(
            rf'(<div class="pos-card {ticker.lower()}".*?<div class="price-cursor" style=")([^"]+)(" title=")[^"]+("></div>)',
            rf'\g<1>{cursor_style}Teraz ${price:.2f}',
            html, flags=re.DOTALL
        )

    for ticker in ["APH", "AMPX"]:
        if ticker not in prices: continue
        price = prices[ticker]
        html = re.sub(
            rf'(<div class="cand-ticker[^>]+>{ticker}</div>.*?<div class="cand-price">)([^<]+)(</div>)',
            rf'\g<1>${price:.2f} 🟢',
            html, flags=re.DOTALL
        )

    # Calculate Total P&L
    total_pnl_usd = total_current_val - total_invested
    total_pnl_pct = (total_pnl_usd / total_invested) * 100
    pnl_usd_str = f"{'+' if total_pnl_usd >= 0 else '-'}${abs(total_pnl_usd):,.2f}"
    pnl_pct_str = f"{'+' if total_pnl_pct >= 0 else ''}{total_pnl_pct:.2f}%"
    pnl_cls = "c-green" if total_pnl_usd >= 0 else "c-red"
    
    # Replace the FIRST hero stat (previously Avg P&L)
    html = re.sub(
        r'(<div class="hero-stat-val )([^"]+)(">)([^<]+)(</div>\s*<div class="hero-stat-lbl">)[^<]+(</div>\s*<div class="hero-stat-sub">)[^<]+(</div>\s*<div class="hero-stat-glow" style="background:linear-gradient\(90deg,var\(--)[a-z]+(\),transparent\)"></div>)',
        rf'\g<1>{pnl_cls}{pnl_usd_str}Total P&amp;L (USD)Val: ${total_current_val:,.2f} ({pnl_pct_str}){"green" if total_pnl_usd >= 0 else "red"}\8',
        html, count=1
    )

    for ticker in ["MU", "SATL", "AVGO", "AMKR"]:
        if ticker not in prices: continue
        price = prices[ticker]
        data = entries[ticker]
        pnl_pct = ((price - data["entry"]) / data["entry"]) * 100
        pnl_str = f"{'▲ +' if pnl_pct >= 0 else '▼ '}{pnl_pct:.1f}%"
        pnl_cls = "c-green" if pnl_pct >= 0 else "c-red"
        
        html = re.sub(
            rf'(<strong class="[a-z-]+" style="[^"]+">{ticker}</strong>.*?<td class="tr[^"]*">)~\$?\d+\.?\d*(</td>\s*<td class="tr )([^"]+)(">)[^<]+(</td>)',
            rf'\g<1>${price:.2f}{pnl_cls}{pnl_str}',
            html, flags=re.DOTALL
        )
        
    for ticker in ["APH", "AMPX"]:
        if ticker not in prices: continue
        price = prices[ticker]
        html = re.sub(
            rf'(<strong class="[a-z-]+" style="[^"]+">{ticker}</strong>.*?<td class="tr c-dim">—</td>\s*<td class="tr">)([^<]+)(</td>)',
            rf'\g<1>${price:.2f}',
            html, flags=re.DOTALL
        )

    html = re.sub(r'<!-- ═══ LIVE DATA SCRIPT ═══ -->.*?</script>\n</body>', '</body>', html, flags=re.DOTALL)

    content_b64 = base64.b64encode(html.encode('utf-8')).decode()
    payload = {
        "message": "Fix syntax error and add Total Portfolio Value / Total P&L metrics",
        "content": content_b64,
        "sha": sha
    }
    
    req_put = urllib.request.Request(f"https://api.github.com/repos/{REPO}/contents/{TARGET}", method="PUT")
    req_put.add_header("Authorization", f"token {TOKEN}")
    req_put.add_header("Content-Type", "application/json")
    try:
        res_put = urllib.request.urlopen(req_put, data=json.dumps(payload).encode('utf-8')).read()
        print("OK - zaktualizowano HTML")
    except Exception as e:
        print("Błąd zapisu HTML:", e)

if __name__ == "__main__":
    main()

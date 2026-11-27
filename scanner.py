import json
import requests

COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}


def fetch_markets(pages: int = 2) -> list:
    all_items = []
    for page in range(1, pages + 1):
        params = {
            "vs_currency": "usd",
            "order": "volume_desc",
            "per_page": 100,
            "page": page,
            "sparkline": "false",
            "price_change_percentage": "1h,24h",
        }
        resp = requests.get(COINGECKO_MARKETS_URL, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            all_items.extend(data)
    return all_items


def analyze_coin(coin: dict):
    if not isinstance(coin, dict):
        return None

    symbol_raw = str(coin.get("symbol", "")).upper()
    if not symbol_raw:
        return None

    symbol = f"{symbol_raw}USDT"
    price = coin.get("current_price")
    high_24h = coin.get("high_24h")
    low_24h = coin.get("low_24h")
    vol_24h = coin.get("total_volume")
    chg_24h = coin.get("price_change_percentage_24h")
    chg_1h = coin.get("price_change_percentage_1h_in_currency")

    if price is None or high_24h is None or low_24h is None or vol_24h is None or chg_24h is None:
        return None

    price = float(price)
    high_24h = float(high_24h)
    low_24h = float(low_24h)
    vol_24h = float(vol_24h)
    chg_24h = float(chg_24h)
    chg_1h = float(chg_1h) if chg_1h is not None else 0.0

    if price <= 0 or high_24h <= low_24h:
        return None

    # Filter aset bervolatilitas tinggi & likuiditas menengah ("gorengan" aktif)
    range_24h_pct = ((high_24h - low_24h) / price) * 100.0
    if not (5_000_000 <= vol_24h <= 300_000_000):
        return None
    if abs(chg_24h) < 5.0 or range_24h_pct < 6.0:
        return None

    # Estimasi volatilitas lokal (pengganti ATR saat memakai data 24h)
    est_atr = max((high_24h - low_24h) * 0.12, price * 0.012)
    buffer_atr = 0.6 * est_atr

    side = None
    entry = price
    sl = 0.0
    tp1 = 0.0
    tp2 = 0.0

    # Skenario LONG: momentum & tren 24j positif, koreksi jangka pendek (1h) tidak terlalu ekstrem
    if chg_24h >= 5.0 and chg_1h >= -4.0:
        support_est = max(low_24h, price - (1.5 * est_atr))
        side = "LONG"
        entry = price
        sl = min(support_est - buffer_atr, entry - (1.2 * est_atr))
        risk = entry - sl
        if risk <= 0:
            return None
        tp1 = entry + (1.5 * risk)
        tp2 = entry + (2.5 * risk)

    # Skenario SHORT: tekanan turun 24j kuat, pantulan 1h tidak terlalu liar melawan arah
    elif chg_24h <= -5.0 and chg_1h <= 4.0:
        resist_est = min(high_24h, price + (1.5 * est_atr))
        side = "SHORT"
        entry = price
        sl = max(resist_est + buffer_atr, entry + (1.2 * est_atr))
        risk = sl - entry
        if risk <= 0:
            return None
        tp1 = entry - (1.5 * risk)
        tp2 = entry - (2.5 * risk)

    if not side:
        return None

    score = (range_24h_pct * 1.8) + (abs(chg_24h) * 1.2) + (abs(chg_1h) * 0.8)

    return {
        "symbol": symbol,
        "side": side,
        "score": round(score, 2),
        "entry": round(entry, 6),
        "sl": round(sl, 6),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6),
    }


def main():
    coins = fetch_markets(pages=2)
    results = []

    for c in coins:
        try:
            plan = analyze_coin(c)
            if plan:
                results.append(plan)
        except Exception as e:
            print(f"Lewati coin karena error: {e}")

    results.sort(key=lambda x: x["score"], reverse=True)
    top_signals = results[:5]

    with open("signals.json", "w", encoding="utf-8") as f:
        json.dump(top_signals, f, indent=2)

    print(f"Berhasil menyimpan {len(top_signals)} sinyal ke signals.json")


if __name__ == "__main__":
    main()

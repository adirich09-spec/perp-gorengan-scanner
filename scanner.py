import json
import math
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}


def fetch_okx_perpetuals() -> dict:
    """Ambil data ticker kontrak Perpetual SWAP dari OKX Public API."""
    results = {}
    url = "https://www.okx.com/api/v5/market/tickers?instType=SWAP"
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    payload = r.json()
    for item in payload.get("data", []):
        inst_id = item.get("instId", "")
        if not inst_id.endswith("-USDT-SWAP"):
            continue
        base = inst_id.replace("-USDT-SWAP", "")
        symbol = f"{base}USDT"
        try:
            last_p = float(item.get("last", 0))
            open_24h = float(item.get("open24h", 0))
            high_24h = float(item.get("high24h", 0))
            low_24h = float(item.get("low24h", 0))
            vol_ccy_24h = float(item.get("volCcy24h", 0)) * last_p
            if last_p <= 0 or open_24h <= 0:
                continue
            chg_24h = ((last_p - open_24h) / open_24h) * 100.0
            results[symbol] = {
                "symbol": symbol,
                "price": last_p,
                "high_24h": high_24h,
                "low_24h": low_24h,
                "vol_24h": vol_ccy_24h,
                "chg_24h": chg_24h,
                "chg_1h": 0.0,
                "source": "OKX-Perp",
            }
        except (TypeError, ValueError):
            continue
    return results


def fetch_kucoin_futures() -> dict:
    """Ambil data kontrak aktif dari KuCoin Futures Public API."""
    results = {}
    url = "https://api-futures.kucoin.com/api/v1/contracts/active"
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    payload = r.json()
    for item in payload.get("data", []):
        raw_sym = item.get("symbol", "")
        if not raw_sym.endswith("USDTM"):
            continue
        base = raw_sym.replace("USDTM", "")
        if base == "XBT":
            base = "BTC"
        symbol = f"{base}USDT"
        try:
            last_p = float(item.get("lastTradePrice", 0))
            high_24h = float(item.get("highPrice", 0))
            low_24h = float(item.get("lowPrice", 0))
            vol_24h = float(item.get("turnoverOf24h", 0))
            chg_24h = float(item.get("priceChgPct", 0)) * 100.0
            if last_p <= 0:
                continue
            results[symbol] = {
                "symbol": symbol,
                "price": last_p,
                "high_24h": high_24h,
                "low_24h": low_24h,
                "vol_24h": vol_24h,
                "chg_24h": chg_24h,
                "chg_1h": 0.0,
                "source": "KuCoin-Perp",
            }
        except (TypeError, ValueError):
            continue
    return results


def fetch_coingecko() -> dict:
    """Ambil data pasar dari CoinGecko."""
    results = {}
    url = "https://api.coingecko.com/api/v3/coins/markets"
    for page in (1, 2):
        params = {
            "vs_currency": "usd",
            "order": "volume_desc",
            "per_page": 100,
            "page": page,
            "sparkline": "false",
            "price_change_percentage": "1h,24h",
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        for coin in r.json():
            base = str(coin.get("symbol", "")).upper()
            if not base:
                continue
            symbol = f"{base}USDT"
            try:
                price = float(coin.get("current_price") or 0)
                high_24h = float(coin.get("high_24h") or 0)
                low_24h = float(coin.get("low_24h") or 0)
                vol_24h = float(coin.get("total_volume") or 0)
                chg_24h = float(coin.get("price_change_percentage_24h") or 0)
                chg_1h = float(coin.get("price_change_percentage_1h_in_currency") or 0)
                if price <= 0:
                    continue
                results[symbol] = {
                    "symbol": symbol,
                    "price": price,
                    "high_24h": high_24h,
                    "low_24h": low_24h,
                    "vol_24h": vol_24h,
                    "chg_24h": chg_24h,
                    "chg_1h": chg_1h,
                    "source": "CoinGecko",
                }
            except (TypeError, ValueError):
                continue
    return results


def fetch_coinpaprika() -> dict:
    """Ambil data ticker dari CoinPaprika sebagai sumber cadangan tambahan."""
    results = {}
    url = "https://api.coinpaprika.com/v1/tickers"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    for item in r.json()[:250]:
        base = str(item.get("symbol", "")).upper()
        quotes = item.get("quotes", {}).get("USD", {})
        if not base or not quotes:
            continue
        symbol = f"{base}USDT"
        try:
            price = float(quotes.get("price") or 0)
            vol_24h = float(quotes.get("volume_24h") or 0)
            chg_24h = float(quotes.get("percent_change_24h") or 0)
            chg_1h = float(quotes.get("percent_change_1h") or 0)
            if price <= 0:
                continue
            # Estimasi high/low jika tidak tersedia langsung
            swing = max(abs(chg_24h) / 100.0, 0.04)
            results[symbol] = {
                "symbol": symbol,
                "price": price,
                "high_24h": price * (1 + swing * 0.5),
                "low_24h": price * (1 - swing * 0.5),
                "vol_24h": vol_24h,
                "chg_24h": chg_24h,
                "chg_1h": chg_1h,
                "source": "CoinPaprika",
            }
        except (TypeError, ValueError):
            continue
    return results


def merge_sources() -> list:
    merged = {}
    fetchers = [
        ("OKX-Perp", fetch_okx_perpetuals),
        ("KuCoin-Perp", fetch_kucoin_futures),
        ("CoinGecko", fetch_coingecko),
        ("CoinPaprika", fetch_coinpaprika),
    ]

    for name, fn in fetchers:
        try:
            data = fn()
            print(f"[{name}] berhasil memuat {len(data)} aset.")
            for sym, info in data.items():
                if sym not in merged:
                    merged[sym] = info.copy()
                    merged[sym]["sources"] = [name]
                else:
                    merged[sym]["sources"].append(name)
                    # Prioritaskan harga & high/low langsung dari bursa perpetual jika ada
                    if "Perp" in name:
                        merged[sym]["price"] = info["price"]
                        if info["high_24h"] > 0 and info["low_24h"] > 0:
                            merged[sym]["high_24h"] = info["high_24h"]
                            merged[sym]["low_24h"] = info["low_24h"]
                    if info["chg_1h"] != 0.0:
                        merged[sym]["chg_1h"] = info["chg_1h"]
                    merged[sym]["vol_24h"] = max(merged[sym]["vol_24h"], info["vol_24h"])
        except Exception as e:
            print(f"[{name}] gagal diakses (lanjut sumber lain): {e}")

    return list(merged.values())


def analyze_asset(asset: dict):
    symbol = asset["symbol"]
    price = asset["price"]
    high_24h = asset["high_24h"]
    low_24h = asset["low_24h"]
    vol_24h = asset["vol_24h"]
    chg_24h = asset["chg_24h"]
    chg_1h = asset["chg_1h"]
    sources = asset.get("sources", [])

    if price <= 0 or high_24h <= low_24h:
        return None

    # Filter aset bervolatilitas tinggi ("gorengan") dengan likuiditas layak
    if not (3_000_000 <= vol_24h <= 350_000_000):
        return None

    range_24h_pct = ((high_24h - low_24h) / price) * 100.0
    if abs(chg_24h) < 5.0 or range_24h_pct < 6.0:
        return None

    est_atr = max((high_24h - low_24h) * 0.12, price * 0.012)
    buffer_atr = 0.6 * est_atr

    side = None
    entry = price
    sl = 0.0
    tp1 = 0.0
    tp2 = 0.0

    # Skenario LONG
    if chg_24h >= 5.0 and chg_1h >= -4.0:
        support_est = max(low_24h, price - (1.5 * est_atr))
        side = "LONG"
        sl = min(support_est - buffer_atr, entry - (1.2 * est_atr))
        risk = entry - sl
        if risk <= 0:
            return None
        tp1 = entry + (1.5 * risk)
        tp2 = entry + (2.5 * risk)

    # Skenario SHORT
    elif chg_24h <= -5.0 and chg_1h <= 4.0:
        resist_est = min(high_24h, price + (1.5 * est_atr))
        side = "SHORT"
        sl = max(resist_est + buffer_atr, entry + (1.2 * est_atr))
        risk = sl - entry
        if risk <= 0:
            return None
        tp1 = entry - (1.5 * risk)
        tp2 = entry - (2.5 * risk)

    if not side:
        return None

    # Bonus skor jika terkonfirmasi di beberapa sumber / bursa perpetual
    multi_source_bonus = (len(sources) - 1) * 3.0
    perp_bonus = 4.0 if any("Perp" in s for s in sources) else 0.0
    score = (range_24h_pct * 1.6) + (abs(chg_24h) * 1.1) + (abs(chg_1h) * 0.8) + multi_source_bonus + perp_bonus

    return {
        "symbol": symbol,
        "side": side,
        "score": round(score, 2),
        "sources": "+".join(sources),
        "entry": round(entry, 6),
        "sl": round(sl, 6),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6),
    }


def main():
    assets = merge_sources()
    results = []
    for asset in assets:
        try:
            plan = analyze_asset(asset)
            if plan:
                results.append(plan)
        except Exception as e:
            print(f"Error analisis {asset.get('symbol')}: {e}")

    results.sort(key=lambda x: x["score"], reverse=True)
    top_signals = results[:7]

    with open("signals.json", "w", encoding="utf-8") as f:
        json.dump(top_signals, f, indent=2)

    print(f"Selesai! {len(top_signals)} aset prioritas tersimpan ke signals.json")


if __name__ == "__main__":
    main()

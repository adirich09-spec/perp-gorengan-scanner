import json
import math
import requests
import pandas as pd

BASE_URL = "https://fapi.binance.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_klines(symbol: str, interval: str = "15m", limit: int = 100) -> pd.DataFrame:
    r = requests.get(
        f"{BASE_URL}/fapi/v1/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or len(data) == 0:
        return pd.DataFrame()
    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "qv", "trades", "tb_base", "tb_quote", "ignore"
    ]
    df = pd.DataFrame(data, columns=cols)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df


def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    return float(atr) if not math.isnan(atr) else 0.0


def analyze_symbol(symbol: str, quote_vol: float, price_chg_pct: float):
    df = get_klines(symbol, interval="15m", limit=90)
    if df.empty or len(df) < 55:
        return None

    close_series = df["close"]
    last_close = float(close_series.iloc[-1])
    ema20 = float(close_series.ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(close_series.ewm(span=50, adjust=False).mean().iloc[-1])
    atr = compute_atr(df, 14)

    if last_close <= 0 or atr <= 0:
        return None

    atr_pct = (atr / last_close) * 100.0
    vol_avg = float(df["volume"].iloc[-21:-1].mean())
    vol_ratio = float(df["volume"].iloc[-1]) / (vol_avg + 1e-9)

    if not (5_000_000 <= quote_vol <= 250_000_000):
        return None
    if atr_pct < 1.5 or vol_ratio < 1.6:
        return None

    recent_low = float(df["low"].iloc[-12:-1].min())
    recent_high = float(df["high"].iloc[-12:-1].max())
    buffer_atr = 0.6 * atr

    side = None
    entry = last_close
    sl = 0.0
    tp1 = 0.0
    tp2 = 0.0

    if ema20 > ema50 and last_close >= ema50:
        dist_support_pct = ((last_close - recent_low) / last_close) * 100.0
        if dist_support_pct <= 4.0:
            side = "LONG"
            entry = last_close
            sl = min(recent_low - buffer_atr, entry - (1.2 * atr))
            risk = entry - sl
            if risk <= 0:
                return None
            tp1 = entry + (1.5 * risk)
            tp2 = entry + (2.5 * risk)

    elif ema20 < ema50 and last_close <= ema50:
        dist_resist_pct = ((recent_high - last_close) / last_close) * 100.0
        if dist_resist_pct <= 4.0:
            side = "SHORT"
            entry = last_close
            sl = max(recent_high + buffer_atr, entry + (1.2 * atr))
            risk = sl - entry
            if risk <= 0:
                return None
            tp1 = entry - (1.5 * risk)
            tp2 = entry - (2.5 * risk)

    if not side:
        return None

    priority_score = (atr_pct * 2.0) + (min(vol_ratio, 10.0) * 1.5) + (abs(price_chg_pct) * 0.5)

    return {
        "symbol": symbol,
        "side": side,
        "score": round(priority_score, 2),
        "entry": round(entry, 6),
        "sl": round(sl, 6),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6),
    }


def main():
    resp = requests.get(f"{BASE_URL}/fapi/v1/ticker/24hr", headers=HEADERS, timeout=20)
    resp.raise_for_status()
    tickers = resp.json()

    if not isinstance(tickers, list):
        print(f"Respons ticker bukan list: {tickers}")
        return

    candidates = []
    for t in tickers:
        if not isinstance(t, dict):
            continue
        sym = str(t.get("symbol", ""))
        if not sym.endswith("USDT"):
            continue
        try:
            quote_vol = float(t.get("quoteVolume", 0.0))
            chg_pct = float(t.get("priceChangePercent", 0.0))
        except (TypeError, ValueError):
            continue

        if abs(chg_pct) >= 5.0 and quote_vol >= 5_000_000:
            candidates.append((sym, quote_vol, chg_pct))

    candidates.sort(key=lambda x: abs(x[2]) * math.log10(x[1] + 10), reverse=True)

    results = []
    for sym, qvol, chg in candidates[:25]:
        try:
            plan = analyze_symbol(sym, qvol, chg)
            if plan:
                results.append(plan)
        except Exception as e:
            print(f"Error {sym}: {e}")

    results.sort(key=lambda x: x["score"], reverse=True)
    top_signals = results[:5]

    with open("signals.json", "w", encoding="utf-8") as f:
        json.dump(top_signals, f, indent=2)

    print(f"Berhasil menyimpan {len(top_signals)} sinyal ke signals.json")


if __name__ == "__main__":
    main()

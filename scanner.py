import time
from datetime import datetime, timezone
import pandas as pd
import pandas_ta as ta
from pybit.unified_trading import HTTP
import requests

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = "8698028434:AAEI-rGxwpBcCih-hzMaELPeg5wOkWSc4Ho"
TELEGRAM_CHAT_ID = "639554263"

session = HTTP(testnet=False)

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")

def check_market_sessions():
    now_utc = datetime.now(timezone.utc).hour
    active = []
    if 0 <= now_utc < 8:
        active.append("Tokyo (Asia)")
    if 7 <= now_utc < 16:
        active.append("London (Europe)")
    if 13 <= now_utc < 21:
        active.append("New York (USA)")
    return active

def scan_market():
    print(f"[{datetime.now()}] Запуск сканирования рынка...")
    active_sessions = check_market_sessions()
    
    try:
        response = session.get_instruments_info(category="linear")
        symbols = [
            item["symbol"] for item in response["result"]["list"] 
            if item["symbol"].endswith("USDT") and item["status"] == "Trading"
        ]
    except Exception as e:
        print(f"Ошибка получения списка инструментов: {e}")
        return

    signals_found = 0

    for symbol in symbols:
        try:
            kline_resp = session.get_kline(category="linear", symbol=symbol, interval="240", limit=100)
            if kline_resp["retCode"] != 0:
                continue
                
            df = pd.DataFrame(kline_resp["result"]["list"], columns=["startTime", "open", "high", "low", "close", "volume", "turnover"])
            df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
            df = df.iloc[::-1].reset_index(drop=True)

            if df["volume"].tail(6).mean() < 800000:
                continue

            book_resp = session.get_orderbook(category="linear", symbol=symbol, limit=30)
            if book_resp["retCode"] == 0:
                bids_liq = sum([float(item[1]) for item in book_resp["result"]["bids"][:10]])
                asks_liq = sum([float(item[1]) for item in book_resp["result"]["asks"][:10]])
            else:
                bids_liq, asks_liq = 1, 1

            df["rsi"] = ta.rsi(df["close"], length=14)
            df["ema_50"] = ta.ema(df["close"], length=50)
            df["ema_200"] = ta.ema(df["close"], length=200)
            df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)
            
            bbands = ta.bbands(df["close"], length=20, std=2)
            df["bb_width"] = (bbands["BBU_20_2.0"] - bbands["BBL_20_2.0"]) / bbands["BBM_20_2.0"]

            last = df.iloc[-1]
            prev = df.iloc[-2]

            is_uptrend = last["close"] > last["ema_200"] and last["ema_50"] > last["ema_200"]
            is_accumulation = last["bb_width"] < df["bb_width"].rolling(20).mean().iloc[-1]
            orderbook_imbalance = bids_liq > (asks_liq * 1.25)
            volume_breakout = last["volume"] > df["volume"].rolling(20).mean().iloc[-1] * 1.7

            if is_uptrend and is_accumulation and orderbook_imbalance and volume_breakout:
                entry = last["close"]
                atr = last["atr"]
                sl = entry - (atr * 1.5)
                tp1 = entry + (atr * 2.0)
                tp2 = entry + (atr * 3.5)

                signal_msg = (
                    f"🚀 **SIGNAL: {symbol} (LONG)**\n"
                    f"────────────────────────\n"
                    f"🏢 Сессии: `{', '.join(active_sessions)}`\n"
                    f"📦 **Накопление:** Сжатие волатильности (BB)\n"
                    f"💧 **Стакан:** Перевес покупателей\n"
                    f"────────────────────────\n"
                    f"📊 **Вход:** `{entry}`\n"
                    f"🛑 **SL:** `{round(sl, 4)}`\n"
                    f"🎯 **TP1:** `{round(tp1, 4)}` | 🎯 **TP2:** `{round(tp2, 4)}`"
                )
                send_telegram_message(signal_msg)
                signals_found += 1

        except Exception as e:
            continue
            
        time.sleep(0.05)

    print(f"Сканирование завершено. Найдено сигналов: {signals_found}")

if __name__ == "__main__":
    scan_market()

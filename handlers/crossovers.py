from telegram.ext import CommandHandler
from config import bist_50_stocks, TR_TZ
from database import get_db_connection
from stock_analyzer import StockAnalyzer
import logging
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger(__name__)

def update_user_activity(user_id: int, username: str = None):
    """Kullanıcı aktivitesini güncelle"""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO users (user_id, username, last_active) 
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    last_active = EXCLUDED.last_active
            """, (user_id, username, datetime.now(TR_TZ).isoformat()))
            conn.commit()
    except Exception as e:
        logger.error(f"Kullanıcı aktivitesi güncellenemedi: {e}")

async def detect_ema_crossovers(df: pd.DataFrame, symbol: str, period: str) -> dict:
    """EMA kesişim sinyallerini ve trade kriterlerini tespit et"""
    signals = []
    score = 0
    try:
        # EMA hesaplamaları
        ema_5 = df['Close'].ewm(span=5, adjust=False).mean()
        ema_9 = df['Close'].ewm(span=9, adjust=False).mean()
        ema_20 = df['Close'].ewm(span=20, adjust=False).mean()
        ema_50 = df['Close'].ewm(span=50, adjust=False).mean()
        ema_200 = df['Close'].ewm(span=200, adjust=False).mean()

        # MACD hesaplamaları (sadece günlük için)
        if period == "daily":
            macd = df['Close'].ta.macd(fast=12, slow=26, signal=9)
            macd_line = macd['MACD_12_26_9']
            macd_signal = macd['MACDs_12_26_9']
            macd_hist = macd['MACDh_12_26_9']

        # Son 3 gün/hafta/ay için kesişim kontrolü
        recent_periods = 3 if period == "daily" else 2 if period == "weekly" else 1
        current_price = df['Close'].iloc[-1]

        for i in range(-recent_periods, 0):
            if i == -recent_periods:
                continue
            # Günlük kriterler
            if period == "daily":
                # EMA 50/200 yukarı kesişim
                if (ema_50.iloc[i-1] < ema_200.iloc[i-1] and ema_50.iloc[i] > ema_200.iloc[i]):
                    signals.append(f"🟢 {symbol}: Günlük EMA 50/200 Al Sinyali ({df.index[i].strftime('%Y-%m-%d')})")
                    score += 2
                # EMA 50/200 aşağı kesişim (hariç tutulacak)
                if (ema_50.iloc[i-1] > ema_200.iloc[i-1] and ema_50.iloc[i] < ema_200.iloc[i]):
                    return {"signals": [], "score": 0}  # Aşağı kesişim varsa sinyal üretme

            # Haftalık ve aylık kriterler (EMA 5/20 yukarı kesişim)
            if period in ["weekly", "monthly"]:
                if (ema_5.iloc[i-1] < ema_20.iloc[i-1] and ema_5.iloc[i] > ema_20.iloc[i]):
                    signals.append(f"🟢 {symbol}: {period.capitalize()} EMA 5/20 Al Sinyali ({df.index[i].strftime('%Y-%m-%d')})")
                    score += 2 if period == "weekly" else 3

        # Günlük trade kriterleri
        if period == "daily":
            is_above_ema_200 = current_price > ema_200.iloc[-1]
            is_above_ema_9 = current_price > ema_9.iloc[-1]
            is_macd_buy = macd_line.iloc[-1] > macd_signal.iloc[-1] and macd_hist.iloc[-1] > 0
            if is_above_ema_200 and is_above_ema_9 and is_macd_buy:
                signals.append(f"📈 {symbol}: Günlük Trade Al Sinyali (Fiyat > EMA 200, Fiyat > EMA 9, MACD Al)")
                score += 5

        return {"signals": signals, "score": score}
    except Exception as e:
        logger.error(f"EMA kesişim kontrolü hatası: {symbol}, Period: {period}, Hata: {e}")
        return {"signals": [], "score": 0}

async def crossovers(update, context):
    """BIST 50 hisseleri için EMA kesişim sinyallerini göster"""
    user_id = update.message.from_user.id
    update_user_activity(user_id)

    daily_signals = []
    weekly_signals = []
    monthly_signals = []

    for symbol in bist_50_stocks:
        try:
            # Günlük veri
            df_daily = await StockAnalyzer.get_stock_data(symbol + ".IS", "6mo", interval="1d")
            if df_daily is None or df_daily.empty:
                logger.warning(f"Günlük veri alınamadı: {symbol}")
                continue
            daily_result = await detect_ema_crossovers(df_daily, symbol, "daily")
            if daily_result["signals"]:
                daily_signals.append({"symbol": symbol, "signals": daily_result["signals"], "score": daily_result["score"]})

            # Haftalık veri
            df_weekly = await StockAnalyzer.get_stock_data(symbol + ".IS", "1y", interval="1wk")
            if df_weekly is None or df_weekly.empty:
                logger.warning(f"Haftalık veri alınamadı: {symbol}")
                continue
            weekly_result = await detect_ema_crossovers(df_weekly, symbol, "weekly")
            if weekly_result["signals"]:
                weekly_signals.append({"symbol": symbol, "signals": weekly_result["signals"], "score": weekly_result["score"]})

            # Aylık veri
            df_monthly = await StockAnalyzer.get_stock_data(symbol + ".IS", "2y", interval="1mo")
            if df_monthly is None or df_monthly.empty:
                logger.warning(f"Aylık veri alınamadı: {symbol}")
                continue
            monthly_result = await detect_ema_crossovers(df_monthly, symbol, "monthly")
            if monthly_result["signals"]:
                monthly_signals.append({"symbol": symbol, "signals": monthly_result["signals"], "score": monthly_result["score"]})
        except Exception as e:
            logger.error(f"Kesişim kontrolü hatası: {symbol}, Hata: {e}")
            continue

    # Sinyalleri zaman dilimine göre gruplandır ve sırala
    all_signals = []
    for signals, period in [(daily_signals, "Günlük"), (weekly_signals, "Haftalık"), (monthly_signals, "Aylık")]:
        signals = sorted(signals, key=lambda x: x["score"], reverse=True)
        for signal in signals:
            all_signals.extend(signal["signals"])

    response = (
        "📈 **EMA Kesişim Sinyalleri (BIST 50)**\n\n"
        + ("\n".join(all_signals) if all_signals else "🔔 Şu anda kesişim sinyali yok.")
        + "\n\nℹ️ **Not:** Bu analiz sadece BIST 50 hisseleri için geçerlidir.\n"
        + "ℹ️ **Açıklama:**\n"
        + "- Günlük: EMA 50/200 al sinyali, fiyat > EMA 200, fiyat > EMA 9, MACD al.\n"
        + "- Haftalık/Aylık: EMA 5/20 al sinyali."
    )

    await update.message.reply_text(response, parse_mode='Markdown')
    logger.info(f"Kesişim sinyalleri kontrol edildi: Kullanıcı ID={user_id}, Toplam sinyal: {len(all_signals)}")

def crossovers_handler():
    return CommandHandler("crossovers", crossovers)
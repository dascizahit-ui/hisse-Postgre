
# handlers/stock_scanner.py
import yfinance as yf
import pandas as pd
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from config import bist_stocks, TR_TZ
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def get_stock_data(symbol):
    try:    
        stock = yf.Ticker(f"{symbol}.IS")
        df = stock.history(period="3y", interval="1mo")

        if df.empty or len(df) < 20:
            return None

        df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()

        last_close = df['Close'].iloc[-1]
        ema5 = df['EMA5'].iloc[-1]
        ema20 = df['EMA20'].iloc[-1]
        prev_ema5 = df['EMA5'].iloc[-2]
        prev_ema20 = df['EMA20'].iloc[-2]

        crossover = prev_ema5 <= prev_ema20 and ema5 > ema20
        price_above_ema20 = (last_close - ema20) / ema20 * 100
        price_condition = price_above_ema20 <= 10

        if crossover and price_condition:
            return (
                f"📈 *{symbol}*\n"
                f"Kapanış: {last_close:.2f} TL\n"
                f"EMA5: {ema5:.2f}\n"
                f"EMA20: {ema20:.2f}\n"
                f"Fiyat EMA20'den %{price_above_ema20:.2f} yukarıda"
            )
    except Exception as e:
        logger.error(f"{symbol} hatası: {e}")
    return None

import asyncio

async def scan_stocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # ✅ GIF göndererek bekleme mesajı ver
        waiting_msg = await context.bot.send_animation(
            chat_id=update.effective_chat.id,
            animation="https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExOXRwYmJ6Y3AwM2dlbjlhZWoxcG11bWE5YmlxY2NudjR0dGgzajB3YSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/lXiRLb0xFzmreM8k8/giphy.gif",
            caption="⏳ Hisseler taranıyor, lütfen bekleyin..."
        )

        # Paralel olarak çalıştır
        tasks = [asyncio.to_thread(get_stock_data, symbol) for symbol in bist_stocks]
        results_raw = await asyncio.gather(*tasks)
        results = [r for r in results_raw if r]

        if results:
            message = "📊 *EMA 5-20 Kesişim Taraması* 📊\n\n"
            message += "\n\n".join(results)
            message += f"\n\n🕒 Tarama Zamanı: {datetime.now(TR_TZ).strftime('%Y-%m-%d %H:%M:%S')}"
            message += "\n\n🔍 Aylıkta ema 5-20 yukarı kesen Fiyat aylık ema 20 den en fazla yüzde 10 yukarda hisse taraması"
        else:
            message = "😔 Şartları sağlayan hisse bulunamadı."

        # Önce bekleme mesajını sil
        await waiting_msg.delete()

        # Sonucu gönder
        await update.message.reply_text(message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Tarama hatası: {e}")
        await update.message.reply_text("❌ Tarama sırasında bir hata oluştu.")

def scan_stocks_handler():
    return CommandHandler("scan", scan_stocks)

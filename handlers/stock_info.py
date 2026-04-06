from telegram.ext import CommandHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import api_semaphore, executor, TR_TZ
from database import get_db_connection
from utils.format import format_value
import yfinance as yf
import asyncio
import logging
from datetime import datetime

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

async def stock_info(update, context):
    """Hisse senedi bilgilerini göster"""
    if not context.args:
        await update.message.reply_text("⚠️ Lütfen bir hisse sembolü girin: /hisse <sembol>")
        return

    symbol = context.args[0].upper()
    user_id = update.message.from_user.id
    update_user_activity(user_id)

    original_symbol = symbol
    if not symbol.endswith(".IS"):
        symbol += ".IS"

    try:
        async with api_semaphore:
            info = await asyncio.get_event_loop().run_in_executor(executor, lambda: yf.Ticker(symbol).info)
        if not info or 'regularMarketPrice' not in info:
            await update.message.reply_text("❌ Hisse senedi bilgisi bulunamadı. Geçerli bir sembol girin.")
            return

        price = info.get('regularMarketPrice', 0.0)
        change = info.get('regularMarketChangePercent', 0.0)
        change_amount = info.get('regularMarketChange', 0.0)
        volume = info.get('regularMarketVolume', 'Bilgi Yok')
        market_cap = info.get('marketCap', 'Bilgi Yok')
        pe_ratio = info.get('trailingPE', 'Bilgi Yok')
        day_low = info.get('dayLow', 'Bilgi Yok')
        day_high = info.get('dayHigh', 'Bilgi Yok')

        change_emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"

        response = (
            f"📊 **{original_symbol}**\n\n"
            f"💰 Fiyat: **{format_value(price, 'number')} TL**\n"
            f"{change_emoji} Değişim: **{format_value(change, 'percent')}** ({format_value(change_amount, 'number')} TL)\n"
            f"📊 Günlük Aralık: {format_value(day_low, 'number')} - {format_value(day_high, 'number')} TL\n"
            f"📦 Hacim: {format_value(volume, 'integer')}\n"
            f"🏢 Piyasa Değeri: {format_value(market_cap, 'integer')} TL\n"
            f"📈 F/K Oranı: {format_value(pe_ratio, 'number')}"
        )

        keyboard = [
            [InlineKeyboardButton("📈 Teknik Analiz", callback_data=f"tech_{original_symbol}"),
             InlineKeyboardButton("🔔 Uyarı Ekle", callback_data=f"alert_{original_symbol}")],
            [InlineKeyboardButton("💼 Portföye Ekle", callback_data=f"portfolio_{original_symbol}"),
             InlineKeyboardButton("👁️ İzleme Listesi", callback_data=f"watch_{original_symbol}")],
            [InlineKeyboardButton("📊 Temel Analiz", callback_data=f"fund_{original_symbol}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(response, parse_mode='Markdown', reply_markup=reply_markup)
        logger.info(f"Hisse bilgisi alındı: {symbol}")
    except Exception as e:
        await update.message.reply_text("❌ Hisse senedi bilgisi alınamadı. Geçerli bir sembol girin (ör. THYAO).")
        logger.error(f"Hisse bilgisi alınamadı: {e}")

def stock_info_handler():
    return CommandHandler("hisse", stock_info)
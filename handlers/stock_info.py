from telegram.ext import CommandHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import api_semaphore, executor, TR_TZ, bist_stocks
from database import get_db_connection
from stock_analyzer import StockAnalyzer
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


async def _fetch_info_safe(symbol_with_is: str) -> dict:
    """yfinance .info'yu güvenli şekilde getir — başarısız olursa boş dict döner."""
    try:
        async with api_semaphore:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(
                executor, lambda: yf.Ticker(symbol_with_is).info
            )
            return info or {}
    except Exception as e:
        logger.warning(f".info alınamadı {symbol_with_is}: {e}")
        return {}


async def stock_info(update, context):
    """Hisse senedi bilgilerini göster"""
    if not context.args:
        await update.message.reply_text("⚠️ Lütfen bir hisse sembolü girin: /hisse <sembol>")
        return

    symbol = context.args[0].upper()
    user_id = update.message.from_user.id
    update_user_activity(user_id)

    if symbol not in bist_stocks:
        await update.message.reply_text(
            f"❌ **{symbol}** geçerli bir BIST hissesi değil.\nÖrnek: `/hisse THYAO`",
            parse_mode='Markdown'
        )
        return

    await update.message.reply_text(f"⏳ {symbol} bilgileri alınıyor...")

    # Fiyat ve değişim için güvenilir yol: StockAnalyzer.get_stock_data (history-based)
    df = await StockAnalyzer.get_stock_data(symbol)
    if df is None or df.empty:
        await update.message.reply_text(
            f"❌ **{symbol}** için veri alınamadı. Piyasa kapalı olabilir veya sembol hatalı."
            "\nBiraz sonra tekrar deneyin.",
            parse_mode='Markdown'
        )
        logger.error(f"/hisse: StockAnalyzer boş döndü {symbol}")
        return

    current_price = float(df['Close'].iloc[-1])
    if len(df) > 1:
        prev_close = float(df['Close'].iloc[-2])
        change_amount = current_price - prev_close
        change_pct = (change_amount / prev_close) * 100 if prev_close else 0.0
    else:
        change_amount = 0.0
        change_pct = 0.0

    day_low = float(df['Low'].iloc[-1])
    day_high = float(df['High'].iloc[-1])
    volume = float(df['Volume'].iloc[-1]) if 'Volume' in df.columns else None

    # Ek bilgiler (.info) — başarısız olursa sorun değil, ana çıktı etkilenmez
    info = await _fetch_info_safe(f"{symbol}.IS")
    market_cap = info.get('marketCap')
    pe_ratio = info.get('trailingPE')

    change_emoji = "📈" if change_pct > 0 else "📉" if change_pct < 0 else "➡️"

    lines = [
        f"📊 **{symbol}**",
        "",
        f"💰 Fiyat: **{format_value(current_price, 'number')} TL**",
        f"{change_emoji} Değişim: **{format_value(change_pct, 'percent')}** ({format_value(change_amount, 'number')} TL)",
        f"📊 Günlük Aralık: {format_value(day_low, 'number')} - {format_value(day_high, 'number')} TL",
    ]
    if volume is not None:
        lines.append(f"📦 Hacim: {format_value(volume, 'integer')}")
    if market_cap:
        lines.append(f"🏢 Piyasa Değeri: {format_value(market_cap, 'integer')} TL")
    if pe_ratio:
        lines.append(f"📈 F/K Oranı: {format_value(pe_ratio, 'number')}")

    keyboard = [
        [
            InlineKeyboardButton("📈 Teknik Analiz", callback_data=f"tech_{symbol}"),
            InlineKeyboardButton("🔔 Uyarı Ekle", callback_data=f"alert_{symbol}"),
        ],
        [InlineKeyboardButton("📊 Temel Analiz", callback_data=f"fund_{symbol}")],
    ]

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    logger.info(f"Hisse bilgisi gönderildi: {symbol}, fiyat={current_price}")


def stock_info_handler():
    return CommandHandler("hisse", stock_info)

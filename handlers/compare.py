from telegram.ext import CommandHandler
from config import TR_TZ
from database import get_db_connection
from stock_analyzer import StockAnalyzer
from utils.format import format_value
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

async def compare(update, context):
    """İki hisse senedini karşılaştır"""
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Lütfen iki hisse sembolü girin: /compare <sembol1> <sembol2>")
        return

    symbol1, symbol2 = context.args[0].upper(), context.args[1].upper()
    user_id = update.message.from_user.id
    update_user_activity(user_id)

    fundamentals1 = await StockAnalyzer.get_fundamental_analysis(symbol1)
    fundamentals2 = await StockAnalyzer.get_fundamental_analysis(symbol2)

    if 'error' in fundamentals1 or 'error' in fundamentals2:
        await update.message.reply_text("❌ Bir veya her iki hisse için veri alınamadı.")
        return

    response = (
        f"⚖️ **{symbol1} vs {symbol2} Karşılaştırması**\n\n"
        f"📊 **Sektör**\n"
        f"{symbol1}: {fundamentals1.get('sector', 'Bilgi Yok')}\n"
        f"{symbol2}: {fundamentals2.get('sector', 'Bilgi Yok')}\n\n"
        f"📈 **F/K Oranı**\n"
        f"{symbol1}: {format_value(fundamentals1.get('pe_ratio'), 'number')}\n"
        f"{symbol2}: {format_value(fundamentals2.get('pe_ratio'), 'number')}\n\n"
        f"🔮 **İleri F/K Oranı**\n"
        f"{symbol1}: {format_value(fundamentals1.get('forward_pe'), 'number')}\n"
        f"{symbol2}: {format_value(fundamentals2.get('forward_pe'), 'number')}\n\n"
        f"💰 **EPS**\n"
        f"{symbol1}: {format_value(fundamentals1.get('eps'), 'number')}\n"
        f"{symbol2}: {format_value(fundamentals2.get('eps'), 'number')}\n\n"
        f"📦 **Piyasa Değeri**\n"
        f"{symbol1}: {format_value(fundamentals1.get('market_cap'), 'integer')} TL\n"
        f"{symbol2}: {format_value(fundamentals2.get('market_cap'), 'integer')} TL\n\n"
        f"🎁 **Temettü Verimi**\n"
        f"{symbol1}: {format_value(fundamentals1.get('dividend_yield'), 'percent')}\n"
        f"{symbol2}: {format_value(fundamentals2.get('dividend_yield'), 'percent')}"
    )

    await update.message.reply_text(response, parse_mode='Markdown')
    logger.info(f"Hisse karşılaştırması yapıldı: {symbol1} vs {symbol2}, Kullanıcı ID={user_id}")

def compare_handler():
    return CommandHandler("compare", compare)
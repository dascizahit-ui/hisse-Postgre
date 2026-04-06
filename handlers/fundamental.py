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

async def fundamental_analysis(update, context, symbol: str = None):
    """Temel analiz yap"""
    if symbol is None:
        if update.message and context.args:
            symbol = context.args[0].upper()
        elif update.callback_query and update.callback_query.data.startswith("fund_"):
            symbol = update.callback_query.data.replace("fund_", "").upper()
        else:
            if update.message:
                await update.message.reply_text("⚠️ Lütfen bir hisse sembolü girin: /fundamental <sembol>")
            elif update.callback_query:
                await update.callback_query.edit_message_text("⚠️ Lütfen bir hisse sembolü girin: /fundamental <sembol>")
            return

    user_id = update.effective_user.id
    update_user_activity(user_id)

    fundamentals = await StockAnalyzer.get_fundamental_analysis(symbol)
    if 'error' in fundamentals:
        response = f"❌ {fundamentals['error']}"
    else:
        response = (
            f"📊 **{symbol} Temel Analiz**\n\n"
            f"🏢 **Sektör:** {fundamentals.get('sector', 'Bilgi Yok')}\n"
            f"🏭 **Endüstri:** {fundamentals.get('industry', 'Bilgi Yok')}\n\n"
            f"📈 **Fiyat/Kazanç Oranı (F/K):** {format_value(fundamentals.get('pe_ratio'), 'number')}\n"
            f"🔮 **İleri F/K Oranı:** {format_value(fundamentals.get('forward_pe'), 'number')}\n"
            f"💰 **Hisse Başına Kazanç (EPS):** {format_value(fundamentals.get('eps'), 'number')}\n"
            f"📉 **Kâr Marjı:** {format_value(fundamentals.get('profit_margin'), 'percent')}\n"
            f"🏦 **Öz Sermaye Getirisi (ROE):** {format_value(fundamentals.get('roe'), 'percent')}\n"
            f"💸 **Borç/Öz Sermaye Oranı:** {format_value(fundamentals.get('debt_to_equity'), 'number')}\n"
            f"📦 **Piyasa Değeri:** {format_value(fundamentals.get('market_cap'), 'integer')} TL\n"
            f"🎁 **Temettü Verimi:** {format_value(fundamentals.get('dividend_yield'), 'percent')}"
        )

    if update.message:
        await update.message.reply_text(response, parse_mode='Markdown')
    elif update.callback_query:
        await update.callback_query.edit_message_text(response, parse_mode='Markdown')
    logger.info(f"Temel analiz gönderildi: {symbol}, Kullanıcı ID={user_id}")

def fundamental_analysis_handler():
    return CommandHandler("temel", fundamental_analysis)
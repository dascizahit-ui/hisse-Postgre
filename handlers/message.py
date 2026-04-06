from telegram.ext import MessageHandler
from telegram.ext.filters import Text, COMMAND
from config import bist_stocks, TR_TZ
from database import get_db_connection
from stock_analyzer import StockAnalyzer
from utils.format import format_value
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
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

async def handle_message(update, context):
    """Genel mesajları işle ve hisse sembollerini algıla"""
    user_id = update.message.from_user.id
    update_user_activity(user_id)

    text = update.message.text.upper()
    for symbol in bist_stocks:
        if symbol in text:
            df = await StockAnalyzer.get_stock_data(symbol)
            if df is None or df.empty:
                continue

            current_price = df['Close'].iloc[-1]
            change = ((current_price - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100) if len(df) > 1 else 0.0
            change_emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"

            response = (
                f"📊 **{symbol}**\n\n"
                f"💰 Fiyat: **{format_value(current_price, 'number')} TL**\n"
                f"{change_emoji} Değişim: **{format_value(change, 'percent')}**"
            )

            keyboard = [
                [InlineKeyboardButton("📈 Teknik Analiz", callback_data=f"tech_{symbol}"),
                 InlineKeyboardButton("🔔 Uyarı Ekle", callback_data=f"alert_{symbol}")],
                [InlineKeyboardButton("💼 Portföye Ekle", callback_data=f"portfolio_{symbol}"),
                 InlineKeyboardButton("👁️ İzleme Listesi", callback_data=f"watch_{symbol}")],
                [InlineKeyboardButton("📊 Temel Analiz", callback_data=f"fund_{symbol}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(response, parse_mode='Markdown', reply_markup=reply_markup)
            logger.info(f"Mesajda hisse algılandı: {symbol}, Kullanıcı ID={user_id}")
            break

def get_message_handler():
    return MessageHandler(Text() & ~COMMAND, handle_message)
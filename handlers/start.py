from telegram.ext import CommandHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_db_connection
from config import TR_TZ
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

async def start(update, context):
    """Botu başlat ve ana menüyü göster"""
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "Bilinmiyor"

    update_user_activity(user_id, username)

    keyboard = [
        [InlineKeyboardButton("📊 Hisse Analizi", callback_data="help_stock")],
        [InlineKeyboardButton("🔔 Uyarılar", callback_data="help_alerts")],
        [InlineKeyboardButton("📡 Saatlik Sinyaller", callback_data="help_signals")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info(f"Start komutu alındı: Kullanıcı ID={user_id}, Kullanıcı Adı={username}")
    await update.message.reply_text(
        "🤖 **Hisse Analiz Botu'na Hoş Geldiniz!**\n\n"
        "Bu bot ile BIST hisselerini analiz edebilir, fiyat uyarıları alabilir ve saatlik sinyalleri takip edebilirsiniz.\n\n"
        "🚀 **Temel Komutlar:**\n"
        "• `/hisse <sembol>` - Hisse bilgisi\n"
        "• `/teknik <sembol>` - Detaylı teknik analiz\n"
        "• `/temel <sembol>` - Temel analiz\n"
        "• `/crossovers` - EMA kesişim sinyalleri\n"
        "• `/tara` - Hisse tarama\n"
        "• `/uyari <sembol> <fiyat>` - Fiyat uyarısı\n"
        "• `/saatlik <sembol>` - Saatlik sinyal\n\n"
        "💡 Tüm komutları görmek için: `/help`\n"
        "Daha fazla bilgi için aşağıdaki butonları kullanın:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

def start_handler():
    return CommandHandler("start", start)

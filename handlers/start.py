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

    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO user_settings (user_id) VALUES (%s)
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id,))
            conn.commit()
    except Exception as e:
        logger.error(f"Kullanıcı ayarları oluşturulamadı: {e}")

    keyboard = [
        [InlineKeyboardButton("📊 Hisse Analizi", callback_data="help_stock")],
        [InlineKeyboardButton("🔔 Uyarılar", callback_data="help_alerts")],
        [InlineKeyboardButton("💼 Portföy", callback_data="help_portfolio")],
        [InlineKeyboardButton("⚙️ Ayarlar", callback_data="settings")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info(f"Start komutu alındı: Kullanıcı ID={user_id}, Kullanıcı Adı={username}")
    await update.message.reply_text(
        "🤖 **Hisse Analiz Botu'na Hoş Geldiniz!**\n\n"
        "Bu bot ile BIST hisselerini analiz edebilir, portföyünüzü takip edebilir, fiyat uyarıları alabilir ve sektör analizleri yapabilirsiniz.\n\n"
        "🚀 **Temel Komutlar:**\n"
        "• `/hisse <sembol>` - Hisse bilgisi\n"
        "• `/teknik <sembol>` - Detaylı teknik analiz\n"
        "• `/fundamental <sembol>` - Temel analiz\n"
        "• `/crossovers` - EMA kesişim sinyalleri\n"
        "• `/scan` - Hisse tarama (EMA 5-20 kesişimi)\n"
        "• `/uyari <sembol> <fiyat>` - Fiyat uyarısı\n"
        "• `/portfolio` - Portföy yönetimi\n"
        "• `/watchlist` - İzleme listesi\n"
        "💡 Tüm komutları görmek için: `/help`\n"
        "Daha fazla bilgi için aşağıdaki butonları kullanın:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

def start_handler():
    return CommandHandler("start", start)
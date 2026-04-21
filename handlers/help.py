from telegram.ext import CommandHandler
from database import get_db_connection
from config import TR_TZ
from datetime import datetime
import logging

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

async def help_command(update, context):
    """Kullanım rehberini göster"""
    user_id = update.message.from_user.id
    update_user_activity(user_id)

    response = (
        "📚 **Hisse Analiz Botu Kullanım Rehberi**\n\n"
        "**Genel Komutlar:**\n"
        "• `/start` - Botu başlatır ve ana menüyü gösterir\n\n"
        "**Hisse Analizi:**\n"
        "• `/hisse <sembol>` - Hisse senedi bilgileri (ör. `/hisse THYAO`)\n"
        "• `/teknik <sembol>` - Detaylı teknik analiz + AI yorumu\n"
        "• `/temel <sembol>` - Temel analiz\n"
        "• `/compare <s1> <s2>` - Hisse karşılaştırma\n"
        "• `/crossovers` - EMA kesişim sinyalleri\n\n"
        "**Tarama:**\n"
        "• `/tara` - Momentum + volatilite taraması (AI)\n"
        "• `/trend` - Trend kırılım taraması\n"
        "• `/momentum` - Momentum taraması\n"
        "• `/ultimate` - Kapsamlı tarama\n"
        "• `/bbfisher` / `/bbfisher4h` / `/bbfisherw` - BB Fisher taramaları\n"
        "• `/hacim` - Hacim analizi\n\n"
        "**Uyarılar:**\n"
        "• `/uyari <sembol> <fiyat>` - Fiyat uyarısı ayarla\n"
        "• `/myalerts` - Aktif uyarıları listele\n"
        "• `/cancelalert <id>` - Uyarıyı iptal et\n\n"
        "**Saatlik Sinyaller:**\n"
        "• `/saatlik <sembol>` - Anlık saatlik sinyal analizi\n"
        "• `/sinyal_takip <sembol>` - Otomatik bildirim al\n"
        "• `/sinyal_durdur <sembol>` - Bildirimi durdur\n"
        "• `/takip_listesi` - Takip ettiğin hisseler\n"
        "• `/sinyal_stats` - Sinyal istatistikleri\n\n"
        "**Yönetici:**\n"
        "• `/silent` - Sessiz mod durumu (00:00-07:00)\n"
        "• `/mute <süre> [sebep]` - Kullanıcıyı sustur\n"
        "• `/unmute` - Susturmayı kaldır\n"
        "• `/ban [sebep]` - Kullanıcıyı banla\n"
        "• `/unban` - Banı kaldır\n"
        "• `/report` - Mesajı yöneticilere raporla\n"
    )

    await update.message.reply_text(response, parse_mode='Markdown')
    logger.info(f"Kullanım rehberi gönderildi: Kullanıcı ID={user_id}")

def help_handler():
    return CommandHandler("help", help_command)

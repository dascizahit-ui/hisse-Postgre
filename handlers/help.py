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
        "Aşağıda botun tüm komutları ve kısa açıklamaları listelenmiştir:\n\n"
        "**Genel Komutlar:**\n"
        "• `/start` - Botu başlatır ve ana menüyü gösterir\n"
        "**Hisse Analizi Komutları:**\n"
        "• `/hisse <sembol>` - Hisse senedi bilgileri (ör. `/hisse THYAO`)\n"
        "• `/teknik <sembol>` - Detaylı teknik analiz + AI yorumu (ör. `/teknik BIMAS`)\n"
        "• `/fundamental <sembol>` - Temel analiz (ör. `/fundamental THYAO`)\n"
        "• `/crossovers` - EMA kesişim sinyalleri\n"
        "**Tarama Komutları:**\n"
        "• `/tara` - Momentum ve volatilite taraması + AI analizi\n"
        "• `/trend` - Trend kırılım taraması (Düşen trendi kıran veya haftalık yükseliş trendine değen hisseler, RSI<70) + AI analizi\n"
        "**Uyarı Komutları:**\n"
        "• `/uyari <sembol> <fiyat>` - Fiyat uyarısı ayarla (ör. `/uyari THYAO 150`)\n"
        "• `/myalerts` - Aktif uyarıları listele\n"
        "• `/cancelalert <id>` - Belirtilen uyarıyı iptal et (ör. `/cancelalert 1`)\n\n"
        "**Portföy ve İzleme Listesi:**\n"
        "• `/portfolio` - Portföy özetini göster\n"
        "• `/addstock <sembol> <adet> <fiyat>` - Portföye hisse ekle (ör. `/addstock THYAO 100 145.50`)\n"
        "• `/removestock <sembol>` - Portföyden hisse çıkar (ör. `/removestock THYAO`)\n"
        "• `/watchlist` - İzleme listesini göster\n"
        "• `/addwatch <sembol>` - İzleme listesine hisse ekle (ör. `/addwatch THYAO`)\n"
        "• `/removewatch <sembol>` - İzleme listesinden hisse çıkar (ör. `/removewatch THYAO`)\n\n"
        "**Ayarlar:**\n"
        "**Yönetici Komutları:**\n"
        "• `/silent` - Sessiz mod durumunu kontrol et (00:00-07:00)\n"
        "• `/mute <süre> [sebep]` - Kullanıcıyı sustur (ör. `/mute 10 Test`)\n"
        "• `/unmute` - Kullanıcı susturmasını kaldır\n"
        "• `/ban [sebep]` - Kullanıcıyı banla (ör. `/ban Test`)\n"
        "• `/unban` - Kullanıcı banını kaldır\n"
        "• `/report` - Bir mesajı yöneticilere raporla\n\n"
    )

    await update.message.reply_text(response, parse_mode='Markdown')
    logger.info(f"Kullanım rehberi gönderildi: Kullanıcı ID={user_id}")

def help_handler():
    return CommandHandler("help", help_command)
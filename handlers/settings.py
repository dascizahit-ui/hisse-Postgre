from telegram.ext import CommandHandler
from telegram import Update
from config import TR_TZ
from database import get_db_connection
import pytz
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

async def notifications(update: Update, context):
    """Bildirimleri aç/kapat"""
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("⚠️ Lütfen 'on' veya 'off' girin: /notifications <on|off>")
        return

    state = 1 if context.args[0].lower() == 'on' else 0
    user_id = update.message.from_user.id
    update_user_activity(user_id)

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO user_settings (user_id, notifications_enabled) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET notifications_enabled = EXCLUDED.notifications_enabled",
            (user_id, state)
        )
        conn.commit()

    await update.message.reply_text(
        f"✅ Bildirimler {'açıldı' if state else 'kapatıldı'}."
    )
    logger.info(f"Bildirim ayarları güncellendi: State={state}, Kullanıcı ID={user_id}")

async def dailysummary(update: Update, context):
    """Günlük özeti aç/kapat"""
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("⚠️ Lütfen 'on' veya 'off' girin: /dailysummary <on|off>")
        return

    state = 1 if context.args[0].lower() == 'on' else 0
    user_id = update.message.from_user.id
    update_user_activity(user_id)

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO user_settings (user_id, daily_summary_enabled) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET daily_summary_enabled = EXCLUDED.daily_summary_enabled",
            (user_id, state)
        )
        conn.commit()

    await update.message.reply_text(
        f"✅ Günlük özet {'açıldı' if state else 'kapatıldı'}."
    )
    logger.info(f"Günlük özet ayarları güncellendi: State={state}, Kullanıcı ID={user_id}")

async def timezone(update: Update, context):
    """Saat dilimini ayarla"""
    if not context.args:
        await update.message.reply_text("⚠️ Lütfen bir saat dilimi girin: /timezone <saat_dilimi>")
        return

    timezone = " ".join(context.args)
    user_id = update.message.from_user.id
    update_user_activity(user_id)

    try:
        pytz.timezone(timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        await update.message.reply_text("❌ Geçersiz saat dilimi. Örnek: /timezone Europe/Istanbul")
        return

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO user_settings (user_id, timezone) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET timezone = EXCLUDED.timezone",
            (user_id, timezone)
        )
        conn.commit()

    await update.message.reply_text(f"✅ Saat dilimi **{timezone}** olarak ayarlandı.")
    logger.info(f"Saat dilimi ayarlandı: {timezone}, Kullanıcı ID={user_id}")

def notifications_handler():
    return CommandHandler("notifications", notifications)

def dailysummary_handler():
    return CommandHandler("dailysummary", dailysummary)

def timezone_handler():
    return CommandHandler("timezone", timezone)
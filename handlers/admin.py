from telegram.ext import CommandHandler
from telegram import Update
from database import get_db_connection
from config import TR_TZ, ADMIN_CHAT_ID
from datetime import datetime, time, timedelta
import logging

logger = logging.getLogger(__name__)

async def is_admin(update: Update, context):
    """Kullanıcının yönetici olup olmadığını kontrol et"""
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception as e:
        logger.error(f"Yönetici kontrolü hatası: {e}")
        return False

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

def check_silent_mode():
    """Sessiz mod kontrolü (00:00-07:00)"""
    now = datetime.now(TR_TZ).time()
    return time(0, 0) <= now <= time(7, 0)

async def get_chat_id(update: Update, context):
    """Sohbet ID'sini döndür"""
    chat_id = update.message.chat_id
    logger.info(f"Chat ID istendi: {chat_id}")
    await update.message.reply_text(f"📋 Bu sohbetin ID'si: `{chat_id}`", parse_mode='Markdown')

async def silent(update: Update, context):
    """Sessiz mod durumunu göster"""
    if check_silent_mode():
        await update.message.reply_text("🌙 Sessiz mod aktif (00:00 - 07:00). Mesajlar sessiz gönderilecek.")
    else:
        await update.message.reply_text("☀️ Sessiz mod şu an aktif değil.")
    logger.info("Silent komutu çalıştırıldı")

async def mute(update: Update, context):
    """Kullanıcıyı sustur"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Bu komutu sadece yöneticiler kullanabilir!")
        logger.info("Yetkisiz mute denemesi")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Lütfen süre (dakika) belirtin: /mute <süre> [sebep]")
        return

    try:
        duration = int(context.args[0])
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Belirtilmedi"
        user = update.message.reply_to_message.from_user if update.message.reply_to_message else None
        if not user:
            await update.message.reply_text("⚠️ Lütfen susturmak için bir mesajı yanıtlayın.")
            return

        user_id = user.id
        mute_until = datetime.now(TR_TZ) + timedelta(minutes=duration)

        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO mutes (user_id, mute_until, reason) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET mute_until = EXCLUDED.mute_until, reason = EXCLUDED.reason", 
                     (user_id, mute_until.isoformat(), reason))
            conn.commit()

        await update.message.reply_text(
            f"🔇 {user.first_name} (@{user.username or 'Bilinmiyor'}) {duration} dakika süreyle susturuldu.\n"
            f"📝 Sebep: {reason}"
        )
        logger.info(f"Kullanıcı susturuldu: ID={user_id}, Süre={duration} dakika, Sebep={reason}")
    except ValueError:
        await update.message.reply_text("❌ Lütfen geçerli bir süre (dakika) girin.")
        logger.error("Geçersiz süre girildi")

async def ban(update: Update, context):
    """Kullanıcıyı banla"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Bu komutu sadece yöneticiler kullanabilir!")
        logger.info("Yetkisiz ban denemesi")
        return

    user = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    if not user:
        await update.message.reply_text("⚠️ Lütfen banlamak için bir mesajı yanıtlayın.")
        return

    reason = " ".join(context.args) if context.args else "Belirtilmedi"
    user_id = user.id

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO bans (user_id, reason) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET reason = EXCLUDED.reason", (user_id, reason))
        conn.commit()

    await update.message.reply_text(
        f"🚫 {user.first_name} (@{user.username or 'Bilinmiyor'}) banlandı!\n"
        f"📝 Sebep: {reason}"
    )
    logger.info(f"Kullanıcı banlandı: ID={user_id}, Sebep={reason}")

async def unban(update: Update, context):
    """Kullanıcı banını kaldır"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Bu komutu sadece yöneticiler kullanabilir!")
        logger.info("Yetkisiz unban denemesi")
        return

    user = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    if not user:
        await update.message.reply_text("⚠️ Lütfen banı kaldırmak için bir mesajı yanıtlayın.")
        return

    user_id = user.id

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM bans WHERE user_id = %s", (user_id,))
        conn.commit()

    await update.message.reply_text(
        f"✅ {user.first_name} (@{user.username or 'Bilinmiyor'}) banı kaldırıldı!"
    )
    logger.info(f"Kullanıcı banı kaldırıldı: ID={user_id}")

async def unmute(update: Update, context):
    """Kullanıcı susturmasını kaldır"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Bu komutu sadece yöneticiler kullanabilir!")
        logger.info("Yetkisiz unmute denemesi")
        return

    user = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    if not user:
        await update.message.reply_text("⚠️ Lütfen susturmayı kaldırmak için bir mesajı yanıtlayın.")
        return

    user_id = user.id

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM mutes WHERE user_id = %s", (user_id,))
        conn.commit()

    await update.message.reply_text(
        f"✅ {user.first_name} (@{user.username or 'Bilinmiyor'}) susturması kaldırıldı!"
    )
    logger.info(f"Kullanıcı susturması kaldırıldı: ID={user_id}")

async def report(update: Update, context):
    """Mesajı yöneticilere raporla"""
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Lütfen raporlamak için bir mesajı yanıtlayın.")
        return

    reported_user = update.message.reply_to_message.from_user
    reported_message_text = update.message.reply_to_message.text or "Mesaj içeriği yok"
    reporter = update.message.from_user
    timestamp = datetime.now(TR_TZ).isoformat()

    report_text = (
        f"🚨 **YENİ RAPOR**\n\n"
        f"👤 Raporlayan: {reporter.first_name} (@{reporter.username or 'Bilinmiyor'})\n"
        f"🎯 Raporlanan: {reported_user.first_name} (@{reported_user.username or 'Bilinmiyor'})\n"
        f"💬 Mesaj: {reported_message_text}\n"
        f"🕐 Zaman: {timestamp}"
    )

    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO reports (reporter_id, reported_user_id, message, timestamp) VALUES (%s, %s, %s, %s)",
                      (reporter.id, reported_user.id, reported_message_text, timestamp))
            conn.commit()

        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=report_text,
            parse_mode='Markdown',
            disable_notification=False
        )
        await update.message.reply_text("✅ Mesaj yöneticilere raporlandı.")
        logger.info(f"Rapor gönderildi: Raporlayan ID={reporter.id}, Raporlanan ID={reported_user.id}")
    except Exception as e:
        await update.message.reply_text("❌ Rapor gönderilemedi. Lütfen ADMIN_CHAT_ID'nin doğru olduğundan ve botun yönetici yetkisine sahip olduğundan emin olun.")
        logger.error(f"Rapor gönderilemedi: {e}")

def get_chat_id_handler():
    return CommandHandler("getchatid", get_chat_id)

def silent_handler():
    return CommandHandler("silent", silent)

def mute_handler():
    return CommandHandler("mute", mute)

def ban_handler():
    return CommandHandler("ban", ban)

def unban_handler():
    return CommandHandler("unban", unban)

def unmute_handler():
    return CommandHandler("unmute", unmute)

def report_handler():
    return CommandHandler("report", report)
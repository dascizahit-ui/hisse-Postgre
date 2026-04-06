from telegram.ext import CommandHandler
from telegram import Update
from config import bist_stocks, TR_TZ
from database import get_db_connection
from stock_analyzer import StockAnalyzer
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

def check_user_started_bot(user_id: int) -> bool:
    """Kullanıcının botu /start komutuyla başlatıp başlatmadığını kontrol et"""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id,))
            return c.fetchone() is not None
    except Exception as e:
        logger.error(f"Kullanıcı kontrolü sırasında hata: {e}")
        return False

async def set_alert(update: Update, context, symbol: str = None):
    """Fiyat uyarısı ayarla"""
    if symbol is None:
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("⚠️ Lütfen hisse sembolü ve fiyat girin: /uyari <sembol> <fiyat>")
            return
        symbol, price = context.args[0].upper(), context.args[1]
    else:
        if not context.args:
            await update.message.reply_text(f"⚠️ Lütfen fiyat girin: /uyari {symbol} <fiyat>")
            return
        price = context.args[0]

    try:
        price = float(price)
    except ValueError:
        await update.message.reply_text("❌ Lütfen geçerli bir fiyat girin.")
        return

    if symbol not in bist_stocks:
        await update.message.reply_text("❌ Geçersiz hisse sembolü.")
        return

    user_id = update.message.from_user.id
    
    # Kullanıcının botu başlatıp başlatmadığını kontrol et
    if not check_user_started_bot(user_id):
        await update.message.reply_text(
            "⚠️ **ÖNEMLİ:** Botu kullanmaya başlamadan önce lütfen önce /start komutunu kullanın!\n\n"
            "Botu başlatmak için lütfen /start komutunu gönderin, ardından uyarı oluşturabilirsiniz."
        )
        return
    
    update_user_activity(user_id)

    df = await StockAnalyzer.get_stock_data(symbol)
    if df is None or df.empty:
        await update.message.reply_text("❌ Hisse verisi alınamadı.")
        return

    current_price = df['Close'].iloc[-1]
    direction = "above" if price > current_price else "below"

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO alerts (user_id, symbol, price, direction, created_at) VALUES (%s, %s, %s, %s, %s)",
            (user_id, symbol, price, direction, datetime.now(TR_TZ).isoformat())
        )
        conn.commit()

    await update.message.reply_text(
        f"🔔 **{symbol}** için {price:.2f} TL {direction} uyarısı ayarlandı.\n"
        f"📊 Güncel fiyat: {current_price:.2f} TL",
        parse_mode='Markdown'
    )
    logger.info(f"Uyarı ayarlandı: {symbol}, Fiyat={price}, Kullanıcı ID={user_id}")

async def my_alerts(update: Update, context):
    """Aktif uyarıları listele"""
    user_id = update.message.from_user.id
    update_user_activity(user_id)

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, symbol, price, direction FROM alerts WHERE user_id = %s AND is_active = 1", (user_id,))
        alerts = c.fetchall()

    if not alerts:
        await update.message.reply_text("🔔 Aktif uyarınız bulunmuyor.")
        return

    response = ["🔔 **Aktif Uyarılarım**"]
    for alert_id, symbol, price, direction in alerts:
        response.append(f"ID: {alert_id} | {symbol} | {price:.2f} TL {direction}")

    await update.message.reply_text("\n".join(response), parse_mode='Markdown')
    logger.info(f"Uyarılar listelendi: Kullanıcı ID={user_id}")

async def cancel_alert(update: Update, context):
    """Belirtilen uyarıyı iptal et"""
    if not context.args:
        await update.message.reply_text("⚠️ Lütfen uyarı ID'si girin: /cancelalert <id>")
        return

    try:
        alert_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Lütfen geçerli bir uyarı ID'si girin.")
        return

    user_id = update.message.from_user.id
    update_user_activity(user_id)

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE alerts SET is_active = 0 WHERE id = %s AND user_id = %s", (alert_id, user_id))
        conn.commit()

    if c.rowcount == 0:
        await update.message.reply_text("❌ Bu ID'ye sahip bir uyarınız bulunmuyor.")
    else:
        await update.message.reply_text(f"✅ Uyarı ID {alert_id} iptal edildi.")
    logger.info(f"Uyarı iptal edildi: ID={alert_id}, Kullanıcı ID={user_id}")

async def check_alerts_async(application):
    """Uyarıları kontrol et ve bildirim gönder"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, user_id, symbol, price, direction FROM alerts WHERE is_active = 1")
        alerts = c.fetchall()

    for alert_id, user_id, symbol, price, direction in alerts:
        df = await StockAnalyzer.get_stock_data(symbol)
        if df is None or df.empty:
            continue

        current_price = df['Close'].iloc[-1]
        triggered = (direction == "above" and current_price >= price) or (direction == "below" and current_price <= price)

        if triggered:
            try:
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"🔔 **{symbol} Uyarısı**\n\nFiyat {price:.2f} TL {direction} seviyesine ulaştı!\n📊 Güncel fiyat: {current_price:.2f} TL",
                    parse_mode='Markdown'
                )
                with get_db_connection() as conn:
                    c = conn.cursor()
                    c.execute("UPDATE alerts SET is_active = 0 WHERE id = %s", (alert_id,))
                    conn.commit()
                logger.info(f"Uyarı tetiklendi: ID={alert_id}, Kullanıcı ID={user_id}, Sembol={symbol}")
            except Exception as e:
                logger.error(f"Uyarı bildirimi gönderilemedi: {e}")

def set_alert_handler():
    return CommandHandler("uyari", set_alert)

def my_alerts_handler():
    return CommandHandler("myalerts", my_alerts)

def cancel_alert_handler():
    return CommandHandler("cancelalert", cancel_alert)
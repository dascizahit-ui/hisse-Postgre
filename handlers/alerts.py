from telegram.ext import CommandHandler
from telegram import Update
from config import bist_stocks, TR_TZ
from database import get_db_connection
from stock_analyzer import StockAnalyzer
import logging
from datetime import datetime, time

logger = logging.getLogger(__name__)

DIRECTION_LABELS = {"above": "üstüne çıkınca", "below": "altına inince"}


def update_user_activity(user_id: int, username: str = None):
    """Kullanıcı aktivitesini güncelle"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
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
            with conn.cursor() as c:
                c.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id,))
                return c.fetchone() is not None
    except Exception as e:
        logger.error(f"Kullanıcı kontrolü sırasında hata: {e}")
        return False


def is_bist_market_open() -> bool:
    """BIST piyasa saatleri içinde mi? (Pzt-Cum 09:30-18:15 TR saati)"""
    now = datetime.now(TR_TZ)
    if now.weekday() >= 5:  # Cumartesi=5, Pazar=6
        return False
    return time(9, 30) <= now.time() <= time(18, 15)


async def set_alert(update: Update, context, symbol: str = None):
    """Fiyat uyarısı ayarla"""
    if symbol is None:
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("⚠️ Lütfen hisse sembolü ve fiyat girin: /uyari <sembol> <fiyat>")
            return
        symbol, price_str = context.args[0].upper(), context.args[1]
    else:
        if not context.args:
            await update.message.reply_text(f"⚠️ Lütfen fiyat girin: /uyari {symbol} <fiyat>")
            return
        price_str = context.args[0]

    try:
        price = float(price_str.replace(',', '.'))
    except ValueError:
        await update.message.reply_text("❌ Lütfen geçerli bir fiyat girin.")
        return

    if price <= 0:
        await update.message.reply_text("❌ Fiyat sıfırdan büyük olmalı.")
        return

    if symbol not in bist_stocks:
        await update.message.reply_text(f"❌ Geçersiz hisse sembolü: {symbol}")
        return

    user_id = update.message.from_user.id

    if not check_user_started_bot(user_id):
        await update.message.reply_text(
            "⚠️ **ÖNEMLİ:** Botu kullanmaya başlamadan önce lütfen /start komutunu kullanın!",
            parse_mode='Markdown'
        )
        return

    update_user_activity(user_id)

    df = await StockAnalyzer.get_stock_data(symbol)
    if df is None or df.empty:
        await update.message.reply_text("❌ Hisse verisi alınamadı. Biraz sonra tekrar deneyin.")
        return

    current_price = float(df['Close'].iloc[-1])
    direction = "above" if price > current_price else "below"

    with get_db_connection() as conn:
        with conn.cursor() as c:
            # Duplicate kontrolü — aynı kullanıcı, aynı hisse, aynı fiyat, aktif
            c.execute(
                "SELECT id FROM alerts WHERE user_id = %s AND symbol = %s AND price = %s AND is_active = 1",
                (user_id, symbol, price)
            )
            if c.fetchone():
                await update.message.reply_text(
                    f"ℹ️ **{symbol}** için {price:.2f} TL uyarısı zaten aktif.",
                    parse_mode='Markdown'
                )
                return

            c.execute(
                "INSERT INTO alerts (user_id, symbol, price, direction, created_at) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (user_id, symbol, price, direction, datetime.now(TR_TZ).isoformat())
            )
            alert_id = c.fetchone()[0]
        conn.commit()

    await update.message.reply_text(
        f"🔔 **{symbol}** için uyarı eklendi (ID: `{alert_id}`)\n"
        f"🎯 Hedef: **{price:.2f} TL** {DIRECTION_LABELS[direction]}\n"
        f"📊 Güncel fiyat: {current_price:.2f} TL",
        parse_mode='Markdown'
    )
    logger.info(f"Uyarı ayarlandı: ID={alert_id}, {symbol}, Fiyat={price}, Kullanıcı={user_id}")


async def my_alerts(update: Update, context):
    """Aktif uyarıları listele"""
    user_id = update.message.from_user.id
    update_user_activity(user_id)

    with get_db_connection() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT id, symbol, price, direction FROM alerts "
                "WHERE user_id = %s AND is_active = 1 ORDER BY symbol, price",
                (user_id,)
            )
            alerts = c.fetchall()

    if not alerts:
        await update.message.reply_text("🔔 Aktif uyarınız bulunmuyor.")
        return

    lines = ["🔔 **Aktif Uyarılarım**\n"]
    for alert_id, symbol, price, direction in alerts:
        label = DIRECTION_LABELS.get(direction, direction)
        lines.append(f"`{alert_id}` • **{symbol}** → {price:.2f} TL {label}")

    lines.append("\n💡 İptal için: `/cancelalert <id>`")
    await update.message.reply_text("\n".join(lines), parse_mode='Markdown')
    logger.info(f"Uyarılar listelendi: Kullanıcı={user_id}, Sayı={len(alerts)}")


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
        with conn.cursor() as c:
            c.execute(
                "UPDATE alerts SET is_active = 0 "
                "WHERE id = %s AND user_id = %s AND is_active = 1",
                (alert_id, user_id)
            )
            affected = c.rowcount
        conn.commit()

    if affected == 0:
        await update.message.reply_text(f"❌ ID `{alert_id}` ile aktif uyarınız bulunmuyor.", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"✅ Uyarı ID `{alert_id}` iptal edildi.", parse_mode='Markdown')
    logger.info(f"Uyarı iptal edildi: ID={alert_id}, Kullanıcı={user_id}, Etkilenen={affected}")


async def check_alerts_async(application):
    """Uyarıları kontrol et ve bildirim gönder — sembol bazında tek API çağrısı"""
    # Piyasa kapalıysa hiç API çağrısı yapma
    if not is_bist_market_open():
        return

    with get_db_connection() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT id, user_id, symbol, price, direction "
                "FROM alerts WHERE is_active = 1"
            )
            alerts = c.fetchall()

    if not alerts:
        return

    # Sembol bazında grupla — her sembol için tek API çağrısı
    symbols = {row[2] for row in alerts}
    price_cache = {}
    for symbol in symbols:
        df = await StockAnalyzer.get_stock_data(symbol)
        if df is None or df.empty:
            continue
        price_cache[symbol] = float(df['Close'].iloc[-1])

    triggered_ids = []
    for alert_id, user_id, symbol, target_price, direction in alerts:
        current_price = price_cache.get(symbol)
        if current_price is None:
            continue

        triggered = (
            (direction == "above" and current_price >= target_price) or
            (direction == "below" and current_price <= target_price)
        )
        if not triggered:
            continue

        try:
            await application.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🔔 **{symbol} Uyarısı Tetiklendi!**\n\n"
                    f"🎯 Hedef: {target_price:.2f} TL {DIRECTION_LABELS.get(direction, direction)}\n"
                    f"📊 Güncel fiyat: **{current_price:.2f} TL**"
                ),
                parse_mode='Markdown'
            )
            triggered_ids.append(alert_id)
            logger.info(f"Uyarı tetiklendi: ID={alert_id}, {symbol} @ {current_price}")
        except Exception as e:
            logger.error(f"Uyarı bildirimi gönderilemedi (ID={alert_id}, user={user_id}): {e}")
            # Kullanıcı botu blokladıysa uyarıyı deaktive et
            if "blocked" in str(e).lower() or "chat not found" in str(e).lower():
                triggered_ids.append(alert_id)

    # Tetiklenenleri toplu kapat
    if triggered_ids:
        with get_db_connection() as conn:
            with conn.cursor() as c:
                c.execute(
                    "UPDATE alerts SET is_active = 0 WHERE id = ANY(%s)",
                    (triggered_ids,)
                )
            conn.commit()


def set_alert_handler():
    return CommandHandler("uyari", set_alert)


def my_alerts_handler():
    return CommandHandler("myalerts", my_alerts)


def cancel_alert_handler():
    return CommandHandler("cancelalert", cancel_alert)

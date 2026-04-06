from telegram.ext import CommandHandler
from telegram import Update
from config import bist_stocks, TR_TZ
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

async def portfolio(update: Update, context):
    """Portföy özetini göster"""
    user_id = update.message.from_user.id
    update_user_activity(user_id)

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT symbol, quantity, avg_price FROM portfolio WHERE user_id = %s", (user_id,))
        stocks = c.fetchall()

    if not stocks:
        await update.message.reply_text("💼 Portföyünüz boş.")
        return

    total_value = 0
    total_cost = 0
    response = ["💼 **Portföy Özeti**"]
    for symbol, quantity, avg_price in stocks:
        df = await StockAnalyzer.get_stock_data(symbol)
        if df is None or df.empty:
            continue

        current_price = df['Close'].iloc[-1]
        value = quantity * current_price
        cost = quantity * avg_price
        profit_loss = value - cost
        total_value += value
        total_cost += cost
        response.append(
            f"📊 **{symbol}**\n"
            f"Adet: {quantity}\n"
            f"Ort. Maliyet: {format_value(avg_price, 'number')} TL\n"
            f"Güncel Fiyat: {format_value(current_price, 'number')} TL\n"
            f"Değer: {format_value(value, 'number')} TL\n"
            f"Kâr/Zarar: {format_value(profit_loss, 'number')} TL\n"
        )

    total_profit_loss = total_value - total_cost
    response.append(
        f"\n📈 **Toplam Değer:** {format_value(total_value, 'number')} TL\n"
        f"💰 **Toplam Kâr/Zarar:** {format_value(total_profit_loss, 'number')} TL"
    )

    await update.message.reply_text("\n".join(response), parse_mode='Markdown')
    logger.info(f"Portföy özeti gönderildi: Kullanıcı ID={user_id}")

async def add_stock(update: Update, context, symbol: str = None):
    """Portföye hisse ekle"""
    if symbol is None:
        if len(context.args) < 3:
            await update.message.reply_text("⚠️ Lütfen hisse sembolü, adet ve ortalama fiyat girin: /addstock <sembol> <adet> <fiyat>")
            return
        symbol, quantity, avg_price = context.args[0].upper(), context.args[1], context.args[2]
    else:
        if len(context.args) < 2:
            await update.message.reply_text(f"⚠️ Lütfen adet ve fiyat girin: /addstock {symbol} <adet> <fiyat>")
            return
        quantity, avg_price = context.args[0], context.args[1]

    try:
        quantity = float(quantity)
        avg_price = float(avg_price)
    except ValueError:
        await update.message.reply_text("❌ Lütfen geçerli bir adet ve fiyat girin.")
        return

    if symbol not in bist_stocks:
        await update.message.reply_text("❌ Geçersiz hisse sembolü.")
        return

    user_id = update.message.from_user.id
    update_user_activity(user_id)

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO portfolio (user_id, symbol, quantity, avg_price) VALUES (%s, %s, %s, %s) ON CONFLICT (user_id, symbol) DO UPDATE SET quantity = EXCLUDED.quantity, avg_price = EXCLUDED.avg_price",
            (user_id, symbol, quantity, avg_price)
        )
        conn.commit()

    await update.message.reply_text(
        f"✅ **{symbol}** portföye eklendi.\nAdet: {quantity}\nOrt. Fiyat: {avg_price:.2f} TL",
        parse_mode='Markdown'
    )
    logger.info(f"Portföye hisse eklendi: {symbol}, Kullanıcı ID={user_id}")

async def remove_stock(update: Update, context):
    """Portföyden hisse çıkar"""
    if not context.args:
        await update.message.reply_text("⚠️ Lütfen bir hisse sembolü girin: /removestock <sembol>")
        return

    symbol = context.args[0].upper()
    user_id = update.message.from_user.id
    update_user_activity(user_id)

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM portfolio WHERE user_id = %s AND symbol = %s", (user_id, symbol))
        conn.commit()

    if c.rowcount == 0:
        await update.message.reply_text(f"❌ Portföyünüzde **{symbol}** bulunmuyor.")
    else:
        await update.message.reply_text(f"✅ **{symbol}** portföyden kaldırıldı.")
    logger.info(f"Portföyden hisse kaldırıldı: {symbol}, Kullanıcı ID={user_id}")

async def send_daily_summary(application):
    """Günlük portföy özetini gönder"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT DISTINCT user_id FROM portfolio")
        users = c.fetchall()

    for (user_id,) in users:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT notifications_enabled, daily_summary_enabled FROM user_settings WHERE user_id = %s", (user_id,))
            settings = c.fetchone()
            if not settings or not settings[0] or not settings[1]:
                continue

            c.execute("SELECT symbol, quantity, avg_price FROM portfolio WHERE user_id = %s", (user_id,))
            stocks = c.fetchall()

        total_value = 0
        total_cost = 0
        response = ["📊 **Günlük Portföy Özeti**"]
        for symbol, quantity, avg_price in stocks:
            df = await StockAnalyzer.get_stock_data(symbol)
            if df is None or df.empty:
                continue

            current_price = df['Close'].iloc[-1]
            value = quantity * current_price
            cost = quantity * avg_price
            profit_loss = value - cost
            total_value += value
            total_cost += cost
            response.append(
                f"**{symbol}**\n"
                f"Adet: {quantity}\n"
                f"Ort. Maliyet: {format_value(avg_price, 'number')} TL\n"
                f"Güncel Fiyat: {format_value(current_price, 'number')} TL\n"
                f"Kâr/Zarar: {format_value(profit_loss, 'number')} TL\n"
            )

        total_profit_loss = total_value - total_cost
        response.append(
            f"\n📈 **Toplam Değer:** {format_value(total_value, 'number')} TL\n"
            f"💰 **Toplam Kâr/Zarar:** {format_value(total_profit_loss, 'number')} TL"
        )

        try:
            await application.bot.send_message(
                chat_id=user_id,
                text="\n".join(response),
                parse_mode='Markdown'
            )
            logger.info(f"Günlük özet gönderildi: Kullanıcı ID={user_id}")
        except Exception as e:
            logger.error(f"Günlük özet gönderilemedi: Kullanıcı ID={user_id}, Hata: {e}")

def portfolio_handler():
    return CommandHandler("portfolio", portfolio)

def add_stock_handler():
    return CommandHandler("addstock", add_stock)

def remove_stock_handler():
    return CommandHandler("removestock", remove_stock)
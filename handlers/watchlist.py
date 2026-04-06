from telegram.ext import CommandHandler
from telegram import Update
from telegram.ext import ContextTypes
from config import bist_stocks, TR_TZ
from database import get_db_connection
import logging
from datetime import datetime
import yfinance as yf

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


def ensure_watchlist_table():
    """Watchlist tablosunun doğru yapıda olduğundan emin ol"""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()

            c.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                user_id BIGINT,
                symbol TEXT,
                added_price REAL,
                added_date TEXT,
                PRIMARY KEY (user_id, symbol)
            )
            """)

            conn.commit()

    except Exception as e:
        logger.error(f"Watchlist tablosu oluşturulamadı: {e}")


async def get_current_price(symbol: str):
    """Hisse senedinin güncel fiyatını al"""
    try:

        ticker = yf.Ticker(symbol + ".IS")
        df = ticker.history(period="1d", interval="1d")

        if df.empty:
            logger.warning(f"Güncel fiyat alınamadı: {symbol}")
            return None

        return float(df['Close'].iloc[-1])

    except Exception as e:
        logger.error(f"Fiyat alınamadı: {symbol} hata: {e}")
        return None


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """İzleme listesini göster"""

    ensure_watchlist_table()

    user_id = update.effective_user.id
    username = update.effective_user.username

    update_user_activity(user_id, username)

    with get_db_connection() as conn:
        c = conn.cursor()

        c.execute("""
        SELECT symbol, added_price, added_date 
        FROM watchlist 
        WHERE user_id = %s
        """, (user_id,))

        symbols = c.fetchall()

    if not symbols:
        await update.message.reply_text(
            "👁️ **İzleme Listeniz Boş**",
            parse_mode="Markdown"
        )
        return

    response = []

    response.append("👁️ **İzleme Listem**")
    response.append("```")
    response.append("Hisse | Eklendiğinde | Güncel | Değişim")
    response.append("------|-------------|-------|--------")

    for symbol, added_price, added_date in symbols:

        current_price = await get_current_price(symbol)

        if current_price is None:

            response.append(
                f"{symbol:<5} | {added_price:.2f} TL ({added_date}) | Veri yok | -"
            )

        else:

            if added_price:
                change_percent = ((current_price - added_price) / added_price) * 100
            else:
                change_percent = 0

            emoji = "✅" if change_percent >= 0 else "❌"

            response.append(
                f"{symbol:<5} | {added_price:.2f} TL ({added_date}) | "
                f"{current_price:.2f} TL | "
                f"{emoji} {'+' if change_percent >= 0 else ''}{change_percent:.2f}%"
            )

    response.append("```")

    await update.message.reply_text(
        "\n".join(response),
        parse_mode="Markdown"
    )

    logger.info(f"Watchlist gönderildi Kullanıcı={user_id}")


async def addwatch(update: Update, context: ContextTypes.DEFAULT_TYPE, symbol: str = None):
    """İzleme listesine hisse ekle"""

    ensure_watchlist_table()

    if symbol is None:

        if not context.args:
            await update.message.reply_text(
                "⚠️ Kullanım:\n`/addwatch <SEMBOL>`",
                parse_mode="Markdown"
            )
            return

        symbol = context.args[0].upper()

    else:
        symbol = symbol.upper()

    if symbol not in bist_stocks:

        await update.message.reply_text(
            f"❌ **{symbol}** geçersiz hisse.",
            parse_mode="Markdown"
        )
        return

    user_id = update.effective_user.id
    username = update.effective_user.username

    update_user_activity(user_id, username)

    current_price = await get_current_price(symbol)

    if current_price is None:

        await update.message.reply_text(
            f"❌ {symbol} için fiyat alınamadı.",
            parse_mode="Markdown"
        )
        return

    added_date = datetime.now(TR_TZ).strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:

        c = conn.cursor()

        c.execute("""
        INSERT INTO watchlist 
        (user_id, symbol, added_price, added_date)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, symbol) DO UPDATE SET
            added_price = EXCLUDED.added_price,
            added_date = EXCLUDED.added_date
        """, (user_id, symbol, current_price, added_date))

        conn.commit()

        if c.rowcount == 0:

            await update.message.reply_text(
                f"❌ **{symbol}** zaten listenizde.",
                parse_mode="Markdown"
            )

        else:

            await update.message.reply_text(
                f"✅ **{symbol}** eklendi\n"
                f"💰 Fiyat: {current_price:.2f} TL\n"
                f"📅 Tarih: {added_date}",
                parse_mode="Markdown"
            )

    logger.info(f"Watchlist eklendi {symbol} kullanıcı={user_id}")


async def remove_from_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Watchlistten çıkar"""

    ensure_watchlist_table()

    if not context.args:

        await update.message.reply_text(
            "⚠️ Kullanım:\n`/removewatch <SEMBOL>`",
            parse_mode="Markdown"
        )
        return

    symbol = context.args[0].upper()

    user_id = update.effective_user.id
    username = update.effective_user.username

    update_user_activity(user_id, username)

    with get_db_connection() as conn:

        c = conn.cursor()

        c.execute("""
        DELETE FROM watchlist 
        WHERE user_id = %s AND symbol = %s
        """, (user_id, symbol))

        conn.commit()

        if c.rowcount == 0:

            await update.message.reply_text(
                f"❌ **{symbol}** listenizde yok.",
                parse_mode="Markdown"
            )

        else:

            await update.message.reply_text(
                f"✅ **{symbol}** listeden kaldırıldı.",
                parse_mode="Markdown"
            )

    logger.info(f"Watchlistten silindi {symbol} kullanıcı={user_id}")


def watchlist_handler():
    return CommandHandler("watchlist", watchlist)


def addwatch_handler():
    return CommandHandler("addwatch", addwatch)


def remove_from_watchlist_handler():
    return CommandHandler("removewatch", remove_from_watchlist)
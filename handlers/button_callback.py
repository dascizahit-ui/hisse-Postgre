from telegram.ext import CallbackQueryHandler
from handlers.technical import technical_analysis
from handlers.alerts import set_alert
from handlers.portfolio import add_stock
from handlers.watchlist import addwatch
from handlers.fundamental import fundamental_analysis
import logging

logger = logging.getLogger(__name__)

async def button_callback(update, context):
    """Inline keyboard buton işlemleri"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "help_stock":
        text = (
            "📊 **Hisse Analizi Komutları:**\n\n"
            "• `/hisse <sembol>` - Temel hisse bilgileri\n"
            "• `/teknik <sembol>` - Detaylı teknik analiz\n"
            "• `/fundamental <sembol>` - Temel analiz\n"
            "• `/crossovers` - EMA kesişim sinyalleri\n"
            "**Örnek:** `/hisse THYAO` veya `/teknik BIMAS`"
        )
        await query.edit_message_text(text, parse_mode='Markdown')
    elif data == "help_alerts":
        text = (
            "🔔 **Uyarı Komutları:**\n\n"
            "• `/uyari <sembol> <fiyat>` - Fiyat uyarısı ayarla\n"
            "• `/myalerts` - Aktif uyarılarım\n"
            "• `/cancelalert <id>` - Uyarı iptal et\n\n"
            "**Örnek:** `/uyari THYAO 150`"
        )
        await query.edit_message_text(text, parse_mode='Markdown')
    elif data == "help_portfolio":
        text = (
            "💼 **Portföy Komutları:**\n\n"
            "• `/portfolio` - Portföy özeti\n"
            "• `/addstock <sembol> <adet> <fiyat>` - Hisse ekle\n"
            "• `/removestock <sembol>` - Hisse çıkar\n"
            "• `/watchlist` - İzleme listesi\n"
            "• `/addwatch <sembol>` - İzleme listesine ekle\n"
            "• `/removewatch <sembol>` - İzleme listesinden çıkar\n\n"
            "**Örnek:** `/addstock THYAO 100 145.50`"
        )
        await query.edit_message_text(text, parse_mode='Markdown')
    elif data == "settings":
        text = (
            "⚙️ **Ayarlar:**\n\n"
            "• `/notifications on/off` - Bildirimleri aç/kapat\n"
            "• `/dailysummary on/off` - Günlük özet\n"
            "• `/timezone <saat_dilimi>` - Saat dilimi ayarla\n\n"
            "**Örnek:** `/notifications on`"
        )
        await query.edit_message_text(text, parse_mode='Markdown')
    elif data.startswith("tech_"):
        symbol = data.replace("tech_", "").upper()
        await technical_analysis(update, context, symbol=symbol)
    elif data.startswith("alert_"):
        symbol = data.replace("alert_", "").upper()
        text = f"🔔 **{symbol} için Uyarı Ayarla**\n\nLütfen fiyat belirtin: `/uyari {symbol} <fiyat>`\nÖrnek: `/uyari {symbol} 150`"
        await query.edit_message_text(text, parse_mode='Markdown')
    elif data.startswith("portfolio_"):
        symbol = data.replace("portfolio_", "").upper()
        text = f"💼 **{symbol} Portföye Ekle**\n\nLütfen bilgileri girin: `/addstock {symbol} <adet> <ortalama_fiyat>`\nÖrnek: `/addstock {symbol} 100 145.50`"
        await query.edit_message_text(text, parse_mode='Markdown')
    elif data.startswith("watch_"):
        symbol = data.replace("watch_", "").upper()
        await addwatch(update, context, symbol=symbol)
    elif data.startswith("fund_"):
        symbol = data.replace("fund_", "").upper()
        await fundamental_analysis(update, context, symbol=symbol)
    else:
        text = "❌ Geçersiz işlem."
        await query.edit_message_text(text, parse_mode='Markdown')

def button_callback_handler():
    return CallbackQueryHandler(button_callback)
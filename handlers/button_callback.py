from telegram.ext import CallbackQueryHandler
from handlers.technical import technical_analysis
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
            "• `/temel <sembol>` - Temel analiz\n"
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
    elif data == "help_signals":
        text = (
            "📡 **Saatlik Sinyal Komutları:**\n\n"
            "• `/saatlik <sembol>` - Saatlik sinyal analizi\n"
            "• `/sinyal_takip <sembol>` - Otomatik bildirim al\n"
            "• `/sinyal_durdur <sembol>` - Bildirimi durdur\n"
            "• `/takip_listesi` - Takip ettiklerim\n\n"
            "**Örnek:** `/sinyal_takip THYAO`"
        )
        await query.edit_message_text(text, parse_mode='Markdown')
    elif data.startswith("tech_"):
        symbol = data.replace("tech_", "").upper()
        await technical_analysis(update, context, symbol=symbol)
    elif data.startswith("alert_"):
        symbol = data.replace("alert_", "").upper()
        text = f"🔔 **{symbol} için Uyarı Ayarla**\n\nLütfen fiyat belirtin: `/uyari {symbol} <fiyat>`\nÖrnek: `/uyari {symbol} 150`"
        await query.edit_message_text(text, parse_mode='Markdown')
    elif data.startswith("fund_"):
        symbol = data.replace("fund_", "").upper()
        await fundamental_analysis(update, context, symbol=symbol)
    else:
        text = "❌ Geçersiz işlem."
        await query.edit_message_text(text, parse_mode='Markdown')

def button_callback_handler():
    return CallbackQueryHandler(button_callback)

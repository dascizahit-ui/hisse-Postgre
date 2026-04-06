# scanner_handler.py

import logging
from telegram import Update, constants
from telegram.ext import CommandHandler, ContextTypes
import g4f
import asyncio
import os

# Windows için asenkron ayar
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Az önce oluşturduğumuz tarama motorunu import et
from handlers.scanner_engine import run_all_scans

logger = logging.getLogger(__name__)

def get_ai_scanner_analysis(stock_data: str) -> str:
    """AI ile tarama sonuçlarını analiz et ve tavan potansiyeli olan hisseleri belirle"""
    try:
        prompt = f"""Sen bir hisse senedi uzmanısın. Aşağıdaki tarama sonuçlarını analiz et ve hangi hisselerin bugün TAVAN yapma potansiyeli yüksek olduğunu belirle.

Tarama Sonuçları:
{stock_data}

ÖNEMLİ KRİTERLER:
1. RVOL > 1.5 olanlar çok önemli (yüksek hacim = güçlü hareket)
2. Yeşil mum (🟢) olanlar daha olumlu
3. "Fiyat > VWAP" işareti olanlar güçlü
4. "VWAP Yukarı Kesişimi" olanlar çok önemli (saatlik onay gibi)
5. Kırmızı mum + yüksek hacim olanlar riskli (Geçmiş Olsun uyarısı)

Lütfen:
- En yüksek tavan potansiyeli olan 3-5 hisseyi belirle
- Her hisse için KISA (1-2 cümle) yorum yap
- Emoji kullan ama abartma
- Net ve anlaşılır ol
- "Tavan potansiyeli yüksek" gibi ifadeler kullan

Format:
🎯 TAVAN POTANSİYELİ YÜKSEK HİSSELER:

[Hisse Adı]: [Kısa yorum]

Örnek: THYAO: RVOL 2.1 ile güçlü hacim, VWAP üzerinde ve yeşil mum. Tavan potansiyeli yüksek."""

        # g4f ile AI analizi
        response = g4f.ChatCompletion.create(
            model=g4f.models.gpt_4,
            messages=[{"role": "user", "content": prompt}],
        )
        
        return f"\n\n🤖 **AI Analizi:**\n{response}"
    
    except Exception as e:
        logger.error(f"AI analiz hatası: {e}")
        return "\n\n⚠️ AI analizi şu anda yapılamadı."

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/tara komutu ile tüm taramaları başlatır ve sonuçları gönderir."""
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name

    logger.info(f"Kullanıcı {user_name} (ID: {chat_id}) tarafından tarama başlatıldı.")

    await context.bot.send_message(
        chat_id=chat_id,
        text="🔍 Tarama başlatılıyor... BIST'teki tüm hisseler analiz ediliyor, bu işlem birkaç dakika sürebilir. Lütfen bekleyin."
    )

    await context.bot.send_chat_action(
        chat_id=chat_id,
        action=constants.ChatAction.TYPING
    )

    try:
        scan_results = await run_all_scans()

        momentum_stocks = scan_results.get("momentum", [])
        volatility_stocks = scan_results.get("volatility", [])

        # Tüm hisseleri birleştir AI analizi için
        all_stocks_data = ""
        if momentum_stocks:
            all_stocks_data += "MOMENTUM TARAMASI:\n" + "\n".join(momentum_stocks) + "\n\n"
        if volatility_stocks:
            all_stocks_data += "VOLATİLİTE TARAMASI:\n" + "\n".join(volatility_stocks)

        # AI analizi yap
        ai_analysis = ""
        if momentum_stocks or volatility_stocks:
            ai_analysis = get_ai_scanner_analysis(all_stocks_data)

        # Sonuç mesajını formatla - Mesaj 1: Tarama Sonuçları
        message_part1 = "✅ *Tarama Tamamlandı!*\n\n"

        # --- Momentum Sonuçları ---
        message_part1 += "📈 *Hacim ve Güç Teyitli Momentum Taraması*\n"
        if momentum_stocks:
            message_part1 += "```\n" + "\n".join(momentum_stocks) + "\n```\n"
        else:
            message_part1 += "_Bu kritere uyan hisse bulunamadı._\n"

        message_part1 += "\n" # Boşluk bırak

        # --- Volatilite Sonuçları ---
        message_part1 += "💥 *Volatilite Kırılımı (Bollinger) Taraması*\n"
        if volatility_stocks:
            message_part1 += "```\n" + "\n".join(volatility_stocks) + "\n```\n"
        else:
            message_part1 += "_Bu kritere uyan hisse bulunamadı._\n"

        # Mesaj 2: AI Analizi
        message_part2 = ai_analysis + "\n\n_Not: Bu sonuçlar yatırım tavsiyesi değildir. Lütfen kendi analizlerinizi yapınız._"

        # Mesajları gönder
        await context.bot.send_message(
            chat_id=chat_id,
            text=message_part1,
            parse_mode="Markdown"
        )

        if ai_analysis:
            await context.bot.send_message(
                chat_id=chat_id,
                text=message_part2,
                parse_mode="Markdown"
            )


    except Exception as e:
        logger.error(f"Tarama sırasında bir hata oluştu: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Tarama sırasında bir hata oluştu: {e}"
        )

def scan_command_handler() -> CommandHandler:
    """/tara komutu için handler oluşturur."""
    return CommandHandler("tara", scan_command)

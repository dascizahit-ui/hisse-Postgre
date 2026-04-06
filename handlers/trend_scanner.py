# trend_scanner.py

import asyncio
import logging
from typing import List
from telegram import Update, constants
from telegram.ext import CommandHandler, ContextTypes
import g4f
import os

# Windows için asenkron ayar
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from stock_analyzer import StockAnalyzer
from config import fetch_bist_symbols, bist_50_stocks

logger = logging.getLogger(__name__)

async def run_trend_breakout_scan(symbols: List[str]) -> List[str]:
    """Trend Kırılım Taraması: Düşen trendi kıran veya haftalık yükseliş trendine değen hisseler"""
    logger.info("Trend Kırılım Taraması başlatılıyor...")
    found_stocks = []

    async def check_stock(symbol):
        try:
            # Günlük ve haftalık veri çek
            df_daily = await StockAnalyzer.get_stock_data(symbol, period="6mo", interval="1d")
            df_weekly = await StockAnalyzer.get_stock_data(symbol, period="1y", interval="1wk")
            
            if df_daily is None or len(df_daily) < 50 or df_weekly is None or len(df_weekly) < 20:
                return

            # Günlük indikatörler
            indicators_daily = await StockAnalyzer.calculate_technical_indicators(df_daily)
            
            last_price = df_daily['Close'].iloc[-1]
            
            # RSI kontrolü - 70 altında olmalı
            rsi = indicators_daily.get('rsi', 100)
            if rsi >= 70:
                return
            
            # 1. DÜŞEN TRENDİ KIRMA KONTROLÜ (Günlük)
            recent_highs = df_daily['High'].tail(20).values
            is_breaking_downtrend = False
            
            if len(recent_highs) >= 20:
                # Düşen trend çizgisi: son 20 günün yüksek noktaları düşüyor mu?
                first_high = recent_highs[:10].max()
                last_high = recent_highs[-10:].max()
                
                is_downtrend = last_high < first_high * 0.95  # %5 düşüş varsa düşen trend
                
                # Düşen trendi kırma: fiyat son 5 günün en yüksek seviyesini geçti mi?
                recent_5day_high = df_daily['High'].tail(5).max()
                is_breaking_downtrend = last_price > recent_5day_high and is_downtrend
            
            # 2. HAFTALIK YÜKSELİŞ TRENDİNE DEĞME KONTROLÜ
            # Haftalık EMA hesapla
            df_weekly['ema_20'] = df_weekly['Close'].ewm(span=20, adjust=False).mean()
            df_weekly['ema_50'] = df_weekly['Close'].ewm(span=50, adjust=False).mean()
            
            weekly_ema_20 = df_weekly['ema_20'].iloc[-1] if len(df_weekly) >= 20 else None
            weekly_ema_50 = df_weekly['ema_50'].iloc[-1] if len(df_weekly) >= 50 else None
            
            # Haftalık yükseliş trendi: EMA20 > EMA50
            is_weekly_uptrend = False
            is_touching_weekly_trend = False
            
            if weekly_ema_20 and weekly_ema_50:
                is_weekly_uptrend = weekly_ema_20 > weekly_ema_50
                
                # Fiyat haftalık EMA20'ye değiyor mu? (%2 tolerans)
                distance_to_ema20 = abs(last_price - weekly_ema_20) / weekly_ema_20
                is_touching_weekly_trend = distance_to_ema20 < 0.02 and is_weekly_uptrend
            
            # Sonuç değerlendirmesi
            found = False
            reason = ""
            
            if is_breaking_downtrend:
                found = True
                reason = "Düşen trendi kırıyor"
            
            if is_touching_weekly_trend:
                found = True
                if reason:
                    reason += " + Haftalık yükseliş trendine değdi"
                else:
                    reason = "Haftalık yükseliş trendine değdi"
            
            if found:
                result_string = f"{symbol} | RSI: {rsi:.1f} | {reason}"
                logger.info(f"[Trend Scan] Bulundu: {result_string}")
                found_stocks.append(result_string)

        except Exception as e:
            logger.error(f"[Trend Scan] {symbol} işlenirken hata: {e}")

    tasks = [check_stock(s) for s in symbols]
    await asyncio.gather(*tasks)

    logger.info(f"Trend Kırılım Taraması tamamlandı. {len(found_stocks)} hisse bulundu.")
    return found_stocks


def get_ai_trend_analysis(stock_data: str) -> str:
    """AI ile trend kırılım sonuçlarını analiz et"""
    try:
        prompt = f"""Sen bir hisse senedi uzmanısın. Aşağıdaki trend kırılım taraması sonuçlarını analiz et.

Tarama Sonuçları:
{stock_data}

Bu hisseler ya düşen trendi kırıyor ya da haftalık yükseliş trendine değiyor. RSI 70 altında.

ÖNEMLİ KRİTERLER:
1. Düşen trendi kıranlar çok önemli (güçlü alım sinyali)
2. Haftalık yükseliş trendine değenler destek bulabilir
3. Her ikisi de varsa çok güçlü sinyal

Lütfen:
- En yüksek potansiyeli olan 3-5 hisseyi belirle
- Her hisse için KISA (1-2 cümle) yorum yap
- Hangi sinyalin daha güçlü olduğunu belirt
- Net ve anlaşılır ol

Format:
🎯 TREND KIRILIM POTANSİYELİ YÜKSEK:

[Hisse Adı]: [Kısa yorum]"""

        # g4f ile AI analizi
        response = g4f.ChatCompletion.create(
            model=g4f.models.gpt_4,
            messages=[{"role": "user", "content": prompt}],
        )
        
        return f"\n\n🤖 **AI Analizi:**\n{response}"
    
    except Exception as e:
        logger.error(f"AI analiz hatası: {e}")
        return "\n\n⚠️ AI analizi şu anda yapılamadı."


async def trend_scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/trend komutu ile trend kırılım taraması başlatır"""
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name

    logger.info(f"Kullanıcı {user_name} (ID: {chat_id}) tarafından trend taraması başlatıldı.")

    await context.bot.send_message(
        chat_id=chat_id,
        text="🔍 Trend Kırılım Taraması başlatılıyor... BIST'teki tüm hisseler analiz ediliyor, bu işlem birkaç dakika sürebilir. Lütfen bekleyin."
    )

    await context.bot.send_chat_action(
        chat_id=chat_id,
        action=constants.ChatAction.TYPING
    )

    try:
        # Hisse listesini al
        try:
            symbols = fetch_bist_symbols()
            symbols = [s.replace('.IS', '') for s in symbols]
            logger.info(f"Taranacak {len(symbols)} adet hisse senedi bulundu.")
        except Exception as e:
            logger.error(f"Hisse listesi alınamadı: {e}")
            symbols = bist_50_stocks
            logger.warning(f"BIST 50 listesi ile devam ediliyor.")

        # Taramayı çalıştır
        trend_stocks = await run_trend_breakout_scan(symbols)

        # AI analizi yap
        ai_analysis = ""
        if trend_stocks:
            all_stocks_data = "TREND KIRILIM TARAMASI:\n" + "\n".join(trend_stocks)
            ai_analysis = get_ai_trend_analysis(all_stocks_data)

        # Sonuç mesajını formatla
        message_part1 = "✅ *Trend Kırılım Taraması Tamamlandı!*\n\n"
        message_part1 += "📊 *Düşen Trendi Kıran veya Haftalık Yükseliş Trendine Değen Hisseler*\n"
        message_part1 += "_(RSI < 70)_\n\n"
        
        if trend_stocks:
            message_part1 += "```\n" + "\n".join(trend_stocks) + "\n```\n"
        else:
            message_part1 += "_Bu kriterlere uyan hisse bulunamadı._\n"

        # Mesaj 2: AI Analizi
        message_part2 = ai_analysis + "\n\n_Not: Bu sonuçlar yatırım tavsiyesi değildir. Lütfen kendi analizlerinizi yapınız._"

        # Mesajları gönder
        await context.bot.send_message(
            chat_id=chat_id,
            text=message_part1[:4000],
            parse_mode="Markdown"
        )

        if ai_analysis:
            await context.bot.send_message(
                chat_id=chat_id,
                text=message_part2[:4000],
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Trend taraması sırasında bir hata oluştu: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Trend taraması sırasında bir hata oluştu: {e}"
        )


def trend_scan_command_handler() -> CommandHandler:
    """/trend komutu için handler oluşturur."""
    return CommandHandler("trend", trend_scan_command)

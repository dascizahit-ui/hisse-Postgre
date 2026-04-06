from telegram.ext import CommandHandler
from config import TR_TZ, bist_stocks
from database import get_db_connection
from stock_analyzer import StockAnalyzer
import logging
from datetime import datetime
import pandas as pd
import os
import g4f
import asyncio

# Windows için asenkron ayar
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

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

def get_status_icon(condition: bool):
    """Durum simgesi döndür"""
    return "🟢" if condition else "🔴"

def validate_symbol(symbol: str) -> bool:
    """Hisse sembolünün geçerli olup olmadığını kontrol et"""
    return symbol.upper() in bist_stocks or symbol.upper().endswith(".IS")

def get_bollinger_bands_comment(current_price: float, bb_upper: float, bb_middle: float, bb_lower: float) -> str:
    """Bollinger Bantları yorumu"""
    if current_price >= bb_upper * 0.98:  # Üst banda yakın
        return "⚠️ (Üst banda yakın - aşırı alım bölgesi)"
    elif current_price <= bb_lower * 1.02:  # Alt banda yakın
        return "🔥 (Alt banda yakın - aşırı satım bölgesi)"
    elif current_price > bb_middle:
        return "📈 (Orta bandın üzerinde - olumlu)"
    else:
        return "📉 (Orta bandın altında - olumsuz)"

def get_support_resistance_comment(current_price: float, support: float, resistance: float) -> str:
    """Destek/Direnç yorumu"""
    support_distance = ((current_price - support) / support) * 100
    resistance_distance = ((resistance - current_price) / current_price) * 100

    if resistance_distance < 2:
        return "⚠️ Direnç seviyesine çok yakın - kırılımı bekleyin"
    elif support_distance < 2:
        return "🚨 Destek seviyesine yakın - dikkatli olun"
    elif support_distance > 5 and resistance_distance > 5:
        return "✅ Destek ve dirençten uzak - rahat hareket alanı"
    else:
        return "📊 Normal aralıkta"

def get_general_trend_analysis(indicators: dict, current_price: float) -> str:
    """Genel trend analizi ve yorum"""
    ema_5 = indicators.get("ema_5", 0)
    ema_20 = indicators.get("ema_20", 0)
    ema_50 = indicators.get("ema_50", 0)
    ema_200 = indicators.get("ema_200", 0)

    rsi = indicators.get("rsi", 50)
    macd = indicators.get("macd", 0)
    macd_signal = indicators.get("macd_signal", 0)

    resistance = indicators.get("resistance", 0)
    support = indicators.get("support", 0)

    bb_upper = indicators.get("bb_upper", 0)
    bb_lower = indicators.get("bb_lower", 0)

    trend_comments = []

    # Trend yönü analizi
    if current_price > ema_5 > ema_20 > ema_50:
        trend_comments.append("🚀 **Güçlü Yükseliş Trendi:** EMA'lar sıralı dizilimde")
    elif current_price < ema_5 < ema_20 < ema_50:
        trend_comments.append("📉 **Güçlü Düşüş Trendi:** EMA'lar ters sıralı")
    elif current_price > ema_20:
        trend_comments.append("📈 **Orta Vadeli Yükseliş:** Fiyat EMA20 üzerinde")
    else:
        trend_comments.append("📉 **Orta Vadeli Düşüş:** Fiyat EMA20 altında")

    # MACD sinyali
    if macd > macd_signal and macd > 0:
        trend_comments.append("💪 MACD pozitif bölgede ve yükselişte")
    elif macd > macd_signal and macd < 0:
        trend_comments.append("⚡ MACD negatif bölgede ama toparlanıyor")
    else:
        trend_comments.append("⚠️ MACD düşüş sinyali veriyor")

    # RSI durumu
    if rsi > 70:
        trend_comments.append("🔴 RSI aşırı alım bölgesinde - dikkat")
    elif rsi < 30:
        trend_comments.append("🟢 RSI aşırı satım bölgesinde - fırsat olabilir")
    else:
        trend_comments.append("✅ RSI normal seviyelerde")

    # Destek/Direnç analizi
    resistance_distance = ((resistance - current_price) / current_price) * 100
    support_distance = ((current_price - support) / support) * 100

    if resistance_distance < 3:
        trend_comments.append(f"🎯 **Kritik Seviye:** Direnç {resistance:.2f} TL'yi kırması halinde yükseliş devam edebilir")
    elif support_distance < 3:
        trend_comments.append(f"🚨 **Dikkat:** Destek {support:.2f} TL kırılırsa daha fazla düşüş olabilir")

    # Bollinger Bantları pozisyonu
    if current_price >= bb_upper * 0.98:
        trend_comments.append("⚠️ **Aşırı Alım:** Fiyat Bollinger üst bandında - geri çekilme beklenebilir")
    elif current_price <= bb_lower * 1.02:
        trend_comments.append("🔥 **Aşırı Satım:** Fiyat Bollinger alt bandında - toparlanma beklenebilir")

    return "\n".join([f"• {comment}" for comment in trend_comments])

def get_ai_technical_analysis(symbol: str, current_price: float, indicators: dict) -> str:
    """AI ile teknik analiz yorumu oluştur"""
    try:
        # Teknik verileri hazırla
        technical_data = f"""
Hisse: {symbol}
Güncel Fiyat: {current_price:.2f} TL

Momentum İndikatörleri:
- RSI (14): {indicators.get('rsi', 0):.2f}
- Stochastic %K: {indicators.get('stoch_k', 0):.2f}
- Stochastic %D: {indicators.get('stoch_d', 0):.2f}
- ATR (14): {indicators.get('atr', 0):.2f}

Trend İndikatörleri:
- MACD: {indicators.get('macd', 0):.4f}
- MACD Sinyal: {indicators.get('macd_signal', 0):.4f}
- MACD Histogram: {indicators.get('macd_histogram', 0):.4f}

Hareketli Ortalamalar:
- EMA 5: {indicators.get('ema_5', 0):.2f} TL
- EMA 9: {indicators.get('ema_9', 0):.2f} TL
- EMA 20: {indicators.get('ema_20', 0):.2f} TL
- EMA 50: {indicators.get('ema_50', 0):.2f} TL
- EMA 200: {indicators.get('ema_200', 0):.2f} TL
- VWAP: {indicators.get('vwap', 0):.2f} TL

Destek/Direnç:
- Direnç: {indicators.get('resistance', 0):.2f} TL
- Destek: {indicators.get('support', 0):.2f} TL

Bollinger Bantları:
- Üst Bant: {indicators.get('bb_upper', 0):.2f} TL
- Orta Bant: {indicators.get('bb_middle', 0):.2f} TL
- Alt Bant: {indicators.get('bb_lower', 0):.2f} TL
"""

        prompt = f"""Sen profesyonel bir teknik analiz uzmanısın. Aşağıdaki teknik verileri analiz et ve detaylı bir yorum yap.

{technical_data}

ÖNEMLİ: Cevabın MAKSIMUM 2000 karakter olmalı!

Şu konulara detaylı değin:
1. Genel trend durumu (yükseliş/düşüş/yatay) ve gücü
2. RSI ve momentum analizi - aşırı alım/satım durumu
3. MACD sinyalleri ve histogram yorumu
4. EMA'ların konumu ve anlamı (kısa/orta/uzun vadeli)
5. Destek ve direnç seviyeleri - kritik noktalar
6. Bollinger Bantları pozisyonu ve volatilite
7. VWAP durumu ve hacim analizi
8. Kısa vadeli (1-5 gün) beklentiler
9. Orta vadeli (1-4 hafta) beklentiler
10. Risk seviyesi ve dikkat edilmesi gerekenler

Detaylı ve anlaşılır ol. Emoji kullanabilirsin. Bu bir teknik analiz yorumudur, yatırım tavsiyesi değildir."""

        # g4f ile AI analizi
        response = g4f.ChatCompletion.create(
            model=g4f.models.gpt_4,
            messages=[{"role": "user", "content": prompt}],
        )
        
        # Cevabı kısalt (Telegram limiti 4096 karakter)
        if len(response) > 3500:
            response = response[:3500] + "..."
        
        return f"🤖 **AI Teknik Analiz Yorumu:**\n\n{response}"
    
    except Exception as e:
        logger.error(f"AI analiz hatası: {e}")
        return "⚠️ AI analizi şu anda yapılamadı. Teknik veriler yukarıda gösterilmektedir."

async def technical_analysis(update, context, symbol: str = None):
    """Geliştirilmiş teknik analiz yap"""
    # Sembol belirleme
    if symbol is None:
        if update.message and context.args:
            symbol = context.args[0].upper()
        elif update.callback_query and update.callback_query.data.startswith("tech_"):
            symbol = update.callback_query.data.replace("tech_", "").upper()
        else:
            message = "⚠️ Lütfen bir hisse sembolü girin: /teknik <sembol> (ör. THYAO)"
            if update.message:
                await update.message.reply_text(message)
            elif update.callback_query:
                await update.callback_query.edit_message_text(message)
            logger.error("technical_analysis: Sembol belirlenemedi.")
            return

    # Sembol doğrulama
    if not validate_symbol(symbol):
        message = f"❌ Geçersiz hisse sembolü: {symbol}. Lütfen geçerli bir BIST sembolü girin (ör. THYAO)."
        if update.message:
            await update.message.reply_text(message)
        elif update.callback_query:
            await update.callback_query.edit_message_text(message)
        logger.error(f"Geçersiz sembol: {symbol}")
        return

    user_id = update.effective_user.id
    update_user_activity(user_id)

    # Sembole .IS ekleme
    if not symbol.endswith(".IS"):
        symbol += ".IS"

    try:
        # Veri çekme (1 yıllık veri)
        df = await StockAnalyzer.get_stock_data(symbol, "1y")
        if df is None or df.empty:
            message = f"❌ {symbol.replace('.IS', '')} için veri alınamadı. Lütfen sembolü kontrol edin."
            if update.message:
                await update.message.reply_text(message)
            elif update.callback_query:
                await update.callback_query.edit_message_text(message)
            logger.error(f"Veri alınamadı: {symbol}")
            return

        # Teknik indikatörleri hesapla
        indicators = await StockAnalyzer.calculate_technical_indicators(df)
        current_price = df["Close"].iloc[-1]

        # Piyasa duyarlılığı
        sentiment = StockAnalyzer.get_market_sentiment(indicators, current_price)

        # İndikatör değerlendirmeleri
        rsi = indicators.get("rsi", 0)
        macd = indicators.get("macd", 0)
        macd_signal = indicators.get("macd_signal", 0)
        macd_hist = indicators.get("macd_histogram", 0)
        atr = indicators.get("atr", 0)

        rsi_icon = get_status_icon(30 < rsi < 70)
        rsi_desc = " (Normal)" if 30 < rsi < 70 else " (Aşırı alım/satım)"
        macd_icon = get_status_icon(macd > macd_signal and macd_hist > 0)
        macd_desc = " (Yükseliş)" if macd > macd_signal else " (Düşüş)"

        # EMA değerlendirmesi
        ema_5 = indicators.get("ema_5", 0)
        ema_9 = indicators.get("ema_9", 0)
        ema_20 = indicators.get("ema_20", 0)
        ema_50 = indicators.get("ema_50", 0)
        ema_200 = indicators.get("ema_200", 0)

        ema_short_term = get_status_icon(current_price > ema_5 and current_price > ema_9)
        ema_mid_term = get_status_icon(current_price > ema_20 and current_price > ema_50)
        ema_long_term = get_status_icon(current_price > ema_200)

        # VWAP ekleme - hata kontrolü ile
        vwap = indicators.get("vwap", 0)
        vwap_line = ""
        if vwap > 0:
            vwap_icon = get_status_icon(current_price > vwap)
            vwap_status = 'Alıcılar güçlü' if current_price > vwap else 'Satıcılar güçlü'
            vwap_line = f"• VWAP: {vwap:.2f} TL {vwap_icon} ({vwap_status})\n"

        # Bollinger Bantları yorumu
        bb_upper = indicators.get('bb_upper', 0)
        bb_middle = indicators.get('bb_middle', 0)
        bb_lower = indicators.get('bb_lower', 0)
        bb_comment = get_bollinger_bands_comment(current_price, bb_upper, bb_middle, bb_lower)

        # Destek/Direnç yorumu
        resistance = indicators.get('resistance', 0)
        support = indicators.get('support', 0)
        sr_comment = get_support_resistance_comment(current_price, support, resistance)

        # Genel trend analizi
        general_analysis = get_general_trend_analysis(indicators, current_price)

        # AI ile teknik analiz yorumu
        ai_analysis = get_ai_technical_analysis(symbol.replace('.IS', ''), current_price, indicators)

        # Yanıt oluştur - Mesaj 1: Teknik Veriler
        response_part1 = (
            f"📈 **{symbol.replace('.IS', '')} Detaylı Teknik Analiz**\n\n"
            f"💰 **Güncel Fiyat:** {current_price:.2f} TL\n\n"
            f"📊 **Momentum İndikatörleri:**\n"
            f"• RSI (14): {rsi:.2f} {rsi_icon}{rsi_desc}\n"
            f"• Stochastic %K: {indicators.get('stoch_k', 0):.2f}\n"
            f"• Stochastic %D: {indicators.get('stoch_d', 0):.2f}\n"
            f"• ATR (14): {atr:.2f} - {'Yüksek volatilite' if atr > current_price * 0.03 else 'Normal volatilite'}\n\n"
            f"📉 **Trend İndikatörleri:**\n"
            f"• MACD: {macd:.4f}\n"
            f"• MACD Sinyal: {macd_signal:.4f}\n"
            f"• Histogram: {macd_hist:.4f} {macd_icon}{macd_desc}\n\n"
            f"📊 **Hareketli Ortalamalar:**\n"
            f"• EMA 5: {ema_5:.2f} TL\n"
            f"• EMA 9: {ema_9:.2f} TL {ema_short_term}\n"
            f"• EMA 20: {ema_20:.2f} TL\n"
            f"• EMA 50: {ema_50:.2f} TL {ema_mid_term}\n"
            f"• EMA 200: {ema_200:.2f} TL {ema_long_term}\n"
            f"{vwap_line}"
        )

        # Mesaj 2: Destek/Direnç ve Bollinger
        response_part2 = (
            f"🎯 **Destek/Direnç:**\n"
            f"• Direnç: {resistance:.2f} TL\n"
            f"• Destek: {support:.2f} TL\n"
            f"• Yorum: {sr_comment}\n\n"
            f"📈 **Bollinger Bantları:**\n"
            f"• Üst: {bb_upper:.2f} TL\n"
            f"• Orta: {bb_middle:.2f} TL\n"
            f"• Alt: {bb_lower:.2f} TL\n"
            f"• Durum: {bb_comment}"
        )

        # Mesaj 3: Piyasa Duyarlılığı ve Genel Analiz (kısaltılmış)
        # Sentiment ve general_analysis çok uzunsa kısalt
        sentiment_short = sentiment[:500] + "..." if len(sentiment) > 500 else sentiment
        general_analysis_short = general_analysis[:500] + "..." if len(general_analysis) > 500 else general_analysis
        
        response_part3 = (
            f"🧠 **Piyasa Duyarlılığı:**\n{sentiment_short}\n\n"
            f"📋 **Genel Trend:**\n{general_analysis_short}"
        )

        # Mesaj 4: AI Analizi
        response_part4 = ai_analysis + "\n\n⚠️ Bu analiz yatırım tavsiyesi değildir!"

        # Mesajları güvenli şekilde gönder
        try:
            if update.message:
                await update.message.reply_text(response_part1[:4000], parse_mode="Markdown")
                await update.message.reply_text(response_part2[:4000], parse_mode="Markdown")
                await update.message.reply_text(response_part3[:4000], parse_mode="Markdown")
                await update.message.reply_text(response_part4[:4000], parse_mode="Markdown")
            elif update.callback_query:
                await update.callback_query.edit_message_text(response_part1[:4000], parse_mode="Markdown")
                await update.callback_query.message.reply_text(response_part2[:4000], parse_mode="Markdown")
                await update.callback_query.message.reply_text(response_part3[:4000], parse_mode="Markdown")
                await update.callback_query.message.reply_text(response_part4[:4000], parse_mode="Markdown")
        except Exception as send_error:
            logger.error(f"Mesaj gönderme hatası: {send_error}")
            # Hata durumunda basit mesaj gönder
            simple_msg = f"📈 {symbol.replace('.IS', '')} analizi tamamlandı ancak mesaj çok uzun. Lütfen tekrar deneyin."
            if update.message:
                await update.message.reply_text(simple_msg)
            elif update.callback_query:
                await update.callback_query.message.reply_text(simple_msg)

        logger.info(f"AI destekli teknik analiz gönderildi: {symbol}, Kullanıcı ID={user_id}")

    except Exception as e:
        message = f"❌ Teknik analiz yapılamadı: {str(e)}. Lütfen geçerli bir sembol girin (ör. THYAO)."
        if update.message:
            await update.message.reply_text(message)
        elif update.callback_query:
            await update.callback_query.edit_message_text(message)
        logger.error(f"Teknik analiz hatası: {symbol}, Hata: {e}")

def technical_analysis_handler():
    return CommandHandler("teknik", technical_analysis)

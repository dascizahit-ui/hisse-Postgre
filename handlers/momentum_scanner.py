# handlers/momentum_scanner.py
import yfinance as yf
import pandas as pd
import numpy as np
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from ta.trend import MACD, EMAIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange
from config import bist_stocks, TR_TZ
from datetime import datetime
import logging
import asyncio

logger = logging.getLogger(__name__)

def calculate_vwap(df):
    """VWAP hesaplama"""
    try:
        if 'Volume' not in df.columns or df['Volume'].sum() == 0:
            return 0

        recent_df = df.tail(20).copy()
        typical_price = (recent_df['High'] + recent_df['Low'] + recent_df['Close']) / 3
        volume_sum = recent_df['Volume'].sum()

        if volume_sum == 0:
            return 0

        vwap = (typical_price * recent_df['Volume']).sum() / volume_sum
        return float(vwap) if not np.isnan(vwap) else 0

    except Exception as e:
        logger.error(f"VWAP hesaplama hatası: {e}")
        return 0

def get_momentum_indicators(symbol):
    """Tek hisse için momentum göstergelerini hesapla"""
    try:
        stock = yf.Ticker(f"{symbol}.IS")
        df = stock.history(period="3mo", interval="1d")

        if df.empty or len(df) < 50:
            return None

        current_price = df['Close'].iloc[-1]

        # RSI
        rsi_indicator = RSIIndicator(df['Close'])
        rsi = rsi_indicator.rsi().iloc[-1]

        # MACD
        macd_indicator = MACD(df['Close'])
        macd = macd_indicator.macd().iloc[-1]
        macd_signal = macd_indicator.macd_signal().iloc[-1]

        # EMA'lar
        ema_5 = EMAIndicator(df['Close'], window=5).ema_indicator().iloc[-1]
        ema_9 = EMAIndicator(df['Close'], window=9).ema_indicator().iloc[-1]
        ema_20 = EMAIndicator(df['Close'], window=20).ema_indicator().iloc[-1]
        ema_50 = EMAIndicator(df['Close'], window=50).ema_indicator().iloc[-1]
        ema_200 = EMAIndicator(df['Close'], window=200).ema_indicator().iloc[-1]

        # Bollinger Bands
        bb = BollingerBands(df['Close'])
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        bb_middle = bb.bollinger_mavg().iloc[-1]

        # Stochastic
        stoch = StochasticOscillator(df['High'], df['Low'], df['Close'])
        stoch_k = stoch.stoch().iloc[-1]

        # VWAP
        vwap = calculate_vwap(df)

        # Williams %R
        high_14 = df['High'].rolling(window=14).max().iloc[-1]
        low_14 = df['Low'].rolling(window=14).min().iloc[-1]
        williams_r = -100 * (high_14 - current_price) / (high_14 - low_14) if (high_14 - low_14) != 0 else 0

        # Momentum skorunu hesapla
        score = 0
        signals = []

        # 1. Trend güçlülüğü
        if current_price > ema_200:
            score += 15
            signals.append("✅ EMA200 üstünde")

        if current_price > ema_50:
            score += 12
            signals.append("✅ EMA50 üstünde")

        if current_price > ema_9:
            score += 8
            signals.append("✅ EMA9 üstünde")

        if ema_5 > ema_9 > ema_20:
            score += 10
            signals.append("✅ EMA sıralaması pozitif")

        # 2. VWAP
        if vwap > 0 and current_price > vwap:
            score += 10
            signals.append("✅ VWAP üstünde")

        # 3. MACD
        if macd > macd_signal:
            score += 15
            signals.append("✅ MACD pozitif")

        # 4. RSI kontrolü
        if 40 <= rsi <= 75:
            score += 8
            signals.append(f"✅ RSI optimal ({rsi:.1f})")
        elif rsi > 75:
            score += 4
            signals.append(f"⚠️ RSI yüksek ({rsi:.1f})")

        # 5. Bollinger Bands
        bb_position = (current_price - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0
        if 0.6 <= bb_position <= 0.9:
            score += 8
            signals.append("✅ BB üst bölgede")
        elif bb_position > 0.9:
            score += 4
            signals.append("⚠️ BB üst banda yakın")

        # 6. Stochastic
        if stoch_k > 80:
            score += 5
            signals.append("✅ Stochastic güçlü")

        # Son 3 günlük performans
        price_change_3d = ((current_price - df['Close'].iloc[-4]) / df['Close'].iloc[-4]) * 100 if len(df) >= 4 else 0

        # Hacim kontrolü
        avg_volume = df['Volume'].tail(10).mean()
        current_volume = df['Volume'].iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

        if score >= 45:  # Minimum eşik
            return {
                'symbol': symbol,
                'price': current_price,
                'score': score,
                'signals': signals[:4],  # En önemli 4 sinyal
                'rsi': rsi,
                'price_change_3d': price_change_3d,
                'volume_ratio': volume_ratio,
                'vwap': vwap
            }

    except Exception as e:
        logger.error(f"{symbol} momentum analiz hatası: {e}")

    return None

async def momentum_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Momentum tarama komutu"""
    try:
        # Bekleme mesajı
        waiting_msg = await context.bot.send_animation(
            chat_id=update.effective_chat.id,
            animation="https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExOXRwYmJ6Y3AwM2dlbjlhZWoxcG11bWE5YmlxY2NudjR0dGgzajB3YSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/lXiRLb0xFzmreM8k8/giphy.gif",
            caption="🚀 Momentum hisseleri taranıyor, lütfen bekleyin..."
        )

        # Paralel tarama
        tasks = [asyncio.to_thread(get_momentum_indicators, symbol) for symbol in bist_stocks]
        results_raw = await asyncio.gather(*tasks)
        results = [r for r in results_raw if r]

        if results:
            # Skoruna göre sırala
            results.sort(key=lambda x: x['score'], reverse=True)
            results = results[:12]  # En iyi 12 hisse

            message = "🚀 *MOMENTUM TARAMA SONUÇLARI* 🚀\n\n"

            for i, stock in enumerate(results, 1):
                message += f"🟢 *{stock['symbol']}* | {stock['price']:.2f} TL\n"
                message += f"📊 Momentum Skoru: {stock['score']}/100\n"

                if stock['price_change_3d'] != 0:
                    change_emoji = "📈" if stock['price_change_3d'] > 0 else "📉"
                    message += f"{change_emoji} 3G Değişim: %{stock['price_change_3d']:+.2f}\n"

                if stock['volume_ratio'] > 1.2:
                    message += f"🔊 Hacim: {stock['volume_ratio']:.1f}x artmış\n"

                # En önemli sinyalleri göster
                for signal in stock['signals'][:2]:  # İlk 2 sinyal
                    message += f"   {signal}\n"

                message += "\n"

                # Mesaj çok uzun olmasın
                if len(message) > 3500:
                    message += f"... ve {len(results)-i} hisse daha\n"
                    break

            message += f"🕒 Tarama: {datetime.now(TR_TZ).strftime('%H:%M:%S')}\n"
            message += "📈 *Momentum kriterleri:* EMA sıralaması, VWAP pozisyonu, MACD sinyali\n"
            message += "⚠️ *Risk Uyarısı:* Yatırım tavsiyesi değildir!"

        else:
            message = "😔 Şu anda momentum kriterlerini sağlayan hisse bulunamadı.\n"
            message += "🔍 Minimum skor: 45/100\n"
            message += "📊 Kriterler: Trend güçlülüğü, VWAP, MACD, RSI dengesi"

        # Bekleme mesajını sil
        await waiting_msg.delete()

        # Sonucu gönder
        await update.message.reply_text(message, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Momentum tarama hatası: {e}")
        await update.message.reply_text("❌ Momentum tarama sırasında bir hata oluştu.")

def momentum_scan_handler():
    """Momentum tarama handler'ı döndür"""
    return CommandHandler("momentum", momentum_scan)
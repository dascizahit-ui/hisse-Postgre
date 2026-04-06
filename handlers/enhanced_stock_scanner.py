from telegram.ext import CommandHandler
from config import bist_50_stocks, TR_TZ
from database import get_db_connection
from stock_analyzer import StockAnalyzer
import logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import asyncio
from typing import List, Dict, Optional, Tuple
import yfinance as yf
import requests
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import ta

logger = logging.getLogger(__name__)

@dataclass
class TechnicalData:
    """Teknik analiz verilerini tutmak için dataclass"""
    symbol: str
    current_price: float
    rsi: float
    macd: float
    macd_signal: float
    macd_histogram: float
    ema_5: float
    ema_9: float
    ema_20: float
    ema_50: float
    ema_200: float
    volume: float
    avg_volume: float
    atr: float
    stoch_k: float
    stoch_d: float
    price_change_1d: float
    price_change_5d: float
    price_change_10d: float
    price_change_20d: float
    bollinger_upper: float
    bollinger_middle: float
    bollinger_lower: float
    williams_r: float
    momentum: float
    cci: float
    adx: float

# Geliştirilmiş puanlama sistemi - kar odaklı
ENHANCED_SCORING_WEIGHTS = {
    "günlük": {
        "trend_alignment": 5,  # Trend uyumu
        "momentum_strength": 4,  # Momentum gücü
        "volume_confirmation": 3,  # Hacim onayı
        "oversold_bounce": 4,  # Aşırı satımdan dönüş
        "breakout_signal": 5,  # Kırılım sinyali
        "support_resistance": 3,  # Destek/direnç
        "volatility_opportunity": 2,  # Volatilite fırsatı
        "multi_timeframe": 3  # Çoklu zaman dilimi uyumu
    },
    "haftalık": {
        "weekly_trend": 6,  # Haftalık trend
        "swing_setup": 5,  # Swing kurulumu
        "weekly_momentum": 4,  # Haftalık momentum
        "volume_pattern": 3,  # Hacim deseni
        "price_pattern": 4,  # Fiyat deseni
        "risk_reward": 5,  # Risk/ödül oranı
        "sector_strength": 2,  # Sektör gücü
        "institutional_interest": 3  # Kurumsal ilgi
    },
    "aylık": {
        "monthly_trend": 8,  # Aylık trend
        "long_term_momentum": 6,  # Uzun vadeli momentum
        "fundamental_support": 5,  # Temel analiz desteği
        "accumulation_pattern": 6,  # Birikim deseni
        "breakout_confirmation": 7,  # Kırılım onayı
        "market_leadership": 4,  # Piyasa liderliği
        "earnings_cycle": 3,  # Kazanç döngüsü
        "dividend_yield": 2  # Temettü verimi
    }
}

class EnhancedDataProvider:
    """Geliştirilmiş veri sağlayıcı - çoklu kaynak desteği"""

    @staticmethod
    async def get_stock_data_multi_source(symbol: str, period: str) -> Optional[pd.DataFrame]:
        """Çoklu kaynaktan veri alma"""
        yahoo_symbol = f"{symbol}.IS"

        # Önce yfinance'dan dene
        try:
            ticker = yf.Ticker(yahoo_symbol)
            if period == "günlük":
                df = ticker.history(period="6mo", interval="1d")
            elif period == "haftalık":
                df = ticker.history(period="1y", interval="1wk")
            else:  # aylık
                df = ticker.history(period="2y", interval="1mo")

            if not df.empty and len(df) > 50:
                return df
        except Exception as e:
            logger.warning(f"Yahoo Finance error for {symbol}: {e}")

        # Alternatif kaynak: StockAnalyzer
        try:
            if period == "günlük":
                df = await StockAnalyzer.get_stock_data(yahoo_symbol, "6mo", interval="1d")
            elif period == "haftalık":
                df = await StockAnalyzer.get_stock_data(yahoo_symbol, "1y", interval="1wk")
            else:
                df = await StockAnalyzer.get_stock_data(yahoo_symbol, "2y", interval="1mo")

            if df is not None and not df.empty and len(df) > 30:
                return df
        except Exception as e:
            logger.warning(f"StockAnalyzer error for {symbol}: {e}")

        # Son çare: Daha kısa periyot dene
        try:
            ticker = yf.Ticker(yahoo_symbol)
            df = ticker.history(period="3mo", interval="1d")
            if not df.empty and len(df) > 20:
                logger.info(f"Using shorter period data for {symbol}")
                return df
        except Exception as e:
            logger.error(f"All data sources failed for {symbol}: {e}")

        return None

    @staticmethod
    def calculate_technical_indicators(df: pd.DataFrame) -> TechnicalData:
        """Geliştirilmiş teknik indikatörler hesaplama"""
        try:
            if df.empty:
                raise ValueError("Empty DataFrame")

            close = df['Close']
            high = df['High']
            low = df['Low']
            volume = df['Volume'] if 'Volume' in df.columns else pd.Series([1] * len(df))

            # Temel fiyat bilgileri
            current_price = close.iloc[-1]

            # RSI (14 period)
            rsi = ta.momentum.RSIIndicator(close=close, window=14).rsi().iloc[-1]
            if pd.isna(rsi):
                rsi = 50.0

            # MACD
            macd_indicator = ta.trend.MACD(close=close)
            macd = macd_indicator.macd().iloc[-1] if not macd_indicator.macd().empty else 0
            macd_signal = macd_indicator.macd_signal().iloc[-1] if not macd_indicator.macd_signal().empty else 0
            macd_histogram = macd_indicator.macd_diff().iloc[-1] if not macd_indicator.macd_diff().empty else 0

            # EMA'lar
            ema_5 = ta.trend.EMAIndicator(close=close, window=5).ema_indicator().iloc[-1] if len(close) >= 5 else current_price
            ema_9 = ta.trend.EMAIndicator(close=close, window=9).ema_indicator().iloc[-1] if len(close) >= 9 else current_price
            ema_20 = ta.trend.EMAIndicator(close=close, window=20).ema_indicator().iloc[-1] if len(close) >= 20 else current_price
            ema_50 = ta.trend.EMAIndicator(close=close, window=50).ema_indicator().iloc[-1] if len(close) >= 50 else current_price
            ema_200 = ta.trend.EMAIndicator(close=close, window=200).ema_indicator().iloc[-1] if len(close) >= 200 else current_price

            # Hacim analizi
            current_volume = volume.iloc[-1] if len(volume) > 0 else 1
            avg_volume = volume.rolling(20).mean().iloc[-1] if len(volume) >= 20 else current_volume

            # ATR (Volatilite)
            atr = ta.volatility.AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range().iloc[-1]
            if pd.isna(atr):
                atr = (high - low).mean()

            # Stochastic
            stoch = ta.momentum.StochasticOscillator(high=high, low=low, close=close)
            stoch_k = stoch.stoch().iloc[-1] if not stoch.stoch().empty else 50
            stoch_d = stoch.stoch_signal().iloc[-1] if not stoch.stoch_signal().empty else 50

            # Fiyat değişimleri
            price_change_1d = ((current_price - close.iloc[-2]) / close.iloc[-2]) * 100 if len(close) >= 2 else 0
            price_change_5d = ((current_price - close.iloc[-6]) / close.iloc[-6]) * 100 if len(close) >= 6 else 0
            price_change_10d = ((current_price - close.iloc[-11]) / close.iloc[-11]) * 100 if len(close) >= 11 else 0
            price_change_20d = ((current_price - close.iloc[-21]) / close.iloc[-21]) * 100 if len(close) >= 21 else 0

            # Bollinger Bands
            bollinger = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
            bollinger_upper = bollinger.bollinger_hband().iloc[-1] if not bollinger.bollinger_hband().empty else current_price * 1.1
            bollinger_middle = bollinger.bollinger_mavg().iloc[-1] if not bollinger.bollinger_mavg().empty else current_price
            bollinger_lower = bollinger.bollinger_lband().iloc[-1] if not bollinger.bollinger_lband().empty else current_price * 0.9

            # Williams %R
            williams_r = ta.momentum.WilliamsRIndicator(high=high, low=low, close=close, lbp=14).williams_r().iloc[-1]
            if pd.isna(williams_r):
                williams_r = -50

            # Momentum
            momentum = ta.momentum.ROCIndicator(close=close, window=10).roc().iloc[-1]
            if pd.isna(momentum):
                momentum = 0

            # CCI
            cci = ta.trend.CCIIndicator(high=high, low=low, close=close, window=20).cci().iloc[-1]
            if pd.isna(cci):
                cci = 0

            # ADX
            adx = ta.trend.ADXIndicator(high=high, low=low, close=close, window=14).adx().iloc[-1]
            if pd.isna(adx):
                adx = 25

            return TechnicalData(
                symbol="",
                current_price=current_price,
                rsi=rsi,
                macd=macd,
                macd_signal=macd_signal,
                macd_histogram=macd_histogram,
                ema_5=ema_5,
                ema_9=ema_9,
                ema_20=ema_20,
                ema_50=ema_50,
                ema_200=ema_200,
                volume=current_volume,
                avg_volume=avg_volume,
                atr=atr,
                stoch_k=stoch_k,
                stoch_d=stoch_d,
                price_change_1d=price_change_1d,
                price_change_5d=price_change_5d,
                price_change_10d=price_change_10d,
                price_change_20d=price_change_20d,
                bollinger_upper=bollinger_upper,
                bollinger_middle=bollinger_middle,
                bollinger_lower=bollinger_lower,
                williams_r=williams_r,
                momentum=momentum,
                cci=cci,
                adx=adx
            )

        except Exception as e:
            logger.error(f"Technical indicator calculation error: {e}")
            # Hata durumunda güvenli varsayılan değerler döndür
            current_price = df['Close'].iloc[-1] if not df.empty else 0
            return TechnicalData(
                symbol="", current_price=current_price, rsi=50, macd=0, macd_signal=0, macd_histogram=0,
                ema_5=current_price, ema_9=current_price, ema_20=current_price, ema_50=current_price, ema_200=current_price,
                volume=1, avg_volume=1, atr=1, stoch_k=50, stoch_d=50,
                price_change_1d=0, price_change_5d=0, price_change_10d=0, price_change_20d=0,
                bollinger_upper=current_price*1.1, bollinger_middle=current_price, bollinger_lower=current_price*0.9,
                williams_r=-50, momentum=0, cci=0, adx=25
            )

class EnhancedStockScanner:
    """Geliştirilmiş kar odaklı hisse tarayıcı"""

    @staticmethod
    def calculate_profit_potential_score(tech_data: TechnicalData, period: str) -> dict:
        """Kar potansiyeli odaklı puanlama sistemi"""
        score = 0
        signals = []
        warnings = []
        entry_signals = []
        risk_level = "Orta"

        try:
            # GÜNLÜK TİCARET SINYALLERI
            if period == "günlük":
                # 1. Trend Uyumu (5 puan)
                if (tech_data.ema_5 > tech_data.ema_9 > tech_data.ema_20 and 
                    tech_data.current_price > tech_data.ema_5):
                    score += 5
                    signals.append("🚀 Güçlü yükselis trend uyumu")
                    entry_signals.append("Mevcut fiyattan giriş uygun")

                # 2. Momentum Gücü (4 puan)
                if tech_data.rsi > 50 and tech_data.macd > tech_data.macd_signal and tech_data.adx > 25:
                    score += 4
                    signals.append("💪 Güçlü momentum sinyali")
                elif tech_data.rsi < 30 and tech_data.stoch_k < 20:
                    score += 3
                    signals.append("📈 Aşırı satım bölgesinden çıkış")
                    entry_signals.append("Düşük seviyeden giriş fırsatı")

                # 3. Hacim Onayı (3 puan)
                volume_ratio = tech_data.volume / tech_data.avg_volume if tech_data.avg_volume > 0 else 1
                if volume_ratio > 1.5:
                    score += 3
                    signals.append(f"🔊 Yüksek hacim onayı ({volume_ratio:.1f}x)")
                elif volume_ratio > 1.2:
                    score += 2
                    signals.append(f"📊 Hacim artışı ({volume_ratio:.1f}x)")

                # 4. Kırılım Sinyali (5 puan)
                if (tech_data.current_price > tech_data.bollinger_upper and 
                    tech_data.volume > tech_data.avg_volume * 1.3):
                    score += 5
                    signals.append("🎯 Bollinger üst band kırılımı")
                    entry_signals.append("Kırılım sonrası momentum takibi")
                    risk_level = "Yüksek"

                # 5. Destek/Direnç (3 puan)
                if (tech_data.current_price > tech_data.bollinger_lower * 1.02 and 
                    tech_data.current_price < tech_data.bollinger_middle):
                    score += 3
                    signals.append("🛡️ Destek seviyesinden yükseliş")

                # Risk değerlendirmesi
                if tech_data.rsi > 80:
                    warnings.append("⚠️ RSI aşırı alım bölgesinde")
                    risk_level = "Yüksek"
                if tech_data.atr / tech_data.current_price > 0.05:
                    warnings.append("⚠️ Yüksek volatilite")

            # HAFTALIK TİCARET SINYALLERI
            elif period == "haftalık":
                # 1. Haftalık Trend (6 puan)
                if (tech_data.current_price > tech_data.ema_20 > tech_data.ema_50 and 
                    tech_data.price_change_20d > 5):
                    score += 6
                    signals.append("📈 Güçlü haftalık yükseliş trendi")
                    entry_signals.append("Trend devamı için pozisyon")

                # 2. Swing Kurulumu (5 puan)
                if (tech_data.rsi > 40 and tech_data.rsi < 70 and 
                    tech_data.stoch_k > tech_data.stoch_d and tech_data.stoch_k > 20):
                    score += 5
                    signals.append("🎯 İdeal swing trade kurulumu")

                # 3. Risk/Ödül Oranı (5 puan)
                potential_upside = (tech_data.bollinger_upper - tech_data.current_price) / tech_data.current_price
                potential_downside = (tech_data.current_price - tech_data.bollinger_lower) / tech_data.current_price
                if potential_upside > potential_downside * 2:
                    score += 5
                    signals.append(f"💰 Olumlu risk/ödül oranı (1:{potential_upside/potential_downside:.1f})")
                    entry_signals.append("Sınırlı risk, yüksek kar potansiyeli")

                # 4. Momentum Sürdürülebilirliği (4 puan)
                if (tech_data.macd_histogram > 0 and tech_data.momentum > 2 and 
                    tech_data.price_change_10d > 0):
                    score += 4
                    signals.append("⚡ Sürdürülebilir momentum")

                # 5. Fiyat Deseni (4 puan)
                if tech_data.price_change_5d > 2 and tech_data.price_change_10d > 0:
                    score += 4
                    signals.append("📊 Pozitif fiyat deseni")

            # AYLIK TİCARET SINYALLERI
            elif period == "aylık":
                # 1. Aylık Trend (8 puan)
                if (tech_data.current_price > tech_data.ema_50 > tech_data.ema_200 and 
                    tech_data.price_change_20d > 10):
                    score += 8
                    signals.append("🚀 Güçlü aylık yükseliş trendi")
                    entry_signals.append("Uzun vadeli pozisyon için ideal")

                # 2. Birikim Deseni (6 puan)
                avg_volume_20 = tech_data.avg_volume
                if tech_data.volume > avg_volume_20 * 0.8 and tech_data.price_change_20d > 0:
                    score += 6
                    signals.append("📈 Birikim deseni tespit edildi")

                # 3. Kırılım Onayı (7 puan)
                if (tech_data.current_price > max(tech_data.ema_20, tech_data.ema_50) and 
                    tech_data.rsi > 55 and tech_data.adx > 30):
                    score += 7
                    signals.append("💎 Uzun vadeli kırılım onayı")
                    entry_signals.append("Trend başlangıcı sinyali")

                # 4. Piyasa Liderliği (4 puan)
                if tech_data.price_change_20d > 15:
                    score += 4
                    signals.append("👑 Piyasa lideri performansı")

                # 5. Değer Fırsatı (5 puan)
                if tech_data.rsi < 60 and tech_data.current_price < tech_data.bollinger_upper * 0.95:
                    score += 5
                    signals.append("💰 Değer fırsatı penceresi")

            # Hedef fiyat hesaplama
            if tech_data.atr > 0:
                target_price = tech_data.current_price + (tech_data.atr * 2)
                stop_loss = tech_data.current_price - (tech_data.atr * 1)
            else:
                target_price = tech_data.current_price * 1.05
                stop_loss = tech_data.current_price * 0.95

            return {
                "score": score,
                "max_score": sum(ENHANCED_SCORING_WEIGHTS[period].values()),
                "signals": signals,
                "warnings": warnings,
                "entry_signals": entry_signals,
                "risk_level": risk_level,
                "target_price": target_price,
                "stop_loss": stop_loss,
                "potential_return": ((target_price - tech_data.current_price) / tech_data.current_price) * 100,
                "technical_data": tech_data
            }

        except Exception as e:
            logger.error(f"Profit potential calculation error: {e}")
            return {
                "score": 0,
                "max_score": sum(ENHANCED_SCORING_WEIGHTS[period].values()),
                "signals": [f"❌ Hesaplama hatası: {str(e)}"],
                "warnings": [],
                "entry_signals": [],
                "risk_level": "Bilinmiyor",
                "target_price": tech_data.current_price,
                "stop_loss": tech_data.current_price,
                "potential_return": 0,
                "technical_data": tech_data
            }

def update_user_activity(user_id: int, username: str = None):
    """Update user activity in database"""
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
        logger.error(f"Failed to update user activity: {e}")

async def process_single_stock(symbol: str, period: str) -> Optional[dict]:
    """Tek hisse için analiz işlemi"""
    try:
        # Veri alma
        df = await EnhancedDataProvider.get_stock_data_multi_source(symbol, period)
        if df is None or df.empty:
            return None

        # Teknik analiz
        tech_data = EnhancedDataProvider.calculate_technical_indicators(df)
        tech_data.symbol = symbol

        # Kar potansiyeli analizi
        analysis = EnhancedStockScanner.calculate_profit_potential_score(tech_data, period)
        analysis["symbol"] = symbol

        return analysis

    except Exception as e:
        logger.error(f"Error processing {symbol}: {e}")
        return None

async def enhanced_scan_stocks(update, context):
    """Geliştirilmiş kar odaklı hisse tarama"""
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    update_user_activity(user_id, username)

    # Parameter kontrolü
    if not context.args:
        await update.message.reply_text(
            "💎 **Geliştirilmiş Kar Odaklı Hisse Tarama**\n\n"
            "**Kullanım:**\n"
            "• `/ktarama günlük` - Günlük kar fırsatları\n"
            "• `/ktarama haftalık` - Haftalık swing fırsatları\n" 
            "• `/ktarama aylık` - Aylık trend fırsatları\n\n"
            "**Özellikler:**\n"
            "🎯 Kar potansiyeli odaklı analiz\n"
            "📊 Çoklu teknik indikatör\n"
            "🔍 Risk/ödül oranı hesaplama\n"
            "💰 Hedef fiyat ve stop-loss önerileri\n"
            "⚡ Gerçek zamanlı sinyal takibi",
            parse_mode='Markdown'
        )
        return

    period = context.args[0].lower()
    if period not in ["günlük", "haftalık", "aylık"]:
        await update.message.reply_text("❌ Geçersiz parametre! 'günlük', 'haftalık' veya 'aylık' seçin.")
        return

    # Loading mesajı
    loading_msg = await update.message.reply_text(
        f"🔄 **{period.capitalize()} kar fırsatları taranıyor...**\n"
        f"📈 {len(bist_50_stocks)} hisse analiz ediliyor\n"
        f"⏱️ Bu işlem 45-90 saniye sürebilir"
    )

    # Paralel işlem
    tasks = [process_single_stock(symbol, period) for symbol in bist_50_stocks]
    results = await asyncio.gather(*tasks)

    # Sonuçları filtrele ve sırala
    valid_results = [r for r in results if r is not None and r["score"] > 0]
    valid_results.sort(key=lambda x: x["score"], reverse=True)

    # Başarısız analizler
    failed_count = len([r for r in results if r is None])

    # Yanıt oluştur
    if valid_results:
        response = f"💎 **{period.capitalize()} Kar Fırsatları** (En İyi 8)\n\n"

        for i, result in enumerate(valid_results[:8], 1):
            tech = result["technical_data"]
            score_percent = (result["score"] / result["max_score"]) * 100

            response += f"**{i}. {result['symbol']}** 📈\n"
            response += f"💰 **Fiyat:** {tech.current_price:.2f} TL\n"
            response += f"🎯 **Skor:** {result['score']}/{result['max_score']} ({score_percent:.0f}%)\n"
            response += f"📊 **Hedef:** {result['target_price']:.2f} TL (+{result['potential_return']:.1f}%)\n"
            response += f"🛡️ **Stop:** {result['stop_loss']:.2f} TL\n"
            response += f"⚖️ **Risk:** {result['risk_level']}\n"

            # Ana sinyaller (en fazla 2)
            if result["signals"]:
                response += "**Sinyaller:**\n"
                for signal in result["signals"][:2]:
                    response += f"• {signal}\n"

            # Giriş önerileri
            if result["entry_signals"]:
                response += f"💡 **Strateji:** {result['entry_signals'][0]}\n"

            response += "\n"

        # Özet bilgiler
        response += f"📊 **Özet:**\n"
        response += f"• Analiz edilen: {len(bist_50_stocks)} hisse\n"
        response += f"• Fırsat tespit: {len(valid_results)} hisse\n"
        response += f"• Başarısız analiz: {failed_count} hisse\n"
        response += f"• Ortalama potansiyel: {np.mean([r['potential_return'] for r in valid_results[:5]]):.1f}%\n\n"

        response += "⚠️ **Uyarı:** Bu analizler yatırım tavsiyesi değildir!"

    else:
        response = f"📉 **{period.capitalize()} dönemde kar fırsatı bulunamadı**\n\n"
        response += "🔍 **Öneriler:**\n"
        response += "• Piyasa koşulları uygun olmayabilir\n"
        response += "• Farklı zaman dilimi deneyin\n"
        response += "• Daha sonra tekrar kontrol edin\n\n"
        response += f"📊 Başarısız analiz: {failed_count}/{len(bist_50_stocks)}"

    # Mesajı güncelle
    await loading_msg.edit_text(response, parse_mode='Markdown')

    logger.info(f"Enhanced scan completed - Period: {period}, User: {user_id}, Results: {len(valid_results)}")

def enhanced_scan_stocks_handler():
    """Handler function"""
    return CommandHandler("ktarama", enhanced_scan_stocks)
import yfinance as yf
import pandas as pd
from ta.trend import MACD, SMAIndicator, EMAIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange
import asyncio
from config import api_semaphore, executor
import logging
from typing import Dict, Optional
import numpy as np

logger = logging.getLogger(__name__)

def calculate_vwap(df):
    """VWAP hesaplama - günlük hacim ağırlıklı ortalama fiyat"""
    try:
        if 'Volume' not in df.columns or df['Volume'].sum() == 0:
            logger.warning("Volume verisi yok veya sıfır")
            return 0

        # Son 20 günlük VWAP hesapla
        recent_df = df.tail(20).copy()

        # Typical Price (HLC/3)
        typical_price = (recent_df['High'] + recent_df['Low'] + recent_df['Close']) / 3

        # Volume kontrolü
        volume_sum = recent_df['Volume'].sum()
        if volume_sum == 0:
            return 0

        # VWAP hesaplama
        vwap = (typical_price * recent_df['Volume']).sum() / volume_sum

        return float(vwap) if not np.isnan(vwap) else 0

    except Exception as e:
        logger.error(f"VWAP hesaplama hatası: {e}")
        return 0

class StockAnalyzer:
    """Hisse senedi analiz sınıfı"""

    @staticmethod
    async def get_stock_data(symbol: str, period: str = "3mo", interval: str = "1d") -> Optional[pd.DataFrame]:
        """Hisse senedi verilerini asenkron olarak al"""
        async with api_semaphore:
            loop = asyncio.get_event_loop()
            try:
                if not symbol.endswith('.IS'):
                    symbol += '.IS'
                df = await loop.run_in_executor(executor, lambda: yf.Ticker(symbol).history(period=period, interval=interval))
                if df.empty:
                    return None
                return df
            except Exception as e:
                logger.error(f"Hisse verisi alınamadı {symbol}: {e}")
                return None

    @staticmethod
    async def calculate_technical_indicators(df: pd.DataFrame, interval: str = "1d") -> Dict:
        """Teknik göstergeleri hesapla"""
        try:
            indicators = {}

            # RSI
            rsi = RSIIndicator(df['Close']).rsi()
            indicators['rsi'] = rsi.iloc[-1] if not rsi.empty else 50

            # MACD
            macd_indicator = MACD(df['Close'])
            indicators['macd'] = macd_indicator.macd().iloc[-1]
            indicators['macd_signal'] = macd_indicator.macd_signal().iloc[-1]
            indicators['macd_histogram'] = macd_indicator.macd_diff().iloc[-1]

            # Bollinger Bands
            bb = BollingerBands(df['Close'])
            indicators['bb_upper'] = bb.bollinger_hband().iloc[-1]
            indicators['bb_lower'] = bb.bollinger_lband().iloc[-1]
            indicators['bb_middle'] = bb.bollinger_mavg().iloc[-1]

            # Stochastic
            stoch = StochasticOscillator(df['High'], df['Low'], df['Close'])
            indicators['stoch_k'] = stoch.stoch().iloc[-1]
            indicators['stoch_d'] = stoch.stoch_signal().iloc[-1]

            # Average True Range (ATR) - Volatilite ölçümü
            try:
                atr = AverageTrueRange(df['High'], df['Low'], df['Close'])
                indicators['atr'] = atr.average_true_range().iloc[-1]
            except Exception as e:
                logger.warning(f"ATR hesaplanamadı: {e}")
                indicators['atr'] = 0

            # Hareketli Ortalamalar
            indicators['sma_20'] = SMAIndicator(df['Close'], window=20).sma_indicator().iloc[-1]
            indicators['sma_50'] = SMAIndicator(df['Close'], window=50).sma_indicator().iloc[-1]
            indicators['sma_200'] = SMAIndicator(df['Close'], window=200).sma_indicator().iloc[-1]
            indicators['ema_5'] = EMAIndicator(df['Close'], window=5).ema_indicator().iloc[-1]
            indicators['ema_9'] = EMAIndicator(df['Close'], window=9).ema_indicator().iloc[-1]
            indicators['ema_12'] = EMAIndicator(df['Close'], window=12).ema_indicator().iloc[-1]
            indicators['ema_20'] = EMAIndicator(df['Close'], window=20).ema_indicator().iloc[-1]
            indicators['ema_26'] = EMAIndicator(df['Close'], window=26).ema_indicator().iloc[-1]
            indicators['ema_50'] = EMAIndicator(df['Close'], window=50).ema_indicator().iloc[-1]
            indicators['ema_200'] = EMAIndicator(df['Close'], window=200).ema_indicator().iloc[-1]

            # VWAP hesaplama - ARTIK EKLENDİ!
            indicators['vwap'] = calculate_vwap(df)

            # Destek ve Direnç
            recent_highs = df['High'].rolling(window=20).max()
            recent_lows = df['Low'].rolling(window=20).min()
            indicators['resistance'] = recent_highs.iloc[-1]
            indicators['support'] = recent_lows.iloc[-1]

            # EMA Kesişimleri
            ema_50 = EMAIndicator(df['Close'], window=50).ema_indicator()
            ema_200 = EMAIndicator(df['Close'], window=200).ema_indicator()
            ema_5 = EMAIndicator(df['Close'], window=5).ema_indicator()
            ema_20 = EMAIndicator(df['Close'], window=20).ema_indicator()

            indicators['ema_50_200_cross'] = (ema_50.iloc[-2] < ema_200.iloc[-2] and 
                                            ema_50.iloc[-1] > ema_200.iloc[-1]) if len(ema_50) >= 2 else False
            indicators['ema_5_20_cross'] = (ema_5.iloc[-2] < ema_20.iloc[-2] and 
                                          ema_5.iloc[-1] > ema_20.iloc[-1]) if len(ema_5) >= 2 else False

            # Williams %R (ek momentum indikatörü)
            try:
                high_14 = df['High'].rolling(window=14).max()
                low_14 = df['Low'].rolling(window=14).min()
                williams_r = -100 * (high_14.iloc[-1] - df['Close'].iloc[-1]) / (high_14.iloc[-1] - low_14.iloc[-1])
                indicators['williams_r'] = williams_r
            except:
                indicators['williams_r'] = 0

            # RSI verilerini DataFrame'e ekle (grafik için)
            df['RSI'] = rsi

            # EMA verilerini DataFrame'e ekle (grafik için)
            df['ema_20'] = EMAIndicator(df['Close'], window=20).ema_indicator()
            df['ema_50'] = EMAIndicator(df['Close'], window=50).ema_indicator()

            # Bollinger Bands verilerini DataFrame'e ekle
            df['bb_upper'] = bb.bollinger_hband()
            df['bb_middle'] = bb.bollinger_mavg()
            df['bb_lower'] = bb.bollinger_lband()

            return indicators
        except Exception as e:
            logger.error(f"Teknik indikatör hesaplama hatası: {e}")
            return {}

    @staticmethod
    async def get_fundamental_analysis(symbol: str) -> Dict:
        """Temel analiz bilgilerini al"""
        async with api_semaphore:
            loop = asyncio.get_event_loop()
            try:
                original_symbol = symbol.upper()
                if not symbol.endswith('.IS'):
                    symbol = symbol + '.IS'
                info = await loop.run_in_executor(executor, lambda: yf.Ticker(symbol).info)
                if not info or 'symbol' not in info or info.get('symbol') is None:
                    logger.error(f"Temel analiz için veri alınamadı: {symbol}")
                    return {'error': f"{original_symbol} için veri bulunamadı"}

                fundamentals = {
                    'pe_ratio': info.get('trailingPE', 'Bilgi Yok'),
                    'forward_pe': info.get('forwardPE', 'Bilgi Yok'),
                    'eps': info.get('trailingEps', 'Bilgi Yok'),
                    'dividend_yield': info.get('dividendYield', 'Bilgi Yok'),
                    'market_cap': info.get('marketCap', 'Bilgi Yok'),
                    'debt_to_equity': info.get('debtToEquity', 'Bilgi Yok'),
                    'roe': info.get('returnOnEquity', 'Bilgi Yok'),
                    'profit_margin': info.get('profitMargins', 'Bilgi Yok'),
                    'sector': info.get('sector', 'Bilgi Yok'),
                    'industry': info.get('industry', 'Bilgi Yok')
                }

                logger.info(f"Temel analiz alındı: {original_symbol}")
                return fundamentals
            except Exception as e:
                logger.error(f"Temel analiz hatası {symbol}: {str(e)}")
                return {'error': f"{original_symbol} için veri alınırken hata oluştu: {str(e)}"}

    @staticmethod
    def get_market_sentiment(indicators: Dict, current_price: float) -> str:
        """Piyasa duyarlılığını analiz et"""
        try:
            signals = []

            # RSI analizi
            rsi = indicators.get('rsi', 50)
            if rsi > 70:
                signals.append("🔴 RSI Aşırı Alım")
            elif rsi < 30:
                signals.append("🟢 RSI Aşırı Satım")
            else:
                signals.append("🟡 RSI Nötr")

            # MACD analizi
            macd = indicators.get('macd', 0)
            macd_signal = indicators.get('macd_signal', 0)
            if macd > macd_signal:
                signals.append("🟢 MACD Pozitif")
            else:
                signals.append("🔴 MACD Negatif")

            # Bollinger Bands analizi
            bb_upper = indicators.get('bb_upper', 0)
            bb_lower = indicators.get('bb_lower', 0)
            if current_price > bb_upper:
                signals.append("🔴 BB Üst Band Üstü")
            elif current_price < bb_lower:
                signals.append("🟢 BB Alt Band Altı")
            else:
                signals.append("🟡 BB Bandlar Arası")

            # VWAP analizi
            vwap = indicators.get('vwap', 0)
            if vwap > 0:
                if current_price > vwap:
                    signals.append("🟢 VWAP Üstünde")
                else:
                    signals.append("🔴 VWAP Altında")

            # EMA 50-200 Kesişimi
            if indicators.get('ema_50_200_cross', False):
                signals.append("🟢 EMA 50/200 Al Sinyali")

            # EMA 5-20 Kesişimi
            if indicators.get('ema_5_20_cross', False):
                signals.append("🟢 EMA 5/20 Al Sinyali")

            # Fiyat EMA 200 üstü kontrolü
            if current_price > indicators.get('ema_200', 0):
                signals.append("🟢 Fiyat EMA 200 Üstünde")

            # Fiyat EMA 9 üstü kontrolü
            if current_price > indicators.get('ema_9', 0):
                signals.append("🟢 Fiyat EMA 9 Üstünde")

            # Williams %R analizi
            williams_r = indicators.get('williams_r', 0)
            if williams_r < -80:
                signals.append("🟢 Williams %R Aşırı Satım")
            elif williams_r > -20:
                signals.append("🔴 Williams %R Aşırı Alım")

            # Genel değerlendirme
            positive_signals = len([s for s in signals if s.startswith("🟢")])
            negative_signals = len([s for s in signals if s.startswith("🔴")])

            if positive_signals > negative_signals:
                overall = "📈 Genel Görünüm: Pozitif"
            elif negative_signals > positive_signals:
                overall = "📉 Genel Görünüm: Negatif"
            else:
                overall = "➡️ Genel Görünüm: Nötr"

            return "\n".join(signals + [overall])
        except Exception as e:
            logger.error(f"Piyasa duyarlılığı analiz hatası: {e}")
            return "❌ Analiz yapılamadı"
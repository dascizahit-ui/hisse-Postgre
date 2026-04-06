import asyncio
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
from datetime import datetime
import yfinance as yf
from config import api_semaphore, executor, bist_stocks, TR_TZ
import os

# Windows için async ayarı
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logger = logging.getLogger(__name__)

# Telegram mesaj limiti
TELEGRAM_MSG_LIMIT = 4000


class MessageSplitter:
    """Telegram mesajlarını bölen yardımcı sınıf"""
    
    @staticmethod
    def split_message(text: str, limit: int = TELEGRAM_MSG_LIMIT) -> List[str]:
        """Uzun mesajı parçalara böl"""
        if len(text) <= limit:
            return [text]
        
        messages = []
        current_msg = ""
        
        paragraphs = text.split('\n\n')
        
        for para in paragraphs:
            if len(para) > limit:
                lines = para.split('\n')
                for line in lines:
                    if len(current_msg) + len(line) + 2 > limit:
                        if current_msg:
                            messages.append(current_msg.strip())
                        current_msg = line + '\n'
                    else:
                        current_msg += line + '\n'
            else:
                if len(current_msg) + len(para) + 2 > limit:
                    if current_msg:
                        messages.append(current_msg.strip())
                    current_msg = para + '\n\n'
                else:
                    current_msg += para + '\n\n'
        
        if current_msg.strip():
            messages.append(current_msg.strip())
        
        return messages
    
    @staticmethod
    async def send_long_message(update: Update, text: str, parse_mode: str = 'HTML'):
        """Uzun mesajı parçalar halinde gönder"""
        messages = MessageSplitter.split_message(text)
        
        for i, msg in enumerate(messages):
            if i == 0:
                await update.message.reply_text(msg, parse_mode=parse_mode)
            else:
                await asyncio.sleep(0.5)
                await update.message.reply_text(msg, parse_mode=parse_mode)
        
        return len(messages)


class FisherTransform:
    """Fisher Transform Indicator"""
    
    @staticmethod
    def calculate(prices, period=10):
        """Fisher Transform hesaplama"""
        try:
            lowest_low = prices.rolling(window=period).min()
            highest_high = prices.rolling(window=period).max()
            
            value = 2 * ((prices - lowest_low) / (highest_high - lowest_low)) - 1
            value = value.clip(-0.999, 0.999)
            fisher = 0.5 * np.log((1 + value) / (1 - value))
            
            return fisher
        except:
            return pd.Series([0] * len(prices))


class BBFisherWeeklyScanner:
    """Haftalık Bollinger Bands + Fisher Transform Scanner"""
    
    @staticmethod
    async def scan_single_stock(symbol: str) -> Optional[Dict]:
        """Tek bir hisseyi haftalık grafikte tara"""
        try:
            async with api_semaphore:
                loop = asyncio.get_event_loop()
                
                if not symbol.endswith('.IS'):
                    symbol_with_ext = symbol + '.IS'
                else:
                    symbol_with_ext = symbol
                
                # Haftalık veri al (2 yıl geriye)
                df = await loop.run_in_executor(
                    executor,
                    lambda: yf.Ticker(symbol_with_ext).history(period="2y", interval="1wk")
                )
                
                if df.empty or len(df) < 52:  # En az 1 yıllık veri
                    return None
                
                df = df.copy()
                
                # Bollinger Bands (20 hafta, 2 std)
                bb = BollingerBands(df['Close'], window=20, window_dev=2)
                df['bb_upper'] = bb.bollinger_hband()
                df['bb_middle'] = bb.bollinger_mavg()
                df['bb_lower'] = bb.bollinger_lband()
                
                # Fisher Transform (Period 9)
                df['fisher'] = FisherTransform.calculate(df['Close'], period=9)
                
                # EMA (haftalık)
                df['ema_9'] = EMAIndicator(df['Close'], window=9).ema_indicator()
                df['ema_20'] = EMAIndicator(df['Close'], window=20).ema_indicator()
                df['ema_50'] = EMAIndicator(df['Close'], window=50).ema_indicator()
                
                # RSI
                df['rsi'] = RSIIndicator(df['Close']).rsi()
                
                # MACD
                macd = MACD(df['Close'])
                df['macd'] = macd.macd()
                df['macd_signal'] = macd.macd_signal()
                
                # 52 haftalık en yüksek/düşük
                week_52_high = df['High'].tail(52).max()
                week_52_low = df['Low'].tail(52).min()
                current_price = df['Close'].iloc[-1]
                
                # 52 haftalık pozisyon (%)
                week_52_position = ((current_price - week_52_low) / (week_52_high - week_52_low)) * 100
                
                # === HAFTALIK STRATEJİ ===
                current = df.iloc[-1]
                prev1 = df.iloc[-2]
                prev2 = df.iloc[-3]
                prev3 = df.iloc[-4]
                
                # KURAL 1: BB ALT BANDINA DOKUNUŞ (son 3 hafta içinde)
                bb_touch = (
                    (prev3['Low'] <= prev3['bb_lower']) or
                    (prev2['Low'] <= prev2['bb_lower']) or
                    (prev1['Low'] <= prev1['bb_lower'])
                )
                
                # KURAL 2: FISHER YUKARIYA YÖNELIM
                fisher_rising = current['fisher'] > prev1['fisher'] > prev2['fisher']
                fisher_positive = current['fisher'] > 0
                fisher_cross = fisher_rising or fisher_positive
                
                # KURAL 3: FIYAT BB ALT BANDININ ÜZERİNDE
                price_above_bb = current['Close'] > current['bb_lower']
                
                # HAFTALIK ONAYLAMA (daha katı)
                ema_ok = current['Close'] > current['ema_20']
                rsi_ok = 35 < current['rsi'] < 70  # Haftalık için daha dar
                macd_ok = current['macd'] > current['macd_signal']
                
                # Trend onayı (haftalık için önemli)
                trend_ok = current['ema_9'] > current['ema_20']  # Kısa vadeli trend yukarı
                
                # SINYAL
                long_signal = bb_touch and fisher_cross and price_above_bb
                
                logger.info(f"W {symbol}: BB={bb_touch} Fisher={fisher_cross} Price={price_above_bb} RSI={current['rsi']:.1f}")
                
                if long_signal and ema_ok and rsi_ok:
                    logger.info(f"✓ HAFTALIK SINYAL: {symbol}")
                    
                    strength = sum([ema_ok, macd_ok, rsi_ok, trend_ok])
                    
                    # Potansiyel kar hesapla
                    potential_tp1 = ((current['bb_middle'] - current['Close']) / current['Close']) * 100
                    potential_tp2 = ((current['bb_upper'] - current['Close']) / current['Close']) * 100
                    potential_52h = ((week_52_high - current['Close']) / current['Close']) * 100
                    
                    return {
                        'symbol': symbol,
                        'price': float(current['Close']),
                        'bb_upper': float(current['bb_upper']),
                        'bb_middle': float(current['bb_middle']),
                        'bb_lower': float(current['bb_lower']),
                        'fisher': float(current['fisher']),
                        'rsi': float(current['rsi']),
                        'ema_9': float(current['ema_9']),
                        'ema_20': float(current['ema_20']),
                        'ema_50': float(current['ema_50']),
                        'macd': float(current['macd']),
                        'macd_signal': float(current['macd_signal']),
                        'signal_strength': strength,
                        'bb_touch': bb_touch,
                        'fisher_cross': fisher_cross,
                        'ema_ok': ema_ok,
                        'macd_ok': macd_ok,
                        'rsi_ok': rsi_ok,
                        'trend_ok': trend_ok,
                        'week_52_high': float(week_52_high),
                        'week_52_low': float(week_52_low),
                        'week_52_position': float(week_52_position),
                        'potential_tp1': potential_tp1,
                        'potential_tp2': potential_tp2,
                        'potential_52h': potential_52h
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"Weekly Scanner {symbol}: {e}")
            return None
    
    @staticmethod
    async def scan_all_stocks(stocks: List[str]) -> List[Dict]:
        """Tüm hisseleri tara"""
        tasks = [BBFisherWeeklyScanner.scan_single_stock(stock) for stock in stocks]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]


async def bb_fisher_weekly_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Haftalık BB Fisher Tarama Handler"""
    try:
        msg = await update.message.reply_text(
            "🔍 <b>HAFTALIK</b> BB + Fisher taraması başlıyor...\n"
            "⏳ Lütfen bekleyin...",
            parse_mode='HTML'
        )
        
        logger.info("Haftalık Tarama başladı")
        
        # Tara
        results = await BBFisherWeeklyScanner.scan_all_stocks(bist_stocks)
        results.sort(key=lambda x: x['signal_strength'], reverse=True)
        
        logger.info(f"Haftalık Tarama tamamlandı: {len(results)} sinyal")
        
        if not results:
            await msg.edit_text("❌ Haftalık grafikte sinyal bulunamadı")
            return
        
        # Mesaj oluştur
        text = "🎯 <b>HAFTALIK BB + FISHER LONG SİNYALLERİ</b>\n"
        text += f"⏰ {datetime.now(TR_TZ).strftime('%d.%m.%Y %H:%M')}\n"
        text += f"📊 Toplam Sinyal: {len(results)}\n"
        text += "=" * 55 + "\n\n"
        
        for i, r in enumerate(results[:15], 1):
            strength_bar = "🟢" * r['signal_strength'] + "⚪" * (4 - r['signal_strength'])
            
            text += f"<b>{i}. {r['symbol']}</b> {strength_bar}\n"
            text += f"💰 Fiyat: {r['price']:.2f} ₺\n"
            text += f"📍 BB: Alt={r['bb_lower']:.2f} | Orta={r['bb_middle']:.2f} | Üst={r['bb_upper']:.2f}\n"
            text += f"📊 Fisher: {r['fisher']:.2f} | RSI: {r['rsi']:.1f}\n"
            text += f"📈 52H Poz: %{r['week_52_position']:.0f} | 52H: {r['week_52_high']:.2f} ₺\n"
            text += f"🎯 TP1: %{r['potential_tp1']:.1f} | TP2: %{r['potential_tp2']:.1f} | 52H: %{r['potential_52h']:.1f}\n"
            text += f"✓ EMA: {'✅' if r['ema_ok'] else '❌'} | MACD: {'✅' if r['macd_ok'] else '❌'} | Trend: {'✅' if r['trend_ok'] else '❌'}\n"
            text += "-" * 55 + "\n"
        
      
       

        
        # Mesajı parçala ve gönder
        await msg.delete()
        await MessageSplitter.send_long_message(update, text)
        
    except Exception as e:
        logger.error(f"Weekly Handler hatası: {e}")
        await update.message.reply_text(f"❌ Hata: {str(e)}")


def bb_fisher_weekly_command() -> CommandHandler:
    """Weekly Handler döndür"""
    return CommandHandler('bbfisherw', bb_fisher_weekly_handler)
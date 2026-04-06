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


class BBFisher4HScanner:
    """4 Saatlik Bollinger Bands + Fisher Transform Scanner"""
    
    @staticmethod
    async def scan_single_stock(symbol: str) -> Optional[Dict]:
        """Tek bir hisseyi 4 saatlik grafikte tara"""
        try:
            async with api_semaphore:
                loop = asyncio.get_event_loop()
                
                if not symbol.endswith('.IS'):
                    symbol_with_ext = symbol + '.IS'
                else:
                    symbol_with_ext = symbol
                
                # 4 saatlik veri al (60 gün geriye, 4h interval)
                # yfinance'de 4h için "60d" period ve "1h" interval kullanıp sonra resample yapacağız
                # veya direkt "1h" alıp 4'e böleceğiz
                df = await loop.run_in_executor(
                    executor,
                    lambda: yf.Ticker(symbol_with_ext).history(period="60d", interval="1h")
                )
                
                if df.empty or len(df) < 100:
                    return None
                
                # 1 saatlik veriyi 4 saatliğe çevir (resample)
                df_4h = df.resample('4h').agg({
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last',
                    'Volume': 'sum'
                }).dropna()
                
                if len(df_4h) < 50:
                    return None
                
                df = df_4h.copy()
                
                # Bollinger Bands (20, 2)
                bb = BollingerBands(df['Close'], window=20, window_dev=2)
                df['bb_upper'] = bb.bollinger_hband()
                df['bb_middle'] = bb.bollinger_mavg()
                df['bb_lower'] = bb.bollinger_lband()
                
                # Fisher Transform (Period 9)
                df['fisher'] = FisherTransform.calculate(df['Close'], period=9)
                
                # EMA
                df['ema_9'] = EMAIndicator(df['Close'], window=9).ema_indicator()
                df['ema_20'] = EMAIndicator(df['Close'], window=20).ema_indicator()
                df['ema_50'] = EMAIndicator(df['Close'], window=50).ema_indicator()
                
                # RSI
                df['rsi'] = RSIIndicator(df['Close']).rsi()
                
                # MACD
                macd = MACD(df['Close'])
                df['macd'] = macd.macd()
                df['macd_signal'] = macd.macd_signal()
                
                # === 4 SAATLİK STRATEJİ ===
                current = df.iloc[-1]
                prev1 = df.iloc[-2]
                prev2 = df.iloc[-3]
                prev3 = df.iloc[-4]
                
                # KURAL 1: BB ALT BANDINA DOKUNUŞ (son 3 mum içinde)
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
                
                # ONAYLAMA
                ema_ok = current['Close'] > current['ema_20']
                rsi_ok = 30 < current['rsi'] < 75  # 4H için biraz daha dar
                macd_ok = current['macd'] > current['macd_signal']
                
                # SINYAL
                long_signal = bb_touch and fisher_cross and price_above_bb
                
                logger.info(f"4H {symbol}: BB={bb_touch} Fisher={fisher_cross} Price={price_above_bb} RSI={current['rsi']:.1f}")
                
                if long_signal and ema_ok and rsi_ok:
                    logger.info(f"✓ 4H SINYAL: {symbol}")
                    
                    strength = sum([ema_ok, macd_ok, rsi_ok])
                    
                    # Potansiyel kar hesapla
                    potential_tp1 = ((current['bb_middle'] - current['Close']) / current['Close']) * 100
                    potential_tp2 = ((current['bb_upper'] - current['Close']) / current['Close']) * 100
                    
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
                        'potential_tp1': potential_tp1,
                        'potential_tp2': potential_tp2
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"4H Scanner {symbol}: {e}")
            return None
    
    @staticmethod
    async def scan_all_stocks(stocks: List[str]) -> List[Dict]:
        """Tüm hisseleri tara"""
        tasks = [BBFisher4HScanner.scan_single_stock(stock) for stock in stocks]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]


async def bb_fisher_4h_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """4 Saatlik BB Fisher Tarama Handler"""
    try:
        msg = await update.message.reply_text(
            "🔍 <b>4 SAATLİK</b> BB + Fisher taraması başlıyor...\n"
            "⏳ Lütfen bekleyin...",
            parse_mode='HTML'
        )
        
        logger.info("4H Tarama başladı")
        
        # Tara
        results = await BBFisher4HScanner.scan_all_stocks(bist_stocks)
        results.sort(key=lambda x: x['signal_strength'], reverse=True)
        
        logger.info(f"4H Tarama tamamlandı: {len(results)} sinyal")
        
        if not results:
            await msg.edit_text("❌ 4 saatlik grafikte sinyal bulunamadı")
            return
        
        # Mesaj oluştur
        text = "🎯 <b>4 SAATLİK BB + FISHER LONG SİNYALLERİ</b>\n"
        text += f"⏰ {datetime.now(TR_TZ).strftime('%d.%m.%Y %H:%M')}\n"
        text += f"📊 Toplam Sinyal: {len(results)}\n"
        text += "=" * 55 + "\n\n"
        
        for i, r in enumerate(results[:15], 1):
            strength_bar = "🟢" * r['signal_strength'] + "⚪" * (3 - r['signal_strength'])
            
            text += f"<b>{i}. {r['symbol']}</b> {strength_bar}\n"
            text += f"💰 Fiyat: {r['price']:.2f} ₺\n"
            text += f"📍 BB: Alt={r['bb_lower']:.2f} | Orta={r['bb_middle']:.2f} | Üst={r['bb_upper']:.2f}\n"
            text += f"📊 Fisher: {r['fisher']:.2f} | RSI: {r['rsi']:.1f}\n"
            text += f"🎯 EMA20: {r['ema_20']:.2f} | MACD: {'✅' if r['macd_ok'] else '❌'}\n"
            text += f"📈 TP1: %{r['potential_tp1']:.1f} | TP2: %{r['potential_tp2']:.1f}\n"
            text += "-" * 55 + "\n"
        
        
        # Mesajı parçala ve gönder
        await msg.delete()
        await MessageSplitter.send_long_message(update, text)
        
    except Exception as e:
        logger.error(f"4H Handler hatası: {e}")
        await update.message.reply_text(f"❌ Hata: {str(e)}")


def bb_fisher_4h_command() -> CommandHandler:
    """4H Handler döndür"""
    return CommandHandler('bbfisher4h', bb_fisher_4h_handler)
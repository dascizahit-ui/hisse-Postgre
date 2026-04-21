import asyncio
import logging
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from config import api_semaphore, executor
from database import get_db_connection
from typing import Dict, List, Optional


logger = logging.getLogger(__name__)

class HourlySignalGenerator:
    """Saatlik sinyal üretici sınıfı"""

    def __init__(self):
        self.init_signals_db()

    def init_signals_db(self):
        """Sinyal veritabanı tablolarını oluştur"""
        try:
            with get_db_connection() as conn:
                c = conn.cursor()

                # Saatlik sinyaller tablosu
                c.execute('''CREATE TABLE IF NOT EXISTS hourly_signals (
                    id SERIAL PRIMARY KEY,
                    symbol TEXT,
                    signal_type TEXT,
                    signal_strength INTEGER,
                    price REAL,
                    volume REAL,
                    rsi REAL,
                    macd REAL,
                    ema_cross BOOLEAN,
                    bb_position TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    hour_timestamp TIMESTAMP
                )''')

                # Aktif sinyal takipleri tablosu
                c.execute('''CREATE TABLE IF NOT EXISTS signal_subscriptions (
                    user_id BIGINT,
                    symbol TEXT,
                    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    PRIMARY KEY (user_id, symbol),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )''')

                # İndeksler
                c.execute('CREATE INDEX IF NOT EXISTS idx_hourly_signals_symbol ON hourly_signals(symbol)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_hourly_signals_timestamp ON hourly_signals(hour_timestamp)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_signal_subscriptions_user ON signal_subscriptions(user_id)')

                conn.commit()
                logger.info("Sinyal tabloları oluşturuldu")

        except Exception as e:
            logger.error(f"Sinyal veritabanı oluşturma hatası: {e}")

    async def get_hourly_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Saatlik veri al (son 5 gün)"""
        async with api_semaphore:
            loop = asyncio.get_event_loop()
            try:
                if not symbol.endswith('.IS'):
                    symbol += '.IS'

                df = await loop.run_in_executor(
                    executor, 
                    lambda: yf.Ticker(symbol).history(period="5d", interval="1h")
                )

                if df.empty:
                    return None

                return df

            except Exception as e:
                logger.error(f"Saatlik veri alınamadı {symbol}: {e}")
                return None

    def calculate_hourly_indicators(self, df: pd.DataFrame) -> Dict:
        """Saatlik teknik göstergeleri hesapla"""
        try:
            indicators = {}

            # RSI (14 period)
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            indicators['rsi'] = rsi.iloc[-1] if not rsi.empty else 50

            # MACD (12, 26, 9)
            exp1 = df['Close'].ewm(span=12).mean()
            exp2 = df['Close'].ewm(span=26).mean()
            macd_line = exp1 - exp2
            signal_line = macd_line.ewm(span=9).mean()
            indicators['macd'] = macd_line.iloc[-1]
            indicators['macd_signal'] = signal_line.iloc[-1]
            indicators['macd_histogram'] = (macd_line - signal_line).iloc[-1]

            # EMA'lar
            ema_9 = df['Close'].ewm(span=9).mean()
            ema_21 = df['Close'].ewm(span=21).mean()
            ema_50 = df['Close'].ewm(span=50).mean()

            indicators['ema_9'] = ema_9.iloc[-1]
            indicators['ema_21'] = ema_21.iloc[-1]
            indicators['ema_50'] = ema_50.iloc[-1] if len(ema_50) > 0 else 0

            # EMA kesişim kontrolü
            if len(ema_9) >= 2 and len(ema_21) >= 2:
                indicators['ema_9_21_cross_up'] = (
                    ema_9.iloc[-2] < ema_21.iloc[-2] and ema_9.iloc[-1] > ema_21.iloc[-1]
                )
                indicators['ema_9_21_cross_down'] = (
                    ema_9.iloc[-2] > ema_21.iloc[-2] and ema_9.iloc[-1] < ema_21.iloc[-1]
                )
            else:
                indicators['ema_9_21_cross_up'] = False
                indicators['ema_9_21_cross_down'] = False

            # Bollinger Bands (20 period, 2 std)
            bb_period = min(20, len(df))
            if bb_period > 1:
                bb_middle = df['Close'].rolling(window=bb_period).mean()
                bb_std = df['Close'].rolling(window=bb_period).std()
                bb_upper = bb_middle + (bb_std * 2)
                bb_lower = bb_middle - (bb_std * 2)

                current_price = df['Close'].iloc[-1]
                indicators['bb_upper'] = bb_upper.iloc[-1]
                indicators['bb_middle'] = bb_middle.iloc[-1]
                indicators['bb_lower'] = bb_lower.iloc[-1]

                # BB pozisyonu
                if current_price > bb_upper.iloc[-1]:
                    indicators['bb_position'] = 'ÜSTÜNDE'
                elif current_price < bb_lower.iloc[-1]:
                    indicators['bb_position'] = 'ALTINDA'
                else:
                    indicators['bb_position'] = 'ORTADA'
            else:
                indicators['bb_position'] = 'YETERSİZ_VERİ'

            # Hacim analizi
            volume_ma = df['Volume'].rolling(window=20).mean()
            indicators['volume_ratio'] = (
                df['Volume'].iloc[-1] / volume_ma.iloc[-1] 
                if volume_ma.iloc[-1] > 0 else 1
            )

            # Momentum (Price Rate of Change)
            if len(df) >= 10:
                price_10_ago = df['Close'].iloc[-10]
                current_price = df['Close'].iloc[-1]
                indicators['momentum'] = ((current_price - price_10_ago) / price_10_ago) * 100
            else:
                indicators['momentum'] = 0

            return indicators

        except Exception as e:
            logger.error(f"Saatlik gösterge hesaplama hatası: {e}")
            return {}

    def generate_signal(self, symbol: str, df: pd.DataFrame, indicators: Dict) -> Dict:
        """Sinyal üret"""
        try:
            current_price = df['Close'].iloc[-1]
            current_volume = df['Volume'].iloc[-1]

            # Sinyal puanı hesaplama
            buy_signals = 0
            sell_signals = 0
            signal_reasons = []

            # RSI analizi
            rsi = indicators.get('rsi', 50)
            if rsi < 30:
                buy_signals += 2
                signal_reasons.append("🟢 RSI Aşırı Satım (<30)")
            elif rsi > 70:
                sell_signals += 2
                signal_reasons.append("🔴 RSI Aşırı Alım (>70)")
            elif rsi < 40:
                buy_signals += 1
                signal_reasons.append("🟡 RSI Satım Bölgesi")
            elif rsi > 60:
                sell_signals += 1
                signal_reasons.append("🟡 RSI Alım Bölgesi")

            # MACD analizi
            macd = indicators.get('macd', 0)
            macd_signal = indicators.get('macd_signal', 0)
            macd_hist = indicators.get('macd_histogram', 0)

            if macd > macd_signal and macd_hist > 0:
                buy_signals += 2
                signal_reasons.append("🟢 MACD Al Sinyali")
            elif macd < macd_signal and macd_hist < 0:
                sell_signals += 2
                signal_reasons.append("🔴 MACD Sat Sinyali")

            # EMA kesişimleri
            if indicators.get('ema_9_21_cross_up', False):
                buy_signals += 3
                signal_reasons.append("🟢 EMA 9/21 Al Kesişimi")
            elif indicators.get('ema_9_21_cross_down', False):
                sell_signals += 3
                signal_reasons.append("🔴 EMA 9/21 Sat Kesişimi")

            # EMA trend kontrolü
            ema_9 = indicators.get('ema_9', 0)
            ema_21 = indicators.get('ema_21', 0)
            ema_50 = indicators.get('ema_50', 0)

            if current_price > ema_9 > ema_21 > ema_50:
                buy_signals += 1
                signal_reasons.append("🟢 Güçlü Yükselis Trend")
            elif current_price < ema_9 < ema_21 < ema_50:
                sell_signals += 1
                signal_reasons.append("🔴 Güçlü Düşüş Trend")

            # Bollinger Bands
            bb_position = indicators.get('bb_position', 'ORTADA')
            if bb_position == 'ALTINDA':
                buy_signals += 1
                signal_reasons.append("🟢 BB Alt Band Altında")
            elif bb_position == 'ÜSTÜNDE':
                sell_signals += 1
                signal_reasons.append("🔴 BB Üst Band Üstünde")

            # Hacim onayı
            volume_ratio = indicators.get('volume_ratio', 1)
            if volume_ratio > 1.5:
                if buy_signals > sell_signals:
                    buy_signals += 1
                    signal_reasons.append("🚀 Yüksek Hacim Onayı")
                else:
                    sell_signals += 1
                    signal_reasons.append("⚠️ Yüksek Hacim Sat Baskısı")

            # Momentum
            momentum = indicators.get('momentum', 0)
            if momentum > 5:
                buy_signals += 1
                signal_reasons.append("🟢 Pozitif Momentum")
            elif momentum < -5:
                sell_signals += 1
                signal_reasons.append("🔴 Negatif Momentum")

            # Sinyal belirleme
            signal_strength = abs(buy_signals - sell_signals)

            if buy_signals > sell_signals and signal_strength >= 3:
                signal_type = "AL"
            elif sell_signals > buy_signals and signal_strength >= 3:
                signal_type = "SAT"
            else:
                signal_type = "BEKLE"

            return {
                'symbol': symbol.replace('.IS', ''),
                'signal_type': signal_type,
                'signal_strength': signal_strength,
                'price': current_price,
                'volume': current_volume,
                'rsi': rsi,
                'macd': macd,
                'ema_cross': indicators.get('ema_9_21_cross_up', False) or indicators.get('ema_9_21_cross_down', False),
                'bb_position': bb_position,
                'buy_signals': buy_signals,
                'sell_signals': sell_signals,
                'reasons': signal_reasons,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'hour_timestamp': datetime.now().strftime('%Y-%m-%d %H:00')
            }

        except Exception as e:
            logger.error(f"Sinyal üretme hatası {symbol}: {e}")
            return None

    async def process_hourly_signal(self, symbol: str) -> Optional[Dict]:
        """Bir hisse için saatlik sinyal işle"""
        try:
            # Veri al
            df = await self.get_hourly_data(symbol)
            if df is None or df.empty:
                return None

            # Göstergeleri hesapla
            indicators = self.calculate_hourly_indicators(df)
            if not indicators:
                return None

            # Sinyal üret
            signal = self.generate_signal(symbol, df, indicators)
            if not signal:
                return None

            # Veritabanına kaydet
            await self.save_signal_to_db(signal)

            return signal

        except Exception as e:
            logger.error(f"Saatlik sinyal işleme hatası {symbol}: {e}")
            return None

    async def save_signal_to_db(self, signal: Dict):
        """Sinyali veritabanına kaydet"""
        try:
            with get_db_connection() as conn:
                c = conn.cursor()

                # Aynı saate ait sinyal var mı kontrol et
                c.execute('''SELECT id FROM hourly_signals 
                           WHERE symbol = %s AND hour_timestamp = %s''',
                         (signal['symbol'], signal['hour_timestamp']))

                existing = c.fetchone()

                if existing:
                    # Güncelle
                    c.execute('''UPDATE hourly_signals SET
                               signal_type = %s, signal_strength = %s, price = %s,
                               volume = %s, rsi = %s, macd = %s, ema_cross = %s,
                               bb_position = %s, created_at = CURRENT_TIMESTAMP
                               WHERE symbol = %s AND hour_timestamp = %s''',
                             (signal['signal_type'], signal['signal_strength'], 
                              signal['price'], signal['volume'], signal['rsi'],
                              signal['macd'], signal['ema_cross'], signal['bb_position'],
                              signal['symbol'], signal['hour_timestamp']))
                else:
                    # Yeni kayıt
                    c.execute('''INSERT INTO hourly_signals 
                               (symbol, signal_type, signal_strength, price, volume,
                                rsi, macd, ema_cross, bb_position, hour_timestamp)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                             (signal['symbol'], signal['signal_type'], signal['signal_strength'],
                              signal['price'], signal['volume'], signal['rsi'], signal['macd'],
                              signal['ema_cross'], signal['bb_position'], signal['hour_timestamp']))

                conn.commit()

        except Exception as e:
            logger.error(f"Sinyal veritabanına kaydetme hatası: {e}")

# Bot komut handlers
async def hourly_signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saatlik sinyal komutu"""
    try:
        if not context.args:
            await update.message.reply_text(
                "❓ **Saatlik Sinyal Kullanımı:**\n\n"
                "📊 `/saatlik HISSE_KODU` - Tek hisse sinyal analizi\n"
                "ℹ️ **Bilgi:**\n"
                "• Saatlik veriler kullanılır (15-20dk gecikme)\n"
                "• RSI, MACD, EMA kesişimleri analiz edilir\n"
                "• AL/SAT/BEKLE sinyalleri üretilir\n"
                "• Sinyal gücü 1-10 arası puanlanır",
                parse_mode='Markdown'
            )
            return

        symbol = context.args[0].upper()
        await update.message.reply_text(f"⏳ {symbol} için saatlik sinyal analizi yapılıyor...")

        generator = HourlySignalGenerator()
        signal = await generator.process_hourly_signal(symbol)

        if not signal:
            await update.message.reply_text(f"❌ {symbol} için sinyal üretilemedi.")
            return

        # Sinyal mesajını formatla
        signal_emoji = {
            "AL": "🟢",
            "SAT": "🔴", 
            "BEKLE": "🟡"
        }

        strength_stars = "⭐" * min(signal['signal_strength'], 5)

        message = f"📊 **{signal['symbol']} - Saatlik Sinyal**\n\n"
        message += f"{signal_emoji.get(signal['signal_type'], '❓')} **Sinyal: {signal['signal_type']}** {strength_stars}\n"
        message += f"💪 **Güç:** {signal['signal_strength']}/10\n"
        message += f"💰 **Fiyat:** {signal['price']:.2f} ₺\n"
        message += f"📊 **RSI:** {signal['rsi']:.1f}\n"
        message += f"📈 **MACD:** {signal['macd']:.4f}\n"
        message += f"🎯 **BB Pozisyon:** {signal['bb_position']}\n"
        message += f"⏰ **Zaman:** {signal['timestamp']}\n\n"

        message += "🔍 **Analiz Detayları:**\n"
        for reason in signal['reasons'][:5]:  # İlk 5 sebep
            message += f"• {reason}\n"

        message += f"\n📊 Al Sinyali: {signal['buy_signals']} | Sat Sinyali: {signal['sell_signals']}\n"
        message += "\n⚠️ *Bu bilgiler yatırım tavsiyesi değildir.*"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Saatlik sinyal komutu hatası: {e}")
        await update.message.reply_text("❌ Sinyal analizi sırasında hata oluştu.")

async def signal_subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sinyal takip komutu"""
    try:
        if not context.args:
            await update.message.reply_text("❓ Kullanım: /sinyal_takip HISSE_KODU")
            return

        user_id = update.effective_user.id
        username = update.effective_user.username
        symbol = context.args[0].upper()

        with get_db_connection() as conn:
            c = conn.cursor()

            # Kullanıcıyı users tablosuna ekle (varsa güncelle)
            c.execute(
                'INSERT INTO users (user_id, username) VALUES (%s, %s) '
                'ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username',
                (user_id, username)
            )

            # Takip ekle
            c.execute('''INSERT INTO signal_subscriptions
                        (user_id, symbol, is_active) VALUES (%s, %s, 1) ON CONFLICT (user_id, symbol) DO UPDATE SET is_active = 1''',
                     (user_id, symbol))
            conn.commit()

        await update.message.reply_text(
            f"🔔 **{symbol}** için saatlik sinyal bildirimleri aktifleştirildi!\n"
            "AL/SAT sinyalleri otomatik olarak gönderilecek."
        )

    except Exception as e:
        logger.error(f"Sinyal takip hatası: {e}")
        await update.message.reply_text("❌ Sinyal takibi eklenirken hata oluştu.")

async def signal_unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sinyal takip durdurma komutu"""
    try:
        if not context.args:
            await update.message.reply_text("❓ Kullanım: /sinyal_durdur HISSE_KODU")
            return

        user_id = update.effective_user.id
        symbol = context.args[0].upper()

        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE signal_subscriptions SET is_active = 0 WHERE user_id = %s AND symbol = %s',
                     (user_id, symbol))
            conn.commit()

        await update.message.reply_text(f"🔕 **{symbol}** sinyal bildirimleri durduruldu.")

    except Exception as e:
        logger.error(f"Sinyal durdurma hatası: {e}")
        await update.message.reply_text("❌ Sinyal durdurulurken hata oluştu.")

async def signal_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Takip edilen sinyaller listesi"""
    try:
        user_id = update.effective_user.id

        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('''SELECT symbol, subscribed_at FROM signal_subscriptions 
                        WHERE user_id = %s AND is_active = 1 ORDER BY subscribed_at DESC''',
                     (user_id,))
            subscriptions = c.fetchall()

        if not subscriptions:
            await update.message.reply_text("📭 Henüz hiç hisse takip etmiyorsunuz.")
            return

        message = "🔔 **Takip Ettiğiniz Hisseler:**\n\n"
        for sub in subscriptions:
            subscribed_at = sub[1].strftime('%Y-%m-%d') if hasattr(sub[1], 'strftime') else str(sub[1])[:10]
            message += f"📊 **{sub[0]}** - {subscribed_at}\n"

        message += f"\n📊 Toplam: {len(subscriptions)} hisse"
        message += "\n\n❓ `/sinyal_durdur HISSE_KODU` ile durdurabilirsiniz."

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Sinyal listesi hatası: {e}")
        await update.message.reply_text("❌ Liste alınırken hata oluştu.")

# Handler fonksiyonları
def hourly_signal_handler():
    return CommandHandler('saatlik', hourly_signal_command)

def signal_subscribe_handler():
    return CommandHandler('sinyal_takip', signal_subscribe_command)

def signal_unsubscribe_handler():
    return CommandHandler('sinyal_durdur', signal_unsubscribe_command)

def signal_list_handler():
    return CommandHandler('takip_listesi', signal_list_command)
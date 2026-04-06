import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict
from telegram.ext import Application
from database import get_db_connection
from handlers.hourly_signals import HourlySignalGenerator

logger = logging.getLogger(__name__)

class SignalBackgroundService:
    """Arka plan sinyal servisi - sürekli çalışır"""

    def __init__(self, application: Application):
        self.application = application
        self.signal_generator = HourlySignalGenerator()
        self.last_signal_time = {}  # Her hisse için son sinyal zamanı
        self.is_running = False

    async def get_subscribed_symbols(self) -> List[str]:
        """Takip edilen hisse listesini al"""
        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute('''SELECT DISTINCT symbol FROM signal_subscriptions 
                           WHERE is_active = 1''')
                symbols = [row[0] for row in c.fetchall()]
                return symbols
        except Exception as e:
            logger.error(f"Takip edilen hisseler alınırken hata: {e}")
            return []

    async def get_symbol_subscribers(self, symbol: str) -> List[int]:
        """Belirli bir hisseyi takip eden kullanıcıları al"""
        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute('''SELECT user_id FROM signal_subscriptions 
                           WHERE symbol = %s AND is_active = 1''', (symbol,))
                user_ids = [row[0] for row in c.fetchall()]
                return user_ids
        except Exception as e:
            logger.error(f"{symbol} takipçileri alınırken hata: {e}")
            return []

    async def should_send_signal(self, symbol: str, signal: Dict) -> bool:
        """Sinyal gönderilmeli mi kontrol et"""
        try:
            current_time = datetime.now()
            current_hour = current_time.replace(minute=0, second=0, microsecond=0)

            # Son gönderilen sinyal zamanını kontrol et
            last_time = self.last_signal_time.get(symbol)

            # Aynı saatte sinyal gönderilmemiş ve AL/SAT sinyali ise gönder
            if (signal['signal_type'] in ['AL', 'SAT'] and 
                signal['signal_strength'] >= 4 and  # Minimum güç
                (last_time is None or last_time < current_hour)):
                return True

            return False

        except Exception as e:
            logger.error(f"Sinyal kontrol hatası {symbol}: {e}")
            return False

    async def send_signal_to_users(self, symbol: str, signal: Dict, user_ids: List[int]):
        """Kullanıcılara sinyal gönder"""
        try:
            signal_emoji = {"AL": "🟢", "SAT": "🔴"}
            emoji = signal_emoji.get(signal['signal_type'], '❓')

            # Mesajı hazırla
            message = f"🚨 **SAATLİK SİNYAL** 🚨\n\n"
            message += f"{emoji} **{signal['symbol']}: {signal['signal_type']}**\n"
            message += f"💪 **Güç:** {'⭐' * min(signal['signal_strength'], 5)}\n"
            message += f"💰 **Fiyat:** {signal['price']:.2f} ₺\n"
            message += f"📊 **RSI:** {signal['rsi']:.1f}\n"
            message += f"⏰ **Zaman:** {signal['timestamp']}\n\n"

            # İlk 3 sebebi ekle
            if 'reasons' in signal and signal['reasons']:
                message += "🔍 **Sebepler:**\n"
                for reason in signal['reasons'][:3]:
                    message += f"• {reason}\n"

            message += "\n⚠️ *Yatırım tavsiyesi değildir. Kendi analizinizi yapın.*"

            # Kullanıcılara gönder
            sent_count = 0
            for user_id in user_ids:
                try:
                    await self.application.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode='Markdown'
                    )
                    sent_count += 1

                    # Rate limiting için kısa bekle
                    await asyncio.sleep(0.1)

                except Exception as e:
                    logger.warning(f"Kullanıcıya sinyal gönderilemedi {user_id}: {e}")
                    continue

            logger.info(f"{signal['symbol']} sinyali {sent_count} kullanıcıya gönderildi")

            # Son gönderim zamanını güncelle
            self.last_signal_time[symbol] = datetime.now().replace(minute=0, second=0, microsecond=0)

        except Exception as e:
            logger.error(f"Sinyal gönderme hatası {symbol}: {e}")

    async def process_symbol_signals(self, symbol: str):
        """Bir hisse için sinyal işle"""
        try:
            # Sinyal üret
            signal = await self.signal_generator.process_hourly_signal(symbol)
            if not signal:
                return

            # Sinyal gönderilmeli mi kontrol et
            should_send = await self.should_send_signal(symbol, signal)
            if not should_send:
                return

            # Takipçileri al
            subscribers = await self.get_symbol_subscribers(symbol)
            if not subscribers:
                return

            # Sinyali gönder
            await self.send_signal_to_users(symbol, signal, subscribers)

        except Exception as e:
            logger.error(f"Hisse sinyal işleme hatası {symbol}: {e}")

    async def run_signal_cycle(self):
        """Bir sinyal döngüsü çalıştır"""
        try:
            # Takip edilen hisseleri al
            symbols = await self.get_subscribed_symbols()
            if not symbols:
                logger.debug("Takip edilen hisse yok")
                return

            logger.info(f"{len(symbols)} hisse için sinyal kontrol ediliyor")

            # Her hisse için paralel olarak sinyal işle (max 5 paralel)
            semaphore = asyncio.Semaphore(5)

            async def process_with_semaphore(symbol):
                async with semaphore:
                    await self.process_symbol_signals(symbol)
                    # Hisseler arası kısa bekleme
                    await asyncio.sleep(1)

            # Paralel işlem başlat
            tasks = [process_with_semaphore(symbol) for symbol in symbols]
            await asyncio.gather(*tasks, return_exceptions=True)

            logger.info("Sinyal döngüsü tamamlandı")

        except Exception as e:
            logger.error(f"Sinyal döngüsü hatası: {e}")

    async def start_background_service(self):
        """Arka plan servisini başlat"""
        logger.info("Sinyal arka plan servisi başlatılıyor...")
        self.is_running = True

        while self.is_running:
            try:
                current_time = datetime.now()

                # Piyasa saatleri kontrolü (09:30 - 18:00, Pazartesi-Cuma)
                is_market_hours = (
                    current_time.hour >= 9 and current_time.hour <= 18 and
                    current_time.weekday() < 5  # Pazartesi=0, Cuma=4
                )

                if is_market_hours:
                    # Saatlik sinyal döngüsü (her saatin 5. dakikasında çalış)
                    if current_time.minute == 5:
                        logger.info("Saatlik sinyal döngüsü başlatılıyor")
                        await self.run_signal_cycle()

                        # Bir sonraki saatin 5. dakikasına kadar bekle
                        await asyncio.sleep(3600)  # 1 saat bekle
                    else:
                        # Saatin 5. dakikasını bekle
                        minutes_to_wait = (65 - current_time.minute) % 60
                        await asyncio.sleep(minutes_to_wait * 60)
                else:
                    # Piyasa dışı saatlerde 30 dakika bekle
                    logger.debug("Piyasa kapalı, 30 dakika bekle")
                    await asyncio.sleep(1800)

            except Exception as e:
                logger.error(f"Arka plan servis hatası: {e}")
                await asyncio.sleep(300)  # 5 dakika bekle ve tekrar dene

    def stop_service(self):
        """Servisi durdur"""
        logger.info("Sinyal arka plan servisi durduruluyor...")
        self.is_running = False

# Arka plan sinyal kontrolü için job fonksiyonu
async def check_hourly_signals_job(context):
    """Job queue için saatlik sinyal kontrol fonksiyonu"""
    try:
        application = context.job.data['application']
        service = context.job.data.get('signal_service')

        if not service:
            service = SignalBackgroundService(application)
            context.job.data['signal_service'] = service

        # Piyasa saatleri kontrolü
        current_time = datetime.now()
        is_market_hours = (
            current_time.hour >= 9 and current_time.hour <= 18 and
            current_time.weekday() < 5
        )

        if is_market_hours:
            await service.run_signal_cycle()

    except Exception as e:
        logger.error(f"Saatlik sinyal job hatası: {e}")

# Manuel sinyal kontrol komutu
async def manual_signal_check_command(update, context):
    """Manuel sinyal kontrol komutu (admin)"""
    try:
        user_id = update.effective_user.id

        # Admin kontrolü (isteğe bağlı)
        # if user_id not in ADMIN_IDS:
        #     return

        await update.message.reply_text("🔄 Manuel sinyal kontrolü başlatılıyor...")

        service = SignalBackgroundService(context.application)
        await service.run_signal_cycle()

        await update.message.reply_text("✅ Manuel sinyal kontrolü tamamlandı!")

    except Exception as e:
        logger.error(f"Manuel sinyal kontrol hatası: {e}")
        await update.message.reply_text("❌ Manuel kontrol sırasında hata oluştu.")

# İstatistik komutu
async def signal_stats_command(update, context):
    """Sinyal istatistikleri komutu"""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()

            # Son 24 saatte gönderilen sinyaller
            c.execute('''SELECT signal_type, COUNT(*) FROM hourly_signals 
                        WHERE created_at >= datetime('now', '-1 day')
                        GROUP BY signal_type''')
            recent_signals = c.fetchall()

            # Toplam takip edilen hisse sayısı
            c.execute('''SELECT COUNT(DISTINCT symbol) FROM signal_subscriptions 
                        WHERE is_active = 1''')
            total_symbols = c.fetchone()[0]

            # Toplam aktif kullanıcı sayısı
            c.execute('''SELECT COUNT(DISTINCT user_id) FROM signal_subscriptions 
                        WHERE is_active = 1''')
            total_users = c.fetchone()[0]

            # En çok takip edilen hisseler
            c.execute('''SELECT symbol, COUNT(*) as count FROM signal_subscriptions 
                        WHERE is_active = 1 
                        GROUP BY symbol 
                        ORDER BY count DESC LIMIT 5''')
            top_symbols = c.fetchall()

        message = "📊 **Sinyal İstatistikleri**\n\n"
        message += f"👥 **Aktif Kullanıcı:** {total_users}\n"
        message += f"📈 **Takip Edilen Hisse:** {total_symbols}\n\n"

        message += "🕐 **Son 24 Saat Sinyaller:**\n"
        for signal_type, count in recent_signals:
            emoji = {"AL": "🟢", "SAT": "🔴", "BEKLE": "🟡"}.get(signal_type, "❓")
            message += f"{emoji} {signal_type}: {count}\n"

        if top_symbols:
            message += "\n🔥 **En Popüler Hisseler:**\n"
            for symbol, count in top_symbols:
                message += f"📊 {symbol}: {count} takipçi\n"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"İstatistik komutu hatası: {e}")
        await update.message.reply_text("❌ İstatistikler alınırken hata oluştu.")

# Handler fonksiyonları
def manual_signal_check_handler():
    from telegram.ext import CommandHandler
    return CommandHandler('sinyal_kontrol', manual_signal_check_command)

def signal_stats_handler():
    from telegram.ext import CommandHandler
    return CommandHandler('sinyal_stats', signal_stats_command)
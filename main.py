import asyncio
import logging
import platform
from telegram import Update
from telegram.ext import Application
from handlers.bb_fisher_scanner import bb_fisher_scan_command
from handlers.bb_fisher_4h import bb_fisher_4h_command
from handlers.bb_fisher_weekly import bb_fisher_weekly_command
from config import TOKEN
from database import init_db
from handlers.ultimate_scanner import ultimate_scanner_handler, ultimate_scan_command

from handlers import (
    start_handler,
    help_handler,
    get_chat_id_handler,
    silent_handler,
    mute_handler,
    ban_handler,
    unban_handler,
    unmute_handler,
    report_handler,
    stock_info_handler,
    technical_analysis_handler,
    fundamental_analysis_handler,
    compare_handler,
    crossovers_handler,
    set_alert_handler,
    my_alerts_handler,
    cancel_alert_handler,
    button_callback_handler,
)
from handlers.alerts import check_alerts_async
from handlers.scanner_handler import scan_command_handler
from handlers.stock_scanner import scan_stocks_handler
from handlers.scanner import scan_command
from handlers.momentum_scanner import momentum_scan_handler
from handlers.volume_handler import volume_handler
from handlers.trend_scanner import trend_scan_command_handler
from handlers.hourly_signals import (
    hourly_signal_handler,
    signal_subscribe_handler, 
    signal_unsubscribe_handler,
    signal_list_handler
)
from handlers.signal_background_service import (
    check_hourly_signals_job,
    manual_signal_check_handler,
    signal_stats_handler
)

# -------------------- LOG --------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Flask kaldirildi

# -------------------- TELEGRAM BOT --------------------
async def main():
    """Ana asyncio fonksiyonu"""
    try:
        # Veritabanını başlat
        init_db()

        # Telegram uygulaması - timeout sürelerini artır
        application = Application.builder() \
            .token(TOKEN) \
            .connect_timeout(30.0) \
            .read_timeout(30.0) \
            .write_timeout(30.0) \
            .pool_timeout(30.0) \
            .build()

        # -------------------- HANDLER'LER --------------------
        # BB Fisher tarama handler'ları
        application.add_handler(ultimate_scanner_handler())  # /ultimate komutu
        application.add_handler(ultimate_scan_command())      # /tara komutu
        application.add_handler(bb_fisher_scan_command())      # /bbfisher - Günlük (AI analizli)
        application.add_handler(bb_fisher_4h_command())        # /bbfisher4h - 4 Saatlik
        application.add_handler(bb_fisher_weekly_command())    # /bbfisherw - Haftalık
        
        # Diğer handler'ları ekle
        application.add_handler(momentum_scan_handler())
        application.add_handler(scan_command())
        application.add_handler(scan_command_handler())
        application.add_handler(trend_scan_command_handler())  # /trend komutu
        application.add_handler(start_handler())
        application.add_handler(scan_stocks_handler())
        application.add_handler(help_handler())
        application.add_handler(get_chat_id_handler())
        application.add_handler(silent_handler())
        application.add_handler(mute_handler())
        application.add_handler(ban_handler())
        application.add_handler(unban_handler())
        application.add_handler(unmute_handler())
        application.add_handler(report_handler())
        application.add_handler(stock_info_handler())
        application.add_handler(technical_analysis_handler())
        application.add_handler(fundamental_analysis_handler())
        application.add_handler(compare_handler())
        application.add_handler(crossovers_handler())
        application.add_handler(set_alert_handler())
        application.add_handler(my_alerts_handler())
        application.add_handler(cancel_alert_handler())
        application.add_handler(volume_handler())

        # Saatlik sinyal sistemleri
        application.add_handler(hourly_signal_handler())
        application.add_handler(signal_subscribe_handler())
        application.add_handler(signal_unsubscribe_handler())
        application.add_handler(signal_list_handler())
        application.add_handler(manual_signal_check_handler())
        application.add_handler(signal_stats_handler())

        application.add_handler(button_callback_handler())

    
        # 1 dk aralıkla alert kontrol
        application.job_queue.run_repeating(
            lambda context: asyncio.create_task(
                check_alerts_async(context.job.data['application'])
            ),
            interval=60,
            first=10,
            data={'application': application}
        )

        # Saatlik sinyal kontrolü (her saatin 5. dakikasında)
        application.job_queue.run_repeating(
            check_hourly_signals_job,
            interval=3600,
            first=300,
            data={'application': application}
        )

        # -------------------- BOT BAŞLAT --------------------
        logger.info("Bot başlatılıyor...")
        
        # Botu başlat (standart yöntem)
        await application.initialize()
        await application.start()
        
        # Bot bilgilerini al
        bot_info = await application.bot.get_me()
        logger.info(f"Bot başlatıldı: @{bot_info.username}")
        
        # Polling başlat
        await application.updater.start_polling(
            poll_interval=0.5,
            timeout=20,
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
        logger.info("Bot polling başlatıldı. CTRL+C ile durdurabilirsiniz.")
        logger.info("BB Fisher Komutları: /bbfisher (günlük), /bbfisher4h (4 saatlik), /bbfisherw (haftalık)")
        
        # Sonsuz döngü (bot sürekli çalışacak)
        await asyncio.Event().wait()

    except KeyboardInterrupt:
        logger.info("Bot kapatılıyor...")
    except Exception as e:
        logger.error(f"Bot başlatılırken hata: {e}", exc_info=True)
        raise
    finally:
        # Temizlik
        try:
            if 'application' in locals():
                await application.updater.stop()
                await application.stop()
                await application.shutdown()
                logger.info("Bot başarıyla kapatıldı.")
        except Exception as e:
            logger.error(f"Bot kapatılırken hata: {e}")

# -------------------- ANA BAŞLATMA --------------------
if __name__ == '__main__':
    # Windows için event loop policy
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        # Telegram botunu başlat
        # Python 3.13 için uyumlu başlatma
        try:
            # Yeni asyncio runner kullan
            asyncio.run(main())
        except RuntimeError:
            # Eski Python versiyonları için
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(main())
            
    except KeyboardInterrupt:
        logger.info("Program kapatılıyor...")
    except Exception as e:
        logger.error(f"Program başlatılamadı: {e}", exc_info=True)
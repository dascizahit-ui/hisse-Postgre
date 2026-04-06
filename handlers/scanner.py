import asyncio
import yfinance as yf
import pandas as pd
from telegram import Update, constants
from telegram.ext import ContextTypes, CommandHandler
from config import ADMIN_CHAT_ID, bist_stocks
from stock_analyzer import StockAnalyzer
import logging

# Logger'ı bu dosyada da kullanalım
logger = logging.getLogger(__name__)

# --- MESAJ GRUPLAMA FONKSİYONU ---
async def send_batched_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int, header: str, stock_reports: list):
    """
    Mesajları 4096 karakter limitini aşmayacak şekilde gruplayarak gönderir.
    """
    await context.bot.send_message(
        chat_id=chat_id,
        text=header,
        parse_mode=constants.ParseMode.MARKDOWN
    )
    await asyncio.sleep(1)

    # Her 5 hissede bir mesaj gönder
    batch_size = 5 
    for i in range(0, len(stock_reports), batch_size):
        batch = stock_reports[i:i + batch_size]
        combined_message = "\n\n".join(batch)

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=combined_message,
                parse_mode=constants.ParseMode.MARKDOWN
            )
            await asyncio.sleep(1.5) # API limitleri için bekle
        except Exception as e:
            logger.error(f"Mesaj gönderilirken hata oluştu: {e}")
            # Hata durumunda mesajı bölerek göndermeyi dene
            for single_report in batch:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=single_report, parse_mode=constants.ParseMode.MARKDOWN)
                    await asyncio.sleep(1)
                except Exception as inner_e:
                     logger.error(f"Tekli mesaj gönderimi de başarısız: {inner_e}")


async def scan_stocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    BIST'teki en çok yükselen ve düşen hisseleri tarar, detaylı analiz eder ve gruplar halinde gönderir.
    """
    user_chat_id = update.effective_chat.id
    try:
        await context.bot.send_message(
            chat_id=user_chat_id,
            text="🔍 BIST hisseleri taranıyor... Bu işlem veri yoğunluğuna göre 2-3 dakika sürebilir. Lütfen bekleyin."
        )

        # EMA200 için yeterli veri çektiğimizden emin olalım (18 ay = ~378 işlem günü)
        symbols_with_suffix = [symbol + '.IS' for symbol in bist_stocks]
        data = yf.download(
            tickers=symbols_with_suffix,
            period="18mo", 
            interval="1d",
            group_by='ticker',
            progress=False,
            timeout=60
        )

        if data.empty:
            await context.bot.send_message(user_chat_id, "Hata: Borsa verileri alınamadı. Lütfen daha sonra tekrar deneyin.")
            return

        results = []
        for symbol in bist_stocks:
            symbol_suffix = symbol + '.IS'
            if symbol_suffix not in data.columns.levels[0]: continue

            stock_data = data[symbol_suffix].dropna()

            if len(stock_data) >= 2:
                last_close = stock_data['Close'].iloc[-1]
                prev_close = stock_data['Close'].iloc[-2]

                if pd.notna(last_close) and pd.notna(prev_close) and prev_close > 0:
                    change_pct = ((last_close - prev_close) / prev_close) * 100

                    # BIST sınırı
                    if 0 < change_pct <= 10:
                        results.append({'symbol': symbol, 'change': change_pct, 'price': last_close})


        gainers = sorted([r for r in results if r['change'] > 0], key=lambda x: x['change'], reverse=True)[:25]
        losers = sorted([r for r in results if r['change'] < 0], key=lambda x: x['change'])[:25]

        # --- Yükselen ve Düşenler için Raporları Hazırla ---
        gainer_reports = []
        for stock in gainers:
            try:
                # Periyodu artırarak daha doğru EMA hesaplamaları sağlıyoruz
                df = await StockAnalyzer.get_stock_data(stock['symbol'], period="18mo")
                if df is None or len(df) < 200: continue # Yeterli veri yoksa atla

                indicators = await StockAnalyzer.calculate_technical_indicators(df)
                sentiment = StockAnalyzer.get_market_sentiment(indicators, stock['price'])

                # Fiyatın EMA'lara göre konumunu belirle
                price_vs_ema50 = "Üstünde ✅" if stock['price'] > indicators.get('ema_50', float('inf')) else "Altında ❌"
                price_vs_ema200 = "Üstünde ✅" if stock['price'] > indicators.get('ema_200', float('inf')) else "Altında ❌"

                report = (
                    f"🟢 *{stock['symbol']}* | Fiyat: `{stock['price']:.2f} TRY` | Değişim: *+{stock['change']:.2f}%*\n"
                    f"----------------------------------------\n"
                    f"📈 *Hareketli Ort. (EMA):*\n"
                    f"  EMA5: `{indicators.get('ema_5', 0):.2f}` | EMA9: `{indicators.get('ema_9', 0):.2f}`\n"
                    f"  EMA20: `{indicators.get('ema_20', 0):.2f}` | EMA50: `{indicators.get('ema_50', 0):.2f}`\n"
                    f"  EMA200: `{indicators.get('ema_200', 0):.2f}`\n"
                    f"  Fiyat/EMA50: *{price_vs_ema50}* | Fiyat/EMA200: *{price_vs_ema200}*\n\n"

                    f"Momentum & Hacim:\n"
                    f"  RSI(14): `{indicators.get('rsi', 0):.2f}` | VWAP: `{indicators.get('vwap', 0):.2f}`\n"
                    f"  Stoch(K/D): `{indicators.get('stoch_k', 0):.1f}`/`{indicators.get('stoch_d', 0):.1f}`\n\n"

                    f"Volatility:\n"
                    f"  ATR: `{indicators.get('atr', 0):.2f}`\n"
                    f"  BBands (Alt/Orta/Üst):\n"
                    f"  `{indicators.get('bb_lower', 0):.2f}` / `{indicators.get('bb_middle', 0):.2f}` / `{indicators.get('bb_upper', 0):.2f}`\n\n"

                    f"💡 *Özet Sinyaller:*\n{sentiment}"
                )
                gainer_reports.append(report)
            except Exception as e:
                logger.error(f"Hisse analizi hatası ({stock['symbol']}): {e}")
                continue

        loser_reports = []
        for stock in losers:
            try:
                df = await StockAnalyzer.get_stock_data(stock['symbol'], period="18mo")
                if df is None or len(df) < 200: continue

                indicators = await StockAnalyzer.calculate_technical_indicators(df)
                sentiment = StockAnalyzer.get_market_sentiment(indicators, stock['price'])

                price_vs_ema50 = "Üstünde ✅" if stock['price'] > indicators.get('ema_50', float('inf')) else "Altında ❌"
                price_vs_ema200 = "Üstünde ✅" if stock['price'] > indicators.get('ema_200', float('inf')) else "Altında ❌"

                report = (
                    f"🔴 *{stock['symbol']}* | Fiyat: `{stock['price']:.2f} TRY` | Değişim: *{stock['change']:.2f}%*\n"
                    f"----------------------------------------\n"
                    f"📈 *Hareketli Ort. (EMA):*\n"
                    f"  EMA5: `{indicators.get('ema_5', 0):.2f}` | EMA9: `{indicators.get('ema_9', 0):.2f}`\n"
                    f"  EMA20: `{indicators.get('ema_20', 0):.2f}` | EMA50: `{indicators.get('ema_50', 0):.2f}`\n"
                    f"  EMA200: `{indicators.get('ema_200', 0):.2f}`\n"
                    f"  Fiyat/EMA50: *{price_vs_ema50}* | Fiyat/EMA200: *{price_vs_ema200}*\n\n"

                    f"Momentum & Hacim:\n"
                    f"  RSI(14): `{indicators.get('rsi', 0):.2f}` | VWAP: `{indicators.get('vwap', 0):.2f}`\n"
                    f"  Stoch(K/D): `{indicators.get('stoch_k', 0):.1f}`/`{indicators.get('stoch_d', 0):.1f}`\n\n"

                    f"Volatility:\n"
                    f"  ATR: `{indicators.get('atr', 0):.2f}`\n"
                    f"  BBands (Alt/Orta/Üst):\n"
                    f"  `{indicators.get('bb_lower', 0):.2f}` / `{indicators.get('bb_middle', 0):.2f}` / `{indicators.get('bb_upper', 0):.2f}`\n\n"

                    f"💡 *Özet Sinyaller:*\n{sentiment}"
                )
                loser_reports.append(report)
            except Exception as e:
                logger.error(f"Hisse analizi hatası ({stock['symbol']}): {e}")
                continue

        # --- Hazırlanan Raporları Gruplayarak Gönder ---
        if gainer_reports:
            header = "--- *📈 GÜNÜN EN ÇOK YÜKSELEN HİSSELERİ* ---"
            await send_batched_messages(context, ADMIN_CHAT_ID, header, gainer_reports)
            # Yükselenler için genel yorum
            general_comment_gainers = ("...") # Önceki yanıttaki yorumu buraya ekleyebilirsiniz.
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=general_comment_gainers, parse_mode=constants.ParseMode.MARKDOWN)

        if loser_reports:
            header = "\n\n--- *📉 GÜNÜN EN ÇOK DÜŞEN HİSSELERİ* ---"
            await send_batched_messages(context, ADMIN_CHAT_ID, header, loser_reports)
            # Düşenler için genel yorum
            general_comment_losers = ("...") # Önceki yanıttaki yorumu buraya ekleyebilirsiniz.
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=general_comment_losers, parse_mode=constants.ParseMode.MARKDOWN)

        await context.bot.send_message(user_chat_id, "✅ Tarama tamamlandı. Detaylı ve gruplanmış sonuçlar belirlediğiniz gruba gönderildi.")

    except Exception as e:
        logger.error(f"Genel tarama fonksiyonunda hata: {e}")
        await context.bot.send_message(user_chat_id, f"❌ Tarama sırasında beklenmedik bir hata oluştu. Detaylar için logları kontrol edin: {e}")

def scan_command():
    return CommandHandler("analiz", scan_stocks, block=False) # block=False botun diğer komutları beklemesini engeller
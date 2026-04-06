import asyncio
import logging
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from config import api_semaphore, executor
import numpy as np

logger = logging.getLogger(__name__)

class VolumeAnalyzer:
    """Hacim analizi sınıfı"""

    @staticmethod
    def format_volume(volume):
        """Hacmi okunabilir formatta formatla"""
        if volume >= 1_000_000_000:
            return f"{volume/1_000_000_000:.2f}B"
        elif volume >= 1_000_000:
            return f"{volume/1_000_000:.2f}M"
        elif volume >= 1_000:
            return f"{volume/1_000:.2f}K"
        else:
            return f"{volume:.0f}"

    @staticmethod
    def calculate_volume_metrics(df):
        """Hacim metriklerini hesapla"""
        try:
            metrics = {}

            # Son günün hacmi
            current_volume = df['Volume'].iloc[-1]
            metrics['current_volume'] = current_volume

            # Ortalama hacim (son 20 gün)
            avg_volume_20 = df['Volume'].tail(20).mean()
            metrics['avg_volume_20'] = avg_volume_20

            # Ortalama hacim (son 50 gün)
            avg_volume_50 = df['Volume'].tail(50).mean()
            metrics['avg_volume_50'] = avg_volume_50

            # Hacim oranları
            if avg_volume_20 > 0:
                metrics['volume_ratio_20'] = current_volume / avg_volume_20
            else:
                metrics['volume_ratio_20'] = 0

            if avg_volume_50 > 0:
                metrics['volume_ratio_50'] = current_volume / avg_volume_50
            else:
                metrics['volume_ratio_50'] = 0

            # En yüksek ve en düşük hacim (son 30 gün)
            last_30_days = df.tail(30)
            metrics['max_volume_30'] = last_30_days['Volume'].max()
            metrics['min_volume_30'] = last_30_days['Volume'].min()

            # Hacim volatilitesi (standart sapma)
            metrics['volume_std'] = df['Volume'].tail(20).std()

            # Hacim trendi (son 5 günün ortalaması vs önceki 5 günün ortalaması)
            if len(df) >= 10:
                recent_5_avg = df['Volume'].tail(5).mean()
                previous_5_avg = df['Volume'].tail(10).head(5).mean()
                if previous_5_avg > 0:
                    metrics['volume_trend'] = ((recent_5_avg - previous_5_avg) / previous_5_avg) * 100
                else:
                    metrics['volume_trend'] = 0
            else:
                metrics['volume_trend'] = 0

            return metrics
        except Exception as e:
            logger.error(f"Hacim metrikleri hesaplama hatası: {e}")
            return {}

    @staticmethod
    def get_volume_analysis(metrics, current_price, df):
        """Hacim analizini yorumla"""
        try:
            analysis = []

            # Hacim seviyesi analizi
            ratio_20 = metrics.get('volume_ratio_20', 0)
            if ratio_20 > 2:
                analysis.append("🔥 Çok Yüksek Hacim (2x üstü)")
            elif ratio_20 > 1.5:
                analysis.append("📈 Yüksek Hacim (1.5x üstü)")
            elif ratio_20 > 0.8:
                analysis.append("➡️ Normal Hacim")
            else:
                analysis.append("📉 Düşük Hacim")

            # Hacim trendi
            trend = metrics.get('volume_trend', 0)
            if trend > 20:
                analysis.append("🟢 Hacim Artış Trendi Güçlü")
            elif trend > 0:
                analysis.append("🟡 Hacim Artış Trendi")
            elif trend < -20:
                analysis.append("🔴 Hacim Azalış Trendi Güçlü")
            elif trend < 0:
                analysis.append("🟠 Hacim Azalış Trendi")
            else:
                analysis.append("➡️ Hacim Trendi Sabit")

            # Fiyat-Hacim İlişkisi
            try:
                price_change = ((df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2]) * 100
                if price_change > 2 and ratio_20 > 1.5:
                    analysis.append("🚀 Güçlü Al Baskısı (Yüksek Hacim + Fiyat Artışı)")
                elif price_change < -2 and ratio_20 > 1.5:
                    analysis.append("⚠️ Güçlü Sat Baskısı (Yüksek Hacim + Fiyat Düşüşü)")
                elif price_change > 0 and ratio_20 < 0.5:
                    analysis.append("🤔 Zayıf Al Sinyali (Düşük Hacim)")
                elif price_change < 0 and ratio_20 < 0.5:
                    analysis.append("💭 Zayıf Sat Sinyali (Düşük Hacim)")
            except:
                pass

            return "\n".join(analysis)
        except Exception as e:
            logger.error(f"Hacim analizi yorumlama hatası: {e}")
            return "❌ Analiz yapılamadı"

async def get_stock_volume_data(symbol: str, period: str = "1mo", interval: str = "1d"):
    """Hisse senedi hacim verilerini al"""
    async with api_semaphore:
        loop = asyncio.get_event_loop()
        try:
            if not symbol.endswith('.IS'):
                symbol += '.IS'
            df = await loop.run_in_executor(executor, lambda: yf.Ticker(symbol).history(period=period, interval=interval))
            if df.empty:
                return None, None

            # Son fiyat bilgisi
            current_price = df['Close'].iloc[-1]
            return df, current_price
        except Exception as e:
            logger.error(f"Hacim verisi alınamadı {symbol}: {e}")
            return None, None

async def volume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hacim analizi komutu"""
    try:
        if not context.args:
            await update.message.reply_text(
                "❓ Kullanım:\n"
                "/hacim HISSE_KODU [PERIOD] [INTERVAL]\n\n"
                "Örnekler:\n"
                "• /hacim SUNTK - Son 1 aylık günlük hacim\n"
                "• /hacim THYAO 3mo 1d - Son 3 aylık günlük hacim\n"
                "• /hacim AKBNK 1mo 1h - Son 1 aylık saatlik hacim\n\n"
                "Period seçenekleri: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y\n"
                "Interval seçenekleri: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo"
            )
            return

        symbol = context.args[0].upper()
        period = context.args[1] if len(context.args) > 1 else "1mo"
        interval = context.args[2] if len(context.args) > 2 else "1d"

        # Geçerli period ve interval kontrolü
        valid_periods = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y']
        valid_intervals = ['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo']

        if period not in valid_periods:
            await update.message.reply_text(f"❌ Geçersiz period: {period}\nGeçerli seçenekler: {', '.join(valid_periods)}")
            return

        if interval not in valid_intervals:
            await update.message.reply_text(f"❌ Geçersiz interval: {interval}\nGeçerli seçenekler: {', '.join(valid_intervals)}")
            return

        await update.message.reply_text(f"⏳ {symbol} için hacim analizi yapılıyor...")

        # Veri al
        df, current_price = await get_stock_volume_data(symbol, period, interval)

        if df is None:
            await update.message.reply_text(f"❌ {symbol} için veri bulunamadı.")
            return

        if df['Volume'].sum() == 0:
            await update.message.reply_text(f"❌ {symbol} için hacim verisi bulunamadı.")
            return

        # Hacim metriklerini hesapla
        analyzer = VolumeAnalyzer()
        metrics = analyzer.calculate_volume_metrics(df)

        if not metrics:
            await update.message.reply_text(f"❌ {symbol} için hacim analizi yapılamadı.")
            return

        # Analiz yap
        analysis = analyzer.get_volume_analysis(metrics, current_price, df)

        # Mesajı oluştur
        message = f"📊 **{symbol} - Hacim Analizi**\n"
        message += f"Period: {period} | Interval: {interval}\n"
        message += f"Güncel Fiyat: {current_price:.2f} ₺\n\n"

        message += "📈 **Hacim Verileri:**\n"
        message += f"• Son Hacim: {analyzer.format_volume(metrics['current_volume'])}\n"
        message += f"• 20 Gün Ort: {analyzer.format_volume(metrics['avg_volume_20'])}\n"
        message += f"• 50 Gün Ort: {analyzer.format_volume(metrics['avg_volume_50'])}\n\n"

        message += "📊 **Hacim Oranları:**\n"
        message += f"• 20 Gün Oranı: {metrics['volume_ratio_20']:.2f}x\n"
        message += f"• 50 Gün Oranı: {metrics['volume_ratio_50']:.2f}x\n\n"

        message += "📈 **Son 30 Gün:**\n"
        message += f"• En Yüksek: {analyzer.format_volume(metrics['max_volume_30'])}\n"
        message += f"• En Düşük: {analyzer.format_volume(metrics['min_volume_30'])}\n\n"

        message += f"📊 **Hacim Trendi:** %{metrics['volume_trend']:.1f}\n\n"

        message += "🎯 **Analiz:**\n"
        message += analysis

        # Son 10 günün hacim verilerini ekle
        message += "\n\n📅 **Son 10 Gün Hacim:**\n"
        last_10_days = df.tail(10)
        for i, (date, row) in enumerate(last_10_days.iterrows()):
            date_str = date.strftime('%d/%m')
            volume_formatted = analyzer.format_volume(row['Volume'])
            price = row['Close']
            price_change = ((row['Close'] - row['Open']) / row['Open']) * 100
            change_emoji = "🟢" if price_change > 0 else "🔴" if price_change < 0 else "➡️"
            message += f"{date_str}: {volume_formatted} | {price:.2f}₺ {change_emoji}\n"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Hacim komutu hatası: {e}")
        await update.message.reply_text("❌ Hacim analizi sırasında bir hata oluştu.")

def volume_handler():
    """Hacim analizi handler'ını döndür"""
    return CommandHandler('hacim', volume_command)
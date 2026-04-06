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
import g4f
import os

# Windows için async ayarı
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logger = logging.getLogger(__name__)

# Telegram mesaj limiti
TELEGRAM_MSG_LIMIT = 4000  # 4096'dan biraz az tutuyoruz güvenlik için


class MessageSplitter:
    """Telegram mesajlarını bölen yardımcı sınıf"""
    
    @staticmethod
    def split_message(text: str, limit: int = TELEGRAM_MSG_LIMIT) -> List[str]:
        """Uzun mesajı parçalara böl"""
        if len(text) <= limit:
            return [text]
        
        messages = []
        current_msg = ""
        
        # Önce çift yeni satıra göre böl (paragraflar)
        paragraphs = text.split('\n\n')
        
        for para in paragraphs:
            # Paragraf tek başına limite sığmıyorsa, satır satır böl
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
                # Paragraf sığıyor mu kontrol et
                if len(current_msg) + len(para) + 2 > limit:
                    if current_msg:
                        messages.append(current_msg.strip())
                    current_msg = para + '\n\n'
                else:
                    current_msg += para + '\n\n'
        
        # Son kalan mesajı ekle
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
                # Parçalar arası kısa bekle (rate limit için)
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


class AIVolumeAnalyzer:
    """AI destekli hacim ve BB analizi - GELİŞTİRİLMİŞ VERSİYON"""
    
    @staticmethod
    async def get_volume_data(symbol: str):
        """1 aylık hacim verisi al"""
        try:
            async with api_semaphore:
                loop = asyncio.get_event_loop()
                
                if not symbol.endswith('.IS'):
                    symbol_with_ext = symbol + '.IS'
                else:
                    symbol_with_ext = symbol
                
                df = await loop.run_in_executor(
                    executor,
                    lambda: yf.Ticker(symbol_with_ext).history(period="1mo", interval="1d")
                )
                
                if df.empty or len(df) < 10:
                    return None
                
                return df
        except Exception as e:
            logger.error(f"Hacim verisi alınamadı {symbol}: {e}")
            return None
    
    @staticmethod
    def calculate_volume_metrics(df):
        """Hacim metriklerini hesapla"""
        try:
            current_volume = df['Volume'].iloc[-1]
            avg_volume_20 = df['Volume'].tail(20).mean()
            avg_volume_5 = df['Volume'].tail(5).mean()
            volume_ratio = current_volume / avg_volume_20 if avg_volume_20 > 0 else 0
            
            # Son 5 günün hacim ortalaması
            recent_5_avg = df['Volume'].tail(5).mean()
            previous_5_avg = df['Volume'].tail(10).head(5).mean() if len(df) >= 10 else avg_volume_20
            volume_trend = ((recent_5_avg - previous_5_avg) / previous_5_avg) * 100 if previous_5_avg > 0 else 0
            
            # Hacim momentumu (son 3 gün artan mı?)
            vol_momentum = "ARTAN" if df['Volume'].iloc[-1] > df['Volume'].iloc[-2] > df['Volume'].iloc[-3] else "AZALAN" if df['Volume'].iloc[-1] < df['Volume'].iloc[-2] < df['Volume'].iloc[-3] else "DALGALI"
            
            # Fiyat-Hacim uyumu
            price_up = df['Close'].iloc[-1] > df['Close'].iloc[-2]
            vol_up = df['Volume'].iloc[-1] > df['Volume'].iloc[-2]
            pv_harmony = "UYUMLU" if (price_up and vol_up) or (not price_up and not vol_up) else "UYUMSUZ"
            
            return {
                'current_volume': current_volume,
                'avg_volume_20': avg_volume_20,
                'avg_volume_5': avg_volume_5,
                'volume_ratio': volume_ratio,
                'volume_trend': volume_trend,
                'vol_momentum': vol_momentum,
                'pv_harmony': pv_harmony
            }
        except Exception as e:
            logger.error(f"Hacim metrikleri hesaplama hatası: {e}")
            return None
    
    @staticmethod
    def calculate_advanced_metrics(df, stock_data):
        """Gelişmiş teknik metrikler hesapla"""
        try:
            # Son 5 günlük fiyat değişimleri
            price_changes = []
            for i in range(1, min(6, len(df))):
                change = ((df['Close'].iloc[-i] - df['Close'].iloc[-i-1]) / df['Close'].iloc[-i-1]) * 100
                price_changes.append(change)
            
            # Volatilite (son 20 gün)
            volatility = df['Close'].tail(20).std() / df['Close'].tail(20).mean() * 100
            
            # Destek/Direnç seviyeleri (basit)
            recent_low = df['Low'].tail(20).min()
            recent_high = df['High'].tail(20).max()
            
            # BB pozisyonu (0-100 arası, 0=alt band, 100=üst band)
            bb_position = ((df['Close'].iloc[-1] - stock_data['bb_lower']) / 
                          (stock_data['bb_upper'] - stock_data['bb_lower'])) * 100
            
            # Trend gücü (EMA'ların sıralaması)
            ema_trend = "GÜÇLÜ YUKARI" if stock_data['ema_9'] > stock_data['ema_20'] > stock_data['ema_50'] else \
                       "GÜÇLÜ AŞAĞI" if stock_data['ema_9'] < stock_data['ema_20'] < stock_data['ema_50'] else \
                       "KARARSIZ"
            
            return {
                'price_changes': price_changes,
                'volatility': volatility,
                'recent_low': recent_low,
                'recent_high': recent_high,
                'bb_position': bb_position,
                'ema_trend': ema_trend
            }
        except Exception as e:
            logger.error(f"Gelişmiş metrik hesaplama hatası: {e}")
            return None
    
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
    def quick_analysis(symbol: str, stock_data: Dict, volume_metrics: Dict, advanced_metrics: Dict) -> Dict:
        """Hızlı analiz skoru hesapla (AI'sız)"""
        score = 0
        signals = []
        warnings = []
        
        # 1. Hacim analizi (max 30 puan)
        if volume_metrics['volume_ratio'] >= 2:
            score += 30
            signals.append("🔥 Hacim patlaması (2x+)")
        elif volume_metrics['volume_ratio'] >= 1.5:
            score += 20
            signals.append("📈 Hacim artışı (1.5x+)")
        elif volume_metrics['volume_ratio'] >= 1:
            score += 10
            signals.append("✓ Normal hacim")
        else:
            warnings.append("⚠️ Düşük hacim")
        
        # 2. Fiyat-Hacim uyumu (max 15 puan)
        if volume_metrics['pv_harmony'] == "UYUMLU":
            score += 15
            signals.append("✓ Fiyat-Hacim uyumlu")
        else:
            warnings.append("⚠️ Fiyat-Hacim uyumsuz")
        
        # 3. BB pozisyonu (max 20 puan)
        bb_pos = advanced_metrics['bb_position']
        if 20 <= bb_pos <= 50:  # Alt-orta bölge (ideal giriş)
            score += 20
            signals.append("🎯 BB ideal giriş bölgesi")
        elif bb_pos < 20:
            score += 10
            signals.append("⚡ BB aşırı satım")
        elif bb_pos > 80:
            warnings.append("⚠️ BB aşırı alım")
        else:
            score += 5
        
        # 4. Trend (max 20 puan)
        if advanced_metrics['ema_trend'] == "GÜÇLÜ YUKARI":
            score += 20
            signals.append("📈 Güçlü yükseliş trendi")
        elif advanced_metrics['ema_trend'] == "GÜÇLÜ AŞAĞI":
            warnings.append("⚠️ Düşüş trendi")
        else:
            score += 10
        
        # 5. RSI (max 15 puan)
        if 30 < stock_data['rsi'] < 50:
            score += 15
            signals.append("✓ RSI ideal bölge")
        elif 50 <= stock_data['rsi'] < 70:
            score += 10
        elif stock_data['rsi'] >= 70:
            warnings.append("⚠️ RSI aşırı alım")
        elif stock_data['rsi'] <= 30:
            score += 5
            signals.append("⚡ RSI aşırı satım")
        
        # Tavsiye belirle
        if score >= 80:
            recommendation = "🟢 GÜÇLÜ AL"
        elif score >= 60:
            recommendation = "🟡 AL (Dikkatli)"
        elif score >= 40:
            recommendation = "🟠 BEKLE"
        else:
            recommendation = "🔴 KAÇIN"
        
        return {
            'score': score,
            'recommendation': recommendation,
            'signals': signals,
            'warnings': warnings
        }
    
    @staticmethod
    async def ai_analyze_stock(symbol: str, stock_data: Dict, volume_metrics: Dict, 
                               advanced_metrics: Dict, quick_result: Dict, df: pd.DataFrame) -> str:
        """AI ile hisse analizi yap - GELİŞTİRİLMİŞ"""
        try:
            # BB bant genişliği hesapla
            bb_width = ((stock_data['bb_upper'] - stock_data['bb_lower']) / stock_data['bb_middle']) * 100
            
            # Fiyat değişimi
            price_change = ((df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2]) * 100 if len(df) > 1 else 0
            
            # AI için geliştirilmiş prompt
            prompt = f"""
Sen bir profesyonel teknik analiz uzmanısın. Aşağıdaki verileri analiz et ve KISA, NET, AKSİYON ODAKLI cevap ver.

═══════════════════════════════════════
📊 {symbol} - TEKNİK ANALİZ VERİLERİ
═══════════════════════════════════════

💰 FİYAT BİLGİLERİ:
• Güncel: {stock_data['price']:.2f} ₺
• Son 1 gün: %{price_change:+.2f}
• 20 Günlük En Düşük: {advanced_metrics['recent_low']:.2f} ₺
• 20 Günlük En Yüksek: {advanced_metrics['recent_high']:.2f} ₺
• Volatilite: %{advanced_metrics['volatility']:.1f}

📏 BOLLINGER BANDS:
• Alt: {stock_data['bb_lower']:.2f} ₺
• Orta: {stock_data['bb_middle']:.2f} ₺
• Üst: {stock_data['bb_upper']:.2f} ₺
• Bant Genişliği: %{bb_width:.2f}
• BB Pozisyonu: %{advanced_metrics['bb_position']:.0f} (0=Alt, 100=Üst)

📊 HACİM ANALİZİ:
• Son Hacim: {AIVolumeAnalyzer.format_volume(volume_metrics['current_volume'])}
• 20 Gün Ort: {AIVolumeAnalyzer.format_volume(volume_metrics['avg_volume_20'])}
• Hacim Oranı: {volume_metrics['volume_ratio']:.2f}x
• Hacim Trendi: %{volume_metrics['volume_trend']:+.1f}
• Hacim Momentumu: {volume_metrics['vol_momentum']}
• Fiyat-Hacim Uyumu: {volume_metrics['pv_harmony']}

📈 İNDİKATÖRLER:
• RSI: {stock_data['rsi']:.1f}
• Fisher: {stock_data['fisher']:.2f}
• EMA Trend: {advanced_metrics['ema_trend']}
• MACD: {'Pozitif ✓' if stock_data['macd_ok'] else 'Negatif ✗'}

🎯 ÖN ANALİZ SKORU: {quick_result['score']}/100 → {quick_result['recommendation']}

═══════════════════════════════════════

GÖREV: Aşağıdaki 4 başlığa göre analiz yap. Her başlık MAX 2 cümle olsun.

1️⃣ HACİM DEĞERLENDİRMESİ: Hacim normal mi? Prim yapıyor mu? Kurumsal alım işareti var mı?

2️⃣ TEKNİK GÖRÜNÜM: BB ve trend ne söylüyor? Giriş zamanlaması uygun mu?

3️⃣ RİSK ANALİZİ: Ana riskler neler? Stop-loss nerede olmalı?

4️⃣ TAVSİYE: AL/BEKLE/SAT? Neden? Hedef fiyat tahmini?

TOPLAM MAX 100 KELİME. Direkt, net, profesyonel ol.
"""
            
            # AI'ya sor
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                executor,
                lambda: g4f.ChatCompletion.create(
                    model=g4f.models.gpt_4,
                    messages=[{"role": "user", "content": prompt}],
                )
            )
            
            return response
            
        except Exception as e:
            logger.error(f"AI analiz hatası {symbol}: {e}")
            return f"❌ AI analizi yapılamadı: {str(e)}"
    
    @staticmethod
    async def analyze_single_stock(r: Dict) -> str:
        """Tek bir hisse için tam analiz"""
        symbol = r['symbol']
        
        # Hacim verisi al
        df = await AIVolumeAnalyzer.get_volume_data(symbol)
        if df is None:
            return f"\n<b>❌ {symbol}</b>: Hacim verisi alınamadı\n"
        
        # Hacim metriklerini hesapla
        volume_metrics = AIVolumeAnalyzer.calculate_volume_metrics(df)
        if volume_metrics is None:
            return f"\n<b>❌ {symbol}</b>: Metrik hesaplanamadı\n"
        
        # Gelişmiş metrikler
        advanced_metrics = AIVolumeAnalyzer.calculate_advanced_metrics(df, r)
        if advanced_metrics is None:
            advanced_metrics = {
                'price_changes': [],
                'volatility': 0,
                'recent_low': 0,
                'recent_high': 0,
                'bb_position': 50,
                'ema_trend': 'KARARSIZ'
            }
        
        # Hızlı analiz (AI'sız skor)
        quick_result = AIVolumeAnalyzer.quick_analysis(symbol, r, volume_metrics, advanced_metrics)
        
        # Sonucu formatla
        analysis_text = f"\n{'═'*40}\n"
        analysis_text += f"<b>📊 {symbol}</b>\n"
        analysis_text += f"{'═'*40}\n\n"
        
        # Özet bilgiler
        analysis_text += f"💰 <b>Fiyat:</b> {r['price']:.2f} ₺\n"
        analysis_text += f"📊 <b>Hacim:</b> {AIVolumeAnalyzer.format_volume(volume_metrics['current_volume'])} ({volume_metrics['volume_ratio']:.1f}x)\n"
        analysis_text += f"📏 <b>BB Poz:</b> %{advanced_metrics['bb_position']:.0f} | <b>RSI:</b> {r['rsi']:.0f}\n"
        analysis_text += f"📈 <b>Trend:</b> {advanced_metrics['ema_trend']}\n\n"
        
        # Hızlı skor
        analysis_text += f"🎯 <b>SKOR:</b> {quick_result['score']}/100\n"
        analysis_text += f"📌 <b>TAVSİYE:</b> {quick_result['recommendation']}\n\n"
        
        # Sinyaller ve uyarılar
        if quick_result['signals']:
            analysis_text += "<b>✅ Pozitif:</b>\n"
            for sig in quick_result['signals'][:3]:
                analysis_text += f"  • {sig}\n"
        
        if quick_result['warnings']:
            analysis_text += "<b>⚠️ Dikkat:</b>\n"
            for warn in quick_result['warnings'][:2]:
                analysis_text += f"  • {warn}\n"
        
        # AI Analizi
        analysis_text += "\n<b>🤖 AI Yorumu:</b>\n"
        ai_response = await AIVolumeAnalyzer.ai_analyze_stock(
            symbol, r, volume_metrics, advanced_metrics, quick_result, df
        )
        analysis_text += f"{ai_response}\n"
        
        return analysis_text
    
    @staticmethod
    async def analyze_all_signals(results: List[Dict], update: Update) -> None:
        """Tüm sinyaller için AI analizi yap ve parça parça gönder"""
        
        # Başlık mesajı
        header = "🤖 <b>YAPAY ZEKA ANALİZ RAPORU</b>\n"
        header += f"⏰ {datetime.now(TR_TZ).strftime('%d.%m.%Y %H:%M')}\n"
        header += f"🎯 Toplam {len(results)} sinyal analiz edilecek\n"
        header += "═" * 40
        
        await update.message.reply_text(header, parse_mode='HTML')
        
        # Her hisseyi ayrı analiz et ve gönder
        current_batch = ""
        batch_count = 0
        
        for i, r in enumerate(results[:10]):  # Max 10 hisse
            try:
                # Tek hisse analizi
                analysis = await AIVolumeAnalyzer.analyze_single_stock(r)
                
                # Batch'e ekle veya gönder
                if len(current_batch) + len(analysis) > TELEGRAM_MSG_LIMIT:
                    # Mevcut batch'i gönder
                    if current_batch:
                        await update.message.reply_text(current_batch, parse_mode='HTML')
                        batch_count += 1
                        await asyncio.sleep(1)  # Rate limit
                    current_batch = analysis
                else:
                    current_batch += analysis
                
                # Her 3 hissede bir durum güncellemesi
                if (i + 1) % 3 == 0 and i < len(results) - 1:
                    await asyncio.sleep(2)  # Rate limiting
                    
            except Exception as e:
                logger.error(f"Analiz hatası {r['symbol']}: {e}")
                current_batch += f"\n<b>❌ {r['symbol']}</b>: Analiz hatası\n"
        
        # Son batch'i gönder
        if current_batch:
            await update.message.reply_text(current_batch, parse_mode='HTML')
        
        # Kapanış mesajı
        footer = "\n" + "═" * 40 + "\n"
        footer += "<b>📋 ÖZET TAVSİYELER:</b>\n\n"
        footer += "• 80+ Skor: Güçlü alım fırsatı\n"
        footer += "• 60-79 Skor: Dikkatli alım\n"
        footer += "• 40-59 Skor: Bekle, takip et\n"
        footer += "• 40 altı: Riskli, kaçın\n\n"
        footer += "<b>⚠️ YASAL UYARI:</b>\n"
        footer += "Bu analiz yatırım tavsiyesi değildir. "
        footer += "Kararlarınızı kendi araştırmanıza göre verin.\n"
        footer += "═" * 40
        
        await update.message.reply_text(footer, parse_mode='HTML')


class BBFisherScanner:
    """Bollinger Bands + Fisher Transform Scanner"""
    
    @staticmethod
    async def scan_single_stock(symbol: str) -> Optional[Dict]:
        """Tek bir hisseyi tara"""
        try:
            async with api_semaphore:
                loop = asyncio.get_event_loop()
                
                if not symbol.endswith('.IS'):
                    symbol_with_ext = symbol + '.IS'
                else:
                    symbol_with_ext = symbol
                
                # Veri al
                df = await loop.run_in_executor(
                    executor,
                    lambda: yf.Ticker(symbol_with_ext).history(period="6mo", interval="1d")
                )
                
                if df.empty or len(df) < 50:
                    return None
                
                df = df.copy()
                
                # Bollinger Bands (20, 2)
                bb = BollingerBands(df['Close'], window=20, window_dev=2)
                df['bb_upper'] = bb.bollinger_hband()
                df['bb_middle'] = bb.bollinger_mavg()
                df['bb_lower'] = bb.bollinger_lband()
                
                # Fisher Transform (Period 9 - TradingView uyumlu)
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
                
                # === STRATEJI: BB ALT BANDA 2-3 MUM DOKUNUŞU + FISHER KESIŞI ===
                
                # Son 5 mumu kontrol et (2-3 mum = son dönem)
                current = df.iloc[-1]
                prev1 = df.iloc[-2]
                prev2 = df.iloc[-3]
                prev3 = df.iloc[-4]
                prev4 = df.iloc[-5]
                
                # KURAL 1: BB ALT BANDINA DOKUNUŞ (son 3 mum içinde)
                bb_touch = (
                    (prev3['Low'] <= prev3['bb_lower']) or
                    (prev2['Low'] <= prev2['bb_lower']) or
                    (prev1['Low'] <= prev1['bb_lower'])
                )
                
                # KURAL 2: FISHER YUKARIYA YÖNELIM (kesişim şartı kaldırıldı)
                fisher_rising = current['fisher'] > prev1['fisher'] > prev2['fisher']
                fisher_positive = current['fisher'] > 0
                
                fisher_cross = fisher_rising or fisher_positive
                
                # KURAL 3: FIYAT BB ALT BANDININ ÜZERİNDE (çıkmış)
                price_above_bb = current['Close'] > current['bb_lower']
                
                # === ONAYLAMA GOSTERGELERİ ===
                ema_ok = current['Close'] > current['ema_20']  # EMA 20 üstünde
                rsi_ok = 30 < current['rsi'] < 80  # RSI normal
                macd_ok = current['macd'] > current['macd_signal']  # MACD pozitif
                
                # SINYAL: Her iki temel koşul gerekli + onaylama
                long_signal = bb_touch and fisher_cross and price_above_bb
                
                logger.info(f"{symbol}: BB={bb_touch} Fisher={fisher_cross} Price={price_above_bb} RSI={current['rsi']:.1f}")
                
                if long_signal and ema_ok and rsi_ok:
                    logger.info(f"✓ SINYAL: {symbol}")
                    
                    strength = sum([ema_ok, macd_ok, rsi_ok])
                    
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
                        'rsi_ok': rsi_ok
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"Scanner {symbol}: {e}")
            return None
    
    @staticmethod
    async def scan_all_stocks(stocks: List[str]) -> List[Dict]:
        """Tüm hisseleri tara"""
        tasks = [BBFisherScanner.scan_single_stock(stock) for stock in stocks]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]


async def bb_fisher_scan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tarama handler - GELİŞTİRİLMİŞ"""
    try:
        msg = await update.message.reply_text("🔍 BB + Fisher taraması başlıyor...\n⏳ Lütfen bekleyin...")
        
        logger.info(f"Tarama başladı")
        
        # Tara
        results = await BBFisherScanner.scan_all_stocks(bist_stocks)
        results.sort(key=lambda x: x['signal_strength'], reverse=True)
        
        logger.info(f"Tarama tamamlandı: {len(results)} sinyal")
        
        if not results:
            await msg.edit_text("❌ Bu an için sinyal bulunamadı")
            return
        
        # 1. MESAJ: Normal tarama sonuçları (ESKİ FORMAT)
        text = "🎯 <b>BB + FISHER LONG SİNYALLERİ</b>\n"
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
            text += "-" * 55 + "\n"
        
        # Strateji
        text += "\n<b>📋 STRATEJİ:</b>\n\n"
        text += "<b>1️⃣ GİRİŞ SİNYALİ:</b>\n"
        text += "   🔹 BB alt bandına 2-3 mum dokunuşu\n"
        text += "   🔹 Fisher Transform yukarı yönelim veya pozitif bölge\n"
        text += "   🔹 Fiyat BB alt bandının üzerine çıkmış\n\n"
        text += "<b>2️⃣ ONAYLAMA İNDİKATÖRLERİ:</b>\n"
        text += "   🔹 EMA 20 > Fiyat (yükseliş eğilimi)\n"
        text += "   🔹 RSI: 30-80 arasında (normal bölge)\n"
        text += "   🔹 MACD: Signal üstünde (pozitif momentum)\n\n"
        text += "<b>3️⃣ HEDEFLER (Take Profit):</b>\n"
        text += "   🎯 Kısa Vadeli TP: BB orta bandına rahat çıkma\n"
        text += "   🎯 Orta Vadeli TP: BB üst bandına kadar\n"
        text += "   🎯 Daha Ötesi: Tahtacı işlemci istemeyi\n\n"
        text += "<b>4️⃣ ZARARI KES (Stop Loss):</b>\n"
        text += "   ❌ BB alt band altına kapanış = pozisyondan çık\n\n"
        text += "<b>5️⃣ SİNYAL GÜÇLERİ:</b>\n"
        text += "   🟢🟢🟢 = Tüm onaylar sağlanmış (En kuvvetli)\n"
        text += "   🟢🟢⚪ = 2 onay var\n"
        text += "   🟢⚪⚪ = 1 onay var (Risk daha yüksek)\n"
        
        # Mesajı parçala ve gönder
        await msg.delete()
        await MessageSplitter.send_long_message(update, text)
        
        # 2. AI ANALİZİ
        await update.message.reply_text(
            "🤖 AI analizi başlatılıyor...\n"
            f"📊 {min(10, len(results))} hisse analiz edilecek\n"
            "⏳ Bu işlem 1-2 dakika sürebilir..."
        )
        
        try:
            await AIVolumeAnalyzer.analyze_all_signals(results, update)
        except Exception as e:
            logger.error(f"AI analiz hatası: {e}")
            await update.message.reply_text(f"❌ AI analizi sırasında hata: {str(e)}")
        
    except Exception as e:
        logger.error(f"Handler hatası: {e}")
        await update.message.reply_text(f"❌ Hata: {str(e)}")


def bb_fisher_scan_command() -> CommandHandler:
    """Handler döndür"""
    return CommandHandler('bbfisher', bb_fisher_scan_handler)
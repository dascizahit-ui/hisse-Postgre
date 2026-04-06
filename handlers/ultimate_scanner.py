"""
🎯 BIST Ultimate Multi-Layer Scanner v2.0
DİPTEN YAKALAMA odaklı - BB Alt Bant stratejisi
Çok katmanlı filtreleme ile yükseliş potansiyeli yüksek hisseleri bulur.

Komutlar: /ultimate veya /tara
"""

import asyncio
import logging
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Windows için asyncio ayarı
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import yfinance as yf
import pandas as pd
import numpy as np
from ta.trend import MACD, SMAIndicator, EMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator, StochasticOscillator, WilliamsRIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

# g4f import - hata olursa devre dışı
try:
    import g4f
    G4F_AVAILABLE = True
except ImportError:
    G4F_AVAILABLE = False
    logger.warning("g4f yüklenemedi, AI analizi devre dışı")


# ==================== BIST SEMBOLLERİ ====================
BIST_50_STOCKS = [
    "AEFES", "AKBNK", "ALARK", "ARCLK", "ASELS", "ASTOR", "BIMAS",
    "CCOLA", "CIMSA", "DOAS", "DOHOL", "EKGYO", "ENKAI",
    "EREGL", "FROTO", "GUBRF", "GARAN", "HALKB", "HEKTS", "ISCTR",
    "KCHOL", "KONTR", "KOZAL", "KOZAA", "KRDMD", "MGROS",
    "OYAKC", "PGSUS", "PETKM", "SASA", "SISE", "SOKM",
    "TAVHL", "TCELL", "THYAO", "TKFEN", "TOASO", "TSKB", "TTKOM",
    "TUPRS", "ULKER", "VAKBN", "VESTL", "YKBNK"
]


# ==================== KONFİGÜRASYON ====================
class ScannerConfig:
    PERIOD = "6mo"
    INTERVAL = "1d"
    
    # RSI - Aşırı satım bölgesine yakın (dipten yakalama)
    RSI_MIN = 30  # Aşırı satıma yakın
    RSI_MAX = 55  # Henüz aşırı alımda değil
    
    # ADX - Trend gücü
    ADX_MIN = 18  # Biraz daha düşük, erken trend yakalama
    
    # Volume - Dipte hacim artışı önemli
    VOLUME_INCREASE_RATIO = 1.3  # Biraz daha yüksek hacim arıyoruz
    
    # Stochastic - Aşırı satım bölgesi
    STOCH_K_MIN = 10  # Aşırı satım
    STOCH_K_MAX = 40  # Henüz yukarıda değil
    
    # Williams %R - Aşırı satım
    WILLIAMS_R_MIN = -90
    WILLIAMS_R_MAX = -50
    
    MIN_SCORE = 65  # Daha fazla fırsat için biraz düşürdük
    MAX_RESULTS = 15  # Daha fazla sonuç


# ==================== İNDİKATÖR HESAPLAMA ====================
def calculate_all_indicators(df: pd.DataFrame) -> Optional[Dict]:
    """Tüm teknik indikatörleri hesapla"""
    try:
        if len(df) < 50:
            return None
            
        indicators = {}
        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']
        
        # RSI
        rsi_indicator = RSIIndicator(close, window=14)
        rsi_series = rsi_indicator.rsi()
        indicators['rsi'] = float(rsi_series.iloc[-1])
        indicators['rsi_prev'] = float(rsi_series.iloc[-2])
        indicators['rsi_prev_3'] = float(rsi_series.iloc[-3]) if len(rsi_series) > 3 else indicators['rsi_prev']
        indicators['rsi_rising'] = indicators['rsi'] > indicators['rsi_prev']
        indicators['rsi_divergence'] = (indicators['rsi'] > indicators['rsi_prev_3']) and (float(close.iloc[-1]) < float(close.iloc[-3]))
        
        # MACD
        macd_indicator = MACD(close)
        indicators['macd'] = float(macd_indicator.macd().iloc[-1])
        indicators['macd_signal'] = float(macd_indicator.macd_signal().iloc[-1])
        indicators['macd_histogram'] = float(macd_indicator.macd_diff().iloc[-1])
        indicators['macd_histogram_prev'] = float(macd_indicator.macd_diff().iloc[-2])
        indicators['macd_histogram_prev_3'] = float(macd_indicator.macd_diff().iloc[-3]) if len(df) > 3 else indicators['macd_histogram_prev']
        indicators['macd_positive'] = indicators['macd'] > indicators['macd_signal']
        indicators['macd_histogram_rising'] = indicators['macd_histogram'] > indicators['macd_histogram_prev']
        indicators['macd_turning'] = (indicators['macd_histogram'] > indicators['macd_histogram_prev']) and (indicators['macd_histogram_prev'] < indicators['macd_histogram_prev_3'])
        
        # EMA'lar
        indicators['ema_5'] = float(EMAIndicator(close, window=5).ema_indicator().iloc[-1])
        indicators['ema_9'] = float(EMAIndicator(close, window=9).ema_indicator().iloc[-1])
        indicators['ema_20'] = float(EMAIndicator(close, window=20).ema_indicator().iloc[-1])
        indicators['ema_50'] = float(EMAIndicator(close, window=50).ema_indicator().iloc[-1])
        
        if len(df) >= 200:
            indicators['ema_200'] = float(EMAIndicator(close, window=200).ema_indicator().iloc[-1])
        else:
            indicators['ema_200'] = indicators['ema_50']
        
        # Stochastic
        stoch = StochasticOscillator(high, low, close, window=14)
        stoch_k = stoch.stoch()
        stoch_d = stoch.stoch_signal()
        indicators['stoch_k'] = float(stoch_k.iloc[-1])
        indicators['stoch_d'] = float(stoch_d.iloc[-1])
        indicators['stoch_k_prev'] = float(stoch_k.iloc[-2])
        indicators['stoch_bullish'] = indicators['stoch_k'] > indicators['stoch_d']
        indicators['stoch_cross_up'] = (indicators['stoch_k'] > indicators['stoch_d']) and (float(stoch_k.iloc[-2]) <= float(stoch_d.iloc[-2]))
        
        # Volume
        avg_volume_20 = float(volume.rolling(window=20).mean().iloc[-1])
        avg_volume_5 = float(volume.rolling(window=5).mean().iloc[-1])
        indicators['current_volume'] = float(volume.iloc[-1])
        indicators['avg_volume_20'] = avg_volume_20
        indicators['avg_volume_5'] = avg_volume_5
        indicators['volume_ratio'] = indicators['current_volume'] / avg_volume_20 if avg_volume_20 > 0 else 0
        indicators['volume_surge'] = avg_volume_5 > avg_volume_20 * 1.2  # Son 5 gün hacim artışı
        
        # ADX
        adx_indicator = ADXIndicator(high, low, close, window=14)
        indicators['adx'] = float(adx_indicator.adx().iloc[-1])
        indicators['di_plus'] = float(adx_indicator.adx_pos().iloc[-1])
        indicators['di_minus'] = float(adx_indicator.adx_neg().iloc[-1])
        indicators['di_cross_up'] = indicators['di_plus'] > indicators['di_minus']
        
        # Bollinger Bands
        bb = BollingerBands(close, window=20, window_dev=2)
        indicators['bb_upper'] = float(bb.bollinger_hband().iloc[-1])
        indicators['bb_middle'] = float(bb.bollinger_mavg().iloc[-1])
        indicators['bb_lower'] = float(bb.bollinger_lband().iloc[-1])
        indicators['bb_width'] = (indicators['bb_upper'] - indicators['bb_lower']) / indicators['bb_middle'] * 100
        indicators['bb_percent'] = (float(close.iloc[-1]) - indicators['bb_lower']) / (indicators['bb_upper'] - indicators['bb_lower']) * 100 if (indicators['bb_upper'] - indicators['bb_lower']) > 0 else 50
        
        # ATR
        atr = AverageTrueRange(high, low, close, window=14)
        indicators['atr'] = float(atr.average_true_range().iloc[-1])
        indicators['atr_percent'] = (indicators['atr'] / float(close.iloc[-1])) * 100
        
        # VWAP
        typical_price = (high + low + close) / 3
        vwap_num = (typical_price * volume).rolling(20).sum().iloc[-1]
        vwap_den = volume.rolling(20).sum().iloc[-1]
        indicators['vwap'] = float(vwap_num / vwap_den) if vwap_den > 0 else float(close.iloc[-1])
        
        # Williams %R
        williams = WilliamsRIndicator(high, low, close, lbp=14)
        williams_r = williams.williams_r()
        indicators['williams_r'] = float(williams_r.iloc[-1])
        indicators['williams_r_prev'] = float(williams_r.iloc[-2])
        indicators['williams_r_rising'] = indicators['williams_r'] > indicators['williams_r_prev']
        
        # OBV
        obv = OnBalanceVolumeIndicator(close, volume)
        obv_values = obv.on_balance_volume()
        indicators['obv'] = float(obv_values.iloc[-1])
        indicators['obv_sma'] = float(obv_values.rolling(window=20).mean().iloc[-1])
        indicators['obv_rising'] = indicators['obv'] > indicators['obv_sma']
        
        # Higher Lows/Highs - Dipten dönüş sinyali
        lows_5 = low.tail(5).values
        highs_5 = high.tail(5).values
        closes_5 = close.tail(5).values
        indicators['higher_lows'] = all(lows_5[i] <= lows_5[i+1] for i in range(len(lows_5)-1))
        indicators['higher_highs'] = all(highs_5[i] <= highs_5[i+1] for i in range(len(highs_5)-1))
        indicators['higher_closes'] = all(closes_5[i] <= closes_5[i+1] for i in range(len(closes_5)-1))
        
        # Son X günde düşüş - Düzeltme sonrası fırsat
        indicators['drop_5d'] = ((float(close.iloc[-1]) - float(close.iloc[-5])) / float(close.iloc[-5])) * 100 if len(close) >= 5 else 0
        indicators['drop_10d'] = ((float(close.iloc[-1]) - float(close.iloc[-10])) / float(close.iloc[-10])) * 100 if len(close) >= 10 else 0
        indicators['drop_20d'] = ((float(close.iloc[-1]) - float(close.iloc[-20])) / float(close.iloc[-20])) * 100 if len(close) >= 20 else 0
        
        # 52 hafta (yaklaşık 250 gün) düşük/yüksek
        if len(close) >= 250:
            indicators['low_52w'] = float(low.tail(250).min())
            indicators['high_52w'] = float(high.tail(250).max())
            indicators['from_52w_low'] = ((float(close.iloc[-1]) - indicators['low_52w']) / indicators['low_52w']) * 100
            indicators['from_52w_high'] = ((float(close.iloc[-1]) - indicators['high_52w']) / indicators['high_52w']) * 100
        else:
            indicators['low_52w'] = float(low.min())
            indicators['high_52w'] = float(high.max())
            indicators['from_52w_low'] = ((float(close.iloc[-1]) - indicators['low_52w']) / indicators['low_52w']) * 100
            indicators['from_52w_high'] = ((float(close.iloc[-1]) - indicators['high_52w']) / indicators['high_52w']) * 100
        
        # Fiyat verileri
        indicators['current_price'] = float(close.iloc[-1])
        indicators['prev_close'] = float(close.iloc[-2])
        indicators['daily_change'] = ((indicators['current_price'] - indicators['prev_close']) / indicators['prev_close']) * 100
        
        if len(close) >= 5:
            indicators['weekly_change'] = ((indicators['current_price'] - float(close.iloc[-5])) / float(close.iloc[-5])) * 100
        else:
            indicators['weekly_change'] = 0
            
        if len(close) >= 20:
            indicators['monthly_change'] = ((indicators['current_price'] - float(close.iloc[-20])) / float(close.iloc[-20])) * 100
        else:
            indicators['monthly_change'] = 0
        
        # Destek/Direnç
        indicators['resistance'] = float(high.rolling(window=20).max().iloc[-1])
        indicators['support'] = float(low.rolling(window=20).min().iloc[-1])
        
        # EMA Kesişimleri
        ema_5_series = EMAIndicator(close, window=5).ema_indicator()
        ema_9_series = EMAIndicator(close, window=9).ema_indicator()
        ema_20_series = EMAIndicator(close, window=20).ema_indicator()
        
        indicators['ema_5_9_cross'] = (float(ema_5_series.iloc[-2]) < float(ema_9_series.iloc[-2]) and 
                                       float(ema_5_series.iloc[-1]) > float(ema_9_series.iloc[-1]))
        indicators['ema_5_20_cross'] = (float(ema_5_series.iloc[-2]) < float(ema_20_series.iloc[-2]) and 
                                        float(ema_5_series.iloc[-1]) > float(ema_20_series.iloc[-1]))
        indicators['ema_9_20_cross'] = (float(ema_9_series.iloc[-2]) < float(ema_20_series.iloc[-2]) and 
                                        float(ema_9_series.iloc[-1]) > float(ema_20_series.iloc[-1]))
        
        # Fiyat EMA'lara göre pozisyon
        indicators['price_above_ema5'] = indicators['current_price'] > indicators['ema_5']
        indicators['price_above_ema20'] = indicators['current_price'] > indicators['ema_20']
        indicators['price_above_ema50'] = indicators['current_price'] > indicators['ema_50']
        
        return indicators
        
    except Exception as e:
        logger.error(f"İndikatör hesaplama hatası: {e}")
        return None


# ==================== DİPTEN YAKALAMA PUANLAMA ====================
def calculate_score(indicators: Dict, config: ScannerConfig) -> Tuple[int, List[str]]:
    """DİPTEN YAKALAMA odaklı puanlama sistemi"""
    score = 0
    passed_criteria = []
    price = indicators['current_price']
    
    # ==================== BB ALT BANT (MEGA ÖNEMLİ) ====================
    bb_percent = indicators['bb_percent']
    
    # BB Alt Banda Çok Yakın (0-15%) - EN GÜÇLÜ SİNYAL
    if bb_percent <= 15:
        score += 20
        passed_criteria.append(f"🔥🔥 BB DİP ({bb_percent:.0f}%)")
    # BB Alt-Orta Arası (15-40%)
    elif bb_percent <= 40:
        score += 15
        passed_criteria.append(f"🔥 BB Alt-Orta ({bb_percent:.0f}%)")
    # BB Orta (40-60%) - Nötr
    elif bb_percent <= 60:
        score += 5
        passed_criteria.append(f"✅ BB Orta ({bb_percent:.0f}%)")
    # BB Üst tarafı - PUAN YOK, zaten çıkmış
    
    # ==================== RSI AŞIRI SATIM ====================
    rsi = indicators['rsi']
    
    # RSI Aşırı Satım (30 altı) - DİP SİNYALİ
    if rsi < 30:
        score += 15
        passed_criteria.append(f"🔥 RSI Aşırı Satım ({rsi:.0f})")
    # RSI Dipten Dönüyor (30-45)
    elif rsi < 45 and indicators['rsi_rising']:
        score += 12
        passed_criteria.append(f"✅ RSI Dönüş ({rsi:.0f}) ↑")
    # RSI Uygun Aralık (45-55)
    elif 45 <= rsi <= 55:
        score += 8
        passed_criteria.append(f"✅ RSI Nötr ({rsi:.0f})")
    # RSI Yükseliyor
    if indicators['rsi_rising'] and rsi < 60:
        score += 3
    
    # RSI Pozitif Divergence (Fiyat düşerken RSI yükseliyor)
    if indicators.get('rsi_divergence', False):
        score += 8
        passed_criteria.append("🔥 RSI Divergence!")
    
    # ==================== STOCHASTIC AŞIRI SATIM ====================
    stoch_k = indicators['stoch_k']
    
    # Stoch Aşırı Satım (20 altı)
    if stoch_k < 20:
        score += 12
        passed_criteria.append(f"🔥 Stoch Dip ({stoch_k:.0f})")
    # Stoch Dipten Dönüyor
    elif stoch_k < 40 and indicators['stoch_bullish']:
        score += 8
        passed_criteria.append(f"✅ Stoch Dönüş ({stoch_k:.0f})")
    
    # Stochastic Golden Cross
    if indicators.get('stoch_cross_up', False):
        score += 10
        passed_criteria.append("🔥 Stoch Cross ↑")
    
    # ==================== WILLIAMS %R ====================
    williams = indicators['williams_r']
    
    # Williams Aşırı Satım (-80 altı)
    if williams < -80:
        score += 10
        passed_criteria.append(f"🔥 W%R Dip ({williams:.0f})")
    elif williams < -60 and indicators['williams_r_rising']:
        score += 6
        passed_criteria.append(f"✅ W%R Dönüş ({williams:.0f})")
    
    # ==================== MACD ====================
    # MACD Pozitif - Erken trend
    if indicators['macd_positive']:
        score += 8
        passed_criteria.append("✅ MACD Pozitif")
    # MACD Henüz negatif ama dönüyor
    elif indicators['macd_histogram_rising']:
        score += 10
        passed_criteria.append("🔥 MACD Dönüyor")
    
    # MACD Turning Point
    if indicators.get('macd_turning', False):
        score += 8
        passed_criteria.append("🔥 MACD Pivot!")
    
    # ==================== HACİM ====================
    volume_ratio = indicators['volume_ratio']
    
    # Dipte Yüksek Hacim - ÇOK ÖNEMLİ
    if volume_ratio >= 2.0 and bb_percent < 40:
        score += 12
        passed_criteria.append(f"🔥🔥 Dipte Hacim Patlaması ({volume_ratio:.1f}x)")
    elif volume_ratio >= config.VOLUME_INCREASE_RATIO:
        score += 6
        passed_criteria.append(f"✅ Hacim Artışı ({volume_ratio:.1f}x)")
    
    # Volume Surge (Son 5 gün ortalaması yüksek)
    if indicators.get('volume_surge', False):
        score += 5
        passed_criteria.append("✅ Hacim Trendi ↑")
    
    # ==================== OBV ====================
    if indicators['obv_rising']:
        score += 5
        passed_criteria.append("✅ OBV Yükseliyor")
    
    # ==================== ADX & DI ====================
    adx = indicators['adx']
    
    if adx >= config.ADX_MIN:
        score += 5
        passed_criteria.append(f"✅ ADX: {adx:.0f}")
    
    if indicators['di_cross_up']:
        score += 5
        passed_criteria.append("✅ DI+ > DI-")
    
    # ==================== EMA KESİŞİMLERİ ====================
    if indicators.get('ema_5_9_cross', False):
        score += 8
        passed_criteria.append("🔥 EMA 5/9 Cross!")
    
    if indicators.get('ema_5_20_cross', False):
        score += 10
        passed_criteria.append("🔥🔥 EMA 5/20 Cross!")
    
    if indicators.get('ema_9_20_cross', False):
        score += 8
        passed_criteria.append("🔥 EMA 9/20 Cross!")
    
    # ==================== DESTEK SEVİYESİ ====================
    support = indicators['support']
    distance_to_support = ((price - support) / support) * 100
    
    # Desteğe çok yakın (%2 içinde)
    if distance_to_support <= 2:
        score += 10
        passed_criteria.append(f"🔥 Destek Yakın (%{distance_to_support:.1f})")
    elif distance_to_support <= 5:
        score += 5
        passed_criteria.append(f"✅ Destek Bölgesi")
    
    # ==================== 52 HAFTA ANALİZİ ====================
    from_low = indicators.get('from_52w_low', 0)
    from_high = indicators.get('from_52w_high', 0)
    
    # 52 hafta dibine yakın
    if from_low <= 10:
        score += 10
        passed_criteria.append(f"🔥 52H Dibe Yakın (+%{from_low:.0f})")
    elif from_low <= 20:
        score += 5
        passed_criteria.append(f"✅ 52H Alt Bölge")
    
    # ==================== DÜZELTME SONRASI ====================
    drop_10d = indicators.get('drop_10d', 0)
    
    # Son 10 günde %5+ düşüş (düzeltme fırsatı)
    if drop_10d < -5 and indicators['rsi_rising']:
        score += 8
        passed_criteria.append(f"🔥 Düzeltme Fırsatı ({drop_10d:.1f}%)")
    
    # ==================== HIGHER LOWS ====================
    if indicators['higher_lows']:
        score += 5
        passed_criteria.append("✅ Yükselen Dipler")
    
    if indicators['higher_closes']:
        score += 3
        passed_criteria.append("✅ Yükselen Kapanışlar")
    
    # ==================== VWAP ====================
    if price < indicators['vwap']:
        # Fiyat VWAP altında - potansiyel fırsat
        score += 3
        passed_criteria.append("✅ VWAP Altı (Fırsat)")
    elif price > indicators['vwap'] and bb_percent < 50:
        score += 5
        passed_criteria.append("✅ VWAP Kırılımı")
    
    return min(score, 100), passed_criteria


# ==================== HEDEF HESAPLAMA ====================
def calculate_targets(indicators: Dict, score: int) -> Dict:
    """Stop-loss ve take-profit hesapla - Dipten yakalama için optimize"""
    price = indicators['current_price']
    atr = indicators.get('atr', price * 0.02)
    support = indicators.get('support', price * 0.95)
    resistance = indicators.get('resistance', price * 1.05)
    bb_upper = indicators.get('bb_upper', price * 1.05)
    bb_middle = indicators.get('bb_middle', price * 1.02)
    
    # Stop-loss (Daha dar, dipte daha az risk)
    atr_stop = price - (atr * 1.2)
    support_stop = support * 0.98
    stop_loss = max(atr_stop, support_stop)
    stop_loss_pct = ((price - stop_loss) / price) * 100
    
    # Take-profit hedefleri (BB ve dirence göre)
    # TP1: BB orta veya %3-5 (hangisi önce gelirse)
    tp1_price = min(bb_middle, price * 1.05)
    tp1_pct = ((tp1_price - price) / price) * 100
    
    # TP2: BB üst veya direnç (hangisi önce gelirse)
    tp2_price = min(bb_upper, resistance)
    tp2_pct = ((tp2_price - price) / price) * 100
    
    # TP3: Direnç üstü
    tp3_price = resistance * 1.02
    tp3_pct = ((tp3_price - price) / price) * 100
    
    # Bekleme süresi (dipten alım için daha uzun tutulabilir)
    if score >= 85:
        hold_days = "3-7 gün (Kısa Swing)"
    elif score >= 75:
        hold_days = "5-12 gün (Swing)"
    else:
        hold_days = "7-20 gün (Orta Vade)"
    
    return {
        'stop_loss': stop_loss,
        'stop_loss_pct': stop_loss_pct,
        'take_profit_1': tp1_price,
        'take_profit_1_pct': tp1_pct,
        'take_profit_2': tp2_price,
        'take_profit_2_pct': tp2_pct,
        'take_profit_3': tp3_price,
        'take_profit_3_pct': tp3_pct,
        'hold_days': hold_days,
        'risk_reward': tp1_pct / stop_loss_pct if stop_loss_pct > 0 else 0,
        'bb_middle': bb_middle,
        'bb_upper': bb_upper
    }


# ==================== BASİT ANALİZ ====================
def generate_basic_analysis(symbol: str, indicators: Dict, score: int, targets: Dict) -> str:
    """AI olmadan basit analiz üret"""
    
    bb_percent = indicators.get('bb_percent', 50)
    rsi = indicators.get('rsi', 50)
    
    # Durum değerlendirmesi
    if bb_percent <= 20 and rsi < 35:
        overall = "🟢 DİPTEN DÖNÜŞ SİNYALİ"
        rec = "GÜÇLÜ AL"
        detail = "Fiyat BB alt bandında ve RSI aşırı satımda"
    elif bb_percent <= 40 and rsi < 45:
        overall = "🟢 DİP BÖLGESİ"
        rec = "AL"
        detail = "Teknik göstergeler dip bölgesini işaret ediyor"
    elif score >= 80:
        overall = "🟢 GÜÇLÜ FIRSAT"
        rec = "AL"
        detail = "Çoklu göstergeler yukarı yönü destekliyor"
    elif score >= 70:
        overall = "🟡 ORTA FIRSAT"
        rec = "DİKKATLİ AL"
        detail = "İyi sinyaller var, stop-loss kullan"
    else:
        overall = "⚪ TAKİPTE TUT"
        rec = "BEKLE"
        detail = "Daha güçlü sinyal için bekle"
    
    analysis = f"""🎯 DEĞERLENDİRME: {overall}

📍 DURUM: {detail}

📈 GÜÇLÜ YÖNLER:
• BB %{bb_percent:.0f} (Alt bölge)
• RSI {rsi:.0f} (Toparlanma potansiyeli)
• Teknik dönüş sinyalleri

⚠️ RİSKLER:
• Genel piyasa riski
• Stop-loss mutlaka kullanın

🎯 HEDEFLER:
• TP1: {targets['take_profit_1']:.2f} TL (+%{targets['take_profit_1_pct']:.1f})
• TP2: {targets['take_profit_2']:.2f} TL (+%{targets['take_profit_2_pct']:.1f})
• Stop: {targets['stop_loss']:.2f} TL (-%{targets['stop_loss_pct']:.1f})

⏱️ BEKLEME: {targets['hold_days']}
📊 TAVSİYE: {rec}"""
    
    return analysis


# ==================== AI ANALİZ ====================
async def ai_analyze_stock(symbol: str, indicators: Dict, score: int, passed_criteria: List[str], targets: Dict) -> str:
    """AI ile hisse analizi yap"""
    
    if not G4F_AVAILABLE:
        return generate_basic_analysis(symbol, indicators, score, targets)
    
    try:
        bb_percent = indicators.get('bb_percent', 50)
        
        prompt = f"""Sen uzman bir borsa analisti olarak {symbol} hissesini DİPTEN YAKALAMA stratejisi açısından analiz et.

VERİLER:
- Fiyat: {indicators['current_price']:.2f} TL
- Puan: {score}/100
- BB Pozisyon: %{bb_percent:.0f} (0=Alt Bant, 100=Üst Bant)
- RSI: {indicators['rsi']:.1f}
- Stoch K: {indicators['stoch_k']:.1f}
- MACD: {'Pozitif' if indicators['macd_positive'] else 'Negatif'}, {'Yükseliyor' if indicators['macd_histogram_rising'] else 'Düşüyor'}
- ADX: {indicators['adx']:.1f}
- Hacim: {indicators['volume_ratio']:.1f}x ortalama
- Destek: {indicators['support']:.2f} TL
- Direnç: {indicators['resistance']:.2f} TL
- 52H Dipten: +%{indicators.get('from_52w_low', 0):.1f}

HEDEFLER:
- Stop-Loss: {targets['stop_loss']:.2f} TL (-%{targets['stop_loss_pct']:.1f})
- TP1 (BB Orta): {targets['take_profit_1']:.2f} TL (+%{targets['take_profit_1_pct']:.1f})
- TP2 (BB Üst/Direnç): {targets['take_profit_2']:.2f} TL (+%{targets['take_profit_2_pct']:.1f})
- R/R Oranı: {targets['risk_reward']:.2f}

GEÇEN KRİTERLER:
{chr(10).join(passed_criteria[:8])}

ŞU FORMATTA KISA CEVAP VER (max 150 kelime):
🎯 DEĞERLENDİRME: (DİP sinyali gücü)
📈 GÜÇLÜ YÖNLER: (2-3 madde, dipten yakalama açısından)
⚠️ RİSKLER: (1-2 madde)
📊 TAVSİYE: (GÜÇLÜ AL / AL / DİKKATLİ AL / BEKLE)
💡 STRATEJİ: (Kısa öneri)

Türkçe yaz, teknik terimler kullan."""

        response = g4f.ChatCompletion.create(
            model=g4f.models.gpt_4,
            messages=[{"role": "user", "content": prompt}],
        )
        
        if response:
            return response
        else:
            return generate_basic_analysis(symbol, indicators, score, targets)
        
    except Exception as e:
        logger.error(f"AI analiz hatası {symbol}: {e}")
        return generate_basic_analysis(symbol, indicators, score, targets)


# ==================== VERİ ÇEKME ====================
async def get_stock_data(symbol: str, period: str = "6mo") -> Optional[pd.DataFrame]:
    """Hisse verisini al"""
    try:
        ticker_symbol = f"{symbol}.IS" if not symbol.endswith('.IS') else symbol
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period=period, interval="1d")
        
        if df.empty or len(df) < 50:
            return None
        return df
    except Exception as e:
        logger.debug(f"Veri alınamadı {symbol}: {e}")
        return None


# ==================== ANA TARAMA ====================
async def scan_bist_stocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """BIST hisselerini DİPTEN YAKALAMA stratejisi ile tara"""
    
    chat_id = update.effective_chat.id
    config = ScannerConfig()
    
    # Başlangıç mesajı
    start_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="🔍 <b>BIST DİPTEN YAKALAMA Taraması Başlıyor...</b>\n\n"
             "🎯 BB Alt Bant Stratejisi Aktif\n"
             "⏳ Bu işlem 1-3 dakika sürebilir.\n"
             "📊 Çok katmanlı filtreleme aktif.",
        parse_mode=ParseMode.HTML
    )
    
    results = []
    scanned = 0
    
    # Config'den sembolleri al veya default kullan
    try:
        from config import bist_stocks
        all_stocks = list(set(BIST_50_STOCKS + bist_stocks))
    except:
        all_stocks = BIST_50_STOCKS
    
    total = len(all_stocks)
    
    # Tarama
    for symbol in all_stocks:
        scanned += 1
        
        # Progress güncelle (her 10 hissede)
        if scanned % 10 == 0:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=start_msg.message_id,
                    text=f"🔍 <b>DİP Taraması...</b>\n\n"
                         f"📊 {scanned}/{total} ({scanned*100//total}%)\n"
                         f"🎯 Bulunan: {len(results)}",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
        
        try:
            # Veri al
            df = await get_stock_data(symbol, config.PERIOD)
            if df is None:
                continue
            
            # İndikatörler
            indicators = calculate_all_indicators(df)
            if indicators is None:
                continue
            
            bb_percent = indicators.get('bb_percent', 50)
            rsi = indicators['rsi']
            
            # ==================== DİPTEN YAKALAMA FİLTRELERİ ====================
            
            # KATMAN 1: BB Alt Yarısında olmalı (<%60)
            if bb_percent > 60:
                continue
            
            # KATMAN 2: RSI aşırı alımda olmamalı (<65)
            if rsi > 65:
                continue
            
            # KATMAN 3: En az bir dönüş sinyali olmalı
            has_turn_signal = (
                indicators['rsi_rising'] or 
                indicators['macd_histogram_rising'] or 
                indicators.get('stoch_cross_up', False) or
                indicators.get('stoch_bullish', False) or
                indicators['williams_r_rising']
            )
            if not has_turn_signal:
                continue
            
            # Puan hesapla
            score, passed_criteria = calculate_score(indicators, config)
            
            if score >= config.MIN_SCORE:
                results.append({
                    'symbol': symbol,
                    'score': score,
                    'indicators': indicators,
                    'passed_criteria': passed_criteria,
                    'bb_percent': bb_percent
                })
                
        except Exception as e:
            logger.debug(f"Hata {symbol}: {e}")
            continue
    
    # BB pozisyonuna göre sırala (en dipte olan önce), sonra puana göre
    results.sort(key=lambda x: (x['bb_percent'], -x['score']))
    results = results[:config.MAX_RESULTS]
    
    # Sonuç yoksa
    if not results:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=start_msg.message_id,
            text="😔 <b>Dipten yakalama kriterlerine uyan hisse bulunamadı.</b>\n\n"
                 "📊 BB alt bantında dönüş sinyali veren hisse yok.\n"
                 "💡 Piyasa aşırı alım bölgesinde olabilir.\n"
                 "⏳ Daha sonra tekrar deneyin.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Tarama tamamlandı mesajı
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=start_msg.message_id,
        text=f"✅ <b>DİP Taraması Tamamlandı!</b>\n\n"
             f"📊 Taranan: {scanned} hisse\n"
             f"🎯 DİP Fırsatı: {len(results)} hisse\n\n"
             f"🤖 AI Analizi hazırlanıyor...",
        parse_mode=ParseMode.HTML
    )
    
    # Sonuçları gönder
    for idx, result in enumerate(results, 1):
        symbol = result['symbol']
        score = result['score']
        indicators = result['indicators']
        passed_criteria = result['passed_criteria']
        bb_percent = result['bb_percent']
        
        # Hedefler
        targets = calculate_targets(indicators, score)
        
        # AI analizi
        ai_analysis = await ai_analyze_stock(symbol, indicators, score, passed_criteria, targets)
        
        # BB durumuna göre emoji
        if bb_percent <= 15:
            bb_emoji = "🔥🔥🔥"
            bb_status = "TAM DİP"
        elif bb_percent <= 30:
            bb_emoji = "🔥🔥"
            bb_status = "DİP BÖLGESİ"
        elif bb_percent <= 45:
            bb_emoji = "🔥"
            bb_status = "ALT-ORTA"
        else:
            bb_emoji = "✅"
            bb_status = "ORTA"
        
        trend = "📈" if indicators['daily_change'] > 0 else "📉" if indicators['daily_change'] < 0 else "➡️"
        
        # Risk/Ödül durumu
        rr = targets['risk_reward']
        if rr >= 2:
            rr_status = "🟢 Mükemmel"
        elif rr >= 1.5:
            rr_status = "🟢 İyi"
        elif rr >= 1:
            rr_status = "🟡 Kabul"
        else:
            rr_status = "🔴 Düşük"
        
        # Mesaj oluştur
        message = f"""
{bb_emoji} <b>#{idx} {symbol}</b> | Puan: <b>{score}/100</b>
{'─' * 32}

<b>📍 BB POZİSYONU: {bb_status} (%{bb_percent:.0f})</b>

<b>💰 FİYAT</b>
├ Güncel: <b>{indicators['current_price']:.2f} TL</b>
├ {trend} Günlük: %{indicators['daily_change']:.2f}
├ Haftalık: %{indicators['weekly_change']:.2f}
├ 52H Dipten: +%{indicators.get('from_52w_low', 0):.1f}
├ Destek: {indicators['support']:.2f} TL
└ Direnç: {indicators['resistance']:.2f} TL

<b>📊 TEKNİK</b>
├ RSI: {indicators['rsi']:.0f} {'↑' if indicators['rsi_rising'] else '↓'}
├ Stoch: {indicators['stoch_k']:.0f} {'↑' if indicators['stoch_bullish'] else '↓'}
├ MACD: {'🟢' if indicators['macd_positive'] else '🔴'} {'↑' if indicators['macd_histogram_rising'] else '↓'}
├ Hacim: {indicators['volume_ratio']:.1f}x {'🔥' if indicators['volume_ratio'] >= 1.5 else ''}
└ ADX: {indicators['adx']:.0f}

<b>🎯 HEDEFLER</b>
├ 🔴 Stop: {targets['stop_loss']:.2f} TL (-%{targets['stop_loss_pct']:.1f})
├ 🟢 TP1: {targets['take_profit_1']:.2f} TL (+%{targets['take_profit_1_pct']:.1f}) [BB Orta]
├ 🟢 TP2: {targets['take_profit_2']:.2f} TL (+%{targets['take_profit_2_pct']:.1f}) [BB Üst]
├ ⚖️ R/R: {rr:.2f} {rr_status}
└ ⏱️ Süre: {targets['hold_days']}

<b>✅ GEÇEN KRİTERLER</b>
{chr(10).join(passed_criteria[:8])}
{'─' * 32}

<b>🤖 AI ANALİZİ</b>
{ai_analysis}

⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}
"""
        
        # Mesajı böl (4000 karakter limiti)
        if len(message) > 4000:
            parts = [message[i:i+4000] for i in range(0, len(message), 4000)]
            for part in parts:
                await context.bot.send_message(chat_id=chat_id, text=part, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode=ParseMode.HTML)
        
        await asyncio.sleep(0.5)
    
    # Özet
    summary = f"""
{'═' * 32}
<b>📊 DİPTEN YAKALAMA ÖZETİ</b>
{'═' * 32}

🔍 Taranan: {scanned} hisse
🎯 DİP Fırsatı: {len(results)} hisse

<b>🔥 EN DERİN DİPLER:</b>
"""
    for i, r in enumerate(results[:5], 1):
        bb = r['bb_percent']
        emoji = "🔥🔥🔥" if bb <= 15 else "🔥🔥" if bb <= 30 else "🔥"
        summary += f"{i}. {r['symbol']} - BB %{bb:.0f} | {r['score']} puan {emoji}\n"
    
    summary += f"""
{'─' * 32}
💡 <b>STRATEJİ:</b>
• BB alt bantından orta banda yükselişi hedefle
• Stop-loss mutlaka kullan
• Kademe kademe al, tek seferde değil

⚠️ <i>Bu yatırım tavsiyesi değildir.</i>
⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}
"""
    
    await context.bot.send_message(chat_id=chat_id, text=summary, parse_mode=ParseMode.HTML)


# ==================== HANDLERS ====================
def ultimate_scanner_handler():
    return CommandHandler("ultimate", scan_bist_stocks)

def ultimate_scan_command():
    return CommandHandler("dip", scan_bist_stocks)
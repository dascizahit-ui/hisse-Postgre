import asyncio
import pandas as pd
import logging
from typing import List, Dict

# Projendeki mevcut modülleri import et
from stock_analyzer import StockAnalyzer
from config import fetch_bist_symbols

logger = logging.getLogger(__name__)

async def run_momentum_scan(symbols: List[str]) -> List[str]:
    logger.info("Algoritma 1: Momentum Taraması başlatılıyor...")
    found_stocks = []

    async def check_stock(symbol):
        try:
            df = await StockAnalyzer.get_stock_data(symbol, period="1y", interval="1d")
            if df is None or len(df) < 200:
                return

            indicators = await StockAnalyzer.calculate_technical_indicators(df)

            last_price = df['Close'].iloc[-1]
            last_open = df['Open'].iloc[-1]
            prev_close = df['Close'].iloc[-2] if len(df) >= 2 else None
            prev_vwap = indicators.get('vwap_prev', None)  # Önceki gün VWAP (eğer varsa)
            vwap_val = indicators.get('vwap', None)       # Son gün VWAP

            avg_volume_20 = df['Volume'].rolling(window=20).mean().iloc[-1]
            last_volume = df['Volume'].iloc[-1]

            rvol = last_volume / avg_volume_20 if avg_volume_20 != 0 else 0
            is_green_candle = last_price > last_open
            is_red_candle = last_price < last_open
            rvol_status = "Olumlu" if rvol > 1 and is_green_candle else "Olumsuz"
            emoji = "🟢" if is_green_candle else "🔴"

            # Fiyat ve indikatör koşulları
            is_price_above_ema200 = last_price > indicators.get('ema_200', float('inf'))
            is_ema_crossed = indicators.get('ema_5_20_cross', False)
            is_volume_high = last_volume > (avg_volume_20 * 1.5)
            is_rsi_strong = indicators.get('rsi', 0) > 55

            # Yeni eklenen VWAP kontrolleri
            is_price_above_vwap = False
            is_vwap_cross_up = False

            if vwap_val is not None and prev_close is not None:
                is_price_above_vwap = last_price > vwap_val
                # Önceki kapanış VWAP'ın altındaysa ve son kapanış üstündeyse yukarı kesişme var
                is_vwap_cross_up = (prev_close < vwap_val) and (last_price > vwap_val)

            # "Geçmiş olsun" uyarısı: rvol > 1 ve kırmızı mum
            warning_msg = ""
            if rvol > 1 and is_red_candle:
                warning_msg = " ⚠️ Geçmiş Olsun (Yüksek hacim + kırmızı mum)"

            if is_price_above_ema200 and is_ema_crossed and is_volume_high and is_rsi_strong:
                result_string = (
                    f"{symbol} | RVOL: {rvol:.2f} | Mum: {emoji} | Yorum: {rvol_status}"
                )
                if warning_msg:
                    result_string += warning_msg
                if is_price_above_vwap:
                    result_string += " 📈 Fiyat > VWAP"
                if is_vwap_cross_up:
                    result_string += " 🚀 VWAP Yukarı Kesişimi"
                logger.info(f"[Momentum Scan] Bulundu: {result_string}")
                found_stocks.append(result_string)

        except Exception as e:
            logger.error(f"[Momentum Scan] {symbol} işlenirken hata: {e}")

    tasks = [check_stock(s) for s in symbols]
    await asyncio.gather(*tasks)

    logger.info(f"Momentum Taraması tamamlandı. {len(found_stocks)} hisse bulundu.")
    return found_stocks


async def run_volatility_breakout_scan(symbols: List[str]) -> List[str]:
    logger.info("Algoritma 2: Volatilite Kırılım Taraması başlatılıyor...")
    found_stocks = []

    async def check_stock(symbol):
        try:
            df = await StockAnalyzer.get_stock_data(symbol, period="6mo", interval="1d")
            if df is None or len(df) < 60:
                return

            indicators = await StockAnalyzer.calculate_technical_indicators(df)

            last_price = df['Close'].iloc[-1]
            last_open = df['Open'].iloc[-1]
            prev_close = df['Close'].iloc[-2] if len(df) >= 2 else None

            vwap_val = indicators.get('vwap', None)
            avg_volume_20 = df['Volume'].rolling(window=20).mean().iloc[-1]
            last_volume = df['Volume'].iloc[-1]

            rvol = last_volume / avg_volume_20 if avg_volume_20 != 0 else 0
            is_green_candle = last_price > last_open
            is_red_candle = last_price < last_open
            rvol_status = "Olumlu" if rvol > 1 and is_green_candle else "Olumsuz"
            emoji = "🟢" if is_green_candle else "🔴"

            bb_high = df['bb_upper']
            bb_low = df['bb_lower']
            bb_middle = df['bb_middle']
            bb_width = ((bb_high - bb_low) / bb_middle).dropna()
            if len(bb_width) < 60:
                return

            recent_bb_width = bb_width.tail(60)
            is_squeezing = recent_bb_width.iloc[-1] <= recent_bb_width.quantile(0.10)

            is_price_above_ema50 = last_price > indicators.get('ema_50', float('inf'))
            is_breaking_out = last_price > indicators.get('bb_upper', float('inf'))
            is_volume_very_high = last_volume > (avg_volume_20 * 2)

            # VWAP kontrolleri
            is_price_above_vwap = False
            is_vwap_cross_up = False
            if vwap_val is not None and prev_close is not None:
                is_price_above_vwap = last_price > vwap_val
                is_vwap_cross_up = (prev_close < vwap_val) and (last_price > vwap_val)

            warning_msg = ""
            if rvol > 1 and is_red_candle:
                warning_msg = " ⚠️ Geçmiş Olsun (Yüksek hacim + kırmızı mum)"

            if is_price_above_ema50 and is_squeezing and is_breaking_out and is_volume_very_high:
                result_string = (
                    f"{symbol} | RVOL: {rvol:.2f} | Mum: {emoji} | Yorum: {rvol_status}"
                )
                if warning_msg:
                    result_string += warning_msg
                if is_price_above_vwap:
                    result_string += " 📈 Fiyat > VWAP"
                if is_vwap_cross_up:
                    result_string += " 🚀 VWAP Yukarı Kesişimi"
                logger.info(f"[Volatility Scan] Bulundu: {result_string}")
                found_stocks.append(result_string)

        except Exception as e:
            logger.error(f"[Volatility Scan] {symbol} işlenirken hata: {e}")

    tasks = [check_stock(s) for s in symbols]
    await asyncio.gather(*tasks)

    logger.info(f"Volatilite Taraması tamamlandı. {len(found_stocks)} hisse bulundu.")
    return found_stocks


async def run_all_scans() -> Dict[str, List[str]]:
    logger.info("Tüm taramalar için hisse senetleri çekiliyor...")
    try:
        symbols = fetch_bist_symbols()
        symbols = [s.replace('.IS', '') for s in symbols]
        logger.info(f"Taranacak {len(symbols)} adet hisse senedi bulundu.")
    except Exception as e:
        logger.error(f"Hisse listesi alınamadı: {e}")
        from config import bist_50_stocks
        symbols = bist_50_stocks
        logger.warning(f"BIST 50 listesi ile devam ediliyor.")

    momentum_results, volatility_results = await asyncio.gather(
        run_momentum_scan(symbols),
        run_volatility_breakout_scan(symbols)
    )

    return {
        "momentum": momentum_results,
        "volatility": volatility_results
    }

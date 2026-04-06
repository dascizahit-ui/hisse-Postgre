import yfinance as yf
import pandas as pd
import numpy as np

def teknik_analiz_skoru(df):
    skor = 0
    yorumlar = []

    # EMA'lar
    ema_list = [5, 20, 50, 200]
    for ema in ema_list:
        df[f'EMA_{ema}'] = df['Close'].ewm(span=ema).mean()

    # EMA koşulları (hepsi sırayla yukarı yönlü)
    ema_kosulu = all(df[f'EMA_{ema}'].iloc[-1] > df[f'EMA_{ema2}'].iloc[-1] for ema, ema2 in zip(ema_list[:-1], ema_list[1:]))
    if ema_kosulu:
        skor += 8
        yorumlar.append("✅ EMA 5 > 20 > 50 > 200: Trend güçlü yukarı")
    else:
        yorumlar.append("❌ EMA'lar uyumlu değil: Trend kararsız veya zayıf")

    # RSI
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    rsi = df['RSI'].iloc[-1]
    if rsi > 50:
        skor += 4
        yorumlar.append(f"✅ RSI {rsi:.2f} > 50: Momentum yukarı")
    else:
        yorumlar.append(f"❌ RSI {rsi:.2f} <= 50: Momentum zayıf")

    # MACD
    exp1 = df['Close'].ewm(span=12).mean()
    exp2 = df['Close'].ewm(span=26).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9).mean()

    if df['MACD'].iloc[-1] > df['Signal'].iloc[-1]:
        skor += 4
        yorumlar.append("✅ MACD > Sinyal: Al sinyali var")
    else:
        yorumlar.append("❌ MACD ≤ Sinyal: Net sinyal yok")

    return skor, yorumlar

import pytz
import requests
from asyncio import Semaphore
from concurrent.futures import ThreadPoolExecutor
import os

my_secret = "7866899479:AAGDi6XqrnQEJ59GD_DnqwfrWlaWW1BseVo"
my_secret1 = ['-1002892890103']
# Telegram Bot Ayarları
TOKEN = my_secret
ADMIN_CHAT_ID = my_secret1

# Türkiye saat dilimi
TR_TZ = pytz.timezone('Europe/Istanbul')

# Thread & API kontrolü
executor = ThreadPoolExecutor(max_workers=10)
api_semaphore = Semaphore(5)

# --- BIST Hisse Sembollerini TradingView'dan Çek ---
def fetch_bist_symbols():
    url = "https://scanner.tradingview.com/turkey/scan"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    payload = {
        "filter": [],
        "options": {"lang": "tr"},
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": ["name"],
        "sort": {"sortBy": "name", "sortOrder": "asc"}
    }

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()

    bist_stocks = [item["d"][0].replace("BIST:", "") for item in data.get("data", [])]
    return bist_stocks

# Örnek kullanım:
bist_stocks = fetch_bist_symbols()

# --- BIST 50 Sembolleri (Sabit Liste) ---
bist_50_stocks = [
    "AEFES", "AKBNK", "ALARK", "ARCLK", "ASELS", "ASTOR", "BIMAS",
    "CCOLA", "CIMSA", "DOAS", "DOHOL", "DSTKF", "EKGYO", "ENKAI",
    "EREGL", "FROTO", "GUBRF", "GARAN", "HALKB", "HEKTS", "ISCTR",
    "KCHOL", "KONTR", "KOZAL", "KOZAA", "KRDMD", "KUYAS", "MGROS",
    "MIATK", "OYAKC", "PGSUS", "PETKM", "SASA", "SISE", "SOKM",
    "TAVHL", "TCELL", "THYAO", "TKFEN", "TOASO", "TSKB", "TTKOM",
    "TUPRS", "ULKER", "VAKBN", "VESTL", "YKBNK", "SUNTK"
]
import os
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Railway'den gelecek olan DATABASE_URL
DATABASE_URL = os.environ.get("DATABASE_URL")

# Bağlantı havuzu
connection_pool = None

def init_pool():
    global connection_pool
    if not DATABASE_URL:
        logger.warning("DATABASE_URL bulunamadi, PostgreSQL baglantisi calismayabilir!")
        return
    try:
        connection_pool = SimpleConnectionPool(1, 10, dsn=DATABASE_URL)
        logger.info("PostgreSQL baglanti havuzu olusturuldu.")
    except Exception as e:
        logger.error(f"PostgreSQL havuzu olusturulamadi: {e}")
        raise

@contextmanager
def get_db_connection():
    """Veritabanı bağlantısı sağlar ve otomatik kapatır"""
    global connection_pool
    if connection_pool is None:
        init_pool()
        
    conn = None
    try:
        conn = connection_pool.getconn()
        yield conn
    except Exception as e:
        logger.error(f"Veritabanı bağlantısı başarısız: {e}")
        raise
    finally:
        if conn:
            try:
                # İşlem bitince bağlantıyı havuza geri ver
                connection_pool.putconn(conn)
            except Exception as e:
                logger.warning(f"Veritabanı bağlantısı iade edilirken hata: {e}")

def init_db():
    """Veritabanını başlatır ve gerekli tabloları oluşturur"""
    init_pool()
    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
                # Kullanıcılar tablosu
                c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')

                # Yasaklamalar tablosu
                c.execute('''CREATE TABLE IF NOT EXISTS bans (
                    user_id BIGINT PRIMARY KEY,
                    banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reason TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )''')

                # Susturmalar tablosu
                c.execute('''CREATE TABLE IF NOT EXISTS mutes (
                    user_id BIGINT PRIMARY KEY,
                    mute_until TIMESTAMP,
                    muted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reason TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )''')

                # Uyarılar tablosu
                c.execute('''CREATE TABLE IF NOT EXISTS alerts (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    symbol TEXT,
                    price REAL,
                    direction TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )''')

                # Raporlar tablosu
                c.execute('''CREATE TABLE IF NOT EXISTS reports (
                    report_id SERIAL PRIMARY KEY,
                    reporter_id BIGINT,
                    reported_user_id BIGINT,
                    message TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    FOREIGN KEY (reporter_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (reported_user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )''')

                # SAATLİK SİNYALLER TABLOSU
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

                # SİNYAL TAKİPLERİ TABLOSU
                c.execute('''CREATE TABLE IF NOT EXISTS signal_subscriptions (
                    user_id BIGINT,
                    symbol TEXT,
                    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    PRIMARY KEY (user_id, symbol),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )''')

                # İndeksler (IF NOT EXISTS için PostgreSQL'de CREATE INDEX IF NOT EXISTS kullanılır)
                c.execute('CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON alerts(user_id)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_reports_reporter_id ON reports(reporter_id)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_reports_reported_user_id ON reports(reported_user_id)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')

                # YENİ İNDEKSLER 
                c.execute('CREATE INDEX IF NOT EXISTS idx_hourly_signals_symbol ON hourly_signals(symbol)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_hourly_signals_timestamp ON hourly_signals(hour_timestamp)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_hourly_signals_created_at ON hourly_signals(created_at)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_signal_subscriptions_user ON signal_subscriptions(user_id)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_signal_subscriptions_symbol ON signal_subscriptions(symbol)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_signal_subscriptions_active ON signal_subscriptions(is_active)')

            conn.commit()
            logger.info("PostgreSQL Veritabanı başarıyla başlatıldı")

    except Exception as e:
        logger.error(f"PostgreSQL Veritabanı başlatılamadı: {e}")
        raise
# CRITICAL WARNING FOR MAINTAINERS:
# DO NOT change the logic below to strictly overwrite or delete old records.
# Coinalyze history is severely limited (e.g., last 2000 candles).
# Once historical data is deleted or overwritten with NULLs, it CANNOT be re-downloaded.
# The database mechanism MUST remain purely incremental/append-only.

"""
Core module consolidating database, data fetching, and data exporting functionality.
"""
import sqlite3
import os
import logging
import requests
import pandas as pd
import time
import io
import zipfile
import concurrent.futures
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Callable
from contextlib import contextmanager
from dotenv import load_dotenv

# Configure logging
logger = logging.getLogger(__name__)

# Database path in the app directory
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'market_data.db')

# ---------------------------------------------------------------------------
# Database Logic
# ---------------------------------------------------------------------------

@contextmanager
def get_connection():
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        if conn: conn.rollback()
        raise
    finally:
        if conn: conn.close()

def init_db():
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS market_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    time TIMESTAMP NOT NULL,
                    price_open REAL,
                    price_close REAL,
                    price_high REAL,
                    price_low REAL,
                    volume REAL,
                    oi_open_coin REAL,
                    oi_high_coin REAL,
                    oi_low_coin REAL,
                    oi_close_coin REAL,
                    liq_long_coin REAL,
                    liq_short_coin REAL,
                    UNIQUE(ticker, timeframe, time)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ticker_tf_time ON market_data(ticker, timeframe, time)')
            conn.commit()
            _check_schema_updates(conn)
            logger.info("Database initialized successfully")
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

def _check_schema_updates(conn):
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(market_data)")
        columns = [row['name'] for row in cursor.fetchall()]

        # New columns to add based on test_csv_builder.py
        required_columns = {
            'volume': 'REAL',
            'taker_buy_base': 'REAL',
            'mark_price': 'REAL',
            'index_price': 'REAL',
            'funding_rate': 'REAL',
            'oi_binance': 'REAL',
            'ls_ratio': 'REAL',
            'top_ls_ratio': 'REAL',
            'taker_vol_ratio': 'REAL'
        }

        for col, col_type in required_columns.items():
            if col not in columns:
                logger.info(f"Adding '{col}' column to market_data table")
                cursor.execute(f"ALTER TABLE market_data ADD COLUMN {col} {col_type}")
                conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Failed to check schema updates: {e}")
        pass

def _validate_ticker_timeframe(ticker: str, timeframe: str):
    if not ticker or not isinstance(ticker, str) or not ticker.strip():
        raise ValueError("Ticker must be a non-empty string")
    if not timeframe or not isinstance(timeframe, str) or not timeframe.strip():
        raise ValueError("Timeframe must be a non-empty string")

def insert_data(df: pd.DataFrame, ticker: str, timeframe: str):
    _validate_ticker_timeframe(ticker, timeframe)
    if df.empty:
        logger.warning(f"Empty DataFrame provided for {ticker} {timeframe}")
        return
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            # Map dataframe columns to DB columns
            db_cols = [
                'time', 'price_open', 'price_close', 'price_high', 'price_low', 'volume',
                'oi_open_coin', 'oi_high_coin', 'oi_low_coin', 'oi_close_coin',
                'liq_long_coin', 'liq_short_coin', 'taker_buy_base', 'mark_price',
                'index_price', 'funding_rate', 'oi_binance', 'ls_ratio',
                'top_ls_ratio', 'taker_vol_ratio'
            ]

            records = []
            for _, row in df.iterrows():
                time_val = row['time']
                if isinstance(time_val, pd.Timestamp): time_val = time_val.isoformat()
                elif isinstance(time_val, datetime): time_val = time_val.isoformat()

                def _val(col):
                    v = row.get(col)
                    return None if pd.isna(v) else v

                records.append((
                    ticker, timeframe, time_val,
                    _val('price_open'), _val('price_close'), _val('price_high'), _val('price_low'), _val('volume'),
                    _val('oi_open_coin'), _val('oi_high_coin'), _val('oi_low_coin'), _val('oi_close_coin'),
                    _val('liq_long_coin'), _val('liq_short_coin'),
                    _val('taker_buy_base'), _val('mark_price'), _val('index_price'), _val('funding_rate'),
                    _val('oi_binance'), _val('ls_ratio'), _val('top_ls_ratio'), _val('taker_vol_ratio')
                ))

            cursor.executemany('''
                INSERT INTO market_data
                (ticker, timeframe, time, price_open, price_close, price_high, price_low, volume,
                 oi_open_coin, oi_high_coin, oi_low_coin, oi_close_coin,
                 liq_long_coin, liq_short_coin, taker_buy_base, mark_price, index_price,
                 funding_rate, oi_binance, ls_ratio, top_ls_ratio, taker_vol_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, timeframe, time) DO UPDATE SET
                    price_open = COALESCE(excluded.price_open, market_data.price_open),
                    price_close = COALESCE(excluded.price_close, market_data.price_close),
                    price_high = COALESCE(excluded.price_high, market_data.price_high),
                    price_low = COALESCE(excluded.price_low, market_data.price_low),
                    volume = COALESCE(excluded.volume, market_data.volume),
                    oi_open_coin = COALESCE(excluded.oi_open_coin, market_data.oi_open_coin),
                    oi_high_coin = COALESCE(excluded.oi_high_coin, market_data.oi_high_coin),
                    oi_low_coin = COALESCE(excluded.oi_low_coin, market_data.oi_low_coin),
                    oi_close_coin = COALESCE(excluded.oi_close_coin, market_data.oi_close_coin),
                    liq_long_coin = COALESCE(excluded.liq_long_coin, market_data.liq_long_coin),
                    liq_short_coin = COALESCE(excluded.liq_short_coin, market_data.liq_short_coin),
                    taker_buy_base = COALESCE(excluded.taker_buy_base, market_data.taker_buy_base),
                    mark_price = COALESCE(excluded.mark_price, market_data.mark_price),
                    index_price = COALESCE(excluded.index_price, market_data.index_price),
                    funding_rate = COALESCE(excluded.funding_rate, market_data.funding_rate),
                    oi_binance = COALESCE(excluded.oi_binance, market_data.oi_binance),
                    ls_ratio = COALESCE(excluded.ls_ratio, market_data.ls_ratio),
                    top_ls_ratio = COALESCE(excluded.top_ls_ratio, market_data.top_ls_ratio),
                    taker_vol_ratio = COALESCE(excluded.taker_vol_ratio, market_data.taker_vol_ratio)
            ''', records)
            conn.commit()
            logger.info(f"Inserted/Updated {len(records)} records for {ticker} {timeframe}")
    except Exception as e:
        logger.error(f"Failed to insert data for {ticker} {timeframe}: {e}")
        raise

def get_data(ticker: str, timeframe: str, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> pd.DataFrame:
    _validate_ticker_timeframe(ticker, timeframe)
    try:
        with get_connection() as conn:
            query = '''
                SELECT * FROM market_data
                WHERE ticker = ? AND timeframe = ?
            '''
            params = [ticker, timeframe]
            if start_time:
                query += ' AND time >= ?'
                params.append(start_time.isoformat() if isinstance(start_time, datetime) else start_time)
            if end_time:
                query += ' AND time <= ?'
                params.append(end_time.isoformat() if isinstance(end_time, datetime) else end_time)
            query += ' ORDER BY time'
            df = pd.read_sql_query(query, conn, params=tuple(params))
            if not df.empty:
                df['time'] = pd.to_datetime(df['time'])
            return df
    except Exception as e:
        logger.error(f"Failed to retrieve data for {ticker} {timeframe}: {e}")
        raise

def get_available_tickers() -> List[Tuple[str, str]]:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT ticker, timeframe FROM market_data ORDER BY ticker, timeframe')
            return [(row['ticker'], row['timeframe']) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Failed to get available tickers: {e}")
        raise

def get_data_summary() -> List[dict]:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT ticker, timeframe, MIN(time) as start_time, MAX(time) as end_time, COUNT(*) as count
                FROM market_data GROUP BY ticker, timeframe ORDER BY ticker, timeframe
            ''')
            return [{'ticker': row['ticker'], 'timeframe': row['timeframe'], 'start_time': row['start_time'], 'end_time': row['end_time'], 'count': row['count']} for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Failed to get data summary: {e}")
        raise

def get_latest_timestamp(ticker: str, timeframe: str) -> Optional[datetime]:
    _validate_ticker_timeframe(ticker, timeframe)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT MAX(time) as latest FROM market_data WHERE ticker = ? AND timeframe = ?', (ticker, timeframe))
            row = cursor.fetchone()
            if row and row['latest']:
                try:
                    return pd.to_datetime(row['latest']).to_pydatetime()
                except (ValueError, TypeError):
                    return datetime.fromisoformat(row['latest'])
            return None
    except Exception as e:
        logger.error(f"Failed to get latest timestamp for {ticker} {timeframe}: {e}")
        raise

def get_earliest_timestamp(ticker: str, timeframe: str) -> Optional[datetime]:
    _validate_ticker_timeframe(ticker, timeframe)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT MIN(time) as earliest FROM market_data WHERE ticker = ? AND timeframe = ?', (ticker, timeframe))
            row = cursor.fetchone()
            if row and row['earliest']:
                try:
                    return pd.to_datetime(row['earliest']).to_pydatetime()
                except (ValueError, TypeError):
                    return datetime.fromisoformat(row['earliest'])
            return None
    except Exception as e:
        logger.error(f"Failed to get earliest timestamp for {ticker} {timeframe}: {e}")
        raise

def get_missing_metrics_start(ticker: str, timeframe: str) -> Optional[datetime]:
    _validate_ticker_timeframe(ticker, timeframe)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT MIN(time) as missing_start
                FROM market_data
                WHERE ticker = ? AND timeframe = ?
                AND (funding_rate IS NULL OR mark_price IS NULL OR oi_binance IS NULL)
            ''', (ticker, timeframe))
            row = cursor.fetchone()
            if row and row['missing_start']:
                try:
                    return pd.to_datetime(row['missing_start']).to_pydatetime()
                except (ValueError, TypeError):
                    return datetime.fromisoformat(row['missing_start'])
            return None
    except Exception as e:
        logger.error(f"Failed to get missing metrics timestamp for {ticker} {timeframe}: {e}")
        return None

def get_missing_intervals(ticker: str, timeframe: str, start_ts: datetime, end_ts: datetime) -> List[Tuple[datetime, datetime]]:
    _validate_ticker_timeframe(ticker, timeframe)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT time FROM market_data
                WHERE ticker = ? AND timeframe = ?
                AND (funding_rate IS NULL OR mark_price IS NULL OR oi_binance IS NULL)
                ORDER BY time
            ''', (ticker, timeframe))
            rows = cursor.fetchall()
            if not rows: return []

            missing_times = [pd.to_datetime(r['time']).tz_localize(None) for r in rows]
            missing_times = [t for t in missing_times if start_ts <= t <= end_ts]
            if not missing_times: return []

            ranges = []
            start_gap = missing_times[0]
            prev_time = missing_times[0]

            for t in missing_times[1:]:
                # If gap is larger than 2 days, split the chunk
                if (t - prev_time).total_seconds() > 86400 * 2:
                    ranges.append((start_gap - timedelta(hours=1), prev_time + timedelta(hours=1)))
                    start_gap = t
                prev_time = t
            ranges.append((start_gap - timedelta(hours=1), prev_time + timedelta(hours=1)))
            return ranges
    except Exception as e:
        logger.error(f"Error finding gaps for {ticker} {timeframe}: {e}")
        return []

def delete_data(ticker: str, timeframe: str) -> int:
    _validate_ticker_timeframe(ticker, timeframe)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM market_data WHERE ticker = ? AND timeframe = ?', (ticker, timeframe))
            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count
    except Exception as e:
        logger.error(f"Failed to delete data for {ticker} {timeframe}: {e}")
        raise

# ---------------------------------------------------------------------------
# Data Fetcher Logic
# ---------------------------------------------------------------------------

# Fix path: look in the same directory as core.py
dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path)

API_KEY = os.getenv('API_KEY_COINALYZE')
BASE_URL = 'https://api.coinalyze.net/v1'

# Global cache to prevent re-downloading identical daily ZIP archives across different timeframes
VISION_DAY_CACHE = {}

TIMEFRAME_MAP = {
    '1m': '1min', '5m': '5min', '15m': '15min', '30m': '30min',
    '1h': '1hour', '2h': '2hour', '4h': '4hour', '6h': '6hour',
    '12h': '12hour', '1d': 'daily',
}

TICKER_MAP = {
    'BTCUSDT': 'BTCUSDT_PERP.A', 'ETHUSDT': 'ETHUSDT_PERP.A',
    'SOLUSDT': 'SOLUSDT_PERP.A', 'BNBUSDT': 'BNBUSDT_PERP.A',
    'XRPUSDT': 'XRPUSDT_PERP.A', 'ADAUSDT': 'ADAUSDT_PERP.A',
    'DOGEUSDT': 'DOGEUSDT_PERP.A', 'AVAXUSDT': 'AVAXUSDT_PERP.A',
    'DOTUSDT': 'DOTUSDT_PERP.A', 'LTCUSDT': 'LTCUSDT_PERP.A',
}

BINANCE_INTERVAL_MAP = {
    '1min': '1m', '5min': '5m', '15min': '15m', '30min': '30m',
    '1hour': '1h', '2hour': '2h', '4hour': '4h', '6hour': '6h',
    '12hour': '12h', 'daily': '1d',
}

def get_api_symbol(ticker: str) -> str:
    return TICKER_MAP.get(ticker.upper(), f"{ticker.upper()}_PERP.A")

def get_api_interval(timeframe: str) -> str:
    return TIMEFRAME_MAP.get(timeframe.lower(), timeframe)

def _make_request(endpoint: str, params: dict, max_retries: int = 3) -> Optional[dict]:
    for attempt in range(max_retries):
        try:
            response = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=30)
            if response.status_code == 200: return response.json()
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 2))
                logger.warning(f"Rate limit exceeded for {endpoint}. Waiting {retry_after}s...")
                time.sleep(retry_after)
            else:
                logger.error(f"API Error {response.status_code} for {endpoint}: {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {endpoint} on attempt {attempt+1}: {e}")
            time.sleep(1)
    return None

def _fetch_binance_klines(symbol: str, interval: str, start_ms: int, end_ms: int, price_type: str = '') -> pd.DataFrame:
    binance_interval = BINANCE_INTERVAL_MAP.get(interval, interval)
    binance_symbol = symbol.replace('_PERP.A', '')

    endpoint = 'klines'
    if price_type == 'mark': endpoint = 'markPriceKlines'
    elif price_type == 'index': endpoint = 'indexPriceKlines'

    # Calculate step size (1000 candles per chunk for safety limit)
    interval_ms_map = {'1m': 60000, '3m': 180000, '5m': 300000, '15m': 900000, '30m': 1800000, '1h': 3600000, '2h': 7200000, '4h': 14400000, '6h': 21600000, '12h': 43200000, '1d': 86400000}
    step_ms = interval_ms_map.get(binance_interval, 60000) * 1000

    chunks = [(ts, min(ts + step_ms - 1, end_ms)) for ts in range(start_ms, end_ms, step_ms)]
    logger.info(f"Fetching Binance {endpoint} for {binance_symbol} ({binance_interval}) in {len(chunks)} parallel chunks")

    def fetch_chunk(chunk):
        c_start, c_end = chunk
        params = {'interval': binance_interval, 'startTime': c_start, 'endTime': c_end, 'limit': 1500}
        if price_type == 'index': params['pair'] = binance_symbol
        else: params['symbol'] = binance_symbol
        try:
            res = requests.get(f"https://fapi.binance.com/fapi/v1/{endpoint}", params=params, timeout=15)
            if res.status_code == 200: return res.json()
        except: pass
        return []

    all_klines = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = executor.map(fetch_chunk, chunks)
        for res in results:
            if res: all_klines.extend(res)

    if not all_klines:
        logger.warning(f"No data retrieved for Binance {endpoint} {binance_symbol}")
        return pd.DataFrame()

    df = pd.DataFrame(all_klines)
    df = df.drop_duplicates(subset=[0]).sort_values(by=0)  # Ensure unique sorted times
    df['time'] = pd.to_datetime(df[0], unit='ms')

    if price_type == '':
        df = df.rename(columns={1: 'price_open', 2: 'price_high', 3: 'price_low', 4: 'price_close', 5: 'volume', 9: 'taker_buy_base'})
        for col in ['price_open', 'price_close', 'price_high', 'price_low', 'volume', 'taker_buy_base']:
            df[col] = df[col].astype(float)
        return df[['time', 'price_open', 'price_close', 'price_high', 'price_low', 'volume', 'taker_buy_base']]
    else:
        df[f'{price_type}_price'] = df[4].astype(float)
        return df[['time', f'{price_type}_price']]

def _fetch_funding_rate(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    all_funding = []
    current_start = start_ms
    binance_symbol = symbol.replace('_PERP.A', '')
    while current_start < end_ms:
        params = {'symbol': binance_symbol, 'startTime': current_start, 'endTime': end_ms, 'limit': 1000}
        try:
            res = requests.get('https://fapi.binance.com/fapi/v1/fundingRate', params=params, timeout=30)
            if res.status_code == 200 and res.json():
                data = res.json()
                all_funding.extend(data)
                current_start = data[-1]['fundingTime'] + 1
            else: break
        except Exception:
            time.sleep(1)
            break
    if not all_funding: return pd.DataFrame()
    df = pd.DataFrame(all_funding)
    df['time'] = pd.to_datetime(df['fundingTime'], unit='ms')
    df['funding_rate'] = df['fundingRate'].astype(float)
    return df[['time', 'funding_rate']]

def _fetch_vision_metrics(symbol: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    binance_symbol = symbol.replace('_PERP.A', '')
    days = [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
    session = requests.Session()

    def download_day(d):
        date_str = d.strftime('%Y-%m-%d')
        cache_key = (binance_symbol, date_str)

        # Return cached dataframe if already downloaded in this session
        if cache_key in VISION_DAY_CACHE:
            return VISION_DAY_CACHE[cache_key].copy()

        url = f"https://data.binance.vision/data/futures/um/daily/metrics/{binance_symbol}/{binance_symbol}-metrics-{date_str}.zip"
        try:
            res = session.get(url, timeout=30)
            if res.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
                    df = pd.read_csv(zf.open(zf.namelist()[0]), low_memory=False)
                    t_col = 'create_time'
                    if df[t_col].astype(str).str.contains('-').any():
                        df['time'] = pd.to_datetime(df[t_col], errors='coerce')
                    else:
                        df['time'] = pd.to_datetime(pd.to_numeric(df[t_col], errors='coerce'), unit='ms')
                    df = df.dropna(subset=['time'])
                    df = df[['time', 'sum_open_interest', 'count_long_short_ratio', 'sum_toptrader_long_short_ratio', 'sum_taker_long_short_vol_ratio']]
                    df.columns = ['time', 'oi_binance', 'ls_ratio', 'top_ls_ratio', 'taker_vol_ratio']
                    VISION_DAY_CACHE[cache_key] = df.copy()  # Save to cache
                    return df.copy()
        except Exception as e:
            logger.warning(f"Vision metrics missing or failed for {binance_symbol} on {date_str}: {e}")

    all_dfs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for df in executor.map(download_day, days):
            if df is not None: all_dfs.append(df)
    if not all_dfs: return pd.DataFrame()
    df_final = pd.concat(all_dfs, ignore_index=True)
    df_final['time'] = pd.to_datetime(df_final['time'])
    # IMPORTANT: Strip timezones for compatibility with merge_asof
    df_final['time'] = df_final['time'].apply(lambda x: x.replace(tzinfo=None) if pd.notnull(x) else x)
    # IMPORTANT: Align datetime resolution with main klines to prevent MergeError
    df_final['time'] = df_final['time'].astype('datetime64[ms]')
    return df_final.sort_values('time').drop_duplicates('time')

def _fetch_oi(symbol: str, interval: str, start_time: int, end_time: int) -> pd.DataFrame:
    params = {'api_key': API_KEY, 'symbols': symbol, 'interval': interval, 'from': start_time, 'to': end_time, 'convert_to_usd': 'false'}
    response = _make_request('open-interest-history', params)
    if response and isinstance(response, list) and response[0].get('history'):
        df = pd.DataFrame(response[0]['history'])
        df['time'] = pd.to_datetime(df['t'], unit='s')
        df.drop(columns=['t'], inplace=True)  # Remove original column to avoid conflict
        df.rename(columns={'o': 'oi_open_coin', 'h': 'oi_high_coin', 'l': 'oi_low_coin', 'c': 'oi_close_coin'}, inplace=True)
        return df[['time', 'oi_open_coin', 'oi_high_coin', 'oi_low_coin', 'oi_close_coin']]
    return pd.DataFrame()

def _fetch_liquidations(symbol: str, interval: str, start_time: int, end_time: int) -> pd.DataFrame:
    params = {'api_key': API_KEY, 'symbols': symbol, 'interval': interval, 'from': start_time, 'to': end_time, 'convert_to_usd': 'false'}
    response = _make_request('liquidation-history', params)
    if response and isinstance(response, list) and response[0].get('history'):
        df = pd.DataFrame(response[0]['history'])
        df['time'] = pd.to_datetime(df['t'], unit='s')
        df.drop(columns=['t'], inplace=True)  # Remove original column to avoid conflict
        if 'l' in df.columns and 's' in df.columns:
            df.rename(columns={'l': 'liq_long_coin', 's': 'liq_short_coin'}, inplace=True)
            return df[['time', 'liq_long_coin', 'liq_short_coin']]
    return pd.DataFrame()

def download_data(ticker: str, timeframe: str, start_date: datetime, end_date: Optional[datetime] = None, progress_callback: Optional[Callable] = None, incremental: bool = True) -> int:
    if end_date is None: end_date = datetime.now()
    api_symbol, api_interval = get_api_symbol(ticker), get_api_interval(timeframe)

    ranges_to_download = []
    earliest = get_earliest_timestamp(ticker, timeframe)
    latest = get_latest_timestamp(ticker, timeframe)
    missing_start = get_missing_metrics_start(ticker, timeframe)

    if not earliest or not latest:
        # DB is empty, download full range
        ranges_to_download.append((start_date, end_date))
    else:
        # 1. Prefix: Data missing before our DB history
        if start_date < earliest:
            ranges_to_download.append((start_date, earliest))

        # 2. Overlap Gaps: Find EXACT missing blocks inside the DB to prevent over-downloading
        overlap_start = max(start_date, earliest)
        overlap_end = min(end_date, latest)
        if overlap_start < overlap_end:
            gaps = get_missing_intervals(ticker, timeframe, overlap_start, overlap_end)
            ranges_to_download.extend(gaps)

        # 3. Suffix: Fresh data after our DB history
        if end_date > latest:
            ranges_to_download.append((latest - timedelta(hours=1), end_date))

    if not ranges_to_download:
        msg = f"Data up to date for {ticker} ({timeframe})"
        if progress_callback: progress_callback(msg)
        logger.info(msg)
        return 0

    total_records = 0
    for range_start, range_end in ranges_to_download:
        start_ts, end_ts = int(range_start.timestamp()), int(range_end.timestamp())
        start_ms, end_ms = start_ts * 1000, end_ts * 1000
        if progress_callback: progress_callback(f"Fetching {ticker} ({timeframe}): {range_start.date()} -> {range_end.date()}")

        # 1. OHLCV + Taker Buy Base
        try:
            if progress_callback: progress_callback(f"  [{ticker}] Fetching candles (Binance)...")
            df_ohlcv = _fetch_binance_klines(api_symbol, api_interval, start_ms, end_ms)
            if not df_ohlcv.empty:
                # Merging additional metrics here
                # Mark & Index Price
                df_mark = _fetch_binance_klines(api_symbol, api_interval, start_ms, end_ms, 'mark')
                if not df_mark.empty: df_ohlcv = pd.merge(df_ohlcv, df_mark, on='time', how='left')
                df_index = _fetch_binance_klines(api_symbol, api_interval, start_ms, end_ms, 'index')
                if not df_index.empty: df_ohlcv = pd.merge(df_ohlcv, df_index, on='time', how='left')

                # Funding Rate
                df_fund = _fetch_funding_rate(api_symbol, start_ms, end_ms)
                if not df_fund.empty:
                    df_ohlcv = pd.merge_asof(df_ohlcv.sort_values('time'), df_fund.sort_values('time'), on='time', direction='backward')

                # Vision Metrics (BINANCE VISION ZIPs)
                df_vis = _fetch_vision_metrics(api_symbol, range_start, range_end)
                if not df_vis.empty:
                    df_ohlcv = pd.merge_asof(df_ohlcv.sort_values('time'), df_vis.sort_values('time'), on='time', direction='backward')

                # IMPORTANT: Fill gaps (ffill/bfill) before DB write
                cols_to_fill = ['funding_rate', 'oi_binance', 'ls_ratio', 'top_ls_ratio', 'taker_vol_ratio', 'mark_price', 'index_price']
                for c in cols_to_fill:
                    if c in df_ohlcv.columns:
                        df_ohlcv[c] = df_ohlcv[c].ffill().bfill()

                insert_data(df_ohlcv, ticker, timeframe)
                total_records += len(df_ohlcv)
                if progress_callback: progress_callback(f"  [{ticker}] Candles & metrics: saved {len(df_ohlcv)} records")
        except Exception as e:
            # Log the hidden crash (e.g., MergeError) to the terminal
            logger.error(f"Failed to merge or insert main data for {ticker}: {e}", exc_info=True)
            if progress_callback: progress_callback(f"  [{ticker}] Main data error: {e}")

        # 2. OI and Liquidations (Coinalyze)
        ALLOWED_COINALYZE = ['1min', '5min', '15min', '30min', '1hour', '2hour', '4hour', '6hour', '12hour', 'daily']
        if API_KEY and api_interval in ALLOWED_COINALYZE:
            try:
                msg = f"  [{ticker}] Fetching OI (Coinalyze)..."
                if progress_callback: progress_callback(msg)
                logger.info(msg)



                df_oi = _fetch_oi(api_symbol, api_interval, start_ts, end_ts)
                time.sleep(0.5)
                if not df_oi.empty:
                    insert_data(df_oi, ticker, timeframe)
                    total_records += len(df_oi)
                    success_msg = f"  [{ticker}] OI: saved {len(df_oi)} records"
                    if progress_callback: progress_callback(success_msg)
                    logger.info(success_msg)
            except Exception as e:
                err_msg = f"  [{ticker}] OI error: {e}"
                if progress_callback: progress_callback(err_msg)
                logger.error(err_msg, exc_info=True)

            try:
                msg_liq = f"  [{ticker}] Fetching liquidations (Coinalyze)..."
                if progress_callback: progress_callback(msg_liq)
                logger.info(msg_liq)



                df_liq = _fetch_liquidations(api_symbol, api_interval, start_ts, end_ts)
                time.sleep(0.5)
                if not df_liq.empty:
                    insert_data(df_liq, ticker, timeframe)
                    total_records += len(df_liq)
                    success_msg_liq = f"  [{ticker}] Liquidations: saved {len(df_liq)} records"
                    if progress_callback: progress_callback(success_msg_liq)
                    logger.info(success_msg_liq)
            except Exception as e:
                err_msg_liq = f"  [{ticker}] Liquidations error: {e}"
                if progress_callback: progress_callback(err_msg_liq)
                logger.error(err_msg_liq, exc_info=True)
        else:
            warn_msg = f"  [{ticker}] API_KEY_COINALYZE not found — OI and liquidations skipped"
            if progress_callback: progress_callback(warn_msg)
            logger.warning(warn_msg)

    return total_records

def download_multiple(tickers: list, timeframes: list, start_date: datetime, end_date: Optional[datetime] = None, progress_callback: Optional[Callable] = None, incremental: bool = True) -> dict:
    results, total, current = {}, len(tickers) * len(timeframes), 0
    for ticker in tickers:
        for timeframe in timeframes:
            current += 1
            base_pct = ((current - 1) / total) * 100
            if progress_callback: progress_callback(f"[{current}/{total}] {ticker} {timeframe}", base_pct)
            def sub_progress(msg, sub_pct=0):
                if progress_callback:
                    overall_pct = base_pct + ((sub_pct / 100) * (100 / total))
                    progress_callback(msg, overall_pct)
            try:
                count = download_data(ticker=ticker, timeframe=timeframe, start_date=start_date, end_date=end_date, progress_callback=sub_progress, incremental=incremental)
                results[(ticker, timeframe)] = count
            except Exception as e:
                if progress_callback: progress_callback(f"Error: {ticker} {timeframe}: {e}", base_pct)
                results[(ticker, timeframe)] = -1
            time.sleep(1)
    return results

# ---------------------------------------------------------------------------
# Data Exporter Logic
# ---------------------------------------------------------------------------

def export_to_csv(ticker: str, timeframe: str, start_date: datetime, end_date: datetime, columns: List[str], output_file: str) -> bool:
    try:
        df = get_data(ticker, timeframe, start_date, end_date)
        if df.empty: return False
        available_cols = df.columns.tolist()
        cols_to_export = [c for c in columns if c in available_cols]
        if not cols_to_export: return False
        df[cols_to_export].to_csv(output_file, index=False)
        return True
    except Exception as e:
        print(f"Export failed: {e}")
        return False

# Initialize database on module import
try:
    init_db()
except Exception as e:
    logger.critical(f"Failed to initialize database on module import: {e}")
    raise

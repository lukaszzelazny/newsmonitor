"""Utility functions for fetching financial market data with PLN normalization."""
import os
import yfinance as yf
from functools import lru_cache
import pandas as pd
from typing import Dict, List, Optional, Callable, Tuple
import requests
import time
from sqlalchemy.orm import Session
from datetime import datetime

# Database session factory for --database mode
_DB_SESSION_FACTORY: Optional[Callable[[], Session]] = None

def enable_database_mode(session_factory: Callable[[], Session]):
    """Enable database mode for fetching prices."""
    global _DB_SESSION_FACTORY
    _DB_SESSION_FACTORY = session_factory

def _get_db_session() -> Optional[Session]:
    if _DB_SESSION_FACTORY:
        return _DB_SESSION_FACTORY()
    return None

def _get_caching_session() -> Optional[Session]:
    """
    Attempts to create a database session for caching purposes
    even if database mode is not explicitly enabled.
    """
    if _DB_SESSION_FACTORY:
        return None  # Let the main logic handle explicit DB mode

    try:
        from database import Database
        db = Database()
        return db.Session()
    except (ImportError, Exception):
        pass
    return None

def _find_asset_in_db(session: Session, ticker_symbol: str):
    """
    Helper to find an asset in the database, trying variations of the ticker.
    DB seems to store Polish stocks with .PL suffix, while app might use .WA or no suffix.
    """
    try:
        from backend.database import Asset
        
        # 1. Exact match
        asset = session.query(Asset).filter(Asset.ticker == ticker_symbol).first()
        if asset:
            return asset

        # 2. Try common suffixes if input has no suffix
        if '.' not in ticker_symbol:
            # Prioritize .PL as observed in DB
            candidates = [f"{ticker_symbol}.PL", f"{ticker_symbol}.WA", f"{ticker_symbol}.US"]
            for c in candidates:
                asset = session.query(Asset).filter(Asset.ticker == c).first()
                if asset:
                    return asset
        
        # 3. Handle .WA -> .PL conversion (common mismatch)
        if ticker_symbol.endswith('.WA'):
            alt = ticker_symbol.replace('.WA', '.PL')
            asset = session.query(Asset).filter(Asset.ticker == alt).first()
            if asset:
                return asset
                
        # 4. Handle .PL -> .WA conversion (reverse mismatch)
        if ticker_symbol.endswith('.PL'):
            alt = ticker_symbol.replace('.PL', '.WA')
            asset = session.query(Asset).filter(Asset.ticker == alt).first()
            if asset:
                return asset
                
        # 5. If ticker ends with .PL, try without .PL (e.g., SNT.PL -> SNT)
        if ticker_symbol.endswith('.PL'):
            base = ticker_symbol[:-3]  # remove '.PL'
            asset = session.query(Asset).filter(Asset.ticker == base).first()
            if asset:
                return asset
                
        # 6. If ticker has no suffix but we have .PL version, try that (reverse of 5)
        if '.' not in ticker_symbol:
            asset = session.query(Asset).filter(Asset.ticker == ticker_symbol + '.PL').first()
            if asset:
                return asset

    except ImportError:
        pass
        
    return None

def _get_or_create_asset(session: Session, ticker_symbol: str):
    """
    Finds an asset or creates it if it doesn't exist.
    """
    from backend.database import Asset
    
    asset = _find_asset_in_db(session, ticker_symbol)
    if asset:
        return asset
        
    # Create new
    clean_ticker = ticker_symbol.upper()
    
    new_asset = Asset(
        ticker=clean_ticker,
        asset_type='stock' # Default
    )
    session.add(new_asset)
    session.flush() # To get ID
    return new_asset

def _save_history_to_db(session: Session, asset_id: int, df: pd.DataFrame):
    """
    Saves DataFrame history to DB.
    df index should be DatetimeIndex or contain Date column.
    """
    from backend.database import AssetPriceHistory
    
    if df is None or df.empty:
        return

    # Normalize DF
    # If it comes from yf.Ticker.history, index is Date.
    
    for date_idx, row in df.iterrows():
        try:
            date_val = date_idx.date() if hasattr(date_idx, 'date') else pd.to_datetime(date_idx).date()
            
            # Check existing
            existing = session.query(AssetPriceHistory).filter(
                AssetPriceHistory.asset_id == asset_id,
                AssetPriceHistory.date == date_val
            ).first()
            
            close_val = float(row['Close'])
            # Basic validation
            if pd.isna(close_val):
                continue

            if existing:
                # Update
                existing.close = close_val
                if 'Open' in row: existing.open = float(row['Open'])
                if 'High' in row: existing.high = float(row['High'])
                if 'Low' in row: existing.low = float(row['Low'])
                if 'Volume' in row: existing.volume = float(row['Volume'])
                existing.adjusted_close = close_val # Assuming YF history is adj close by default or close
            else:
                # Insert
                new_rec = AssetPriceHistory(
                    asset_id=asset_id,
                    date=date_val,
                    close=close_val,
                    open=float(row['Open']) if 'Open' in row else None,
                    high=float(row['High']) if 'High' in row else None,
                    low=float(row['Low']) if 'Low' in row else None,
                    volume=float(row['Volume']) if 'Volume' in row else None,
                    adjusted_close=close_val
                )
                session.add(new_rec)
        except Exception as e:
            continue
    
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Commit failed: {e}")

# Simple in-memory cache for quote API to reduce request rate and avoid bans
# Maps symbol -> (price: float, fetched_ts: float)
_QUOTE_CACHE: Dict[str, tuple] = {}
_QUOTE_TTL_SECONDS = 60.0

# FX series cache to reduce repeated historical downloads (limits Yahoo calls)
# Key: (tuple(sorted(fx_symbols)), str(start_date), str(end_date)) -> (result_dict, fetched_ts)
_FX_SERIES_CACHE: Dict[tuple, tuple] = {}
_FX_SERIES_TTL_SECONDS = 3600.0

# Simple throttle for yfinance calls to mitigate rate-limits/bans
_YF_LAST_CALL_TS = 0.0
_YF_MIN_INTERVAL_SECONDS = 1.0  # minimum spacing between yf requests

def _throttle_yf():
    global _YF_LAST_CALL_TS
    now = time.time()
    wait = _YF_MIN_INTERVAL_SECONDS - (now - _YF_LAST_CALL_TS)
    if wait > 0:
        try:
            time.sleep(wait)
        except Exception:
            pass
    _YF_LAST_CALL_TS = time.time()


@lru_cache(maxsize=2048)
def _resolve_ambiguous_symbol(base: str) -> str:
    """
    Resolve ambiguous short tickers (len<=4) without explicit suffix by probing Yahoo v7 quote API.
    Try common markets: US (no suffix), Warsaw (.WA), London (.L), Frankfurt (.DE) and pick first that returns data.
    """
    base = base.upper()
    # Prioritize Warsaw (.WA) for this environment
    candidates = [f"{base}.WA", base, f"{base}.L", f"{base}.DE"]
    res = _fetch_quotes_batch_via_api(candidates)
    # Pick first candidate that returned a price
    for c in candidates:
        if c in res:
            return c
    # Fallback to base (US)
    return base


def get_yf_symbol(ticker_symbol: str) -> str:
    """Converts a given ticker symbol to the Yahoo Finance format."""
    crypto_map = {
        "BITCOIN": "BTC-USD",
        "ETHEREUM": "ETH-USD",
        "XAUUSD=X": "GC=F", # XAUUSD=X broken in yfinance, use Futures
        "XAUUSD": "GC=F",
    }
    t = ticker_symbol.upper()
    if t in crypto_map:
        return crypto_map[t]
    if t.endswith(".PL"):
        return t.replace(".PL", ".WA")
    if t.endswith(".US"):
        return t.replace(".US", "")
    if t.endswith(".DE"):
        return t  # .DE is correct for Frankfurt
    if t.endswith(".UK"):
        return t.replace(".UK", ".L")  # .L for London
    if t.endswith(".L") or t.endswith(".WA"):
        return t
    # Ambiguous short tickers: resolve via API instead of assuming .WA
    if len(t) <= 4 and t.isupper():
        return _resolve_ambiguous_symbol(t)
    return ticker_symbol


def get_currency_for_ticker(ticker_symbol: str) -> str:
    """Best-effort currency inference from ticker suffixes/maps."""
    t = ticker_symbol.upper()

    # Check environment overrides first
    # Format: "TICKER1:CURRENCY,TICKER2:CURRENCY"
    overrides = os.getenv('CURRENCY_OVERRIDES', '')
    if overrides:
        for entry in overrides.split(','):
            if ':' in entry:
                key, val = entry.split(':')
                if key.strip().upper() == t:
                    return val.strip().upper()

    if t in ("BITCOIN", "ETHEREUM"):
        return "USD"
    if t.endswith(".US"):
        return "USD"
    if t.endswith(".DE"):
        return "EUR"
    # London uses .L
    if t.endswith(".UK") or t.endswith(".L"):
        return "GBP"
    # Warsaw uses .WA (or legacy .PL mapped to .WA)
    if t.endswith(".PL") or t.endswith(".WA"):
        return "PLN"
    # Default: assume US USD when no suffix
    return "USD"


def fx_symbol_to_pln(currency: str) -> str:
    """Map a currency code to the Yahoo Finance FX pair quoted in PLN."""
    mapping = {
        "USD": "USDPLN=X",
        "EUR": "EURPLN=X",
        "GBP": "GBPPLN=X",
    }
    return mapping.get(currency, "")


def _normalize_to_dataframe(close_obj):
    """Ensure the close object is a DataFrame with columns as tickers."""
    if isinstance(close_obj, pd.Series):
        return close_obj.to_frame(name=close_obj.name if isinstance(close_obj.name, str) else "value")
    return close_obj


def _fetch_fx_series(currencies: List[str], start_date, end_date) -> Dict[str, pd.Series]:
    """Fetch FX close series to convert foreign prices to PLN.
    Batched, cached, and without per-symbol fallback to avoid bans.
    """
    fx_needed = [fx_symbol_to_pln(c) for c in currencies if c != "PLN"]
    fx_needed = [s for s in fx_needed if s]

    result: Dict[str, pd.Series] = {}
    if not fx_needed:
        return result

    # Cache key (make args hashable/consistent)
    try:
        key = (tuple(sorted(fx_needed)), str(start_date), str(end_date))
    except Exception:
        key = (tuple(sorted(fx_needed)), repr(start_date), repr(end_date))

    now_ts = time.time()
    cached = _FX_SERIES_CACHE.get(key)
    if cached and (now_ts - cached[1]) < _FX_SERIES_TTL_SECONDS:
        return cached[0]

    # Database Mode: Try DB first
    if _DB_SESSION_FACTORY:
        session = _get_db_session()
        try:
            from backend.database import AssetPriceHistory
            
            missing_in_db = []
            for fx in fx_needed:
                asset = _find_asset_in_db(session, fx)
                found = False
                if asset:
                    history = session.query(AssetPriceHistory)\
                        .filter(AssetPriceHistory.asset_id == asset.id)\
                        .filter(AssetPriceHistory.date >= start_date)\
                        .filter(AssetPriceHistory.date <= end_date)\
                        .order_by(AssetPriceHistory.date.asc())\
                        .all()
                    
                    if history:
                        series = pd.Series(
                            [float(h.close) for h in history],
                            index=pd.to_datetime([h.date for h in history])
                        )
                        result[fx] = series.ffill().bfill()
                        found = True
                
                if not found:
                    missing_in_db.append(fx)
            
            # Update needed list to only fetch missing
            fx_needed = missing_in_db
            
        except Exception as e:
            print(f"DB FX Error: {e}")
        finally:
            if session:
                session.close()

    if not fx_needed:
        # All found in DB or empty request
        _FX_SERIES_CACHE[key] = (result, now_ts)
        return result

    # Single batched download to limit requests (for missing ones)
    try:
        _throttle_yf()
        data = yf.download(fx_needed, start=start_date, end=end_date, progress=False, threads=False)
    except Exception:
        data = pd.DataFrame()

    if data is None or data.empty:
        # Cache empty to avoid hammering on repeated calls
        _FX_SERIES_CACHE[key] = (result, now_ts)
        return result

    # Normalize close
    if "Close" not in data.columns and isinstance(data.columns, pd.MultiIndex):
        close = data["Close"]
    else:
        close = data.get("Close", data)
    close = _normalize_to_dataframe(close)

    for fx in fx_needed:
        try:
            if isinstance(close, pd.DataFrame) and fx in close.columns:
                series = close[fx].ffill().bfill()
                result[fx] = series
            elif isinstance(close, pd.Series) and close.name == fx:
                result[fx] = close.ffill().bfill()
        except Exception:
            continue

    _FX_SERIES_CACHE[key] = (result, now_ts)
    return result


def _fetch_fx_rate_from_db_or_yf(currency: str) -> Optional[float]:
    """Helper to get current FX rate from DB (if available) or YF."""
    if currency == "PLN":
        return 1.0
    
    fx_ticker = fx_symbol_to_pln(currency)
    if not fx_ticker:
        return None

    # Try DB if enabled
    if _DB_SESSION_FACTORY:
        session = _get_db_session()
        try:
            from backend.database import AssetPriceHistory
            
            asset = _find_asset_in_db(session, fx_ticker)
            if asset:
                last = session.query(AssetPriceHistory).filter(AssetPriceHistory.asset_id == asset.id).order_by(AssetPriceHistory.date.desc()).first()
                if last:
                    return float(last.close)
        except Exception:
            pass
        finally:
            if session:
                session.close()
    
    # Fallback to YF (via api batch)
    try:
        api_fx = _fetch_quotes_batch_via_api([fx_ticker])
        return api_fx.get(fx_ticker)
    except Exception:
        return None


@lru_cache(maxsize=1000)
def get_current_price(ticker_symbol: str):
    """Fetches the current price of a ticker, converted to PLN."""
    
    # Database Mode
    if _DB_SESSION_FACTORY:
        session = _get_db_session()
        price = None
        try:
            from backend.database import AssetPriceHistory
            
            asset = _find_asset_in_db(session, ticker_symbol)
            
            if asset:
                last = session.query(AssetPriceHistory).filter(AssetPriceHistory.asset_id == asset.id).order_by(AssetPriceHistory.date.desc()).first()
                if last:
                    price = float(last.close)
        except Exception as e:
            print(f"DB Error for {ticker_symbol}: {e}")
        finally:
            if session:
                session.close()
        
        if price is not None:
             # Handle Currency using resolved asset ticker
            yf_symbol = get_yf_symbol(asset.ticker)
            currency = get_currency_for_ticker(yf_symbol)
            
            if currency != "PLN":
                fx_rate = _fetch_fx_rate_from_db_or_yf(currency)
                if fx_rate:
                    return price * float(fx_rate)
            return price
        
        # If not found in DB, return None (Database mode implies preferring DB)
        # Try Stooq for Polish tickers
        price = None
        if ticker_symbol.endswith('.PL'):
            # Use Stooq
            clean_ticker = ticker_symbol.replace('.PL', '').lower()
            url = f'https://stooq.pl/q/l/?s={clean_ticker}&f=sd2t2ohlcv&h&e=csv'
            try:
                import pandas as pd
                df = pd.read_csv(url)
                if not df.empty and 'Close' in df.columns:
                    price = float(df['Close'].iloc[0])
                    return price
            except Exception:
                pass
        
        # If still no price, try Yahoo Finance as fallback (especially for .PL tickers)
        if price is None:
            yf_symbol = get_yf_symbol(ticker_symbol)
            try:
                api_res = _fetch_quotes_batch_via_api([yf_symbol])
                if yf_symbol in api_res:
                    price = api_res[yf_symbol]
                    # Convert to PLN if needed (YF returns price in original currency)
                    currency = get_currency_for_ticker(yf_symbol)
                    if currency != "PLN":
                        fx_rate = _fetch_fx_rate_from_db_or_yf(currency)
                        if fx_rate:
                            price = price * float(fx_rate)
                    return price
            except Exception:
                pass
        
        return price

    # Non-database mode
    # For Polish tickers, try Stooq first
    if ticker_symbol.endswith('.PL'):
        clean_ticker = ticker_symbol.replace('.PL', '').lower()
        url = f'https://stooq.pl/q/l/?s={clean_ticker}&f=sd2t2ohlcv&h&e=csv'
        try:
            import pandas as pd
            df = pd.read_csv(url)
            if not df.empty and 'Close' in df.columns:
                price = float(df['Close'].iloc[0])
                return price
        except Exception:
            pass

    yf_symbol = get_yf_symbol(ticker_symbol)
    currency = get_currency_for_ticker(yf_symbol)
    
    price = None
    
    # 1. Try lightweight API first (avoids yf.Ticker initialization overhead and frequent bans)
    try:
        api_res = _fetch_quotes_batch_via_api([yf_symbol])
        if yf_symbol in api_res:
            price = api_res[yf_symbol]
    except Exception:
        pass

    # 2. Fallback disabled to avoid yfinance bans; if API failed, leave as None
    # (we prefer missing data over triggering rate limits)
            
    # 3. Raw symbol fallback disabled (same reason as above)

    if price is None:
        return None

    # Convert to PLN if needed (FX via quote API only; avoid yfinance history endpoints)
    if currency != "PLN":
        fx_ticker = fx_symbol_to_pln(currency)
        if fx_ticker:
            try:
                api_fx = _fetch_quotes_batch_via_api([fx_ticker])
                fx_price = api_fx.get(fx_ticker)
                if fx_price:
                    return float(price) * float(fx_price)
            except Exception:
                pass
                
    return float(price)


def _fetch_quotes_batch_via_api(yf_symbols: List[str]) -> Dict[str, float]:
    """
    Attempts to fetch current prices using Yahoo Finance.
    Falls back to yf.download since v7 quote API requires authentication.
    Returns {yf_symbol: price}.
    """
    results = {}
    
    # Use TTL cache to avoid hammering API repeatedly
    now_ts = time.time()
    pending: List[str] = []
    for s in yf_symbols:
        cached = _QUOTE_CACHE.get(s)
        if cached and (now_ts - cached[1]) < _QUOTE_TTL_SECONDS:
            results[s] = cached[0]
        else:
            pending.append(s)
    
    if not pending:
        return results

    # Deduplicate pending
    pending = list(set(pending))
    
    try:
        # Use threads=False to avoid issues, progress=False
        # period="5d" to catch last close
        _throttle_yf()
        # Suppress FutureWarnings from yfinance if possible, or just ignore
        df = yf.download(pending, period="5d", progress=False, threads=False)
        
        if df is not None and not df.empty:
            # Normalize to get Close prices
            close_df = None
            if "Close" in df.columns:
                close_df = df["Close"]
            elif "Adj Close" in df.columns:
                close_df = df["Adj Close"]
            else:
                # Fallback if single column or different structure
                close_df = df
            
            # Extract prices
            if isinstance(close_df, pd.Series):
                 # Single symbol result
                 val = close_df.dropna()
                 if not val.empty:
                     price = float(val.iloc[-1])
                     # We need to know WHICH symbol this is.
                     sym = close_df.name
                     if sym in pending:
                         results[sym] = price
                         _QUOTE_CACHE[sym] = (price, now_ts)
                     elif len(pending) == 1:
                         results[pending[0]] = price
                         _QUOTE_CACHE[pending[0]] = (price, now_ts)
            elif isinstance(close_df, pd.DataFrame):
                 for col in close_df.columns:
                     series = close_df[col].dropna()
                     if not series.empty:
                         price = float(series.iloc[-1])
                         results[col] = price
                         _QUOTE_CACHE[col] = (price, now_ts)
                         
    except Exception as e:
        print(f"Batch fetch failed: {e}")
        pass
            
    return results

def get_current_prices(tickers: List[str]) -> Dict[str, float]:
    """
    Fetches current prices for a list of tickers in batch, converted to PLN.
    It returns a dictionary {ticker: price_in_pln}.
    Tickers that fail to fetch are omitted from the result.
    """
    if not tickers:
        return {}
        
    # Database Mode
    if _DB_SESSION_FACTORY:
        results = {}
        for t in tickers:
            p = get_current_price(t)
            if p is not None:
                results[t] = p
        return results

    # Deduplicate
    tickers = list(set(tickers))
    
    # 1. Prepare symbols
    yf_symbols_map = {t: get_yf_symbol(t) for t in tickers}
    yf_symbols = list(set(yf_symbols_map.values()))
    
    raw_prices = {} 
    
    # Try efficient API batch first (reduces HTTP calls from N to 1 per chunk)
    try:
        api_results = _fetch_quotes_batch_via_api(yf_symbols)
        if api_results:
            # Map back to original tickers
            for t in tickers:
                sym = yf_symbols_map[t]
                if sym in api_results:
                    raw_prices[t] = api_results[sym]
    except Exception:
        pass
    
    # If API batch missed many, or failed, we might use yf.download but it's risky for bans.
    # Only try yf.download for tickers we don't have yet.
    missing_symbols = [yf_symbols_map[t] for t in tickers if t not in raw_prices]
    missing_symbols = list(set(missing_symbols))
    
    # Single batch fallback via yfinance for still-missing symbols (throttled)
    if missing_symbols:
        try:
            _throttle_yf()
            data = yf.download(missing_symbols, period="5d", progress=False, threads=False)
            if data is not None and not data.empty:
                closes = data["Close"] if "Close" in data.columns else data
                # Normalize shape
                if isinstance(closes, pd.Series) and len(missing_symbols) == 1:
                    closes = closes.to_frame(name=missing_symbols[0])
                closes = _normalize_to_dataframe(closes)
                
                for sym in missing_symbols:
                    series = None
                    if isinstance(closes, pd.DataFrame) and sym in closes.columns:
                        series = closes[sym].dropna()
                    elif isinstance(closes, pd.Series) and closes.name == sym:
                        series = closes.dropna()
                    if series is not None and not series.empty:
                        price = float(series.iloc[-1])
                        # Assign back to all original tickers mapped to this sym
                        for orig_t, mapped_s in yf_symbols_map.items():
                            if mapped_s == sym:
                                raw_prices[orig_t] = price
        except Exception:
            # If fallback fails, we leave symbols missing
            pass
        
    final_prices = {}
    
    # Prepare FX
    tickers_needing_fx = [t for t in raw_prices.keys() if get_currency_for_ticker(t) != "PLN"]
    fx_rates = {}
    
    if tickers_needing_fx:
        currencies = sorted({get_currency_for_ticker(t) for t in tickers_needing_fx})
        fx_symbols = [fx_symbol_to_pln(c) for c in currencies]
        fx_symbols = [s for s in fx_symbols if s]
        
        if fx_symbols:
            try:
                # Use v7 quote API for FX to avoid yfinance timezone/history calls
                fx_api = _fetch_quotes_batch_via_api(fx_symbols)
                for c in currencies:
                    sym = fx_symbol_to_pln(c)
                    if sym and sym in fx_api:
                        fx_rates[c] = float(fx_api[sym])
            except Exception:
                pass
    
    # Convert raw prices
    for t, p in raw_prices.items():
        curr = get_currency_for_ticker(t)
        if curr == "PLN":
            final_prices[t] = p
        else:
            rate = fx_rates.get(curr)
            if rate:
                final_prices[t] = p * rate
            else:
                final_prices[t] = p
                
    return final_prices


def get_price_history_from_stooq(ticker_symbol: str, days: int = 90):
    """Fetch price history from Stooq for Polish stocks (removes .WA suffix)."""
    # Stooq uses lowercase usually, and no .WA suffix
    clean_ticker = ticker_symbol.replace('.WA', '').lower()
    url = f"https://stooq.pl/q/d/l/?s={clean_ticker}&i=d"
    
    try:
        # Use pandas to read CSV directly
        df = pd.read_csv(url)
        
        if df.empty or "Date" not in df.columns:
            return []

        df["Date"] = pd.to_datetime(df["Date"])
        start_date = pd.Timestamp.now() - pd.Timedelta(days=days)
        df = df[df["Date"] >= start_date]
        
        price_data = []
        for _, row in df.iterrows():
            try:
                price_data.append({
                    "date": row["Date"].strftime("%Y-%m-%d"),
                    "price": float(row["Close"]),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(row["Volume"])
                })
            except (ValueError, TypeError):
                continue
                
        return price_data
    except Exception as e:
        print(f"Stooq download failed for {clean_ticker}: {e}")
        return []

def get_price_history(ticker_symbol: str, days: int = 90):
    """Fetches the price history of a ticker, converted to PLN.

    Robust fallbacks:
    - If the requested period is empty, try a longer window via yf.download
    - If still empty, try the full history (period='max')
    """
    
    # Database Mode or Caching Mode
    forced_session = _get_db_session()
    session = forced_session if forced_session else _get_caching_session()
    is_caching_mode = (session is not None and forced_session is None)
    
    if session:
        price_data = []
        try:
            from backend.database import AssetPriceHistory
            
            # In caching mode, we ensure asset exists. In forced mode, we just look for it.
            asset = None
            if is_caching_mode:
                asset = _get_or_create_asset(session, ticker_symbol)
            else:
                asset = _find_asset_in_db(session, ticker_symbol)
            
            if asset:
                start_date = pd.Timestamp.now().date() - pd.Timedelta(days=days)
                
                # Check for sync need (only in Caching Mode)
                if is_caching_mode:
                    last_entry = session.query(AssetPriceHistory)\
                        .filter(AssetPriceHistory.asset_id == asset.id)\
                        .order_by(AssetPriceHistory.date.desc()).first()
                    
                    need_fetch = False
                    if not last_entry:
                        need_fetch = True
                    else:
                        # If data is older than yesterday, fetch
                        if last_entry.date < (datetime.now().date() - pd.Timedelta(days=1)):
                            need_fetch = True
                        # Also check if we have enough history (start_date)
                        first_entry = session.query(AssetPriceHistory)\
                            .filter(AssetPriceHistory.asset_id == asset.id)\
                            .order_by(AssetPriceHistory.date.asc()).first()
                        if first_entry and first_entry.date > start_date + pd.Timedelta(days=5):
                            # We might have gaps at the beginning, but simpler to just fetch if we need older data
                            need_fetch = True
                            
                    if need_fetch:
                        yf_symbol = get_yf_symbol(ticker_symbol)
                        # Fetch df using internal logic (duplicated slightly to get DF)
                        try:
                            _throttle_yf()
                            ticker = yf.Ticker(yf_symbol)
                            df = ticker.history(period=f"{days}d")
                            if df is None or df.empty:
                                try:
                                    longer = max(180, days * 2)
                                    _throttle_yf()
                                    alt = yf.download(yf_symbol, period=f"{longer}d", progress=False, threads=False)
                                    if alt is not None and not alt.empty:
                                        df = alt
                                except Exception:
                                    pass
                            
                            if df is not None and not df.empty:
                                _save_history_to_db(session, asset.id, df)
                        except Exception as e:
                            print(f"Caching fetch failed: {e}")

                history = session.query(AssetPriceHistory)\
                    .filter(AssetPriceHistory.asset_id == asset.id)\
                    .filter(AssetPriceHistory.date >= start_date)\
                    .order_by(AssetPriceHistory.date.asc())\
                    .all()
                
                # Convert to PLN if needed
                yf_symbol = get_yf_symbol(asset.ticker)
                currency = get_currency_for_ticker(yf_symbol)
                
                # TODO: Handle currency conversion for history in DB mode
                # Currently returning raw prices or 1:1 if currency mismatch
                
                for h in history:
                    price_data.append({
                        "date": h.date.strftime("%Y-%m-%d"),
                        "price": float(h.close),
                        "open": float(h.open) if h.open is not None else float(h.close),
                        "high": float(h.high) if h.high is not None else float(h.close),
                        "low": float(h.low) if h.low is not None else float(h.close),
                        "close": float(h.close),
                        "volume": int(h.volume) if h.volume else 0
                    })
                
                if price_data:
                    return price_data
                    
        except Exception as e:
            print(f"DB History Error: {e}")
        finally:
            if session:
                session.close()
        
        # If forced DB and failed, return empty
        if forced_session:
            return price_data

    yf_symbol = get_yf_symbol(ticker_symbol)
    currency = 'PLN' #get_currency_for_ticker(yf_symbol)
    
    # Use Stooq for Polish tickers
    # if yf_symbol.endswith(".WA"):
    stooq_data = get_price_history_from_stooq(yf_symbol, days)
    if stooq_data:
        return stooq_data

    try:
        _throttle_yf()
        ticker = yf.Ticker(yf_symbol)
        # Primary fetch
        _throttle_yf()
        hist = ticker.history(period=f"{days}d")

        # Fallback 1: try a longer period using yf.download (some symbols behave better here)
        if hist is None or hist.empty:
            try:
                longer = max(180, days * 2)
                _throttle_yf()
                alt = yf.download(yf_symbol, period=f"{longer}d", progress=False, threads=False)
                if alt is not None and not alt.empty:
                    hist = alt
            except Exception:
                pass

        # Fallback 2: try full available history
        if hist is None or hist.empty:
            try:
                _throttle_yf()
                alt = ticker.history(period="max")
                if alt is not None and not alt.empty:
                    hist = alt
            except Exception:
                pass

        if hist is None or hist.empty:
            return []

        # Choose a close-like series
        if "Close" in hist.columns:
            series = hist["Close"].copy()
        elif "Adj Close" in hist.columns:
            series = hist["Adj Close"].copy()
        else:
            # Fall back to the first numeric column
            series = hist.select_dtypes(include="number").iloc[:, 0].copy()

        # Convert to PLN if needed
        fx_series = None
        if currency != "PLN":
            fx_ticker = fx_symbol_to_pln(currency)
            if fx_ticker:
                try:
                    _throttle_yf()
                    fx_hist = yf.Ticker(fx_ticker).history(period=f"{max(180, days)}d")
                    if not fx_hist.empty:
                        fx_col = "Close" if "Close" in fx_hist.columns else ("Adj Close" if "Adj Close" in fx_hist.columns else None)
                        if fx_col:
                            # Normalize TZs to ensure alignment
                            if series.index.tz is not None:
                                series.index = series.index.tz_localize(None)
                            if fx_hist.index.tz is not None:
                                fx_hist.index = fx_hist.index.tz_localize(None)
                                
                            fx_series = fx_hist[fx_col].reindex(series.index).ffill().bfill()
                            series = series * fx_series
                except Exception:
                    # If FX fails, return native currency series (better than empty)
                    pass
        
        # Apply FX to OHLC if needed
        if fx_series is not None:
             for col in ["Open", "High", "Low", "Close"]:
                 if col in hist.columns:
                     # Reindex fx_series to match hist index just in case
                     aligned_fx = fx_series.reindex(hist.index).ffill().bfill()
                     hist[col] = hist[col] * aligned_fx

        price_data = []
        for date, value in series.items():
            # Get OHLC values
            o = float(hist.loc[date]["Open"]) if "Open" in hist.columns else float(value)
            h = float(hist.loc[date]["High"]) if "High" in hist.columns else float(value)
            l = float(hist.loc[date]["Low"]) if "Low" in hist.columns else float(value)
            c = float(hist.loc[date]["Close"]) if "Close" in hist.columns else float(value)
            
            price_data.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "price": float(value),
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": int(hist.loc[date]["Volume"]) if "Volume" in hist.columns else 0,
                }
            )
        return price_data
    except Exception:
        return []


@lru_cache(maxsize=16)
def _get_historical_prices_cached(tickers_tuple, start_date, end_date):
    """Cached implementation of get_historical_prices_for_tickers."""
    tickers = list(tickers_tuple)
    yf_symbols = [get_yf_symbol(t) for t in tickers]
    
    # Prepare FX conversion series upfront
    # Use yf_symbol for currency detection to correctly handle resolved ambiguous tickers (e.g. SNT -> SNT.WA -> PLN)
    currency_by_ticker: Dict[str, str] = {}
    for t, yf_sym in zip(tickers, yf_symbols):
        currency_by_ticker[t] = get_currency_for_ticker(yf_sym)

    unique_currencies = sorted({c for c in currency_by_ticker.values() if c != "PLN"})
    fx_series_map = _fetch_fx_series(unique_currencies, start_date, end_date)
    
    price_dict = {}

    # Helper to process a series
    def process_series(ticker, series):
        if series is None or series.empty:
            return

        # Ensure we have a Series, not a DataFrame (e.g. if duplicate cols)
        if isinstance(series, pd.DataFrame):
            # Take the first column if duplicates exist
            series = series.iloc[:, 0]
            
        series = series.ffill().bfill()
        
        currency = currency_by_ticker.get(ticker, "PLN")
        if currency != "PLN":
            fx_ticker = fx_symbol_to_pln(currency)
            fx_series = fx_series_map.get(fx_ticker)
            if fx_series is not None and not fx_series.empty:
                aligned_fx = fx_series.reindex(series.index).ffill().bfill()
                series = series * aligned_fx
        
        price_dict[ticker] = series.to_dict()

    # Try batch download first
    try:
        # Use threads=False to prevent bans
        _throttle_yf()
        data = yf.download(yf_symbols, start=start_date, end=end_date, progress=False, threads=False)
        
        if not data.empty:
            prices = data["Close"]
            prices = _normalize_to_dataframe(prices)

            for ticker, yf_symbol in zip(tickers, yf_symbols):
                series = None
                if yf_symbol in prices.columns:
                    series = prices[yf_symbol].copy()
                elif isinstance(prices, pd.Series) and prices.name == yf_symbol:
                    series = prices.copy()
                
                if series is not None and not series.dropna().empty:
                     process_series(ticker, series)
    except Exception as e:
        print(f"Batch download failed: {e}")

    return price_dict

def get_historical_prices_for_tickers(tickers, start_date, end_date, session: Optional[Session] = None):
    """
    Fetches historical daily closing prices for a list of tickers in a given date range.
    All prices are converted to PLN using historical FX rates.
    Wrapper to allow caching on tuple arguments.
    """
    if session or _DB_SESSION_FACTORY:
        # DB Mode Implementation
        db_session = session if session else _get_db_session()
        result = {}
        if not db_session:
            return result
        
        should_close = (session is None)
        
        try:
            from backend.database import AssetPriceHistory
            
            # Resolve assets
            ticker_to_asset = {}
            
            for ticker in tickers:
                asset = _find_asset_in_db(db_session, ticker)
                if asset:
                    ticker_to_asset[ticker] = asset

            for ticker, asset in ticker_to_asset.items():
                history = db_session.query(AssetPriceHistory)\
                    .filter(AssetPriceHistory.asset_id == asset.id)\
                    .filter(AssetPriceHistory.date >= start_date)\
                    .filter(AssetPriceHistory.date <= end_date)\
                    .order_by(AssetPriceHistory.date.asc())\
                    .all()
                    
                if not history:
                    continue
                    
                series = pd.Series(
                    [float(h.close) for h in history],
                    index=pd.to_datetime([h.date for h in history])
                )
                
                # NO FX Conversion when using DB prices (assumed to be already in PLN per requirements)
                
                result[ticker] = series.to_dict()
                
        except Exception as e:
            print(f"DB Batch History Error: {e}")
        finally:
            if should_close and db_session:
                db_session.close()
        return result

    return _get_historical_prices_cached(tuple(tickers), start_date, end_date)


def get_ohlc_history_df(ticker_symbol: str, days: int = 365) -> pd.DataFrame:
    """
    Fetches OHLC history as DataFrame.
    Used for technical analysis.
    """
    # Database Mode or Caching Mode
    forced_session = _get_db_session()
    session = forced_session if forced_session else _get_caching_session()
    is_caching_mode = (session is not None and forced_session is None)

    if session:
        try:
            from backend.database import AssetPriceHistory
            
            asset = None
            if is_caching_mode:
                asset = _get_or_create_asset(session, ticker_symbol)
            else:
                asset = _find_asset_in_db(session, ticker_symbol)
                
            if asset:
                 start_date = pd.Timestamp.now().date() - pd.Timedelta(days=days)
                 
                 # Check sync need (Caching Mode)
                 if is_caching_mode:
                    last_entry = session.query(AssetPriceHistory)\
                        .filter(AssetPriceHistory.asset_id == asset.id)\
                        .order_by(AssetPriceHistory.date.desc()).first()
                    
                    need_fetch = False
                    if not last_entry:
                        need_fetch = True
                    elif last_entry.date < (datetime.now().date() - pd.Timedelta(days=1)):
                        need_fetch = True
                    
                    if need_fetch:
                        yf_symbol = get_yf_symbol(ticker_symbol)
                        try:
                            _throttle_yf()
                            ticker = yf.Ticker(yf_symbol)
                            df = ticker.history(period=f"{days}d")
                            # Fallbacks
                            if df is None or df.empty:
                                try:
                                    longer = max(180, days * 2)
                                    _throttle_yf()
                                    alt = yf.download(yf_symbol, period=f"{longer}d", progress=False, threads=False)
                                    if alt is not None and not alt.empty:
                                        df = alt
                                except Exception:
                                    pass
                            
                            if df is not None and not df.empty:
                                _save_history_to_db(session, asset.id, df)
                        except Exception as e:
                            print(f"Caching fetch failed: {e}")

                 history = session.query(AssetPriceHistory)\
                    .filter(AssetPriceHistory.asset_id == asset.id)\
                    .filter(AssetPriceHistory.date >= start_date)\
                    .order_by(AssetPriceHistory.date.asc())\
                    .all()
                 
                 if not history:
                     if forced_session:
                         return pd.DataFrame()
                     # If caching mode and still no history, fall through to online
                 else:
                     data = []
                     for h in history:
                         data.append({
                             "Date": pd.to_datetime(h.date),
                             "Open": float(h.open) if h.open is not None else float(h.close),
                             "High": float(h.high) if h.high is not None else float(h.close),
                             "Low": float(h.low) if h.low is not None else float(h.close),
                             "Close": float(h.close),
                             "Volume": int(h.volume) if h.volume is not None else 0
                         })
                     df = pd.DataFrame(data)
                     df.set_index("Date", inplace=True)
                     return df
        except Exception as e:
            print(f"DB OHLC Error: {e}")
        finally:
            if session:
                session.close()
        
        if forced_session:
            return pd.DataFrame()

    # Online Mode
    yf_symbol = get_yf_symbol(ticker_symbol)
    try:
        _throttle_yf()
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=f"{days}d")
        
        if df is None or df.empty:
             try:
                longer = max(180, days * 2)
                _throttle_yf()
                alt = yf.download(yf_symbol, period=f"{longer}d", progress=False, threads=False)
                if alt is not None and not alt.empty:
                    # Filter to requested days
                    start_ts = pd.Timestamp.now() - pd.Timedelta(days=days)
                    df = alt[alt.index >= start_ts]
             except Exception:
                pass

        if df is None or df.empty:
            try:
                _throttle_yf()
                alt = ticker.history(period="max")
                if alt is not None and not alt.empty:
                     start_ts = pd.Timestamp.now() - pd.Timedelta(days=days)
                     df = alt[alt.index >= start_ts]
            except Exception:
                pass
                
        return df if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def get_fx_rate_for_date(currency: str, date_obj) -> float:
    """
    Fetches the FX rate (Currency -> PLN) for a specific date.
    Returns 1.0 if currency is PLN or failed to fetch.
    """
    if currency == 'PLN':
        return 1.0
        
    fx_ticker = fx_symbol_to_pln(currency)
    if not fx_ticker:
        return 1.0
        
    # Try fetching history for that date
    try:
        # Fetch a small window around the date to ensure we get a close price
        start = pd.Timestamp(date_obj) - pd.Timedelta(days=5)
        end = pd.Timestamp(date_obj) + pd.Timedelta(days=1)
        
        # We can use _fetch_fx_series but it returns a dict of series
        series_map = _fetch_fx_series([currency], start, end)
        if fx_ticker in series_map:
            series = series_map[fx_ticker]
            # Get the rate on or before the date
            if not series.empty:
                # Series index is Timestamp
                idx = series.index[series.index <= pd.Timestamp(date_obj)]
                if not idx.empty:
                    return float(series.loc[idx.max()])
    except Exception as e:
        print(f"Error fetching FX rate for {currency} on {date_obj}: {e}")
        
    return 1.0


def get_dividends_for_tickers(tickers, start_date, end_date):
    """
    Fetches dividend-per-share series for given tickers between dates, converted to PLN.
    Uses batch download to minimize API calls.

    Returns:
        Dict[str, pd.Series] where index are dates (Timestamp at date-resolution) and values are dividend-per-share in PLN.
    """
    if not tickers:
        return {}
    
    # In DB Mode, we probably don't have dividends in DB.
    # So we continue to use YF or return empty?
    # Returning empty avoids YF calls if we want to be "offline".
    # But current request is "replace price fetching".
    # If I leave it as is, it uses YF.
    # Given the constraint, I'll let it use YF but maybe throttle/check if enabled?
    # Let's leave it as is for now.
    
    tickers = list(set(tickers))

    # Map tickers to yf symbols
    yf_map = {t: get_yf_symbol(t) for t in tickers}

    # Prepare FX conversion series upfront
    # Use yf_symbol for currency detection
    currency_by_ticker: Dict[str, str] = {}
    for t, yf_sym in yf_map.items():
        currency_by_ticker[t] = get_currency_for_ticker(yf_sym)

    unique_currencies = sorted({c for c in currency_by_ticker.values() if c != "PLN"})
    fx_series_map = _fetch_fx_series(unique_currencies, start_date, end_date) if unique_currencies else {}

    result: Dict[str, pd.Series] = {}
    yf_symbols = list(set(yf_map.values()))
    
    # 1. Batch download
    try:
        # Use threads=False to avoid launching N parallel requests which triggers bans
        # yf.download by default uses threads=True (multiprocessing).
        _throttle_yf()
        data = yf.download(yf_symbols, start=start_date, end=end_date, actions=True, progress=False, threads=False)
        
        dividends_df = None
        
        if not data.empty:
            # Check for Dividends column
            # Case 1: MultiIndex (Price, Ticker) - typical for multiple tickers
            if isinstance(data.columns, pd.MultiIndex):
                if "Dividends" in data.columns.get_level_values(0):
                    dividends_df = data["Dividends"]
            # Case 2: Single Index - typical for single ticker (columns are Price types)
            elif "Dividends" in data.columns:
                # If single ticker, it might not have ticker name in columns if we passed list of length 1
                # But if we passed list of length 1, yf.download usually returns DataFrame with columns Open, Close...
                # We need to map it to the ticker
                if len(yf_symbols) == 1:
                    dividends_df = data["Dividends"].to_frame(name=yf_symbols[0])
                else:
                    dividends_df = data["Dividends"]

        if dividends_df is not None:
            # Iterate over requested tickers and extract from dividends_df
            for ticker in tickers:
                sym = yf_map[ticker]
                
                series = None
                if sym in dividends_df.columns:
                    series = dividends_df[sym]
                elif isinstance(dividends_df, pd.Series) and dividends_df.name == sym:
                     series = dividends_df
                
                if series is not None:
                    # Filter out zeros (yf.download returns 0.0 for non-dividend days)
                    series = series[series > 0]
                    
                    if not series.empty:
                        # Normalize index
                        series.index = pd.to_datetime([pd.Timestamp(d).date() for d in series.index])
                        
                        # Convert to PLN
                        curr = currency_by_ticker.get(ticker, "PLN")
                        if curr != "PLN":
                            fx_ticker = fx_symbol_to_pln(curr)
                            fx_series = fx_series_map.get(fx_ticker)
                            if fx_series is not None and not fx_series.empty:
                                aligned_fx = fx_series.reindex(series.index).ffill().bfill()
                                series = series * aligned_fx
                        
                        result[ticker] = series.astype(float)
                        
    except Exception as e:
        print(f"Batch dividend download failed: {e}")

    return result

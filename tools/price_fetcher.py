"""Utility functions for fetching financial market data with PLN normalization."""
import yfinance as yf
from functools import lru_cache
import pandas as pd
from typing import Dict, List
import requests
import time

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

    # Single batched download to limit requests
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


@lru_cache(maxsize=1000)
def get_current_price(ticker_symbol: str):
    """Fetches the current price of a ticker from Yahoo Finance, converted to PLN."""
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
        if currency != "PLN":
            fx_ticker = fx_symbol_to_pln(currency)
            if fx_ticker:
                try:
                    _throttle_yf()
                    fx_hist = yf.Ticker(fx_ticker).history(period=f"{max(180, days)}d")
                    if not fx_hist.empty:
                        fx_col = "Close" if "Close" in fx_hist.columns else ("Adj Close" if "Adj Close" in fx_hist.columns else None)
                        if fx_col:
                            fx_series = fx_hist[fx_col].reindex(series.index).ffill().bfill()
                            series = series * fx_series
                except Exception:
                    # If FX fails, return native currency series (better than empty)
                    pass

        price_data = []
        for date, value in series.items():
            price_data.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "price": float(value),
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

    # Fallback for missing tickers disabled to prevent bans
    # for ticker, yf_symbol in zip(tickers, yf_symbols):
    #     if ticker not in price_dict:
    #         try:
    #             # Download individual
    #             single = yf.download(yf_symbol, start=start_date, end=end_date, progress=False)
    #             if not single.empty and "Close" in single.columns:
    #                  process_series(ticker, single["Close"])
    #         except Exception:
    #             pass
    
    return price_dict

def get_historical_prices_for_tickers(tickers, start_date, end_date):
    """
    Fetches historical daily closing prices for a list of tickers in a given date range.
    All prices are converted to PLN using historical FX rates.
    Wrapper to allow caching on tuple arguments.
    """
    return _get_historical_prices_cached(tuple(tickers), start_date, end_date)


def get_dividends_for_tickers(tickers, start_date, end_date):
    """
    Fetches dividend-per-share series for given tickers between dates, converted to PLN.
    Uses batch download to minimize API calls.

    Returns:
        Dict[str, pd.Series] where index are dates (Timestamp at date-resolution) and values are dividend-per-share in PLN.
    """
    if not tickers:
        return {}
    
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

    # 2. Fallback for missing tickers disabled to prevent bans
    # If batch download fails, do not retry individually.
    
    return result

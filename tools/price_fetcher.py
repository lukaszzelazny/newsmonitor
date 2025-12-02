"""Utility functions for fetching financial market data with PLN normalization."""
import yfinance as yf
from functools import lru_cache
import pandas as pd
from typing import Dict, List


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
    if len(t) <= 4 and t.isupper():
        # Assume Warsaw
        return f"{t}.WA"
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
    if t.endswith(".UK"):
        return "GBP"
    if t.endswith(".PL") or len(t) <= 4:
        return "PLN"
    # Fallback to PLN
    return "PLN"


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
    """Fetch FX close series to convert foreign prices to PLN."""
    fx_needed = [fx_symbol_to_pln(c) for c in currencies if c != "PLN"]
    fx_needed = [s for s in fx_needed if s]

    result: Dict[str, pd.Series] = {}
    if not fx_needed:
        return result

    data = yf.download(fx_needed, start=start_date, end=end_date, progress=False)
    if data.empty:
        # Try individual fallback to be resilient
        for fx in fx_needed:
            try:
                s = yf.download(fx, start=start_date, end=end_date, progress=False)["Close"]
                if not s.empty:
                    result[fx] = s.ffill().bfill()
            except Exception:
                continue
        return result

    close = data["Close"]
    close = _normalize_to_dataframe(close)

    for fx in fx_needed:
        if fx in close.columns:
            series = close[fx].ffill().bfill()
            result[fx] = series
        elif isinstance(close, pd.Series) and close.name == fx:
            result[fx] = close.ffill().bfill()

    return result


@lru_cache(maxsize=1000)
def get_current_price(ticker_symbol: str):
    """Fetches the current price of a ticker from Yahoo Finance, converted to PLN."""
    yf_symbol = get_yf_symbol(ticker_symbol)
    currency = get_currency_for_ticker(ticker_symbol)
    try:
        ticker = yf.Ticker(yf_symbol)
        info = getattr(ticker, "info", {}) or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        if not price:
            hist = ticker.history(period="5d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
            else:
                price = None
        if price is None:
            return None

        # Convert to PLN if needed
        if currency != "PLN":
            fx_ticker = fx_symbol_to_pln(currency)
            if fx_ticker:
                try:
                    fx_hist = yf.Ticker(fx_ticker).history(period="10d")
                    if not fx_hist.empty:
                        fx_rate = float(fx_hist["Close"].dropna().iloc[-1])
                        return float(price) * fx_rate
                except Exception:
                    pass
        return float(price)
    except Exception:
        # Fallback: try raw symbol without mapping
        try:
            ticker = yf.Ticker(ticker_symbol)
            info = getattr(ticker, "info", {}) or {}
            price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
            if price is None:
                return None
            if get_currency_for_ticker(ticker_symbol) != "PLN":
                fx_ticker = fx_symbol_to_pln(get_currency_for_ticker(ticker_symbol))
                if fx_ticker:
                    fx_hist = yf.Ticker(fx_ticker).history(period="10d")
                    if not fx_hist.empty:
                        fx_rate = float(fx_hist["Close"].dropna().iloc[-1])
                        return float(price) * fx_rate
            return float(price)
        except Exception:
            return None


def get_price_history(ticker_symbol: str, days: int = 90):
    """Fetches the price history of a ticker, converted to PLN.

    Robust fallbacks:
    - If the requested period is empty, try a longer window via yf.download
    - If still empty, try the full history (period='max')
    """
    yf_symbol = get_yf_symbol(ticker_symbol)
    currency = get_currency_for_ticker(ticker_symbol)
    try:
        ticker = yf.Ticker(yf_symbol)
        print('check ticker')
        print(ticker.info)
        # Primary fetch
        hist = ticker.history(period=f"{days}d")

        # Fallback 1: try a longer period using yf.download (some symbols behave better here)
        if hist is None or hist.empty:
            try:
                longer = max(180, days * 2)
                alt = yf.download(yf_symbol, period=f"{longer}d", progress=False)
                if alt is not None and not alt.empty:
                    hist = alt
            except Exception:
                pass

        # Fallback 2: try full available history
        if hist is None or hist.empty:
            try:
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
    currency_by_ticker: Dict[str, str] = {t: get_currency_for_ticker(t) for t in tickers}
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
        data = yf.download(yf_symbols, start=start_date, end=end_date, progress=False)
        
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

    # Fallback for missing tickers
    for ticker, yf_symbol in zip(tickers, yf_symbols):
        if ticker not in price_dict:
            try:
                # Download individual
                single = yf.download(yf_symbol, start=start_date, end=end_date, progress=False)
                if not single.empty and "Close" in single.columns:
                     process_series(ticker, single["Close"])
            except Exception:
                pass
    
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

    Returns:
        Dict[str, pd.Series] where index are dates (Timestamp at date-resolution) and values are dividend-per-share in PLN.
    """
    if not tickers:
        return {}

    # Prepare FX conversion series upfront
    currency_by_ticker: Dict[str, str] = {t: get_currency_for_ticker(t) for t in tickers}
    unique_currencies = sorted({c for c in currency_by_ticker.values() if c != "PLN"})
    fx_series_map = _fetch_fx_series(unique_currencies, start_date, end_date) if unique_currencies else {}

    result: Dict[str, pd.Series] = {}
    for ticker in tickers:
        try:
            yf_symbol = get_yf_symbol(ticker)
            t = yf.Ticker(yf_symbol)
            div = t.dividends  # Series indexed by Timestamp, values in native currency per share
            if div is None or len(div) == 0:
                continue

            # Filter date range (inclusive)
            s = div[(div.index.date >= start_date) & (div.index.date <= end_date)]
            if s is None or s.empty:
                continue

            # Normalize index to date (no time)
            s.index = pd.to_datetime([pd.Timestamp(d).date() for d in s.index])

            # Convert to PLN if needed
            curr = currency_by_ticker.get(ticker, "PLN")
            if curr != "PLN":
                fx_ticker = fx_symbol_to_pln(curr)
                fx_series = fx_series_map.get(fx_ticker)
                if fx_series is not None and not fx_series.empty:
                    # Align by date and multiply
                    aligned_fx = fx_series.reindex(s.index).ffill().bfill()
                    s = s * aligned_fx

            # Ensure float
            s = s.astype(float)
            result[ticker] = s
        except Exception:
            continue

    return result

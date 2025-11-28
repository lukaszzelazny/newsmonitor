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


def get_historical_prices_for_tickers(tickers, start_date, end_date):
    """
    Fetches historical daily closing prices for a list of tickers in a given date range.
    All prices are converted to PLN using historical FX rates.
    """
    yf_symbols = [get_yf_symbol(t) for t in tickers]
    try:
        data = yf.download(yf_symbols, start=start_date, end=end_date, progress=False)
        if data.empty:
            return {}

        prices = data["Close"]
        prices = _normalize_to_dataframe(prices)

        # Prepare FX conversion series
        currency_by_ticker: Dict[str, str] = {t: get_currency_for_ticker(t) for t in tickers}
        unique_currencies = sorted({c for c in currency_by_ticker.values() if c != "PLN"})
        fx_series_map = _fetch_fx_series(unique_currencies, start_date, end_date)

        price_dict = {}
        for ticker, yf_symbol in zip(tickers, yf_symbols):
            if yf_symbol not in prices.columns and isinstance(prices, pd.Series) and prices.name == yf_symbol:
                ticker_series = prices.copy()
            elif yf_symbol in prices.columns:
                ticker_series = prices[yf_symbol].copy()
            else:
                # No data for this symbol
                continue

            # Fill missing values for the asset itself
            ticker_series = ticker_series.ffill().bfill()

            # Convert to PLN if needed
            currency = currency_by_ticker.get(ticker, "PLN")
            if currency != "PLN":
                fx_ticker = fx_symbol_to_pln(currency)
                fx_series = fx_series_map.get(fx_ticker)
                if fx_series is not None and not fx_series.empty:
                    # Align indices and fill
                    aligned_fx = fx_series.reindex(ticker_series.index).ffill().bfill()
                    ticker_series = ticker_series * aligned_fx

            # Ensure pure Python dict keyed by pandas Timestamps
            price_dict[ticker] = ticker_series.to_dict()

        return price_dict
    except Exception as e:
        print(f"Error fetching historical data: {e}")
        return {}

"""Functions for portfolio analysis."""

from sqlalchemy.orm import Session
from portfolio.models import Portfolio, Transaction, TransactionType
from collections import defaultdict
from tools.price_fetcher import get_current_price, get_historical_prices_for_tickers, get_currency_for_ticker, fx_symbol_to_pln, _fetch_fx_series
from portfolio.models import Asset
import pandas as pd
from datetime import timedelta
import math


def get_holdings(session: Session, portfolio_id: int) -> dict:
    """
    Calculates the current holdings for a given portfolio.

    Args:
        session: The database session.
        portfolio_id: The ID of the portfolio to analyze.

    Returns:
        A dictionary with asset tickers as keys and their quantities as values.
    """
    holdings = defaultdict(float)
    transactions = session.query(Transaction).filter_by(portfolio_id=portfolio_id).all()

    for t in transactions:
        if t.transaction_type == TransactionType.BUY:
            holdings[t.asset.ticker] += t.quantity
        elif t.transaction_type == TransactionType.SELL:
            holdings[t.asset.ticker] -= t.quantity

    # Filter out assets with zero or negative quantity
    return {ticker: qty for ticker, qty in holdings.items() if qty > 0}


def calculate_asset_return(session: Session, portfolio_id: int, asset_id: int) -> dict:
    """
    Calculates the rate of return for a single asset in a portfolio.
    """
    transactions = session.query(Transaction).filter_by(
        portfolio_id=portfolio_id, asset_id=asset_id
    ).order_by(Transaction.transaction_date).all()

    total_cost = 0
    total_revenue = 0
    quantity_held = 0
    asset_ticker = transactions[0].asset.ticker if transactions else None

    for t in transactions:
        if t.transaction_type == TransactionType.BUY:
            total_cost += t.quantity * t.price + (t.commission or 0)
            quantity_held += t.quantity
        elif t.transaction_type == TransactionType.SELL:
            total_revenue += t.quantity * t.price - (t.commission or 0)
            quantity_held -= t.quantity
    
    realized_pnl = total_revenue - total_cost
    unrealized_pnl = 0
    market_value = 0

    if quantity_held > 0 and asset_ticker:
        current_price = get_current_price(asset_ticker)
        if current_price:
            market_value = quantity_held * current_price
            # Simplified unrealized PnL. A more accurate calculation would use average cost basis.
            avg_cost_per_share = total_cost / sum(t.quantity for t in transactions if t.transaction_type == TransactionType.BUY)
            unrealized_pnl = (current_price - avg_cost_per_share) * quantity_held

    total_pnl = realized_pnl + unrealized_pnl
    rate_of_return = (total_pnl / total_cost) * 100 if total_cost > 0 else 0

    return {
        "total_cost": total_cost,
        "total_revenue": total_revenue,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "market_value": market_value,
        "rate_of_return": rate_of_return,
        "quantity_held": quantity_held
    }


def calculate_portfolio_return(session: Session, portfolio_id: int) -> dict:
    """
    Calculates the overall rate of return for a portfolio.
    """
    assets = session.query(Transaction.asset_id).filter_by(portfolio_id=portfolio_id).distinct().all()
    
    total_cost_portfolio = 0
    total_realized_pnl_portfolio = 0
    total_unrealized_pnl_portfolio = 0
    total_market_value_portfolio = 0

    for asset in assets:
        asset_return = calculate_asset_return(session, portfolio_id, asset.asset_id)
        total_cost_portfolio += asset_return['total_cost']
        total_realized_pnl_portfolio += asset_return['realized_pnl']
        total_unrealized_pnl_portfolio += asset_return['unrealized_pnl']
        total_market_value_portfolio += asset_return['market_value']

    total_pnl = total_realized_pnl_portfolio + total_unrealized_pnl_portfolio
    rate_of_return = (total_pnl / total_cost_portfolio) * 100 if total_cost_portfolio > 0 else 0

    return {
        "total_cost": total_cost_portfolio,
        "realized_pnl": total_realized_pnl_portfolio,
        "unrealized_pnl": total_unrealized_pnl_portfolio,
        "market_value": total_market_value_portfolio,
        "rate_of_return": rate_of_return
    }


def calculate_group_return(session: Session) -> dict:
    """
    Calculates the combined rate of return for all portfolios.

    Args:
        session: The database session.

    Returns:
        A dictionary with aggregated performance for all portfolios.
    """
    portfolios = session.query(Portfolio).all()
    
    total_cost = 0
    total_revenue = 0

    for p in portfolios:
        portfolio_return = calculate_portfolio_return(session, p.id)
        total_cost += portfolio_return['total_cost']
        total_revenue += portfolio_return['total_revenue']

    realized_pnl = total_revenue - total_cost
    rate_of_return = (realized_pnl / total_cost) * 100 if total_cost > 0 else 0

    return {
        "total_cost": total_cost,
        "total_revenue": total_revenue,
        "realized_pnl": realized_pnl,
        "rate_of_return": rate_of_return
    }


if __name__ == '__main__':
    # Example usage:
    from database import Database
    from portfolio.models import Portfolio, Asset

    db = Database()
    session = db.Session()

    # Assuming a portfolio exists
    portfolio = session.query(Portfolio).first()
    if portfolio:
        print(f"--- Analysis for Portfolio: {portfolio.name} ---")

        # Holdings
        current_holdings = get_holdings(session, portfolio.id)
        print("\nCurrent Holdings:")
        for ticker, qty in current_holdings.items():
            print(f"  {ticker}: {qty:.2f}")

        # Per-asset return
        print("\nAsset Returns:")
        assets = session.query(Asset.id, Asset.ticker).join(Transaction).filter(Transaction.portfolio_id == portfolio.id).distinct().all()
        for asset_id, ticker in assets:
            asset_return = calculate_asset_return(session, portfolio.id, asset_id)
            print(f"  {ticker}:")
            print(f"    Realized PnL: {asset_return['realized_pnl']:.2f}")
            print(f"    Rate of Return: {asset_return['rate_of_return']:.2f}%")

        # Portfolio return
        portfolio_return = calculate_portfolio_return(session, portfolio.id)
        print("\nPortfolio Summary:")
        print(f"  Total Cost: {portfolio_return['total_cost']:.2f}")
        print(f"  Total Revenue: {portfolio_return['total_revenue']:.2f}")
        print(f"  Realized PnL: {portfolio_return['realized_pnl']:.2f}")
        print(f"  Rate of Return: {portfolio_return['rate_of_return']:.2f}%")

    # Group return for all portfolios
    group_return = calculate_group_return(session)
    print("\n--- Group Analysis (All Portfolios) ---")
    print(f"  Total Cost: {group_return['total_cost']:.2f}")
    print(f"  Total Revenue: {group_return['total_revenue']:.2f}")
    print(f"  Realized PnL: {group_return['realized_pnl']:.2f}")
    print(f"  Rate of Return: {group_return['rate_of_return']:.2f}%")

    session.close()

"""Poprawiona funkcja calculate_roi_over_time"""


def calculate_roi_over_time(session: Session, portfolio_id: int):
    """
    Oblicza stopę zwrotu portfela w czasie używając Time-Weighted Return (TWR).
    
    TWR eliminuje wpływ wpłat i wypłat na wynik procentowy.
    TWR = (1 + r1) * (1 + r2) * ... * (1 + rn) - 1
    gdzie ri = (EV - (BV + CF)) / (BV + CF)
    EV: End Value, BV: Begin Value, CF: Cash Flow
    """
    # Pobierz wszystkie transakcje
    transactions = session.query(Transaction).filter_by(
        portfolio_id=portfolio_id
    ).order_by(Transaction.transaction_date).all()

    if not transactions:
        return []

    # Zakres dat
    start_date = transactions[0].transaction_date
    end_date = pd.Timestamp.today().date()

    # Pobierz unikalne tickery
    asset_ids = session.query(Transaction.asset_id).filter_by(
        portfolio_id=portfolio_id
    ).distinct().all()
    tickers = []
    for asset_id in asset_ids:
        ticker = session.query(Asset.ticker).filter_by(id=asset_id[0]).scalar()
        if ticker:
            tickers.append(ticker)

    if not tickers:
        return []

    # Przygotuj dane walutowe
    try:
        currency_by_ticker = {t: get_currency_for_ticker(t) for t in tickers}
        currencies = sorted({c for c in currency_by_ticker.values() if c != "PLN"})
        fx_series_map = _fetch_fx_series(currencies, start_date, end_date) if currencies else {}
    except Exception as e:
        print(f"Błąd pobierania kursów walut: {e}")
        currency_by_ticker = {t: "PLN" for t in tickers}
        fx_series_map = {}

    # Pobierz historyczne ceny dla wszystkich tickerów
    historical_prices = get_historical_prices_for_tickers(tickers, start_date, end_date)

    # Funkcja pomocnicza do konwersji ceny na PLN
    def convert_to_pln(price, ticker, date):
        currency = currency_by_ticker.get(ticker, "PLN")
        if currency == "PLN":
            return float(price)
        fx_ticker = fx_symbol_to_pln(currency)
        fx_series = fx_series_map.get(fx_ticker)
        if fx_series is None or fx_series.empty:
            return float(price)
        date_ts = pd.Timestamp(date)
        if date_ts in fx_series.index:
            fx_rate = float(fx_series.loc[date_ts])
        else:
            prev_dates = fx_series.index[fx_series.index <= date_ts]
            if len(prev_dates) > 0:
                fx_rate = float(fx_series.loc[prev_dates.max()])
            else:
                fx_rate = float(fx_series.iloc[0])
        return float(price) * fx_rate

    def get_price_on_or_before(ticker, date):
        if ticker not in historical_prices or not historical_prices[ticker]:
            return None
        prices = historical_prices[ticker]
        date_ts = pd.Timestamp(date)
        if date_ts in prices:
            return convert_to_pln(prices[date_ts], ticker, date_ts)
        prev_dates = [d for d in prices.keys() if d <= date_ts]
        if prev_dates:
            prev_date = max(prev_dates)
            return convert_to_pln(prices[prev_date], ticker, prev_date)
        return None

    date_range = pd.date_range(start=start_date, end=end_date, freq='D')
    
    # Agreguj przepływy pieniężne według dat
    cash_flows_by_date = defaultdict(float)
    for t in transactions:
        date = t.transaction_date
        price_pln = convert_to_pln(t.price, t.asset.ticker, date)
        gross = float(t.quantity) * price_pln
        commission = float(t.commission or 0.0)

        if t.transaction_type == TransactionType.BUY:
            cash_flow = (gross + commission) # Inflow to assets (Cost)
            cash_flows_by_date[date] += cash_flow
        elif t.transaction_type == TransactionType.SELL:
            cash_flow = -(gross - commission) # Outflow from assets (Proceeds)
            cash_flows_by_date[date] += cash_flow

    holdings = defaultdict(float)
    results = []
    
    cumulative_twr = 1.0
    prev_market_value = 0.0
    cumulative_invested = 0.0

    for date in date_range:
        date_obj = date.date()
        
        # Calculate market value BEFORE transactions (Start Value)
        # Actually TWR usually assumes transactions happen at start or end.
        # If we use Daily valuation: 
        # r = (V_end - V_begin - CF) / (V_begin + CF) if CF at start
        # or r = (V_end - V_begin - CF) / V_begin if CF at end
        # We will assume CF happens at START of day for simplicity (invested immediately affects exposure).
        
        # Apply transactions to holdings
        # Note: holdings need to be updated to calculate End Value
        
        current_holdings_value = 0.0
        # Calculate value of PREVIOUS holdings at CURRENT prices (to approximate return including day's move)
        # But standard way is:
        # 1. Get Market Value at End of Day (with new holdings)
        # 2. Get Cash Flow sum for the day
        # 3. Previous Market Value is V_begin
        
        # Update holdings for the day
        daily_cash_flow = cash_flows_by_date.get(date_obj, 0.0)
        cumulative_invested += daily_cash_flow

        for t in [tr for tr in transactions if tr.transaction_date == date_obj]:
            if t.transaction_type == TransactionType.BUY:
                holdings[t.asset.ticker] += t.quantity
            elif t.transaction_type == TransactionType.SELL:
                holdings[t.asset.ticker] -= t.quantity

        # Calculate End Market Value
        market_value = 0.0
        for ticker, qty in holdings.items():
            if qty > 0:
                price = get_price_on_or_before(ticker, date)
                if price is not None and price > 0:
                    market_value += qty * price
        
        # Calculate Daily Return
        # Denominator: Capital at risk during the day.
        # If we assume CF at start: V_begin + CF
        denominator = prev_market_value + daily_cash_flow
        
        if denominator > 0.01: # Avoid division by zero or tiny amounts
            daily_return = (market_value - denominator) / denominator
        else:
            daily_return = 0.0
            
        cumulative_twr *= (1 + daily_return)
        
        results.append({
            'date': date,
            'market_value': market_value,
            'invested': cumulative_invested,
            'rate_of_return': (cumulative_twr - 1) * 100.0
        })
        
        prev_market_value = market_value

    # Utwórz DataFrame i agreguj do tygodni
    df = pd.DataFrame(results)
    df['date'] = pd.to_datetime(df['date'])
    
    # Forward fill 
    df['market_value'] = df['market_value'].replace(0, pd.NA).ffill().fillna(0)
    df['rate_of_return'] = df['rate_of_return'].ffill().fillna(0)
    df['invested'] = df['invested'].ffill().fillna(0)

    # Zwracaj dane dzienne (bez agregacji tygodniowej)
    roi_data = []
    for _, row in df.iterrows():
        roi_data.append({
            'date': row['date'].strftime('%Y-%m-%d'),
            'rate_of_return': float(row['rate_of_return']),
            'market_value': float(row['market_value']),
            'invested': float(row['invested'])
        })

    return roi_data

def calculate_portfolio_overview(session: Session, portfolio_id: int) -> dict:
    """
    Calculates extended portfolio summary:
    - current value (PLN)
    - day change value and percent (vs previous available trading day)
    - total profit (holdings + sales - buys)
    - ROI (TWR %) from calculate_roi_over_time
    - current profit (value - net invested capital)
    - annualized return (from TWR over period)
    - top gainers / decliners (day-over-day for current holdings)
    """
    # Load transactions
    transactions = session.query(Transaction).filter_by(
        portfolio_id=portfolio_id
    ).order_by(Transaction.transaction_date).all()

    if not transactions:
        return {
            'value': 0.0,
            'daily_change_value': 0.0,
            'daily_change_pct': 0.0,
            'total_profit': 0.0,
            'roi_pct': 0.0,
            'current_profit': 0.0,
            'annualized_return_pct': 0.0,
            'gainers': [],
            'decliners': []
        }

    start_date = transactions[0].transaction_date
    end_date = pd.Timestamp.today().date()

    # Buys/Sells aggregations in PLN by historical FX at transaction dates
    try:
        currencies = sorted({get_currency_for_ticker(t.asset.ticker) for t in transactions if get_currency_for_ticker(t.asset.ticker) != "PLN"})
        fx_series_map = _fetch_fx_series(currencies, start_date, end_date) if currencies else {}
    except Exception:
        fx_series_map = {}

    def to_pln(t):
        px = float(t.price)
        currency = "PLN"
        try:
            currency = get_currency_for_ticker(t.asset.ticker)
        except Exception:
            pass
        if currency != "PLN":
            fx_ticker = fx_symbol_to_pln(currency)
            fx_series = fx_series_map.get(fx_ticker)
            if fx_series is not None and not fx_series.empty:
                d = pd.Timestamp(t.transaction_date)
                if d in fx_series.index:
                    fx_rate = float(fx_series.loc[d])
                else:
                    prev_idx = fx_series.index[fx_series.index <= d]
                    fx_rate = float(fx_series.loc[prev_idx.max()]) if len(prev_idx) > 0 else float(fx_series.iloc[0])
                px *= fx_rate
        return px

    total_buys = sum(float(t.quantity) * to_pln(t) + float(t.commission or 0.0) for t in transactions if t.transaction_type == TransactionType.BUY)
    total_sells = sum(float(t.quantity) * to_pln(t) - float(t.commission or 0.0) for t in transactions if t.transaction_type == TransactionType.SELL)
    net_invested = total_buys - total_sells

    # Current holdings (ticker -> qty)
    holdings = get_holdings(session, portfolio_id)
    tickers = list(holdings.keys())

    # Fetch recent historical prices for current holdings to compute day change
    gainers = []
    decliners = []
    current_value = 0.0
    prev_value = 0.0

    if tickers:
        # Look back enough to find previous available trading day
        hist_start = end_date - timedelta(days=30)
        hist = get_historical_prices_for_tickers(tickers, hist_start, end_date)

        # Helper to get last and previous price for a ticker
        def last_and_prev_price(tkr):
            if tkr not in hist or not hist[tkr]:
                return None, None, None
            dates = sorted(hist[tkr].keys())
            last_d = max(dates)
            last_p = hist[tkr][last_d]
            # previous available date strictly before last_d
            prev_dates = [d for d in dates if d < last_d]
            if prev_dates:
                prev_d = max(prev_dates)
                prev_p = hist[tkr][prev_d]
                return last_p, prev_p, last_d
            else:
                return last_p, None, last_d

        for tkr, qty in holdings.items():
            last_p, prev_p, last_d = last_and_prev_price(tkr)
            if last_p is not None and math.isfinite(float(last_p)):
                current_value += qty * float(last_p)
            if prev_p is not None and math.isfinite(float(prev_p)):
                prev_value += qty * float(prev_p)
                # day-over-day percent for this ticker
                if float(prev_p) > 0 and last_p is not None and math.isfinite(float(last_p)):
                    pct = (float(last_p) - float(prev_p)) / float(prev_p) * 100.0
                    entry = {'ticker': tkr, 'pct': pct}
                    if pct >= 0:
                        gainers.append(entry)
                    else:
                        decliners.append(entry)
            else:
                # If no previous price, count previous value with last price (no change contribution)
                if last_p is not None and math.isfinite(float(last_p)):
                    prev_value += qty * float(last_p)

    daily_change_value = current_value - prev_value
    daily_change_pct = (daily_change_value / prev_value * 100.0) if prev_value > 0 else 0.0

    # ROI (TWR) for overview: use time-weighted return from series (matches wykres i oczekiwania)
    roi_series = calculate_roi_over_time(session, portfolio_id) or []
    roi_pct = roi_series[-1]['rate_of_return'] if roi_series else 0.0

    # Annualized from TWR over holding period
    days = (end_date - start_date).days or 1
    twr_total = max(min(roi_pct / 100.0, 10.0), -0.9999)
    annualized_return_pct = ((1.0 + twr_total) ** (365.0 / days) - 1.0) * 100.0 if days > 0 else 0.0

    # Profits
    total_profit = current_value + total_sells - total_buys
    current_profit = current_value - net_invested

    # Sort gainers/decliners
    gainers = sorted(gainers, key=lambda x: x['pct'], reverse=True)[:5]
    decliners = sorted(decliners, key=lambda x: x['pct'])[:5]

    return {
        'value': float(current_value),
        'daily_change_value': float(daily_change_value),
        'daily_change_pct': float(daily_change_pct),
        'total_profit': float(total_profit),
        'roi_pct': float(roi_pct),
        'current_profit': float(current_profit),
        'annualized_return_pct': float(annualized_return_pct),
        'gainers': gainers,
        'decliners': decliners
    }


def calculate_portfolio_value_over_time(session: Session, portfolio_id: int):
    """
    Oblicza historyczną wartość portfela w czasie.

    Returns:
        Lista słowników z kluczami: 'date', 'value'.
    """
    transactions = session.query(Transaction).filter_by(
        portfolio_id=portfolio_id
    ).order_by(Transaction.transaction_date).all()

    if not transactions:
        return []

    start_date = transactions[0].transaction_date
    end_date = pd.Timestamp.today().date()

    asset_ids = session.query(Transaction.asset_id).filter_by(
        portfolio_id=portfolio_id
    ).distinct().all()
    tickers = [session.query(Asset.ticker).filter_by(id=asset_id[0]).scalar() for asset_id in asset_ids if session.query(Asset.ticker).filter_by(id=asset_id[0]).scalar()]

    if not tickers:
        return []

    try:
        currency_by_ticker = {t: get_currency_for_ticker(t) for t in tickers}
        currencies = sorted({c for c in currency_by_ticker.values() if c != "PLN"})
        fx_series_map = _fetch_fx_series(currencies, start_date, end_date) if currencies else {}
    except Exception as e:
        print(f"Błąd pobierania kursów walut: {e}")
        currency_by_ticker = {t: "PLN" for t in tickers}
        fx_series_map = {}

    historical_prices = get_historical_prices_for_tickers(tickers, start_date, end_date)

    def convert_to_pln(price, ticker, date):
        currency = currency_by_ticker.get(ticker, "PLN")
        if currency == "PLN":
            return float(price)
        fx_ticker = fx_symbol_to_pln(currency)
        fx_series = fx_series_map.get(fx_ticker)
        if fx_series is None or fx_series.empty:
            return float(price)
        date_ts = pd.Timestamp(date)
        if date_ts in fx_series.index:
            fx_rate = float(fx_series.loc[date_ts])
        else:
            prev_dates = fx_series.index[fx_series.index <= date_ts]
            if len(prev_dates) > 0:
                fx_rate = float(fx_series.loc[prev_dates.max()])
            else:
                fx_rate = float(fx_series.iloc[0])
        return float(price) * fx_rate

    def get_price_on_or_before(ticker, date):
        if ticker not in historical_prices or not historical_prices[ticker]:
            return None
        prices = historical_prices[ticker]
        date_ts = pd.Timestamp(date)
        if date_ts in prices:
            return convert_to_pln(prices[date_ts], ticker, date_ts)
        prev_dates = [d for d in prices.keys() if d <= date_ts]
        if prev_dates:
            prev_date = max(prev_dates)
            return convert_to_pln(prices[prev_date], ticker, prev_date)
        return None

    date_range = pd.date_range(start=start_date, end=end_date, freq='D')
    holdings = defaultdict(float)
    results = []

    for date in date_range:
        date_obj = date.date()

        for t in [tr for tr in transactions if tr.transaction_date == date_obj]:
            if t.transaction_type == TransactionType.BUY:
                holdings[t.asset.ticker] += t.quantity
            elif t.transaction_type == TransactionType.SELL:
                holdings[t.asset.ticker] -= t.quantity

        market_value = 0.0
        for ticker, qty in holdings.items():
            if qty > 0:
                price = get_price_on_or_before(ticker, date)
                if price is not None and price > 0:
                    market_value += qty * price

        results.append({'date': date.strftime('%Y-%m-%d'), 'value': market_value})
        
    df = pd.DataFrame(results)
    df['value'] = df['value'].replace(0, pd.NA).ffill().fillna(0)

    return df.to_dict('records')

"""Functions for portfolio analysis."""

from sqlalchemy.orm import Session
from portfolio.models import Portfolio, Transaction, TransactionType
from collections import defaultdict
from tools.price_fetcher import get_current_price, get_historical_prices_for_tickers, get_currency_for_ticker, fx_symbol_to_pln, _fetch_fx_series, get_dividends_for_tickers
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
    gdzie ri = (EV - CF - BV) / BV
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

    # Pobierz historyczne ceny dla wszystkich tickerów (już skonwertowane na PLN)
    historical_prices = get_historical_prices_for_tickers(tickers, start_date, end_date)

    # Funkcja pomocnicza do konwersji ceny na PLN (dla transakcji)
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

    # Pobierz cenę rynkową (już w PLN, bez ponownej konwersji)
    def get_price_on_or_before(ticker, date):
        if ticker not in historical_prices or not historical_prices[ticker]:
            return None
        prices = historical_prices[ticker]
        date_ts = pd.Timestamp(date)
        if date_ts in prices:
            return prices[date_ts] 
        prev_dates = [d for d in prices.keys() if d <= date_ts]
        if prev_dates:
            prev_date = max(prev_dates)
            return prices[prev_date]
        return None

    date_range = pd.date_range(start=start_date, end=end_date, freq='D')
    
    # Agreguj przepływy pieniężne według dat (PLN)
    cash_flows_by_date = defaultdict(float)
    for t in transactions:
        date = t.transaction_date
        price_pln = convert_to_pln(t.price, t.asset.ticker, date)
        gross = float(t.quantity) * price_pln
        commission = float(t.commission or 0.0)

        if t.transaction_type == TransactionType.BUY:
            cash_flow = (gross + commission) # Inflow to assets
            cash_flows_by_date[date] += cash_flow
        elif t.transaction_type == TransactionType.SELL:
            cash_flow = -(gross - commission) # Outflow from assets
            cash_flows_by_date[date] += cash_flow

    holdings = defaultdict(float)
    last_known_prices = {} # Fallback prices from transactions
    results = []
    
    cumulative_twr = 1.0
    prev_market_value = 0.0
    cumulative_invested = 0.0
    
    split_ratios = {} # Ticker -> Ratio

    for date in date_range:
        date_obj = date.date()
        
        # Update holdings and split heuristic
        daily_cash_flow = cash_flows_by_date.get(date_obj, 0.0)
        cumulative_invested += daily_cash_flow

        # Process transactions for today
        day_transactions = [tr for tr in transactions if tr.transaction_date == date_obj]
        
        for t in day_transactions:
             # Heuristic Split Detection
             # If transaction price (PLN) differs massively from market price (PLN), adjust quantity
             market_p = get_price_on_or_before(t.asset.ticker, date)
             trans_p = convert_to_pln(t.price, t.asset.ticker, date)
             
             if market_p and market_p > 0:
                 ratio = trans_p / market_p
                 # If ratio > 1.5 or < 0.6, assumesplit. But be careful of volatile assets.
                 # Splits are usually integers like 2, 3, 4, 10, 20.
                 # Reverse split: 0.1, 0.5.
                 if ratio > 1.8 or ratio < 0.6:
                     split_ratios[t.asset.ticker] = ratio
                     # Also adjust last_known to market price to avoid skew
                     last_known_prices[t.asset.ticker] = market_p
                 else:
                     last_known_prices[t.asset.ticker] = trans_p
             else:
                 last_known_prices[t.asset.ticker] = trans_p

        # Apply quantity updates
        for t in day_transactions:
            ratio = split_ratios.get(t.asset.ticker, 1.0)
            qty = t.quantity * ratio
            
            if t.transaction_type == TransactionType.BUY:
                holdings[t.asset.ticker] += qty
            elif t.transaction_type == TransactionType.SELL:
                holdings[t.asset.ticker] -= qty

        # Calculate End Market Value
        market_value = 0.0
        for ticker, qty in holdings.items():
            if qty > 0:
                price = get_price_on_or_before(ticker, date)
                
                # Fallback
                if price is None or price <= 0:
                    price = last_known_prices.get(ticker)
                else:
                    last_known_prices[ticker] = price
                
                if price is not None and price > 0:
                    market_value += qty * price
        
        # Calculate Daily Return (End-of-Day TWR)
        # r = (V_end - CF - V_begin) / V_begin
        if prev_market_value > 0.01:
            daily_return = (market_value - daily_cash_flow - prev_market_value) / prev_market_value
        elif daily_cash_flow > 0.01:
            # Initial funding or restart
            daily_return = (market_value - daily_cash_flow) / daily_cash_flow
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

    # Utwórz DataFrame
    df = pd.DataFrame(results)
    df['date'] = pd.to_datetime(df['date'])
    
    # Forward fill 
    df['market_value'] = df['market_value'].replace(0, pd.NA).ffill().fillna(0)
    df['rate_of_return'] = df['rate_of_return'].ffill().fillna(0)
    df['invested'] = df['invested'].ffill().fillna(0)

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
    - assets details (list of holdings with metrics)
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
            'assets': []
        }

    start_date = transactions[0].transaction_date
    end_date = pd.Timestamp.today().date()

    # Buys/Sells aggregations in PLN by historical FX at transaction dates
    try:
        currencies = sorted({get_currency_for_ticker(t.asset.ticker) for t in transactions if get_currency_for_ticker(t.asset.ticker) != "PLN"})
        fx_series_map = _fetch_fx_series(currencies, start_date, end_date) if currencies else {}
    except Exception:
        fx_series_map = {}

    def get_fx_rate(ticker, date):
        currency = "PLN"
        try:
            currency = get_currency_for_ticker(ticker)
        except Exception:
            pass
        if currency == "PLN":
            return 1.0
        
        fx_ticker = fx_symbol_to_pln(currency)
        fx_series = fx_series_map.get(fx_ticker)
        if fx_series is not None and not fx_series.empty:
            d = pd.Timestamp(date)
            if d in fx_series.index:
                return float(fx_series.loc[d])
            else:
                prev_idx = fx_series.index[fx_series.index <= d]
                return float(fx_series.loc[prev_idx.max()]) if len(prev_idx) > 0 else float(fx_series.iloc[0])
        return 1.0

    def to_pln(t):
        px = float(t.price)
        fx = get_fx_rate(t.asset.ticker, t.transaction_date)
        return px * fx

    total_buys = sum(float(t.quantity) * to_pln(t) + float(t.commission or 0.0) for t in transactions if t.transaction_type == TransactionType.BUY)
    total_sells = sum(float(t.quantity) * to_pln(t) - float(t.commission or 0.0) for t in transactions if t.transaction_type == TransactionType.SELL)
    net_invested = total_buys - total_sells

    # Calculate per-asset avg price (Original Currency) and Cost Basis (PLN)
    # Handles both Long and Short positions correctly.
    asset_metrics = {} # ticker -> {qty, avg_price_org, cost_basis_pln}

    for t in transactions:
        tkr = t.asset.ticker
        if tkr not in asset_metrics:
            asset_metrics[tkr] = {'qty': 0.0, 'avg_price_org': 0.0, 'cost_basis_pln': 0.0}
        
        curr = asset_metrics[tkr]
        old_qty = curr['qty']
        tx_qty = float(t.quantity)
        tx_price = float(t.price)
        tx_val_pln = tx_qty * to_pln(t)
        
        if t.transaction_type == TransactionType.BUY:
            # Buying
            if old_qty >= 0:
                # Long: Add to position
                new_qty = old_qty + tx_qty
                # Avg Price Update
                if new_qty > 0:
                    curr['avg_price_org'] = ((old_qty * curr['avg_price_org']) + (tx_qty * tx_price)) / new_qty
                
                curr['cost_basis_pln'] += (tx_val_pln + float(t.commission or 0.0))
                curr['qty'] = new_qty
            else:
                # Short: Covering
                # Determine if we flip to long
                abs_old = abs(old_qty)
                if tx_qty >= abs_old:
                    # Closed completely or flipped
                    # First, close the short
                    curr['qty'] = 0.0
                    curr['avg_price_org'] = 0.0
                    curr['cost_basis_pln'] = 0.0
                    
                    excess_qty = tx_qty - abs_old
                    if excess_qty > 0:
                        # Opened long
                        curr['qty'] = excess_qty
                        curr['avg_price_org'] = tx_price
                        curr['cost_basis_pln'] = excess_qty * to_pln(t) # approx cost basis for new long
                else:
                    # Partial cover
                    remaining_fraction = (abs_old - tx_qty) / abs_old
                    curr['qty'] += tx_qty # -10 + 2 = -8
                    # Reduce cost basis (Proceeds)
                    curr['cost_basis_pln'] *= remaining_fraction

        elif t.transaction_type == TransactionType.SELL:
            # Selling
            if old_qty <= 0:
                # Short: Adding to position (or opening)
                new_qty = old_qty - tx_qty # -5 - 5 = -10
                abs_new = abs(new_qty)
                
                # Avg Price Update (Weighted avg of entry)
                if abs_new > 0:
                    curr['avg_price_org'] = ((abs(old_qty) * curr['avg_price_org']) + (tx_qty * tx_price)) / abs_new
                
                # Cost Basis (Proceeds) Update
                curr['cost_basis_pln'] += (tx_val_pln - float(t.commission or 0.0))
                curr['qty'] = new_qty
            else:
                # Long: Selling
                if tx_qty >= old_qty:
                    # Closed or flipped
                    curr['qty'] = 0.0
                    curr['avg_price_org'] = 0.0
                    curr['cost_basis_pln'] = 0.0
                    
                    excess_qty = tx_qty - old_qty
                    if excess_qty > 0:
                        # Opened short
                        curr['qty'] = -excess_qty
                        curr['avg_price_org'] = tx_price
                        curr['cost_basis_pln'] = excess_qty * to_pln(t) # Proceeds
                else:
                    # Partial sell
                    fraction_remaining = (old_qty - tx_qty) / old_qty
                    curr['qty'] -= tx_qty
                    curr['cost_basis_pln'] *= fraction_remaining

    # Current holdings (ticker -> qty)
    # Filter out near-zero quantities (both pos and neg)
    holdings = {k: v for k, v in asset_metrics.items() if abs(v['qty']) > 0.000001}
    tickers = list(holdings.keys())

    # Fetch recent historical prices for current holdings to compute day change and value
    current_value = 0.0
    prev_value = 0.0
    assets_list = []

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

        for tkr, metrics in holdings.items():
            qty = metrics['qty']
            last_p, prev_p, last_d = last_and_prev_price(tkr)

            # Prefer live current price (already in PLN). Fallback to last historical price (also PLN).
            price_pln = None
            # Prefer last historical PLN price (spójne z wykresem i unikamy błędnych live cen dla NewConnect)
            if last_p is not None and math.isfinite(float(last_p)) and float(last_p) > 0:
                price_pln = float(last_p)
            else:
                # Fallback do live price jeśli nie mamy historii
                live_price = get_current_price(tkr)
                if live_price is not None and math.isfinite(float(live_price)) and float(live_price) > 0:
                    price_pln = float(live_price)
                else:
                    price_pln = 0.0

            asset_val_pln = qty * price_pln
            current_value += asset_val_pln

            # Daily change based on historical previous price if available
            daily_chg_pct = 0.0
            if prev_p is not None and math.isfinite(float(prev_p)) and float(prev_p) > 0 and price_pln > 0:
                prev_price_pln = float(prev_p)
                prev_val_pln = qty * prev_price_pln
                prev_value += prev_val_pln
                daily_chg_pct = (price_pln - prev_price_pln) / prev_price_pln * 100.0

            price_org = price_pln

            # Profit calculation
            cost_basis_pln = metrics['cost_basis_pln']
            profit_pln = asset_val_pln - cost_basis_pln
            
            # Rate of Return % (on current holding)
            return_pct = (profit_pln / cost_basis_pln * 100.0) if cost_basis_pln > 0 else 0.0
            
            assets_list.append({
                'ticker': tkr,
                'quantity': float(qty),
                'avg_purchase_price': float(metrics['avg_price_org']),
                'current_price': float(price_org) if price_org else 0.0,
                'value': float(asset_val_pln),
                'daily_change': float(daily_chg_pct),
                'profit_pln': float(profit_pln),
                'return_pct': float(return_pct),
                'share_pct': 0.0 # to be calculated after total value
            })

    # Calculate share pct
    if current_value > 0:
        for asset in assets_list:
            asset['share_pct'] = (asset['value'] / current_value) * 100.0
            
    # Sort assets by value descending
    assets_list.sort(key=lambda x: x['value'], reverse=True)

    daily_change_value = current_value - prev_value
    daily_change_pct = (daily_change_value / prev_value * 100.0) if prev_value > 0 else 0.0

    # ROI (TWR) for overview: use time-weighted return from series (matches wykres i oczekiwania)
    roi_series = calculate_roi_over_time(session, portfolio_id) or []
    roi_pct = roi_series[-1]['rate_of_return'] if roi_series else 0.0

    # Annualized from TWR over holding period
    days = (end_date - start_date).days or 1
    twr_total = max(min(roi_pct / 100.0, 10.0), -0.9999)
    annualized_return_pct = ((1.0 + twr_total) ** (365.0 / days) - 1.0) * 100.0 if days > 0 else 0.0

    # Dividends (PLN): sum over all dividend events of (div_per_share * quantity held on ex-date)
    dividends_total_pln = 0.0
    try:
        all_tickers = sorted({t.asset.ticker for t in transactions})
        div_map = get_dividends_for_tickers(all_tickers, start_date, end_date)
        # Build transactions by ticker for quick qty lookup
        tx_by_ticker = {}
        for t in transactions:
            tx_by_ticker.setdefault(t.asset.ticker, []).append(t)
        # Sort transactions per ticker by date
        for tkr in tx_by_ticker:
            tx_by_ticker[tkr].sort(key=lambda tr: tr.transaction_date)

        for tkr, series in (div_map or {}).items():
            # series: pd.Series indexed by date -> dividend per share in PLN
            tx_list = tx_by_ticker.get(tkr, [])
            if not tx_list or series is None or series.empty:
                continue
            for dt, div_ps in series.items():
                # Quantity held on dt (inclusive)
                qty = 0.0
                for tr in tx_list:
                    if tr.transaction_date <= pd.Timestamp(dt).date():
                        if tr.transaction_type == TransactionType.BUY:
                            qty += float(tr.quantity)
                        elif tr.transaction_type == TransactionType.SELL:
                            qty -= float(tr.quantity)
                if qty > 0 and div_ps and float(div_ps) != 0.0:
                    dividends_total_pln += qty * float(div_ps)
    except Exception as _e:
        # Keep dividends_total_pln = 0.0 on errors
        pass

    # Profits
    # Bieżący zysk (unrealized): suma zysków pozycji w assets_list (spójne z tabelą)
    current_profit = sum(a['profit_pln'] for a in assets_list) if assets_list else 0.0
    # Na życzenie: Zysk łącznie = bieżący zysk + dywidendy (bez realized)
    total_profit = current_profit + float(dividends_total_pln or 0.0)
    # realized pozostawiamy tylko jako wartość pochodną (nieeksponowaną)
    realized_profit = (current_value + total_sells - total_buys) + float(dividends_total_pln or 0.0) - total_profit

    return {
        'value': float(current_value),
        'daily_change_value': float(daily_change_value),
        'daily_change_pct': float(daily_change_pct),
        'total_profit': float(total_profit),
        'roi_pct': float(roi_pct),
        'current_profit': float(current_profit),
        'annualized_return_pct': float(annualized_return_pct),
        'dividends_total': float(dividends_total_pln),
        'assets': assets_list
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

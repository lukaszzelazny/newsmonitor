"""Functions for portfolio analysis."""

from sqlalchemy.orm import Session
from portfolio.models import Portfolio, Transaction, TransactionType
from collections import defaultdict
from tools.price_fetcher import get_current_price, get_historical_prices_for_tickers
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


def calculate_roi_over_time(session: Session, portfolio_id: int):
    """
    Calculates a daily time-weighted rate of return for the portfolio.

    Returns a list of dictionaries with 'date' and 'rate_of_return' keys.
    """
    print(f"\n=== DEBUG: Starting ROI calculation for portfolio {portfolio_id} ===")

    # Get all transactions for this portfolio
    transactions = session.query(Transaction).filter_by(
        portfolio_id=portfolio_id
    ).order_by(Transaction.transaction_date).all()

    if not transactions:
        print("No transactions found!")
        return []

    print(f"Found {len(transactions)} transactions")

    # Determine date range
    start_date = transactions[0].transaction_date
    end_date = pd.Timestamp.today().date()
    print(f"Date range: {start_date} to {end_date}")

    # Get all unique tickers in the portfolio
    asset_ids = session.query(Transaction.asset_id).filter_by(
        portfolio_id=portfolio_id
    ).distinct().all()
    tickers = []
    for asset_id in asset_ids:
        ticker = session.query(Asset.ticker).filter_by(id=asset_id[0]).scalar()
        if ticker:
            tickers.append(ticker)

    print(f"Tickers in portfolio: {tickers}")

    if not tickers:
        print("No tickers found!")
        return []

    # Fetch historical prices for all tickers
    print("Fetching historical prices...")
    historical_prices = get_historical_prices_for_tickers(tickers, start_date, end_date)

    # Debug: Check what prices we got
    for ticker, prices in historical_prices.items():
        print(f"  {ticker}: {len(prices)} price points")
        if prices:
            first_date = min(prices.keys())
            last_date = max(prices.keys())
            print(f"    Date range: {first_date} to {last_date}")

    # Create date range for daily calculations
    date_range = pd.date_range(start=start_date, end=end_date, freq='D')

    # Initialize cash flows
    cash_flows = pd.Series(0.0, index=date_range)

    # Record all cash flows
    for t in transactions:
        date = pd.Timestamp(t.transaction_date)
        if t.transaction_type == TransactionType.BUY:
            cash_flows[date] -= t.quantity * t.price + (t.commission or 0)
        elif t.transaction_type == TransactionType.SELL:
            cash_flows[date] += t.quantity * t.price - (t.commission or 0)

    print(f"\nTotal cash flows: {cash_flows.sum():.2f}")
    print(f"Days with transactions: {(cash_flows != 0).sum()}")

    # Calculate daily holdings, end-of-day market value, and TWR using cash-flow adjustment
    holdings = defaultdict(float)  # end-of-day holdings after applying today's trades
    daily_values = []              # end-of-day market value
    daily_returns = []             # TWR subperiod returns r_t = (M_t - (M_{t-1} + F_t)) / M_{t-1}

    def price_on_or_before(ticker, day_ts):
        if ticker not in historical_prices:
            return None
        price_data = historical_prices[ticker]
        if day_ts in price_data:
            return price_data[day_ts]
        prev_dates = [d for d in price_data.keys() if d <= day_ts]
        if prev_dates:
            return price_data[max(prev_dates)]
        return None

    def value_of(position_map, price_map):
        total = 0.0
        for tkr, qty in position_map.items():
            if qty > 0:
                p = price_map.get(tkr)
                if p is not None and p > 0:
                    total += qty * p
        return total

    prev_day = None
    for day in date_range:
        prices_today = {t: price_on_or_before(t, day) for t in tickers}
        prices_prev = {t: price_on_or_before(t, prev_day) if prev_day is not None else prices_today.get(t) for t in tickers}

        # Start-of-day market value (yesterday's EOD holdings valued at yesterday's prices)
        mv_prev = value_of(holdings, prices_prev)

        # Net external cash flow during the day, with deposits (buys) positive for TWR adjustment
        C_t = float(-cash_flows.get(day, 0.0))

        # Apply today's transactions to update holdings to end-of-day state
        for tr in [tr for tr in transactions if tr.transaction_date == day.date()]:
            if tr.transaction_type == TransactionType.BUY:
                holdings[tr.asset.ticker] += tr.quantity
            elif tr.transaction_type == TransactionType.SELL:
                holdings[tr.asset.ticker] -= tr.quantity

        # End-of-day market value on updated holdings
        mv_eod = value_of(holdings, prices_today)

        # Time-Weighted daily return using cash-flow adjustment
        if mv_prev > 0:
            r_t = (mv_eod - (mv_prev + C_t)) / mv_prev
        else:
            r_t = 0.0

        daily_returns.append(r_t)
        daily_values.append(mv_eod)
        prev_day = day

    print(f"\nMarket values calculated for {len(daily_values)} days")
    non_zero = [v for v in daily_values if v > 0]
    if non_zero:
        print(f"Min market value: {min(non_zero):.2f}")
        print(f"Max market value: {max(non_zero):.2f}")
    print(f"Latest market value: {daily_values[-1] if daily_values else 0:.2f}")
    print(f"Non-zero values: {sum(1 for v in daily_values if v > 0)}")

    # Create DataFrame for calculations (align by date index to ensure proper cash flow alignment)
    df = pd.DataFrame(
        {
            'market_value': daily_values,
            'cash_flow': cash_flows
        },
        index=date_range
    )
    df['date'] = df.index

    # Forward fill market values to handle weekends/holidays
    df['market_value'] = df['market_value'].replace(0, pd.NA).ffill().fillna(0)

    # Calculate invested capital over time (net amount still deployed)
    df['invested_capital'] = (-cash_flows).cumsum()

    # Time-Weighted Return (TWR) using price-only P&L on previous-day holdings
    df['daily_return'] = pd.Series(daily_returns, index=date_range).astype(float)
    df['daily_return'] = df['daily_return'].fillna(0.0).replace([float('inf'), -float('inf')], 0.0)

    # Compound daily returns into cumulative TWR
    df['twr'] = (1.0 + df['daily_return']).cumprod() - 1.0

    # Percentage rate of return for charting
    df['rate_of_return'] = (df['twr'] * 100).astype(float)

    # For debugging and summary metrics
    total_buys = (-cash_flows[cash_flows < 0]).sum()
    total_sells = cash_flows[cash_flows > 0].sum()

    print(f"\nFinal calculations:")
    print(f"Total money invested (all purchases): {total_buys:.2f} PLN")
    print(f"Money received from sales: {total_sells:.2f} PLN")
    print(f"Current holdings value: {df['market_value'].iloc[-1]:.2f} PLN")
    print(f"Total return (holdings + sales): {(df['market_value'].iloc[-1] + total_sells):.2f} PLN")
    print(f"Net profit: {(df['market_value'].iloc[-1] + total_sells - total_buys):.2f} PLN")
    print(f"ROI (TWR): {df['rate_of_return'].iloc[-1]:.2f}%")
    print(f"\nCapital currently invested: {df['invested_capital'].iloc[-1]:.2f} PLN")

    # Format for the chart (return ALL daily points to densify X axis)
    roi_data = []
    for idx in range(len(df)):
        row = df.iloc[idx]
        # Convert to Python native types, handling NaN
        market_val = row['market_value']
        if pd.isna(market_val):
            market_val = 0.0
        else:
            market_val = float(market_val)

        roi_val = row['rate_of_return']
        if pd.isna(roi_val):
            roi_val = 0.0
        else:
            roi_val = float(roi_val)

        invested_val = row['invested_capital']
        if pd.isna(invested_val):
            invested_val = 0.0
        else:
            invested_val = float(invested_val)

        roi_data.append({
            'date': row['date'].strftime('%Y-%m-%d'),
            'rate_of_return': roi_val,
            'market_value': market_val,
            'invested': invested_val
        })

    print(f"\nReturning {len(roi_data)} data points for chart")
    if roi_data:
        print(f"First point: {roi_data[0]}")
        print(f"Last point: {roi_data[-1]}")

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

    # Buys/Sells aggregations
    total_buys = sum(t.quantity * t.price + (t.commission or 0) for t in transactions if t.transaction_type == TransactionType.BUY)
    total_sells = sum(t.quantity * t.price - (t.commission or 0) for t in transactions if t.transaction_type == TransactionType.SELL)
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

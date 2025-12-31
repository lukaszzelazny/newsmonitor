"""Functions for portfolio analysis."""

from sqlalchemy.orm import Session
from collections import defaultdict
import pandas as pd
from datetime import timedelta
import math

# Import models using absolute path to avoid conflicts
from backend.database import Portfolio, Asset, TransactionType, Transaction
from backend.tools.price_fetcher import get_current_price, get_current_prices, get_historical_prices_for_tickers, get_currency_for_ticker, fx_symbol_to_pln, _fetch_fx_series, get_dividends_for_tickers


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


def calculate_asset_return(session: Session, portfolio_id: int, asset_id: int, price_map: dict = None, transactions: list = None) -> dict:
    """
    Calculates the rate of return for a single asset in a portfolio.
    Uses purchase_value_pln and sale_value_pln if available.
    """
    if transactions is None:
        transactions = session.query(Transaction).filter_by(
            portfolio_id=portfolio_id, asset_id=asset_id
        ).order_by(Transaction.transaction_date).all()

    total_cost_pln = 0.0
    total_revenue_pln = 0.0
    total_bought_shares = 0.0
    total_sold_shares = 0.0
    quantity_held = 0.0
    asset_ticker = transactions[0].asset.ticker if transactions else None

    # Helper to get transaction type as string
    def get_type(t):
        tt = t.transaction_type
        if hasattr(tt, 'value'):
            return tt.value
        return str(tt)

    # Helper to get transaction value in PLN
    def get_tx_value_pln_asset(t):
        tt = get_type(t)
        if tt == 'BUY':
            if t.purchase_value_pln is not None and float(t.purchase_value_pln) > 0:
                return float(t.purchase_value_pln)
            else:
                return float(t.quantity) * float(t.price) + float(t.commission or 0.0)
        elif tt == 'SELL':
            if t.sale_value_pln is not None and float(t.sale_value_pln) > 0:
                return float(t.sale_value_pln)
            else:
                return float(t.quantity) * float(t.price) - float(t.commission or 0.0)
        return 0.0

    for t in transactions:
        tx_value_pln = get_tx_value_pln_asset(t)
        tt = get_type(t)
        if tt == 'BUY':
            total_cost_pln += tx_value_pln
            total_bought_shares += float(t.quantity)
            quantity_held += float(t.quantity)
        elif tt == 'SELL':
            total_revenue_pln += tx_value_pln
            total_sold_shares += float(t.quantity)
            quantity_held -= float(t.quantity)
    
    # Average cost per share (PLN) for bought shares
    avg_cost_per_share_pln = total_cost_pln / total_bought_shares if total_bought_shares > 0 else 0.0
    
    # Realized PnL: revenue from sales minus cost of sold shares (using average cost)
    cost_of_sold = avg_cost_per_share_pln * total_sold_shares
    realized_pnl = total_revenue_pln - cost_of_sold
    
    unrealized_pnl = 0.0
    market_value = 0.0

    if quantity_held > 0 and asset_ticker:
        current_price = None
        if price_map and asset_ticker in price_map:
             current_price = price_map[asset_ticker]
        else:
             try:
                 current_price = get_current_price(asset_ticker)  # already in PLN
             except Exception:
                 current_price = None
             
        if current_price:
            market_value = quantity_held * current_price
            unrealized_pnl = (current_price - avg_cost_per_share_pln) * quantity_held if avg_cost_per_share_pln > 0 else 0.0

    total_pnl = realized_pnl + unrealized_pnl
    rate_of_return = (total_pnl / total_cost_pln) * 100 if total_cost_pln > 0 else 0.0

    return {
        "total_cost": total_cost_pln,
        "total_revenue": total_revenue_pln,
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
    # 1. Fetch assets
    asset_ids_result = session.query(Transaction.asset_id).filter_by(portfolio_id=portfolio_id).distinct().all()
    
    # 2. Pre-fetch prices
    tickers = []
    asset_id_list = []
    for row in asset_ids_result:
        asset_id = row.asset_id
        asset_id_list.append(asset_id)
        ticker = session.query(Asset.ticker).filter_by(id=asset_id).scalar()
        if ticker:
            tickers.append(ticker)
            
    price_map = get_current_prices(tickers) if tickers else {}

    total_cost_portfolio = 0
    total_realized_pnl_portfolio = 0
    total_unrealized_pnl_portfolio = 0
    total_market_value_portfolio = 0

    # Pre-fetch all transactions to avoid N+1 queries
    transactions = session.query(Transaction).filter_by(
        portfolio_id=portfolio_id
    ).order_by(Transaction.transaction_date).all()

    for asset_id in asset_id_list:
        asset_transactions = [t for t in transactions if t.asset_id == asset_id]
        asset_return = calculate_asset_return(session, portfolio_id, asset_id, price_map=price_map, transactions=asset_transactions)
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


def calculate_roi_over_time(session: Session, portfolio_id: int, excluded_tickers=None):
    if excluded_tickers is None:
        excluded_tickers = set()
    """
    Calculates portfolio ROI over time.
    Tracks Cash Balance and Assets Market Value.
    """
    all_transactions = session.query(Transaction).filter_by(
        portfolio_id=portfolio_id
    ).order_by(Transaction.transaction_date).all()

    transactions = [t for t in all_transactions if t.asset.ticker not in excluded_tickers]

    if not transactions:
        return []

    start_date = transactions[0].transaction_date
    end_date = pd.Timestamp.today().date()

    asset_ids = session.query(Transaction.asset_id).filter_by(
        portfolio_id=portfolio_id
    ).distinct().all()

    tickers = []
    for asset_id in asset_ids:
        ticker = session.query(Asset.ticker).filter_by(id=asset_id[0]).scalar()
        if ticker and ticker != 'PLN':
            tickers.append(ticker)

    if not tickers:
        # Check if we have only Cash transactions?
        pass

    # Fetch historical prices
    historical_prices = get_historical_prices_for_tickers(tickers, start_date, end_date, session=session)

    # Helper: Get value in PLN
    def get_tx_value_pln(t):
        if t.transaction_type == TransactionType.BUY:
            if t.purchase_value_pln is not None and float(t.purchase_value_pln) > 0:
                return float(t.purchase_value_pln)
            else:
                return float(t.quantity) * float(t.price) + float(t.commission or 0.0)
        elif t.transaction_type == TransactionType.SELL:
            if t.sale_value_pln is not None and float(t.sale_value_pln) > 0:
                return float(t.sale_value_pln)
            else:
                return float(t.quantity) * float(t.price) - float(t.commission or 0.0)
        elif t.transaction_type in [TransactionType.DEPOSIT, TransactionType.WITHDRAWAL]:
            if t.purchase_value_pln is not None:
                return float(t.purchase_value_pln)
            return float(t.quantity)
        elif t.transaction_type == TransactionType.DIVIDEND:
            if t.sale_value_pln is not None:
                return float(t.sale_value_pln)
            return float(t.price) if t.price else 0.0
        return 0.0

    def get_tx_price_per_share_pln(t):
        if t.transaction_type == TransactionType.BUY and t.purchase_value_pln is not None and float(t.purchase_value_pln) > 0:
            return float(t.purchase_value_pln) / float(t.quantity)
        elif t.transaction_type == TransactionType.SELL and t.sale_value_pln is not None and float(t.sale_value_pln) > 0:
            return float(t.sale_value_pln) / float(t.quantity)
        else:
            return float(t.price)

    def get_price_on_or_before(ticker, date):
        if ticker == 'PLN': return 1.0
        if ticker not in historical_prices or not historical_prices[ticker]:
            return None
        prices = historical_prices[ticker]
        date_ts = pd.Timestamp(date)
        if date_ts in prices:
            price = prices[date_ts]
            if isinstance(price, (int, float)) and not math.isnan(price):
                return float(price)
        prev_dates = [d for d in prices.keys() if d <= date_ts]
        prev_dates.sort(reverse=True)
        for d in prev_dates:
            price = prices[d]
            if isinstance(price, (int, float)) and not math.isnan(price):
                return float(price)
        return None

    date_range = pd.date_range(start=start_date, end=end_date, freq='D')
    results = []
    
    holdings = defaultdict(float)
    cash_balance = 0.0
    last_known_prices = {}
    
    cumulative_buys = 0.0
    cumulative_sells = 0.0
    
    cumulative_weighted_capital = 0.0
    days_with_capital = 0
    prev_invested_sum = 0.0
    
    cost_basis_by_ticker = defaultdict(float)
    
    # Check if user has deposits
    has_deposits = any(t.transaction_type == TransactionType.DEPOSIT for t in transactions)
    
    cumulative_deposits = 0.0
    cumulative_withdrawals = 0.0

    for t in transactions:
        ticker = t.asset.ticker
        if ticker not in last_known_prices and ticker != 'PLN':
            price = get_tx_price_per_share_pln(t)
            if price > 0:
                last_known_prices[ticker] = price

    for date in date_range:
        date_obj = date.date()
        day_transactions = [tr for tr in transactions if tr.transaction_date == date_obj]
        
        daily_buys_val = 0.0
        daily_sells_val = 0.0 # Revenue from assets
        
        for t in day_transactions:
            val = get_tx_value_pln(t)
            ticker = t.asset.ticker
            
            if t.transaction_type == TransactionType.BUY:
                if ticker != 'PLN':
                    holdings[ticker] += float(t.quantity)
                    daily_buys_val += val
                    # Cost Basis Update
                    if holdings[ticker] > 0: # simplified
                        cost_basis_by_ticker[ticker] += val
                
                # Cash impact: Buying asset reduces cash
                cash_balance -= val
                
            elif t.transaction_type == TransactionType.SELL:
                if ticker != 'PLN':
                    prev_qty = holdings[ticker]
                    qty = float(t.quantity)
                    holdings[ticker] -= qty
                    daily_sells_val += val
                    
                    # Cost Basis Update
                    if prev_qty > 0:
                        amount_sold_from_long = min(qty, prev_qty)
                        ratio = amount_sold_from_long / prev_qty
                        reduction = cost_basis_by_ticker[ticker] * ratio
                        cost_basis_by_ticker[ticker] -= reduction
                        
                # Cash impact: Selling asset increases cash
                cash_balance += val

            elif t.transaction_type == TransactionType.DIVIDEND:
                daily_sells_val += val # Treated as revenue
                cash_balance += val
                
            elif t.transaction_type == TransactionType.DEPOSIT:
                cash_balance += val
                cumulative_deposits += val
                
            elif t.transaction_type == TransactionType.WITHDRAWAL:
                cash_balance -= val
                cumulative_withdrawals += val
                
            # Cleanup small holdings
            if ticker != 'PLN' and abs(holdings[ticker]) < 0.0001:
                holdings[ticker] = 0.0
                cost_basis_by_ticker[ticker] = 0.0

        # Current Market Value of Assets
        assets_market_value = 0.0
        for ticker, qty in holdings.items():
            if abs(qty) > 0.0001:
                price = get_price_on_or_before(ticker, date)
                if price is None or price <= 0:
                    price = last_known_prices.get(ticker)
                else:
                    last_known_prices[ticker] = price
                
                if price and price > 0:
                    assets_market_value += qty * price
        
        cumulative_buys += daily_buys_val
        cumulative_sells += daily_sells_val
        
        # Calculate Value and Invested based on mode
        if has_deposits:
            # "Cash Aware" Mode
            total_market_value = assets_market_value + cash_balance
            # Invested = Net Deposits
            # If Net Deposits <= 0 (e.g. profitable withdrawal or just started), 
            # we might have issues with ROI denominator.
            current_invested_sum = cumulative_deposits - cumulative_withdrawals
            if current_invested_sum < 0.0001: 
                # Fallback to Cost Basis if Net Deposits is 0/neg (e.g. trading on house money)
                # But Cost Basis ignores Cash. 
                # Ideally ROI on house money is infinite.
                # Let's clamp or fallback.
                current_invested_sum = sum(cost_basis_by_ticker.values()) + max(0, cash_balance)
        else:
            # "Asset Only" Mode (Legacy)
            # Ignore Cash Balance (which is likely negative due to no deposits)
            total_market_value = assets_market_value
            # Invested = Cost Basis of Held Assets
            current_invested_sum = sum(cost_basis_by_ticker.values())

        # Daily Capital (for Time Weighted Return approximation)
        daily_capital = max(prev_invested_sum, current_invested_sum)
        if daily_capital < 0.0001 and daily_buys_val > 0.0001:
            daily_capital = daily_buys_val
            
        if daily_capital > 0.0001:
            cumulative_weighted_capital += daily_capital
            days_with_capital += 1
            
        avg_capital = cumulative_weighted_capital / days_with_capital if days_with_capital > 0 else 0.0
        
        # Total PnL Calculation
        # Universal Formula: Assets Value + Sales - Buys
        # This represents total profit generated by trading activity.
        # It works regardless of deposits/withdrawals.
        # Note: 'cumulative_buys' includes Cost of Assets Bought.
        # 'cumulative_sells' includes Revenue from Assets Sold + Dividends.
        total_pnl = assets_market_value + cumulative_sells - cumulative_buys
        
        roi_pct = 0.0
        
        if avg_capital > 0.0001:
            roi_pct = (total_pnl / avg_capital) * 100.0
            
        # Special case: If has_deposits and using Net Invested, maybe we should use (Value - Invested) / Invested?
        # Let's verify consistency.
        # If I Deposit 1000. Buy 1000. Value 1100.
        # PnL = 1100 + 0 - 1000 = 100.
        # Avg Capital = 1000.
        # ROI = 10%. Correct.
        # If I Deposit 1000. Keep Cash. Value 1000.
        # PnL = 0 + 0 - 0 = 0.
        # Avg Capital = 1000.
        # ROI = 0%. Correct.
        # So Universal PnL formula works with Net Deposits as Capital.
            
        results.append({
            'date': date,
            'market_value': total_market_value,
            'invested': current_invested_sum,
            'rate_of_return': roi_pct,
            'total_pnl': total_pnl
        })
        
        prev_invested_sum = current_invested_sum

    df = pd.DataFrame(results)
    df['date'] = pd.to_datetime(df['date'])
    df['market_value'] = df['market_value'].ffill().fillna(0)
    df['rate_of_return'] = df['rate_of_return'].ffill().fillna(0)
    df['invested'] = df['invested'].ffill().fillna(0)

    roi_data = []
    for _, row in df.iterrows():
        roi_data.append({
            'date': row['date'].strftime('%Y-%m-%d'),
            'rate_of_return': float(row['rate_of_return']),
            'market_value': float(row['market_value']),
            'invested': float(row['invested']),
            'total_pnl': float(row['total_pnl']) if 'total_pnl' in row else 0.0
        })

    return roi_data

def calculate_portfolio_overview(session: Session, portfolio_id: int, roi_series=None, div_map=None, excluded_tickers=None) -> dict:
    if excluded_tickers is None:
        excluded_tickers = set()

    all_transactions = session.query(Transaction).filter_by(
         portfolio_id=portfolio_id
     ).order_by(Transaction.transaction_date).all()

    if not all_transactions:
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

    transactions = [t for t in all_transactions if t.asset.ticker not in excluded_tickers]
    
    start_date = transactions[0].transaction_date if transactions else all_transactions[0].transaction_date
    end_date = pd.Timestamp.today().date()

    def get_tx_value_pln(t):
        if t.transaction_type == TransactionType.BUY:
            if t.purchase_value_pln is not None and float(t.purchase_value_pln) > 0:
                return float(t.purchase_value_pln)
            else:
                return float(t.quantity) * float(t.price) + float(t.commission or 0.0)
        elif t.transaction_type == TransactionType.SELL:
            if t.sale_value_pln is not None and float(t.sale_value_pln) > 0:
                return float(t.sale_value_pln)
            else:
                return float(t.quantity) * float(t.price) - float(t.commission or 0.0)
        elif t.transaction_type in [TransactionType.DEPOSIT, TransactionType.WITHDRAWAL]:
            if t.purchase_value_pln is not None:
                return float(t.purchase_value_pln)
            return float(t.quantity)
        return 0.0

    # Calculate Cash Balance
    # We use ALL transactions for cash balance, even if ticker excluded?
    # If ticker excluded, maybe we shouldn't count its buy/sell?
    # Consistent with 'transactions' filter above.
    cash_balance = 0.0
    for t in transactions:
        val = get_tx_value_pln(t)
        if t.transaction_type == TransactionType.BUY:
            cash_balance -= val
        elif t.transaction_type == TransactionType.SELL:
            cash_balance += val
        elif t.transaction_type == TransactionType.DIVIDEND:
            val_div = val
            if val_div == 0 and t.price: val_div = float(t.price) # Fallback
            cash_balance += val_div
        elif t.transaction_type == TransactionType.DEPOSIT:
            cash_balance += val
        elif t.transaction_type == TransactionType.WITHDRAWAL:
            cash_balance -= val

    total_buys = sum(get_tx_value_pln(t) for t in transactions if t.transaction_type == TransactionType.BUY)
    total_sells = sum(get_tx_value_pln(t) for t in transactions if t.transaction_type == TransactionType.SELL)
    total_dividends_manual = sum(get_tx_value_pln(t) for t in transactions if t.transaction_type == TransactionType.DIVIDEND)
    
    # Asset Metrics
    asset_metrics = {} 

    for t in all_transactions: # Keep using all for asset metrics calc? No, filter excluded.
        if t.asset.ticker in excluded_tickers: continue
        
        tkr = t.asset.ticker
        if tkr not in asset_metrics:
            asset_metrics[tkr] = {'qty': 0.0, 'avg_price_org': 0.0, 'cost_basis_pln': 0.0}
        
        curr = asset_metrics[tkr]
        old_qty = curr['qty']
        tx_qty = float(t.quantity)
        tx_price = float(t.price)
        tx_val_pln = get_tx_value_pln(t)
        
        if t.transaction_type == TransactionType.BUY:
            if old_qty >= 0:
                new_qty = old_qty + tx_qty
                if new_qty > 0:
                    curr['avg_price_org'] = ((old_qty * curr['avg_price_org']) + (tx_qty * tx_price)) / new_qty
                curr['cost_basis_pln'] += tx_val_pln
                curr['qty'] = new_qty
            else: # Short cover
                abs_old = abs(old_qty)
                if tx_qty >= abs_old:
                    curr['qty'] = 0.0
                    curr['avg_price_org'] = 0.0
                    curr['cost_basis_pln'] = 0.0
                    excess_qty = tx_qty - abs_old
                    if excess_qty > 0:
                        curr['qty'] = excess_qty
                        curr['avg_price_org'] = tx_price
                        curr['cost_basis_pln'] = get_tx_value_pln(t) 
                else:
                    remaining_fraction = (abs_old - tx_qty) / abs_old
                    curr['qty'] += tx_qty
                    curr['cost_basis_pln'] *= remaining_fraction

        elif t.transaction_type == TransactionType.SELL:
            if old_qty <= 0: # Short add
                new_qty = old_qty - tx_qty 
                abs_new = abs(new_qty)
                if abs_new > 0:
                    curr['avg_price_org'] = ((abs(old_qty) * curr['avg_price_org']) + (tx_qty * tx_price)) / abs_new
                curr['cost_basis_pln'] += tx_val_pln
                curr['qty'] = new_qty
            else: # Long sell
                if tx_qty >= old_qty:
                    curr['qty'] = 0.0
                    curr['avg_price_org'] = 0.0
                    curr['cost_basis_pln'] = 0.0
                    excess_qty = tx_qty - old_qty
                    if excess_qty > 0:
                        curr['qty'] = -excess_qty
                        curr['avg_price_org'] = tx_price
                        curr['cost_basis_pln'] = get_tx_value_pln(t)
                else:
                    fraction_remaining = (old_qty - tx_qty) / old_qty
                    curr['qty'] -= tx_qty
                    curr['cost_basis_pln'] *= fraction_remaining

    holdings = {k: v for k, v in asset_metrics.items() if abs(v['qty']) > 0.000001}
    tickers = list(holdings.keys())

    current_value_assets = 0.0
    prev_value_assets = 0.0
    assets_list = []

    if tickers:
        hist_start_short = end_date - timedelta(days=10)
        hist = get_historical_prices_for_tickers(tickers, hist_start_short, end_date, session=session)
        live_prices_map = get_current_prices(tickers)

        def last_and_prev_price(tkr):
            if tkr not in hist or not hist[tkr]:
                return None, None, None
            dates = sorted(hist[tkr].keys())
            last_d = max(dates)
            last_p = hist[tkr][last_d]
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
            
            price_pln = 0.0
            used_live_price = False
            today = pd.Timestamp.today().date()
            is_history_today = False
            if last_d:
                d_date = last_d.date() if hasattr(last_d, 'date') else last_d
                if d_date == today:
                    is_history_today = True

            live_price = live_prices_map.get(tkr)
            has_live = (live_price is not None and math.isfinite(float(live_price)) and float(live_price) > 0)
            
            if has_live and not is_history_today:
                price_pln = float(live_price)
                used_live_price = True
            elif last_p is not None and math.isfinite(float(last_p)) and float(last_p) > 0:
                price_pln = float(last_p)
            elif has_live:
                price_pln = float(live_price)
                used_live_price = True
            
            asset_val_pln = qty * price_pln
            current_value_assets += asset_val_pln

            daily_chg_pct = 0.0
            prev_price_pln = 0.0
            if used_live_price:
                if last_p is not None and math.isfinite(float(last_p)) and float(last_p) > 0:
                    prev_price_pln = float(last_p)
            else:
                if prev_p is not None and math.isfinite(float(prev_p)) and float(prev_p) > 0:
                    prev_price_pln = float(prev_p)
            
            if prev_price_pln > 0 and price_pln > 0:
                prev_val_pln = qty * prev_price_pln
                prev_value_assets += prev_val_pln
                daily_chg_pct = (price_pln - prev_price_pln) / prev_price_pln * 100.0

            cost_basis_pln = metrics['cost_basis_pln']
            profit_pln = asset_val_pln - cost_basis_pln
            return_pct = (profit_pln / cost_basis_pln * 100.0) if cost_basis_pln > 0 else 0.0
            
            assets_list.append({
                'ticker': tkr,
                'quantity': float(qty),
                'avg_purchase_price': float(metrics['avg_price_org']),
                'current_price': float(price_pln),
                'value': float(asset_val_pln),
                'daily_change': float(daily_chg_pct),
                'profit_pln': float(profit_pln),
                'return_pct': float(return_pct),
                'share_pct': 0.0,
                'excluded': False
            })

    # Add Cash Asset
    # Logic: If no deposits exist and cash is negative (implicit loan), ignore it in totals.
    # If cash is positive (realized profit), always include it.
    has_deposits = any(t.transaction_type == TransactionType.DEPOSIT for t in transactions)
    include_cash = True
    if not has_deposits and cash_balance < 0:
        include_cash = False

    if abs(cash_balance) > 0.01:
        if include_cash:
            assets_list.append({
                'ticker': 'PLN',
                'quantity': float(cash_balance),
                'avg_purchase_price': 1.0,
                'current_price': 1.0,
                'value': float(cash_balance),
                'daily_change': 0.0,
                'profit_pln': 0.0,
                'return_pct': 0.0,
                'share_pct': 0.0,
                'excluded': False
            })
    
    if include_cash:
        current_value_total = current_value_assets + cash_balance
    else:
        current_value_total = current_value_assets
    
    # Calculate share pct
    if current_value_total > 0:
        for asset in assets_list:
            asset['share_pct'] = (asset['value'] / current_value_total) * 100.0
            
    assets_list.sort(key=lambda x: x['value'], reverse=True)

    # Previous Value Calculation (Approximation)
    # Assets prev value + Cash (Assuming cash didn't change intra-day for this purpose, or just use current cash)
    # Ideally we reconstruct prev cash, but that's hard.
    # Using current cash for daily change calculation of Total Portfolio minimizes noise from deposits today.
    # Daily Change = (AssetsToday + Cash) - (AssetsYest + Cash) = AssetsChange.
    prev_value_total = prev_value_assets + cash_balance
    
    daily_change_value = current_value_total - prev_value_total
    daily_change_pct = (daily_change_value / prev_value_total * 100.0) if prev_value_total > 0 else 0.0

    if roi_series is None:
        roi_series = calculate_roi_over_time(session, portfolio_id, excluded_tickers=excluded_tickers) or []
    roi_pct = roi_series[-1]['rate_of_return'] if roi_series else 0.0

    days = (end_date - start_date).days or 1
    twr_total = max(min(roi_pct / 100.0, 10.0), -0.9999)
    annualized_return_pct = ((1.0 + twr_total) ** (365.0 / days) - 1.0) * 100.0 if days > 0 else 0.0

    dividends_total_pln = 0.0
    try:
        if div_map is None:
            all_tickers = sorted({t.asset.ticker for t in transactions})
            div_map = get_dividends_for_tickers(all_tickers, start_date, end_date)
        
        tx_by_ticker = {}
        for t in transactions:
            tx_by_ticker.setdefault(t.asset.ticker, []).append(t)
        for tkr in tx_by_ticker:
            tx_by_ticker[tkr].sort(key=lambda tr: tr.transaction_date)

        for tkr, series in (div_map or {}).items():
            tx_list = tx_by_ticker.get(tkr, [])
            if not tx_list or series is None or series.empty:
                continue
            for dt, div_ps in series.items():
                qty = 0.0
                for tr in tx_list:
                    if tr.transaction_date < pd.Timestamp(dt).date():
                        if tr.transaction_type == TransactionType.BUY:
                            qty += float(tr.quantity)
                        elif tr.transaction_type == TransactionType.SELL:
                            qty -= float(tr.quantity)
                if qty > 0 and div_ps and float(div_ps) != 0.0:
                    dividends_total_pln += qty * float(div_ps)
    except Exception:
        pass

    current_profit = sum(a['profit_pln'] for a in assets_list if not a.get('excluded')) if assets_list else 0.0
    
    total_dividends_all = float(dividends_total_pln or 0.0) + total_dividends_manual
    
    # Total Profit: AssetsValue + Sells - Buys + Divs
    # Note: current_value_assets should be used here, NOT total (with cash).
    # Why?
    # Profit = (Assets + Cash) - Net_Deposits.
    # Cash = Sells - Buys + Net_Deposits.
    # Profit = Assets + Sells - Buys.
    # So using current_value_assets + Sells - Buys matches!
    # If we used current_value_total (Assets+Cash), we would double count Sells-Buys part of Cash.
    # UNLESS we subtract Net_Deposits explicitly.
    # But we don't have Net_Deposits variable calculated sum.
    # So `current_value_assets + total_sells - total_buys` is the correct invariant.
    
    total_profit = (current_value_assets + total_sells - total_buys) + total_dividends_all

    return {
        'value': float(current_value_total),
        'daily_change_value': float(daily_change_value),
        'daily_change_pct': float(daily_change_pct),
        'total_profit': float(total_profit),
        'roi_pct': float(roi_pct),
        'current_profit': float(current_profit),
        'annualized_return_pct': float(annualized_return_pct),
        'dividends_total': float(total_dividends_all),
        'assets': assets_list
    }


def calculate_portfolio_value_over_time(session: Session, portfolio_id: int):
    """
    Oblicza historyczną wartość portfela w czasie.
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
    
    # Filter out PLN from price fetching
    tickers = [t for t in tickers if t != 'PLN']

    try:
        currency_by_ticker = {t: get_currency_for_ticker(t) for t in tickers}
        currencies = sorted({c for c in currency_by_ticker.values() if c != "PLN"})
        fx_series_map = _fetch_fx_series(currencies, start_date, end_date) if currencies else {}
    except Exception as e:
        print(f"Błąd pobierania kursów walut: {e}")
        currency_by_ticker = {t: "PLN" for t in tickers}
        fx_series_map = {}

    historical_prices = get_historical_prices_for_tickers(tickers, start_date, end_date, session=session)

    def convert_to_pln(price, ticker, date):
        currency = currency_by_ticker.get(ticker, "PLN")
        if currency == "PLN" or 1:
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
        if ticker == 'PLN': return 1.0
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

    def get_tx_value_pln_simple(t):
        if t.transaction_type == TransactionType.BUY:
            if t.purchase_value_pln: return float(t.purchase_value_pln)
            return float(t.quantity) * float(t.price)
        elif t.transaction_type == TransactionType.SELL:
            if t.sale_value_pln: return float(t.sale_value_pln)
            return float(t.quantity) * float(t.price)
        elif t.transaction_type in [TransactionType.DEPOSIT, TransactionType.WITHDRAWAL]:
            if t.purchase_value_pln: return float(t.purchase_value_pln)
            return float(t.quantity)
        elif t.transaction_type == TransactionType.DIVIDEND:
            if t.sale_value_pln: return float(t.sale_value_pln)
            return float(t.price or 0.0)
        return 0.0

    date_range = pd.date_range(start=start_date, end=end_date, freq='D')
    holdings = defaultdict(float)
    cash_balance = 0.0
    results = []
    
    has_deposits = any(t.transaction_type == TransactionType.DEPOSIT for t in transactions)

    for date in date_range:
        date_obj = date.date()

        for t in [tr for tr in transactions if tr.transaction_date == date_obj]:
            ticker = t.asset.ticker
            val = get_tx_value_pln_simple(t)
            
            if t.transaction_type == TransactionType.BUY:
                if ticker != 'PLN':
                    holdings[ticker] += t.quantity
                cash_balance -= val
            elif t.transaction_type == TransactionType.SELL:
                if ticker != 'PLN':
                    holdings[ticker] -= t.quantity
                cash_balance += val
            elif t.transaction_type == TransactionType.DIVIDEND:
                cash_balance += val
            elif t.transaction_type == TransactionType.DEPOSIT:
                cash_balance += val
            elif t.transaction_type == TransactionType.WITHDRAWAL:
                cash_balance -= val

        market_value = 0.0
        for ticker, qty in holdings.items():
            if qty > 0:
                price = get_price_on_or_before(ticker, date)
                if price is not None and price > 0:
                    market_value += qty * price
        
        # Include Cash in total value logic
        # If no deposits and cash is negative, ignore it (Asset Value Only view)
        if not has_deposits and cash_balance < 0:
            total_value = market_value
        else:
            total_value = market_value + cash_balance
            
        results.append({'date': date.strftime('%Y-%m-%d'), 'value': total_value})
        
    df = pd.DataFrame(results)
    df['value'] = df['value'].replace(0, pd.NA).ffill().fillna(0)

    return df.to_dict('records')


def calculate_all_assets_summary(session: Session, portfolio_id: int):

    """
    Zwraca podsumowanie wszystkich aktywów (tickerów) kiedykolwiek obecnych w portfelu,
    z danymi historycznymi (zrealizowany zysk, niezrealizowany, ilość transakcji, itp.)

    Returns:
        Lista słowników z danymi per ticker.
    """
    # Pobierz wszystkie transakcje portfela
    transactions = session.query(Transaction).filter_by(
        portfolio_id=portfolio_id
    ).order_by(Transaction.transaction_date).all()

    if not transactions:
        return []

    # Unikalne asset_id
    asset_ids_result = session.query(Transaction.asset_id).filter_by(
        portfolio_id=portfolio_id
    ).distinct().all()
    asset_ids = [row[0] for row in asset_ids_result]

    # Pre-fetch current prices dla wszystkich tickerów (opcjonalnie)
    tickers = []
    for asset_id in asset_ids:
        ticker = session.query(Asset.ticker).filter_by(id=asset_id).scalar()
        if ticker:
            tickers.append(ticker)
    price_map = get_current_prices(tickers) if tickers else {}

    assets_summary = []
    for asset_id in asset_ids:
        # Filter transactions for this asset from the pre-fetched list
        asset_transactions = [t for t in transactions if t.asset_id == asset_id]
        
        # Użyj istniejącej funkcji calculate_asset_return przekazując transakcje
        asset_return = calculate_asset_return(session, portfolio_id, asset_id, price_map=price_map, transactions=asset_transactions)
        ticker = session.query(Asset.ticker).filter_by(id=asset_id).scalar()
        if not ticker:
            continue

        # (asset_transactions already filtered above)
        buy_count = sum(1 for t in asset_transactions if t.transaction_type == TransactionType.BUY)
        sell_count = sum(1 for t in asset_transactions if t.transaction_type == TransactionType.SELL)
        total_transactions = buy_count + sell_count

        # Oblicz daty pierwszej i ostatniej transakcji
        if asset_transactions:
            first_date = min(t.transaction_date for t in asset_transactions)
            last_date = max(t.transaction_date for t in asset_transactions)
        else:
            first_date = last_date = None

        # Określ czy nadal w portfelu (quantity_held > 0)
        quantity_held = asset_return['quantity_held']
        still_held = quantity_held > 0

        # Oblicz całkowity koszt (suma kwot zakupu) i przychód (suma kwot sprzedaży)
        total_cost = asset_return['total_cost']
        total_revenue = asset_return['total_revenue']

        # Zrealizowany zysk (realized_pnl) już jest w asset_return
        realized_pnl = asset_return['realized_pnl']
        unrealized_pnl = asset_return['unrealized_pnl']
        total_pnl = realized_pnl + unrealized_pnl

        # Udział procentowy w całkowitym koszcie? Możemy obliczyć później po zebraniu wszystkich.
        # Na razie zwracamy surowe dane.
        assets_summary.append({
            'ticker': ticker,
            'quantity_held': quantity_held,
            'avg_purchase_price': total_cost / sum(t.quantity for t in asset_transactions if t.transaction_type == TransactionType.BUY) if buy_count > 0 else 0,
            'current_price': price_map.get(ticker, 0),
            'value': asset_return['market_value'],
            'daily_change': 0,  # Nie mamy danych historycznych dziennych zmian dla podsumowania
            'profit_pln': total_pnl,
            'return_pct': asset_return['rate_of_return'],
            'realized_pnl': realized_pnl,
            'unrealized_pnl': unrealized_pnl,
            'total_cost': total_cost,
            'total_revenue': total_revenue,
            'buy_count': buy_count,
            'sell_count': sell_count,
            'total_transactions': total_transactions,
            'first_transaction_date': first_date.strftime('%Y-%m-%d') if first_date else None,
            'last_transaction_date': last_date.strftime('%Y-%m-%d') if last_date else None,
            'still_held': still_held
        })

    # Posortuj po tickerze
    assets_summary.sort(key=lambda x: x['ticker'])
    return assets_summary


def calculate_monthly_profit(session: Session, portfolio_id: int, excluded_tickers=None):
    if excluded_tickers is None:
        excluded_tickers = set()
    """
    Calculates monthly total profit (PnL) for the portfolio.
    
    Returns:
        List of dicts: [{'month': 'YYYY-MM', 'profit': float}, ...]
    """
    # 1. Get daily series of Value and Invested
    roi_data = calculate_roi_over_time(session, portfolio_id, excluded_tickers=excluded_tickers)
    if not roi_data:
        return []

    # Pre-fetch dividends to avoid double call
    # Need transactions to know holdings and date range
    all_transactions = session.query(Transaction).filter_by(portfolio_id=portfolio_id).all()
    transactions = [t for t in all_transactions if t.asset.ticker not in excluded_tickers]
    
    div_map = None
    if transactions:
        start_date = transactions[0].transaction_date
        end_date = pd.Timestamp.today().date()
        try:
            all_tickers = sorted({t.asset.ticker for t in transactions})
            div_map = get_dividends_for_tickers(all_tickers, start_date, end_date)
        except Exception:
            pass
    
    # Force alignment with Current Overview (Live Prices)
    # This ensures Sum(Monthly) == Total Profit in Header
    # Pass roi_data and div_map to avoid re-calculation/re-fetching
    # Pass excluded_tickers to overview as well
    overview = calculate_portfolio_overview(session, portfolio_id, roi_series=roi_data, div_map=div_map, excluded_tickers=excluded_tickers)
    current_val = overview['value']
    # Net Invested in Overview = total_buys - total_sells
    # In roi_data, invested = cumulative inflows.
    # Logic should be identical.
    
    # We replace/update the last entry of roi_data to match overview state
    if roi_data:
        last_entry = roi_data[-1]
        # Only update if dates are close (e.g. today or yesterday)
        # overview is "NOW". roi_data last entry is "Today" or "Yesterday".
        # We assume roi_data covers up to today.
        last_entry['market_value'] = current_val
        
        # Sync total_pnl with overview (excluding dividends as roi_data is pure capital gains)
        # overview['total_profit'] includes dividends
        # roi_data['total_pnl'] is Capital Gains only
        capital_gains_total = overview['total_profit'] - float(overview['dividends_total'] or 0.0)
        last_entry['total_pnl'] = capital_gains_total
        
        # invested should be consistent, but we can sync it too if needed
        # net_invested_ovr = overview['value'] - overview['total_profit'] + overview['dividends_total'] 
        # (derived from Total Profit = Val - Inv + Divs => Inv = Val + Divs - Profit)
        # Let's trust roi_data invested as it's built transactionally day-by-day.
        # But market_value is the one affected by Live vs Hist price.
        
    df = pd.DataFrame(roi_data)
    df['date'] = pd.to_datetime(df['date'])
    df['month'] = df['date'].dt.to_period('M')
    
    # 2. Get Dividends (already fetched in div_map)
    
    # Group dividends by month
    dividends_by_month = defaultdict(float)

    def get_tx_value_pln(t):
        if t.transaction_type == TransactionType.DIVIDEND:
             if t.sale_value_pln is not None:
                 return float(t.sale_value_pln)
             return float(t.price)
        return 0.0
    
    # Manual Dividends
    for t in transactions:
        if t.transaction_type == TransactionType.DIVIDEND:
            val = get_tx_value_pln(t)
            m_str = pd.Timestamp(t.transaction_date).strftime('%Y-%m')
            dividends_by_month[m_str] += val

    # Automatic Dividends (YF)
    if transactions and div_map:
        try:
            tx_by_ticker = {}
            for t in transactions:
                tx_by_ticker.setdefault(t.asset.ticker, []).append(t)
            for tkr in tx_by_ticker:
                tx_by_ticker[tkr].sort(key=lambda tr: tr.transaction_date)

            for tkr, series in (div_map or {}).items():
                tx_list = tx_by_ticker.get(tkr, [])
                if not tx_list or series is None or series.empty:
                    continue
                for dt, div_ps in series.items():
                    qty = 0.0
                    for tr in tx_list:
                        if tr.transaction_date <= pd.Timestamp(dt).date():
                            if tr.transaction_type == TransactionType.BUY:
                                qty += float(tr.quantity)
                            elif tr.transaction_type == TransactionType.SELL:
                                qty -= float(tr.quantity)
                    if qty > 0 and div_ps and float(div_ps) != 0.0:
                        amount = qty * float(div_ps)
                        m_str = pd.Timestamp(dt).strftime('%Y-%m')
                        dividends_by_month[m_str] += amount
        except Exception:
            pass

    # 3. Calculate Monthly PnL Change
    # Profit_M = (Value_End - Value_Start) - (Invested_End - Invested_Start) + Dividends
    
    monthly_stats = []
    
    # Find last entry for each month
    # Resample to Month End or just take last entry per month group
    monthly_last = df.groupby('month').last().reset_index()
    
    # Add initial state (0, 0) if needed, or handle diff
    # We need "previous month last value" to calculate change.
    
    # Ensure chronological
    monthly_last = monthly_last.sort_values('month')
    
    prev_total_pnl = 0.0
    
    for _, row in monthly_last.iterrows():
        m_str = str(row['month'])
        
        # Total PnL at time T (Capital Gains only)
        # Use total_pnl directly if available, else fallback to val - inv logic (though invested might be wrong for realized)
        if 'total_pnl' in row:
             pnl_t = float(row['total_pnl'])
        else:
             # Fallback (should not happen with new roi_data)
             pnl_t = float(row['market_value']) - float(row['invested'])

        diff_pnl = pnl_t - prev_total_pnl
        
        # Add dividends
        divs = dividends_by_month.get(m_str, 0.0)
        
        total_monthly_profit = diff_pnl + divs
        
        monthly_stats.append({
            'month': m_str,
            'profit': total_monthly_profit
        })
        
        prev_total_pnl = pnl_t
        
    return monthly_stats


def calculate_dividend_stats(session: Session, portfolio_id: int, excluded_tickers=None):
    if excluded_tickers is None:
        excluded_tickers = set()

    # 1. Get transactions (filtered)
    all_transactions = session.query(Transaction).filter_by(portfolio_id=portfolio_id).all()
    transactions = [t for t in all_transactions if t.asset.ticker not in excluded_tickers]
    
    if not transactions:
        return {'chart_data': [], 'table_data': []}

    # Helper to get transaction value in PLN (Manual Dividends)
    def get_tx_value_pln(t):
        # For dividend, we store value in sale_value_pln (treated as inflow)
        # But we verify type to be safe
        if t.transaction_type == TransactionType.DIVIDEND:
             if t.sale_value_pln is not None:
                 return float(t.sale_value_pln)
             # Fallback if stored differently (e.g. price)
             return float(t.price)
        return 0.0

    dividends_by_month = defaultdict(float)
    dividends_by_ticker_month = defaultdict(lambda: defaultdict(float))
    
    # 2. Manual Dividends
    for t in transactions:
        if t.transaction_type == TransactionType.DIVIDEND:
            val = get_tx_value_pln(t)
            m_str = pd.Timestamp(t.transaction_date).strftime('%Y-%m')
            dividends_by_month[m_str] += val
            dividends_by_ticker_month[t.asset.ticker][m_str] += val
            dividends_by_ticker_month[t.asset.ticker]['total'] += val

    # 3. Automatic Dividends (YF)
    transactions_sorted = sorted(transactions, key=lambda t: t.transaction_date)
    start_date = transactions_sorted[0].transaction_date
    end_date = pd.Timestamp.today().date()
    
    try:
        all_tickers = sorted({t.asset.ticker for t in transactions})
        div_map = get_dividends_for_tickers(all_tickers, start_date, end_date)
        
        # Build transactions by ticker for quick qty lookup
        tx_by_ticker = {}
        for t in transactions:
            tx_by_ticker.setdefault(t.asset.ticker, []).append(t)
        # Sort transactions per ticker by date (already sorted generally, but ensure per ticker)
        for tkr in tx_by_ticker:
            tx_by_ticker[tkr].sort(key=lambda tr: tr.transaction_date)

        for tkr, series in (div_map or {}).items():
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
                
                # Check if holding > 0
                if qty > 0 and div_ps and float(div_ps) != 0.0:
                    amount = qty * float(div_ps)
                    m_str = pd.Timestamp(dt).strftime('%Y-%m')
                    
                    dividends_by_month[m_str] += amount
                    dividends_by_ticker_month[tkr][m_str] += amount
                    dividends_by_ticker_month[tkr]['total'] += amount
    except Exception as e:
        print(f"Error calculating auto dividends: {e}")

    # 4. Format Output
    
    # Chart Data: Sorted by month
    sorted_months = sorted(dividends_by_month.keys())
    chart_data = [{'month': m, 'value': dividends_by_month[m]} for m in sorted_months]
    
    # Table Data: Ticker rows
    # We need a list of all unique months encountered for columns?
    # Or just return the map and let frontend handle?
    # Frontend needs rows.
    # Let's return list of row objects.
    
    table_data = []
    for tkr, data in dividends_by_ticker_month.items():
        row = {'ticker': tkr, 'total': data['total'], 'months': {}}
        for m, val in data.items():
            if m != 'total':
                row['months'][m] = val
        table_data.append(row)
        
    table_data.sort(key=lambda x: x['total'], reverse=True)
    
    return {
        'chart_data': chart_data,
        'table_data': table_data,
        'all_months': sorted_months
    }

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
    Oblicza stopę zwrotu portfela w czasie.

    Metoda: Modified Dietz (przybliżenie TWR uwzględniające timing przepływów)
    ROI = (Wartość końcowa - Wartość początkowa - Przepływy netto) / (Wartość początkowa + Ważone przepływy)

    Returns:
        Lista słowników z kluczami: 'date', 'rate_of_return', 'market_value', 'invested'
    """
    print(f"\n=== Rozpoczynam obliczanie ROI dla portfela {portfolio_id} ===")

    # Pobierz wszystkie transakcje
    transactions = session.query(Transaction).filter_by(
        portfolio_id=portfolio_id
    ).order_by(Transaction.transaction_date).all()

    if not transactions:
        print("Brak transakcji!")
        return []

    print(f"Znaleziono {len(transactions)} transakcji")

    # Zakres dat
    start_date = transactions[0].transaction_date
    end_date = pd.Timestamp.today().date()
    print(f"Okres: {start_date} - {end_date}")

    # Pobierz unikalne tickery
    asset_ids = session.query(Transaction.asset_id).filter_by(
        portfolio_id=portfolio_id
    ).distinct().all()
    tickers = []
    for asset_id in asset_ids:
        ticker = session.query(Asset.ticker).filter_by(id=asset_id[0]).scalar()
        if ticker:
            tickers.append(ticker)

    print(f"Tickery w portfelu: {tickers}")

    if not tickers:
        print("Brak tickerów!")
        return []

    # Przygotuj dane walutowe
    try:
        currency_by_ticker = {t: get_currency_for_ticker(t) for t in tickers}
        currencies = sorted({c for c in currency_by_ticker.values() if c != "PLN"})
        fx_series_map = _fetch_fx_series(currencies, start_date,
                                         end_date) if currencies else {}
        print(f"Pobrano kursy walut dla: {currencies}")
    except Exception as e:
        print(f"Błąd pobierania kursów walut: {e}")
        currency_by_ticker = {t: "PLN" for t in tickers}
        fx_series_map = {}

    # Pobierz historyczne ceny dla wszystkich tickerów
    print("Pobieram historyczne ceny...")
    historical_prices = get_historical_prices_for_tickers(tickers, start_date, end_date)

    print(f"DEBUG: Otrzymane dane cenowe dla {len(historical_prices)} tickerów")
    for ticker, prices in historical_prices.items():
        if prices:
            print(f"  {ticker}: {len(prices)} punktów cenowych")
            first_date = min(prices.keys())
            last_date = max(prices.keys())
            print(f"    Zakres: {first_date} - {last_date}")
            print(f"    Przykładowa cena: {prices[last_date]}")
        else:
            print(f"  {ticker}: BRAK DANYCH!")

    # Funkcja pomocnicza do konwersji ceny na PLN
    def convert_to_pln(price, ticker, date):
        """Konwertuje cenę na PLN używając kursu z danego dnia"""
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

    # Funkcja do pobierania ceny z danego dnia lub wcześniejszej
    def get_price_on_or_before(ticker, date):
        """Pobiera cenę w PLN z danego dnia lub najbliższą wcześniejszą"""
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

    # Utwórz zakres dat (dzienne)
    date_range = pd.date_range(start=start_date, end=end_date, freq='D')

    # Agreguj przepływy pieniężne według dat (w PLN)
    cash_flows_by_date = defaultdict(float)

    print("\nPrzetwarzam transakcje:")
    for t in transactions:
        date = t.transaction_date
        ticker = t.asset.ticker
        print(
            f"  {date}: {t.transaction_type.value} {t.quantity} x {ticker} @ {t.price}")

        price_pln = convert_to_pln(t.price, ticker, date)
        gross = float(t.quantity) * price_pln
        commission = float(t.commission or 0.0)

        if t.transaction_type == TransactionType.BUY:
            # Kupno = wydatek (wartość ujemna)
            cash_flow = -(gross + commission)
            cash_flows_by_date[date] += cash_flow
            print(f"    Wydatek: {cash_flow:.2f} PLN (cena PLN: {price_pln:.2f})")
        elif t.transaction_type == TransactionType.SELL:
            # Sprzedaż = wpływ (wartość dodatnia)
            cash_flow = (gross - commission)
            cash_flows_by_date[date] += cash_flow
            print(f"    Wpływ: {cash_flow:.2f} PLN (cena PLN: {price_pln:.2f})")

    print(f"\nDni z transakcjami: {len(cash_flows_by_date)}")
    total_flows = sum(cash_flows_by_date.values())
    print(f"Suma przepływów: {total_flows:.2f} PLN")

    # Śledź stan portfela dzień po dniu
    holdings = defaultdict(float)  # ticker -> ilość
    results = []

    cumulative_invested = 0.0  # Skumulowany kapitał zainwestowany (netto)

    days_with_value = 0
    for date in date_range:
        date_obj = date.date()

        # Zastosuj transakcje z tego dnia
        for t in [tr for tr in transactions if tr.transaction_date == date_obj]:
            if t.transaction_type == TransactionType.BUY:
                holdings[t.asset.ticker] += t.quantity
            elif t.transaction_type == TransactionType.SELL:
                holdings[t.asset.ticker] -= t.quantity

        # Dodaj przepływy pieniężne z tego dnia do zainwestowanego kapitału
        if date_obj in cash_flows_by_date:
            cumulative_invested += cash_flows_by_date[date_obj]

        # Oblicz bieżącą wartość rynkową portfela
        market_value = 0.0
        for ticker, qty in holdings.items():
            if qty > 0:
                price = get_price_on_or_before(ticker, date)
                if price is not None and price > 0:
                    market_value += qty * price

        if market_value > 0:
            days_with_value += 1

        # Oblicz ROI: (wartość bieżąca - kapitał zainwestowany) / kapitał zainwestowany * 100
        if cumulative_invested > 0:
            roi = ((market_value - cumulative_invested) / cumulative_invested) * 100.0
        else:
            roi = 0.0

        results.append({
            'date': date,
            'market_value': market_value,
            'invested': cumulative_invested,
            'rate_of_return': roi
        })

    print(f"\nObliczono wartości dla {len(results)} dni")
    print(f"Dni z wartością > 0: {days_with_value}")

    if results:
        print(f"Kapitał zainwestowany: {results[-1]['invested']:.2f} PLN")
        print(f"Wartość rynkowa: {results[-1]['market_value']:.2f} PLN")
        print(f"ROI: {results[-1]['rate_of_return']:.2f}%")

    # Utwórz DataFrame i agreguj do tygodni
    df = pd.DataFrame(results)
    df['date'] = pd.to_datetime(df['date'])

    # Forward fill wartości rynkowych (weekendy, święta)
    df['market_value'] = df['market_value'].replace(0, pd.NA).ffill().fillna(0)

    # Przelicz ROI po forward fill
    df['rate_of_return'] = df.apply(
        lambda row: ((row['market_value'] - row['invested']) / row['invested'] * 100.0)
        if row['invested'] > 0 else 0.0,
        axis=1
    )

    # Agregacja tygodniowa (ostatnia wartość z tygodnia)
    df_weekly = df.set_index('date').resample('W-MON').last().reset_index()

    # Formatuj wyniki
    roi_data = []
    for _, row in df_weekly.iterrows():
        roi_data.append({
            'date': row['date'].strftime('%Y-%m-%d'),
            'rate_of_return': float(row['rate_of_return']) if pd.notna(
                row['rate_of_return']) else 0.0,
            'market_value': float(row['market_value']) if pd.notna(
                row['market_value']) else 0.0,
            'invested': float(row['invested']) if pd.notna(row['invested']) else 0.0
        })

    print(f"\nZwracam {len(roi_data)} punktów dla wykresu")
    if roi_data:
        print(f"Pierwszy punkt: {roi_data[0]}")
        print(f"Ostatni punkt: {roi_data[-1]}")

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

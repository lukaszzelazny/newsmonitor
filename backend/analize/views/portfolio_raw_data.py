"""
Endpoint /api/portfolio/raw_data

Returns all raw data needed by a React/Expo frontend to calculate
portfolio metrics locally (ROI, unrealized PnL, market value, etc.)
without needing extra market-data access.

Data returned:
  - transactions  : list of all transactions (with PLN values pre-calculated)
  - price_history : dict  ticker -> [{date, close}]  (historical prices in PLN)
  - current_prices: dict  ticker -> float  (latest price in PLN)
  - prev_prices   : dict  ticker -> float  (previous trading day price in PLN)
  - dividends     : dict  ticker -> [{date, amount_per_share}]
  - portfolio     : {id, name, broker, description}
"""

from datetime import timedelta
from flask import Blueprint, jsonify, request
import pandas as pd
import math

from backend.database import Database, Portfolio, Asset, Transaction, TransactionType
from backend.portfolio.analysis import get_holdings
from backend.tools.price_fetcher import (
    get_historical_prices_for_tickers,
    get_current_prices,
    get_dividends_for_tickers,
)
from backend.utils import clean_nan_in_data

portfolio_raw_bp = Blueprint('portfolio_raw', __name__)


def _get_portfolio(session, name):
    if name:
        return session.query(Portfolio).filter_by(name=name).first()
    preferred = session.query(Portfolio).filter(Portfolio.name.in_(['XTB', 'XTB IKE'])).order_by(Portfolio.id.desc()).first()
    if preferred:
        return preferred
    portfolios = session.query(Portfolio).all()
    if portfolios:
        return sorted(portfolios, key=lambda p: len(p.transactions or []), reverse=True)[0]
    return session.query(Portfolio).first()


@portfolio_raw_bp.route('/api/portfolio/raw_data')
def portfolio_raw_data():
    """
    Returns all raw data required for the frontend to compute portfolio metrics.

    Query params:
      - name             : portfolio name (optional)
      - excluded_tickers : comma-separated tickers to exclude (optional)
    """
    db = Database()
    session = db.Session()
    try:
        portfolio_name = request.args.get('portfolio_name', default=None, type=str)
        excluded_raw = request.args.get('excluded_tickers', '')
        excluded = set(t.strip() for t in excluded_raw.split(',') if t.strip())

        portfolio = _get_portfolio(session, portfolio_name)
        if not portfolio:
            if portfolio_name:
                return jsonify({'error': f'Portfolio "{portfolio_name}" not found'}), 400
            return jsonify({'error': 'No portfolio found in database'}), 404

        # ── 1. Transactions ──────────────────────────────────────────────────
        all_transactions = (
            session.query(Transaction)
            .filter_by(portfolio_id=portfolio.id)
            .order_by(Transaction.transaction_date)
            .all()
        )
        transactions = [t for t in all_transactions if t.asset.ticker not in excluded]

        def _tx_value_pln(t):
            if t.transaction_type == TransactionType.BUY:
                if t.purchase_value_pln and float(t.purchase_value_pln) > 0:
                    return float(t.purchase_value_pln)
                return float(t.quantity) * float(t.price) + float(t.commission or 0)
            if t.transaction_type == TransactionType.SELL:
                if t.sale_value_pln and float(t.sale_value_pln) > 0:
                    return float(t.sale_value_pln)
                return float(t.quantity) * float(t.price) - float(t.commission or 0)
            if t.transaction_type in (TransactionType.DEPOSIT, TransactionType.WITHDRAWAL):
                if t.purchase_value_pln is not None:
                    return float(t.purchase_value_pln)
                return float(t.quantity)
            if t.transaction_type == TransactionType.DIVIDEND:
                if t.sale_value_pln is not None:
                    return float(t.sale_value_pln)
                return float(t.price) if t.price else 0.0
            return 0.0

        tx_list = []
        for t in transactions:
            tx_list.append({
                'id': t.id,
                'ticker': t.asset.ticker,
                'type': t.transaction_type.value,
                'quantity': float(t.quantity),
                'price': float(t.price),              # original price in original currency
                'value_pln': _tx_value_pln(t),        # already in PLN (key field)
                'commission': float(t.commission or 0),
                'date': t.transaction_date.strftime('%Y-%m-%d'),
            })

        # ── 2. Current holdings & tickers ────────────────────────────────────
        holdings = get_holdings(session, portfolio.id)  # ticker -> qty
        # All unique non-PLN tickers ever in the portfolio
        all_tickers = sorted({
            t.asset.ticker for t in transactions
            if t.asset.ticker != 'PLN'
        })
        active_tickers = [tk for tk in holdings if tk != 'PLN']

        # ── 3. Current & previous prices (PLN) ───────────────────────────────
        current_prices_map = get_current_prices(all_tickers, active_tickers=active_tickers) if all_tickers else {}

        # Fetch last 10 days of history to reliably get yesterday's close
        end_date = pd.Timestamp.today().date()
        hist_start = end_date - timedelta(days=10)
        recent_hist = get_historical_prices_for_tickers(all_tickers, hist_start, end_date, session=session) if all_tickers else {}

        prev_prices_map = {}
        for tkr, price_series in recent_hist.items():
            if not price_series:
                continue
            dates = sorted(price_series.keys())
            if len(dates) >= 2:
                # second-to-last trading day
                prev_prices_map[tkr] = float(price_series[dates[-2]])
            elif len(dates) == 1:
                prev_prices_map[tkr] = float(price_series[dates[0]])

        # ── 4. Full historical prices (from first transaction) ───────────────
        if transactions:
            hist_from = transactions[0].transaction_date
        else:
            hist_from = end_date

        full_hist = get_historical_prices_for_tickers(
            all_tickers, hist_from, end_date, session=session
        ) if all_tickers else {}

        price_history_out = {tkr: [] for tkr in all_tickers}  # ensure every ticker key present
        for tkr, price_series in full_hist.items():
            price_history_out[tkr] = [
                {'date': d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10],
                 'close': float(p)}
                for d, p in sorted(price_series.items())
                if p is not None and not (isinstance(p, float) and math.isnan(p))
            ]

        # ── 5. Dividends ─────────────────────────────────────────────────────
        dividends_out = {tkr: [] for tkr in all_tickers}  # ensure every ticker key present
        try:
            if all_tickers and transactions:
                div_map = get_dividends_for_tickers(all_tickers, hist_from, end_date)
                for tkr, series in (div_map or {}).items():
                    if series is None or series.empty:
                        continue
                    dividends_out[tkr] = [
                        {'date': d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10],
                         'amount_per_share': float(v)}
                        for d, v in series.items()
                        if v and float(v) != 0.0
                    ]
        except Exception as e:
            print(f"Warning: dividend fetch failed: {e}")

        # ── 6. Build response ────────────────────────────────────────────────
        result = {
            'portfolio': {
                'id': portfolio.id,
                'name': portfolio.name,
                'broker': portfolio.broker,
                'description': portfolio.description,
            },
            'transactions': tx_list,
            'current_prices': {
                k: float(v) for k, v in current_prices_map.items()
                if v is not None and not (isinstance(v, float) and math.isnan(v))
            },
            'prev_prices': prev_prices_map,
            'price_history': price_history_out,
            'dividends': dividends_out,
        }

        return jsonify(clean_nan_in_data(result))

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

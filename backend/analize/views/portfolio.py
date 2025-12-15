from flask import Blueprint, jsonify, request
from backend.database import Database, Portfolio, Asset, Transaction
from backend.portfolio.analysis import calculate_portfolio_overview, calculate_roi_over_time, calculate_portfolio_value_over_time, calculate_monthly_profit

portfolio_bp = Blueprint('portfolio', __name__)


def _get_portfolio(session, name: str | None):
    if name:
        return session.query(Portfolio).filter_by(name=name).first()

    # Prefer explicitly named portfolios first
    preferred = session.query(Portfolio).filter(Portfolio.name.in_(['XTB', 'XTB IKE'])).order_by(Portfolio.id.desc()).first()
    if preferred:
        return preferred

    # Fallback: pick portfolio with the highest number of transactions
    portfolios = session.query(Portfolio).all()
    if portfolios:
        portfolios_sorted = sorted(portfolios, key=lambda p: len(p.transactions or []), reverse=True)
        return portfolios_sorted[0]

    # Last resort
    return session.query(Portfolio).first()


@portfolio_bp.route('/api/portfolio/overview')
def portfolio_overview():
    """
    Zwraca podsumowanie portfela oparte na calculate_portfolio_overview.
    Parametry (opcjonalne):
      - name: nazwa portfela (jeśli brak, wybierany jest pierwszy z bazy)
    """
    db = Database()
    session = db.Session()
    try:
        name = request.args.get('name', default=None, type=str)
        portfolio = _get_portfolio(session, name)
        if not portfolio:
            return jsonify({'error': 'Brak portfela w bazie'}), 404

        overview = calculate_portfolio_overview(session, portfolio.id) or {}
        overview['portfolio'] = {
            'id': portfolio.id,
            'name': portfolio.name,
            'broker': portfolio.broker,
            'description': portfolio.description,
        }
        return jsonify(overview)
    except Exception as e:
        print(f"Error in /api/portfolio/overview: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@portfolio_bp.route('/api/portfolio/value_over_time')
def portfolio_value_over_time():
    """
    Zwraca historyczną serię wartości portfela z calculate_portfolio_value_over_time.
    Parametry (opcjonalne):
      - name: nazwa portfela (jeśli brak, wybierany jest pierwszy z bazy)
    """
    db = Database()
    session = db.Session()
    try:
        name = request.args.get('name', default=None, type=str)
        portfolio = _get_portfolio(session, name)
        if not portfolio:
            return jsonify([])

        series = calculate_portfolio_value_over_time(session, portfolio.id) or []
        return jsonify(series)
    except Exception as e:
        print(f"Error in /api/portfolio/value_over_time: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@portfolio_bp.route('/api/portfolio/roi')
def portfolio_roi():
    """
    Zwraca tygodniową serię ROI (MWR) portfela z calculate_roi_over_time.
    Parametry (opcjonalne):
      - name: nazwa portfela (jeśli brak, wybierany jest pierwszy z bazy)
    """
    db = Database()
    session = db.Session()
    try:
        name = request.args.get('name', default=None, type=str)
        portfolio = _get_portfolio(session, name)
        if not portfolio:
            return jsonify([])

        series = calculate_roi_over_time(session, portfolio.id) or []
        return jsonify(series)
    except Exception as e:
        print(f"Error in /api/portfolio/roi: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@portfolio_bp.route('/api/portfolio/monthly_profit')
def portfolio_monthly_profit():
    """
    Zwraca miesięczne zyski portfela.
    """
    db = Database()
    session = db.Session()
    try:
        name = request.args.get('name', default=None, type=str)
        portfolio = _get_portfolio(session, name)
        if not portfolio:
            return jsonify([])

        stats = calculate_monthly_profit(session, portfolio.id) or []
        return jsonify(stats)
    except Exception as e:
        print(f"Error in /api/portfolio/monthly_profit: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@portfolio_bp.route('/api/portfolio/all_assets_summary')
def portfolio_all_assets_summary():
    """
    Zwraca podsumowanie wszystkich aktywów (tickerów) kiedykolwiek obecnych w portfelu,
    z danymi historycznymi (zrealizowany zysk, niezrealizowany, ilość transakcji, itp.)
    """
    db = Database()
    session = db.Session()
    try:
        name = request.args.get('name', default=None, type=str)
        portfolio = _get_portfolio(session, name)
        if not portfolio:
            return jsonify([])

        from backend.portfolio.analysis import calculate_all_assets_summary
        summary = calculate_all_assets_summary(session, portfolio.id) or []
        return jsonify(summary)
    except Exception as e:
        print(f"Error in /api/portfolio/all_assets_summary: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@portfolio_bp.route('/api/portfolio/transactions')
def portfolio_transactions():
    """
    Zwraca listę transakcji (buy/sell) dla zadanego tickera.
    Parametry:
      - ticker: symbol tickera (np. 'PKN')
    """
    ticker = request.args.get('ticker', default=None, type=str)
    if not ticker:
        return jsonify([])

    db = Database()
    session = db.Session()
    try:

        # --- ZMODYFIKOWANA LOGIKA FILTROWANIA ---

        base_pl = f'{ticker}.PL'
        base_us = f'{ticker}.US'
        filter_conditions = (Asset.ticker == ticker) | (Asset.ticker == base_pl) | (Asset.ticker == base_us)

        # Stosujemy zdefiniowany warunek filtrowania
        rows = session.query(Transaction).join(Asset).filter(
            filter_conditions).order_by(Transaction.transaction_date).all()

        # --- KONIEC ZMODYFIKOWANEJ LOGIKI FILTROWANIA ---

        result = []
        for t in rows:
            result.append({
                'id': t.id,
                'transaction_type': t.transaction_type.value if hasattr(
                    t.transaction_type, 'value') else str(t.transaction_type),
                'quantity': float(t.quantity) if t.quantity is not None else None,
                'price': float(t.price) if t.price is not None else None,
                'transaction_date': t.transaction_date.strftime('%Y-%m-%d') if hasattr(
                    t.transaction_date, 'strftime') else str(t.transaction_date),
            })
        return jsonify(result)
    except Exception as e:
        print(f"Error in /api/portfolio/transactions: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

from datetime import datetime
from flask import Blueprint, jsonify, request
from backend.database import Database, Portfolio, Asset, Transaction, TransactionType
from backend.portfolio.analysis import calculate_portfolio_overview, calculate_roi_over_time, calculate_portfolio_value_over_time, calculate_monthly_profit
from backend.utils import clean_nan_in_data

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

def _get_excluded_tickers(req):
    excluded = req.args.get('excluded_tickers', '')
    if not excluded:
        return set()
    return set(t.strip() for t in excluded.split(',') if t.strip())


@portfolio_bp.route('/api/portfolio/overview')
def portfolio_overview():
    """
    Zwraca podsumowanie portfela oparte na calculate_portfolio_overview.
    Parametry (opcjonalne):
      - name: nazwa portfela (jeśli brak, wybierany jest pierwszy z bazy)
      - excluded_tickers: lista tickerów do wykluczenia (oddzielona przecinkami)
    """
    db = Database()
    session = db.Session()
    try:
        name = request.args.get('name', default=None, type=str)
        excluded = _get_excluded_tickers(request)
        
        portfolio = _get_portfolio(session, name)
        if not portfolio:
            return jsonify({'error': 'Brak portfela w bazie'}), 404

        overview = calculate_portfolio_overview(session, portfolio.id, excluded_tickers=excluded) or {}
        overview['portfolio'] = {
            'id': portfolio.id,
            'name': portfolio.name,
            'broker': portfolio.broker,
            'description': portfolio.description,
        }
        # Clean NaN values before returning JSON
        return jsonify(clean_nan_in_data(overview))
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
      - excluded_tickers: lista tickerów do wykluczenia
    """
    db = Database()
    session = db.Session()
    try:
        name = request.args.get('name', default=None, type=str)
        excluded = _get_excluded_tickers(request)
        
        portfolio = _get_portfolio(session, name)
        if not portfolio:
            return jsonify([])

        series = calculate_portfolio_value_over_time(session, portfolio.id, excluded_tickers=excluded) or []
        # Clean NaN values before returning JSON
        return jsonify(clean_nan_in_data(series))
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
      - excluded_tickers: lista tickerów do wykluczenia
    """
    db = Database()
    session = db.Session()
    try:
        name = request.args.get('name', default=None, type=str)
        excluded = _get_excluded_tickers(request)
        
        portfolio = _get_portfolio(session, name)
        if not portfolio:
            return jsonify([])

        series = calculate_roi_over_time(session, portfolio.id, excluded_tickers=excluded) or []
        # Clean NaN values before returning JSON
        return jsonify(clean_nan_in_data(series))
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
        excluded = _get_excluded_tickers(request)
        
        portfolio = _get_portfolio(session, name)
        if not portfolio:
            return jsonify([])

        stats = calculate_monthly_profit(session, portfolio.id, excluded_tickers=excluded) or []
        # Clean NaN values before returning JSON
        return jsonify(clean_nan_in_data(stats))
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
        # Clean NaN values before returning JSON
        return jsonify(clean_nan_in_data(summary))
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
        # Clean NaN values before returning JSON (though unlikely in transactions, we do it for consistency)
        return jsonify(clean_nan_in_data(result))
    except Exception as e:
        print(f"Error in /api/portfolio/transactions: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@portfolio_bp.route('/api/portfolio/transaction', methods=['POST'])
def add_transaction():
    """
    Dodaje nową transakcję do portfela.
    Payload: {
        'ticker': str,
        'date': str (YYYY-MM-DD),
        'type': str (BUY/SELL),
        'quantity': float,
        'price': float, # cena w oryginalnej walucie
        'commission': float (optional, default 0),
        'portfolio_id': int (opcjonalne)
    }
    """
    db = Database()
    session = db.Session()
    try:
        data = request.json
        ticker_symbol = data.get('ticker')
        date_str = data.get('date')
        tx_type_str = data.get('type')
        try:
            quantity = float(data.get('quantity'))
            price = float(data.get('price'))
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid quantity or price'}), 400
            
        portfolio_id = data.get('portfolio_id')
        commission = float(data.get('commission', 0.0))

        if not all([ticker_symbol, date_str, tx_type_str]):
             return jsonify({'error': 'Missing required fields'}), 400

        # Get Portfolio
        if portfolio_id:
            portfolio = session.query(Portfolio).get(portfolio_id)
        else:
            portfolio = _get_portfolio(session, None)
        
        if not portfolio:
            return jsonify({'error': 'Portfolio not found'}), 404

        # Get or Create Asset
        from backend.tools.price_fetcher import get_yf_symbol, get_currency_for_ticker, get_fx_rate_for_date
        
        # Clean ticker
        ticker_symbol = ticker_symbol.strip().upper()
        
        asset = session.query(Asset).filter_by(ticker=ticker_symbol).first()
        if not asset:
            # Check if it looks like a commodity or just default to stock
            a_type = 'commodity' if ticker_symbol in ['GC=F', 'XAUUSD=X', 'SI=F'] else 'stock'
            asset = Asset(ticker=ticker_symbol, name=ticker_symbol, asset_type=a_type)
            session.add(asset)
            session.flush()

        # Parse Date
        try:
            tx_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        # Determine Currency and FX Rate
        yf_symbol = get_yf_symbol(ticker_symbol)
        
        payload_currency = data.get('currency', 'AUTO')
        if payload_currency and payload_currency != 'AUTO':
            currency = payload_currency
        else:
            currency = get_currency_for_ticker(yf_symbol)
        
        fx_rate = 1.0
        if currency != 'PLN':
            fx_rate = get_fx_rate_for_date(currency, tx_date)
            print(f"Using FX Rate {currency}->PLN for {tx_date}: {fx_rate}")
        
        # Calculate Value in PLN
        purchase_value_pln = None
        sale_value_pln = None
        commission_pln = commission * fx_rate
        
        tx_type = TransactionType.BUY if tx_type_str.upper() == 'BUY' else TransactionType.SELL
        
        if tx_type == TransactionType.BUY:
            # (Price * Qty + Comm) * FX
            purchase_value_pln = (price * quantity + commission) * fx_rate
        else:
            # (Price * Qty - Comm) * FX
            sale_value_pln = (price * quantity - commission) * fx_rate

        transaction = Transaction(
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            transaction_type=tx_type,
            quantity=quantity,
            price=price,
            transaction_date=tx_date,
            commission=commission_pln,
            purchase_value_pln=purchase_value_pln,
            sale_value_pln=sale_value_pln
        )
        
        session.add(transaction)
        session.commit()
        
        return jsonify({'message': 'Transaction added', 'id': transaction.id})

    except Exception as e:
        session.rollback()
        print(f"Error adding transaction: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

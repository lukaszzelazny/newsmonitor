from datetime import datetime
from flask import Blueprint, jsonify, request
import os
from backend.database import Database, Portfolio, Asset, Transaction, TransactionType
from backend.portfolio.analysis import calculate_portfolio_overview, calculate_roi_over_time, calculate_portfolio_value_over_time, calculate_monthly_profit, calculate_dividend_stats
from backend.utils import clean_nan_in_data
from backend.database import AssetPriceHistory
from backend.tools.price_fetcher import get_yf_symbol, get_currency_for_ticker, fx_symbol_to_pln, _fetch_fx_series, fetch_price_history_with_exchange
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

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


@portfolio_bp.route('/api/config')
def get_config():
    excluded_str = os.getenv('DEFAULT_EXCLUDED_TICKERS', '')
    excluded = [t.strip() for t in excluded_str.split(',') if t.strip()]
    return jsonify({
        'default_excluded_tickers': excluded,
        'default_theme': os.getenv('DEFAULT_THEME', 'dark')
    })


@portfolio_bp.route('/api/portfolios', methods=['GET'])
def list_portfolios():
    """
    Zwraca listę wszystkich portfeli.
    """
    db = Database()
    session = db.Session()
    try:
        portfolios = session.query(Portfolio).order_by(Portfolio.id).all()
        result = []
        for p in portfolios:
            tx_count = session.query(Transaction).filter_by(portfolio_id=p.id).count()
            result.append({
                'id': p.id,
                'name': p.name,
                'broker': p.broker,
                'description': p.description,
                'transaction_count': tx_count,
            })
        return jsonify(result)
    except Exception as e:
        print(f"Error in /api/portfolios: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@portfolio_bp.route('/api/portfolios', methods=['POST'])
def create_portfolio():
    """
    Tworzy nowy portfel.
    Payload: { 'name': str, 'broker': str (opcjonalne), 'description': str (opcjonalne) }
    """
    db = Database()
    session = db.Session()
    try:
        data = request.json or {}
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'error': 'Nazwa portfela jest wymagana'}), 400

        existing = session.query(Portfolio).filter_by(name=name).first()
        if existing:
            return jsonify({'error': f'Portfel o nazwie "{name}" już istnieje'}), 409

        portfolio = Portfolio(
            name=name,
            broker=data.get('broker', '').strip() or None,
            description=data.get('description', '').strip() or None,
        )
        session.add(portfolio)
        session.commit()
        return jsonify({
            'id': portfolio.id,
            'name': portfolio.name,
            'broker': portfolio.broker,
            'description': portfolio.description,
            'transaction_count': 0,
        }), 201
    except Exception as e:
        session.rollback()
        print(f"Error in POST /api/portfolios: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


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


@portfolio_bp.route('/api/portfolio/dividend_stats')
def portfolio_dividend_stats():
    """
    Zwraca statystyki dywidend.
    """
    db = Database()
    session = db.Session()
    try:
        name = request.args.get('name', default=None, type=str)
        excluded = _get_excluded_tickers(request)
        
        portfolio = _get_portfolio(session, name)
        if not portfolio:
            return jsonify({})

        stats = calculate_dividend_stats(session, portfolio.id, excluded_tickers=excluded) or {}
        return jsonify(clean_nan_in_data(stats))
    except Exception as e:
        print(f"Error in /api/portfolio/dividend_stats: {e}")
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
    Zwraca listę transakcji.
    Parametry:
      - name: (opcjonalny) nazwa portfela
      - ticker: (opcjonalny) symbol tickera
    """
    ticker = request.args.get('ticker', default=None, type=str)
    name = request.args.get('name', default=None, type=str)

    db = Database()
    session = db.Session()
    try:
        rows = []
        if ticker:
            base_pl = f'{ticker}.PL'
            base_us = f'{ticker}.US'
            filter_conditions = (Asset.ticker == ticker) | (Asset.ticker == base_pl) | (Asset.ticker == base_us)
            query = session.query(Transaction).join(Asset).filter(filter_conditions)
            if name:
                portfolio = _get_portfolio(session, name)
                if portfolio:
                    query = query.filter(Transaction.portfolio_id == portfolio.id)
            rows = query.order_by(Transaction.transaction_date.desc()).all()
        else:
            portfolio = _get_portfolio(session, name)
            if portfolio:
                rows = session.query(Transaction).filter_by(
                    portfolio_id=portfolio.id
                ).order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).limit(200).all()
            else:
                rows = session.query(Transaction).order_by(
                    Transaction.transaction_date.desc(), Transaction.id.desc()
                ).limit(200).all()

        result = []
        for t in rows:
            ticker_name = t.asset.ticker if t.asset else 'Unknown'
            result.append({
                'id': t.id,
                'ticker': ticker_name,
                'transaction_type': t.transaction_type.value if hasattr(
                    t.transaction_type, 'value') else str(t.transaction_type),
                'quantity': float(t.quantity) if t.quantity is not None else None,
                'price': float(t.price) if t.price is not None else None,
                'transaction_date': t.transaction_date.strftime('%Y-%m-%d') if hasattr(
                    t.transaction_date, 'strftime') else str(t.transaction_date),
            })
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
        
        tx_type_str = tx_type_str.upper()
        if tx_type_str == 'BUY':
            tx_type = TransactionType.BUY
        elif tx_type_str == 'SELL':
            tx_type = TransactionType.SELL
        elif tx_type_str == 'DIVIDEND':
            tx_type = TransactionType.DIVIDEND
        elif tx_type_str == 'DEPOSIT':
            tx_type = TransactionType.DEPOSIT
        elif tx_type_str == 'WITHDRAWAL':
            tx_type = TransactionType.WITHDRAWAL
        else:
            return jsonify({'error': 'Invalid transaction type'}), 400
        
        if tx_type == TransactionType.BUY:
            # (Price * Qty + Comm) * FX
            purchase_value_pln = (price * quantity + commission) * fx_rate
        elif tx_type == TransactionType.SELL:
            # (Price * Qty - Comm) * FX
            sale_value_pln = (price * quantity - commission) * fx_rate
        elif tx_type == TransactionType.DIVIDEND:
            sale_value_pln = (price - commission) * fx_rate
        elif tx_type in [TransactionType.DEPOSIT, TransactionType.WITHDRAWAL]:
            # For Cash ops, Quantity is Amount. Price is 1.0.
            # Value is Amount * FX (if currency != PLN, but usually PLN)
            purchase_value_pln = quantity * fx_rate
            # commission on deposit/withdrawal?
            if commission > 0:
                 commission_pln = commission * fx_rate
                 # Net value might be adjusted? 
                 # Usually deposit 1000 - 0 comm = 1000.
                 # Withdrawal 1000 - 0 comm = 1000.
                 # If withdrawal fee exists?
                 # Handled by commission field.
                 # Logic in analysis.py uses val = purchase_value_pln (or qty).
                 # So we should store the GROSS amount in value or NET?
                 # If I withdraw 1000, and pay 10 fee.
                 # Cash balance -1000? Or -1010?
                 # Usually fee is deducted from account?
                 # Let's assume Amount is the change in cash. Commission is just for record.

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


@portfolio_bp.route('/api/portfolio/transaction/<int:tx_id>', methods=['DELETE'])
def delete_transaction(tx_id):
    """
    Usuwa transakcję.
    """
    db = Database()
    session = db.Session()
    try:
        transaction = session.query(Transaction).get(tx_id)
        if not transaction:
            return jsonify({'error': 'Transaction not found'}), 404
        
        session.delete(transaction)
        session.commit()
        return jsonify({'message': 'Transaction deleted'})
    except Exception as e:
        session.rollback()
        print(f"Error deleting transaction: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@portfolio_bp.route('/api/portfolio/update_prices', methods=['POST'])
def update_portfolio_prices():
    """
    Updates prices for all assets currently held in the portfolio.
    """
    db = Database()
    session = db.Session()
    try:
        # Get portfolio
        name = request.json.get('name') if request.json else None
        portfolio = _get_portfolio(session, name)
        
        if not portfolio:
            return jsonify({'error': 'Portfolio not found'}), 404

        # Identify assets held
        overview = calculate_portfolio_overview(session, portfolio.id)
        
        if not overview or 'assets' not in overview:
             return jsonify({'message': 'No assets in portfolio'}), 200

        assets_to_update = []
        for a in overview['assets']:
             if a['quantity'] > 0: # Only held assets
                 assets_to_update.append(a['ticker'])
        
        updated_count = 0
        
        for ticker in assets_to_update:
            try:
                asset = session.query(Asset).filter_by(ticker=ticker).first()
                if not asset: continue
                
                # Use new function that respects exchange - increase window to 30 days
                print(f"  Fetching prices for {ticker}...")
                df = fetch_price_history_with_exchange(ticker, days=30)
                
                if df is not None and not df.empty:
                    print(f"    Got {len(df)} rows of data")
                    print(f"    Date range: {df.index[0].date()} to {df.index[-1].date()}")
                    
                    # Save to DB
                    rows_added = 0
                    rows_updated = 0
                    for date_idx, row in df.iterrows():
                        date_val = date_idx.date()
                        existing = session.query(AssetPriceHistory).filter(
                            AssetPriceHistory.asset_id == asset.id,
                            AssetPriceHistory.date == date_val
                        ).first()
                        
                        # Handle potential missing/nan values
                        close_val = float(row['Close'])
                        if pd.isna(close_val): continue
                        
                        open_val = float(row['Open']) if 'Open' in row and not pd.isna(row['Open']) else None
                        high_val = float(row['High']) if 'High' in row and not pd.isna(row['High']) else None
                        low_val = float(row['Low']) if 'Low' in row and not pd.isna(row['Low']) else None
                        vol_val = int(row['Volume']) if 'Volume' in row and not pd.isna(row['Volume']) else None
                        
                        if existing:
                            existing.close = close_val
                            if open_val is not None: existing.open = open_val
                            if high_val is not None: existing.high = high_val
                            if low_val is not None: existing.low = low_val
                            if vol_val is not None: existing.volume = vol_val
                            existing.adjusted_close = close_val
                            rows_updated += 1
                        else:
                            new_rec = AssetPriceHistory(
                                asset_id=asset.id,
                                date=date_val,
                                close=close_val,
                                open=open_val,
                                high=high_val,
                                low=low_val,
                                volume=vol_val,
                                adjusted_close=close_val
                            )
                            session.add(new_rec)
                            rows_added += 1
                    
                    print(f"    Added {rows_added} new records, updated {rows_updated} existing")
                    
                    # Also try to get today's price using get_current_price for NewConnect tickers
                    # to ensure we have the latest price even if Stooq history doesn't include today
                    try:
                        from backend.tools.price_fetcher import get_current_price, _get_exchange_for_ticker
                        from datetime import date
                        
                        # Check if ticker is NewConnect
                        exchange = _get_exchange_for_ticker(session, ticker)
                        print(f"    Exchange for {ticker}: {exchange}")
                        if exchange == 'NewConnect':
                            print(f"    Fetching today's price for NewConnect ticker {ticker}...")
                            today_price = get_current_price(ticker)
                            print(f"    Today's price: {today_price}")
                            if today_price is not None:
                                today = date.today()
                                existing_today = session.query(AssetPriceHistory).filter(
                                    AssetPriceHistory.asset_id == asset.id,
                                    AssetPriceHistory.date == today
                                ).first()
                                
                                if not existing_today:
                                    new_today_rec = AssetPriceHistory(
                                        asset_id=asset.id,
                                        date=today,
                                        close=today_price,
                                        open=today_price,
                                        high=today_price,
                                        low=today_price,
                                        volume=0,
                                        adjusted_close=today_price
                                    )
                                    session.add(new_today_rec)
                                    print(f"    Added today's price for {ticker}: {today_price}")
                                    rows_added += 1
                                else:
                                    print(f"    Today's price already exists for {ticker}")
                    except Exception as e:
                        print(f"    Error adding today's price for {ticker}: {e}")
                    
                    updated_count += 1
                    session.commit()
                    print(f"    Committed changes for {ticker}")
                    
            except Exception as e:
                print(f"Error updating {ticker}: {e}")
                session.rollback()

        return jsonify({'message': f'Zaktualizowano ceny dla {updated_count} aktywów', 'count': updated_count})

    except Exception as e:
        print(f"Error in update_portfolio_prices: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

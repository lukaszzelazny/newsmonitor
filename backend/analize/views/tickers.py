import json
from flask import Blueprint, jsonify, request
from sqlalchemy import text
from analize.utils import get_db_engine, get_current_price, parse_price, format_summary, resolve_db_ticker
from backend.tools.price_fetcher import get_yf_symbol, get_currency_for_ticker, fx_symbol_to_pln, _fetch_fx_series
import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd
from backend.database import Database, Asset, AssetPriceHistory

tickers_bp = Blueprint('tickers', __name__)
engine, schema = get_db_engine()

@tickers_bp.route('/api/tickers/<ticker>/fundamental', methods=['POST'])
def fetch_fundamental_data(ticker):
    """Fetch and save fundamental data for a ticker from Yahoo Finance."""
    try:
        # Use existing utility to get correct YF symbol (handles .PL -> .WA conversion)
        yf_ticker = get_yf_symbol(ticker)
        
        # Fetch data
        stock = yf.Ticker(yf_ticker)
        info = stock.info
        
        # Extract indicators
        eps = info.get('trailingEps')
        eps_forward = info.get('forwardEps')
        pe_trailing = info.get('trailingPE')
        pe_forward = info.get('forwardPE')
        revenue = info.get('totalRevenue')
        revenue_growth = info.get('revenueGrowth')
        earnings_growth = info.get('earningsGrowth')
        peg_ratio = info.get('pegRatio')
        market_cap = info.get('marketCap')
        ebitda = info.get('ebitda')
        cash_flow = info.get('freeCashflow')
        profit_margin = info.get('profitMargins')
        
        # Save current data to DB (Delete existing for today to prevent duplicates, then Insert)
        with engine.connect() as conn:
             today = datetime.now().date()
             
             # Delete existing record for today
             delete_query = text(f"""
                DELETE FROM {schema}.fundamental_analysis 
                WHERE ticker = :ticker AND date::date = :today
             """)
             conn.execute(delete_query, {'ticker': ticker, 'today': today})
             
             # Insert new record
             insert_query = text(f"""
                INSERT INTO {schema}.fundamental_analysis 
                (ticker, date, eps, eps_forward, pe_trailing, pe_forward, revenue, revenue_growth, earnings_growth, peg_ratio, market_cap, ebitda, cash_flow, profit_margin)
                VALUES (:ticker, NOW(), :eps, :eps_forward, :pe_trailing, :pe_forward, :revenue, :revenue_growth, :earnings_growth, :peg_ratio, :market_cap, :ebitda, :cash_flow, :profit_margin)
             """)
             conn.execute(insert_query, {
                 'ticker': ticker,
                 'eps': eps,
                 'eps_forward': eps_forward,
                 'pe_trailing': pe_trailing,
                 'pe_forward': pe_forward,
                 'revenue': revenue,
                 'revenue_growth': revenue_growth,
                 'earnings_growth': earnings_growth,
                 'peg_ratio': peg_ratio,
                 'market_cap': market_cap,
                 'ebitda': ebitda,
                 'cash_flow': cash_flow,
                 'profit_margin': profit_margin
             })
             conn.commit()

        # Fetch Historical Data (Financials)
        try:
            financials = stock.financials
            cashflow = stock.cashflow
            
            if not financials.empty:
                # Prepare FX rates if needed
                currency = get_currency_for_ticker(yf_ticker)
                fx_rates = {}
                if currency != 'PLN':
                    dates_list = [pd.to_datetime(d).date() for d in financials.columns]
                    if dates_list:
                        start_d = min(dates_list)
                        end_d = max(dates_list) + timedelta(days=5)
                        fx_ticker_sym = fx_symbol_to_pln(currency)
                        if fx_ticker_sym:
                            fx_map = _fetch_fx_series([currency], start_d, end_d)
                            fx_series = fx_map.get(fx_ticker_sym)
                            if fx_series is not None:
                                fx_rates = {d.date(): val for d, val in fx_series.items()}

                dates = financials.columns
                for date in dates:
                    try:
                        date_val = pd.to_datetime(date).date()
                        
                        # Get FX rate for this date
                        fx_rate = 1.0
                        if currency != 'PLN':
                            # Simple lookup with 5 day tolerance backward
                            for d in range(5):
                                check_date = date_val - timedelta(days=d)
                                if check_date in fx_rates:
                                    fx_rate = float(fx_rates[check_date])
                                    break

                        # Helper to get value and convert
                        def get_val(df, key_primary, key_alt, date_col):
                            val = None
                            if key_primary in df.index: val = df.loc[key_primary, date_col]
                            elif key_alt in df.index: val = df.loc[key_alt, date_col]
                            
                            if val is not None and not pd.isna(val):
                                return float(val) * fx_rate
                            return None

                        rev = get_val(financials, 'Total Revenue', 'TotalRevenue', date)
                        ebitda_hist = get_val(financials, 'EBITDA', 'Normalized EBITDA', date)
                        net_income = get_val(financials, 'Net Income', 'NetIncome', date)
                        eps_hist = get_val(financials, 'Basic EPS', 'Diluted EPS', date)
                        
                        cf_hist = None
                        if not cashflow.empty and date in cashflow.columns:
                            cf_hist = get_val(cashflow, 'Free Cash Flow', 'Operating Cash Flow', date)
                        
                        profit_margin_hist = None
                        if net_income and rev:
                            profit_margin_hist = net_income / rev
                            
                        market_cap_hist = None
                        pe_trailing_hist = None
                        
                        hist = stock.history(start=date, end=date + timedelta(days=5))
                        if not hist.empty:
                            close_price_native = float(hist['Close'].iloc[0])
                            close_price_pln = close_price_native * fx_rate
                            
                            shares = info.get('sharesOutstanding')
                            if shares:
                                market_cap_hist = close_price_pln * shares
                            if eps_hist:
                                pe_trailing_hist = close_price_pln / eps_hist

                        with engine.connect() as conn:
                            # Delete existing for this date to prevent duplicates
                            delete_query = text(f"""
                                DELETE FROM {schema}.fundamental_analysis 
                                WHERE ticker = :ticker AND date::date = :date
                            """)
                            conn.execute(delete_query, {'ticker': ticker, 'date': date_val})
                            
                            # Insert
                            insert_query = text(f"""
                                INSERT INTO {schema}.fundamental_analysis 
                                (ticker, date, eps, pe_trailing, revenue, market_cap, ebitda, cash_flow, profit_margin)
                                VALUES (:ticker, :date, :eps, :pe_trailing, :revenue, :market_cap, :ebitda, :cash_flow, :profit_margin)
                            """)
                            conn.execute(insert_query, {
                                'ticker': ticker,
                                'date': date_val,
                                'eps': eps_hist,
                                'pe_trailing': pe_trailing_hist,
                                'revenue': rev,
                                'market_cap': market_cap_hist,
                                'ebitda': ebitda_hist,
                                'cash_flow': cf_hist,
                                'profit_margin': profit_margin_hist
                            })
                            conn.commit()

                    except Exception as e:
                        print(f"Error processing historical date {date}: {e}")
                        continue
        except Exception as e:
            print(f"Error processing historical financials: {e}")
            # Continue without history if failed (user gets current data at least)
             
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error fetching fundamental data: {e}")
        return jsonify({'error': str(e)}), 500

@tickers_bp.route('/api/tickers/<ticker>/fundamental', methods=['GET'])
def get_fundamental_data(ticker):
    """Get historical fundamental data for a ticker."""
    try:
        query = text(f"""
            SELECT date, eps, eps_forward, pe_trailing, pe_forward, revenue, revenue_growth, earnings_growth, peg_ratio, market_cap, ebitda, cash_flow, profit_margin
            FROM {schema}.fundamental_analysis
            WHERE ticker = :ticker
            ORDER BY date DESC
        """)
        
        with engine.connect() as conn:
            result = conn.execute(query, {'ticker': ticker})
            data = []
            for row in result:
                data.append({
                    'date': row[0].strftime('%Y-%m-%d') if row[0] else None,
                    'eps': row[1],
                    'eps_forward': row[2],
                    'pe_trailing': row[3],
                    'pe_forward': row[4],
                    'revenue': row[5],
                    'revenue_growth': row[6],
                    'earnings_growth': row[7],
                    'peg_ratio': row[8],
                    'market_cap': row[9],
                    'ebitda': row[10],
                    'cash_flow': row[11],
                    'profit_margin': row[12]
                })
                
        return jsonify(data)
        
    except Exception as e:
        print(f"Error getting fundamental data: {e}")
        return jsonify({'error': str(e)}), 500

@tickers_bp.route('/api/tickers/<ticker>/sync_prices', methods=['POST'])
def sync_ticker_prices(ticker):
    """Sync price history for a specific ticker on demand."""
    try:
        db = Database()
        session = db.Session()
        
        try:
            # 1. Get or Create Asset
            asset = session.query(Asset).filter(Asset.ticker == ticker).first()
            if not asset:
                asset = Asset(ticker=ticker, asset_type='stock')
                session.add(asset)
                session.flush()

            # 2. Determine fetch range
            last_record = session.query(AssetPriceHistory).filter(AssetPriceHistory.asset_id == asset.id).order_by(AssetPriceHistory.date.desc()).first()
            
            end_date = datetime.now()
            if last_record:
                # Sync from last record minus 1 day to cover overlaps/updates
                start_date = datetime.combine(last_record.date, datetime.min.time()) - timedelta(days=1)
            else:
                # Default 5 years history if empty
                start_date = end_date - timedelta(days=365*5)
            
            # 3. Fetch from YF
            yf_ticker = get_yf_symbol(ticker)
            stock = yf.Ticker(yf_ticker)
            df = stock.history(start=start_date, end=end_date)
            
            if df.empty:
                 # Try downloading max history if 5 years returned nothing (sometimes helps with delisted/old)
                 if not last_record:
                     df = stock.history(period="max")
            
            if df.empty:
                 return jsonify({'success': False, 'message': 'No data found'}), 404

            # 4. Convert to PLN
            currency = get_currency_for_ticker(yf_ticker)
            if currency != "PLN":
                fx_ticker_sym = fx_symbol_to_pln(currency)
                if fx_ticker_sym:
                    # Fetch FX series
                    fx_start = df.index.min().date()
                    fx_end = df.index.max().date() + timedelta(days=1)
                    fx_series_map = _fetch_fx_series([currency], fx_start, fx_end)
                    fx_series = fx_series_map.get(fx_ticker_sym)
                    
                    if fx_series is not None and not fx_series.empty:
                        # Align indexes
                        if df.index.tz is not None: df.index = df.index.tz_localize(None)
                        if fx_series.index.tz is not None: fx_series.index = fx_series.index.tz_localize(None)
                        
                        aligned_fx = fx_series.reindex(df.index).ffill().bfill()
                        
                        for col in ['Open', 'High', 'Low', 'Close', 'Adj Close']:
                            if col in df.columns:
                                df[col] = df[col] * aligned_fx.values

            # 5. Save to DB
            count = 0
            for date_idx, row in df.iterrows():
                date_val = date_idx.date() if hasattr(date_idx, 'date') else pd.to_datetime(date_idx).date()
                
                existing = session.query(AssetPriceHistory).filter(
                    AssetPriceHistory.asset_id == asset.id,
                    AssetPriceHistory.date == date_val
                ).first()
                
                # Check for NaNs
                close_val = row['Close']
                if pd.isna(close_val): continue
                close_val = float(close_val)
                
                if existing:
                    existing.close = close_val
                    existing.open = float(row['Open']) if 'Open' in row else None
                    existing.high = float(row['High']) if 'High' in row else None
                    existing.low = float(row['Low']) if 'Low' in row else None
                    existing.volume = float(row['Volume']) if 'Volume' in row else None
                    existing.adjusted_close = close_val
                else:
                    new_rec = AssetPriceHistory(
                        asset_id=asset.id,
                        date=date_val,
                        close=close_val,
                        open=float(row['Open']) if 'Open' in row else None,
                        high=float(row['High']) if 'High' in row else None,
                        low=float(row['Low']) if 'Low' in row else None,
                        volume=float(row['Volume']) if 'Volume' in row else None,
                        adjusted_close=close_val
                    )
                    session.add(new_rec)
                count += 1
            
            session.commit()
            return jsonify({'success': True, 'count': count, 'ticker': ticker})
            
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    except Exception as e:
        print(f"Error syncing prices: {e}")
        return jsonify({'error': str(e)}), 500

@tickers_bp.route('/api/tickers')
def get_tickers():
    """Endpoint zwracający listę tickerów z sentymentem"""
    days = request.args.get('days', 30, type=int)

    query = text(f"""
    WITH sentiment_stats AS (
        SELECT
            ts.ticker,
            COUNT(*) as mentions,
            AVG(ts.impact::numeric) as avg_sentiment,
            AVG(ts.confidence::numeric) as avg_confidence,
            MAX(na.date) as last_mention
        FROM {schema}.ticker_sentiment ts
        JOIN {schema}.analysis_result ar ON ts.analysis_id = ar.id
        JOIN {schema}.news_articles na ON ar.news_id = na.id
        WHERE na.date >= CURRENT_DATE - INTERVAL '{days} days'
        AND na.id NOT IN (SELECT news_id FROM {schema}.news_not_analyzed WHERE reason = 'duplicate')
        GROUP BY ts.ticker
    )
    SELECT
        t.ticker,
        t.company_name,
        t.sector,
        COALESCE(s.mentions, 0) as mentions,
        COALESCE(s.avg_sentiment, 0) as avg_sentiment,
        COALESCE(s.avg_confidence, 0) as avg_confidence,
        s.last_mention,
        COALESCE(t.in_portfolio, 0) as in_portfolio,
        COALESCE(t.is_favorite, false) as is_favorite
    FROM {schema}.tickers t
    LEFT JOIN sentiment_stats s ON t.ticker = s.ticker
    WHERE s.mentions > 0 OR t.in_portfolio = 1 OR t.is_favorite = true
    ORDER BY COALESCE(s.mentions, 0) DESC, t.ticker
    """)

    with engine.connect() as conn:
        result = conn.execute(query)
        tickers_data = []
        for row in result:
            tickers_data.append({
                'ticker': row[0],
                'company_name': row[1],
                'sector': row[2],
                'mentions': int(row[3]),
                'avg_sentiment': float(row[4]) if row[4] else 0,
                'avg_confidence': float(row[5]) if row[5] else 0,
                'last_mention': row[6].strftime('%Y-%m-%d') if row[6] else None,
                'in_portfolio': bool(row[7]) if row[7] else False,
                'is_favorite': bool(row[8]) if row[8] else False
            })

    return jsonify(tickers_data)

@tickers_bp.route('/api/analyses/<ticker>')
def get_analyses(ticker):
    """Endpoint zwracający szczegółowe analizy dla tickera"""
    days = request.args.get('days', 30, type=int)

    # Resolve ticker to match DB format (e.g. COG -> COG.PL)
    resolved_ticker = resolve_db_ticker(engine, schema, ticker)

    query = text(f"""
    SELECT 
        na.id as news_id,
        ar.id as analysis_id,
        na.date,
        na.title,
        na.source,
        na.url,
        ts.impact,
        ts.confidence,
        ts.occasion,
        ar.summary
    FROM {schema}.ticker_sentiment ts
    JOIN {schema}.analysis_result ar ON ts.analysis_id = ar.id
    JOIN {schema}.news_articles na ON ar.news_id = na.id
    WHERE ts.ticker = :ticker
        AND na.date >= CURRENT_DATE - INTERVAL '{days} days'
        AND na.id NOT IN (SELECT news_id FROM {schema}.news_not_analyzed WHERE reason = 'duplicate')
    ORDER BY na.date DESC, ts.impact DESC
    """)

    # --- New logic to exclude duplicate news for contracts ---
    # If a news item is identified as a contract, we want to return ONLY the contract analysis,
    # and filter out the generic "news" analysis for the same news_id.
    
    get_contract_info_query = text(f"""
        SELECT ar.news_id, c.analysis_id
        FROM {schema}.contracts c
        JOIN {schema}.analysis_result ar ON c.analysis_id = ar.id
        WHERE c.ticker = :ticker
    """)
    
    contract_news_ids = set()
    contract_analysis_ids = set()
    
    with engine.connect() as conn:
        result = conn.execute(get_contract_info_query, {'ticker': resolved_ticker})
        for row in result:
            contract_news_ids.add(row[0])
            contract_analysis_ids.add(row[1])

    with engine.connect() as conn:
        result = conn.execute(query, {'ticker': resolved_ticker})
        analyses = []
        for row in result:
            news_id = row[0]
            analysis_id = row[1]
            
            # If this news is a contract
            if news_id in contract_news_ids:
                # If this analysis is NOT the contract analysis, skip it (it's the duplicate/old generic news)
                if analysis_id not in contract_analysis_ids:
                    continue
                # If it IS the contract analysis, keep it (so it shows on chart)
            
            analyses.append({
                'news_id': row[0],
                'analysis_id': row[1],
                'date': row[2].strftime('%Y-%m-%d') if row[2] else None,
                'title': row[3],
                'source': row[4],
                'url': row[5],
                'impact': float(row[6]) if row[6] else 0,
                'confidence': float(row[7]) if row[7] else 0,
                'occasion': row[8],
                'summary': format_summary(row[9])
            })

    return jsonify(analyses)

@tickers_bp.route('/api/brokerage/<ticker>')
def get_brokerage_analyses(ticker):
    """Endpoint zwracający rekomendacje brokerskie dla tickera"""
    days = request.args.get('days', 90, type=int)

    # Resolve ticker to match DB format (e.g. COG -> COG.PL)
    resolved_ticker = resolve_db_ticker(engine, schema, ticker)

    current_price = get_current_price(ticker)

    query = text(f"""
    SELECT DISTINCT ON (ba.price_old, ba.price_new, ba.brokerage_house)
        ba.created_at,
        ba.brokerage_house,
        ba.price_old,
        ba.price_new,
        ba.price_recommendation,
        ba.price_comment,
        na.date
    FROM {schema}.brokerage_analysis ba
    JOIN {schema}.analysis_result ar ON ba.analysis_id = ar.id
    LEFT JOIN {schema}.news_articles na ON ar.news_id = na.id
    WHERE ba.ticker = :ticker
        AND ba.created_at >= CURRENT_DATE - INTERVAL '{days} days'
        AND (na.id IS NULL OR na.id NOT IN (SELECT news_id FROM {schema}.news_not_analyzed WHERE reason = 'duplicate'))
    ORDER BY ba.price_old, ba.price_new, ba.brokerage_house, ba.created_at DESC
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {'ticker': resolved_ticker})
        brokerage_analyses = []
        seen_combinations = set()

        for row in result:
            price_old = parse_price(row[2])
            price_new = parse_price(row[3])
            brokerage_house = row[1]

            combination_key = (price_old, price_new, brokerage_house)

            if combination_key in seen_combinations:
                continue

            seen_combinations.add(combination_key)

            price_change_percent = None
            if price_old and price_new and price_old > 0:
                price_change_percent = ((price_new - price_old) / price_old) * 100

            upside_percent = None
            if price_new and current_price and current_price > 0:
                upside_percent = ((price_new - current_price) / current_price) * 100
            elif price_new and price_old and price_old > 0:
                upside_percent = ((price_new - price_old) / price_old) * 100

            brokerage_analyses.append({
                'date': row[0].strftime('%Y-%m-%d') if row[0] else (
                    row[6].strftime('%Y-%m-%d') if row[6] else None),
                'brokerage_house': brokerage_house,
                'price_old': price_old,
                'price_new': price_new,
                'current_price': current_price,
                'recommendation': row[4],
                'comment': row[5],
                'price_change_percent': price_change_percent,
                'upside_percent': upside_percent
            })

        brokerage_analyses.sort(key=lambda x: x['date'] if x['date'] else '1900-01-01',
                                reverse=True)

    return jsonify(brokerage_analyses)

@tickers_bp.route('/api/all_tickers')
def get_all_tickers():
    """Endpoint zwracający listę wszystkich dostępnych tickerów"""
    query = text(f"""
    SELECT ticker, company_name FROM {schema}.tickers ORDER BY ticker
    """)
    with engine.connect() as conn:
        result = conn.execute(query)
        tickers = [{'value': row[0], 'label': f"{row[0]} - {row[1]}"} for row in result]
    return jsonify(tickers)

@tickers_bp.route('/api/update_analysis_tickers', methods=['POST'])
def update_analysis_tickers():
    """Endpoint do aktualizacji tickerów dla danej analizy"""
    try:
        data = request.get_json()
        analysis_id = data.get('analysis_id')
        tickers = data.get('tickers')

        if not analysis_id or not isinstance(tickers, list):
            return jsonify({'error': 'Missing analysis_id or tickers'}), 400

        with engine.connect() as conn:
            # Rozpocznij transakcję
            trans = conn.begin()
            try:
                # 1. Pobierz impact i confidence z analizy, jeśli nie ma jeszcze tickerów
                get_analysis_details_query = text(f"""
                    SELECT summary FROM {schema}.analysis_result WHERE id = :analysis_id
                """)
                res = conn.execute(get_analysis_details_query,
                                   {'analysis_id': analysis_id}).fetchone()
                if not res:
                    return jsonify({'error': 'Analysis not found'}), 404

                summary_data = {}
                try:
                    if res[0] and isinstance(res[0], str):
                        summary_data = json.loads(res[0])
                    elif isinstance(res[0], dict):
                        summary_data = res[0]
                except json.JSONDecodeError:
                    pass

                impact = summary_data.get('ticker_impact')
                confidence = summary_data.get('confidence')
                occasion = summary_data.get('occasion')

                impact = float(impact) if impact is not None else 0.4
                confidence = float(confidence) if confidence is not None else 0.7

                # 2. Usuń istniejące powiązania tickerów dla tej analizy
                delete_query = text(f"""
                    DELETE FROM {schema}.ticker_sentiment WHERE analysis_id = :analysis_id
                """)
                conn.execute(delete_query, {'analysis_id': analysis_id})

                # 3. Wstaw nowe tickery
                if tickers:
                    insert_query = text(f"""
                        INSERT INTO {schema}.ticker_sentiment (analysis_id, ticker, impact, confidence, occasion)
                        VALUES (:analysis_id, :ticker, :impact, :confidence, :occasion)
                    """)
                    for ticker in tickers:
                        conn.execute(insert_query, {
                            'analysis_id': analysis_id,
                            'ticker': ticker,
                            'impact': impact,
                            'confidence': confidence,
                            'occasion': occasion
                        })

                trans.commit()
                return jsonify(
                    {'success': True, 'message': 'Tickers updated successfully'})

            except Exception as e:
                trans.rollback()
                raise e

    except Exception as e:
        print(f"Error updating tickers: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@tickers_bp.route('/api/toggle_portfolio', methods=['POST'])
def toggle_portfolio():
    """Endpoint do przełączania statusu portfolio dla tickera"""
    try:
        data = request.get_json()
        ticker_symbol = data.get('ticker')
        in_portfolio = data.get('in_portfolio', False)

        if not ticker_symbol:
            return jsonify({'error': 'Missing ticker'}), 400

        with engine.connect() as conn:
            # Sprawdź czy ticker istnieje
            check_query = text(f"""
                SELECT ticker FROM {schema}.tickers WHERE ticker = :ticker
            """)
            result = conn.execute(check_query, {'ticker': ticker_symbol})
            exists = result.fetchone()

            if not exists:
                # Utwórz ticker jeśli nie istnieje
                insert_query = text(f"""
                    INSERT INTO {schema}.tickers (ticker, in_portfolio)
                    VALUES (:ticker, :in_portfolio)
                """)
                conn.execute(insert_query, {
                    'ticker': ticker_symbol,
                    'in_portfolio': 1 if in_portfolio else 0
                })
            else:
                # Zaktualizuj istniejący ticker
                update_query = text(f"""
                    UPDATE {schema}.tickers
                    SET in_portfolio = :in_portfolio
                    WHERE ticker = :ticker
                """)
                conn.execute(update_query, {
                    'ticker': ticker_symbol,
                    'in_portfolio': 1 if in_portfolio else 0
                })

            conn.commit()

        return jsonify(
            {'success': True, 'ticker': ticker_symbol, 'in_portfolio': in_portfolio})

    except Exception as e:
        print(f"Error toggling portfolio: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@tickers_bp.route('/api/toggle_favorite', methods=['POST'])
def toggle_favorite():
    """Endpoint do przełączania statusu ulubionych dla tickera"""
    try:
        data = request.get_json()
        ticker_symbol = data.get('ticker')
        is_favorite = data.get('is_favorite', False)

        if not ticker_symbol:
            return jsonify({'error': 'Missing ticker'}), 400

        with engine.connect() as conn:
            # Sprawdź czy ticker istnieje
            check_query = text(f"""
                SELECT ticker FROM {schema}.tickers WHERE ticker = :ticker
            """)
            result = conn.execute(check_query, {'ticker': ticker_symbol})
            exists = result.fetchone()

            if not exists:
                # Utwórz ticker jeśli nie istnieje
                insert_query = text(f"""
                    INSERT INTO {schema}.tickers (ticker, is_favorite)
                    VALUES (:ticker, :is_favorite)
                """)
                conn.execute(insert_query, {
                    'ticker': ticker_symbol,
                    'is_favorite': is_favorite
                })
            else:
                # Zaktualizuj istniejący ticker
                update_query = text(f"""
                    UPDATE {schema}.tickers
                    SET is_favorite = :is_favorite
                    WHERE ticker = :ticker
                """)
                conn.execute(update_query, {
                    'ticker': ticker_symbol,
                    'is_favorite': is_favorite
                })

            conn.commit()

        return jsonify(
            {'success': True, 'ticker': ticker_symbol, 'is_favorite': is_favorite})

    except Exception as e:
        print(f"Error toggling favorite: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@tickers_bp.route('/api/tickers/add', methods=['POST'])
def add_ticker():
    """Endpoint do dodawania nowego tickera"""
    try:
        data = request.get_json()
        ticker_symbol = data.get('ticker')
        company_name = data.get('company_name')
        sector = data.get('sector')

        if not ticker_symbol:
            return jsonify({'error': 'Missing ticker symbol'}), 400

        with engine.connect() as conn:
            # Sprawdź czy ticker istnieje
            check_query = text(f"""
                SELECT ticker, in_portfolio, is_favorite FROM {schema}.tickers WHERE ticker = :ticker
            """)
            result = conn.execute(check_query, {'ticker': ticker_symbol})
            exists = result.fetchone()

            if exists:
                # Jeśli ticker istnieje ale nie jest widoczny (nie jest w portfolio ani ulubiony),
                # to ustaw go jako ulubiony, aby pojawił się na liście.
                in_portfolio = exists[1]
                is_favorite = exists[2]

                if not in_portfolio and not is_favorite:
                    update_query = text(f"""
                        UPDATE {schema}.tickers 
                        SET is_favorite = true 
                        WHERE ticker = :ticker
                    """)
                    conn.execute(update_query, {'ticker': ticker_symbol})
                    conn.commit()
                    return jsonify({'success': True, 'ticker': ticker_symbol, 'message': 'Ticker restored to favorites'})
                
                return jsonify({'error': 'Ticker already exists'}), 409

            # Dodaj nowy ticker (domyślnie jako ulubiony, aby był widoczny)
            insert_query = text(f"""
                INSERT INTO {schema}.tickers (ticker, company_name, sector, in_portfolio, is_favorite)
                VALUES (:ticker, :company_name, :sector, 0, true)
            """)
            conn.execute(insert_query, {
                'ticker': ticker_symbol,
                'company_name': company_name,
                'sector': sector
            })
            conn.commit()

        return jsonify({'success': True, 'ticker': ticker_symbol})

    except Exception as e:
        print(f"Error adding ticker: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@tickers_bp.route('/api/tickers/<ticker>/notes', methods=['GET'])
def get_ticker_notes(ticker):
    """Endpoint do pobierania notatek dla tickera"""
    try:
        # Resolve ticker if needed, but notes are attached to specific ticker symbol usually
        # resolved_ticker = resolve_db_ticker(engine, schema, ticker) 
        # Actually better use the raw ticker or ensure consistency. 
        # Existing endpoints use resolve_db_ticker but that's for matching with external data maybe?
        # Let's stick to simple ticker lookup for notes.

        query = text(f"""
            SELECT id, content, created_at, updated_at
            FROM {schema}.ticker_notes
            WHERE ticker = :ticker
            ORDER BY created_at DESC
        """)

        with engine.connect() as conn:
            result = conn.execute(query, {'ticker': ticker})
            notes = []
            for row in result:
                notes.append({
                    'id': row[0],
                    'content': row[1],
                    'created_at': row[2].strftime('%Y-%m-%d %H:%M:%S') if row[2] else None,
                    'updated_at': row[3].strftime('%Y-%m-%d %H:%M:%S') if row[3] else None
                })

        return jsonify(notes)

    except Exception as e:
        print(f"Error fetching notes: {e}")
        return jsonify({'error': str(e)}), 500

@tickers_bp.route('/api/tickers/<ticker>/notes', methods=['POST'])
def add_ticker_note(ticker):
    """Endpoint do dodawania notatki"""
    try:
        data = request.get_json()
        content = data.get('content')

        if not content:
            return jsonify({'error': 'Missing content'}), 400

        with engine.connect() as conn:
            insert_query = text(f"""
                INSERT INTO {schema}.ticker_notes (ticker, content, created_at, updated_at)
                VALUES (:ticker, :content, NOW(), NOW())
                RETURNING id, created_at
            """)
            result = conn.execute(insert_query, {
                'ticker': ticker,
                'content': content
            })
            row = result.fetchone()
            conn.commit()
            
            new_note = {
                'id': row[0],
                'content': content,
                'created_at': row[1].strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': row[1].strftime('%Y-%m-%d %H:%M:%S')
            }

        return jsonify(new_note)

    except Exception as e:
        print(f"Error adding note: {e}")
        return jsonify({'error': str(e)}), 500

@tickers_bp.route('/api/notes/<int:note_id>', methods=['PUT'])
def update_note(note_id):
    """Endpoint do edycji notatki"""
    try:
        data = request.get_json()
        content = data.get('content')

        if not content:
            return jsonify({'error': 'Missing content'}), 400

        with engine.connect() as conn:
            update_query = text(f"""
                UPDATE {schema}.ticker_notes
                SET content = :content, updated_at = NOW()
                WHERE id = :id
            """)
            conn.execute(update_query, {'content': content, 'id': note_id})
            conn.commit()

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error updating note: {e}")
        return jsonify({'error': str(e)}), 500

@tickers_bp.route('/api/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    """Endpoint do usuwania notatki"""
    try:
        with engine.connect() as conn:
            delete_query = text(f"""
                DELETE FROM {schema}.ticker_notes WHERE id = :id
            """)
            conn.execute(delete_query, {'id': note_id})
            conn.commit()

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error deleting note: {e}")
        return jsonify({'error': str(e)}), 500

@tickers_bp.route('/api/tickers/<ticker>/update', methods=['POST'])
def update_ticker_details(ticker):
    """Endpoint do aktualizacji szczegółów tickera (nazwa, sektor, scrape_url)"""
    try:
        data = request.get_json()
        company_name = data.get('company_name')
        sector = data.get('sector')
        scrape_url = data.get('scrape_url')
        
        # We allow partial updates
        
        with engine.connect() as conn:
            # Check if exists
            # We assume it exists as we update existing
            
            # Construct update query dynamically or just set both if provided
            updates = []
            params = {'ticker': ticker}
            
            if company_name is not None:
                updates.append("company_name = :company_name")
                params['company_name'] = company_name
            
            if sector is not None:
                updates.append("sector = :sector")
                params['sector'] = sector
            
            if scrape_url is not None:
                updates.append("scrape_url = :scrape_url")
                params['scrape_url'] = scrape_url
                
            if not updates:
                return jsonify({'success': True, 'message': 'Nothing to update'})
                
            update_sql = f"UPDATE {schema}.tickers SET {', '.join(updates)} WHERE ticker = :ticker"
            conn.execute(text(update_sql), params)
            conn.commit()
            
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error updating ticker details: {e}")
        return jsonify({'error': str(e)}), 500

@tickers_bp.route('/api/analyze_as_contract', methods=['POST'])
def analyze_as_contract():
    """Endpoint do ręcznego wymuszenia analizy newsa jako kontrakt"""
    try:
        data = request.get_json()
        news_id = data.get('news_id')
        ticker = data.get('ticker')
        
        if not news_id:
            return jsonify({'error': 'Missing news_id'}), 400
            
        db = Database()
        
        # Uruchom analizę z flagą force_contract=True
        # Używamy mode='id' dla konkretnego artykułu
        from backend.ai.ai_analist import analyze_articles
        result = analyze_articles(db, mode='id', article_id=news_id, skip_relevance_check=True, force_contract=True, forced_ticker=ticker)
        
        db.close()
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error analyzing as contract: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@tickers_bp.route('/api/contracts/<ticker>')
def get_contracts(ticker):
    """Endpoint zwracający listę kontraktów dla tickera"""
    
    # Resolve ticker to match DB format (e.g. COG -> COG.PL)
    resolved_ticker = resolve_db_ticker(engine, schema, ticker)

    query = text(f"""
    SELECT 
        c.date,
        c.contract_value,
        c.contract_summary,
        c.investment_relevance,
        c.key_risks
    FROM {schema}.contracts c
    JOIN {schema}.analysis_result ar ON c.analysis_id = ar.id
    JOIN {schema}.news_articles na ON ar.news_id = na.id
    WHERE c.ticker = :ticker
    AND na.id NOT IN (SELECT news_id FROM {schema}.news_not_analyzed WHERE reason = 'duplicate')
    ORDER BY c.date DESC
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {'ticker': resolved_ticker})
        contracts = []
        for row in result:
            key_risks = []
            try:
                if row[4]:
                    key_risks = json.loads(row[4])
            except:
                pass
                
            contracts.append({
                'date': row[0].strftime('%Y-%m-%d') if row[0] else None,
                'contract_value': row[1],
                'contract_summary': row[2],
                'investment_relevance': row[3],
                'key_risks': key_risks
            })

    return jsonify(contracts)

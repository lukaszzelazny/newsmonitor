import json
from flask import Blueprint, jsonify, request
from sqlalchemy import text
from analize.utils import get_db_engine, get_current_price, parse_price, format_summary, resolve_db_ticker

tickers_bp = Blueprint('tickers', __name__)
engine, schema = get_db_engine()

@tickers_bp.route('/api/tickers')
def get_tickers():
    """Endpoint zwracający listę tickerów z sentymentem"""
    days = request.args.get('days', 30, type=int)

    query = text(f"""
    SELECT
        ts.ticker,
        t.company_name,
        t.sector,
        COUNT(*) as mentions,
        AVG(ts.impact::numeric) as avg_sentiment,
        AVG(ts.confidence::numeric) as avg_confidence,
        MAX(na.date) as last_mention,
        COALESCE(t.in_portfolio, 0) as in_portfolio,
        COALESCE(t.is_favorite, false) as is_favorite
    FROM {schema}.ticker_sentiment ts
    JOIN {schema}.analysis_result ar ON ts.analysis_id = ar.id
    JOIN {schema}.news_articles na ON ar.news_id = na.id
    LEFT JOIN {schema}.tickers t ON ts.ticker = t.ticker
    WHERE ts.ticker IS NOT NULL
        AND na.date >= CURRENT_DATE - INTERVAL '{days} days'
        AND na.id NOT IN (SELECT news_id FROM {schema}.news_not_analyzed WHERE reason = 'duplicate')
    GROUP BY ts.ticker, t.company_name, t.sector, t.in_portfolio, t.is_favorite
    HAVING COUNT(*) >= 1
    ORDER BY COUNT(*) DESC, ts.ticker
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

    with engine.connect() as conn:
        result = conn.execute(query, {'ticker': resolved_ticker})
        analyses = []
        for row in result:
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

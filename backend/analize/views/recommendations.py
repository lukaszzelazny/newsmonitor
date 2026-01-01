from flask import Blueprint, jsonify, request
from sqlalchemy import text
from analize.utils import get_db_engine, parse_price
from backend.tools.price_fetcher import get_current_prices

recommendations_bp = Blueprint('recommendations', __name__)
engine, schema = get_db_engine()

@recommendations_bp.route('/api/recommendations')
def get_all_recommendations():
    """Endpoint zwracający listę wszystkich rekomendacji brokerskich"""
    days = request.args.get('days', 90, type=int)

    # Use distinct on ticker, brokerage_house and date to avoid duplicates
    query = text(f"""
    SELECT * FROM (
        SELECT DISTINCT ON (ba.ticker, ba.brokerage_house, COALESCE(na.date, ba.created_at::date))
            ba.id,
            ba.created_at,
            ba.brokerage_house,
            ba.price_old,
            ba.price_new,
            ba.price_recommendation,
            ba.price_comment,
            ba.ticker,
            na.date,
            na.url,
            t.company_name
        FROM {schema}.brokerage_analysis ba
        JOIN {schema}.analysis_result ar ON ba.analysis_id = ar.id
        LEFT JOIN {schema}.news_articles na ON ar.news_id = na.id
        LEFT JOIN {schema}.tickers t ON ba.ticker = t.ticker
        WHERE ba.created_at >= CURRENT_DATE - INTERVAL '{days} days'
            AND (na.id IS NULL OR na.id NOT IN (SELECT news_id FROM {schema}.news_not_analyzed WHERE reason = 'duplicate'))
        ORDER BY ba.ticker, ba.brokerage_house, COALESCE(na.date, ba.created_at::date), ba.created_at DESC
    ) AS sub
    ORDER BY created_at DESC
    """)

    with engine.connect() as conn:
        result = conn.execute(query).fetchall() # fetchall needed to iterate twice (or list)
        
        # Collect unique tickers and force .WA suffix for GPW context
        tickers_raw = {row[7] for row in result if row[7]}
        
        tickers_to_fetch = []
        ticker_map = {} # raw -> fetched_symbol

        for t in tickers_raw:
            # Assume GPW if no suffix provided, as these are from Polish recommendations
            if '.' not in t:
                fixed = f"{t}.WA"
                tickers_to_fetch.append(fixed)
                ticker_map[t] = fixed
            else:
                tickers_to_fetch.append(t)
                ticker_map[t] = t

        # Batch fetch prices
        fetched_prices = get_current_prices(tickers_to_fetch)
        
        # Map back to raw tickers
        current_prices = {}
        for raw, fixed in ticker_map.items():
            if fixed in fetched_prices:
                current_prices[raw] = fetched_prices[fixed]

        recommendations = []
        for row in result:
            rec_id = row[0]
            ticker = row[7]
            
            current_price = current_prices.get(ticker)

            price_old = parse_price(row[3])
            price_new = parse_price(row[4])
            
            price_change_percent = None
            if price_old and price_new and price_old > 0:
                price_change_percent = ((price_new - price_old) / price_old) * 100

            upside_percent = None
            if price_new and current_price and current_price > 0:
                upside_percent = ((price_new - current_price) / current_price) * 100
            elif price_new and price_old and price_old > 0:
                upside_percent = ((price_new - price_old) / price_old) * 100

            recommendations.append({
                'id': rec_id,
                'date': row[1].strftime('%Y-%m-%d') if row[1] else (
                    row[8].strftime('%Y-%m-%d') if row[8] else None),
                'brokerage_house': row[2],
                'price_old': price_old,
                'price_at_recommendation': price_old, # Explicit alias
                'price_new': price_new,
                'recommendation': row[5],
                'comment': row[6],
                'ticker': ticker,
                'company_name': row[10],
                'url': row[9],
                'current_price': current_price,
                'price_change_percent': price_change_percent,
                'upside_percent': upside_percent
            })

    return jsonify(recommendations)

@recommendations_bp.route('/api/recommendations/<int:id>', methods=['DELETE'])
def delete_recommendation(id):
    """Usuwa rekomendację z bazy"""
    try:
        query = text(f"DELETE FROM {schema}.brokerage_analysis WHERE id = :id")
        with engine.connect() as conn:
            conn.execute(query, {'id': id})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error deleting recommendation {id}: {e}")
        return jsonify({'error': str(e)}), 500

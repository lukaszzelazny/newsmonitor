import json
from flask import Blueprint, jsonify, request
from sqlalchemy import text
from analize.utils import get_db_engine, format_summary

calendar_bp = Blueprint('calendar', __name__)
engine, schema = get_db_engine()

@calendar_bp.route('/api/calendar_stats')
def get_calendar_stats():
    """Endpoint zwracający statystyki newsów dla każdego dnia (dla color coding kalendarza)"""
    days = request.args.get('days', 90, type=int)

    query = text(f"""
    SELECT
        na.date,
        COUNT(DISTINCT na.id) as news_count,
        AVG(ts.impact::numeric) as avg_impact
    FROM {schema}.news_articles na
    JOIN {schema}.analysis_result ar ON ar.news_id = na.id
    LEFT JOIN {schema}.ticker_sentiment ts ON ts.analysis_id = ar.id
    WHERE na.date >= CURRENT_DATE - INTERVAL '{days} days'
        AND na.id NOT IN (SELECT news_id FROM {schema}.news_not_analyzed WHERE reason = 'duplicate')
        AND ar.summary IS NOT NULL
    GROUP BY na.date
    ORDER BY na.date DESC
    """)

    with engine.connect() as conn:
        result = conn.execute(query)
        calendar_data = []
        for row in result:
            calendar_data.append({
                'date': row[0].strftime('%Y-%m-%d') if row[0] else None,
                'news_count': int(row[1]),
                'avg_impact': float(row[2]) if row[2] else 0
            })

    return jsonify(calendar_data)

@calendar_bp.route('/api/news_by_date/<date>')
def get_news_by_date(date):
    """Endpoint zwracający wszystkie newsy z wybranego dnia z tickerami"""
    query = text(f"""
    SELECT
        na.id as news_id,
        ar.id as analysis_id,
        na.date,
        na.published_at,
        na.title,
        na.source,
        na.url,
        ar.summary
    FROM {schema}.news_articles na
    JOIN {schema}.analysis_result ar ON ar.news_id = na.id
    WHERE na.date = :date
        AND ar.summary IS NOT NULL
        AND na.id NOT IN (SELECT news_id FROM {schema}.news_not_analyzed WHERE reason = 'duplicate')
    ORDER BY na.published_at DESC
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {'date': date})
        news_dict = {}

        for row in result:
            news_id = row[0]
            summary_data = {}
            try:
                if row[7] and isinstance(row[7], str):
                    summary_data = json.loads(row[7])
                elif isinstance(row[7], dict):
                    summary_data = row[7]
            except json.JSONDecodeError:
                pass

            impact = summary_data.get('ticker_impact')
            confidence = summary_data.get('confidence')

            news_dict[news_id] = {
                'news_id': news_id,
                'analysis_id': row[1],
                'date': row[2].strftime('%Y-%m-%d') if row[2] else None,
                'published_at': row[3].strftime('%H:%M') if row[3] else None,
                'title': row[4],
                'source': row[5],
                'url': row[6],
                'impact': float(impact) if impact is not None else 0.4,
                'confidence': float(confidence) if confidence is not None else 0.7,
                'occasion': summary_data.get('occasion'),
                'summary': format_summary(summary_data),
                'tickers': []
            }

        if news_dict:
            # Create a map from analysis_id to the news item object
            analysis_id_to_news = {data['analysis_id']: data for data in
                                   news_dict.values()}
            analysis_ids = list(analysis_id_to_news.keys())

            if analysis_ids:
                ticker_query = text(f"""
                    SELECT ts.analysis_id, ts.ticker, ts.impact
                    FROM {schema}.ticker_sentiment ts
                    WHERE ts.analysis_id = ANY(:analysis_ids)
                    AND ts.ticker IS NOT NULL
                    ORDER BY ts.impact DESC
                """)
                ticker_result = conn.execute(ticker_query,
                                             {'analysis_ids': analysis_ids})

                for ticker_row in ticker_result:
                    analysis_id = ticker_row[0]
                    news_item = analysis_id_to_news.get(analysis_id)
                    if news_item:
                        news_item['tickers'].append({
                            'ticker': ticker_row[1],
                            'impact': float(ticker_row[2]) if ticker_row[2] else 0
                        })

        news_list = list(news_dict.values())
        # Sort by impact if no published_at is available
        news_list.sort(key=lambda x: x.get('published_at') or '00:00', reverse=True)

    return jsonify(news_list)

@calendar_bp.route('/api/mark_duplicate', methods=['POST'])
def mark_duplicate():
    """Endpoint oznaczający news jako duplikat"""
    try:
        data = request.get_json()
        news_id = data.get('news_id')

        if not news_id:
            return jsonify({'error': 'Missing news_id'}), 400

        with engine.connect() as conn:
            # Sprawdź czy news istnieje
            check_query = text(f"""
                SELECT id FROM {schema}.news_articles WHERE id = :news_id
            """)
            result = conn.execute(check_query, {'news_id': news_id})
            if not result.fetchone():
                return jsonify({'error': 'News not found'}), 404

            # Dodaj wpis do news_not_analyzed
            insert_query = text(f"""
                INSERT INTO {schema}.news_not_analyzed (news_id, reason, relevance_score)
                VALUES (:news_id, 'duplicate', 0.0)
                ON CONFLICT (news_id) DO UPDATE SET reason = 'duplicate'
            """)
            conn.execute(insert_query, {'news_id': news_id})
            conn.commit()

        return jsonify({'success': True, 'message': 'News marked as duplicate'})

    except Exception as e:
        print(f"Error marking duplicate: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

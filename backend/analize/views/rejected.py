from flask import Blueprint, jsonify, request
from sqlalchemy import text
from backend.analize.utils import get_db_engine

rejected_bp = Blueprint('rejected', __name__)
engine, schema = get_db_engine()

@rejected_bp.route('/api/rejected_calendar_stats')
def get_rejected_calendar_stats():
    """Endpoint zwracający statystyki odrzuconych newsów dla każdego dnia (dla color coding kalendarza)"""
    days = request.args.get('days', 90, type=int)

    query = text(f"""
    SELECT
        na.date,
        COUNT(DISTINCT nna.id) as news_count,
        nna.reason
    FROM {schema}.news_articles na
    JOIN {schema}.news_not_analyzed nna ON nna.news_id = na.id
    WHERE na.date >= CURRENT_DATE - INTERVAL '{days} days'
    GROUP BY na.date, nna.reason
    ORDER BY na.date DESC
    """)

    with engine.connect() as conn:
        result = conn.execute(query)
        calendar_data = []
        for row in result:
            calendar_data.append({
                'date': row[0].strftime('%Y-%m-%d') if row[0] else None,
                'news_count': int(row[1]),
                'reason': row[2]
            })

    return jsonify(calendar_data)

@rejected_bp.route('/api/rejected_news_by_date/<date>')
def get_rejected_news_by_date(date):
    """Endpoint zwracający wszystkie odrzucone newsy z wybranego dnia"""
    query = text(f"""
    SELECT
        na.id as news_id,
        na.date,
        na.title,
        na.source,
        na.url,
        na.content,
        nna.reason,
        nna.relevance_score
    FROM {schema}.news_articles na
    JOIN {schema}.news_not_analyzed nna ON nna.news_id = na.id
    WHERE na.date = :date
    ORDER BY nna.created_at DESC
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {'date': date})
        news_list = []

        for row in result:
            news_list.append({
                'news_id': row[0],
                'date': row[1].strftime('%Y-%m-%d') if row[1] else None,
                'title': row[2],
                'source': row[3],
                'url': row[4],
                'content': row[5],
                'reason': row[6],
                'relevance_score': float(row[7]) if row[7] else 0.0
            })

    return jsonify(news_list)

@rejected_bp.route('/api/reanalyze_news', methods=['POST'])
def reanalyze_news():
    """Endpoint do ponownej analizy odrzuconego newsa przez AI"""
    try:
        data = request.get_json()
        news_id = data.get('news_id')

        if not news_id:
            return jsonify({'error': 'Missing news_id'}), 400

        # Import potrzebnych modułów
        from backend.ai.ai_analist import analyze_articles
        from database import Database

        # Usuń news z news_not_analyzed
        with engine.connect() as conn:
            delete_query = text(f"""
                DELETE FROM {schema}.news_not_analyzed
                WHERE news_id = :news_id
            """)
            conn.execute(delete_query, {'news_id': news_id})
            conn.commit()

        # Uruchom analizę AI (pomijamy sprawdzanie wzorców - od razu do OpenAI)
        db = Database()
        result = analyze_articles(db, mode='id', article_id=news_id, telegram=None,
                                  skip_relevance_check=True)

        if result['status'] == 'error':
            return jsonify({'error': result.get('message', 'Unknown error')}), 500

        return jsonify({
            'success': True,
            'message': 'News został pomyślnie przeanalizowany',
            'result': result
        })

    except Exception as e:
        print(f"Error reanalyzing news: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

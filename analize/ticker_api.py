"""
Flask API dla interaktywnego dashboardu tickerów
Uruchom: python ticker_api.py
Potem otwórz: http://localhost:5000
"""

from flask import Flask, render_template_string, jsonify
from sqlalchemy import create_engine, text
import os
from datetime import datetime, timedelta

app = Flask(__name__)


# Konfiguracja bazy danych
def get_db_engine():
    db_url = "postgresql:///?service=stock"

    engine = create_engine(db_url)
    schema = os.getenv('DB_SCHEMA', 'stock')
    return engine, schema


engine, schema = get_db_engine()

# HTML Template z React aplikacją
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Analiza Sentymentu Tickerów</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
</head>
<body>
    <div id="root"></div>
    
    <script type="text/babel">
        const { useState, useEffect } = React;

        const TickerDashboard = () => {
          const [tickers, setTickers] = useState([]);
          const [selectedTicker, setSelectedTicker] = useState(null);
          const [analyses, setAnalyses] = useState([]);
          const [loading, setLoading] = useState(false);
          const [searchTerm, setSearchTerm] = useState('');
          const [days, setDays] = useState(30);

          useEffect(() => {
            fetchTickers();
          }, [days]);

          useEffect(() => {
            if (selectedTicker) {
              fetchAnalyses(selectedTicker.ticker);
            }
          }, [selectedTicker]);

          const fetchTickers = async () => {
            try {
              const response = await fetch(`/api/tickers?days=${days}`);
              const data = await response.json();
              setTickers(data);
            } catch (error) {
              console.error('Error fetching tickers:', error);
            }
          };

          const fetchAnalyses = async (ticker) => {
            setLoading(true);
            try {
              const response = await fetch(`/api/analyses/${ticker}?days=${days}`);
              const data = await response.json();
              setAnalyses(data);
            } catch (error) {
              console.error('Error fetching analyses:', error);
            } finally {
              setLoading(false);
            }
          };

          const filteredTickers = tickers.filter(t => 
            t.ticker.toLowerCase().includes(searchTerm.toLowerCase()) ||
            (t.company_name && t.company_name.toLowerCase().includes(searchTerm.toLowerCase()))
          );

          const getSentimentColor = (sentiment) => {
            if (sentiment > 0.3) return 'text-green-600';
            if (sentiment > 0) return 'text-green-400';
            if (sentiment > -0.3) return 'text-yellow-500';
            return 'text-red-500';
          };

          const getSentimentBg = (sentiment) => {
            if (sentiment > 0.3) return 'bg-green-100';
            if (sentiment > 0) return 'bg-green-50';
            if (sentiment > -0.3) return 'bg-yellow-50';
            return 'bg-red-50';
          };

          const getImpactColor = (impact) => {
            if (impact > 0.5) return 'bg-green-500';
            if (impact > 0.2) return 'bg-green-400';
            if (impact > -0.2) return 'bg-yellow-400';
            if (impact > -0.5) return 'bg-orange-400';
            return 'bg-red-500';
          };

          return (
            <div className="min-h-screen bg-gray-50 p-6">
              <div className="max-w-7xl mx-auto">
                <div className="flex items-center justify-between mb-6">
                  <h1 className="text-3xl font-bold text-gray-900">
                    Analiza Sentymentu Tickerów
                  </h1>
                  <div className="flex items-center gap-2">
                    <label className="text-sm text-gray-600">Okres:</label>
                    <select 
                      value={days} 
                      onChange={(e) => setDays(Number(e.target.value))}
                      className="px-3 py-2 border border-gray-300 rounded-lg"
                    >
                      <option value="7">7 dni</option>
                      <option value="14">14 dni</option>
                      <option value="30">30 dni</option>
                      <option value="60">60 dni</option>
                      <option value="90">90 dni</option>
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-12 gap-6">
                  {/* Lewa kolumna - Lista tickerów */}
                  <div className="col-span-4 bg-white rounded-lg shadow-lg p-4">
                    <div className="mb-4">
                      <input
                        type="text"
                        placeholder="Szukaj tickera lub firmy..."
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                      />
                    </div>

                    <div className="space-y-2 max-h-[calc(100vh-200px)] overflow-y-auto">
                      {filteredTickers.map((ticker) => (
                        <div
                          key={ticker.ticker}
                          onClick={() => setSelectedTicker(ticker)}
                          className={`p-3 rounded-lg cursor-pointer transition-all ${
                            selectedTicker?.ticker === ticker.ticker
                              ? 'bg-blue-50 border-2 border-blue-500'
                              : 'bg-gray-50 hover:bg-gray-100 border-2 border-transparent'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex-1">
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-lg text-gray-900">
                                  {ticker.ticker}
                                </span>
                              </div>
                              <p className="text-sm text-gray-600">{ticker.company_name || 'Brak nazwy'}</p>
                              <p className="text-xs text-gray-500">{ticker.sector || 'Brak sektora'}</p>
                            </div>
                            <div className="text-right">
                              <div className={`text-lg font-bold ${getSentimentColor(ticker.avg_sentiment)}`}>
                                {ticker.avg_sentiment > 0 ? '+' : ''}{Number(ticker.avg_sentiment).toFixed(2)}
                              </div>
                              <div className="text-xs text-gray-500">
                                {ticker.mentions} wzmianek
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Prawa kolumna - Szczegóły analiz */}
                  <div className="col-span-8 bg-white rounded-lg shadow-lg p-6">
                    {!selectedTicker ? (
                      <div className="flex items-center justify-center h-full text-gray-400">
                        <div className="text-center">
                          <p className="text-xl">Wybierz ticker z listy po lewej</p>
                        </div>
                      </div>
                    ) : (
                      <div>
                        {/* Nagłówek */}
                        <div className={`p-4 rounded-lg mb-6 ${getSentimentBg(selectedTicker.avg_sentiment)}`}>
                          <div className="flex items-center justify-between">
                            <div>
                              <h2 className="text-2xl font-bold text-gray-900">
                                {selectedTicker.ticker} - {selectedTicker.company_name || 'Brak nazwy'}
                              </h2>
                              <p className="text-gray-600">{selectedTicker.sector || 'Brak sektora'}</p>
                            </div>
                            <div className="text-right">
                              <div className={`text-3xl font-bold ${getSentimentColor(selectedTicker.avg_sentiment)}`}>
                                {selectedTicker.avg_sentiment > 0 ? '+' : ''}{Number(selectedTicker.avg_sentiment).toFixed(2)}
                              </div>
                              <div className="text-sm text-gray-600">
                                Średni sentyment
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* Lista analiz */}
                        {loading ? (
                          <div className="flex items-center justify-center py-12">
                            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                          </div>
                        ) : analyses.length === 0 ? (
                          <div className="text-center py-12 text-gray-500">
                            <p>Brak dostępnych analiz dla tego tickera</p>
                          </div>
                        ) : (
                          <div className="space-y-4 max-h-[calc(100vh-350px)] overflow-y-auto">
                            {analyses.map((analysis, idx) => (
                              <div
                                key={idx}
                                className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
                              >
                                <div className="flex items-start gap-4">
                                  {/* Impact indicator */}
                                  <div className="flex-shrink-0">
                                    <div className={`w-3 h-24 ${getImpactColor(analysis.impact)} rounded`}></div>
                                  </div>

                                  <div className="flex-1">
                                    {/* Header */}
                                    <div className="flex items-start justify-between mb-2">
                                      <div className="flex-1">
                                        <h3 className="font-semibold text-gray-900 mb-1">
                                          {analysis.title}
                                        </h3>
                                        <div className="flex items-center gap-3 text-sm text-gray-500">
                                          <span>{analysis.date}</span>
                                          <span>•</span>
                                          <span>{analysis.source}</span>
                                        </div>
                                      </div>
                                    </div>

                                    {/* Metrics */}
                                    <div className="flex items-center gap-4 mb-3">
                                      <div className="flex items-center gap-2">
                                        <span className="text-sm text-gray-600">Impact:</span>
                                        <span className={`font-bold ${getSentimentColor(analysis.impact)}`}>
                                          {analysis.impact > 0 ? '+' : ''}{Number(analysis.impact).toFixed(2)}
                                        </span>
                                      </div>
                                      <div className="flex items-center gap-2">
                                        <span className="text-sm text-gray-600">Confidence:</span>
                                        <span className="font-bold text-blue-600">
                                          {(Number(analysis.confidence) * 100).toFixed(0)}%
                                        </span>
                                      </div>
                                      {analysis.occasion && (
                                        <div className="flex items-center gap-2">
                                          <span className="px-2 py-1 bg-blue-100 text-blue-700 text-xs rounded-full">
                                            {analysis.occasion}
                                          </span>
                                        </div>
                                      )}
                                    </div>

                                    {/* Summary */}
                                    {analysis.summary && (
                                      <div 
                                        className="text-sm text-gray-700 leading-relaxed"
                                        dangerouslySetInnerHTML={%raw%}{{ __html: analysis.summary }}{%endraw%}
                                      />
                                    )}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        };

        ReactDOM.render(<TickerDashboard />, document.getElementById('root'));
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Główna strona aplikacji"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/tickers')
def get_tickers():
    """Endpoint zwracający listę tickerów z sentymentem"""
    from flask import request
    days = request.args.get('days', 30, type=int)

    query = text(f"""
    SELECT 
        ts.ticker,
        t.company_name,
        t.sector,
        COUNT(*) as mentions,
        AVG(ts.impact::numeric) as avg_sentiment,
        AVG(ts.confidence::numeric) as avg_confidence,
        MAX(na.date) as last_mention
    FROM {schema}.ticker_sentiment ts
    JOIN {schema}.analysis_result ar ON ts.analysis_id = ar.id
    JOIN {schema}.news_articles na ON ar.news_id = na.id
    LEFT JOIN {schema}.tickers t ON ts.ticker = t.ticker
    WHERE ts.ticker IS NOT NULL
        AND na.date >= CURRENT_DATE - INTERVAL '{days} days'
    GROUP BY ts.ticker, t.company_name, t.sector
    HAVING COUNT(*) >= 1
    ORDER BY COUNT(*) DESC, ts.ticker
    """)

    with engine.connect() as conn:
        result = conn.execute(query)
        tickers = []
        for row in result:
            tickers.append({
                'ticker': row[0],
                'company_name': row[1],
                'sector': row[2],
                'mentions': int(row[3]),
                'avg_sentiment': float(row[4]) if row[4] else 0,
                'avg_confidence': float(row[5]) if row[5] else 0,
                'last_mention': row[6].strftime('%Y-%m-%d') if row[6] else None
            })

    return jsonify(tickers)

def format_summary(summary_json):
    """Konwertuje JSON summary na human-friendly opis"""
    import json

    try:
        if isinstance(summary_json, str):
            data = json.loads(summary_json)
        else:
            data = summary_json

        # Podstawowy opis z reason
        description = data.get('reason', 'Brak szczegółowego opisu.')

        # Dodaj informacje o rekomendacji brokerskiej (jeśli są)
        if data.get('brokerage_house'):
            parts = [f"<strong>Dom maklerski {data['brokerage_house']}</strong>"]

            if data.get('price_recomendation'):
                parts.append(f"Rekomendacja: <strong>{data['price_recomendation']}</strong>")

            if data.get('price_old') and data.get('price_new'):
                parts.append(f"Zmiana ceny docelowej: {data['price_old']} → {data['price_new']}")
            elif data.get('price_new'):
                parts.append(f"Cena docelowa: {data['price_new']}")

            if data.get('price_comment'):
                parts.append(data['price_comment'])

            description = '<br>'.join(parts)

        # Dodaj informacje o typie i sektorze
        metadata = []
        if data.get('typ'):
            metadata.append(f"Typ: {data['typ']}")
        if data.get('sector'):
            metadata.append(f"Sektor: {data['sector']}")
        if data.get('occasion'):
            metadata.append(f"Horyzont: {data['occasion']}")

        if metadata:
            description += f"<br><small class='text-gray-500'>({' | '.join(metadata)})</small>"

        return description

    except (json.JSONDecodeError, TypeError):
        # Jeśli to nie jest JSON, zwróć jako tekst
        return summary_json if summary_json else 'Brak opisu'

@app.route('/api/analyses/<ticker>')
def get_analyses(ticker):
    """Endpoint zwracający szczegółowe analizy dla tickera"""
    from flask import request
    days = request.args.get('days', 30, type=int)

    query = text(f"""
    SELECT 
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
    ORDER BY na.date DESC, ts.impact DESC
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {'ticker': ticker})
        analyses = []
        for row in result:
            analyses.append({
                'date': row[0].strftime('%Y-%m-%d') if row[0] else None,
                'title': row[1],
                'source': row[2],
                'url': row[3],
                'impact': float(row[4]) if row[4] else 0,
                'confidence': float(row[5]) if row[5] else 0,
                'occasion': row[6],
                'summary': format_summary(row[7])
            })

    return jsonify(analyses)

if __name__ == '__main__':
    print("🚀 Uruchamiam dashboard...")
    print("📊 Otwórz przeglądarkę: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
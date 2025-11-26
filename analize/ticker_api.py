"""
Flask API dla interaktywnego dashboardu tickerów z wykresem kursu
Uruchom: python ticker_api.py
Potem otwórz: http://localhost:5000

Wymagane biblioteki:
pip install flask sqlalchemy yfinance psycopg2-binary
"""
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, render_template_string, jsonify, request
from actions import run_ticker_scraper
from sqlalchemy import create_engine, text
from tools.ticker_analizer import getScoreWithDetails, RATING_LABELS
from tools.moving_analizer import calculate_moving_averages_signals
import yfinance as yf
from functools import lru_cache
import json

app = Flask(__name__)


# Konfiguracja bazy danych
def get_db_engine():
    db_url = "postgresql:///?service=stock"
    engine = create_engine(db_url)
    schema = os.getenv('DB_SCHEMA', 'stock')
    return engine, schema


engine, schema = get_db_engine()


# Cache dla cen z Yahoo Finance
@lru_cache(maxsize=1000)
def get_current_price(ticker_symbol):
    """Pobiera aktualną cenę tickera z Yahoo Finance"""
    try:
        if len(ticker_symbol) <= 4 and ticker_symbol.isupper():
            yf_symbol = f"{ticker_symbol}.WA"
        else:
            yf_symbol = ticker_symbol

        ticker = yf.Ticker(yf_symbol)
        info = ticker.info

        price = (
            info.get('currentPrice') or
            info.get('regularMarketPrice') or
            info.get('previousClose')
        )

        if price:
            return float(price)

        hist = ticker.history(period='1d')
        if not hist.empty:
            return float(hist['Close'].iloc[-1])

        return None

    except Exception as e:
        print(f"Błąd pobierania ceny dla {ticker_symbol}: {e}")
        return None


def get_price_history(ticker_symbol, days=90):
    """Pobiera historię cen tickera"""
    try:
        if len(ticker_symbol) <= 4 and ticker_symbol.isupper():
            yf_symbol = f"{ticker_symbol}.WA"
        else:
            yf_symbol = ticker_symbol

        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period=f"{days}d")

        if hist.empty:
            return []

        price_data = []
        for date, row in hist.iterrows():
            price_data.append({
                'date': date.strftime('%Y-%m-%d'),
                'price': float(row['Close']),
                'volume': int(row['Volume']) if 'Volume' in row else 0
            })

        return price_data

    except Exception as e:
        print(f"Błąd pobierania historii dla {ticker_symbol}: {e}")
        return []


def parse_price(price_str):
    """Parsuje cenę z różnych formatów string i usuwa waluty"""
    if not price_str:
        return None

    try:
        price_clean = str(price_str).strip()
        price_clean = price_clean.replace('PLN', '').replace('zł', '').replace('USD', '').replace('EUR', '')
        price_clean = price_clean.replace('$', '').replace('€', '').strip()
        price_clean = price_clean.replace(',', '.')
        price_clean = ''.join(c for c in price_clean if c.isdigit() or c == '.')

        if price_clean:
            return float(price_clean)
    except (ValueError, TypeError):
        pass

    return None


def signal_to_label_and_color(signal_value):
    """
    Konwertuje wartość sygnału liczbowego na etykietę tekstową i kolor

    Args:
        signal_value: wartość od -2 do 2
        -2: Mocne sprzedaj
        -1: Sprzedaj
         0: Neutralne/Trzymaj
         1: Kupuj
         2: Mocne kupuj

    Returns:
        dict z 'label', 'color' i 'bg_color'
    """
    mapping = {
        2: {
            'label': 'Mocne kupuj',
            'color': '#065f46',  # ciemny zielony (text)
            'bg_color': '#d1fae5'  # jasny zielony (background)
        },
        1: {
            'label': 'Kupuj',
            'color': '#047857',  # zielony (text)
            'bg_color': '#d1fae5'  # jasny zielony (background)
        },
        0: {
            'label': 'Neutralne',
            'color': '#4b5563',  # szary (text)
            'bg_color': '#f3f4f6'  # jasny szary (background)
        },
        -1: {
            'label': 'Sprzedaj',
            'color': '#b91c1c',  # czerwony (text)
            'bg_color': '#fee2e2'  # jasny czerwony (background)
        },
        -2: {
            'label': 'Mocne sprzedaj',
            'color': '#7f1d1d',  # ciemny czerwony (text)
            'bg_color': '#fee2e2'  # jasny czerwony (background)
        }
    }

    return mapping.get(signal_value, mapping[0])


def get_technical_analysis(ticker_symbol, period="1y"):
    """
    Pobiera analizę techniczną dla tickera

    Args:
        ticker_symbol: symbol tickera (np. 'PKO', 'CDR')
        period: okres analizy (domyślnie "1y")

    Returns:
        dict z analizą techniczną zawierającą:
        - summary: podsumowanie z etykietami i kolorami
        - details: szczegółowe informacje o wskaźnikach
    """
    try:
        # Konwersja symbolu na format Yahoo Finance
        if len(ticker_symbol) <= 4 and ticker_symbol.isupper():
            yf_symbol = f"{ticker_symbol}.WA"
        else:
            yf_symbol = ticker_symbol

        # Pobierz dane z Yahoo Finance
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=period)

        if df.empty:
            return {
                'error': 'Brak danych dla tickera',
                'summary': None,
                'details': None
            }

        # Analiza wskaźników technicznych
        indicators_score, indicators_details = getScoreWithDetails(df)
        indicators_info = signal_to_label_and_color(indicators_score)

        # Analiza średnich kroczących
        ma_results = calculate_moving_averages_signals(df)
        ma_score = ma_results['overall_summary']['signal']
        ma_info = signal_to_label_and_color(ma_score)

        # Przygotuj szczegóły średnich kroczących
        ma_details = []
        for ma_type in ['sma', 'ema']:
            details_key = f'{ma_type}_details'
            if details_key in ma_results:
                for period_name, period_data in ma_results[details_key].items():
                    ma_details.append({
                        'name': period_name,
                        'value': period_data['value'],
                        'signal': period_data['signal'],
                        'difference': f"{period_data['difference']:+.2f}%"
                    })

        # Zwróć strukturę z podsumowaniem i szczegółami
        return {
            'summary': {
                'indicators': {
                    'label': indicators_info['label'],
                    'color': indicators_info['color'],
                    'bg_color': indicators_info['bg_color'],
                    'score': indicators_score
                },
                'moving_averages': {
                    'label': ma_info['label'],
                    'color': ma_info['color'],
                    'bg_color': ma_info['bg_color'],
                    'score': ma_score,
                    'buy_count': ma_results['overall_summary']['buy_count'],
                    'sell_count': ma_results['overall_summary']['sell_count']
                }
            },
            'details': {
                'indicators': indicators_details,
                'moving_averages': ma_details,
                'current_price': ma_results['current_price']
            }
        }

    except Exception as e:
        print(f"Błąd analizy technicznej dla {ticker_symbol}: {e}")
        return {
            'error': str(e),
            'summary': None,
            'details': None
        }


def format_summary(summary_json):
    """Konwertuje JSON summary na human-friendly opis"""
    try:
        if isinstance(summary_json, str):
            data = json.loads(summary_json)
        else:
            data = summary_json

        description = data.get('reason', 'Brak szczegółowego opisu.')

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
        return summary_json if summary_json else 'Brak opisu'


# HTML Template z React aplikacją
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Analiza Sentymentu Tickerów</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <style>
        .ticker-select-container .ticker-select__control {
            border-radius: 0.5rem;
            border-color: #d1d5db;
        }
        .ticker-select-container .ticker-select__multi-value {
            background-color: #dbeafe;
        }
    </style>
</head>
<body class="bg-gray-50">
    <div id="root"></div>
    
    <script type="text/babel">
    {% raw %}
        const { useState, useEffect, useRef } = React;

        // Komponent wykresu Canvas z punktami dla newsów
        function PriceChart({ ticker, priceHistory, brokerageAnalyses, analyses, onNewsClick }) {
          const canvasRef = useRef(null);
          const [hoveredNews, setHoveredNews] = useState(null);

          useEffect(() => {
            if (!canvasRef.current || !priceHistory || priceHistory.length === 0) return;

            const canvas = canvasRef.current;
            const ctx = canvas.getContext('2d');
            const width = canvas.width;
            const height = canvas.height;

            ctx.clearRect(0, 0, width, height);

            const prices = priceHistory.map(p => p.price);
            const minPrice = Math.min(...prices);
            const maxPrice = Math.max(...prices);
            const priceRange = maxPrice - minPrice;

            const margin = { top: 20, right: 80, bottom: 40, left: 60 };
            const chartWidth = width - margin.left - margin.right;
            const chartHeight = height - margin.top - margin.bottom;

            // Funkcja do konwersji daty na pozycję X
            const dateToX = (dateStr) => {
              const targetDate = new Date(dateStr);
              const firstDate = new Date(priceHistory[0].date);
              const lastDate = new Date(priceHistory[priceHistory.length - 1].date);
              const totalRange = lastDate - firstDate;
              const datePos = targetDate - firstDate;
              return margin.left + (datePos / totalRange) * chartWidth;
            };

            // Osie
            ctx.strokeStyle = '#e5e7eb';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(margin.left, margin.top);
            ctx.lineTo(margin.left, height - margin.bottom);
            ctx.lineTo(width - margin.right, height - margin.bottom);
            ctx.stroke();

            // Siatka i etykiety Y
            ctx.fillStyle = '#6b7280';
            ctx.font = '12px sans-serif';
            const ySteps = 5;
            for (let i = 0; i <= ySteps; i++) {
              const y = margin.top + (chartHeight / ySteps) * i;
              const price = maxPrice - (priceRange / ySteps) * i;

              ctx.strokeStyle = '#f3f4f6';
              ctx.beginPath();
              ctx.moveTo(margin.left, y);
              ctx.lineTo(width - margin.right, y);
              ctx.stroke();

              ctx.fillStyle = '#6b7280';
              ctx.textAlign = 'right';
              ctx.fillText(price.toFixed(2), margin.left - 10, y + 4);
            }

            // Wykres
            ctx.strokeStyle = '#3b82f6';
            ctx.lineWidth = 2;
            ctx.beginPath();

            priceHistory.forEach((item, i) => {
              const x = margin.left + (chartWidth / (priceHistory.length - 1)) * i;
              const y = margin.top + chartHeight - ((item.price - minPrice) / priceRange) * chartHeight;

              if (i === 0) {
                ctx.moveTo(x, y);
              } else {
                ctx.lineTo(x, y);
              }
            });

            ctx.stroke();

            // Etykiety X
            ctx.fillStyle = '#6b7280';
            ctx.textAlign = 'center';
            const xSteps = Math.min(7, priceHistory.length);
            const xInterval = Math.floor(priceHistory.length / xSteps);
            
            for (let i = 0; i < priceHistory.length; i += xInterval) {
              const x = margin.left + (chartWidth / (priceHistory.length - 1)) * i;
              const date = new Date(priceHistory[i].date);
              const label = `${date.getDate()}/${date.getMonth() + 1}`;
              ctx.fillText(label, x, height - margin.bottom + 20);
            }

            // Rysowanie punktów dla newsów
            if (analyses && analyses.length > 0) {
              analyses.forEach((analysis) => {
                const x = dateToX(analysis.date);
                
                // Znajdź najbliższą cenę dla tej daty
                const analysisDate = new Date(analysis.date);
                const closestPrice = priceHistory.reduce((prev, curr) => {
                  const prevDiff = Math.abs(new Date(prev.date) - analysisDate);
                  const currDiff = Math.abs(new Date(curr.date) - analysisDate);
                  return currDiff < prevDiff ? curr : prev;
                });
                
                const y = margin.top + chartHeight - ((closestPrice.price - minPrice) / priceRange) * chartHeight;

                // Kolor punktu bazowany na impact
                let color;
                const impact = analysis.impact;
                if (Math.abs(impact) < 0.05) color = '#9ca3af'; // gray
                else if (impact > 0.5) color = '#059669'; // dark green
                else if (impact > 0.2) color = '#10b981'; // green
                else if (impact > 0.05) color = '#4ade80'; // light green
                else if (impact > -0.2) color = '#fb923c'; // light orange
                else if (impact > -0.5) color = '#f97316'; // orange
                else color = '#dc2626'; // red

                // Rysuj punkt
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(x, y, 6, 0, 2 * Math.PI);
                ctx.fill();
                
                // Obramowanie
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 2;
                ctx.stroke();
                
                // Podświetlenie hoverowanego newsa
                if (hoveredNews && hoveredNews.date === analysis.date && hoveredNews.title === analysis.title) {
                  ctx.strokeStyle = '#000000';
                  ctx.lineWidth = 3;
                  ctx.beginPath();
                  ctx.arc(x, y, 8, 0, 2 * Math.PI);
                  ctx.stroke();
                }
              });
            }

            // Linia ceny docelowej
            const latestBrokerage = brokerageAnalyses?.find(b => b.price_new);
            if (latestBrokerage && latestBrokerage.price_new) {
              const targetPrice = latestBrokerage.price_new;
              const y = margin.top + chartHeight - ((targetPrice - minPrice) / priceRange) * chartHeight;

              ctx.strokeStyle = '#10b981';
              ctx.lineWidth = 2;
              ctx.setLineDash([5, 5]);
              ctx.beginPath();
              ctx.moveTo(margin.left, y);
              ctx.lineTo(width - margin.right, y);
              ctx.stroke();
              ctx.setLineDash([]);

              ctx.fillStyle = '#10b981';
              ctx.font = 'bold 12px sans-serif';
              ctx.textAlign = 'left';
              ctx.fillText(`Cel: ${targetPrice.toFixed(2)}`, width - margin.right + 5, y + 4);
            }

          }, [priceHistory, brokerageAnalyses, analyses, hoveredNews]);

          const handleCanvasClick = (e) => {
            if (!canvasRef.current || !analyses) return;
            
            const rect = canvasRef.current.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            // Sprawdź czy kliknięto w któryś punkt
            const clickRadius = 10;
            for (const analysis of analyses) {
              // Tutaj potrzebujemy odtworzyć pozycję punktu
              // (uproszczone - w produkcji lepiej przechowywać pozycje)
              if (onNewsClick) {
                onNewsClick(analysis);
                break;
              }
            }
          };

          if (!priceHistory || priceHistory.length === 0) {
            return (
              <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
                <div className="text-center text-gray-500 py-8">
                  <p>Brak danych o cenach dla {ticker}</p>
                </div>
              </div>
            );
          }

          const latestPrice = priceHistory[priceHistory.length - 1]?.price;
          const firstPrice = priceHistory[0]?.price;
          const priceChange = latestPrice && firstPrice ? ((latestPrice - firstPrice) / firstPrice * 100) : 0;
          const latestBrokerage = brokerageAnalyses?.find(b => b.price_new);

          return (
            <div className="bg-white rounded-lg shadow-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-xl font-bold text-gray-900">Wykres kursu {ticker}</h3>
                  <p className="text-sm text-gray-600">Ostatnie {priceHistory.length} dni</p>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-bold text-gray-900">
                    {latestPrice?.toFixed(2)} PLN
                  </div>
                  <div className={`text-sm font-semibold ${priceChange >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
                  </div>
                </div>
              </div>

              <canvas 
                ref={canvasRef} 
                width={900} 
                height={250}
                className="w-full cursor-pointer"
                style={{ maxWidth: '100%', height: 'auto' }}
                onClick={handleCanvasClick}
              />

              <div className="mt-4 flex items-center gap-4 text-xs text-gray-600">
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-green-500"></span>
                  Pozytywny (impact &gt; 0.3)
                </span>
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-lime-500"></span>
                  Lekko pozytywny
                </span>
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-gray-400"></span>
                  Neutralny
                </span>
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-orange-500"></span>
                  Lekko negatywny
                </span>
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-red-500"></span>
                  Negatywny (impact &lt; -0.3)
                </span>
              </div>

              {latestBrokerage && (
                <div className="mt-4 p-3 bg-green-50 rounded-lg">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-700">
                      Cena docelowa wg <strong>{latestBrokerage.brokerage_house}</strong>:
                    </span>
                    <div className="flex items-center gap-4">
                      <span className="font-bold text-green-700">
                        {latestBrokerage.price_new?.toFixed(2)} PLN
                      </span>
                      {latestBrokerage.upside_percent !== null && (
                        <span className={`font-semibold ${latestBrokerage.upside_percent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          ({latestBrokerage.upside_percent >= 0 ? '+' : ''}{latestBrokerage.upside_percent.toFixed(1)}%)
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        }

        // Komponent analizy technicznej
        function TechnicalAnalysis({ ticker }) {
          const [technicalData, setTechnicalData] = useState(null);
          const [loading, setLoading] = useState(false);
          const [showDetails, setShowDetails] = useState(false);
          const [error, setError] = useState(null);

          useEffect(() => {
            if (ticker) {
              fetchTechnicalAnalysis();
            }
          }, [ticker]);

          const fetchTechnicalAnalysis = async () => {
            setLoading(true);
            setError(null);
            try {
              const response = await fetch(`/api/technical_analysis/${ticker}?period=1y`);
              const data = await response.json();

              if (data.error) {
                setError(data.error);
                setTechnicalData(null);
              } else {
                setTechnicalData(data);
              }
            } catch (error) {
              console.error('Error fetching technical analysis:', error);
              setError('Błąd pobierania danych');
              setTechnicalData(null);
            } finally {
              setLoading(false);
            }
          };

          if (loading) {
            return (
              <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-lg font-bold text-gray-900 mb-4">Analiza Techniczna</h3>
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                </div>
              </div>
            );
          }

          if (error) {
            return (
              <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-lg font-bold text-gray-900 mb-4">Analiza Techniczna</h3>
                <div className="text-center text-gray-500 py-4">
                  <p>{error}</p>
                </div>
              </div>
            );
          }

          if (!technicalData || !technicalData.summary) {
            return null;
          }

          const { summary, details } = technicalData;

          return (
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-gray-900">Analiza Techniczna</h3>
                <button
                  onClick={() => setShowDetails(!showDetails)}
                  className="text-sm text-blue-600 hover:text-blue-800 font-medium"
                >
                  {showDetails ? 'Ukryj szczegóły ▲' : 'Pokaż szczegóły ▼'}
                </button>
              </div>

              {/* Podsumowanie */}
              <div className="grid grid-cols-2 gap-4 mb-4">
                {/* Wskaźniki */}
                <div
                  className="p-4 rounded-lg border-2"
                  style={{
                    backgroundColor: summary.indicators.bg_color,
                    borderColor: summary.indicators.color
                  }}
                >
                  <div className="text-sm font-medium text-gray-600 mb-2">Wskaźniki</div>
                  <div
                    className="text-2xl font-bold"
                    style={{ color: summary.indicators.color }}
                  >
                    {summary.indicators.label}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    Score: {summary.indicators.score}
                  </div>
                </div>

                {/* Średnie kroczące */}
                <div
                  className="p-4 rounded-lg border-2"
                  style={{
                    backgroundColor: summary.moving_averages.bg_color,
                    borderColor: summary.moving_averages.color
                  }}
                >
                  <div className="text-sm font-medium text-gray-600 mb-2">Średnie kroczące</div>
                  <div
                    className="text-2xl font-bold"
                    style={{ color: summary.moving_averages.color }}
                  >
                    {summary.moving_averages.label}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    Kupuj: {summary.moving_averages.buy_count} | Sprzedaj: {summary.moving_averages.sell_count}
                  </div>
                </div>
              </div>

              {/* Szczegóły (rozwijane) */}
              {showDetails && details && (
                <div className="border-t pt-4">
                  <div className="grid grid-cols-2 gap-6">
                    {/* Szczegóły wskaźników */}
                    <div>
                      <h4 className="text-sm font-semibold text-gray-900 mb-3">Szczegóły wskaźników</h4>
                      <div className="space-y-1 text-xs font-mono">
                        {details.indicators && details.indicators.map((indicator, idx) => (
                          <div key={idx} className="text-gray-700">
                            {indicator}
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Szczegóły średnich kroczących */}
                    <div>
                      <h4 className="text-sm font-semibold text-gray-900 mb-3">
                        Średnie kroczące (Aktualna cena: {details.current_price})
                      </h4>
                      <div className="space-y-2">
                        {details.moving_averages && details.moving_averages.map((ma, idx) => (
                          <div key={idx} className="flex items-center justify-between text-xs p-2 bg-gray-50 rounded">
                            <span className="font-semibold">{ma.name}</span>
                            <span className="text-gray-600">{ma.value}</span>
                            <span
                              className={`font-medium ${
                                ma.signal === 'kupuj' ? 'text-green-600' :
                                ma.signal === 'sprzedaj' ? 'text-red-600' :
                                'text-gray-500'
                              }`}
                            >
                              {ma.signal}
                            </span>
                            <span
                              className={`font-mono ${
                                ma.difference.startsWith('+') ? 'text-green-600' : 'text-red-600'
                              }`}
                            >
                              {ma.difference}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        }

        // Komponent MultiSelect
        function TickerSelect({ analysisId, onSave }) {
            const [allTickers, setAllTickers] = useState([]);
            const [selectedTickers, setSelectedTickers] = useState([]);
            const [isLoading, setIsLoading] = useState(false);

            useEffect(() => {
                fetch('/api/all_tickers')
                    .then(res => res.json())
                    .then(data => setAllTickers(data))
                    .catch(err => console.error("Error fetching all tickers:", err));
            }, []);

            const handleSave = async () => {
                setIsLoading(true);
                try {
                    const response = await fetch('/api/update_analysis_tickers', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            analysis_id: analysisId,
                            tickers: selectedTickers
                        })
                    });
                    if (response.ok) {
                        alert('Tickery zostały zaktualizowane.');
                        if (onSave) {
                            onSave();
                        }
                    } else {
                        alert('Wystąpił błąd podczas zapisywania tickerów.');
                    }
                } catch (error) {
                    console.error('Error saving tickers:', error);
                    alert('Wystąpił błąd sieci.');
                } finally {
                    setIsLoading(false);
                }
            };

            const toggleTicker = (tickerValue) => {
                setSelectedTickers(prev =>
                    prev.includes(tickerValue)
                        ? prev.filter(t => t !== tickerValue)
                        : [...prev, tickerValue]
                );
            };

            return (
                <div className="mt-2 p-2 border border-blue-200 bg-blue-50 rounded-lg">
                    <p className="text-xs font-semibold text-blue-800 mb-2">Przypisz tickery do tej analizy:</p>
                    <div className="max-h-32 overflow-y-auto border bg-white rounded p-1 text-xs mb-2">
                        {allTickers.map(ticker => (
                            <label key={ticker.value} className="flex items-center p-1 hover:bg-gray-100 rounded">
                                <input
                                    type="checkbox"
                                    checked={selectedTickers.includes(ticker.value)}
                                    onChange={() => toggleTicker(ticker.value)}
                                    className="h-3 w-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                                />
                                <span className="ml-2 text-gray-700">{ticker.label}</span>
                            </label>
                        ))}
                    </div>
                    <button
                        onClick={handleSave}
                        disabled={isLoading || selectedTickers.length === 0}
                        className={`w-full px-2 py-1 text-xs font-semibold text-white rounded-md transition-colors ${
                            (isLoading || selectedTickers.length === 0)
                                ? 'bg-gray-400 cursor-not-allowed'
                                : 'bg-blue-600 hover:bg-blue-700'
                        }`}
                    >
                        {isLoading ? 'Zapisywanie...' : 'Zapisz'}
                    </button>
                </div>
            );
        }
        
        // Komponent widoku kalendarzowego
        function CalendarView({ days, onBack, onTickerSelect }) {
          const [calendarStats, setCalendarStats] = useState([]);
          const [selectedDate, setSelectedDate] = useState(null);
          const [newsForDate, setNewsForDate] = useState([]);
          const [loading, setLoading] = useState(false);
          const [currentMonth, setCurrentMonth] = useState(new Date());

          useEffect(() => {
            fetchCalendarStats();
          }, [days]);

          const fetchCalendarStats = async () => {
            try {
              const response = await fetch(`/api/calendar_stats?days=${days}`);
              const data = await response.json();
              setCalendarStats(data);
            } catch (error) {
              console.error('Error fetching calendar stats:', error);
            }
          };

          const fetchNewsForDate = async (date) => {
            setLoading(true);
            try {
              const response = await fetch(`/api/news_by_date/${date}`);
              const data = await response.json();
              setNewsForDate(data);
              setSelectedDate(date);
            } catch (error) {
              console.error('Error fetching news for date:', error);
            } finally {
              setLoading(false);
            }
          };

          const markAsDuplicate = async (newsId) => {
            if (!confirm('Czy na pewno chcesz oznaczyć ten news jako duplikat?')) return;

            try {
              const response = await fetch('/api/mark_duplicate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ news_id: newsId })
              });

              if (response.ok) {
                fetchNewsForDate(selectedDate);
                fetchCalendarStats();
                alert('News oznaczony jako duplikat');
              } else {
                alert('Błąd przy oznaczaniu newsa jako duplikat');
              }
            } catch (error) {
              console.error('Error marking as duplicate:', error);
              alert('Błąd połączenia z serwerem');
            }
          };

          const getDayStats = (dateStr) => {
            return calendarStats.find(s => s.date === dateStr);
          };

          const getDayColor = (stats) => {
            if (!stats || stats.news_count === 0) return 'bg-gray-50';

            const avgImpact = stats.avg_impact;
            const count = stats.news_count;

            // Intensywność bazowana na liczbie newsów
            if (avgImpact > 0.1) {
              if (count > 5) return 'bg-green-500';
              if (count > 2) return 'bg-green-400';
              return 'bg-green-300';
            } else if (avgImpact < -0.1) {
              if (count > 5) return 'bg-red-500';
              if (count > 2) return 'bg-red-400';
              return 'bg-red-300';
            } else {
              if (count > 5) return 'bg-yellow-500';
              if (count > 2) return 'bg-yellow-400';
              return 'bg-yellow-300';
            }
          };

          const getImpactColor = (impact) => {
            const val = Math.abs(impact);
            if (val < 0.05) return 'bg-gray-400';
            if (impact > 0.5) return 'bg-green-600';
            if (impact > 0.2) return 'bg-green-500';
            if (impact > 0.05) return 'bg-green-400';
            if (impact > -0.05) return 'bg-gray-400';
            if (impact > -0.2) return 'bg-orange-400';
            if (impact > -0.5) return 'bg-orange-500';
            return 'bg-red-600';
          };

          const getSentimentColor = (sentiment) => {
            const val = Math.abs(sentiment);
            if (val < 0.05) return 'text-gray-500';
            if (sentiment > 0.3) return 'text-green-600';
            if (sentiment > 0) return 'text-green-400';
            if (sentiment > -0.3) return 'text-yellow-500';
            return 'text-red-500';
          };

          // Generuj dni dla kalendarza
          const generateCalendarDays = () => {
            const year = currentMonth.getFullYear();
            const month = currentMonth.getMonth();

            const firstDay = new Date(year, month, 1);
            const lastDay = new Date(year, month + 1, 0);

            const daysInMonth = lastDay.getDate();
            const startDayOfWeek = (firstDay.getDay() + 6) % 7; // Monday = 0, Sunday = 6

            const days = [];

            // Puste dni przed pierwszym dniem miesiąca
            for (let i = 0; i < startDayOfWeek; i++) {
              days.push(null);
            }

            // Dni miesiąca
            for (let day = 1; day <= daysInMonth; day++) {
              days.push(new Date(year, month, day));
            }

            return days;
          };

          const calendarDays = generateCalendarDays();
          const monthNames = ['Styczeń', 'Luty', 'Marzec', 'Kwiecień', 'Maj', 'Czerwiec',
                            'Lipiec', 'Sierpień', 'Wrzesień', 'Październik', 'Listopad', 'Grudzień'];

          return (
            <div className="space-y-4">
              <div className="bg-white rounded-lg shadow p-4">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xl font-bold text-gray-900">
                    {monthNames[currentMonth.getMonth()]} {currentMonth.getFullYear()}
                  </h2>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1))}
                      className="px-3 py-1 bg-gray-200 hover:bg-gray-300 rounded-lg"
                    >
                      ←
                    </button>
                    <button
                      onClick={() => setCurrentMonth(new Date())}
                      className="px-3 py-1 bg-blue-500 hover:bg-blue-600 text-white rounded-lg text-sm"
                    >
                      Dziś
                    </button>
                    <button
                      onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1))}
                      className="px-3 py-1 bg-gray-200 hover:bg-gray-300 rounded-lg"
                    >
                      →
                    </button>
                  </div>
                </div>

                {/* Legenda */}
                <div className="mb-4 flex items-center gap-4 text-xs text-gray-600 flex-wrap">
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 rounded bg-green-500"></span>
                    Pozytywne (wiele newsów)
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 rounded bg-green-300"></span>
                    Pozytywne (kilka)
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 rounded bg-yellow-400"></span>
                    Mieszane/Neutralne
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 rounded bg-red-300"></span>
                    Negatywne (kilka)
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 rounded bg-red-500"></span>
                    Negatywne (wiele)
                  </span>
                </div>

                {/* Kalendarz */}
                <div className="grid grid-cols-7 gap-2">
                  {['Pn', 'Wt', 'Śr', 'Cz', 'Pt', 'Sb', 'Nd'].map(day => (
                    <div key={day} className="text-center font-bold text-sm text-gray-600 py-2">
                      {day}
                    </div>
                  ))}

                  {calendarDays.map((date, idx) => {
                    if (!date) {
                      return <div key={idx} className="p-2"></div>;
                    }

                    const year = date.getFullYear();
                    const month = (date.getMonth() + 1).toString().padStart(2, '0');
                    const day = date.getDate().toString().padStart(2, '0');
                    const dateStr = `${year}-${month}-${day}`;
                    
                    const stats = getDayStats(dateStr);
                    const dayColor = getDayColor(stats);
                    const isSelected = selectedDate === dateStr;

                    return (
                      <button
                        key={idx}
                        onClick={() => fetchNewsForDate(dateStr)}
                        className={`p-2 text-center ${dayColor} rounded-lg hover:ring-2 hover:ring-blue-500 transition-all relative
                          ${isSelected ? 'ring-2 ring-blue-600' : ''}
                        `}
                      >
                        <div className="font-bold text-sm text-gray-800">
                          {date.getDate()}
                        </div>
                        {stats && stats.news_count > 0 && (
                          <div className="text-xs font-bold text-gray-700 mt-1">
                            {stats.news_count} news
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Lista newsów z wybranego dnia */}
              {selectedDate && (
                <div className="bg-white rounded-lg shadow p-4">
                  <h3 className="text-lg font-bold text-gray-900 mb-3">
                    Newsy z {selectedDate} ({newsForDate.length})
                  </h3>

                  {loading ? (
                    <div className="flex items-center justify-center py-12">
                      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                    </div>
                  ) : newsForDate.length === 0 ? (
                    <p className="text-gray-500 text-center py-8">Brak newsów z tego dnia</p>
                  ) : (
                    <div className="space-y-3">
                      {newsForDate.map((news, idx) => (
                        <div key={idx} className="border border-gray-200 rounded-lg p-3 hover:shadow-md transition-shadow relative">
                          <button
                            onClick={() => markAsDuplicate(news.news_id)}
                            className="absolute top-1.5 right-1.5 w-6 h-6 flex items-center justify-center bg-red-500 hover:bg-red-600 text-white rounded-full text-sm font-bold"
                            title="Oznacz jako duplikat"
                          >
                            ✕
                          </button>

                          <div className="flex items-start gap-3">
                            <div className="flex-shrink-0">
                              <div className={`w-2 h-16 ${getImpactColor(news.impact)} rounded`}></div>
                            </div>

                            <div className="flex-1 pr-8">
                              <h4 className="font-semibold text-sm text-gray-900 mb-1">
                                {news.title}
                              </h4>

                              {/* Tickery */}
                              <div className="flex items-center gap-2 mb-2 flex-wrap">
                                {news.tickers && news.tickers.length > 0 ? (
                                    news.tickers.map((ticker, tidx) => (
                                      <a
                                        href="#"
                                        key={tidx}
                                        onClick={(e) => {
                                            e.preventDefault();
                                            if (onTickerSelect) {
                                                onTickerSelect(ticker.ticker);
                                            }
                                        }}
                                        className="px-2 py-0.5 bg-blue-100 text-blue-800 text-xs font-bold rounded hover:bg-blue-200 cursor-pointer"
                                      >
                                        {ticker.ticker}
                                      </a>
                                    ))
                                ) : (
                                    <span className="px-2 py-0.5 bg-yellow-100 text-yellow-800 text-xs font-semibold rounded">
                                        Brak przypisanych tickerów
                                    </span>
                                )}
                              </div>

                              {news.tickers && news.tickers.length === 0 && (
                                <TickerSelect
                                    analysisId={news.analysis_id}
                                    onSave={() => fetchNewsForDate(selectedDate)}
                                />
                              )}

                              <div className="flex items-center gap-2 text-xs text-gray-500 mb-2">
                                {news.published_at && <span className="font-semibold">{news.published_at}</span>}
                                <span>{news.source}</span>
                                {news.url && (
                                  <>
                                    <span>•</span>
                                    <a
                                      href={news.url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-blue-600 hover:underline"
                                    >
                                      Link
                                    </a>
                                  </>
                                )}
                              </div>

                              <div className="flex items-center gap-3 mb-2">
                                <div className="flex items-center gap-1.5">
                                  <span className="text-xs text-gray-600">Impact:</span>
                                  <span className={`font-bold text-sm ${getSentimentColor(news.impact)}`}>
                                    {news.impact > 0 ? '+' : ''}{Number(news.impact).toFixed(2)}
                                  </span>
                                </div>
                                <div className="flex items-center gap-1.5">
                                  <span className="text-xs text-gray-600">Confidence:</span>
                                  <span className="font-bold text-sm text-blue-600">
                                    {(Number(news.confidence) * 100).toFixed(0)}%
                                  </span>
                                </div>
                              </div>

                              {news.summary && (
                                <div
                                  className="text-xs text-gray-700 leading-relaxed"
                                  dangerouslySetInnerHTML={{ __html: news.summary }}
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
          );
        }

        // Komponent widoku odrzuconych newsów
        function CalendarRejectedView({ days, onBack }) {
          const [calendarStats, setCalendarStats] = useState([]);
          const [selectedDate, setSelectedDate] = useState(null);
          const [newsForDate, setNewsForDate] = useState([]);
          const [loading, setLoading] = useState(false);
          const [reanalyzing, setReanalyzing] = useState({});
          const [currentMonth, setCurrentMonth] = useState(new Date());

          useEffect(() => {
            fetchCalendarStats();
          }, [days]);

          const fetchCalendarStats = async () => {
            try {
              const response = await fetch(`/api/rejected_calendar_stats?days=${days}`);
              const data = await response.json();
              setCalendarStats(data);
            } catch (error) {
              console.error('Error fetching rejected calendar stats:', error);
            }
          };

          const fetchNewsForDate = async (date) => {
            setLoading(true);
            try {
              const response = await fetch(`/api/rejected_news_by_date/${date}`);
              const data = await response.json();
              setNewsForDate(data);
              setSelectedDate(date);
            } catch (error) {
              console.error('Error fetching rejected news for date:', error);
            } finally {
              setLoading(false);
            }
          };

          const reanalyzeNews = async (newsId) => {
            if (!confirm('Czy na pewno chcesz ponownie przeanalizować ten news przez AI?')) return;

            setReanalyzing(prev => ({ ...prev, [newsId]: true }));
            try {
              const response = await fetch('/api/reanalyze_news', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ news_id: newsId })
              });

              const result = await response.json();

              if (response.ok) {
                alert('News został pomyślnie przeanalizowany przez AI!');
                fetchNewsForDate(selectedDate);
                fetchCalendarStats();
              } else {
                alert(`Błąd analizy: ${result.error}`);
              }
            } catch (error) {
              console.error('Error reanalyzing news:', error);
              alert('Błąd połączenia z serwerem');
            } finally {
              setReanalyzing(prev => ({ ...prev, [newsId]: false }));
            }
          };

          const getDayStats = (dateStr) => {
            return calendarStats.filter(s => s.date === dateStr);
          };

          const getDayColor = (stats) => {
            if (!stats || stats.length === 0) return 'bg-gray-50';

            const totalCount = stats.reduce((sum, s) => sum + s.news_count, 0);

            if (totalCount > 10) return 'bg-red-500';
            if (totalCount > 5) return 'bg-red-400';
            if (totalCount > 2) return 'bg-red-300';
            return 'bg-red-200';
          };

          // Generuj dni dla kalendarza
          const generateCalendarDays = () => {
            const year = currentMonth.getFullYear();
            const month = currentMonth.getMonth();

            const firstDay = new Date(year, month, 1);
            const lastDay = new Date(year, month + 1, 0);

            const daysInMonth = lastDay.getDate();
            const startDayOfWeek = (firstDay.getDay() + 6) % 7; // Monday = 0, Sunday = 6

            const days = [];

            // Puste dni przed pierwszym dniem miesiąca
            for (let i = 0; i < startDayOfWeek; i++) {
              days.push(null);
            }

            // Dni miesiąca
            for (let day = 1; day <= daysInMonth; day++) {
              days.push(new Date(year, month, day));
            }

            return days;
          };

          const calendarDays = generateCalendarDays();
          const monthNames = ['Styczeń', 'Luty', 'Marzec', 'Kwiecień', 'Maj', 'Czerwiec',
                            'Lipiec', 'Sierpień', 'Wrzesień', 'Październik', 'Listopad', 'Grudzień'];

          return (
            <div className="space-y-4">
              <div className="bg-white rounded-lg shadow p-4">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xl font-bold text-gray-900">
                    Odrzucone Newsy - {monthNames[currentMonth.getMonth()]} {currentMonth.getFullYear()}
                  </h2>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1))}
                      className="px-3 py-1 bg-gray-200 hover:bg-gray-300 rounded-lg"
                    >
                      ←
                    </button>
                    <button
                      onClick={() => setCurrentMonth(new Date())}
                      className="px-3 py-1 bg-red-500 hover:bg-red-600 text-white rounded-lg text-sm"
                    >
                      Dziś
                    </button>
                    <button
                      onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1))}
                      className="px-3 py-1 bg-gray-200 hover:bg-gray-300 rounded-lg"
                    >
                      →
                    </button>
                  </div>
                </div>

                {/* Legenda */}
                <div className="mb-4 flex items-center gap-4 text-xs text-gray-600 flex-wrap">
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 rounded bg-red-500"></span>
                    Wiele odrzuconych (10+)
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 rounded bg-red-300"></span>
                    Kilka odrzuconych (2-10)
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 rounded bg-red-200"></span>
                    Mało odrzuconych (1-2)
                  </span>
                </div>

                {/* Kalendarz */}
                <div className="grid grid-cols-7 gap-2">
                  {['Pn', 'Wt', 'Śr', 'Cz', 'Pt', 'Sb', 'Nd'].map(day => (
                    <div key={day} className="text-center font-bold text-sm text-gray-600 py-2">
                      {day}
                    </div>
                  ))}

                  {calendarDays.map((date, idx) => {
                    if (!date) {
                      return <div key={idx} className="p-2"></div>;
                    }

                    const year = date.getFullYear();
                    const month = (date.getMonth() + 1).toString().padStart(2, '0');
                    const day = date.getDate().toString().padStart(2, '0');
                    const dateStr = `${year}-${month}-${day}`;

                    const stats = getDayStats(dateStr);
                    const dayColor = getDayColor(stats);
                    const isSelected = selectedDate === dateStr;
                    const totalCount = stats.reduce((sum, s) => sum + s.news_count, 0);

                    return (
                      <button
                        key={idx}
                        onClick={() => fetchNewsForDate(dateStr)}
                        className={`p-2 text-center ${dayColor} rounded-lg hover:ring-2 hover:ring-red-500 transition-all relative
                          ${isSelected ? 'ring-2 ring-red-600' : ''}
                        `}
                      >
                        <div className="font-bold text-sm text-gray-800">
                          {date.getDate()}
                        </div>
                        {totalCount > 0 && (
                          <div className="text-xs font-bold text-gray-700 mt-1">
                            {totalCount} news
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Lista odrzuconych newsów z wybranego dnia */}
              {selectedDate && (
                <div className="bg-white rounded-lg shadow p-4">
                  <h3 className="text-lg font-bold text-gray-900 mb-3">
                    Odrzucone newsy z {selectedDate} ({newsForDate.length})
                  </h3>

                  {loading ? (
                    <div className="flex items-center justify-center py-12">
                      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-red-500"></div>
                    </div>
                  ) : newsForDate.length === 0 ? (
                    <p className="text-gray-500 text-center py-8">Brak odrzuconych newsów z tego dnia</p>
                  ) : (
                    <div className="space-y-3">
                      {newsForDate.map((news, idx) => (
                        <div key={idx} className="border border-red-200 rounded-lg p-4 hover:shadow-md transition-shadow bg-red-50">
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex-1">
                              <h4 className="font-semibold text-sm text-gray-900 mb-2">
                                {news.title}
                              </h4>

                              <div className="flex items-center gap-2 text-xs text-gray-500 mb-2">
                                <span>{news.source}</span>
                                {news.url && (
                                  <>
                                    <span>•</span>
                                    <a
                                      href={news.url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-blue-600 hover:underline"
                                    >
                                      Link
                                    </a>
                                  </>
                                )}
                              </div>

                              <div className="mb-2 p-2 bg-red-100 rounded border border-red-300">
                                <div className="text-xs font-semibold text-red-900 mb-1">Powód odrzucenia:</div>
                                <div className="text-xs text-red-800">{news.reason}</div>
                                <div className="text-xs text-red-600 mt-1">
                                  Score: {(news.relevance_score * 100).toFixed(1)}%
                                </div>
                              </div>

                              {news.content && (
                                <div className="text-xs text-gray-700 leading-relaxed mb-2">
                                  {news.content.substring(0, 200)}...
                                </div>
                              )}
                            </div>

                            <button
                              onClick={() => reanalyzeNews(news.news_id)}
                              disabled={reanalyzing[news.news_id]}
                              className={`flex-shrink-0 px-4 py-2 rounded-lg font-semibold text-sm transition-colors ${
                                reanalyzing[news.news_id]
                                  ? 'bg-gray-300 text-gray-600 cursor-not-allowed'
                                  : 'bg-blue-500 hover:bg-blue-600 text-white'
                              }`}
                            >
                              {reanalyzing[news.news_id] ? 'Analizowanie...' : 'Analizuj AI'}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        }

        // Główny komponent dashboardu
        function TickerDashboard() {
          const [tickers, setTickers] = useState([]);
          const [selectedTicker, setSelectedTicker] = useState(null);
          const [analyses, setAnalyses] = useState([]);
          const [brokerageAnalyses, setBrokerageAnalyses] = useState([]);
          const [priceHistory, setPriceHistory] = useState([]);
          const [loading, setLoading] = useState(false);
          const [loadingChart, setLoadingChart] = useState(false);
          const [searchTerm, setSearchTerm] = useState('');
          const [days, setDays] = useState(30);
          const [filterImpact, setFilterImpact] = useState('all');
          const [showStats, setShowStats] = useState(true);
          const [viewMode, setViewMode] = useState('tickers'); // 'tickers', 'calendar' lub 'rejected'
          const [scrapingTicker, setScrapingTicker] = useState(null);
          const [notification, setNotification] = useState({ message: '', type: '' });

          const handleTickerSelectFromCalendar = (tickerSymbol) => {
            const tickerData = tickers.find(t => t.ticker === tickerSymbol);
            if (tickerData) {
                setSelectedTicker(tickerData);
            } else {
                setSelectedTicker({ ticker: tickerSymbol });
            }
            setViewMode('tickers');
          };

          useEffect(() => {
            fetchTickers();
          }, [days]);

          useEffect(() => {
            if (selectedTicker) {
              fetchAnalyses(selectedTicker.ticker);
              fetchBrokerageAnalyses(selectedTicker.ticker);
              fetchPriceHistory(selectedTicker.ticker);
            }
          }, [selectedTicker, days]);

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

          const fetchBrokerageAnalyses = async (ticker) => {
            try {
              const response = await fetch(`/api/brokerage/${ticker}?days=${days}`);
              const data = await response.json();
              setBrokerageAnalyses(data);
            } catch (error) {
              console.error('Error fetching brokerage analyses:', error);
            }
          };

          const fetchPriceHistory = async (ticker) => {
            setLoadingChart(true);
            try {
              const response = await fetch(`/api/price_history/${ticker}?days=${days}`);
              const data = await response.json();
              setPriceHistory(data);
            } catch (error) {
              console.error('Error fetching price history:', error);
              setPriceHistory([]);
            } finally {
              setLoadingChart(false);
            }
          };

          const markAsDuplicate = async (analysisId, newsId) => {
            if (!confirm('Czy na pewno chcesz oznaczyć ten news jako duplikat?')) return;
            
            try {
              const response = await fetch('/api/mark_duplicate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ news_id: newsId })
              });
              
              if (response.ok) {
                // Odśwież listę analiz
                fetchAnalyses(selectedTicker.ticker);
                fetchTickers(); // Odśwież statystyki tickerów
                alert('News oznaczony jako duplikat i usunięty z widoku');
              } else {
                alert('Błąd przy oznaczaniu newsa jako duplikat');
              }
            } catch (error) {
              console.error('Error marking as duplicate:', error);
              alert('Błąd połączenia z serwerem');
            }
          };

          const filteredTickers = tickers.filter(t => 
            t.ticker.toLowerCase().includes(searchTerm.toLowerCase()) ||
            (t.company_name && t.company_name.toLowerCase().includes(searchTerm.toLowerCase()))
          );

          const sortedTickers = [...filteredTickers].sort((a, b) => {
            // Sortowanie: portfolio -> ulubione -> impact
            if (a.in_portfolio !== b.in_portfolio) {
                return b.in_portfolio - a.in_portfolio;
            }
            if (a.is_favorite !== b.is_favorite) {
                return b.is_favorite - a.is_favorite;
            }
            return b.avg_sentiment - a.avg_sentiment;
          });

          const filteredAnalyses = analyses.filter(a => {
            if (filterImpact === 'all') return true;
            if (filterImpact === 'positive') return a.impact > 0.05;
            if (filterImpact === 'negative') return a.impact < -0.05;
            if (filterImpact === 'neutral') return Math.abs(a.impact) <= 0.05;
            return true;
          });

          const getSentimentColor = (sentiment) => {
            const val = Math.abs(sentiment);
            if (val < 0.05) return 'text-gray-500';
            if (sentiment > 0.3) return 'text-green-600';
            if (sentiment > 0) return 'text-green-400';
            if (sentiment > -0.3) return 'text-yellow-500';
            return 'text-red-500';
          };

          const getSentimentBg = (sentiment) => {
            const val = Math.abs(sentiment);
            if (val < 0.05) return 'bg-gray-100';
            if (sentiment > 0.3) return 'bg-green-100';
            if (sentiment > 0) return 'bg-green-50';
            if (sentiment > -0.3) return 'bg-yellow-50';
            return 'bg-red-50';
          };

          const getRecommendationColor = (recommendation) => {
            if (!recommendation) return 'text-gray-600';
            const rec = recommendation.toLowerCase();
            if (rec.includes('kupuj') || rec.includes('buy') || rec.includes('accumulate')) {
              return 'text-green-600 font-bold';
            }
            if (rec.includes('trzymaj') || rec.includes('hold') || rec.includes('neutral')) {
              return 'text-yellow-600 font-bold';
            }
            if (rec.includes('sprzedaj') || rec.includes('sell') || rec.includes('reduce')) {
              return 'text-red-600 font-bold';
            }
            return 'text-gray-600';
          };

          const getUpsideColor = (upside) => {
            if (upside === null || upside === undefined) return 'text-gray-600';
            if (upside > 30) return 'text-green-700 font-bold';
            if (upside > 15) return 'text-green-600 font-semibold';
            if (upside > 5) return 'text-green-500';
            if (upside > -5) return 'text-gray-600';
            if (upside > -15) return 'text-red-500';
            if (upside > -30) return 'text-red-600 font-semibold';
            return 'text-red-700 font-bold';
          };

          const getUpsideBg = (upside) => {
            if (upside === null || upside === undefined) return 'bg-gray-50';
            if (upside > 20) return 'bg-green-100';
            if (upside > 10) return 'bg-green-50';
            if (upside > -10) return 'bg-gray-50';
            if (upside > -20) return 'bg-red-50';
            return 'bg-red-100';
          };

          const getImpactColor = (impact) => {
            const val = Math.abs(impact);
            if (val < 0.05) return 'bg-gray-400';
            if (impact > 0.5) return 'bg-green-600';
            if (impact > 0.2) return 'bg-green-500';
            if (impact > 0.05) return 'bg-green-400';
            if (impact > -0.05) return 'bg-gray-400';
            if (impact > -0.2) return 'bg-orange-400';
            if (impact > -0.5) return 'bg-orange-500';
            return 'bg-red-600';
          };

          // Statystyki dla wybranego tickera
          const tickerStats = selectedTicker ? {
            totalNews: analyses.length,
            positiveNews: analyses.filter(a => a.impact > 0.05).length,
            negativeNews: analyses.filter(a => a.impact < -0.05).length,
            neutralNews: analyses.filter(a => Math.abs(a.impact) <= 0.05).length,
            avgImpact: analyses.length > 0 ? (analyses.reduce((sum, a) => sum + a.impact, 0) / analyses.length) : 0,
            avgConfidence: analyses.length > 0 ? (analyses.reduce((sum, a) => sum + a.confidence, 0) / analyses.length) : 0
          } : null;

          return (
            <div className="min-h-screen bg-gray-50 p-4">
              <div className="max-w-7xl mx-auto">
                <div className="flex items-center justify-between mb-4">
                  <h1 className="text-2xl font-bold text-gray-900">
                    Analiza Sentymentu Tickerów
                  </h1>
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setViewMode('tickers')}
                        className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                          viewMode === 'tickers'
                            ? 'bg-blue-500 text-white'
                            : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                        }`}
                      >
                        Widok Tickerów
                      </button>
                      <button
                        onClick={() => setViewMode('calendar')}
                        className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                          viewMode === 'calendar'
                            ? 'bg-blue-500 text-white'
                            : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                        }`}
                      >
                        Kalendarz Analiz
                      </button>
                      <button
                        onClick={() => setViewMode('rejected')}
                        className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                          viewMode === 'rejected'
                            ? 'bg-red-500 text-white'
                            : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                        }`}
                      >
                        Odrzucone Newsy
                      </button>
                    </div>
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-gray-600">Okres:</label>
                      <select
                        value={days}
                        onChange={(e) => setDays(Number(e.target.value))}
                        className="px-2 py-1 text-sm border border-gray-300 rounded-lg"
                      >
                        <option value="7">7 dni</option>
                        <option value="14">14 dni</option>
                        <option value="30">1 miesiąc</option>
                        <option value="90">3 miesiące</option>
                        <option value="180">6 miesięcy</option>
                        <option value="365">1 rok</option>
                      </select>
                    </div>
                  </div>
                </div>

                {notification.message && (
                    <div className={`p-3 mb-4 rounded-lg text-sm ${notification.type === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                        {notification.message}
                    </div>
                )}

                {viewMode === 'calendar' ? (
                  <CalendarView days={days} onTickerSelect={handleTickerSelectFromCalendar} />
                ) : viewMode === 'rejected' ? (
                  <CalendarRejectedView days={days} />
                ) : (
                <div className="grid grid-cols-12 gap-4">
                  <div className="col-span-3 bg-white rounded-lg shadow p-3 sticky top-4 self-start" style={{ maxHeight: 'calc(100vh - 2rem)' }}>
                    <div className="mb-3">
                      <input
                        type="text"
                        placeholder="Szukaj tickera..."
                        className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                      />
                    </div>

                      <div className="space-y-1.5 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 10rem)' }}>
                      {sortedTickers.map((ticker) => {
                        const togglePortfolio = async (e) => {
                          e.stopPropagation();
                          try {
                            const response = await fetch('/api/toggle_portfolio', {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({
                                ticker: ticker.ticker,
                                in_portfolio: !ticker.in_portfolio
                              })
                            });
                            if (response.ok) {
                              fetchTickers();
                            }
                          } catch (error) {
                            console.error('Error toggling portfolio:', error);
                          }
                        };
                        const toggleFavorite = async (e) => {
                          e.stopPropagation();
                          try {
                            const response = await fetch('/api/toggle_favorite', {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({
                                ticker: ticker.ticker,
                                is_favorite: !ticker.is_favorite
                              })
                            });
                            if (response.ok) {
                              fetchTickers();
                            }
                          } catch (error) {
                            console.error('Error toggling favorite:', error);
                          }
                        };

                        const handleScrape = async (e) => {
                            e.stopPropagation();
                            if (!confirm(`Do you want to scrape Strefa Inwestorow for ${ticker.ticker}?`)) return;
                            
                            setScrapingTicker(ticker.ticker);
                            setNotification({ message: '', type: '' });

                            try {
                                const response = await fetch('/api/scrape_ticker', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ ticker: ticker.ticker })
                                });
                                const data = await response.json();
                                
                                if (response.ok) {
                                    setNotification({ message: `Scraping for ${ticker.ticker} complete! New articles: ${data.new_articles}`, type: 'success' });
                                    fetchAnalyses(ticker.ticker);
                                } else {
                                    setNotification({ message: `Error scraping ${ticker.ticker}: ${data.error}`, type: 'error' });
                                }
                            } catch (error) {
                                setNotification({ message: `Network error while scraping ${ticker.ticker}.`, type: 'error' });
                            } finally {
                                setScrapingTicker(null);
                            }
                        };

                        return (
                          <div
                            key={ticker.ticker}
                            onClick={() => setSelectedTicker(ticker)}
                            className={`p-2 rounded-lg cursor-pointer transition-all relative ${
                              ticker.in_portfolio
                                ? (selectedTicker?.ticker === ticker.ticker
                                  ? 'bg-gradient-to-r from-green-100 to-emerald-100 border-2 border-blue-500'
                                  : 'bg-gradient-to-r from-green-50 to-emerald-50 hover:from-green-100 hover:to-emerald-100 border-2 border-green-200')
                                : ticker.is_favorite
                                ? (selectedTicker?.ticker === ticker.ticker
                                  ? 'bg-gradient-to-r from-blue-100 to-cyan-100 border-2 border-blue-500'
                                  : 'bg-gradient-to-r from-blue-50 to-cyan-50 hover:from-blue-100 hover:to-cyan-100 border-2 border-blue-200')
                                : (selectedTicker?.ticker === ticker.ticker
                                  ? 'bg-blue-50 border-2 border-blue-500'
                                  : 'bg-gray-50 hover:bg-gray-100 border-2 border-transparent')
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-1.5">
                                  <span className={`text-base ${ticker.in_portfolio ? 'font-extrabold text-green-900' : 'font-bold text-gray-900'}`}>
                                    {ticker.ticker}
                                  </span>
                                  {ticker.in_portfolio && (
                                    <span className="text-xs bg-green-600 text-white px-1.5 py-0.5 rounded-full font-semibold">
                                      Portfolio
                                    </span>
                                  )}
                                   {ticker.is_favorite && (
                                    <span className="text-xs bg-blue-600 text-white px-1.5 py-0.5 rounded-full font-semibold">
                                      Ulubione
                                    </span>
                                  )}
                                </div>
                                <p className="text-xs text-gray-600 truncate">{ticker.company_name || 'Brak nazwy'}</p>
                                <p className="text-xs text-gray-500">{ticker.sector || 'Brak sektora'}</p>
                              </div>
                              <div className="flex flex-col items-center gap-2 ml-2">
                                <button onClick={handleScrape} disabled={scrapingTicker === ticker.ticker} className={`text-white px-2 py-1 rounded text-xs ${scrapingTicker === ticker.ticker ? 'bg-gray-400' : 'bg-blue-500'}`}>
                                    {scrapingTicker === ticker.ticker ? 'Scraping...' : 'Scrape'}
                                </button>
                                <div className="text-right">
                                  <div className={`text-base font-bold ${getSentimentColor(ticker.avg_sentiment)}`}>
                                    {ticker.avg_sentiment > 0 ? '+' : ''}{Number(ticker.avg_sentiment).toFixed(2)}
                                  </div>
                                  <div className="text-xs text-gray-500">
                                    {ticker.mentions} wzm.
                                  </div>
                                </div>
                                 <div className="flex items-center gap-2">
                                <input
                                  type="checkbox"
                                  checked={ticker.is_favorite}
                                  onChange={toggleFavorite}
                                  className="w-4 h-4 cursor-pointer accent-blue-600"
                                  title="Dodaj/usuń z ulubionych"
                                />
                                <input
                                  type="checkbox"
                                  checked={ticker.in_portfolio}
                                  onChange={togglePortfolio}
                                  className="w-4 h-4 cursor-pointer accent-green-600"
                                  title="Dodaj/usuń z portfolio"
                                />
                                </div>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div className="col-span-9">
                    {!selectedTicker ? (
                      <div className="bg-white rounded-lg shadow p-6 flex items-center justify-center" style={{ minHeight: '300px' }}>
                        <div className="text-center text-gray-400">
                          <p className="text-lg">Wybierz ticker z listy po lewej</p>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-4">
                        <div className={`p-3 rounded-lg shadow ${getSentimentBg(selectedTicker.avg_sentiment)}`}>
                          <div className="flex items-center justify-between">
                            <div>
                              <h2 className="text-xl font-bold text-gray-900">
                                {selectedTicker.ticker} - {selectedTicker.company_name || 'Brak nazwy'}
                              </h2>
                              <p className="text-sm text-gray-600">{selectedTicker.sector || 'Brak sektora'}</p>
                            </div>
                            <div className="text-right">
                              <div className={`text-2xl font-bold ${getSentimentColor(selectedTicker.avg_sentiment)}`}>
                                {selectedTicker.avg_sentiment > 0 ? '+' : ''}{Number(selectedTicker.avg_sentiment).toFixed(2)}
                              </div>
                              <div className="text-xs text-gray-600">
                                Średni sentyment
                              </div>
                            </div>
                          </div>
                        </div>

                        {tickerStats && showStats && (
                          <div className="bg-white rounded-lg shadow p-4">
                            <div className="flex items-center justify-between mb-3">
                              <h3 className="text-base font-semibold text-gray-900">Statystyki</h3>
                              <button 
                                onClick={() => setShowStats(false)}
                                className="text-gray-400 hover:text-gray-600 text-sm"
                              >
                                ✕
                              </button>
                            </div>
                            <div className="grid grid-cols-3 gap-3">
                              <div className="bg-gray-50 p-3 rounded-lg">
                                <div className="text-xl font-bold text-gray-900">{tickerStats.totalNews}</div>
                                <div className="text-xs text-gray-600">Wszystkie</div>
                              </div>
                              <div className="bg-green-50 p-3 rounded-lg">
                                <div className="text-xl font-bold text-green-600">{tickerStats.positiveNews}</div>
                                <div className="text-xs text-gray-600">Pozytywne</div>
                              </div>
                              <div className="bg-red-50 p-3 rounded-lg">
                                <div className="text-xl font-bold text-red-600">{tickerStats.negativeNews}</div>
                                <div className="text-xs text-gray-600">Negatywne</div>
                              </div>
                              <div className="bg-gray-50 p-3 rounded-lg">
                                <div className="text-xl font-bold text-gray-600">{tickerStats.neutralNews}</div>
                                <div className="text-xs text-gray-600">Neutralne</div>
                              </div>
                              <div className="bg-blue-50 p-3 rounded-lg">
                                <div className={`text-xl font-bold ${getSentimentColor(tickerStats.avgImpact)}`}>
                                  {tickerStats.avgImpact > 0 ? '+' : ''}{tickerStats.avgImpact.toFixed(3)}
                                </div>
                                <div className="text-xs text-gray-600">Śr. impact</div>
                              </div>
                              <div className="bg-purple-50 p-3 rounded-lg">
                                <div className="text-xl font-bold text-purple-600">
                                  {(tickerStats.avgConfidence * 100).toFixed(0)}%
                                </div>
                                <div className="text-xs text-gray-600">Śr. pewność</div>
                              </div>
                            </div>
                          </div>
                        )}

                        {loadingChart ? (
                          <div className="bg-white rounded-lg shadow-lg p-6 flex items-center justify-center">
                            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                          </div>
                        ) : (
                          <PriceChart 
                            ticker={selectedTicker.ticker} 
                            priceHistory={priceHistory}
                            brokerageAnalyses={brokerageAnalyses}
                            analyses={filteredAnalyses}
                          />
                        )}

                        {/* Analiza Techniczna */}
                        <TechnicalAnalysis ticker={selectedTicker.ticker} />

                        {loading ? (
                          <div className="bg-white rounded-lg shadow-lg p-6 flex items-center justify-center py-12">
                            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                          </div>
                        ) : (
                          <div className="bg-white rounded-lg shadow p-4">
                            <div className="space-y-4">
                              <div>
                                <div className="flex items-center justify-between mb-2">
                                  <h3 className="text-base font-semibold text-gray-900">
                                    Analizy newsowe ({filteredAnalyses.length})
                                  </h3>
                                  <div className="flex items-center gap-2">
                                    <label className="text-xs text-gray-600">Filtruj:</label>
                                    <select 
                                      value={filterImpact} 
                                      onChange={(e) => setFilterImpact(e.target.value)}
                                      className="px-2 py-1 text-xs border border-gray-300 rounded-lg"
                                    >
                                      <option value="all">Wszystkie</option>
                                      <option value="positive">Pozytywne</option>
                                      <option value="negative">Negatywne</option>
                                      <option value="neutral">Neutralne</option>
                                    </select>
                                  </div>
                                </div>
                                {filteredAnalyses.length === 0 ? (
                                  <p className="text-gray-500 text-xs">Brak analiz newsowych</p>
                                ) : (
                                  <div className="space-y-2">
                                    {filteredAnalyses.map((analysis, idx) => (
                                      <div
                                        key={idx}
                                        className="border border-gray-200 rounded-lg p-3 hover:shadow-md transition-shadow relative"
                                      >
                                        <button
                                          onClick={() => markAsDuplicate(analysis.analysis_id, analysis.news_id)}
                                          className="absolute top-1.5 right-1.5 w-6 h-6 flex items-center justify-center bg-red-500 hover:bg-red-600 text-white rounded-full text-sm font-bold transition-colors"
                                          title="Oznacz jako duplikat"
                                        >
                                          ✕
                                        </button>

                                        <div className="flex items-start gap-3">
                                          <div className="flex-shrink-0">
                                            <div className={`w-2 h-16 ${getImpactColor(analysis.impact)} rounded`}></div>
                                          </div>

                                          <div className="flex-1 pr-8">
                                            <div className="flex items-start justify-between mb-1.5">
                                              <div className="flex-1">
                                                <h3 className="font-semibold text-sm text-gray-900 mb-0.5">
                                                  {analysis.title}
                                                </h3>
                                                <div className="flex items-center gap-2 text-xs text-gray-500">
                                                  <span>{analysis.date}</span>
                                                  <span>•</span>
                                                  <span>{analysis.source}</span>
                                                  {analysis.url && (
                                                    <>
                                                      <span>•</span>
                                                      <a 
                                                        href={analysis.url} 
                                                        target="_blank" 
                                                        rel="noopener noreferrer"
                                                        className="text-blue-600 hover:underline"
                                                      >
                                                        Link
                                                      </a>
                                                    </>
                                                  )}
                                                </div>
                                              </div>
                                            </div>

                                            <div className="flex items-center gap-3 mb-2">
                                              <div className="flex items-center gap-1.5">
                                                <span className="text-xs text-gray-600">Impact:</span>
                                                <span className={`font-bold text-sm ${getSentimentColor(analysis.impact)}`}>
                                                  {analysis.impact > 0 ? '+' : ''}{Number(analysis.impact).toFixed(2)}
                                                </span>
                                              </div>
                                              <div className="flex items-center gap-1.5">
                                                <span className="text-xs text-gray-600">Confidence:</span>
                                                <span className="font-bold text-sm text-blue-600">
                                                  {(Number(analysis.confidence) * 100).toFixed(0)}%
                                                </span>
                                              </div>
                                              {analysis.occasion && (
                                                <div className="flex items-center gap-1.5">
                                                  <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">
                                                    {analysis.occasion}
                                                  </span>
                                                </div>
                                              )}
                                            </div>

                                            {analysis.summary && (
                                              <div 
                                                className="text-xs text-gray-700 leading-relaxed"
                                                dangerouslySetInnerHTML={{ __html: analysis.summary }}
                                              />
                                            )}
                                          </div>
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>

                              {brokerageAnalyses.length > 0 && (
                                <div className="mt-4 pt-4 border-t border-gray-200">
                                  <h3 className="text-base font-semibold text-gray-900 mb-2">
                                    Rekomendacje domów maklerskich ({brokerageAnalyses.length})
                                  </h3>
                                  <div className="overflow-x-auto">
                                    <table className="min-w-full divide-y divide-gray-200">
                                      <thead className="bg-gray-50">
                                        <tr>
                                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                            Data
                                          </th>
                                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                            Dom maklerski
                                          </th>
                                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                            Rekomendacja
                                          </th>
                                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                            Cena obecna
                                          </th>
                                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                            Cena docelowa
                                          </th>
                                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                            Zmiana %
                                          </th>
                                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                            Upside %
                                          </th>
                                        </tr>
                                      </thead>
                                      <tbody className="bg-white divide-y divide-gray-200">
                                        {brokerageAnalyses.map((brokerage, idx) => (
                                          <tr key={idx} className={getUpsideBg(brokerage.upside_percent)}>
                                            <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-700">
                                              {brokerage.date}
                                            </td>
                                            <td className="px-3 py-2 text-xs text-gray-900 font-medium">
                                              {brokerage.brokerage_house}
                                            </td>
                                            <td className={`px-3 py-2 whitespace-nowrap text-xs ${getRecommendationColor(brokerage.recommendation)}`}>
                                              {brokerage.recommendation || '-'}
                                            </td>
                                            <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 font-semibold">
                                              {brokerage.current_price 
                                                ? `${brokerage.current_price.toFixed(2)}`
                                                : (brokerage.price_old ? brokerage.price_old.toFixed(2) : '-')}
                                            </td>
                                            <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 font-semibold">
                                              {brokerage.price_new ? brokerage.price_new.toFixed(2) : '-'}
                                            </td>
                                            <td className={`px-3 py-2 whitespace-nowrap text-xs ${getUpsideColor(brokerage.price_change_percent)}`}>
                                              {brokerage.price_change_percent !== null 
                                                ? `${brokerage.price_change_percent > 0 ? '+' : ''}${brokerage.price_change_percent.toFixed(1)}%`
                                                : '-'}
                                            </td>
                                            <td className={`px-3 py-2 whitespace-nowrap text-xs ${getUpsideColor(brokerage.upside_percent)}`}>
                                              {brokerage.upside_percent !== null 
                                                ? `${brokerage.upside_percent > 0 ? '+' : ''}${brokerage.upside_percent.toFixed(1)}%`
                                                : '-'}
                                            </td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
                )}
              </div>
            </div>
          );
        }

        // Renderowanie aplikacji
        const root = ReactDOM.createRoot(document.getElementById('root'));
        root.render(<TickerDashboard />);
    {% endraw %}
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
        tickers = []
        for row in result:
            tickers.append({
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

    return jsonify(tickers)


@app.route('/api/analyses/<ticker>')
def get_analyses(ticker):
    """Endpoint zwracający szczegółowe analizy dla tickera"""
    days = request.args.get('days', 30, type=int)

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
        result = conn.execute(query, {'ticker': ticker})
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


@app.route('/api/brokerage/<ticker>')
def get_brokerage_analyses(ticker):
    """Endpoint zwracający rekomendacje brokerskie dla tickera"""
    days = request.args.get('days', 90, type=int)

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
        result = conn.execute(query, {'ticker': ticker})
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
                'date': row[0].strftime('%Y-%m-%d') if row[0] else (row[6].strftime('%Y-%m-%d') if row[6] else None),
                'brokerage_house': brokerage_house,
                'price_old': price_old,
                'price_new': price_new,
                'current_price': current_price,
                'recommendation': row[4],
                'comment': row[5],
                'price_change_percent': price_change_percent,
                'upside_percent': upside_percent
            })

        brokerage_analyses.sort(key=lambda x: x['date'] if x['date'] else '1900-01-01', reverse=True)

    return jsonify(brokerage_analyses)


@app.route('/api/price_history/<ticker>')
def get_price_history_endpoint(ticker):
    """Endpoint zwracający historię cen tickera"""
    days = request.args.get('days', 90, type=int)
    price_data = get_price_history(ticker, days)
    return jsonify(price_data)


@app.route('/api/mark_duplicate', methods=['POST'])
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


@app.route('/api/all_tickers')
def get_all_tickers():
    """Endpoint zwracający listę wszystkich dostępnych tickerów"""
    query = text(f"""
    SELECT ticker, company_name FROM {schema}.tickers ORDER BY ticker
    """)
    with engine.connect() as conn:
        result = conn.execute(query)
        tickers = [{'value': row[0], 'label': f"{row[0]} - {row[1]}"} for row in result]
    return jsonify(tickers)


@app.route('/api/update_analysis_tickers', methods=['POST'])
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
                res = conn.execute(get_analysis_details_query, {'analysis_id': analysis_id}).fetchone()
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
                return jsonify({'success': True, 'message': 'Tickers updated successfully'})

            except Exception as e:
                trans.rollback()
                raise e

    except Exception as e:
        print(f"Error updating tickers: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/calendar_stats')
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


@app.route('/api/news_by_date/<date>')
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
            analysis_id_to_news = {data['analysis_id']: data for data in news_dict.values()}
            analysis_ids = list(analysis_id_to_news.keys())

            if analysis_ids:
                ticker_query = text(f"""
                    SELECT ts.analysis_id, ts.ticker, ts.impact
                    FROM {schema}.ticker_sentiment ts
                    WHERE ts.analysis_id = ANY(:analysis_ids)
                    AND ts.ticker IS NOT NULL
                    ORDER BY ts.impact DESC
                """)
                ticker_result = conn.execute(ticker_query, {'analysis_ids': analysis_ids})

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


@app.route('/api/rejected_calendar_stats')
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


@app.route('/api/rejected_news_by_date/<date>')
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


@app.route('/api/reanalyze_news', methods=['POST'])
def reanalyze_news():
    """Endpoint do ponownej analizy odrzuconego newsa przez AI"""
    try:
        data = request.get_json()
        news_id = data.get('news_id')

        if not news_id:
            return jsonify({'error': 'Missing news_id'}), 400

        # Import potrzebnych modułów
        from ai_analist import analyze_articles
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
        result = analyze_articles(db, mode='id', article_id=news_id, telegram=None, skip_relevance_check=True)

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


@app.route('/api/toggle_portfolio', methods=['POST'])
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

        return jsonify({'success': True, 'ticker': ticker_symbol, 'in_portfolio': in_portfolio})

    except Exception as e:
        print(f"Error toggling portfolio: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/toggle_favorite', methods=['POST'])
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

        return jsonify({'success': True, 'ticker': ticker_symbol, 'is_favorite': is_favorite})

    except Exception as e:
        print(f"Error toggling favorite: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/technical_analysis/<ticker>')
def get_technical_analysis_endpoint(ticker):
    """
    Endpoint zwracający analizę techniczną dla tickera

    Zwraca:
    - summary: podsumowanie z Wskaźnikami i Średnimi kroczącymi (z kolorami)
    - details: szczegółowe informacje o wszystkich wskaźnikach i średnich

    Format odpowiedzi:
    {
        'summary': {
            'indicators': {
                'label': 'Mocne kupuj',
                'color': '#065f46',
                'bg_color': '#d1fae5',
                'score': 2
            },
            'moving_averages': {
                'label': 'Neutralne',
                'color': '#4b5563',
                'bg_color': '#f3f4f6',
                'score': 0,
                'buy_count': 4,
                'sell_count': 4
            }
        },
        'details': {
            'indicators': [...],
            'moving_averages': [...],
            'current_price': 45.20
        }
    }
    """
    try:
        period = request.args.get('period', '1y', type=str)
        analysis_data = get_technical_analysis(ticker, period)

        return jsonify(analysis_data)

    except Exception as e:
        print(f"Error in technical analysis endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/scrape_ticker', methods=['POST'])
def scrape_ticker_endpoint():
    """Endpoint to trigger ticker scraping."""
    try:
        data = request.get_json()
        ticker = data.get('ticker')
        page_from = data.get('page_from', 0)
        page_to = data.get('page_to', 4)

        if not ticker:
            return jsonify({'error': 'Missing ticker'}), 400

        stats = run_ticker_scraper(ticker, page_from, page_to)

        if "error" in stats:
            return jsonify(stats), 500
        
        return jsonify(stats)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("🚀 Uruchamiam dashboard...")
    print("📊 Otwórz przeglądarkę: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)

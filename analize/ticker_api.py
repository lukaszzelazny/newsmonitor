"""
Flask API dla interaktywnego dashboardu tickerów z wykresem kursu
Uruchom: python ticker_api.py
Potem otwórz: http://localhost:5000

Wymagane biblioteki:
pip install flask sqlalchemy yfinance psycopg2-binary
"""

from flask import Flask, render_template_string, jsonify, request
from sqlalchemy import create_engine, text
import os
from datetime import datetime, timedelta
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
</head>
<body class="bg-gray-50">
    <div id="root"></div>
    
    <script type="text/babel">
    {% raw %}
        const { useState, useEffect, useRef } = React;

        // Komponent wykresu Canvas
        function PriceChart({ ticker, priceHistory, brokerageAnalyses }) {
          const canvasRef = useRef(null);

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

          }, [priceHistory, brokerageAnalyses]);

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
                className="w-full"
                style={{ maxWidth: '100%', height: 'auto' }}
              />

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
          const [sortBy, setSortBy] = useState('mentions');

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

          const filteredTickers = tickers.filter(t => 
            t.ticker.toLowerCase().includes(searchTerm.toLowerCase()) ||
            (t.company_name && t.company_name.toLowerCase().includes(searchTerm.toLowerCase()))
          );

          const sortedTickers = [...filteredTickers].sort((a, b) => {
            if (sortBy === 'impact') {
              return b.avg_sentiment - a.avg_sentiment;
            }
            return b.mentions - a.mentions;
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
                  <div className="flex items-center gap-4">
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
                    <div className="flex items-center gap-2">
                      <label className="text-sm text-gray-600">Sortuj:</label>
                      <select 
                        value={sortBy} 
                        onChange={(e) => setSortBy(e.target.value)}
                        className="px-3 py-2 border border-gray-300 rounded-lg"
                      >
                        <option value="mentions">Po wzmianach</option>
                        <option value="impact">Po sile impactu</option>
                      </select>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-12 gap-6">
                  <div className="col-span-3 bg-white rounded-lg shadow-lg p-4 sticky top-6 self-start" style={{ maxHeight: 'calc(100vh - 3rem)' }}>
                    <div className="mb-4">
                      <input
                        type="text"
                        placeholder="Szukaj tickera lub firmy..."
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                      />
                    </div>

                    <div className="space-y-2 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 12rem)' }}>
                      {sortedTickers.map((ticker) => (
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

                  <div className="col-span-9">
                    {!selectedTicker ? (
                      <div className="bg-white rounded-lg shadow-lg p-6 flex items-center justify-center" style={{ minHeight: '400px' }}>
                        <div className="text-center text-gray-400">
                          <p className="text-xl">Wybierz ticker z listy po lewej</p>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-6">
                        <div className={`p-4 rounded-lg mb-6 shadow-lg ${getSentimentBg(selectedTicker.avg_sentiment)}`}>
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

                        {loadingChart ? (
                          <div className="bg-white rounded-lg shadow-lg p-6 flex items-center justify-center">
                            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                          </div>
                        ) : (
                          <PriceChart 
                            ticker={selectedTicker.ticker} 
                            priceHistory={priceHistory}
                            brokerageAnalyses={brokerageAnalyses}
                          />
                        )}

                        {loading ? (
                          <div className="bg-white rounded-lg shadow-lg p-6 flex items-center justify-center py-12">
                            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                          </div>
                        ) : (
                          <div className="bg-white rounded-lg shadow-lg p-6">
                            <div className="space-y-6">
                              <div>
                                <h3 className="text-lg font-semibold text-gray-900 mb-3">
                                  Analizy newsowe ({analyses.length})
                                </h3>
                                {analyses.length === 0 ? (
                                  <p className="text-gray-500 text-sm">Brak analiz newsowych</p>
                                ) : (
                                  <div className="space-y-3">
                                    {analyses.map((analysis, idx) => (
                                      <div
                                        key={idx}
                                        className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
                                      >
                                        <div className="flex items-start gap-4">
                                          <div className="flex-shrink-0">
                                            <div className={`w-3 h-24 ${getImpactColor(analysis.impact)} rounded`}></div>
                                          </div>

                                          <div className="flex-1">
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

                                            {analysis.summary && (
                                              <div 
                                                className="text-sm text-gray-700 leading-relaxed"
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
                                <div className="mt-6 pt-6 border-t border-gray-200">
                                  <h3 className="text-lg font-semibold text-gray-900 mb-3">
                                    Rekomendacje domów maklerskich ({brokerageAnalyses.length})
                                  </h3>
                                  <div className="overflow-x-auto">
                                    <table className="min-w-full divide-y divide-gray-200">
                                      <thead className="bg-gray-50">
                                        <tr>
                                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Data
                                          </th>
                                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Dom maklerski
                                          </th>
                                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Rekomendacja
                                          </th>
                                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Cena obecna
                                          </th>
                                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Cena docelowa
                                          </th>
                                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Zmiana celu %
                                          </th>
                                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Upside %
                                          </th>
                                        </tr>
                                      </thead>
                                      <tbody className="bg-white divide-y divide-gray-200">
                                        {brokerageAnalyses.map((brokerage, idx) => (
                                          <tr key={idx} className={getUpsideBg(brokerage.upside_percent)}>
                                            <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-700">
                                              {brokerage.date}
                                            </td>
                                            <td className="px-4 py-3 text-sm text-gray-900 font-medium">
                                              {brokerage.brokerage_house}
                                            </td>
                                            <td className={`px-4 py-3 whitespace-nowrap text-sm ${getRecommendationColor(brokerage.recommendation)}`}>
                                              {brokerage.recommendation || '-'}
                                            </td>
                                            <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 font-semibold">
                                              {brokerage.current_price 
                                                ? `${brokerage.current_price.toFixed(2)}`
                                                : (brokerage.price_old ? brokerage.price_old.toFixed(2) : '-')}
                                            </td>
                                            <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 font-semibold">
                                              {brokerage.price_new ? brokerage.price_new.toFixed(2) : '-'}
                                            </td>
                                            <td className={`px-4 py-3 whitespace-nowrap text-sm ${getUpsideColor(brokerage.price_change_percent)}`}>
                                              {brokerage.price_change_percent !== null 
                                                ? `${brokerage.price_change_percent > 0 ? '+' : ''}${brokerage.price_change_percent.toFixed(1)}%`
                                                : '-'}
                                            </td>
                                            <td className={`px-4 py-3 whitespace-nowrap text-sm ${getUpsideColor(brokerage.upside_percent)}`}>
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


@app.route('/api/analyses/<ticker>')
def get_analyses(ticker):
    """Endpoint zwracający szczegółowe analizy dla tickera"""
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


if __name__ == '__main__':
    print("🚀 Uruchamiam dashboard...")
    print("📊 Otwórz przeglądarkę: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, jsonify, request
from flask_cors import CORS
from tools.actions import run_ticker_scraper
from analize.utils import get_price_history, get_technical_analysis
from analize.views.tickers import tickers_bp
from analize.views.calendar import calendar_bp
from analize.views.rejected import rejected_bp
from analize.views.portfolio import portfolio_bp


app = Flask(__name__)
CORS(app)

# Rejestracja blueprintów
app.register_blueprint(tickers_bp)
app.register_blueprint(calendar_bp)
app.register_blueprint(rejected_bp)
app.register_blueprint(portfolio_bp)

@app.route('/api/price_history/<ticker>')
def get_price_history_endpoint(ticker):
    """Endpoint zwracający historię cen tickera"""
    days = request.args.get('days', 90, type=int)
    price_data = get_price_history(ticker, days)
    return jsonify(price_data)

@app.route('/api/technical_analysis/<ticker>')
def get_technical_analysis_endpoint(ticker):
    """
    Endpoint zwracający analizę techniczną dla tickera
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
    print("Uruchamiam dashboard...")
    print("Otwórz przeglądarkę: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)

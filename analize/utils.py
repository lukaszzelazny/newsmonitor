import os
import json
import yfinance as yf
from sqlalchemy import create_engine
from functools import lru_cache
from tools.ticker_analizer import getScoreWithDetails
from tools.moving_analizer import calculate_moving_averages_signals
from tools.price_fetcher import (
    get_current_price as pf_get_current_price,
    get_price_history as pf_get_price_history,
    get_yf_symbol as map_yf_symbol,
    get_ohlc_history_df,
)

# Konfiguracja bazy danych
def get_db_engine():
    db_url = "postgresql:///?service=stock"
    engine = create_engine(db_url)
    schema = os.getenv('DB_SCHEMA', 'stock')
    return engine, schema


# Cache dla cen z Yahoo Finance
@lru_cache(maxsize=1000)
def get_current_price(ticker_symbol):
    """Pobiera aktualną cenę tickera z Yahoo Finance (z fallbackami i konwersją do PLN)."""
    try:
        return pf_get_current_price(ticker_symbol)
    except Exception as e:
        print(f"Błąd pobierania ceny dla {ticker_symbol}: {e}")
        return None


def get_price_history(ticker_symbol, days=90):
    """Pobiera historię cen tickera (solidny fallback, konwersja do PLN)."""
    try:
        return pf_get_price_history(ticker_symbol, days)
    except Exception as e:
        print(f"Błąd pobierania historii dla {ticker_symbol}: {e}")
        return []


def parse_price(price_str):
    """Parsuje cenę z różnych formatów string i usuwa waluty"""
    if not price_str:
        return None

    try:
        price_clean = str(price_str).strip()
        price_clean = price_clean.replace('PLN', '').replace('zł', '').replace('USD',
                                                                               '').replace(
            'EUR', '')
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
        # Map period to days
        days = 365
        if period == "1mo": days = 30
        elif period == "3mo": days = 90
        elif period == "6mo": days = 180
        elif period == "1y": days = 365
        elif period == "2y": days = 730
        elif period == "5y": days = 1825
        elif period == "max": days = 3650
        elif period.endswith('d'):
            try:
                days = int(period[:-1])
            except ValueError:
                pass

        # Pobierz dane (z bazy lub YF przez price_fetcher)
        df = get_ohlc_history_df(ticker_symbol, days=days)

        if df is None or df.empty:
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
                parts.append(
                    f"Rekomendacja: <strong>{data['price_recomendation']}</strong>")

            if data.get('price_old') and data.get('price_new'):
                parts.append(
                    f"Zmiana ceny docelowej: {data['price_old']} → {data['price_new']}")
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


def resolve_db_ticker(engine, schema, ticker_symbol):
    """
    Resolves ticker symbol to the one present in DB (e.g. PZU -> PZU.PL).
    """
    from sqlalchemy import text
    with engine.connect() as conn:
        # 1. Exact
        res = conn.execute(text(f"SELECT ticker FROM {schema}.tickers WHERE ticker = :t"), {'t': ticker_symbol}).fetchone()
        if res: return res[0]
        
        # 2. Suffixes
        if '.' not in ticker_symbol:
            for suffix in ['.PL', '.WA', '.US']:
                candidate = f"{ticker_symbol}{suffix}"
                res = conn.execute(text(f"SELECT ticker FROM {schema}.tickers WHERE ticker = :t"), {'t': candidate}).fetchone()
                if res: return res[0]
                
        # 3. .WA -> .PL
        if ticker_symbol.endswith('.WA'):
             candidate = ticker_symbol.replace('.WA', '.PL')
             res = conn.execute(text(f"SELECT ticker FROM {schema}.tickers WHERE ticker = :t"), {'t': candidate}).fetchone()
             if res: return res[0]
             
    return ticker_symbol # Fallback to original

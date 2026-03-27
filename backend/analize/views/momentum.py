from flask import Blueprint, jsonify
from sqlalchemy import text
from backend.analize.utils import get_db_engine

momentum_bp = Blueprint('momentum', __name__)
engine, _ = get_db_engine()

MODEL_VERSION = 'momentum_v1'
LGBM_SCHEMA = 'lgbm'


def _score_label(score: float) -> str:
    if score >= 8.0:
        return 'Silny pozytywny momentum'
    elif score >= 6.0:
        return 'Umiarkowanie pozytywny'
    elif score >= 4.0:
        return 'Neutralny'
    elif score >= 2.0:
        return 'Negatywny momentum'
    else:
        return 'Silnie negatywny'


def _get_momentum_signals(row: dict) -> tuple[list[str], list[str]]:
    """
    Oblicza listę pozytywnych i negatywnych sygnałów momentum
    na podstawie progów opisanych w readme_momentum_v1.md (sekcja 6).
    """
    positive = []
    negative = []

    # --- Returny ---
    ret1w = row.get('return_1w')
    if ret1w is not None:
        if ret1w < -0.03:
            negative.append(f"Spadek {ret1w:+.1%} w ostatnim tygodniu")

    ret1m = row.get('return_1m')
    if ret1m is not None:
        if ret1m > 0.05:
            positive.append(f"Wzrost {ret1m:+.1%} w ostatnim miesiącu")
        elif ret1m < -0.10:
            negative.append(f"Spadek {ret1m:+.1%} w ostatnim miesiącu")

    ret3m = row.get('return_3m')
    if ret3m is not None:
        if ret3m > 0.15:
            positive.append(f"Silny trend kwartalny ({ret3m:+.1%})")
        elif ret3m < -0.15:
            negative.append(f"Trend spadkowy w kwartale ({ret3m:+.1%})")

    # --- RSI ---
    rsi = row.get('rsi_14')
    if rsi is not None:
        if 40 <= rsi <= 65:
            positive.append(f"RSI w zdrowej strefie ({rsi:.0f})")
        elif rsi > 80:
            negative.append(f"Ekstremalnie wykupiona (RSI = {rsi:.0f}) — ryzyko korekty")
        elif rsi < 25:
            negative.append(f"Ekstremalnie wyprzedana (RSI = {rsi:.0f})")

    # --- SMA 50 ---
    vs_sma50 = row.get('price_vs_sma50')
    if vs_sma50 is not None:
        if vs_sma50 > 1.02:
            positive.append(f"Cena powyżej SMA 50 ({(vs_sma50 - 1) * 100:+.0f}%) — trend krótkoterm.")
        elif vs_sma50 < 0.95:
            negative.append(f"Cena poniżej SMA 50 ({(vs_sma50 - 1) * 100:+.0f}%) — krótkoterm. downtrend")

    # --- SMA 200 ---
    vs_sma200 = row.get('price_vs_sma200')
    if vs_sma200 is not None:
        if vs_sma200 > 1.05:
            positive.append(f"Cena powyżej SMA 200 ({(vs_sma200 - 1) * 100:+.0f}%) — długoterm. uptrend")
        elif vs_sma200 < 0.90:
            negative.append(f"Cena poniżej SMA 200 ({(vs_sma200 - 1) * 100:+.0f}%) — długoterm. downtrend")

    # --- Golden / Death cross ---
    sma_cross = row.get('sma50_vs_sma200')
    if sma_cross is not None:
        if sma_cross > 1.02:
            positive.append("Golden cross — SMA 50 powyżej SMA 200")
        elif sma_cross < 0.98:
            negative.append("Death cross — SMA 50 poniżej SMA 200")

    # --- Wolumen ---
    vol_ratio = row.get('volume_ratio_20d')
    if vol_ratio is not None:
        if 1.5 < vol_ratio <= 3.0:
            positive.append(f"Rosnący wolumen ({vol_ratio:.1f}x średniej) — zainteresowanie rynku")
        elif vol_ratio > 3.0:
            negative.append(f"Ekstremalny wolumen ({vol_ratio:.1f}x) — panika lub spekulacja")
        elif vol_ratio < 0.7:
            negative.append(f"Malejący wolumen ({vol_ratio:.1f}x średniej)")

    # --- Volume trend ---
    vol_trend = row.get('volume_trend')
    if vol_trend is not None:
        if vol_trend > 1.1:
            positive.append(f"Trend wolumenu rosnący ({vol_trend:.2f}x)")

    # --- Momentum quality ---
    mq = row.get('momentum_quality')
    if mq is not None:
        if mq == 1:
            positive.append("Potwierdzony trend — cena i wolumen rosną razem")
        elif mq == -1:
            negative.append("Dystrybucja — cena spada przy rosnącym wolumenie")

    # --- Pozycja 52-tygodniowa ---
    pos52w = row.get('price_position_52w')
    if pos52w is not None:
        if 60 <= pos52w <= 90:
            positive.append(f"Blisko rocznych szczytów ({pos52w:.0f}/100) — silna pozycja")
        elif pos52w < 20:
            negative.append(f"Blisko rocznych minimów ({pos52w:.0f}/100)")

    # --- Zmienność (vol_ratio) ---
    vol_ratio_feat = row.get('vol_ratio')
    if vol_ratio_feat is not None:
        if vol_ratio_feat < 0.8:
            positive.append(f"Zmienność maleje ({vol_ratio_feat:.2f}) — stabilizacja trendu")
        elif vol_ratio_feat > 1.5:
            negative.append(f"Zmienność rośnie ({vol_ratio_feat:.2f}) — niestabilność")

    # --- OBV slope ---
    obv = row.get('obv_slope_20d')
    if obv is not None:
        if obv > 0.3:
            positive.append("Rosnący OBV — akumulacja (mądrzy kupują)")
        elif obv < -0.3:
            negative.append("Spadający OBV — dystrybucja (mądrzy sprzedają)")

    return positive, negative


@momentum_bp.route('/api/tickers/<ticker>/momentum', methods=['GET'])
def get_momentum_score(ticker: str):
    """
    Zwraca scoring momentum modelu LightGBM dla podanego tickera.

    Response JSON:
    {
      "ticker": "CDR",
      "snapshot_date": "2025-12-19",
      "run_date": "2025-12-19",
      "score": 7.2,
      "rank": 35,
      "total_in_ranking": 215,
      "score_label": "Umiarkowanie pozytywny",
      "score_change": 0.8,
      "previous_score": 6.4,
      "previous_run_date": "2025-12-12",
      "positive_signals": [...],
      "negative_signals": [...],
      "indicators": { ... }
    }
    """
    try:
        query = text(f"""
            SELECT
                ticker,
                score,
                rank,
                data_date,
                snapshot_date,
                run_date,
                return_1w,
                return_1m,
                return_3m,
                rsi_14,
                price_vs_sma50,
                price_vs_sma200,
                volume_ratio_20d,
                volatility_20d
            FROM {LGBM_SCHEMA}.scoring_results_momentum
            WHERE ticker = :ticker
              AND model_version = :model_version
            ORDER BY run_date DESC
            LIMIT 2
        """)

        with engine.connect() as conn:
            result = conn.execute(query, {
                'ticker': ticker.upper(),
                'model_version': MODEL_VERSION,
            })
            rows = result.fetchall()
            keys = result.keys()

        if not rows:
            return jsonify(None)

        def row_to_dict(row):
            return dict(zip(keys, row))

        current = row_to_dict(rows[0])
        previous = row_to_dict(rows[1]) if len(rows) > 1 else None

        # Compute total tickers in latest run (for rank context)
        count_query = text(f"""
            SELECT COUNT(*)
            FROM {LGBM_SCHEMA}.scoring_results_momentum
            WHERE run_date = :run_date
              AND model_version = :model_version
        """)
        with engine.connect() as conn:
            total = conn.execute(count_query, {
                'run_date': current['run_date'],
                'model_version': MODEL_VERSION,
            }).scalar()

        positive_signals, negative_signals = _get_momentum_signals(current)

        current_score = float(current['score']) if current['score'] is not None else None
        previous_score = float(previous['score']) if previous and previous['score'] is not None else None
        score_change = round(current_score - previous_score, 2) if (current_score is not None and previous_score is not None) else None

        def fmt_date(d):
            return d.strftime('%Y-%m-%d') if d else None

        def maybe_float(v, ndigits: int = 4):
            if v is None:
                return None
            return round(float(v), ndigits)

        response = {
            'ticker': current['ticker'],
            'snapshot_date': fmt_date(current['snapshot_date']),
            'run_date': fmt_date(current['run_date']),
            'data_date': fmt_date(current['data_date']),
            'score': maybe_float(current_score, 2),
            'rank': int(current['rank']) if current['rank'] is not None else None,
            'total_in_ranking': int(total) if total else None,
            'score_label': _score_label(current_score) if current_score is not None else None,
            'score_change': score_change,
            'previous_score': maybe_float(previous_score, 2),
            'previous_run_date': fmt_date(previous['run_date']) if previous else None,
            'positive_signals': positive_signals,
            'negative_signals': negative_signals,
            'indicators': {
                'return_1w': maybe_float(current.get('return_1w')),
                'return_1m': maybe_float(current.get('return_1m')),
                'return_3m': maybe_float(current.get('return_3m')),
                'return_6m': maybe_float(current.get('return_6m')),
                'return_1y': maybe_float(current.get('return_1y')),
                'rsi_14': maybe_float(current.get('rsi_14'), 1),
                'price_vs_sma50': maybe_float(current.get('price_vs_sma50')),
                'price_vs_sma200': maybe_float(current.get('price_vs_sma200')),
                'sma50_vs_sma200': maybe_float(current.get('sma50_vs_sma200')),
                'volume_ratio_20d': maybe_float(current.get('volume_ratio_20d')),
                'volume_trend': maybe_float(current.get('volume_trend')),
                'momentum_quality': int(current['momentum_quality']) if current.get('momentum_quality') is not None else None,
                'price_position_52w': maybe_float(current.get('price_position_52w'), 1),
                'volatility_20d': maybe_float(current.get('volatility_20d')),
                'volatility_60d': maybe_float(current.get('volatility_60d')),
                'vol_ratio': maybe_float(current.get('vol_ratio')),
                'obv_slope_20d': maybe_float(current.get('obv_slope_20d')),
            }
        }

        return jsonify(response)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

import re
from flask import Blueprint, jsonify, request
from sqlalchemy import text
from backend.analize.utils import get_db_engine

assessment_bp = Blueprint('assessment', __name__)
engine, schema = get_db_engine()

LGBM_SCHEMA    = 'lgbm'
FUND_MODEL     = 'fundamental_v1'
MOM_MODEL      = 'momentum_v1'

W_FUNDAMENTAL  = 0.40
W_MOMENTUM     = 0.40
W_SENTIMENT    = 0.20


def _fundamental_label(score: float) -> str:
    if score >= 8.0: return 'Silne fundamenty'
    if score >= 6.0: return 'Dobre fundamenty'
    if score >= 4.0: return 'Przeciętne'
    if score >= 2.0: return 'Słabe fundamenty'
    return 'Bardzo słabe'


def _score_tag(master: float) -> str:
    if master >= 8.0: return 'LIDER SEKTORA'
    if master >= 7.0: return 'SOLIDNA SPÓŁKA'
    if master >= 5.5: return 'OBSERWUJ'
    if master >= 4.0: return 'NEUTRALNA'
    if master >= 2.5: return 'WYSOKE RYZYKO'
    return 'SPEKULACYJNA'


def _sentiment_to_score(avg_impact: float | None) -> float | None:
    if avg_impact is None:
        return None
    return round(1.0 + (max(-1.0, min(1.0, avg_impact)) + 1.0) / 2.0 * 9.0, 2)


# ─── Pros / cons (reguły z readme_model_v1.md sekcja 7) ──────────────────────

def _get_pros_cons(row: dict) -> tuple[list[dict], list[dict]]:
    pros: list[dict] = []
    cons: list[dict] = []

    def add_pro(bold: str, detail: str):
        pros.append({"bold": bold, "text": f"{bold} — {detail}"})

    def add_con(bold: str, detail: str):
        cons.append({"bold": bold, "text": f"{bold} — {detail}"})

    def fv(key):
        v = row.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    pe = fv('pe_ratio')
    if pe is not None:
        if 0 < pe < 12:
            add_pro(f"Niska wycena (P/E = {pe:.0f}×)",
                    "Kurs niski względem zysków — potencjał wzrostu wyceny.")
        elif pe > 30 or pe < 0:
            add_con(f"Wycena ({pe:.0f}×)",
                    f"P/E = {pe:.0f} — droga wycena lub spółka generuje stratę.")

    pb = fv('price_to_book')
    if pb is not None:
        if 0 < pb < 1.5:
            add_pro(f"Cena poniżej wartości księgowej (P/B = {pb:.1f}×)",
                    "Kurs poniżej lub blisko wartości aktywów netto.")
        elif pb > 5:
            add_con(f"Wysoka premia do majątku (P/B = {pb:.1f}×)",
                    "Rynek wycenia spółkę znacznie powyżej wartości księgowej.")

    ev = fv('ev_ebitda')
    if ev is not None:
        if 0 < ev < 8:
            add_pro(f"Niska wycena operacyjna (EV/EBITDA = {ev:.1f}×)",
                    "Spółka tania względem zysku operacyjnego.")
        elif ev > 15:
            add_con(f"Wysoka wycena (EV/EBITDA = {ev:.1f}×)",
                    "Ograniczona marża bezpieczeństwa — rynek wysoko wycenia zysk operacyjny.")

    fcf = fv('fcf_yield')
    if fcf is not None and fcf > 0.08:
        add_pro(f"Wysoki FCF yield ({fcf:.0%})",
                "Duże wolne przepływy pieniężne — spółka generuje realne pieniądze.")

    roe = fv('roe')
    if roe is not None:
        if roe > 15:
            add_pro(f"Wysoka rentowność (ROE = {roe:.0f}%)",
                    "Spółka efektywnie generuje zysk z kapitału własnego.")
        elif roe < 5:
            add_con(f"Niska rentowność (ROE = {roe:.0f}%)",
                    "Mały zwrot z kapitału własnego — nieefektywne wykorzystanie majątku.")

    ebitda_margin = fv('ebitda_margin')
    if ebitda_margin is not None:
        if ebitda_margin > 20:
            add_pro(f"Wysoka marża EBITDA ({ebitda_margin:.0f}%)",
                    "Silna zdolność do generowania zysku operacyjnego.")
        elif ebitda_margin < 5:
            add_con(f"Niska marża EBITDA ({ebitda_margin:.0f}%)",
                    "Niska efektywność operacyjna — wrażliwość na wzrost kosztów.")

    roa = fv('roa')
    if roa is not None and roa > 8:
        add_pro(f"Efektywne aktywa (ROA = {roa:.0f}%)",
                "Spółka generuje ponadprzeciętny zysk z aktywów.")

    rev_yoy = fv('revenue_yoy')
    if rev_yoy is not None:
        if rev_yoy > 0.15:
            add_pro(f"Dynamiczny wzrost przychodów (+{rev_yoy:.0%} r/r)",
                    "Silna ekspansja przychodów potwierdza popyt na produkty spółki.")
        elif rev_yoy < -0.10:
            add_con(f"Spadek przychodów ({rev_yoy:.0%} r/r)",
                    "Przychody wyraźnie niższe rok do roku — ryzyko strukturalne.")

    net_profit_growth = fv('net_profit_growth_1y')
    if net_profit_growth is not None:
        if net_profit_growth > 0.20:
            add_pro(f"Silny wzrost zysku (+{net_profit_growth:.0%} r/r)",
                    "Zysk netto rośnie szybciej niż przychody — rosnąca efektywność.")
        elif net_profit_growth < -0.20:
            add_con(f"Spadek zysku netto ({net_profit_growth:.0%} r/r)",
                    "Wyraźne pogorszenie wyników finansowych rok do roku.")

    cf_ratio = fv('cf_oper_to_profit')
    if cf_ratio is not None:
        if cf_ratio > 0.8:
            add_pro(f"Zyski pokryte gotówką (CF/Zysk = {cf_ratio:.1f}×)",
                    "Cash flow operacyjny potwierdza jakość raportowanych zysków.")
        elif cf_ratio < 0:
            add_con("Ujemny cash flow operacyjny",
                    "Zyski księgowe nie są poparte realnymi przepływami gotówki — red flag.")

    debt = fv('net_fin_debt_to_ebitda')
    if debt is not None:
        if debt < 2.0:
            add_pro(f"Niskie zadłużenie (Dług/EBITDA = {debt:.1f}×)",
                    "Bezpieczna struktura kapitałowa — duży bufor bezpieczeństwa.")
        elif debt > 4.0:
            add_con(f"Wysokie zadłużenie (Dług/EBITDA = {debt:.1f}×)",
                    "Dźwignia finansowa na ryzykownym poziomie.")

    current = fv('current_ratio')
    if current is not None:
        if 1.5 <= current <= 3.0:
            add_pro(f"Zdrowa płynność bieżąca ({current:.1f}×)",
                    "Spółka comfortably pokrywa zobowiązania krótkoterminowe.")
        elif current < 1.0:
            add_con(f"Ryzyko płynności (CR = {current:.1f}×)",
                    "Aktywa obrotowe nie pokrywają bieżących zobowiązań.")

    turnaround = fv('profit_turnaround') if 'profit_turnaround' in row else None
    if turnaround == 1:
        add_pro("Powrót do zyskowności (turnaround)",
                "Spółka przeszła ze straty w zysk — potencjał dla rynku.")
    elif turnaround == -1:
        add_con("Przejście w stratę",
                "Spółka przeszła z zysku w stratę — pogorszenie fundamentalne.")

    rel_str = fv('rel_strength_6m')
    if rel_str is not None:
        if rel_str > 0.20:
            add_pro(f"Silny momentum cenowy (+{rel_str:.0%} / 6M)",
                    "Kurs wyraźnie rośnie w ostatnim półroczu — potwierdzenie trendu.")
        elif rel_str < -0.20:
            add_con(f"Słaby momentum cenowy ({rel_str:.0%} / 6M)",
                    "Kurs traci na tle rynku w ostatnich 6 miesiącach.")

    return pros, cons


# ─── Formatowanie sekcji Kluczowe fundamenty ─────────────────────────────────

def _badge(good_cond: bool, bad_cond: bool) -> tuple[str, str]:
    """Zwraca (badge_type, badge_label)."""
    if good_cond: return 'good', 'Mocne'
    if bad_cond:  return 'bad',  'Słabe'
    return 'warn', 'Neutralnie'


def _fmt_pct(v: float | None) -> str | None:
    if v is None: return None
    return f"{v * 100:.1f}%"


def _build_fundamentals(row: dict) -> list[dict]:
    def fv(key):
        v = row.get(key)
        if v is None: return None
        try: return float(v)
        except: return None

    items = []

    pe = fv('pe_ratio')
    if pe is not None:
        badge, label = _badge(0 < pe < 12, pe > 30 or pe < 0)
        items.append({
            'label': 'P/E',
            'value': f"{pe:.1f}×" if pe > 0 else 'strata',
            'sub': 'Cena / Zysk TTM',
            'badge': badge,
            'badgeLabel': label,
        })

    pb = fv('price_to_book')
    if pb is not None:
        badge, label = _badge(0 < pb < 1.5, pb > 5)
        items.append({
            'label': 'P/BV',
            'value': f"{pb:.2f}×",
            'sub': 'Cena / Wartość Księgowa',
            'badge': badge,
            'badgeLabel': label,
        })

    roe = fv('roe')
    if roe is not None:
        badge, label = _badge(roe > 15, roe < 5)
        items.append({
            'label': 'ROE',
            'value': f"{roe:.1f}%",
            'sub': 'Zwrot z kapitału własnego',
            'badge': badge,
            'badgeLabel': label,
        })

    ebitda_margin = fv('ebitda_margin')
    if ebitda_margin is not None:
        badge, label = _badge(ebitda_margin > 20, ebitda_margin < 5)
        items.append({
            'label': 'Marża EBITDA',
            'value': f"{ebitda_margin:.1f}%",
            'sub': 'Zysk operacyjny / Przychody',
            'badge': badge,
            'badgeLabel': label,
        })

    debt = fv('net_fin_debt_to_ebitda')
    if debt is not None:
        badge, label = _badge(debt < 2.0, debt > 4.0)
        items.append({
            'label': 'Dług/EBITDA',
            'value': f"{debt:.1f}×",
            'sub': 'Zadłużenie netto finansowe',
            'badge': badge,
            'badgeLabel': label,
        })

    ev = fv('ev_ebitda')
    if ev is not None:
        badge, label = _badge(0 < ev < 8, ev > 15)
        items.append({
            'label': 'EV/EBITDA',
            'value': f"{ev:.1f}×",
            'sub': 'Wycena operacyjna',
            'badge': badge,
            'badgeLabel': label,
        })

    fcf = fv('fcf_yield')
    if fcf is not None:
        badge, label = _badge(fcf > 0.08, fcf < 0)
        items.append({
            'label': 'FCF Yield',
            'value': f"{fcf * 100:.1f}%",
            'sub': 'Wolny przepływ / Kapitalizacja',
            'badge': badge,
            'badgeLabel': label,
        })

    rev_yoy = fv('revenue_yoy')
    if rev_yoy is not None:
        badge, label = _badge(rev_yoy > 0.15, rev_yoy < -0.10)
        items.append({
            'label': 'Wzrost przychodów',
            'value': f"{rev_yoy * 100:+.1f}%",
            'sub': 'Rok do roku (TTM)',
            'badge': badge,
            'badgeLabel': label,
        })

    return items


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@assessment_bp.route('/api/tickers/<ticker>/assessment', methods=['GET'])
def get_assessment(ticker: str):
    """
    Pełna ocena spółki łącząca model fundamentalny, momentum i sentyment newsowy.

    Wydajność:
    - Jedno połączenie DB dla wszystkich zapytań
    - JOIN z vw_feature_snapshot (nie enriched) — push-down na company_id
    - Wycena/wzrost z progów (nie z ciężkiego vw_snowflake z window functions)
    """
    ticker_upper = ticker.upper()

    # ── Q1: fundamental score + dodatkowe wskaźniki do pros/cons i fundamentals
    # Łączymy scoring_results z vw_feature_snapshot przez company_id i data_date.
    # vw_feature_snapshot to GROUP BY pivot na lgbm.indicators — z filtrem
    # po company_id jest szybki (index push-down do lgbm.indicators).
    # NIE używamy vw_feature_snapshot_enriched — ten widok liczy window functions
    # (PARTITION BY company_id, percentile_cont sektorów) dla WSZYSTKICH spółek.
    q_fund = text(f"""
        SELECT
            sr.score                    AS fundamental_score,
            sr.rank                     AS fundamental_rank,
            sr.run_date,
            sr.data_date,
            sr.pe_ratio,
            sr.roe,
            sr.price_to_book,
            sr.ev_ebitda,
            sr.fcf_yield,
            sr.revenue_yoy,
            sr.revenue_growth_1y,
            sr.company_id,
            (SELECT COUNT(*) FROM lgbm.scoring_results
             WHERE run_date = sr.run_date AND model_version = sr.model_version) AS total_in_ranking,
            -- dodatkowe kolumny z vw_feature_snapshot dla pros/cons i fundamentals
            f.ebitda_margin,
            f.roa,
            f.net_profit_growth_1y,
            f.cf_oper_to_profit,
            f.net_fin_debt_to_ebitda,
            f.current_ratio,
            f.rel_strength_6m
        FROM {LGBM_SCHEMA}.scoring_results sr
        -- subquery zamiast JOIN z całym widokiem — filtruje po company_id
        LEFT JOIN (
            SELECT
                company_id,
                period_date,
                ebitda_margin,
                roa,
                net_profit_growth_1y,
                cf_oper_to_profit,
                net_fin_debt_to_ebitda,
                current_ratio,
                rel_strength_6m
            FROM {LGBM_SCHEMA}.vw_feature_snapshot
            WHERE company_id = (
                SELECT id FROM {LGBM_SCHEMA}.companies
                WHERE short_name = :ticker LIMIT 1
            )
        ) f ON f.company_id = sr.company_id AND f.period_date = sr.data_date
        WHERE sr.ticker = :ticker
          AND sr.model_version = :fund_model
          AND sr.run_date = (
              SELECT MAX(run_date) FROM {LGBM_SCHEMA}.scoring_results
              WHERE ticker = :ticker AND model_version = :fund_model
          )
        LIMIT 1
    """)

    # ── Q1b: previous fundamental score (for score_change)
    q_fund_prev = text(f"""
        SELECT score
        FROM {LGBM_SCHEMA}.scoring_results
        WHERE ticker = :ticker
          AND model_version = :fund_model
          AND run_date < (
              SELECT MAX(run_date) FROM {LGBM_SCHEMA}.scoring_results
              WHERE ticker = :ticker AND model_version = :fund_model
          )
        ORDER BY run_date DESC
        LIMIT 1
    """)

    # ── Q2: momentum score (w tym samym połączeniu)
    q_mom = text(f"""
        SELECT score
        FROM {LGBM_SCHEMA}.scoring_results_momentum
        WHERE ticker = :ticker
          AND model_version = :mom_model
        ORDER BY run_date DESC
        LIMIT 1
    """)

    # ── Q3: sentiment (w tym samym połączeniu)
    q_sent = text(f"""
        SELECT AVG(ts.impact::numeric)
        FROM {schema}.ticker_sentiment ts
        JOIN {schema}.analysis_result ar ON ts.analysis_id = ar.id
        JOIN {schema}.news_articles na    ON ar.news_id    = na.id
        WHERE ts.ticker = :ticker
          AND na.date >= CURRENT_DATE - INTERVAL '90 days'
    """)

    # ── Q4: snowflake z cache (zmaterializowany widok percentylowy)
    q_snow = text(f"""
        SELECT quality_score, value_score, growth_score, health_score, momentum_score
        FROM {LGBM_SCHEMA}.snowflake_cache
        WHERE ticker = :ticker
        LIMIT 1
    """)

    try:
        # ── Jedno połączenie dla wszystkich trzech zapytań ────────────────────
        with engine.connect() as conn:
            fund_row  = conn.execute(q_fund, {
                'ticker': ticker_upper,
                'fund_model': FUND_MODEL,
            }).fetchone()

            fund_prev_row = conn.execute(q_fund_prev, {
                'ticker': ticker_upper,
                'fund_model': FUND_MODEL,
            }).fetchone()

            mom_row   = conn.execute(q_mom, {
                'ticker': ticker_upper,
                'mom_model': MOM_MODEL,
            }).fetchone()

            sent_row  = conn.execute(q_sent, {'ticker': ticker_upper}).fetchone()

            snow_row  = conn.execute(q_snow, {'ticker': ticker_upper}).fetchone()

        if not fund_row and not mom_row:
            return jsonify(None)

        # ── Wyciągnij wartości ────────────────────────────────────────────────
        def mf(v, nd=2):
            if v is None: return None
            try: return round(float(v), nd)
            except: return None

        keys = [
            'fundamental_score', 'fundamental_rank', 'run_date', 'data_date',
            'pe_ratio', 'roe', 'price_to_book', 'ev_ebitda', 'fcf_yield',
            'revenue_yoy', 'revenue_growth_1y', 'company_id', 'total_in_ranking',
            'ebitda_margin', 'roa', 'net_profit_growth_1y', 'cf_oper_to_profit',
            'net_fin_debt_to_ebitda', 'current_ratio', 'rel_strength_6m',
        ]
        fd = dict(zip(keys, fund_row)) if fund_row else {}

        fundamental_score = mf(fd.get('fundamental_score'))
        fundamental_prev  = mf(fund_prev_row[0]) if fund_prev_row else None
        momentum_score    = mf(mom_row[0]) if mom_row else None
        avg_impact        = mf(sent_row[0]) if sent_row and sent_row[0] is not None else None
        sentiment_score   = _sentiment_to_score(avg_impact)

        # ── Master score ──────────────────────────────────────────────────────
        parts, ws = [], []
        if fundamental_score is not None:
            parts.append(fundamental_score * W_FUNDAMENTAL); ws.append(W_FUNDAMENTAL)
        if momentum_score is not None:
            parts.append(momentum_score * W_MOMENTUM);       ws.append(W_MOMENTUM)
        if sentiment_score is not None:
            parts.append(sentiment_score * W_SENTIMENT);     ws.append(W_SENTIMENT)

        if not parts:
            return jsonify(None)

        master_score = round(sum(parts) / sum(ws), 2)

        # ── Snowflake (z lgbm.snowflake_cache — percentyl vs GPW) ────────────
        # Pięć wymiarów to czyste percentyle z vw_snowflake (stan bieżący):
        #   jakosc  = quality_score  (ROE, marża, CF, Piotroski)
        #   wycena  = value_score    (P/E, EV/EBITDA, FCF yield)
        #   wzrost  = growth_score   (przychody, zysk, EBIT QoQ)
        #   zdrowie = health_score   (dług, płynność, Altman Z)
        #   trend   = momentum_score (price change, rel strength, spread)
        # NIE mieszamy z ML scores (fundamental/momentum/sentiment).
        if snow_row:
            snow_keys = ['quality_score', 'value_score', 'growth_score',
                         'health_score', 'momentum_score']
            sd = dict(zip(snow_keys, snow_row))
            snowflake = {
                'jakosc':  mf(sd['quality_score'], 1)  or 5.0,
                'wycena':  mf(sd['value_score'], 1)    or 5.0,
                'wzrost':  mf(sd['growth_score'], 1)   or 5.0,
                'zdrowie': mf(sd['health_score'], 1)   or 5.0,
                'trend':   mf(sd['momentum_score'], 1) or 5.0,
            }
        else:
            snowflake = {
                'jakosc':  5.0,
                'wycena':  5.0,
                'wzrost':  5.0,
                'zdrowie': 5.0,
                'trend':   5.0,
            }

        # ── Pros / cons ───────────────────────────────────────────────────────
        pros, cons = _get_pros_cons(fd)

        # ── Kluczowe fundamenty (dla FundamentalsSection) ────────────────────
        fundamentals = _build_fundamentals(fd)

        run_date = fd.get('run_date')
        updated_at = run_date.strftime('%d %b %Y') if run_date else None

        return jsonify({
            'ticker':               ticker_upper,
            'master_score':         master_score,
            'score_tag':            _score_tag(master_score),
            'fundamental_score':    fundamental_score,
            'fundamental_score_label': _fundamental_label(fundamental_score) if fundamental_score else None,
            'fundamental_score_change': round(fundamental_score - fundamental_prev, 2) if (fundamental_score is not None and fundamental_prev is not None) else None,
            'fundamental_rank':     int(fd['fundamental_rank']) if fd.get('fundamental_rank') else None,
            'fundamental_total':    int(fd['total_in_ranking']) if fd.get('total_in_ranking') else None,
            'fundamental_run_date': run_date.strftime('%Y-%m-%d') if run_date else None,
            'momentum_score':       momentum_score,
            'sentiment_score':      sentiment_score,
            'snowflake':            snowflake,
            'pros':                 pros,
            'cons':                 cons,
            'fundamentals':         fundamentals,
            'updated_at':           updated_at,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@assessment_bp.route('/api/watchlist/summary', methods=['POST'])
def get_watchlist_summary():
    """
    Batch endpoint: zwraca uproszczone dane dla wielu tickerów naraz.
    Body: { "tickers": ["CDR", "XTB", ...] }
    Zwraca: dict ticker → { master_score, fundamental_score, momentum_score,
            sentiment_score, score_tag, current_price, prev_price, spark }
    """
    body = request.get_json(silent=True) or {}
    tickers = body.get('tickers', [])
    if not tickers or not isinstance(tickers, list):
        return jsonify({}), 200

    tickers_upper = [t.upper() for t in tickers[:50]]  # limit 50

    try:
        with engine.connect() as conn:
            # ── 1. Fundamental scores (latest run per ticker) ────────────────
            q_fund = text(f"""
                SELECT DISTINCT ON (sr.ticker)
                    sr.ticker, sr.score
                FROM {LGBM_SCHEMA}.scoring_results sr
                WHERE sr.ticker = ANY(:tickers)
                  AND sr.model_version = :fund_model
                ORDER BY sr.ticker, sr.run_date DESC
            """)
            fund_rows = conn.execute(q_fund, {
                'tickers': tickers_upper, 'fund_model': FUND_MODEL
            }).fetchall()
            fund_map = {r[0]: round(float(r[1]), 2) for r in fund_rows}

            # ── 2. Momentum scores (latest run per ticker) ───────────────────
            q_mom = text(f"""
                SELECT DISTINCT ON (ticker)
                    ticker, score
                FROM {LGBM_SCHEMA}.scoring_results_momentum
                WHERE ticker = ANY(:tickers)
                  AND model_version = :mom_model
                ORDER BY ticker, run_date DESC
            """)
            mom_rows = conn.execute(q_mom, {
                'tickers': tickers_upper, 'mom_model': MOM_MODEL
            }).fetchall()
            mom_map = {r[0]: round(float(r[1]), 2) for r in mom_rows}

            # ── 3. Sentiment scores (90-day average impact) ──────────────────
            q_sent = text(f"""
                SELECT ts.ticker, AVG(ts.impact::numeric)
                FROM {schema}.ticker_sentiment ts
                JOIN {schema}.analysis_result ar ON ts.analysis_id = ar.id
                JOIN {schema}.news_articles na   ON ar.news_id    = na.id
                WHERE ts.ticker = ANY(:tickers)
                  AND na.date >= CURRENT_DATE - INTERVAL '90 days'
                GROUP BY ts.ticker
            """)
            sent_rows = conn.execute(q_sent, {'tickers': tickers_upper}).fetchall()
            sent_map = {}
            for r in sent_rows:
                if r[1] is not None:
                    sent_map[r[0]] = _sentiment_to_score(float(r[1]))

            # ── 4. Sparkline: last 60 days of daily prices ───────────────────
            q_spark = text("""
                SELECT ticker, date, close
                FROM lgbm.daily_prices
                WHERE ticker = ANY(:tickers)
                  AND date >= CURRENT_DATE - INTERVAL '60 days'
                  AND close IS NOT NULL
                ORDER BY ticker, date ASC
            """)
            spark_rows = conn.execute(q_spark, {'tickers': tickers_upper}).fetchall()
            spark_map: dict[str, list] = {}
            for r in spark_rows:
                tk = r[0]
                if tk not in spark_map:
                    spark_map[tk] = []
                spark_map[tk].append({'date': str(r[1]), 'close': float(r[2])})

        # ── Build response ───────────────────────────────────────────────────
        result = {}
        for tk in tickers_upper:
            fs = fund_map.get(tk)
            ms = mom_map.get(tk)
            ss = sent_map.get(tk)

            parts, ws = [], []
            if fs is not None:
                parts.append(fs * W_FUNDAMENTAL); ws.append(W_FUNDAMENTAL)
            if ms is not None:
                parts.append(ms * W_MOMENTUM); ws.append(W_MOMENTUM)
            if ss is not None:
                parts.append(ss * W_SENTIMENT); ws.append(W_SENTIMENT)

            master = round(sum(parts) / sum(ws), 2) if parts else None

            prices = spark_map.get(tk, [])
            current_price = prices[-1]['close'] if prices else None
            prev_price = prices[-2]['close'] if len(prices) >= 2 else None

            result[tk] = {
                'master_score': master,
                'score_tag': _score_tag(master) if master else None,
                'fundamental_score': fs,
                'momentum_score': ms,
                'sentiment_score': ss,
                'current_price': current_price,
                'prev_price': prev_price,
                'spark': [p['close'] for p in prices],
            }

        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


_CORP_SUFFIXES = re.compile(
    r'\s+(?:S\.?A\.?S?\.?|Sp\.?\s*z\s*o\.?o\.?|S\.K\.A\.?|ASI|TFI|NFI'
    r'|Holding|Holdings|Group|Inc\.?|Ltd\.?|GmbH|AG|PLC|Corp\.?)$',
    re.IGNORECASE,
)

def _shorten_name(raw: str) -> str:
    """Usuwa korporacyjne suffiksy z końca nazwy (np. 'Scanway SA' → 'Scanway')."""
    name = raw.strip()
    prev = None
    while prev != name:
        prev = name
        name = _CORP_SUFFIXES.sub('', name).strip().rstrip(',').strip()
    return name or raw


@assessment_bp.route('/api/tickers/<ticker>/prices', methods=['GET'])
def get_ticker_prices(ticker: str):
    """
    Zwraca pełną historię cen dziennych z lgbm.daily_prices dla danego tickera.
    Używane przez wykres notowań (MAX period).
    """
    try:
        q = text("""
            SELECT date, close
            FROM lgbm.daily_prices
            WHERE ticker = :ticker
              AND close IS NOT NULL
            ORDER BY date ASC
        """)
        with engine.connect() as conn:
            rows = conn.execute(q, {'ticker': ticker.upper()}).fetchall()
        if not rows:
            return jsonify([]), 200
        return jsonify([{'date': str(r[0]), 'close': float(r[1])} for r in rows])
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@assessment_bp.route('/api/companies/names', methods=['GET'])
def get_company_names():
    """
    Zwraca mapowanie ticker → company_name dla wszystkich spółek.
    Źródłem jest tabela tickers (pełna lista GPW), nie snowflake_cache
    (która zawiera tylko spółki ze scoringiem).
    Frontend cachuje wynik i nie odpytuje ponownie.
    """
    try:
        q = text(f"""
            SELECT ticker, company_name
            FROM {schema}.tickers
            WHERE deprecated_by IS NULL
            ORDER BY ticker
        """)
        with engine.connect() as conn:
            rows = conn.execute(q).fetchall()
        return jsonify([{'ticker': r[0], 'name': _shorten_name(r[1]) if r[1] else r[0]} for r in rows])
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

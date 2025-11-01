import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from collections import defaultdict
from database import Database, NewsArticle, AnalysisResult, TickerSentiment, Ticker, SectorSentiment
import pandas as pd

load_dotenv()

client = OpenAI(api_key=os.getenv('OPENAI_API', ''))
PROMPT_NEWS = """
Jesteś analitykiem giełdowym specjalizującym się w rynku GPW i dużych spółkach amerykańskich.
Twoim zadaniem jest ocenić pojedynczy news pod kątem jego potencjalnego wpływu na kursy akcji.

Oceń poniższy news i zwróć wynik w formacie JSON.

Zasady oceny:
1. "impact" – liczba od -1.0 do +1.0 (wpływ na kurs, gdzie -1.0 to bardzo negatywny, +1.0 to bardzo pozytywny),
2. "confidence" – 0.0–1.0 (pewność oceny),
3. "sector" – sektor gospodarki,
4. "related_tickers" – lista powiązanych spółek z tą konkretną wiadomością,
5. "type" – "okazja krótkoterminowa" / "średnioterminowa" / "długoterminowa",
6. "reason" – krótkie uzasadnienie.

News:
"{headline}"
"{lead}"

Zwróć wyłącznie JSON:
{{
  "impact": <liczba>,
  "confidence": <liczba>,
  "sector": "<nazwa sektora>",
  "related_tickers": ["..."],
  "type": "<typ okazji>",
  "reason": "<krótkie wyjaśnienie>"
}}
"""

def analyze_news(headline, lead):
    """
    Analizuje pojedynczy news za pomocą OpenAI API.

    Args:
        headline: Tytuł artykułu
        lead: Treść/lead artykułu

    Returns:
        JSON string z wynikiem analizy
    """
    prompt = PROMPT_NEWS.format(headline=headline, lead=lead)

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content


def get_unanalyzed_articles(db: Database):
    """
    Pobiera artykuły, które nie mają jeszcze analizy.

    Args:
        db: Instancja Database

    Returns:
        Lista obiektów NewsArticle
    """
    session = db.Session()
    try:
        # Wybierz artykuły, które nie mają wpisu w analysis_result
        articles = session.query(NewsArticle).outerjoin(
            AnalysisResult, NewsArticle.id == AnalysisResult.news_id
        ).filter(AnalysisResult.id == None).all()
        return articles
    finally:
        session.close()


def get_article_by_id(db: Database, article_id: int):
    """
    Pobiera artykuł po ID.

    Args:
        db: Instancja Database
        article_id: ID artykułu

    Returns:
        Obiekt NewsArticle lub None
    """
    session = db.Session()
    try:
        return session.query(NewsArticle).filter(NewsArticle.id == article_id).first()
    finally:
        session.close()


def is_article_analyzed(db: Database, article_id: int) -> bool:
    """
    Sprawdza czy artykuł został już przeanalizowany.

    Args:
        db: Instancja Database
        article_id: ID artykułu

    Returns:
        True jeśli artykuł ma już analizę, False w przeciwnym razie
    """
    session = db.Session()
    try:
        exists = session.query(AnalysisResult).filter(
            AnalysisResult.news_id == article_id
        ).first() is not None
        return exists
    finally:
        session.close()


def save_analysis_results(db: Database, news_id: int, analysis_json: str):
    """
    Zapisuje wyniki analizy do bazy danych.

    Args:
        db: Instancja Database
        news_id: ID artykułu
        analysis_json: JSON string z wynikiem analizy

    Returns:
        ID utworzonego rekordu AnalysisResult
    """
    session = db.Session()
    try:
        # Usuń potencjalny blok markdown z JSON
        cleaned_json = analysis_json.strip()
        if cleaned_json.startswith('```'):
            # Znajdź początek i koniec bloku JSON
            lines = cleaned_json.split('\n')
            cleaned_json = '\n'.join(lines[1:-1]) if len(lines) > 2 else cleaned_json

        # Parsuj JSON
        print(f"DEBUG: Parsing JSON: {cleaned_json[:200]}...")
        analysis_data = json.loads(cleaned_json)

        # Utwórz wpis w analysis_result
        analysis_result = AnalysisResult(
            news_id=news_id,
            summary=cleaned_json
        )
        session.add(analysis_result)
        session.flush()  # Aby uzyskać ID
        print(f"DEBUG: Utworzono AnalysisResult z ID={analysis_result.id}")

        # Utwórz wpisy w ticker_sentiment dla każdego powiązanego tickera
        related_tickers = analysis_data.get('related_tickers', [])
        impact_value = analysis_data.get('impact', 0.0)
        confidence_value = analysis_data.get('confidence', 0.0)
        sector = analysis_data.get('sector', '')

        print(f"DEBUG: related_tickers={related_tickers}, impact={impact_value}, confidence={confidence_value}, sector={sector}")

        # Najpierw dodaj tickery do słownika (jeśli nie istnieją)
        for ticker_symbol in related_tickers:
            existing_ticker = session.query(Ticker).filter(Ticker.ticker == ticker_symbol).first()
            if not existing_ticker:
                print(f"DEBUG: Dodaję nowy ticker do słownika: {ticker_symbol}")
                new_ticker = Ticker(
                    ticker=ticker_symbol,
                    company_name=None,  # Może być uzupełnione później
                    sector=sector
                )
                session.add(new_ticker)
            else:
                print(f"DEBUG: Ticker {ticker_symbol} już istnieje w słowniku")

        # Teraz utwórz ticker_sentiments
        for ticker_symbol in related_tickers:
            print(f"DEBUG: Dodaję ticker_sentiment dla {ticker_symbol} z impact={impact_value}, confidence={confidence_value}")
            ticker_sentiment = TickerSentiment(
                analysis_id=analysis_result.id,
                ticker=ticker_symbol,
                sector=sector,
                impact=str(impact_value),  # Wartość impact jako string
                score=confidence_value  # Confidence (0.0-1.0) zapisane w kolumnie score
            )
            session.add(ticker_sentiment)

        # Dodaj sector_sentiment
        if sector:
            print(f"DEBUG: Dodaję sector_sentiment dla sektora: {sector} z impact={impact_value}, confidence={confidence_value}")
            sector_sentiment = SectorSentiment(
                analysis_id=analysis_result.id,
                sector=sector,
                impact=str(impact_value),  # Wartość impact jako string
                score=confidence_value  # Confidence (0.0-1.0) zapisane w kolumnie score
            )
            session.add(sector_sentiment)

        session.commit()
        print(f"DEBUG: Commit wykonany pomyślnie")
        return analysis_result.id
    except json.JSONDecodeError as e:
        session.rollback()
        raise ValueError(f"Nie można sparsować JSON: {e}")
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


# przykładowe dane z wyników PROMPT 1
data = [
    {"sector": "surowce", "impact": 4, "confidence": 0.9},
    {"sector": "surowce", "impact": 3, "confidence": 0.8},
    {"sector": "banki", "impact": -2, "confidence": 0.7},
    {"sector": "energetyka", "impact": 1, "confidence": 0.6},
    {"sector": "technologie", "impact": 3, "confidence": 0.8}
]

def analyze_articles(db: Database, mode: str = 'unanalyzed', article_id: int = None):
    """
    Główna funkcja do analizy artykułów.

    Args:
        db: Instancja Database
        mode: 'id' (dla konkretnego ID) lub 'unanalyzed' (dla nieprzeanalizowanych)
        article_id: ID artykułu (wymagane gdy mode='id')

    Returns:
        Dict z informacją o przetworzonych artykułach
    """
    articles = []

    if mode == 'id':
        if article_id is None:
            raise ValueError("Dla trybu 'id' musisz podać article_id")
        print(f"Szukam artykułu o ID={article_id}...")
        article = get_article_by_id(db, article_id)
        if article:
            articles = [article]
            print(f"Znaleziono artykuł: {article.title[:80]}")
        else:
            print(f"Nie znaleziono artykułu o ID={article_id}")
            return {"status": "error", "message": f"Nie znaleziono artykułu o ID={article_id}"}
    elif mode == 'unanalyzed':
        print("Szukam nieprzeanalizowanych artykułów...")
        articles = get_unanalyzed_articles(db)
        print(f"Znaleziono {len(articles)} nieprzeanalizowanych artykułów")
    else:
        raise ValueError(f"Nieprawidłowy tryb: {mode}. Użyj 'id' lub 'unanalyzed'")

    if not articles:
        print("Brak artykułów do analizy")
        return {"status": "success", "message": "Brak artykułów do analizy", "analyzed": 0}

    results = []
    for article in articles:
        try:
            print(f"\n=== Przetwarzam artykuł ID={article.id}: {article.title[:50]}...")

            # Sprawdź czy artykuł już został przeanalizowany
            if is_article_analyzed(db, article.id):
                print(f"⊘ Artykuł ID={article.id} został już wcześniej przeanalizowany - pomijam")
                results.append({
                    "article_id": article.id,
                    "title": article.title,
                    "status": "skipped",
                    "reason": "already_analyzed"
                })
                continue

            # Analizuj artykuł
            print(f"Wysyłam zapytanie do OpenAI...")
            analysis_json = analyze_news(article.title, article.content or "")
            print(f"Otrzymano odpowiedź: {analysis_json[:200]}...")

            # Zapisz wyniki
            print(f"Zapisuję wyniki do bazy danych...")
            analysis_id = save_analysis_results(db, article.id, analysis_json)
            print(f"✓ Pomyślnie zapisano analizę (analysis_id={analysis_id})")

            results.append({
                "article_id": article.id,
                "analysis_id": analysis_id,
                "title": article.title,
                "status": "success"
            })
        except Exception as e:
            print(f"✗ BŁĄD podczas analizy artykułu ID={article.id}: {str(e)}")
            import traceback
            traceback.print_exc()
            results.append({
                "article_id": article.id,
                "title": article.title,
                "status": "error",
                "error": str(e)
            })

    success_count = sum(1 for r in results if r['status'] == 'success')
    skipped_count = sum(1 for r in results if r['status'] == 'skipped')
    error_count = sum(1 for r in results if r['status'] == 'error')

    return {
        "status": "completed",
        "analyzed": success_count,
        "skipped": skipped_count,
        "errors": error_count,
        "results": results
    }

def calculate_trends(news_list):
    """
    Oblicza trendy sektorowe na podstawie ocen newsów.
    Każdy element listy powinien mieć pola:
    - 'sector': str
    - 'impact': float  (od -1 do 1)
    - 'confidence': float  (od 0 do 1)
    """

    # grupowanie po sektorach
    sectors = defaultdict(list)
    for n in news_list:
        if n.get("sector") and n.get("impact") is not None:
            weighted = n["impact"] * n.get("confidence", 1.0)
            sectors[n["sector"]].append(weighted)

    # liczymy średni trend dla każdego sektora
    summary = []
    for sector, weights in sectors.items():
        avg = sum(weights) / len(weights)

        # klasyfikacja trendu
        if avg > 0.15:
            momentum = "rosnące"
        elif avg < -0.15:
            momentum = "malejące"
        else:
            momentum = "neutralne"

        summary.append({
            "sector": sector,
            "trend_score": round(avg, 3),
            "momentum": momentum,
            "count": len(weights)
        })

    # sortowanie po sile trendu (od najwyższego do najniższego)
    summary.sort(key=lambda x: x["trend_score"], reverse=True)
    return summary


def get_sector_report(db: Database):
    """
    Generuje raport trendów dla sektorów na podstawie danych z tabeli sector_sentiment.

    Args:
        db: Instancja Database

    Returns:
        Lista słowników z trendami sektorowymi
    """
    session = db.Session()
    try:
        # Pobierz wszystkie wpisy z sector_sentiment
        sentiments = session.query(SectorSentiment).all()

        # Przekształć do formatu wymaganego przez calculate_trends
        news_list = []
        for sentiment in sentiments:
            if sentiment.sector and sentiment.impact is not None:
                try:
                    impact_value = float(sentiment.impact)
                    confidence_value = sentiment.score if sentiment.score is not None else 1.0

                    news_list.append({
                        "sector": sentiment.sector,
                        "impact": impact_value,
                        "confidence": confidence_value
                    })
                except (ValueError, TypeError):
                    # Pomiń nieprawidłowe wartości
                    continue

        # Użyj calculate_trends do obliczenia raport
        return calculate_trends(news_list)
    finally:
        session.close()


def get_ticker_report(db: Database):
    """
    Generuje raport trendów dla tickerów na podstawie danych z tabeli ticker_sentiment.

    Args:
        db: Instancja Database

    Returns:
        Lista słowników z trendami dla tickerów
    """
    session = db.Session()
    try:
        # Pobierz wszystkie wpisy z ticker_sentiment
        sentiments = session.query(TickerSentiment).all()

        # Grupowanie po tickerach
        tickers = defaultdict(list)
        for sentiment in sentiments:
            if sentiment.ticker and sentiment.impact is not None:
                try:
                    impact_value = float(sentiment.impact)
                    confidence_value = sentiment.score if sentiment.score is not None else 1.0
                    weighted = impact_value * confidence_value
                    tickers[sentiment.ticker].append(weighted)
                except (ValueError, TypeError):
                    continue

        # Liczymy średni trend dla każdego tickera
        summary = []
        for ticker, weights in tickers.items():
            avg = sum(weights) / len(weights)

            # Klasyfikacja trendu
            if avg > 0.15:
                momentum = "pozytywny"
            elif avg < -0.15:
                momentum = "negatywny"
            else:
                momentum = "neutralny"

            summary.append({
                "ticker": ticker,
                "trend_score": round(avg, 3),
                "momentum": momentum,
                "count": len(weights)
            })

        # Sortowanie po sile trendu
        summary.sort(key=lambda x: x["trend_score"], reverse=True)
        return summary
    finally:
        session.close()


def generate_report(db: Database):
    """
    Generuje pełny raport zawierający trendy dla sektorów i tickerów.

    Args:
        db: Instancja Database

    Returns:
        Dict z raportami dla sektorów i tickerów
    """
    print("\n" + "="*60)
    print("GENEROWANIE RAPORTU ANALIZ")
    print("="*60)

    # Raport dla sektorów
    print("\n[1/2] Generuję raport dla sektorów...")
    sector_report = get_sector_report(db)
    print(f"✓ Znaleziono {len(sector_report)} sektorów")

    # Raport dla tickerów
    print("\n[2/2] Generuję raport dla spółek (tickerów)...")
    ticker_report = get_ticker_report(db)
    print(f"✓ Znaleziono {len(ticker_report)} tickerów")

    report = {
        "sectors": sector_report,
        "tickers": ticker_report
    }

    # Wyświetl podsumowanie
    print("\n" + "="*60)
    print("RAPORT SEKTORÓW")
    print("="*60)
    if sector_report:
        for sector in sector_report[:10]:  # Top 10
            print(f"{sector['sector']:20} | Score: {sector['trend_score']:+6.3f} | "
                  f"Momentum: {sector['momentum']:12} | Liczba: {sector['count']}")
    else:
        print("Brak danych dla sektorów")

    print("\n" + "="*60)
    print("RAPORT SPÓŁEK (TOP 20)")
    print("="*60)
    if ticker_report:
        for ticker in ticker_report[:20]:  # Top 20
            print(f"{ticker['ticker']:10} | Score: {ticker['trend_score']:+6.3f} | "
                  f"Momentum: {ticker['momentum']:12} | Liczba: {ticker['count']}")
    else:
        print("Brak danych dla tickerów")

    print("\n" + "="*60)

    return report

if __name__ == "__main__":
    """
    Przykład użycia:

    # Tryb 1: Analiza konkretnego artykułu po ID
    db = Database('news.db')
    result = analyze_articles(db, mode='id', article_id=123)
    print(result)

    # Tryb 2: Analiza wszystkich nieprzeanalizowanych artykułów
    db = Database('news.db')
    result = analyze_articles(db, mode='unanalyzed')
    print(result)
    """
    import sys
    from config import Config

    config = Config()
    db = Database(config.db_path)

    if len(sys.argv) > 1:
        if sys.argv[1] == '--id' and len(sys.argv) > 2:
            # Analiza konkretnego artykułu
            article_id = int(sys.argv[2])
            print(f"Analizuję artykuł ID={article_id}...")
            result = analyze_articles(db, mode='id', article_id=article_id)
            print(result)
        elif sys.argv[1] == '--unanalyzed':
            # Analiza nieprzeanalizowanych
            print("Analizuję nieprzeanalizowane artykuły...")
            result = analyze_articles(db, mode='unanalyzed')
            print(result)
        elif sys.argv[1] == '--report':
            # Generuj raport
            report = generate_report(db)
        else:
            print("Użycie:")
            print("  python ai_analist.py --id <article_id>  # Analizuj konkretny artykuł")
            print("  python ai_analist.py --unanalyzed       # Analizuj wszystkie nieprzeanalizowane")
            print("  python ai_analist.py --report           # Generuj raport trendów")
    else:
        print("Użycie:")
        print("  python ai_analist.py --id <article_id>  # Analizuj konkretny artykuł")
        print("  python ai_analist.py --unanalyzed       # Analizuj wszystkie nieprzeanalizowane")
        print("  python ai_analist.py --report           # Generuj raport trendów")



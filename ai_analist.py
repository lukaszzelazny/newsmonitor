import os
import json
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv
from collections import defaultdict
from database import Database, NewsArticle, AnalysisResult, TickerSentiment, Ticker, \
    SectorSentiment, BrokerageAnalysis
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import text

load_dotenv()

client = OpenAI(api_key=os.getenv('OPENAI_API', ''))

def load_patterns(filepath='patterns.json', name="relevant_patterns"):
    """Wczytuje atrybut 'relevant_patterns' z pliku JSON"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if name in data:
                return data[name]
            else:
                print(f"Brak klucza {name} w {filepath}, używam domyślnych wzorców")
                return None
    except FileNotFoundError:
        print(f"Brak pliku {filepath}, używam domyślnych wzorców")
        return None


# Wzorcowe frazy dla różnych kategorii istotnych newsów
RELEVANT_PATTERNS = load_patterns(name="revelant_patterns")
# Nieistotne wzorce
IRRELEVANT_PATTERNS = load_patterns(name="irrevelant_patterns")
NEGATIVE_KEYWORDS = load_patterns(name="negative_keywords")

NEWS_SUMMARY_PATTERN = load_patterns(name="summary_patterns")

def get_embedding(text: str, model: str = "text-embedding-3-large"):
    """
    Pobiera embedding dla danego tekstu.

    Args:
        text: Tekst do embedowania
        model: Model embeddings

    Returns:
        Lista float - wektor embedingu
    """
    text = text.replace("\n", " ").strip()
    if not text:
        return None

    try:
        response = client.embeddings.create(input=[text], model=model)
        return response.data[0].embedding
    except Exception as e:
        print(f"Błąd podczas generowania embeddingu: {e}")
        return None


def calculate_relevance_score(news_embedding, pattern_embeddings):
    """
    Oblicza score istotności na podstawie podobieństwa cosine.

    Args:
        news_embedding: Embedding newsa
        pattern_embeddings: Lista embeddings wzorców

    Returns:
        Float - maksymalne podobieństwo (0-1)
    """
    if news_embedding is None or not pattern_embeddings:
        return 0.0

    news_emb = np.array(news_embedding).reshape(1, -1)

    max_similarity = 0.0
    for pattern_emb in pattern_embeddings:
        if pattern_emb is not None:
            pattern_arr = np.array(pattern_emb).reshape(1, -1)
            similarity = cosine_similarity(news_emb, pattern_arr)[0][0]
            max_similarity = max(max_similarity, similarity)

    return float(max_similarity)


def contains_pattern(pattern: list, title: str, content: str) -> tuple[bool, str]:
    """
    Sprawdza czy news zawiera słowa kluczowe z listy pattern.
    
    Args:
        title: Tytuł artykułu
        content: Treść artykułu
    
    Returns:
        Tuple[bool, str] - (czy_zawiera, znalezione_słowo_kluczowe)
    """
    if not pattern:
        return False, ""
    
    # Łączymy tytuł i treść w jeden tekst
    full_text = f"{title} {content or ''}".lower()
    
    # Sprawdzamy każde słowo kluczowe
    for keyword in pattern:
        if keyword.lower() in full_text:
            return True, keyword
    
    return False, ""


def is_news_relevant(headline: str, lead: str, threshold: float = 0.65):
    """
    Sprawdza czy news jest istotny przy użyciu embeddings.

    Args:
        headline: Tytuł artykułu
        lead: Treść artykułu
        threshold: Próg istotności (0-1)

    Returns:
        Tuple[bool, float, str] - (czy_istotny, score, powód)
    """
    # Połącz tytuł i lead
    full_text = f"{headline}. {lead}"

    # Pobierz embedding newsa
    news_embedding = get_embedding(full_text)
    if news_embedding is None:
        return False, 0.0, "Błąd generowania embeddingu"

    # Generuj embeddingi dla wzorców istotnych (cachowane w pamięci)
    if not hasattr(is_news_relevant, '_relevant_cache'):
        print("Generuję embeddingi wzorców istotnych...")
        is_news_relevant._relevant_cache = {}
        for category, patterns in RELEVANT_PATTERNS.items():
            is_news_relevant._relevant_cache[category] = [
                get_embedding(pattern) for pattern in patterns
            ]

    # Generuj embeddingi dla wzorców nieistotnych
    if not hasattr(is_news_relevant, '_irrelevant_cache'):
        print("Generuję embeddingi wzorców nieistotnych...")
        is_news_relevant._irrelevant_cache = [
            get_embedding(pattern) for pattern in IRRELEVANT_PATTERNS
        ]

    # Oblicz score dla kategorii istotnych
    category_scores = {}
    for category, embeddings in is_news_relevant._relevant_cache.items():
        score = calculate_relevance_score(news_embedding, embeddings)
        category_scores[category] = score

    max_relevant_score = max(category_scores.values()) if category_scores else 0.0
    best_category = max(category_scores,
                        key=category_scores.get) if category_scores else None

    # Oblicz score dla wzorców nieistotnych
    irrelevant_score = calculate_relevance_score(
        news_embedding,
        is_news_relevant._irrelevant_cache
    )

    # Decyzja
    if irrelevant_score > 0.70:
        return False, irrelevant_score, f"Wykryto nieistotny wzorzec (score: {irrelevant_score:.3f})"

    if max_relevant_score >= threshold:
        return True, max_relevant_score, f"Kategoria: {best_category} (score: {max_relevant_score:.3f})"

    return False, max_relevant_score, f"{max_relevant_score:.3f} < {threshold}, {best_category}"


def save_not_analyzed(db: Database, news_id: int, reason: str, relevance_score: float):
    """
    Zapisuje informację o newsie, który nie został przeanalizowany.

    Args:
        db: Instancja Database
        news_id: ID artykułu
        reason: Powód nieprzeanalizowania
        relevance_score: Score istotności
    """
    session = db.Session()
    try:
        session.execute(
            text("""
            INSERT INTO news_not_analyzed (news_id, reason, relevance_score)
            VALUES (:news_id, :reason, :relevance_score)
            ON CONFLICT (news_id) DO NOTHING
            """),
            {"news_id": news_id, "reason": reason, "relevance_score": relevance_score}
        )
        session.commit()
        print(f"✓ Zapisano do news_not_analyzed: ID={news_id}, powód: {reason}")
    except Exception as e:
        session.rollback()
        print(f"✗ Błąd zapisu do news_not_analyzed: {e}")
    finally:
        session.close()


PROMPT_NEWS = """
Jesteś doświadczonym analitykiem giełdowym.
Twoim zadaniem jest analizować wiadomości ekonomiczne, giełdowe i biznesowe
(np. z serwisu PAP Biznes) oraz oceniać ich potencjalne znaczenie rynkowe.

Zasady analizy:
1. **Rozpoznaj typ wiadomości**:
   - 🏢 Spółka (dotyczy konkretnego podmiotu lub kilku spółek)
   - 🏭 Sektor (dotyczy branży, np. banki, energetyka, gaming)
   - 💰 Debiut / IPO (informacja o wejściu spółki na giełdę)
   - 📊 Makro / Rynek (dotyczy ogólnych zjawisk gospodarczych)
   - 📉 Niepowiązana / neutralna (nie ma znaczenia dla rynku)

2. **Zidentyfikuj tickery**:
   - Jeżeli wiadomość dotyczy konkretnych spółek, zwróć jeden główny ticker oraz ewentualnie inne powiązane.
   - Jeśli brak – zwróć pustą listę: `"related_tickers": []`.

3. **Zwróć szczególną uwagę na wyceny podawane przez domy maklerskie (DM)**:
   - Jeśli występuje nowa wycena, wypisz:
     - nazwę domu maklerskiego,
     - starą wycenę,
     - nową wycenę,
     - zmianę procentową,
     - rekomendację (np. „kupuj", „neutralnie", „sprzedaj"),
     - krótki komentarz.
   - Jeśli nie ma danych o wycenach – wpisz wartości `null`.

4. **Oceń wpływ wiadomości**:
   - Jeśli wiadomość dotyczy spółki lub spółek:
     - `"ticker_impact"` – liczba od -1.0 do +1.0 (wpływ na kurs, gdzie -1.0 = bardzo negatywny, +1.0 = bardzo pozytywny)
     - `"confidence"` – 0.0–1.0 (pewność oceny)
     - `"occasion"` – `"krótkoterminowa"`, `"średnioterminowa"` lub `"długoterminowa"`
     - `"sector"` – nazwa sektora
     - `"sector_impact"` – `null`
   - Jeśli wiadomość nie zawiera tickerów, ale dotyczy sektora:
     - `"sector"` – nazwa sektora
     - `"sector_impact"` – liczba od -1.0 do +1.0
     - `"confidence"` – 0.0–1.0
     - `"occasion"` – `null`
     - `"ticker_impact"` – `null`
   - Jeśli wiadomość jest neutralna:
     - Wszystkie pola wpływu (`ticker_impact`, `sector_impact`, `confidence`, `occasion`, `sector`) mają wartość `null`.

5. **Dodaj krótkie uzasadnienie** w polu `"reason"` – jedno lub dwa zdania.

---

### Wejście:
News:
"{headline}"
"{lead}"

### Oczekiwany wynik:
Zwróć wyłącznie **poprawny JSON** w formacie:

{{
  "typ": "<Sektor / Spółka / Makro / IPO / Neutralna>",
  "related_tickers": ["..."],
  "sector": "<nazwa sektora lub null>",
  "ticker_impact": <liczba lub null>,
  "sector_impact": <liczba lub null>,
  "confidence": <liczba lub null>,
  "occasion": "<typ okazji lub null>",
  "reason": "<krótkie wyjaśnienie>",
  "brokerage_house": "<nazwa domu maklerskiego lub null>",
  "price_old": "<stara wycena lub null>",
  "price_new": "<nowa wycena lub null>",
  "price_recomendation": "<rekomendacja lub null>",
  "price_comment": "<komentarz do wyceny lub null>"
}}
"""


PROMPT_SUMMARY = """
🧠 Prompt PRO — analiza podsumowania dnia (zbioru newsów)

Jesteś doświadczonym analitykiem giełdowym.
Twoim zadaniem jest analizować zbiorcze podsumowania wiadomości ekonomicznych, giełdowych i biznesowych (np. z serwisu PAP Biznes lub Strefa Inwestorów) i oceniać potencjalne znaczenie poszczególnych informacji rynkowych.

Tekst, który otrzymasz, może zawierać wiele krótkich newsów lub streszczeń w jednym artykule. Każdy z nich potraktuj jako osobny wpis.
Dla każdego fragmentu (newsa) zastosuj poniższe zasady analizy i zwróć listę obiektów JSON – po jednym dla każdej istotnej informacji.
Zasady analizy:

Rozpoznaj typ wiadomości:
🏢 Spółka – dotyczy konkretnego podmiotu lub kilku spółek,
🏭 Sektor – odnosi się do całej branży (np. banki, energetyka, gaming),
💰 Debiut / IPO – informacja o wejściu spółki na giełdę,
📊 Makro / Rynek – dotyczy zjawisk gospodarczych, wskaźników, polityki pieniężnej, cen surowców, decyzji NBP/FED itp.,
📉 Niepowiązana / Neutralna – nie ma znaczenia dla rynku lub kursów akcji.

Zidentyfikuj tickery:

Jeżeli wiadomość dotyczy konkretnych spółek, wypisz ich tickery (np. "related_tickers": ["KGHM", "PZU"]).
Jeśli brak — zwróć pustą listę: "related_tickers": [].
Uwzględnij nowe wyceny od domów maklerskich (DM):
Jeśli występuje informacja o rekomendacji lub zmianie wyceny, wypisz:

"brokerage_house" – nazwa domu maklerskiego,
"price_old" – stara wycena,
"price_new" – nowa wycena,
"price_recomendation" – np. "kupuj", "neutralnie", "sprzedaj",
"price_comment" – krótki opis komentarza,
"reason" – uzasadnienie wpływu tej zmiany.

Jeśli brak danych o wycenach — wpisz wartości null.
Oceń wpływ wiadomości:
Jeśli dotyczy spółki/spółek:

"ticker_impact" – liczba od -1.0 do +1.0,
"confidence" – liczba od 0.0 do 1.0,
"occasion" – "krótkoterminowa", "średnioterminowa", "długoterminowa",
"sector" – nazwa sektora,
"sector_impact" – null.

Jeśli dotyczy całego sektora:
"sector" – nazwa sektora,
"sector_impact" – liczba od -1.0 do +1.0,
"confidence" – liczba od 0.0 do 1.0,
"occasion" – null,
"ticker_impact" – null.

Jeśli wiadomość neutralna:
wszystkie pola wpływu (ticker_impact, sector_impact, confidence, occasion, sector) mają wartość null.
Dodaj krótkie uzasadnienie ("reason") – jedno lub dwa zdania wyjaśniające, dlaczego dana informacja może (lub nie może) wpłynąć na rynek.
Wejście:

Podsumowanie dnia:
{news_summary_text}

Oczekiwany wynik:
Zwróć wyłącznie poprawny JSON zawierający listę obiektów – każdy reprezentuje osobny news:

[
  {{
    "typ": "Spółka",
    "related_tickers": ["KGHM"],
    "sector": "surowce",
    "ticker_impact": 0.8,
    "sector_impact": null,
    "confidence": 0.9,
    "occasion": "średnioterminowa",
    "reason": "Ceny miedzi wzrosły po ograniczeniu eksportu z Chile, co sprzyja KGHM.",
    "brokerage_house": null,
    "price_old": null,
    "price_new": null,
    "price_recomendation": null,
    "price_comment": null
  }},
  {{
    "typ": "Sektor",
    "related_tickers": [],
    "sector": "banki",
    "ticker_impact": null,
    "sector_impact": -0.6,
    "confidence": 0.8,
    "occasion": null,
    "reason": "NBP zapowiedział możliwość obniżki stóp, co ogranicza marże odsetkowe banków.",
    "brokerage_house": null,
    "price_old": null,
    "price_new": null,
    "price_recomendation": null,
    "price_comment": null
  }}
]
"""

def analyze_summary(headline, lead):
    """
    Analizuje podsumowanie dnia (może zawierać wiele newsów) za pomocą OpenAI API.

    Args:
        headline: Tytuł artykułu
        lead: Treść/lead artykułu (podsumowanie wielu newsów)

    Returns:
        JSON string z listą analiz (array)
    """
    news_summary_text = f"{headline}\n\n{lead}"
    prompt = PROMPT_SUMMARY.format(news_summary_text=news_summary_text)

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

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


def get_unanalyzed_articles(db: Database, exclude_not_analyzed: bool = True):
    """
    Pobiera artykuły, które nie mają jeszcze analizy.

    Args:
        db: Instancja Database
        exclude_not_analyzed: Czy wykluczyć artykuły z tabeli news_not_analyzed (domyślnie True)

    Returns:
        Lista obiektów NewsArticle
    """
    session = db.Session()
    try:
        # Wybierz artykuły, które nie mają wpisu w analysis_result
        query = session.query(NewsArticle).outerjoin(
            AnalysisResult, NewsArticle.id == AnalysisResult.news_id
        ).filter(AnalysisResult.id == None)

        # Opcjonalnie wykluczamy artykuły z news_not_analyzed
        if exclude_not_analyzed:
            from database import NewsNotAnalyzed
            query = query.outerjoin(
                NewsNotAnalyzed, NewsArticle.id == NewsNotAnalyzed.news_id
            ).filter(NewsNotAnalyzed.id == None)

        articles = query.order_by(NewsArticle.id.desc()).all()
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


def _save_single_analysis(session, news_id: int, analysis_data: dict, analysis_result_id: int):
    """
    Pomocnicza funkcja do zapisu pojedynczej analizy.

    Args:
        session: Sesja SQLAlchemy
        news_id: ID artykułu
        analysis_data: Dict z danymi analizy
        analysis_result_id: ID utworzonego rekordu AnalysisResult
    """
    # Pobierz pola z JSON
    related_tickers = analysis_data.get('related_tickers', [])
    ticker_impact = analysis_data.get('ticker_impact')
    sector_impact = analysis_data.get('sector_impact')
    confidence_value = analysis_data.get('confidence')
    sector = analysis_data.get('sector')
    occasion = analysis_data.get('occasion')

    # Pola dla analiz domów maklerskich
    brokerage_house = analysis_data.get('brokerage_house')
    price_old = analysis_data.get('price_old')
    price_new = analysis_data.get('price_new')
    price_recommendation = analysis_data.get('price_recomendation')
    price_comment = analysis_data.get('price_comment')

    print(
        f"DEBUG: related_tickers={related_tickers}, ticker_impact={ticker_impact}, "
        f"sector_impact={sector_impact}, confidence={confidence_value}, sector={sector}, occasion={occasion}")

    # Najpierw dodaj tickery do słownika (jeśli nie istnieją)
    for ticker_symbol in related_tickers:
        existing_ticker = session.query(Ticker).filter(
            Ticker.ticker == ticker_symbol).first()
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

    # Utwórz ticker_sentiments (tylko jeśli ticker_impact nie jest null)
    if related_tickers and ticker_impact is not None:
        for ticker_symbol in related_tickers:
            print(
                f"DEBUG: Dodaję ticker_sentiment dla {ticker_symbol} z ticker_impact={ticker_impact}, "
                f"confidence={confidence_value}, occasion={occasion}")
            ticker_sentiment = TickerSentiment(
                analysis_id=analysis_result_id,
                ticker=ticker_symbol,
                sector=sector,
                impact=ticker_impact,  # Float z ticker_impact
                confidence=confidence_value,  # Confidence (0.0-1.0)
                occasion=occasion  # Typ okazji
            )
            session.add(ticker_sentiment)

    # Dodaj sector_sentiment (tylko jeśli sector_impact nie jest null)
    if sector and sector_impact is not None:
        print(
            f"DEBUG: Dodaję sector_sentiment dla sektora: {sector} z sector_impact={sector_impact}, "
            f"confidence={confidence_value}")
        sector_sentiment = SectorSentiment(
            analysis_id=analysis_result_id,
            sector=sector,
            impact=sector_impact,  # Float z sector_impact
            confidence=confidence_value  # Confidence (0.0-1.0)
        )
        session.add(sector_sentiment)

    # Dodaj BrokerageAnalysis (tylko jeśli brokerage_house nie jest puste/null)
    if brokerage_house:
        # Jeśli jest brokerage_house, powinien być co najmniej jeden ticker
        ticker_for_brokerage = related_tickers[0] if related_tickers else None
        print(
            f"DEBUG: Dodaję BrokerageAnalysis: {brokerage_house} dla {ticker_for_brokerage}")
        brokerage_analysis = BrokerageAnalysis(
            analysis_id=analysis_result_id,
            ticker=ticker_for_brokerage,
            brokerage_house=brokerage_house,
            price_old=price_old,
            price_new=price_new,
            price_recommendation=price_recommendation,
            price_comment=price_comment
        )
        session.add(brokerage_analysis)


def save_analysis_results(db: Database, news_id: int, analysis_json: str):
    """
    Zapisuje wyniki analizy do bazy danych.
    Obsługuje zarówno pojedynczą analizę (obiekt JSON), jak i listę analiz (array JSON).

    Args:
        db: Instancja Database
        news_id: ID artykułu
        analysis_json: JSON string z wynikiem analizy (obiekt lub array)

    Returns:
        ID utworzonego rekordu AnalysisResult (dla pojedynczej analizy)
        lub lista ID (dla listy analiz)
    """
    session = db.Session()
    try:
        # Usuń potencjalny blok markdown z JSON
        cleaned_json = cleanJson(analysis_json)

        # Parsuj JSON
        print(f"DEBUG: Parsing JSON: {cleaned_json[:200]}...")
        analysis_data = json.loads(cleaned_json)

        # Sprawdź czy analysis_data jest listą (podsumowanie) czy pojedynczym obiektem (pojedynczy news)
        if isinstance(analysis_data, list):
            print(f"DEBUG: Wykryto listę analiz ({len(analysis_data)} elementów)")
            # To jest lista analiz - podsumowanie dnia
            analysis_ids = []
            for idx, single_analysis in enumerate(analysis_data):
                print(f"DEBUG: Przetwarzam analizę {idx + 1}/{len(analysis_data)}")

                # Utwórz osobny wpis w analysis_result dla każdej analizy
                analysis_result = AnalysisResult(
                    news_id=news_id,
                    summary=json.dumps(single_analysis, ensure_ascii=False)
                )
                session.add(analysis_result)
                session.flush()  # Aby uzyskać ID
                print(f"DEBUG: Utworzono AnalysisResult z ID={analysis_result.id}")

                # Zapisz pojedynczą analizę
                _save_single_analysis(session, news_id, single_analysis, analysis_result.id)
                analysis_ids.append(analysis_result.id)

            session.commit()
            print(f"DEBUG: Commit wykonany pomyślnie - zapisano {len(analysis_ids)} analiz")
            return analysis_ids  # Zwróć listę ID
        else:
            print(f"DEBUG: Wykryto pojedynczą analizę")
            # To jest pojedyncza analiza
            analysis_result = AnalysisResult(
                news_id=news_id,
                summary=cleaned_json
            )
            session.add(analysis_result)
            session.flush()  # Aby uzyskać ID
            print(f"DEBUG: Utworzono AnalysisResult z ID={analysis_result.id}")

            # Zapisz pojedynczą analizę
            _save_single_analysis(session, news_id, analysis_data, analysis_result.id)

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


def cleanJson(analysis_json: str) -> str:
    cleaned_json = analysis_json.strip()
    if cleaned_json.startswith('```'):
        # Znajdź początek i koniec bloku JSON
        lines = cleaned_json.split('\n')
        cleaned_json = '\n'.join(lines[1:-1]) if len(lines) > 2 else cleaned_json
    return cleaned_json


def analyze_articles(db: Database, mode: str = 'unanalyzed', article_id: int = None,
                     relevance_threshold: float = 0.50, telegram=None):
    """
    Główna funkcja do analizy artykułów z wstępną filtracją istotności.

    Args:
        db: Instancja Database
        mode: 'id' (dla konkretnego ID) lub 'unanalyzed' (dla nieprzeanalizowanych)
        article_id: ID artykułu (wymagane gdy mode='id')
        relevance_threshold: Próg istotności dla embeddings (0-1)

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
            return {"status": "error",
                    "message": f"Nie znaleziono artykułu o ID={article_id}"}
    elif mode == 'unanalyzed':
        print("Szukam nieprzeanalizowanych artykułów...")
        articles = get_unanalyzed_articles(db)
        print(f"Znaleziono {len(articles)} nieprzeanalizowanych artykułów")
    else:
        raise ValueError(f"Nieprawidłowy tryb: {mode}. Użyj 'id' lub 'unanalyzed'")

    if not articles:
        print("Brak artykułów do analizy")
        return {"status": "success", "message": "Brak artykułów do analizy",
                "not_relevant" : 0,
                "analyzed": 0}

    results = []
    analysis_json = None
    for article in articles:
        try:
            print(f"\n=== Przetwarzam artykuł ID={article.id}: {article.title[:50]}...")

            # Sprawdź czy artykuł już został przeanalizowany
            if is_article_analyzed(db, article.id):
                print(
                    f"⊘ Artykuł ID={article.id} został już wcześniej przeanalizowany - pomijam")
                results.append({
                    "article_id": article.id,
                    "title": article.title,
                    "status": "skipped",
                    "reason": "already_analyzed"
                })
                continue

            # NOWE: Wstępna analiza istotności
            print(f"[1/3] Sprawdzam istotność newsa...")

            # Sprawdź czy news zawiera negatywne słowa kluczowe
            has_negative, negative_keyword = contains_pattern(NEGATIVE_KEYWORDS, article.title, article.content or "")
            if has_negative:
                reason = f"Zawiera negatywne słowo kluczowe: '{negative_keyword}'"
                print(f"    ✗ Wykluczony: {reason}")
                save_not_analyzed(db, article.id, reason, 0.0)
                results.append({
                    "article_id": article.id,
                    "title": article.title,
                    "status": "skipped",
                    "reason": "negative_keyword",
                    "relevance_score": 0.0,
                    "details": reason
                })
                continue
            has_summary, summary_keyword = contains_pattern(NEWS_SUMMARY_PATTERN,
                                                              article.title,
                                                              article.content or "")
            if not has_summary:
                is_relevant, relevance_score, relevance_reason = is_news_relevant(
                    article.title,
                    article.content or "",
                    threshold=relevance_threshold
                )
            else:
                is_relevant, relevance_score, relevance_reason = True, 1, "Podsumowanie dnia"

            print(
                f"    Istotność: {'TAK' if is_relevant else 'NIE'} (score: {relevance_score:.3f})")
            print(f"    Powód: {relevance_reason}")

            if not is_relevant:
                # Zapisz do news_not_analyzed
                save_not_analyzed(db, article.id, relevance_reason, relevance_score)
                results.append({
                    "article_id": article.id,
                    "title": article.title,
                    "status": "skipped",
                    "reason": "not_relevant",
                    "relevance_score": relevance_score,
                    "details": relevance_reason
                })
                continue

            # Analizuj artykuł (tylko jeśli jest istotny)
            print(f"[2/3] Wysyłam zapytanie do OpenAI...")
            if has_summary:
                analysis_json = analyze_summary(article.title, article.content or "")
                analysis_datas = json.loads(cleanJson(analysis_json))
                for analysis_data in analysis_datas:
                    tickers = analysis_data.get('related_tickers', [])
                    ticker_impact = analysis_data.get('ticker_impact')
                    sector = analysis_data.get('sector')
                    sector_impact = analysis_data.get('sector_impact')
                    if tickers and ticker_impact and ticker_impact != 0:
                        telegram.send_analysis_alert(ticker=','.join(tickers),
                                                     title=article.title,
                                                     reason=analysis_data.get('reason'),
                                                     impact=ticker_impact,
                                                     confidence=analysis_data.get(
                                                         'confidence')
                                                     )
                    elif sector and sector_impact:
                        telegram.send_sector_alert(sector=sector,
                                                   title=article.title,
                                                   reason=analysis_data.get('reason'),
                                                   impact=sector_impact,
                                                   confidence=analysis_data.get(
                                                       'confidence')
                                                   )

            else:
                analysis_json = analyze_news(article.title, article.content or "")
                analysis_data = json.loads(cleanJson(analysis_json))
                tickers = analysis_data.get('related_tickers', [])
                sector_impact = analysis_data.get('sector_impact')
                sector = analysis_data.get('sector')
                if tickers:
                    telegram.send_analysis_alert(ticker=','.join(tickers),
                                                 title=article.title,
                                                 reason=analysis_data.get('reason'),
                                                 impact=analysis_data.get('ticker_impact'),
                                                 confidence=analysis_data.get('confidence')
                                                 )
                elif sector:
                    telegram.send_sector_alert(sector=sector,
                                                 title=article.title,
                                                 reason=analysis_data.get('reason'),
                                                 impact=sector_impact,
                                                 confidence=analysis_data.get('confidence')
                                                 )
            print(f"    Otrzymano odpowiedź: {analysis_json[:100]}...")

            # Zapisz wyniki
            print(f"[3/3] Zapisuję wyniki do bazy danych...")

            analysis_id = save_analysis_results(db, article.id, analysis_json)
            print(f"✓ Pomyślnie zapisano analizę (analysis_id={analysis_id})")

            results.append({
                "article_id": article.id,
                "analysis_id": analysis_id,
                "title": article.title,
                "status": "success",
                "relevance_score": relevance_score
            })
        except Exception as e:
            print(f"✗ BŁĄD podczas analizy artykułu ID={article.id}, json={analysis_json}: {str(e)}")
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
    not_relevant_count = sum(1 for r in results if r.get('reason') == 'not_relevant')
    error_count = sum(1 for r in results if r['status'] == 'error')

    print(f"\n{'=' * 60}")
    print(f"PODSUMOWANIE:")
    print(f"  Przeanalizowane:     {success_count}")
    print(f"  Pominięte (już były): {skipped_count - not_relevant_count}")
    print(f"  Odrzucone (nieistotne): {not_relevant_count}")
    print(f"  Błędy:               {error_count}")
    print(f"{'=' * 60}\n")

    return {
        "status": "completed",
        "analyzed": success_count,
        "skipped": skipped_count - not_relevant_count,
        "not_relevant": not_relevant_count,
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
                    confidence_value = sentiment.confidence if sentiment.confidence is not None else 1.0

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
                    confidence_value = sentiment.confidence if sentiment.confidence is not None else 1.0
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
            #print(result)
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

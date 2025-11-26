"""
Moduł do normalizacji tickerów i zapobiegania duplikatom
"""
from sqlalchemy import create_engine, text
from difflib import SequenceMatcher
import os
import json

def get_db_engine():
    db_url = "postgresql:///?service=stock"
    engine = create_engine(db_url)
    schema = os.getenv('DB_SCHEMA', 'stock')
    return engine, schema

engine, schema = get_db_engine()

# Statyczna mapa najczęstszych błędów (backup)
TICKER_ALIASES = {
    'SYN': 'SNT',
    'KGH': 'KGHM',
    'CDP': 'CDR',
    'CD': 'CDR',
    'OPL': 'OPL',  # Orange Polska - czasem skracane
    'PKO': 'PKO',  # PKO BP - czasem bez BP
}

class TickerNormalizer:
    def __init__(self):
        self.company_to_ticker = {}  # Inicjalizuj przed _load_valid_tickers
        self.valid_tickers = self._load_valid_tickers()
        self.aliases = self._load_aliases()

    def _load_valid_tickers(self):
        """Załaduj listę wszystkich poprawnych tickerów z bazy"""
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT ticker, company_name 
                FROM {schema}.tickers
                WHERE ticker IS NOT NULL
                ORDER BY ticker
            """))
            tickers = {}

            for row in result:
                ticker = row[0]
                company = row[1]
                tickers[ticker] = company

                if company:
                    # Normalizuj nazwę (uppercase, bez znaków diakrytycznych)
                    normalized_name = self._normalize_company_name(company)
                    self.company_to_ticker[normalized_name] = ticker

                    # Dodaj również oryginał uppercase
                    self.company_to_ticker[company.upper()] = ticker

                    # Dodaj wersję bez "S.A." / "SA"
                    company_without_sa = company.upper().replace(' S.A.', '').replace(' SA', '').strip()
                    if company_without_sa != company.upper():
                        self.company_to_ticker[company_without_sa] = ticker

            print(f"✓ Załadowano {len(tickers)} tickerów i {len(self.company_to_ticker)} mapowań nazw")

            return tickers

    def _normalize_company_name(self, name: str) -> str:
        """Normalizuje nazwę firmy (usuwa znaki diakrytyczne, etc)"""
        if not name:
            return ""

        # Mapa polskich znaków
        replacements = {
            'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N',
            'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z',
            'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
            'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z'
        }

        result = name.upper()
        for old, new in replacements.items():
            result = result.replace(old, new)

        # Usuń SA, S.A., Spółka Akcyjna, etc.
        result = result.replace(' S.A.', '').replace(' SA', '').replace(' S.A', '')
        result = result.replace(' SPOLKA AKCYJNA', '').replace(' SPÓŁKA AKCYJNA', '')

        return result.strip()

    def _load_aliases(self):
        """Załaduj mapę aliasów z bazy (jeśli istnieje)"""
        try:
            with engine.connect() as conn:
                result = conn.execute(text(f"""
                    SELECT alias, canonical_ticker 
                    FROM {schema}.ticker_aliases
                """))
                return {row[0]: row[1] for row in result}
        except:
            # Tabela może nie istnieć - użyj statycznej mapy
            return TICKER_ALIASES

    def normalize(self, ticker: str, auto_add_alias=True) -> tuple[str, str]:
        """
        Normalizuje ticker do kanonicznej formy

        Args:
            ticker: Ticker lub nazwa firmy do znormalizowania
            auto_add_alias: Czy automatycznie dodać alias do bazy

        Returns:
            tuple: (znormalizowany_ticker, powód_zmiany lub None)
        """
        if not ticker:
            return ticker, None

        original_ticker = ticker
        ticker = ticker.strip().upper()

        # 1. NAJPIERW sprawdź aliasy (przed valid_tickers!)
        if ticker in self.aliases:
            canonical = self.aliases[ticker]
            return canonical, f"alias: {ticker} -> {canonical}"

        # 2. Sprawdź czy ticker już jest poprawny (krótki ticker <= 6 znaków)
        if ticker in self.valid_tickers and len(ticker) <= 6:
            return ticker, None

        # 3. Sprawdź czy to nazwa firmy
        # 3a. Bezpośrednie dopasowanie w company_to_ticker
        if ticker in self.company_to_ticker:
            canonical = self.company_to_ticker[ticker]
            if auto_add_alias and ticker not in self.aliases and len(ticker) > 6:
                self.add_alias(ticker, canonical, silent=True)
            return canonical, f"company name: '{original_ticker}' -> {canonical}"

        # 3b. Dopasowanie znormalizowanej nazwy (bez polskich znaków)
        normalized_name = self._normalize_company_name(ticker)
        if normalized_name != ticker and normalized_name in self.company_to_ticker:
            canonical = self.company_to_ticker[normalized_name]
            if auto_add_alias and ticker not in self.aliases and len(ticker) > 6:
                self.add_alias(ticker, canonical, silent=True)
            return canonical, f"company name normalized: '{original_ticker}' -> {canonical}"

        # 3c. Fuzzy match po nazwach firm (dla długich stringów)
        if len(ticker) > 6:
            best_match = self._fuzzy_match_company(ticker)
            if best_match:
                if auto_add_alias and ticker not in self.aliases:
                    self.add_alias(ticker, best_match, silent=True)
                return best_match, f"fuzzy company match: '{original_ticker}' -> {best_match}"

        # 4. Fuzzy matching - znajdź najbardziej podobny ticker (dla krótkich stringów)
        best_match = None
        best_similarity = 0

        for valid_ticker in self.valid_tickers:
            # Pomiń długie tickery (prawdopodobnie błędne)
            if len(valid_ticker) > 6:
                continue

            similarity = SequenceMatcher(None, ticker, valid_ticker).ratio()

            # Dodatkowe punkty jeśli ticker jest prefiksem
            if valid_ticker.startswith(ticker) or ticker.startswith(valid_ticker):
                similarity += 0.2

            if similarity > best_similarity and similarity > 0.7:
                best_similarity = similarity
                best_match = valid_ticker

        if best_match and best_similarity > 0.8:
            if auto_add_alias and ticker not in self.aliases:
                self.add_alias(ticker, best_match, silent=True)
            return best_match, f"fuzzy ticker match: {ticker} -> {best_match} (similarity: {best_similarity:.2f})"

        # 5. Nie znaleziono - zwróć oryginalny (może to nowy ticker)
        return ticker, f"warning: nieznany ticker '{ticker}'"

    def _fuzzy_match_company(self, company_name: str) -> str:
        """Fuzzy matching dla nazw firm"""
        normalized = self._normalize_company_name(company_name)
        best_match = None
        best_similarity = 0

        for company_key, ticker in self.company_to_ticker.items():
            similarity = SequenceMatcher(None, normalized, company_key).ratio()

            # Bonus za zawieranie
            if normalized in company_key or company_key in normalized:
                similarity += 0.15

            if similarity > best_similarity and similarity > 0.75:
                best_similarity = similarity
                best_match = ticker

        return best_match if best_similarity > 0.8 else None

    def get_prompt_context(self) -> str:
        """Generuje kontekst dla AI z listą poprawnych tickerów"""
        ticker_list = []

        # Grupuj po sektorach jeśli są dostępne
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT ticker, company_name, sector
                FROM {schema}.tickers
                WHERE ticker IS NOT NULL
                ORDER BY 
                    CASE WHEN in_portfolio = 1 THEN 0 ELSE 1 END,
                    sector NULLS LAST,
                    ticker
            """))

            current_sector = None
            for row in result:
                ticker, company, sector = row[0], row[1], row[2]

                # Nagłówek sektora
                if sector and sector != current_sector:
                    ticker_list.append(f"\n{sector}:")
                    current_sector = sector

                ticker_list.append(f"  • {ticker} - {company or 'brak nazwy'}")

        return """
KRYTYCZNE: WALIDACJA TICKERÓW
================================
Używaj WYŁĄCZNIE tickerów z poniższej listy. Nie wymyślaj skrótów ani wariantów!

POPRAWNE TICKERY Z GPW:
{}

CZĘSTE BŁĘDY DO UNIKANIA:
• KGHM (✓) NIE: KGH, KGHM.PL
• SNT (✓) NIE: SYN, SYNEKTIK  
• CDR (✓) NIE: CDP, CD, CDPROJEKT
• OPL (✓) NIE: ORANGE
• PKO (✓) NIE: PKOBP

Jeśli nie jesteś pewien tickera - użyj pełnej nazwy firmy, a system go znormalizuje.
""".format("\n".join(ticker_list))

    def add_alias(self, alias: str, canonical: str, silent=False):
        """Dodaje nowy alias do bazy"""
        with engine.connect() as conn:
            try:
                conn.execute(text(f"""
                    INSERT INTO {schema}.ticker_aliases (alias, canonical_ticker)
                    VALUES (:alias, :canonical)
                    ON CONFLICT (alias) DO UPDATE 
                    SET canonical_ticker = :canonical
                """), {'alias': alias, 'canonical': canonical})
                conn.commit()
                self.aliases[alias] = canonical
                if not silent:
                    print(f"✓ Dodano alias: {alias} -> {canonical}")
            except Exception as e:
                if not silent:
                    print(f"✗ Błąd dodawania aliasu: {e}")

# Singleton
_normalizer = None

def get_normalizer() -> TickerNormalizer:
    """Zwraca singleton normalizera"""
    global _normalizer
    if _normalizer is None:
        _normalizer = TickerNormalizer()
    return _normalizer


# ===== SKRYPT DO CZYSZCZENIA BŁĘDNYCH TICKERÓW =====

def clean_invalid_tickers():
    """Znajduje i naprawia błędne tickery (długie nazwy firm zapisane jako tickery)"""
    print("🔍 Szukam błędnych tickerów (długich nazw firm)...")

    with engine.connect() as conn:
        # Znajdź wszystkie tickery dłuższe niż 6 znaków (prawdopodobnie nazwy firm)
        result = conn.execute(text(f"""
            SELECT DISTINCT ticker 
            FROM {schema}.tickers
            WHERE LENGTH(ticker) > 6
            ORDER BY ticker
        """))

        invalid_tickers = [row[0] for row in result]

        if not invalid_tickers:
            print("✓ Nie znaleziono błędnych tickerów!")
            return

        print(f"Znaleziono {len(invalid_tickers)} podejrzanych tickerów:")

        # Mapuj każdy błędny ticker do poprawnego
        mappings = []
        for invalid in invalid_tickers:
            # Spróbuj znaleźć prawdziwy ticker
            # Szukaj w ticker_sentiment - jakie KRÓTKIE tickery są używane dla podobnych newsów?
            search_result = conn.execute(text(f"""
                SELECT DISTINCT ts2.ticker, COUNT(*) as cnt
                FROM {schema}.ticker_sentiment ts1
                JOIN {schema}.analysis_result ar ON ts1.analysis_id = ar.id
                JOIN {schema}.ticker_sentiment ts2 ON ts2.analysis_id = ar.id
                WHERE ts1.ticker = :invalid
                  AND LENGTH(ts2.ticker) <= 6
                  AND ts2.ticker != ts1.ticker
                GROUP BY ts2.ticker
                ORDER BY cnt DESC
                LIMIT 1
            """), {'invalid': invalid})

            row = search_result.fetchone()
            if row:
                correct_ticker = row[0]
                mappings.append((invalid, correct_ticker))
                print(f"  {invalid:30} -> {correct_ticker}")
            else:
                print(f"  {invalid:30} -> ??? (nie znaleziono kandydata)")

        if not mappings:
            print("\n⚠️  Nie można automatycznie zmapować tickerów")
            return

        # Zapytaj o potwierdzenie
        print(f"\n❓ Czy zastosować {len(mappings)} poprawek? (tak/nie): ", end='')
        confirm = input().lower()

        if confirm not in ['tak', 't', 'yes', 'y']:
            print("❌ Anulowano")
            return

        # Wykonaj poprawki
        for invalid, correct in mappings:
            try:
                # 1. Przenieś dane z ticker_sentiment
                conn.execute(text(f"""
                    UPDATE {schema}.ticker_sentiment
                    SET ticker = :correct
                    WHERE ticker = :invalid
                """), {'correct': correct, 'invalid': invalid})

                # 2. Dodaj alias
                conn.execute(text(f"""
                    INSERT INTO {schema}.ticker_aliases (alias, canonical_ticker)
                    VALUES (:invalid, :correct)
                    ON CONFLICT (alias) DO UPDATE SET canonical_ticker = :correct
                """), {'invalid': invalid, 'correct': correct})

                # 3. Usuń błędny ticker z tickers
                conn.execute(text(f"""
                    DELETE FROM {schema}.tickers
                    WHERE ticker = :invalid
                """), {'invalid': invalid})

                print(f"  ✓ {invalid} -> {correct}")

            except Exception as e:
                print(f"  ✗ {invalid} -> {correct}: {e}")

        conn.commit()
        print("\n✅ Czyszczenie zakończone!")

def fill_missing_company_names():
    """Pobiera brakujące nazwy firm z Yahoo Finance"""
    import yfinance as yf

    print("🔍 Szukam tickerów bez nazw firm...")

    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT ticker 
            FROM {schema}.tickers
            WHERE company_name IS NULL OR company_name = ''
            ORDER BY ticker
        """))

        tickers_without_names = [row[0] for row in result]

        if not tickers_without_names:
            print("✓ Wszystkie tickery mają nazwy!")
            return

        print(f"Znaleziono {len(tickers_without_names)} tickerów bez nazw")

        for ticker in tickers_without_names:
            try:
                # Dodaj .WA dla tickerów z GPW
                yf_symbol = f"{ticker}.WA" if len(ticker) <= 4 else ticker
                yf_ticker = yf.Ticker(yf_symbol)
                info = yf_ticker.info

                company_name = (
                    info.get('longName') or
                    info.get('shortName') or
                    info.get('name')
                )

                if company_name:
                    conn.execute(text(f"""
                        UPDATE {schema}.tickers
                        SET company_name = :name
                        WHERE ticker = :ticker
                    """), {'name': company_name, 'ticker': ticker})
                    print(f"  ✓ {ticker:6} -> {company_name}")
                else:
                    print(f"  ✗ {ticker:6} -> Nie znaleziono nazwy")

            except Exception as e:
                print(f"  ✗ {ticker:6} -> Błąd: {e}")

        conn.commit()
        print("\n✅ Uzupełnianie nazw zakończone!")

def migrate_summary_tickers(dry_run=True):
    """
    Normalizuje tickery w polu `related_tickers` w `analysis_result.summary`
    """
    normalizer = get_normalizer()
    print("\n🔍 Szukam tickerów do normalizacji w `analysis_result.summary`...")

    with engine.connect() as conn:
        # Użyj jsonb_path_exists dla wydajności
        # Użyj standardowych operatorów JSON zamiast jsonb_path_exists, aby uniknąć problemów ze składnią
        result = conn.execute(text(f"""
            SELECT id, summary
            FROM {schema}.analysis_result
            WHERE summary IS NOT NULL 
              AND TRIM(summary) LIKE '{{%'
              AND (summary::jsonb) ? 'related_tickers'
              AND jsonb_typeof(summary::jsonb -> 'related_tickers') = 'array'
              AND jsonb_array_length(summary::jsonb -> 'related_tickers') > 0
        """))

        updates_to_perform = []
        for id, summary_str in result:
            try:
                summary = json.loads(summary_str)
                if not isinstance(summary, dict) or 'related_tickers' not in summary or not summary['related_tickers']:
                    continue
            except json.JSONDecodeError:
                continue  # Pomiń nieprawidłowy JSON

            original_tickers = summary.get('related_tickers', [])
            normalized_tickers = []
            changed = False

            for ticker in original_tickers:
                # Użyj auto_add_alias=True, aby upewnić się, że nowe aliasy są rozpoznawane
                normalized, reason = normalizer.normalize(ticker, auto_add_alias=True)
                normalized_tickers.append(normalized)
                if normalized != ticker:
                    changed = True
                    print(f"  (ID: {id}) {ticker} -> {normalized} ({reason})")

            if changed:
                new_summary = summary.copy()
                new_summary['related_tickers'] = normalized_tickers
                updates_to_perform.append({'id': id, 'summary': new_summary})

        if not updates_to_perform:
            print("✓ Nie znaleziono tickerów do aktualizacji w `summary`!")
            return

        print(f"\n📊 Znaleziono {len(updates_to_perform)} rekordów `analysis_result` do aktualizacji.")

        if dry_run:
            print("\n⚠️  DRY RUN - żadne zmiany nie zostały zapisane w `analysis_result`")
            return

        print("\n🔧 Aktualizuję `analysis_result.summary`...")
        for update in updates_to_perform:
            # Serializuj słownik z powrotem do JSON string przed zapisem
            summary_json_str = json.dumps(update['summary'], ensure_ascii=False)
            conn.execute(text(f"""
                UPDATE {schema}.analysis_result
                SET summary = :summary
                WHERE id = :id
            """), {'summary': summary_json_str, 'id': update['id']})
            print(f"  ✓ Zaktualizowano ID: {update['id']}")
        
        conn.commit()
        print("✅ Aktualizacja `summary` zakończona!")


def migrate_duplicate_tickers(dry_run=True):
    """
    Znajduje i łączy duplikaty tickerów w bazie (w ticker_sentiment)

    Args:
        dry_run: Jeśli True, tylko pokazuje co by się stało
    """
    normalizer = get_normalizer()

    print("🔍 Szukam duplikatów tickerów...")

    with engine.connect() as conn:
        # Znajdź wszystkie używane tickery
        result = conn.execute(text(f"""
            SELECT DISTINCT ticker 
            FROM {schema}.ticker_sentiment
            WHERE ticker IS NOT NULL
            ORDER BY ticker
        """))

        used_tickers = [row[0] for row in result]

        duplicates = {}
        for ticker in used_tickers:
            normalized, reason = normalizer.normalize(ticker)

            if reason and normalized != ticker:
                if normalized not in duplicates:
                    duplicates[normalized] = []
                duplicates[normalized].append(ticker)
                print(f"  ⚠️  {ticker} -> {normalized} ({reason})")

        if not duplicates:
            print("✓ Nie znaleziono duplikatów!")
            return

        print(f"\n📊 Znaleziono {len(duplicates)} grup duplikatów:")
        for canonical, aliases in duplicates.items():
            print(f"  {canonical}: {', '.join(aliases)}")

        if dry_run:
            print("\n⚠️  DRY RUN - żadne zmiany nie zostały zapisane")
            print("Uruchom ponownie z dry_run=False aby zastosować zmiany")
            return

        # Aktualizuj tickery
        print("\n🔧 Aktualizuję tickery...")
        for canonical, aliases in duplicates.items():
            for alias in aliases:
                # Aktualizuj ticker_sentiment
                conn.execute(text(f"""
                    UPDATE {schema}.ticker_sentiment
                    SET ticker = :canonical
                    WHERE ticker = :alias
                """), {'canonical': canonical, 'alias': alias})

                # Dodaj do aliases
                normalizer.add_alias(alias, canonical)

                print(f"  ✓ {alias} -> {canonical}")

        conn.commit()
        print("\n✅ Migracja `ticker_sentiment` zakończona!")


if __name__ == '__main__':
    import sys

    # Obsługa argumentów wiersza poleceń
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == 'clean':
            clean_invalid_tickers()
            sys.exit(0)
        elif command == 'fill-names':
            fill_missing_company_names()
            sys.exit(0)
        elif command == 'migrate':
            dry_run = '--dry-run' in sys.argv or '-n' in sys.argv
            migrate_duplicate_tickers(dry_run=dry_run)
            migrate_summary_tickers(dry_run=dry_run)
            sys.exit(0)
        elif command == 'help':
            print("""
Użycie: python ticker_normalization.py [command]

Dostępne komendy:
  clean         - Usuń błędne tickery (długie nazwy firm) i przenieś dane
  fill-names    - Uzupełnij brakujące nazwy firm z Yahoo Finance
  migrate       - Migruj duplikaty tickerów (użyj --dry-run dla testu)
  help          - Pokaż tę pomoc
  (brak)        - Uruchom testy
            """)
            sys.exit(0)

    # Test
    normalizer = get_normalizer()

    print("=== DEBUG: Przykładowe mapowania ===\n")
    print(f"Załadowano {len(normalizer.valid_tickers)} tickerów i {len(normalizer.company_to_ticker)} mapowań nazw")
    print("\nPierwsze 10 mapowań company_to_ticker:")
    for i, (name, ticker) in enumerate(list(normalizer.company_to_ticker.items())[:10]):
        print(f"  '{name}' -> {ticker}")

    # Sprawdź konkretne przypadki
    print("\n=== DEBUG: Sprawdzanie konkretnych nazw ===")
    test_names = ['ŚNIEŻKA', 'SNIEZKA', 'CD PROJEKT', 'KGHM POLSKA MIEDŹ']
    for name in test_names:
        normalized = normalizer._normalize_company_name(name)
        in_map = name in normalizer.company_to_ticker
        in_map_normalized = normalized in normalizer.company_to_ticker
        print(f"  '{name}':")
        print(f"    normalized: '{normalized}'")
        print(f"    in map (original): {in_map}")
        print(f"    in map (normalized): {in_map_normalized}")
        if in_map:
            print(f"    -> {normalizer.company_to_ticker[name]}")
        if in_map_normalized:
            print(f"    -> {normalizer.company_to_ticker[normalized]}")

    print("\n=== TEST NORMALIZACJI ===\n")

    test_cases = [
        'KGHM',  # poprawny
        'KGH',   # alias
        'SYN',   # alias
        'SNT',   # poprawny
        'CDP',   # alias
        'CDPROJ',  # fuzzy match
        'ŚNIEŻKA',  # nazwa firmy z polskimi znakami
        'SNIEZKA',  # nazwa firmy bez polskich znaków
        'Śnieżka S.A.',  # pełna nazwa
        'CD Projekt',  # nazwa firmy
        'KGHM Polska Miedź',  # pełna nazwa
        'XYZ',   # nieznany
    ]

    for test in test_cases:
        normalized, reason = normalizer.normalize(test)
        status = "✓" if not reason else ("⚠️" if "warning" in reason else "→")
        print(f"{status} {test:25} => {normalized:10} | {reason or 'OK'}")

    print("\n=== PODPOWIEDZI ===")
    print("1. python ticker_normalization.py clean")
    print("   → Usuń błędne tickery (długie nazwy firm)")
    print("2. python ticker_normalization.py fill-names")
    print("   → Uzupełnij brakujące nazwy firm z Yahoo Finance")
    print("3. python ticker_normalization.py migrate --dry-run")
    print("   → Zobacz duplikaty do migracji")

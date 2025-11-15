"""News scraping and analysis service with scheduled tasks."""

import os
import time
import schedule
import logging
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

from config import Config
from database import Database
from scraper import Scraper
from providers.pap_provider import PAPProvider
from providers.strefa_investorow_provider import StrefaInwestorowProvider
from providers.rekomendacje_provider import RekomendacjeProvider
from ai_analist import analyze_articles, generate_report
from notifications import TelegramNotifier

# Konfiguracja logowania
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler('service.log', encoding='utf-8')
stream_handler = logging.StreamHandler()
stream_handler.setStream(open(1, 'w', encoding='utf-8', closefd=False))  # stdout with utf-8 encoding

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)

# Załaduj zmienne środowiskowe
load_dotenv()


class NewsScrapingService:
    """Serwis do automatycznego scrapowania i analizy newsów."""

    def __init__(self):
        """Inicjalizacja serwisu."""
        self.config = Config()
        self.db = Database(self.config.db_path)
        self.telegram = TelegramNotifier(
            token=os.getenv('TELEGRAM_BOT_TOKEN'),
            chat_id=os.getenv('TELEGRAM_CHAT_ID')
        )

        # Interwały czasowe (w minutach) z .env
        self.scrape_si_interval = int(os.getenv('SCRAPE_SI_INTERVAL', '30'))
        self.scrape_sir_interval = int(os.getenv('SCRAPE_SIR_INTERVAL', '30'))
        self.analyze_interval = int(os.getenv('ANALYZE_INTERVAL', '35'))
        self.report_interval = int(os.getenv('REPORT_INTERVAL', '1440'))  # 24h
        self.patterns_refresh_interval = int(
            os.getenv('PATTERNS_REFRESH_INTERVAL', '1440'))  # 24h

        # Liczba stron do scrapowania
        self.si_pages_from = int(os.getenv('SI_PAGES_FROM', '0'))
        self.si_pages_to = int(os.getenv('SI_PAGES_TO', '4'))

        logger.info("=" * 80)
        logger.info("NEWS SCRAPING SERVICE - INICJALIZACJA")
        logger.info("=" * 80)
        logger.info(f"Baza danych: {self.config.db_path}")
        logger.info(f"Interwał SI (news): {self.scrape_si_interval} min")
        logger.info(f"Interwał SIR (rekomendacje): {self.scrape_sir_interval} min")
        logger.info(f"Interwał analizy AI: {self.analyze_interval} min")
        logger.info(f"Interwał raportu: {self.report_interval} min")
        logger.info(
            f"Interwał odświeżania wzorców: {self.patterns_refresh_interval} min")
        logger.info(f"Zakres stron SI: {self.si_pages_from}-{self.si_pages_to}")
        logger.info("=" * 80)

    def scrape_si_news(self):
        """Scrapowanie newsów ze Strefa Inwestorów (tryb SI)."""
        try:
            logger.info("🔄 Rozpoczynam scrapowanie newsów (SI)...")
            start_time = datetime.now()

            provider = StrefaInwestorowProvider()
            scraper = Scraper(self.db, self.telegram)

            stats = scraper.scrape_provider(
                provider,
                self.si_pages_from,
                self.si_pages_to
            )

            duration = (datetime.now() - start_time).total_seconds()

            message = (
                f"✅ *Scrapowanie newsów zakończone*\n\n"
                f"📊 Statystyki:\n"
                f"• Sprawdzono: {stats['total_checked']}\n"
                f"• Nowe artykuły: {stats['new_articles']}\n"
                f"• Pominięte: {stats['skipped_articles']}\n"
                f"• Czas: {duration:.1f}s"
            )

            logger.info(message.replace('*', '').replace('•', '-'))

            # Wyślij powiadomienie jeśli są nowe artykuły
            if stats['new_articles'] > 0:
                self.telegram.send_message(message)

        except Exception as e:
            error_msg = f"❌ Błąd podczas scrapowania SI: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.telegram.send_message(error_msg)

    def scrape_sir_recommendations(self):
        """Scrapowanie rekomendacji (tryb SIR)."""
        try:
            logger.info("🔄 Rozpoczynam scrapowanie rekomendacji (SIR)...")
            start_time = datetime.now()

            provider = RekomendacjeProvider()
            scraper = Scraper(self.db, self.telegram)

            stats = scraper.scrape_recommendations(provider)

            duration = (datetime.now() - start_time).total_seconds()

            message = (
                f"✅ *Scrapowanie rekomendacji zakończone*\n\n"
                f"📊 Statystyki:\n"
                f"• Wszystkich: {stats['total_recommendations']}\n"
                f"• Nowych: {stats['new_recommendations']}\n"
                f"• Pominiętych: {stats['skipped_recommendations']}\n"
                f"• Czas: {duration:.1f}s"
            )

            logger.info(message.replace('*', '').replace('•', '-'))

            # Wyślij powiadomienie jeśli są nowe rekomendacje
            if stats['new_recommendations'] > 0:
                self.telegram.send_message(message)

        except Exception as e:
            error_msg = f"❌ Błąd podczas scrapowania SIR: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.telegram.send_message(error_msg)

    def analyze_unanalyzed(self):
        """Analiza nieprzeanalizowanych artykułów za pomocą AI."""
        try:
            logger.info("🤖 Rozpoczynam analizę AI nieprzeanalizowanych artykułów...")
            start_time = datetime.now()

            result = analyze_articles(self.db, mode='unanalyzed', telegram=self.telegram)

            duration = (datetime.now() - start_time).total_seconds()

            if result['analyzed'] > 0 or result['not_relevant'] > 0:
                message = (
                    f"🤖 *Analiza AI zakończona*\n\n"
                    f"📊 Statystyki:\n"
                    f"• Przeanalizowane: {result['analyzed']}\n"
                    f"• Odrzucone (nieistotne): {result['not_relevant']}\n"
                    f"• Pominięte: {result['skipped']}\n"
                    f"• Błędy: {result['errors']}\n"
                    f"• Czas: {duration:.1f}s"
                )

                logger.info(message.replace('*', '').replace('•', '-'))

                # Wyślij powiadomienie o analizie
                if result['analyzed'] > 0:
                    self.telegram.send_message(message)

                    # TODO: Tu dodaj szczegółowe powiadomienia o konkretnych analizach
                    # Możesz wysłać informacje o najważniejszych newsach,
                    # silnych sygnałach dla tickerów itp.
                    self._send_analysis_highlights(result)
            else:
                logger.info("Brak nowych artykułów do analizy")

        except Exception as e:
            error_msg = f"❌ Błąd podczas analizy AI: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.telegram.send_message(error_msg)

    def _send_analysis_highlights(self, result):
        """
        Wysyła powiadomienia o najważniejszych analizach.

        Args:
            result: Wynik z analyze_articles
        """
        # TODO: Implementacja szczegółowych powiadomień
        # Przykład logiki:
        # 1. Przejrzyj result['results']
        # 2. Znajdź analizy z wysokim impact (>0.7 lub <-0.7)
        # 3. Wyślij osobne powiadomienie dla każdej ważnej analizy
        # 4. Możesz też grupować po tickerach lub sektorach

        try:
            highlights = []
            for item in result.get('results', []):
                if item['status'] == 'success':
                    # Tu możesz dodać logikę wyciągania najważniejszych informacji
                    # z bazy danych na podstawie analysis_id
                    pass

            # Przykład:
            # if highlights:
            #     message = "🎯 *Najważniejsze sygnały:*\n\n" + "\n".join(highlights)
            #     self.telegram.send_message(message)

        except Exception as e:
            logger.error(f"Błąd podczas wysyłania highlights: {e}")

    def generate_daily_report(self):
        """Generowanie dziennego raportu trendów."""
        try:
            logger.info("📊 Generuję dzienny raport...")
            start_time = datetime.now()

            report = generate_report(self.db)

            duration = (datetime.now() - start_time).total_seconds()

            # Przygotuj wiadomość z top wynikami
            message = f"📊 *Dzienny raport trendów*\n\n"

            # Top 5 sektorów
            if report['sectors']:
                message += "🏭 *Top sektory:*\n"
                for sector in report['sectors'][:5]:
                    emoji = "📈" if sector['trend_score'] > 0 else "📉"
                    message += (
                        f"{emoji} {sector['sector']}: "
                        f"{sector['trend_score']:+.2f} ({sector['count']} newsów)\n"
                    )
                message += "\n"

            # Top 10 tickerów
            if report['tickers']:
                message += "📈 *Top spółki:*\n"
                for ticker in report['tickers'][:10]:
                    emoji = "🟢" if ticker['trend_score'] > 0 else "🔴"
                    message += (
                        f"{emoji} {ticker['ticker']}: "
                        f"{ticker['trend_score']:+.2f} ({ticker['count']} newsów)\n"
                    )

            message += f"\n⏱ Czas generowania: {duration:.1f}s"

            logger.info(message.replace('*', '').replace('•', '-'))
            self.telegram.send_message(message)

        except Exception as e:
            error_msg = f"❌ Błąd podczas generowania raportu: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.telegram.send_message(error_msg)

    def refresh_patterns(self):
        """Odświeża embeddingi wzorców z patterns.json."""
        try:
            logger.info("🔄 Odświeżam wzorce z patterns.json...")

            # Sprawdź czy plik istnieje
            patterns_file = Path('patterns.json')
            if not patterns_file.exists():
                logger.warning("Plik patterns.json nie istnieje")
                return

            # Wyczyść cache embeddings w module ai_analist
            import ai_analist
            if hasattr(ai_analist.is_news_relevant, '_relevant_cache'):
                delattr(ai_analist.is_news_relevant, '_relevant_cache')
            if hasattr(ai_analist.is_news_relevant, '_irrelevant_cache'):
                delattr(ai_analist.is_news_relevant, '_irrelevant_cache')

            # Przeładuj moduł (opcjonalnie)
            import importlib
            importlib.reload(ai_analist)

            logger.info("✅ Wzorce odświeżone pomyślnie")
            self.telegram.send_message(
                "🔄 *Wzorce odświeżone*\n\nEmbeddingi zostały przeładowane z patterns.json")

        except Exception as e:
            error_msg = f"❌ Błąd podczas odświeżania wzorców: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.telegram.send_message(error_msg)

    def setup_schedule(self):
        """Konfiguruje harmonogram zadań."""
        # Scrapowanie SI (news)
        schedule.every(self.scrape_si_interval).minutes.do(self.scrape_si_news)

        # Scrapowanie SIR (rekomendacje)
        schedule.every(self.scrape_sir_interval).minutes.do(
            self.scrape_sir_recommendations)

        # Analiza AI
        schedule.every(self.analyze_interval).minutes.do(self.analyze_unanalyzed)

        # Raport dzienny
        schedule.every(self.report_interval).minutes.do(self.generate_daily_report)

        # Odświeżanie wzorców
        schedule.every(self.patterns_refresh_interval).minutes.do(self.refresh_patterns)

        logger.info("✅ Harmonogram zadań skonfigurowany")

    def run(self):
        """Uruchamia serwis."""
        logger.info("🚀 Uruchamiam serwis...")

        # Wyślij powiadomienie o starcie
        self.telegram.send_message(
            "🚀 *News Scraping Service uruchomiony*\n\n"
            f"⚙️ Konfiguracja:\n"
            f"• SI: co {self.scrape_si_interval} min\n"
            f"• SIR: co {self.scrape_sir_interval} min\n"
            f"• AI: co {self.analyze_interval} min\n"
            f"• Raport: co {self.report_interval} min"
        )

        # Skonfiguruj harmonogram
        self.setup_schedule()

        # Wykonaj pierwsze zadania natychmiast
        logger.info("Wykonuję pierwsze zadania...")
        self.scrape_si_news()
        self.scrape_sir_recommendations()
        time.sleep(60)  # Poczekaj minutę przed analizą
        self.analyze_unanalyzed()

        # Główna pętla
        logger.info("✅ Serwis działa - oczekuję na zaplanowane zadania...")
        while True:
            try:
                schedule.run_pending()
                time.sleep(30)  # Sprawdzaj co 30 sekund
            except KeyboardInterrupt:
                logger.info("⛔ Otrzymano sygnał przerwania...")
                break
            except Exception as e:
                logger.error(f"❌ Błąd w głównej pętli: {e}", exc_info=True)
                time.sleep(60)  # Poczekaj minutę przed kolejną próbą

        # Cleanup
        logger.info("🛑 Zamykam serwis...")
        self.db.close()
        self.telegram.send_message("🛑 *News Scraping Service zatrzymany*")


def main():
    """Główna funkcja uruchamiająca serwis."""
    service = NewsScrapingService()
    service.run()


if __name__ == '__main__':
    main()

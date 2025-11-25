"""Main entry point for the news scraper application."""

import argparse
from datetime import datetime, date
from typing import List
from dotenv import load_dotenv

from config import Config
from database import Database
from scraper import Scraper
from providers.pap_provider import PAPProvider
from providers.strefa_investorow_provider import StrefaInwestorowProvider
from providers.rekomendacje_provider import RekomendacjeProvider
from providers.base_provider import BaseProvider
from actions import run_ticker_scraper


# Load environment variables
load_dotenv()


class ProviderFactory:
    """Factory for creating provider instances."""

    @staticmethod
    def create_provider(provider_name: str, base_url: str) -> BaseProvider:
        """
        Create a provider instance based on name.

        Args:
            provider_name: Name of the provider
            base_url: Base URL for the provider

        Returns:
            Provider instance
        """
        provider_name = provider_name.lower()

        if provider_name == 'pap':
            return PAPProvider(base_url)
        elif provider_name == 'strefa_inwestorow':
            return StrefaInwestorowProvider()
        elif provider_name == 'rekomendacje':
            return RekomendacjeProvider()
        else:
            raise ValueError(f"Unknown provider: {provider_name}")

    @staticmethod
    def create_providers(config: Config) -> List[BaseProvider]:
        """
        Create all configured providers.

        Args:
            config: Application configuration

        Returns:
            List of provider instances
        """
        providers = []

        for name, url in config.providers:
            try:
                provider = ProviderFactory.create_provider(name, url)
                providers.append(provider)
                print(f"Registered provider: {name}")
            except ValueError as e:
                print(f"Warning: {e}")

        return providers


def main():
    """Main application entry point."""
    parser = argparse.ArgumentParser(
        description='News scraper application',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'pages',
        type=int,
        nargs='?',
        default=None,
        help='Number of pages to scrape (from 0 to pages-1), e.g., 50 will scrape pages 0-49'
    )

    parser.add_argument(
        '--from',
        dest='page_from',
        type=int,
        default=0,
        help='Start page number (default: 0)'
    )

    parser.add_argument(
        '--to',
        dest='page_to',
        type=int,
        default=None,
        help='End page number (inclusive)'
    )

    parser.add_argument(
        '--mode',
        dest='mode',
        type=str,
        choices=['si', 'sir', 'sit'],
        default='si',
        help='Scraping mode: si (Strefa Inwestorow news, default), sir (Strefa Inwestorow Rekomendacje), sit (Strefa Inwestorow Ticker)'
    )

    parser.add_argument(
        '--ticker',
        dest='ticker',
        type=str,
        default=None,
        help='Ticker symbol to scrape for (used with sit mode)'
    )

    args = parser.parse_args()

    if args.mode == 'sit' and not args.ticker:
        parser.error("--ticker is required when --mode is sit")

    # Load configuration
    config = Config()

    # Handle different modes
    if args.mode == 'sir':
        # Recommendations mode - ignore page arguments
        print("="*80)
        print("NEWS MONITOR - RECOMMENDATIONS SCRAPING")
        print("="*80)
        print(f"\nStart time: {datetime.now()}")
        print(f"\nConfiguration:")
        print(f"  Database: {config.db_path}")
        print(f"  Mode: Recommendations (SIR)")

        # Initialize database
        db = Database(config.db_path)

        # Create recommendations provider
        provider = RekomendacjeProvider()
        print(f"Using provider: {provider.name}")

        # Initialize scraper
        scraper = Scraper(db)

        # Scrape recommendations
        try:
            stats = scraper.scrape_recommendations(provider)

            print(f"\nProvider: {stats['provider']}")
            print(f"  Total recommendations: {stats['total_recommendations']}")
            print(f"  New recommendations: {stats['new_recommendations']}")
            print(f"  Skipped (already exists): {stats['skipped_recommendations']}")
        except Exception as e:
            print(f"\n✗ Error processing recommendations: {e}")
            import traceback
            traceback.print_exc()

        # Print summary
        scraper.print_summary()

        # Close database
        db.close()

        print("\n✓ Recommendations scraping completed!")

    elif args.mode == 'sit':
        # Ticker mode for Strefa Inwestorow
        print("="*80)
        print("NEWS MONITOR - TICKER SCRAPING (STREFA INWESTOROW)")
        print("="*80)
        print(f"\nStart time: {datetime.now()}")
        print(f"\nConfiguration:")
        print(f"  Database: {config.db_path}")
        print(f"  Mode: Ticker (SIT)")
        print(f"  Ticker: {args.ticker}")

        # Determine page range (defaults to 0-4 if not specified)
        page_from = args.page_from
        page_to = args.page_to
        if args.pages is not None:
            page_from = 0
            page_to = args.pages - 1
        elif page_to is None:
            page_from = 0
            page_to = 4  # Default for SIT mode

        print(f"  Page range: {page_from} to {page_to} ({page_to - page_from + 1} pages)")

        stats = run_ticker_scraper(args.ticker, page_from, page_to)

        if "error" in stats:
            print(f"\n✗ Error: {stats['error']}")
        else:
            print(f"\nProvider: {stats['provider']}")
            print(f"  Company: {stats['company_name']}")
            print(f"  Total checked: {stats['total_checked']}")
            print(f"  New articles: {stats['new_articles']}")
            print(f"  Skipped (already exists): {stats['skipped_articles']}")

        print("\n✓ Ticker scraping task finished.")

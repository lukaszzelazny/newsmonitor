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
from providers.base_provider import BaseProvider


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

    args = parser.parse_args()

    # Load configuration
    config = Config()

    # Determine page range
    page_from = args.page_from
    page_to = args.page_to

    # If single number provided, use it as page count from 0
    if args.pages is not None:
        page_from = 0
        page_to = args.pages - 1
    # If --to provided without --from, use default from (0)
    elif page_to is None:
        # Default: scrape 50 pages (0-49)
        page_from = 0
        page_to = 49

    # Validate range
    if page_from < 0:
        print("✗ Error: --from must be >= 0")
        return
    if page_to < page_from:
        print("✗ Error: --to must be >= --from")
        return

    print("="*80)
    print("NEWS MONITOR - SCRAPING APPLICATION")
    print("="*80)
    print(f"\nStart time: {datetime.now()}")
    print(f"\nConfiguration:")
    print(f"  Database: {config.db_path}")
    print(f"  Providers: {len(config.providers)}")
    print(f"  Page range: {page_from} to {page_to} ({page_to - page_from + 1} pages)")

    # Initialize database
    db = Database(config.db_path)

    # Create providers
    providers = ProviderFactory.create_providers(config)

    if not providers:
        print("\n✗ No providers configured or available")
        return

    # Initialize scraper
    scraper = Scraper(db)

    # Scrape from all providers
    for provider in providers:
        try:
            stats = scraper.scrape_provider(provider, page_from, page_to)

            print(f"\nProvider: {stats['provider']}")
            print(f"  Total checked: {stats['total_checked']}")
            print(f"  New articles: {stats['new_articles']}")
            print(f"  Skipped (already exists): {stats['skipped_articles']}")
        except Exception as e:
            print(f"\n✗ Error processing provider {provider.name}: {e}")

    # Print summary
    scraper.print_summary()

    # Close database
    db.close()

    print("\n✓ Scraping completed!")


if __name__ == '__main__':
    main()







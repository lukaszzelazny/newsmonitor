"""Main entry point for the news scraper application."""

import argparse
from datetime import datetime, date
from typing import List
from dotenv import load_dotenv

from config import Config
from database import Database
from scraper import Scraper
from providers.pap_provider import PAPProvider
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
        '--date',
        type=str,
        help='Specific date to scrape (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--start-date',
        type=str,
        help='Start date for date range (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--end-date',
        type=str,
        help='End date for date range (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--date-range',
        choices=['all'],
        help='Scrape all dates (no filtering)'
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = Config()
    
    # Determine target date(s)
    target_date = None
    start_date = None
    end_date = None
    
    if args.date_range == 'all':
        # No date filtering
        target_date = None
    elif args.date:
        target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    elif args.start_date and args.end_date:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
    elif args.start_date:
        target_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
    elif args.end_date:
        target_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
    elif config.start_date and config.end_date:
        start_date = config.start_date
        end_date = config.end_date
    elif config.end_date:
        target_date = config.end_date
    else:
        # Default: yesterday
        target_date = config.get_yesterday_date()
    
    print("="*80)
    print("NEWS MONITOR - SCRAPING APPLICATION")
    print("="*80)
    print(f"\nStart time: {datetime.now()}")
    print(f"\nConfiguration:")
    print(f"  Database: {config.db_path}")
    print(f"  Providers: {len(config.providers)}")
    
    if target_date:
        print(f"  Target date: {target_date}")
    elif start_date and end_date:
        print(f"  Date range: {start_date} to {end_date}")
    else:
        print(f"  Date range: All")
    
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
            if start_date and end_date:
                scraper.scrape_range(provider, start_date, end_date)
            else:
                stats = scraper.scrape_provider(provider, target_date)
                
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





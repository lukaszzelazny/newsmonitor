"""Main entry point for the news scraper application."""

import argparse
from datetime import datetime
from typing import List
from dotenv import load_dotenv

from backend.config import Config
from backend.database import Database, Portfolio, Asset, Transaction
from backend.scraper import Scraper
from backend.scraper.providers.pap_provider import PAPProvider
from backend.scraper.providers.strefa_investorow_provider import StrefaInwestorowProvider
from backend.scraper.providers.rekomendacje_provider import RekomendacjeProvider
from backend.scraper.providers.base_provider import BaseProvider
from backend.tools.actions import run_ticker_scraper, import_xtb_transactions
from backend.portfolio.analysis import calculate_portfolio_return, calculate_group_return, get_holdings, calculate_asset_return

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
        choices=['si', 'sir', 'sit', 'import_xtb', 'analyze'],
        default='si',
        help='Scraping mode: si (Strefa Inwestorow news, default), sir (Strefa Inwestorow Rekomendacje), sit (Strefa Inwestorow Ticker), import_xtb (Import XTB transactions), analyze (Analyze portfolio)'
    )

    parser.add_argument(
        '--ticker',
        dest='ticker',
        type=str,
        default=None,
        help='Ticker symbol to scrape for (used with sit mode)'
    )

    parser.add_argument(
        '--file',
        dest='file_path',
        type=str,
        default=None,
        help='Path to the file to import (used with import_xtb mode)'
    )

    parser.add_argument(
        '--portfolio',
        dest='portfolio_name',
        type=str,
        default=None,
        help='Name of the portfolio to analyze (used with analyze mode)'
    )

    args = parser.parse_args()

    if args.mode == 'sit' and not args.ticker:
        parser.error("--ticker is required when --mode is sit")
    
    if args.mode == 'import_xtb' and not args.file_path:
        parser.error("--file is required when --mode is import_xtb")

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
    
    elif args.mode == 'import_xtb':
        print("="*80)
        print("NEWS MONITOR - XTB TRANSACTION IMPORT")
        print("="*80)
        print(f"\nStart time: {datetime.now()}")
        print(f"\nConfiguration:")
        print(f"  File path: {args.file_path}")

        result = import_xtb_transactions(args.file_path)

        if "error" in result:
            print(f"\n✗ Error: {result['error']}")
        else:
            print(f"\n✓ {result['message']}")

    elif args.mode == 'analyze':
        print("="*80)
        print("NEWS MONITOR - PORTFOLIO ANALYSIS")
        print("="*80)
        
        db = Database()
        session = db.Session()
        try:
            if args.portfolio_name:
                portfolio = session.query(Portfolio).filter_by(name=args.portfolio_name).first()
                if not portfolio:
                    print(f"\n✗ Error: Portfolio '{args.portfolio_name}' not found.")
                    return

                print(f"--- Analysis for Portfolio: {portfolio.name} ---")
                # Holdings
                current_holdings = get_holdings(session, portfolio.id)
                print("\nCurrent Holdings:")
                for ticker, qty in current_holdings.items():
                    print(f"  {ticker}: {qty:.2f}")

                # Per-asset return
                print("\nAsset Returns:")
                assets = session.query(Asset.id, Asset.ticker).join(Transaction).filter(Transaction.portfolio_id == portfolio.id).distinct().all()
                for asset_id, ticker in assets:
                    asset_return = calculate_asset_return(session, portfolio.id, asset_id)
                    print(f"  {ticker}:")
                    print(f"    Realized PnL: {asset_return['realized_pnl']:.2f}")
                    print(f"    Rate of Return: {asset_return['rate_of_return']:.2f}%")

                # Portfolio return
                portfolio_return = calculate_portfolio_return(session, portfolio.id)
                print("\nPortfolio Summary:")
                print(f"  Total Cost: {portfolio_return['total_cost']:.2f}")
                print(f"  Total Revenue: {portfolio_return['total_revenue']:.2f}")
                print(f"  Realized PnL: {portfolio_return['realized_pnl']:.2f}")
                print(f"  Rate of Return: {portfolio_return['rate_of_return']:.2f}%")

            else:
                # Group return for all portfolios
                group_return = calculate_group_return(session)
                print("\n--- Group Analysis (All Portfolios) ---")
                print(f"  Total Cost: {group_return['total_cost']:.2f}")
                print(f"  Total Revenue: {group_return['total_revenue']:.2f}")
                print(f"  Realized PnL: {group_return['realized_pnl']:.2f}")
                print(f"  Rate of Return: {group_return['rate_of_return']:.2f}%")
        finally:
            session.close()
            db.close()

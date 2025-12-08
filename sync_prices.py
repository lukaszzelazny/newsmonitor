"""
Script to sync historical price data from Yahoo Finance to local database.
Can be run manually or scheduled as a daily job.

Usage:
    python sync_prices.py [--full] [--ticker TICKER]

Options:
    --full: Download full history instead of incremental update
    --ticker: Sync only specific ticker (otherwise syncs all assets)
"""

import argparse
import logging
from datetime import datetime, timedelta
from typing import List, Optional
import yfinance as yf
from sqlalchemy.orm import sessionmaker
from portfolio.models import Asset, AssetPriceHistory
from database import Database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PriceSyncService:
    """Service for syncing price data from Yahoo Finance to database."""

    def __init__(self, session):
        self.session = session

    def get_assets_to_sync(self, ticker: Optional[str] = None) -> List[Asset]:
        """Get list of assets that need price sync."""
        query = self.session.query(Asset)
        if ticker:
            query = query.filter(Asset.ticker == ticker.upper())
        return query.all()

    def get_last_sync_date(self, asset_id: int) -> Optional[datetime]:
        """Get the last date for which we have price data."""
        last_record = (
            self.session.query(AssetPriceHistory)
            .filter(AssetPriceHistory.asset_id == asset_id)
            .order_by(AssetPriceHistory.date.desc())
            .first()
        )
        return last_record.date if last_record else None

    def fetch_yahoo_data(self, ticker: str, start_date: Optional[datetime], end_date: datetime):
        """Fetch price data from Yahoo Finance."""
        try:
            # If no start_date, get 5 years of history
            if start_date is None:
                start_date = end_date - timedelta(days=5*365)

            logger.info(f"Fetching data for {ticker} from {start_date} to {end_date}")

            # Download data from Yahoo Finance
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(start=start_date, end=end_date)

            if df.empty:
                logger.warning(f"No data returned for {ticker}")
                return None

            return df

        except Exception as e:
            logger.error(f"Error fetching data for {ticker}: {str(e)}")
            return None

    def save_price_data(self, asset: Asset, df):
        """Save price data to database."""
        if df is None or df.empty:
            return 0

        records_added = 0

        for date, row in df.iterrows():
            # Check if record already exists
            existing = (
                self.session.query(AssetPriceHistory)
                .filter(
                    AssetPriceHistory.asset_id == asset.id,
                    AssetPriceHistory.date == date.date()
                )
                .first()
            )

            if existing:
                # Update existing record
                existing.open = float(row['Open']) if 'Open' in row else None
                existing.high = float(row['High']) if 'High' in row else None
                existing.low = float(row['Low']) if 'Low' in row else None
                existing.close = float(row['Close'])
                existing.volume = float(row['Volume']) if 'Volume' in row else None
                existing.adjusted_close = float(row['Close'])  # YF returns adjusted by default
            else:
                # Create new record
                price_record = AssetPriceHistory(
                    asset_id=asset.id,
                    date=date.date(),
                    open=float(row['Open']) if 'Open' in row else None,
                    high=float(row['High']) if 'High' in row else None,
                    low=float(row['Low']) if 'Low' in row else None,
                    close=float(row['Close']),
                    volume=float(row['Volume']) if 'Volume' in row else None,
                    adjusted_close=float(row['Close'])
                )
                self.session.add(price_record)
                records_added += 1

        return records_added

    def sync_asset(self, asset: Asset, full_sync: bool = False):
        """Sync price data for a single asset."""
        logger.info(f"Syncing {asset.ticker} ({asset.name})")

        end_date = datetime.now()

        if full_sync:
            start_date = None
            logger.info(f"Performing full sync for {asset.ticker}")
        else:
            last_date = self.get_last_sync_date(asset.id)
            if last_date:
                # Start from day after last sync, with 1 day overlap for safety
                start_date = last_date - timedelta(days=1)
                logger.info(f"Incremental sync from {start_date}")
            else:
                start_date = None
                logger.info(f"No existing data, performing initial sync")

        # Fetch data from Yahoo Finance
        df = self.fetch_yahoo_data(asset.ticker, start_date, end_date)

        if df is not None:
            # Save to database
            records_added = self.save_price_data(asset, df)
            self.session.commit()
            logger.info(f"✓ {asset.ticker}: {records_added} new records added")
            return True
        else:
            logger.error(f"✗ {asset.ticker}: Failed to fetch data")
            return False

    def sync_all_assets(self, full_sync: bool = False, ticker: Optional[str] = None):
        """Sync price data for all assets (or specific ticker)."""
        assets = self.get_assets_to_sync(ticker)

        if not assets:
            logger.warning("No assets found to sync")
            return

        logger.info(f"Starting sync for {len(assets)} asset(s)")

        success_count = 0
        fail_count = 0

        for asset in assets:
            try:
                if self.sync_asset(asset, full_sync):
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                logger.error(f"Error syncing {asset.ticker}: {str(e)}")
                fail_count += 1
                self.session.rollback()

        logger.info(f"\n=== Sync Summary ===")
        logger.info(f"Successful: {success_count}")
        logger.info(f"Failed: {fail_count}")
        logger.info(f"Total: {len(assets)}")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description='Sync historical price data from Yahoo Finance')
    parser.add_argument('--full', action='store_true', help='Perform full sync (all historical data)')
    parser.add_argument('--ticker', type=str, help='Sync only specific ticker')

    args = parser.parse_args()

    # Create database session using pg_service connection
    db = Database()
    session = db.Session()

    try:
        logger.info("Connected to PostgreSQL using pg_service 'stock'")

        # Create sync service and run
        service = PriceSyncService(session)
        service.sync_all_assets(full_sync=args.full, ticker=args.ticker)
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise
    finally:
        session.close()


if __name__ == '__main__':
    main()
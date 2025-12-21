"""
Script to sync historical price data from Yahoo Finance to local database.
Can be run manually or scheduled as a daily job.

Usage:
    python sync_prices.py [--full] [--ticker TICKER] [--csv-mode] [--tickers-file TICKERS_FILE] [--output OUTPUT] [--gpw] [--active-only]

Options:
    --full: Download full history instead of incremental update
    --ticker: Sync only specific ticker (otherwise syncs all assets)
    --csv-mode: Export to CSV instead of database (doesn't require DB connection)
    --tickers-file: Path to file with tickers (one per line) for CSV mode
    --output: Output CSV filename (default: price_history_YYYYMMDD.csv)
    --gpw: Add .WA suffix to tickers for Warsaw Stock Exchange (GPW)
    --active-only: Sync only assets that are currently held (quantity > 0) or marked as favorites
    --convert-to-pln: Convert existing prices in database to PLN using historical FX rates
"""

import argparse
import logging
import csv
import time
import random
from datetime import datetime, timedelta
from typing import List, Optional, TYPE_CHECKING
from dotenv import load_dotenv
import yfinance as yf
from sqlalchemy.orm import sessionmaker
import pandas as pd
# import requests
# from requests.adapters import HTTPAdapter
# from urllib3.util.retry import Retry

# Conditional imports for type hints
if TYPE_CHECKING:
    from backend.database import Asset, AssetPriceHistory

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# def create_yf_session():
#     """Create a requests session with retry logic and custom headers to avoid blocking."""
#     session = requests.Session()
#
#     # Add retry logic
#     retries = Retry(
#         total=3,
#         backoff_factor=1,
#         status_forcelist=[429, 500, 502, 503, 504]
#     )
#     session.mount('http://', HTTPAdapter(max_retries=retries))
#     session.mount('https://', HTTPAdapter(max_retries=retries))
#
#     # Add headers to mimic browser
#     session.headers.update({
#         'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
#         'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
#         'Accept-Language': 'en-US,en;q=0.5',
#         'Accept-Encoding': 'gzip, deflate',
#         'Connection': 'keep-alive',
#         'Upgrade-Insecure-Requests': '1'
#     })
#
#     return session


class CSVExporter:
    """Export price data to CSV without database connection."""

    def __init__(self, output_file: str, add_gpw_suffix: bool = False):
        self.output_file = output_file
        self.add_gpw_suffix = add_gpw_suffix
        self.records_written = 0

    def normalize_ticker(self, ticker: str) -> tuple[str, str]:
        """
        Normalize ticker for Yahoo Finance.
        Returns: (original_ticker, yf_ticker)
        """
        original = ticker.strip().upper()
        yf_ticker = original

        if self.add_gpw_suffix and not original.endswith('.WA'):
            yf_ticker = f"{original}.WA"

        return original, yf_ticker

    def read_tickers_from_file(self, file_path: str) -> List[tuple[str, str]]:
        """
        Read ticker symbols from a text file (one per line).
        Returns list of (original_ticker, yf_ticker) tuples.
        """
        try:
            with open(file_path, 'r') as f:
                tickers = [self.normalize_ticker(line) for line in f if line.strip()]
            logger.info(f"Loaded {len(tickers)} tickers from {file_path}")
            if self.add_gpw_suffix:
                logger.info("GPW mode: Adding .WA suffix to tickers")
            return tickers
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            return []

    def fetch_and_export(self, tickers: List[tuple[str, str]], years_back: int = 5):
        """Fetch data for all tickers and export to CSV."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years_back*365)

        logger.info(f"Exporting data to: {self.output_file}")
        logger.info(f"Mode: CSV (Standalone) - Skipping database checks, fetching fresh data from YF")
        logger.info(f"Date range: {start_date.date()} to {end_date.date()}")

        with open(self.output_file, 'w', newline='') as csvfile:
            fieldnames = ['ticker', 'date', 'open', 'high', 'low', 'close', 'volume', 'adjusted_close']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            success_count = 0
            fail_count = 0

            for original_ticker, yf_ticker in tickers:
                try:
                    logger.info(f"Fetching {original_ticker} (YF: {yf_ticker})...")
                    ticker_obj = yf.Ticker(yf_ticker)
                    df = ticker_obj.history(start=start_date, end=end_date)

                    if df.empty:
                        logger.warning(f"No data for {yf_ticker}")
                        fail_count += 1
                        continue

                    # Write rows for this ticker (use original ticker in CSV)
                    for date, row in df.iterrows():
                        writer.writerow({
                            'ticker': original_ticker,
                            'date': date.date().isoformat(),
                            'open': row['Open'] if 'Open' in row else None,
                            'high': row['High'] if 'High' in row else None,
                            'low': row['Low'] if 'Low' in row else None,
                            'close': row['Close'],
                            'volume': row['Volume'] if 'Volume' in row else None,
                            'adjusted_close': row['Close']
                        })
                        self.records_written += 1

                    logger.info(f"✓ {original_ticker}: {len(df)} records")
                    success_count += 1

                except Exception as e:
                    logger.error(f"✗ {yf_ticker}: {str(e)}")
                    fail_count += 1

            logger.info(f"\n=== Export Summary ===")
            logger.info(f"Output file: {self.output_file}")
            logger.info(f"Total records: {self.records_written}")
            logger.info(f"Successful tickers: {success_count}")
            logger.info(f"Failed tickers: {fail_count}")


class PriceSyncService:
    """Service for syncing price data from Yahoo Finance to database."""

    # Mapping for special tickers (e.g., cryptocurrencies)
    TICKER_MAPPING = {
        'BITCOIN': 'BTC-USD',
        'BTC': 'BTC-USD',
        'ETHEREUM': 'ETH-USD',
        'ETH': 'ETH-USD',
        'LITECOIN': 'LTC-USD',
        'LTC': 'LTC-USD',
        'RIPPLE': 'XRP-USD',
        'XRP': 'XRP-USD',
        'CSPX.UK': 'CSPX.AS',
        'TSLA.DE': 'TL0.DE',
        'HOOD.US': 'HOOD'
    }

    def __init__(self, session):
        self.session = session
        # Import price_fetcher functions locally to avoid circular imports
        from backend.tools.price_fetcher import get_currency_for_ticker, fx_symbol_to_pln, _fetch_fx_series
        self.get_currency_for_ticker = get_currency_for_ticker
        self.fx_symbol_to_pln = fx_symbol_to_pln
        self._fetch_fx_series = _fetch_fx_series

    def normalize_ticker_for_yf(self, ticker: str) -> str:
        """
        Normalize ticker for Yahoo Finance API.

        Rules:
        - Special mappings (BITCOIN → BTC-USD, etc.)
        - .PL suffix → .WA (Polish stocks: XTB.PL → XTB.WA)
        - .US suffix → remove (US stocks: GOOGL.US → GOOGL)
        - No suffix → keep as is (AAPL → AAPL)
        """
        ticker = ticker.strip().upper()

        # Check special mappings first
        if ticker in self.TICKER_MAPPING:
            return self.TICKER_MAPPING[ticker]

        if ticker.endswith('.PL'):
            # Polish stocks: replace .PL with .WA
            return ticker.replace('.PL', '.WA')
        elif ticker.endswith('.US'):
            # US stocks: remove .US suffix
            return ticker.replace('.US', '')
        else:
            # Keep as is
            return ticker

    def get_assets_to_sync(self, ticker: Optional[str] = None, active_only: bool = False) -> List:
        """Get list of assets that need price sync."""
        from backend.database import Asset, Ticker, Transaction, TransactionType
        
        query = self.session.query(Asset)
        if ticker:
            query = query.filter(Asset.ticker == ticker.upper())
            
        if active_only:
            logger.info("Filtering for active assets (held or favorites)...")
            
            # 1. Get Favorite Tickers
            favorite_tickers = {
                t[0] for t in self.session.query(Ticker.ticker)
                .filter(Ticker.in_portfolio == 1).all()
            }
            
            # 2. Get Currently Held Asset IDs
            transactions = self.session.query(Transaction).all()
            holdings = {}
            for t in transactions:
                aid = t.asset_id
                qty = float(t.quantity)
                if t.transaction_type == TransactionType.BUY:
                    holdings[aid] = holdings.get(aid, 0.0) + qty
                else:
                    holdings[aid] = holdings.get(aid, 0.0) - qty
            
            held_asset_ids = {aid for aid, qty in holdings.items() if qty > 0.0001}
            
            # Filter assets
            all_assets = query.all()
            filtered_assets = []
            for asset in all_assets:
                is_fav = asset.ticker in favorite_tickers
                is_held = asset.id in held_asset_ids
                if is_fav or is_held:
                    filtered_assets.append(asset)
            
            logger.info(f"Selected {len(filtered_assets)} active assets (out of {len(all_assets)})")
            return filtered_assets
            
        return query.all()

    def get_last_sync_date(self, asset_id: int) -> Optional[datetime]:
        """Get the last date for which we have price data."""
        from backend.database import AssetPriceHistory
        last_record = (
            self.session.query(AssetPriceHistory)
            .filter(AssetPriceHistory.asset_id == asset_id)
            .order_by(AssetPriceHistory.date.desc())
            .first()
        )
        return last_record.date if last_record else None

    def get_first_sync_date(self, asset_id: int) -> Optional[datetime]:
        """Get the first date for which we have price data."""
        from backend.database import AssetPriceHistory
        first_record = (
            self.session.query(AssetPriceHistory)
            .filter(AssetPriceHistory.asset_id == asset_id)
            .order_by(AssetPriceHistory.date.asc())
            .first()
        )
        return first_record.date if first_record else None

    def fetch_yahoo_data(self, ticker: str, start_date: Optional[datetime], end_date: datetime, suppress_errors: bool = False):
        """Fetch price data from Yahoo Finance."""
        yf_logger = logging.getLogger('yfinance')
        original_level = yf_logger.level
        
        if suppress_errors:
            yf_logger.setLevel(logging.CRITICAL)

        try:
            # Normalize ticker for Yahoo Finance
            yf_ticker = self.normalize_ticker_for_yf(ticker)

            # If no start_date, get 5 years of history
            if start_date is None:
                start_date = end_date - timedelta(days=5*365)

            # Handle date/datetime objects for logging
            start_date_log = start_date.date() if isinstance(start_date, datetime) else start_date
            end_date_log = end_date.date() if isinstance(end_date, datetime) else end_date

            logger.info(f"Fetching data for {ticker} (YF: {yf_ticker}) from {start_date_log} to {end_date_log}")

            # Add random delay to avoid rate limiting (1-3 seconds)
            delay = random.uniform(1.0, 3.0)
            time.sleep(delay)

            # Create custom session
            # session = create_yf_session()

            # Download data from Yahoo Finance with custom session
            ticker_obj = yf.Ticker(yf_ticker) # , session=session)
            df = ticker_obj.history(start=start_date, end=end_date)

            if df.empty:
                msg = f"No data returned for {yf_ticker} - ticker may be delisted or invalid"
                if suppress_errors:
                    logger.info(f"Note: {msg} (Expected for history gap fill)")
                else:
                    logger.warning(msg)
                return None

            logger.info(f"✓ Retrieved {len(df)} records for {yf_ticker}")
            return df

        except Exception as e:
            if suppress_errors:
                logger.info(f"Could not fetch data for {ticker} (YF: {yf_ticker}): {str(e)}. This is likely because the asset did not exist yet.")
            else:
                logger.error(f"Error fetching data for {ticker} (YF: {yf_ticker}): {str(e)}")
                # Add longer delay after error
                time.sleep(5)
            return None
        finally:
            if suppress_errors:
                yf_logger.setLevel(original_level)

    def save_price_data(self, asset, df):
        """Save price data to database."""
        from backend.database import AssetPriceHistory

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

    def _convert_df_to_pln(self, asset, df):
        """Convert a DataFrame of price data from original currency to PLN."""
        if df is None or df.empty:
            return df
        
        # Determine currency from ticker
        yf_ticker = self.normalize_ticker_for_yf(asset.ticker)
        currency = self.get_currency_for_ticker(yf_ticker)
        
        if currency == "PLN":
            # Already in PLN, no conversion needed
            return df
        
        # Get date range for FX series
        start_date = df.index.min().date()
        end_date = df.index.max().date() + timedelta(days=1)
        
        # Fetch FX series for this currency
        fx_ticker = self.fx_symbol_to_pln(currency)
        if not fx_ticker:
            logger.error(f"Cannot get FX ticker for currency {currency}, skipping conversion.")
            return df
        
        fx_series_map = self._fetch_fx_series([currency], start_date, end_date)
        fx_series = fx_series_map.get(fx_ticker)
        
        if fx_series is None or fx_series.empty:
            logger.error(f"Cannot fetch FX rates for {fx_ticker} in range {start_date} to {end_date}")
            return df
        
        # Align FX series with df index (ensure same timezone/format)
        # fx_series index is datetime64[ns], df index is also datetime64[ns] from yfinance
        # Reindex fx_series to df.index and forward/backward fill
        
        # Fix timezone mismatch (df is usually aware, fx_series from yf.download is naive)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        
        if fx_series.index.tz is not None:
            fx_series.index = fx_series.index.tz_localize(None)

        aligned_fx = fx_series.reindex(df.index).ffill().bfill()
        
        # Convert all price columns
        price_columns = ['Open', 'High', 'Low', 'Close', 'Adj Close'] if 'Adj Close' in df.columns else ['Open', 'High', 'Low', 'Close']
        for col in price_columns:
            if col in df.columns:
                df[col] = df[col] * aligned_fx.values
        
        # Volume remains unchanged
        return df

    def convert_existing_prices_to_pln(self, asset):
        """Convert existing price records for an asset from original currency to PLN using historical FX rates."""
        from backend.database import AssetPriceHistory
        logger.info(f"Converting existing prices for {asset.ticker} to PLN...")
        
        # Get all price records for this asset
        records = self.session.query(AssetPriceHistory).filter(
            AssetPriceHistory.asset_id == asset.id
        ).order_by(AssetPriceHistory.date.asc()).all()
        
        if not records:
            logger.info(f"No price records found for {asset.ticker}")
            return 0
        
        # Determine currency from ticker
        yf_ticker = self.normalize_ticker_for_yf(asset.ticker)
        currency = self.get_currency_for_ticker(yf_ticker)
        
        if currency == "PLN":
            logger.info(f"{asset.ticker} is already in PLN, skipping conversion.")
            return 0
        
        # Get date range for FX series
        dates = [r.date for r in records]
        start_date = min(dates)
        end_date = max(dates) + timedelta(days=1)
        
        # Fetch FX series for this currency
        fx_ticker = self.fx_symbol_to_pln(currency)
        if not fx_ticker:
            logger.error(f"Cannot get FX ticker for currency {currency}, skipping conversion.")
            return 0
        
        fx_series_map = self._fetch_fx_series([currency], start_date, end_date)
        fx_series = fx_series_map.get(fx_ticker)
        
        if fx_series is None or fx_series.empty:
            logger.error(f"Cannot fetch FX rates for {fx_ticker} in range {start_date} to {end_date}")
            return 0
        
        # Convert each record
        updated_count = 0
        for record in records:
            # Get FX rate for the specific date
            # FX series index is datetime64[ns], convert record.date to same type
            record_date = pd.Timestamp(record.date)
            if record_date in fx_series.index:
                fx_rate = float(fx_series.loc[record_date])
            else:
                # Try to find nearest previous date (forward fill)
                # Use pandas to reindex and ffill
                # Create a single-element series
                try:
                    # Get the FX rate at or before record_date
                    # Use asof which returns last valid value up to record_date
                    fx_rate = float(fx_series.asof(record_date))
                    if pd.isna(fx_rate):
                        # If still NaN, try backward fill
                        fx_rate = float(fx_series.bfill().iloc[0])
                except Exception as e:
                    logger.warning(f"Cannot get FX rate for {record.date}: {e}, skipping")
                    continue
            
            # Convert all price fields
            if record.open is not None:
                record.open = float(record.open) * fx_rate
            if record.high is not None:
                record.high = float(record.high) * fx_rate
            if record.low is not None:
                record.low = float(record.low) * fx_rate
            record.close = float(record.close) * fx_rate
            record.adjusted_close = float(record.adjusted_close) * fx_rate
            
            updated_count += 1
        
        if updated_count > 0:
            self.session.commit()
            logger.info(f"✓ Converted {updated_count} price records for {asset.ticker} to PLN")
        else:
            logger.info(f"No records converted for {asset.ticker}")
        
        return updated_count

    def sync_asset(self, asset, full_sync: bool = False):
        """Sync price data for a single asset."""
        logger.info(f"Syncing {asset.ticker} ({asset.name})")

        end_date = datetime.now()
        target_history_start = end_date - timedelta(days=5*365) # 5 years ago
        
        ranges_to_sync = []
        
        # Check what we have in DB
        first_date = self.get_first_sync_date(asset.id)
        last_date = self.get_last_sync_date(asset.id)

        if not first_date or not last_date:
            # No existing data, performing initial sync
            logger.info(f"No existing data, performing initial sync")
            # (start, end, suppress_errors)
            ranges_to_sync.append((None, end_date, False))
            
        elif full_sync:
            # Smart Full Sync: Fill gaps but avoid re-downloading existing data
            logger.info(f"Smart Full Sync for {asset.ticker} (filling gaps)")

            # 1. Check history gap (older than first_date)
            # Ensure types match for comparison
            first_date_dt = datetime.combine(first_date, datetime.min.time()) if not isinstance(first_date, datetime) else first_date
            
            if first_date_dt > target_history_start + timedelta(days=7):
                logger.info(f"Found history gap: {target_history_start.date()} to {first_date}")
                # Fetch up to first_date, suppress errors as it might not exist
                ranges_to_sync.append((target_history_start, first_date, True))
            
            # 2. Check recent gap (newer than last_date)
            last_date_dt = datetime.combine(last_date, datetime.min.time()) if not isinstance(last_date, datetime) else last_date
            
            if last_date_dt.date() < end_date.date() - timedelta(days=1):
                logger.info(f"Found recent gap: {last_date} to {end_date.date()}")
                start_date = last_date - timedelta(days=1) # 1 day overlap for safety
                ranges_to_sync.append((start_date, end_date, False))
                
            if not ranges_to_sync:
                logger.info("Data is up to date (5 years history + recent), skipping download.")
                
        else:
            # Standard Incremental Sync (Default)
            # Only looks forward from last_date
            start_date = last_date - timedelta(days=1)
            logger.info(f"Incremental sync from {start_date}")
            ranges_to_sync.append((start_date, end_date, False))

        # Execute syncs
        total_records = 0
        success = True
        
        if not ranges_to_sync:
            return True

        for start, end, suppress_errors in ranges_to_sync:
            df = self.fetch_yahoo_data(asset.ticker, start, end, suppress_errors=suppress_errors)
            if df is not None:
                # Convert new data to PLN before saving
                df = self._convert_df_to_pln(asset, df)
                records = self.save_price_data(asset, df)
                total_records += records
            elif not suppress_errors:
                # Only mark as failure if we didn't suppress errors
                success = False

        if success:
            self.session.commit()
            if total_records > 0:
                logger.info(f"✓ {asset.ticker}: {total_records} new records added")
            else:
                logger.info(f"✓ {asset.ticker}: Up to date")
            return True
        else:
            logger.error(f"✗ {asset.ticker}: Failed to fetch data for some ranges")
            return False

    def sync_all_assets(self, full_sync: bool = False, ticker: Optional[str] = None, active_only: bool = False):
        """Sync price data for all assets (or specific ticker)."""
        assets = self.get_assets_to_sync(ticker, active_only=active_only)

        if not assets:
            logger.warning("No assets found to sync")
            return

        logger.info(f"Starting sync for {len(assets)} asset(s)")
        logger.info(f"Adding delays between requests to avoid rate limiting...")

        success_count = 0
        fail_count = 0
        skip_count = 0

        for idx, asset in enumerate(assets, 1):
            try:
                logger.info(f"\n[{idx}/{len(assets)}] Processing {asset.ticker}...")

                # Check if ticker can be normalized
                yf_ticker = self.normalize_ticker_for_yf(asset.ticker)

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

        if fail_count > 0:
            logger.info(f"\nNote: {fail_count} ticker(s) failed - they may be:")
            logger.info("  - Delisted from the exchange")
            logger.info("  - Invalid ticker symbols")
            logger.info("  - Not available in Yahoo Finance")
            logger.info("  - Need manual mapping (check TICKER_MAPPING in script)")
            logger.info("  - Rate limited (try running again with smaller batches)")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description='Sync historical price data from Yahoo Finance')
    parser.add_argument('--full', action='store_true', help='Perform full sync (all historical data)')
    parser.add_argument('--ticker', type=str, help='Sync only specific ticker')
    parser.add_argument('--csv-mode', action='store_true', help='Export to CSV instead of database')
    parser.add_argument('--tickers-file', type=str, help='Path to file with tickers (one per line) for CSV mode')
    parser.add_argument('--output', type=str, help='Output CSV filename')
    parser.add_argument('--gpw', action='store_true', help='Add .WA suffix for Warsaw Stock Exchange tickers')
    parser.add_argument('--convert-to-pln', action='store_true', help='Convert existing prices in database to PLN using historical FX rates')
    parser.add_argument('--active-only', action='store_true', help='Sync only active assets (held or favorites)')

    args = parser.parse_args()

    # CSV export mode - no database connection needed
    if args.csv_mode:
        # Determine output filename
        if args.output:
            output_file = args.output
        else:
            output_file = f"price_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        exporter = CSVExporter(output_file, add_gpw_suffix=args.gpw)

        # Get tickers list
        if args.tickers_file:
            tickers = exporter.read_tickers_from_file(args.tickers_file)
        elif args.ticker:
            original, yf_ticker = exporter.normalize_ticker(args.ticker)
            tickers = [(original, yf_ticker)]
        else:
            logger.error("CSV mode requires either --tickers-file or --ticker")
            return

        if not tickers:
            logger.error("No tickers to process")
            return

        # Fetch and export
        exporter.fetch_and_export(tickers)
        logger.info(f"\n✓ CSV export complete: {output_file}")
        logger.info("You can now import this file to your database using DBeaver or similar tool")
        return

    # Database mode - requires database connection
    try:
        from backend.database import Asset, AssetPriceHistory, Database
    except ImportError as e:
        logger.error(f"Cannot import database modules: {e}")
        logger.error("Use --csv-mode if you don't have database access")
        return

    # Create database session using pg_service connection
    db = Database()
    session = db.Session()

    try:
        logger.info("Connected to PostgreSQL using pg_service 'stock'")

        # Create sync service and run
        service = PriceSyncService(session)
        
        # Convert existing prices to PLN if requested
        if args.convert_to_pln:
            logger.info("Converting existing prices to PLN using historical FX rates...")
            assets = service.get_assets_to_sync(ticker=args.ticker)
            total_converted = 0
            for asset in assets:
                converted = service.convert_existing_prices_to_pln(asset)
                total_converted += converted
            logger.info(f"Total records converted to PLN: {total_converted}")
            # Continue with normal sync after conversion
        
        service.sync_all_assets(full_sync=args.full, ticker=args.ticker, active_only=args.active_only)
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise
    finally:
        session.close()


if __name__ == '__main__':
    main()

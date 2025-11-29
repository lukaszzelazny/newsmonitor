"""Importer for XTB transaction history files with support for CLOSED and OPEN positions."""

import pandas as pd
from sqlalchemy.orm import Session
from portfolio.models import Asset, Transaction, TransactionType
from database import Database
from datetime import datetime


class XtbImporter:
    """Imports transaction data from an XTB XLSX file (closed and open positions)."""

    def __init__(self, db_session: Session):
        self.session = db_session

    @staticmethod
    def _find_header_row(df: pd.DataFrame) -> int:
        """Find row index that contains a header with Position/Symbol columns."""
        for i, row in df.iterrows():
            vals = [str(v).strip() for v in row.values]
            if "Position" in vals and "Symbol" in vals:
                return i
        return -1

    def _get_or_create_asset(self, ticker: str) -> Asset:
        asset = self.session.query(Asset).filter_by(ticker=ticker).first()
        if not asset:
            asset = Asset(ticker=ticker, name=ticker, asset_type='stock')
            self.session.add(asset)
            self.session.flush()
        return asset

    def _process_closed_positions_sheet(self, df: pd.DataFrame, portfolio):
        """Create opening and closing transactions for rows in CLOSED POSITION HISTORY."""
        header_row_index = self._find_header_row(df)
        if header_row_index == -1:
            raise ValueError("Could not find the header row in the 'CLOSED POSITION HISTORY' sheet.")

        # Apply header and clean
        df.columns = df.iloc[header_row_index]
        df = df.drop(range(header_row_index + 1)).reset_index(drop=True)
        df = df.dropna(subset=['Position'])
        df = df[df['Position'] != 'Total']

        for _, row in df.iterrows():
            ticker = str(row['Symbol']).strip()
            if not ticker or ticker == 'nan':
                continue

            asset = self._get_or_create_asset(ticker)

            # Parse fields
            try:
                qty = float(row['Volume'])
            except Exception:
                continue

            try:
                open_price = float(row['Open price'])
            except Exception:
                # If no open price, skip this record
                continue

            try:
                open_time = pd.to_datetime(row['Open time']).date()
            except Exception:
                continue

            # some exports include close leg
            close_price = None
            close_time = None
            if 'Close price' in df.columns and pd.notna(row.get('Close price')):
                try:
                    close_price = float(row.get('Close price'))
                except Exception:
                    close_price = None
            if 'Close time' in df.columns and pd.notna(row.get('Close time')):
                try:
                    close_time = pd.to_datetime(row.get('Close time')).date()
                except Exception:
                    close_time = None

            # Commission handling (split 50/50 between legs if exists)
            commission_total = 0.0
            if 'Commission' in df.columns and pd.notna(row.get('Commission')):
                try:
                    commission_total = float(row.get('Commission') or 0.0)
                except Exception:
                    commission_total = 0.0
            open_comm = commission_total / 2.0
            close_comm = commission_total - open_comm

            open_type = TransactionType.BUY if str(row['Type']).strip().upper() == 'BUY' else TransactionType.SELL
            close_type = TransactionType.SELL if open_type == TransactionType.BUY else TransactionType.BUY

            # Opening leg
            self.session.add(Transaction(
                portfolio_id=portfolio.id,
                asset_id=asset.id,
                transaction_type=open_type,
                quantity=qty,
                price=open_price,
                transaction_date=open_time,
                commission=open_comm
            ))

            # Closing leg if present
            if close_price is not None and close_time is not None:
                self.session.add(Transaction(
                    portfolio_id=portfolio.id,
                    asset_id=asset.id,
                    transaction_type=close_type,
                    quantity=qty,
                    price=close_price,
                    transaction_date=close_time,
                    commission=close_comm
                ))

    def _process_open_positions_sheet(self, df: pd.DataFrame, portfolio):
        """Create a single opening transaction for each OPEN position currently held."""
        header_row_index = self._find_header_row(df)
        if header_row_index == -1:
            # Nothing to do
            return

        df.columns = df.iloc[header_row_index]
        df = df.drop(range(header_row_index + 1)).reset_index(drop=True)

        # Rows with 'Total' are aggregate, skip
        if 'Position' not in df.columns:
            return
        df = df.dropna(subset=['Position'])
        df = df[df['Position'] != 'Total']

        # OPEN POSITION columns differ slightly: use Open time/Open price
        for _, row in df.iterrows():
            ticker = str(row['Symbol']).strip()
            if not ticker or ticker == 'nan':
                continue

            asset = self._get_or_create_asset(ticker)

            try:
                qty = float(row['Volume'])
            except Exception:
                continue

            try:
                open_price = float(row['Open price'])
            except Exception:
                continue

            try:
                open_time = pd.to_datetime(row['Open time']).date()
            except Exception:
                continue

            # Commission if present
            commission_val = 0.0
            if 'Commission' in df.columns and pd.notna(row.get('Commission')):
                try:
                    commission_val = float(row.get('Commission') or 0.0)
                except Exception:
                    commission_val = 0.0

            # In open positions sheet, Type indicates current side. We only add opening leg.
            open_type = TransactionType.BUY if str(row['Type']).strip().upper() == 'BUY' else TransactionType.SELL

            self.session.add(Transaction(
                portfolio_id=portfolio.id,
                asset_id=asset.id,
                transaction_type=open_type,
                quantity=qty,
                price=open_price,
                transaction_date=open_time,
                commission=commission_val
            ))

    def import_transactions(self, file_path: str, portfolio):
        """
        Reads an XLSX file and imports transactions into the given portfolio.

        Args:
            file_path: Path to the XTB XLSX file.
            portfolio: The Portfolio object to which transactions will be added.
        """
        try:
            xfile = pd.ExcelFile(file_path)

            # CLOSED POSITION HISTORY (create open+close legs)
            if 'CLOSED POSITION HISTORY' in xfile.sheet_names:
                df_closed = pd.read_excel(file_path, sheet_name='CLOSED POSITION HISTORY', header=None)
                self._process_closed_positions_sheet(df_closed, portfolio)

            # Any sheet that starts with/contains 'OPEN POSITION' (create opening leg only)
            for sheet in xfile.sheet_names:
                if 'OPEN POSITION' in sheet.upper():
                    df_open = pd.read_excel(file_path, sheet_name=sheet, header=None)
                    self._process_open_positions_sheet(df_open, portfolio)

            self.session.commit()
            print(f"Successfully imported transactions from: {file_path}")

        except Exception as e:
            self.session.rollback()
            print(f"An error occurred during import: {e}")
            raise


if __name__ == '__main__':
    # Example usage
    db = Database()
    session = db.Session()

    from portfolio.models import Portfolio

    # Create a dummy portfolio for testing
    portfolio_name = "My XTB Portfolio"
    portfolio = session.query(Portfolio).filter_by(name=portfolio_name).first()
    if not portfolio:
        portfolio = Portfolio(name=portfolio_name, broker="XTB")
        session.add(portfolio)
        session.commit()

    # Path to the uploaded file
    file_path = "C:/Users/ukasz/Downloads/account_51885378_pl_xlsx_2005-12-31_2025-11-27/account_51885378_pl_xlsx_2005-12-31_2025-11-27.xlsx"
    
    importer = XtbImporter(session)
    importer.import_transactions(file_path, portfolio)

    session.close()

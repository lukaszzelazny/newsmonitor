"""Importer for XTB transaction history files."""

import pandas as pd
from sqlalchemy.orm import Session
from portfolio.models import Asset, Transaction, TransactionType
from database import Database
from datetime import datetime


class XtbImporter:
    """Imports transaction data from an XTB XLSX file."""

    def __init__(self, db_session: Session):
        self.session = db_session

    def import_transactions(self, file_path: str, portfolio):
        """
        Reads an XLSX file and imports transactions into the given portfolio.

        Args:
            file_path: Path to the XTB XLSX file.
            portfolio: The Portfolio object to which transactions will be added.
        """
        try:
            # Read the sheet without a header
            df = pd.read_excel(file_path, sheet_name='CLOSED POSITION HISTORY', header=None)

            # Find the header row
            header_row_index = -1
            for i, row in df.iterrows():
                if 'Position' in row.values and 'Symbol' in row.values:
                    header_row_index = i
                    break
            
            if header_row_index == -1:
                raise ValueError("Could not find the header row in the 'CLOSED POSITION HISTORY' sheet.")

            # Set the column names and drop the rows above it
            df.columns = df.iloc[header_row_index]
            df = df.drop(range(header_row_index + 1))
            df = df.reset_index(drop=True)

            # Clean up the DataFrame
            df = df.dropna(subset=['Position'])  # Drop rows without a Position ID
            df = df[df['Position'] != 'Total']  # Exclude the summary row

            for _, row in df.iterrows():
                # Find or create the asset
                ticker = row['Symbol']
                asset = self.session.query(Asset).filter_by(ticker=ticker).first()
                if not asset:
                    # Assuming asset type is 'stock' for now. This could be improved.
                    asset = Asset(ticker=ticker, name=ticker, asset_type='stock')
                    self.session.add(asset)
                    self.session.flush()

                # Determine transaction type
                transaction_type = TransactionType.BUY if row['Type'].upper() == 'BUY' else TransactionType.SELL

                # Create the transaction
                transaction = Transaction(
                    portfolio_id=portfolio.id,
                    asset_id=asset.id,
                    transaction_type=transaction_type,
                    quantity=row['Volume'],
                    price=row['Open price'],
                    transaction_date=pd.to_datetime(row['Open time']).date(),
                    commission=row.get('Commission', 0)  # Assuming commission is 0 if not present
                )
                self.session.add(transaction)

            self.session.commit()
            print(f"Successfully imported {len(df)} transactions.")

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

import argparse
import glob
import os
from database import Database
from portfolio.models import Portfolio, Transaction
from portfolio.importer import XtbImporter


def find_latest_xtb_file():
    """Finds the most recently modified XTB transaction file in Downloads."""
    base = r"C:\Users\ukasz\Downloads"
    # Pattern includes the known account number for specificity
    pattern = os.path.join(base, "**", "*account_51885378*.xlsx")
    candidates = glob.glob(pattern, recursive=True)

    if not candidates:
        return None

    # Return the file that was most recently modified
    latest_file = max(candidates, key=os.path.getmtime)
    return latest_file


def get_or_create_portfolio(session, name: str | None):
    if not name:
        name = "XTB"  # Default portfolio name

    p = session.query(Portfolio).filter_by(name=name).first()
    if p:
        return p

    p = Portfolio(name=name, broker="XTB")
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def reimport_xtb(portfolio_name: str, append: bool = False):
    """
    Finds the latest XTB file and re-imports transactions for the given portfolio.
    This function is designed to be called from other modules (e.g., the API).
    """
    db = Database()
    session = db.Session()
    try:
        latest_file = find_latest_xtb_file()
        if not latest_file:
            raise FileNotFoundError("Could not find any XTB transaction files in Downloads.")

        print(f"Found latest XTB file: {latest_file}")

        portfolio = get_or_create_portfolio(session, portfolio_name)
        before = session.query(Transaction).filter_by(portfolio_id=portfolio.id).count()
        print(f"Portfolio: {portfolio.name} (id={portfolio.id}) - existing transactions: {before}")

        if not append:
            deleted = session.query(Transaction).filter_by(portfolio_id=portfolio.id).delete(synchronize_session=False)
            session.commit()
            print(f"Deleted transactions: {deleted}")

        importer = XtbImporter(session)
        importer.import_transactions(latest_file, portfolio)

        after = session.query(Transaction).filter_by(portfolio_id=portfolio.id).count()
        print(f"Import complete. Transactions now: {after}")
        return {"file": latest_file, "before": before, "after": after}

    finally:
        session.close()


def main():
    """Command-line interface for re-importing."""
    parser = argparse.ArgumentParser(description="Purge transactions and re-import from XTB XLSX file(s).")
    parser.add_argument("--file", required=False, nargs="+", help="Path(s) to XTB XLSX file(s). If not provided, finds the latest in Downloads.")
    parser.add_argument("--portfolio", required=False, help="Portfolio name (defaults to 'XTB').")
    parser.add_argument("--append", action="store_true", help="Append to existing transactions (do not purge).")
    args = parser.parse_args()

    files_to_import = args.file
    if not files_to_import:
        latest_file = find_latest_xtb_file()
        if not latest_file:
            print("Error: No file specified and could not find an XTB file in Downloads.")
            return
        files_to_import = [latest_file]

    db = Database()
    session = db.Session()
    try:
        portfolio = get_or_create_portfolio(session, args.portfolio)
        before = session.query(Transaction).filter_by(portfolio_id=portfolio.id).count()
        print(f"Portfolio: {portfolio.name} (id={portfolio.id}) - existing transactions: {before}")

        if not args.append:
            deleted = session.query(Transaction).filter_by(portfolio_id=portfolio.id).delete(synchronize_session=False)
            session.commit()
            print(f"Deleted transactions: {deleted}")

        importer = XtbImporter(session)
        for f in files_to_import:
            print(f"Importing from: {f}")
            importer.import_transactions(f, portfolio)

        after = session.query(Transaction).filter_by(portfolio_id=portfolio.id).count()
        print(f"Imported. Transactions now: {after}")

    finally:
        session.close()


if __name__ == "__main__":
    main()

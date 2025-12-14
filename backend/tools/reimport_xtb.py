import argparse
import glob
import os
import sys
from backend.database import Database
from backend.portfolio.models import Portfolio, Transaction
from backend.portfolio.importer import XtbImporter


def find_all_xtb_files():
    """Finds all XTB transaction XLSX files in the current directory."""
    base = os.getcwd()
    pattern = os.path.join(base, "*.xlsx")
    candidates = glob.glob(pattern)

    if not candidates:
        return []
    
    return candidates


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


def reimport_xtb(portfolio_name: str, append: bool = True):
    """
    Finds all XTB XLSX files in the current directory and re-imports transactions for the given portfolio.
    This function is designed to be called from other modules (e.g., the API).
    """
    db = Database()
    session = db.Session()
    try:
        files = find_all_xtb_files()
        if not files:
            raise FileNotFoundError("Could not find any XLSX files in the current directory.")

        print(f"Found {len(files)} XLSX file(s): {files}")

        portfolio = get_or_create_portfolio(session, portfolio_name)
        before = session.query(Transaction).filter_by(portfolio_id=portfolio.id).count()
        print(f"Portfolio: {portfolio.name} (id={portfolio.id}) - existing transactions: {before}")

        # if not append:
        #     deleted = session.query(Transaction).filter_by(portfolio_id=portfolio.id).delete(synchronize_session=False)
        #     session.commit()
        #     print(f"Deleted transactions: {deleted}")

        importer = XtbImporter(session)
        for file_path in files:
            print(f"Importing from: {file_path}")
            importer.import_transactions(file_path, portfolio)

        after = session.query(Transaction).filter_by(portfolio_id=portfolio.id).count()
        print(f"Import complete. Transactions now: {after}")
        return {"files": files, "before": before, "after": after}

    finally:
        session.close()


def main():
    """Command-line interface for re-importing."""
    parser = argparse.ArgumentParser(description="Purge transactions and re-import from XTB XLSX file(s).")
    parser.add_argument("--file", required=False, nargs="+", help="Path(s) to XTB XLSX file(s). If not provided, finds all XLSX files in the current directory.")
    parser.add_argument("--portfolio", required=False, help="Portfolio name (defaults to 'XTB').")
    parser.add_argument("--append", action="store_true", help="Append to existing transactions (do not purge).")
    args = parser.parse_args()

    files_to_import = args.file
    if not files_to_import:
        files_to_import = find_all_xtb_files()
        if not files_to_import:
            print("Error: No file specified and could not find any XLSX files in the current directory.")
            return

    db = Database()
    session = db.Session()
    try:
        portfolio = get_or_create_portfolio(session, args.portfolio)
        before = session.query(Transaction).filter_by(portfolio_id=portfolio.id).count()
        print(f"Portfolio: {portfolio.name} (id={portfolio.id}) - existing transactions: {before}")

        # if not args.append:
        #     deleted = session.query(Transaction).filter_by(portfolio_id=portfolio.id).delete(synchronize_session=False)
        #     session.commit()
        #     print(f"Deleted transactions: {deleted}")

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

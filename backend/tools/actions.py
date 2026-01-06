"""Module for reusable scraping actions."""

from backend.config import Config
from backend.database import Database, Portfolio, Ticker
from backend.scraper import Scraper
from backend.scraper.providers.strefa_investorow_provider import StrefaInwestorowProvider
from backend.portfolio.importer import XtbImporter


def run_ticker_scraper(ticker: str, page_from: int = 0, page_to: int = 4):
    """
    Runs the ticker scraping process for Strefa Inwestorow.

    Args:
        ticker: The ticker symbol to scrape for.
        page_from: The starting page number.
        page_to: The ending page number.
    
    Returns:
        A dictionary with the scraping statistics.
    """
    # config = Config()
    db = Database()
    
    # Get ticker object to check for scrape_url
    session = db.Session()
    ticker_obj = session.query(Ticker).filter(Ticker.ticker == ticker).first()
    
    company_name = None
    scrape_url = None
    
    if ticker_obj:
        company_name = ticker_obj.company_name
        scrape_url = ticker_obj.scrape_url
    
    session.close()

    if not company_name:
        db.close()
        return {"error": f"Ticker '{ticker}' not found in the database."}

    if scrape_url:
        print(f"Using custom scrape URL for {ticker}: {scrape_url}")
        provider = StrefaInwestorowProvider(base_url=scrape_url)
    else:
        provider = StrefaInwestorowProvider()
        
    scraper = Scraper(db)
    
    try:
        # Pass scrape_url to indicate we are using a specific URL (implies we might want to relax name filtering)
        stats = scraper.scrape_ticker(provider, company_name, page_from, page_to, use_custom_url=bool(scrape_url))
        scraper.print_summary()
        return stats
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"An error occurred: {e}"}
    finally:
        db.close()


def import_xtb_transactions(file_path: str, portfolio_name: str = "My XTB Portfolio"):
    """
    Imports transactions from an XTB XLSX file into a specified portfolio.

    Args:
        file_path: The path to the XLSX file.
        portfolio_name: The name of the portfolio to import into.

    Returns:
        A dictionary with the import statistics or an error message.
    """
    db = Database()
    session = db.Session()
    try:
        # Find or create the portfolio
        portfolio = session.query(Portfolio).filter_by(name=portfolio_name).first()
        if not portfolio:
            portfolio = Portfolio(name=portfolio_name, broker="XTB")
            session.add(portfolio)
            session.commit()

        importer = XtbImporter(session)
        importer.import_transactions(file_path, portfolio)
        
        return {"status": "success", "message": f"Transactions imported successfully into portfolio '{portfolio_name}'."}

    except Exception as e:
        session.rollback()
        return {"error": f"An error occurred during import: {e}"}
    finally:
        session.close()
        db.close()

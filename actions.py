"""Module for reusable scraping actions."""

from config import Config
from database import Database
from scraper import Scraper
from providers.strefa_investorow_provider import StrefaInwestorowProvider

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
    company_name = db.get_company_name_by_ticker(ticker)

    if not company_name:
        db.close()
        return {"error": f"Ticker '{ticker}' not found in the database."}

    provider = StrefaInwestorowProvider()
    scraper = Scraper(db)
    
    try:
        stats = scraper.scrape_ticker(provider, company_name, page_from, page_to)
        scraper.print_summary()
        return stats
    except Exception as e:
        return {"error": f"An error occurred: {e}"}
    finally:
        db.close()

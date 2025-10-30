"""Simple test script for the news scraper."""

from datetime import date, datetime
from database import Database
from config import Config

def test_database():
    """Test database operations."""
    print("Testing database operations...")
    
    db = Database('test_news.db')
    
    # Test existence check
    print("\n1. Testing existence check...")
    exists = db.exists("https://example.com/test")
    print(f"   URL exists: {exists}")
    
    from providers.base_provider import NewsArticle
    
    # Test adding article
    print("\n2. Testing article addition...")
    article = NewsArticle(
        title="Test Article",
        url="https://example.com/test",
        source="test",
        date=date.today()
    )
    article.content = "Test content"
    
    db_article = db.add_article(article)
    print(f"   Added article with ID: {db_article.id}")
    print(f"   Title: {db_article.title}")
    
    # Test existence check again
    print("\n3. Testing existence check after addition...")
    exists = db.exists("https://example.com/test")
    print(f"   URL exists: {exists}")
    
    print("\n✓ Database test completed!")


def test_config():
    """Test configuration loading."""
    print("\n" + "="*60)
    print("Testing configuration...")
    print("="*60)
    
    config = Config()
    
    print(f"\nDatabase path: {config.db_path}")
    print(f"Providers: {config.providers}")
    print(f"Scrape hour: {config.scrape_hour}:{config.scrape_minute}")
    print(f"Yesterday: {config.get_yesterday_date()}")
    
    print("\n✓ Configuration test completed!")


if __name__ == '__main__':
    print("="*60)
    print("NEWS MONITOR - TEST SUITE")
    print("="*60)
    
    test_config()
    test_database()
    
    print("\n" + "="*60)
    print("ALL TESTS COMPLETED")
    print("="*60)







"""Simple script to view scraped news articles from the database."""

from database import Database
from config import Config

def main():
    config = Config()
    db = Database(config.db_path)
    
    session = db.Session()
    try:
        from database import NewsArticle
        
        # Get all articles
        articles = session.query(NewsArticle).all()
        
        if not articles:
            print("\nDatabase is empty. Run the scraper first:")
            print("  python3 main.py")
            return
        
        print("\n" + "="*80)
        print(f"SCRAPED NEWS ARTICLES - TOTAL: {len(articles)}")
        print("="*80)
        
        # Group by source
        sources = {}
        for article in articles:
            if article.source not in sources:
                sources[article.source] = []
            sources[article.source].append(article)
        
        for source, source_articles in sources.items():
            print(f"\n{source.upper()}: {len(source_articles)} articles")
            print("-" * 80)
            
            for i, article in enumerate(source_articles[:10], 1):  # Show first 10
                print(f"{i}. {article.title[:70]}")
                print(f"   URL: {article.url}")
                print(f"   Date: {article.date} | Scraped: {article.scraped_at}")
                if article.content:
                    print(f"   Content: {len(article.content)} characters")
                print()
            
            if len(source_articles) > 10:
                print(f"   ... and {len(source_articles) - 10} more articles")
        
        # Show date coverage
        dates = sorted(set([a.date for a in articles if a.date]))
        if dates:
            print(f"\n{'='*80}")
            print(f"DATES COVERED: {dates[0]} to {dates[-1]}")
            print(f"Total dates: {len(dates)}")
        
    finally:
        session.close()
        db.close()

if __name__ == '__main__':
    main()







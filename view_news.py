"""View scraped news articles from the database."""

import sys
from database import Database
from config import Config


def view_all_articles(limit=None):
    """View all articles in the database."""
    config = Config()
    db = Database(config.db_path)
    
    session = db.Session()
    try:
        query = session.query(db.engine.metadata.tables['news_articles'])
        if limit:
            query = query.limit(limit)
        articles = query.all()
        
        print("\n" + "="*80)
        print(f"SCRAPED NEWS ARTICLES")
        print("="*80)
        print(f"\nTotal articles: {len(articles)}\n")
        
        for i, article in enumerate(articles, 1):
            print(f"{i}. [{article.source}] {article.title[:70]}")
            print(f"   URL: {article.url}")
            print(f"   Date: {article.date}")
            print(f"   Scraped: {article.scraped_at}")
            print(f"   Content length: {len(article.content) if article.content else 0} chars")
            print()
        
    finally:
        session.close()
        db.close()


def view_by_source(source, limit=None):
    """View articles by source."""
    config = Config()
    db = Database(config.db_path)
    
    articles = db.get_articles_by_source(source, limit)
    
    print("\n" + "="*80)
    print(f"ARTICLES FROM: {source.upper()}")
    print("="*80)
    print(f"\nTotal: {len(articles)}\n")
    
    for i, article in enumerate(articles, 1):
        print(f"{i}. {article.title[:70]}")
        print(f"   {article.url}")
        print(f"   {article.date} | {article.scraped_at}")
        print()
    
    db.close()


def view_by_date(date_str):
    """View articles by date."""
    from datetime import datetime
    
    config = Config()
    db = Database(config.db_path)
    
    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    articles = db.get_articles_by_date(date_obj)
    
    print("\n" + "="*80)
    print(f"ARTICLES FROM: {date_str}")
    print("="*80)
    print(f"\nTotal: {len(articles)}\n")
    
    for i, article in enumerate(articles, 1):
        print(f"{i}. [{article.source}] {article.title[:70]}")
        print(f"   {article.url}")
        print()
    
    db.close()


def stats():
    """Show database statistics."""
    config = Config()
    db = Database(config.db_path)
    
    session = db.Session()
    try:
        from database import NewsArticle
        
        total = session.query(NewsArticle).count()
        
        # Count by source
        sources = session.query(NewsArticle.source).distinct().all()
        source_counts = {}
        for source in sources:
            count = session.query(NewsArticle).filter(NewsArticle.source == source[0]).count()
            source_counts[source[0]] = count
        
        print("\n" + "="*80)
        print("DATABASE STATISTICS")
        print("="*80)
        print(f"\nTotal articles: {total}")
        print(f"\nBy source:")
        for source, count in source_counts.items():
            print(f"  {source}: {count}")
        
        # Count by date
        if total > 0:
            dates = session.query(NewsArticle.date).distinct().all()
            print(f"\nDates covered: {len([d for d in dates if d[0]])}")
            if dates:
                print("\nRecent dates:")
                for date_obj in sorted([d[0] for d in dates if d[0]], reverse=True)[:5]:
                    count = session.query(NewsArticle).filter(NewsArticle.date == date_obj).count()
                    print(f"  {date_obj}: {count} articles")
        
    finally:
        session.close()
        db.close()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        stats()
        print("\n" + "="*80)
        print("USAGE:")
        print("  python3 view_news.py stats          - Show statistics")
        print("  python3 view_news.py all            - View all articles")
        print("  python3 view_news.py all --limit 10 - View first 10 articles")
        print("  python3 view_news.py source pap     - View articles from PAP")
        print("  python3 view_news.py date 2025-10-25 - View articles from specific date")
        print("="*80)
        return
    
    command = sys.argv[1]
    
    if command == 'stats':
        stats()
    elif command == 'all':
        limit = None
        if '--limit' in sys.argv:
            idx = sys.argv.index('--limit')
            if idx + 1 < len(sys.argv):
                limit = int(sys.argv[idx + 1])
        view_all_articles(limit)
    elif command == 'source' and len(sys.argv) > 2:
        source = sys.argv[2]
        limit = None
        if '--limit' in sys.argv:
            idx = sys.argv.index('--limit')
            if idx + 1 < len(sys.argv):
                limit = int(sys.argv[idx + 1])
        view_by_source(source, limit)
    elif command == 'date' and len(sys.argv) > 2:
        date_str = sys.argv[2]
        view_by_date(date_str)
    else:
        print("Unknown command. Use: python3 view_news.py")


if __name__ == '__main__':
    main()







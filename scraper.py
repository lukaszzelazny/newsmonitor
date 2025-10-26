"""Main scraper orchestration logic."""

from typing import List, Optional
from datetime import date, datetime
from providers.base_provider import BaseProvider, NewsArticle
from database import Database


class Scraper:
    """Main scraper orchestrator."""
    
    def __init__(self, db: Database):
        self.db = db
        self.scraped_count = 0
        self.skipped_count = 0
        self.errors = []
    
    def scrape_provider(self, provider: BaseProvider, target_date: Optional[date] = None) -> dict:
        """
        Scrape articles from a provider.
        
        Args:
            provider: News provider instance
            target_date: Optional target date to filter articles
        
        Returns:
            Dictionary with scraping statistics
        """
        print(f"\n{'='*60}")
        print(f"Scraping from: {provider.name}")
        print(f"Base URL: {provider.base_url}")
        print(f"{'='*60}")
        
        total_articles = 0
        new_articles = 0
        skipped_articles = 0
        
        try:
            # Get total pages
            total_pages = provider.get_total_pages(target_date)
            print(f"Total pages to check: {total_pages}")
            
            # Iterate through pages
            for page_num in range(total_pages):
                print(f"\nProcessing page {page_num + 1}/{total_pages}...")
                
                # Get articles from current page
                articles = provider.get_articles_for_page(page_num)
                
                if not articles:
                    print(f"No articles found on page {page_num}")
                    break
                
                # Process each article
                for article in articles:
                    total_articles += 1
                    
                    # Check if already exists
                    if self.db.exists(article.url):
                        skipped_articles += 1
                        print(f"  ✓ Skipped (already exists): {article.title[:60]}")
                        continue
                    
                    # Fetch article content and date
                    print(f"  → Fetching: {article.title[:60]}")
                    article.content = provider.get_article_content(article)
                    
                    # Filter by date if target_date is specified (after getting date from content)
                    if target_date:
                        if not article.date or article.date != target_date:
                            skipped_articles += 1
                            print(f"    ✓ Skipped (date mismatch: {article.date})")
                            continue
                    
                    if article.content:
                        # Save to database
                        self.db.add_article(article)
                        new_articles += 1
                        print(f"    ✓ Saved")
                    else:
                        print(f"    ✗ Failed to fetch content")
                
                # Stop if we've collected enough articles for the target date
                # and we're getting articles from a different date
                if target_date and articles:
                    dates_found = {a.date for a in articles if a.date}
                    if dates_found and target_date not in dates_found:
                        print(f"\nReached beyond target date {target_date}. Stopping.")
                        break
        
        except Exception as e:
            print(f"\n✗ Error scraping from {provider.name}: {e}")
            self.errors.append(f"{provider.name}: {str(e)}")
        
        stats = {
            'provider': provider.name,
            'total_checked': total_articles,
            'new_articles': new_articles,
            'skipped_articles': skipped_articles
        }
        
        return stats
    
    def scrape_range(self, provider: BaseProvider, start_date: date, end_date: date):
        """Scrape articles for a date range."""
        current_date = start_date
        
        while current_date <= end_date:
            print(f"\n{'='*80}")
            print(f"Processing date: {current_date}")
            print(f"{'='*80}")
            
            stats = self.scrape_provider(provider, current_date)
            
            # Move to next date
            from datetime import timedelta
            current_date += timedelta(days=1)
    
    def print_summary(self):
        """Print scraping summary."""
        print(f"\n{'='*60}")
        print("SCRAPING SUMMARY")
        print(f"{'='*60}")
        
        if self.errors:
            print(f"\nErrors: {len(self.errors)}")
            for error in self.errors:
                print(f"  - {error}")
        
        print(f"\nFinished at: {datetime.now()}")
        print(f"{'='*60}")





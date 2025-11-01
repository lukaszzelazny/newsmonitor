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
    
    def scrape_provider(self, provider: BaseProvider, page_from: int = 0, page_to: int = 49) -> dict:
        """
        Scrape articles from a provider within a page range.

        Args:
            provider: News provider instance
            page_from: Start page number (inclusive)
            page_to: End page number (inclusive)

        Returns:
            Dictionary with scraping statistics
        """
        print(f"\n{'='*60}")
        print(f"Scraping from: {provider.name}")
        print(f"Base URL: {provider.base_url}")
        print(f"Page range: {page_from} to {page_to}")
        print(f"{'='*60}")

        total_articles = 0
        new_articles = 0
        skipped_articles = 0

        try:
            total_pages = page_to - page_from + 1
            print(f"Total pages to scrape: {total_pages}")

            # Iterate through specified page range
            for page_num in range(page_from, page_to + 1):
                print(f"\nProcessing page {page_num} ({page_num - page_from + 1}/{total_pages})...")

                # Get articles from current page
                articles = provider.get_articles_for_page(page_num)

                if not articles:
                    print(f"No articles found on page {page_num}")
                    continue

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
                    article.content = provider.clean_content(provider.get_article_content(article))

                    if article.content:
                        # Save to database
                        self.db.add_article(article)
                        new_articles += 1
                        date_str = f" ({article.date})" if article.date else ""
                        print(f"    ✓ Saved{date_str}")
                    else:
                        print(f"    ✗ Failed to fetch content")

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
    
    def scrape_provider_range(self, provider: BaseProvider, start_date: date, end_date: date) -> dict:
        """Scrape articles within an inclusive date range [start_date, end_date]."""
        print(f"\n{'='*60}")
        print(f"Scraping from: {provider.name}")
        print(f"Base URL: {provider.base_url}")
        print(f"{'='*60}")

        total_articles = 0
        new_articles = 0
        skipped_articles = 0

        try:
            total_pages = provider.get_total_pages(None)
            print(f"Total pages to check: {total_pages}")

            for page_num in range(total_pages):
                print(f"\nProcessing page {page_num + 1}/{total_pages}...")

                articles = provider.get_articles_for_page(page_num)
                if not articles:
                    print(f"No articles found on page {page_num}")
                    break

                # For early-stop heuristic, compute page date bounds after fetching content
                page_dates = []

                for article in articles:
                    total_articles += 1

                    if self.db.exists(article.url):
                        skipped_articles += 1
                        # print(f"  ✓ Skipped (already exists): {article.title[:60]}")
                        continue

                    # Fetch content and infer date
                    print(f"  → Fetching: {article.title[:60]}")
                    article.content = provider.get_article_content(article)
                    if article.date:
                        page_dates.append(article.date)

                    # Save only if date is within range
                    if article.content and article.date and (start_date <= article.date <= end_date):
                        self.db.add_article(article)
                        new_articles += 1
                        print(f"    ✓ Saved ({article.date})")
                    else:
                        skipped_articles += 1
                        print(f"    ✓ Skipped (out of range or no content/date: {article.date})")

                # Early stop: if the newest on page is older than start_date, remaining pages will be older
                if page_dates:
                    newest_on_page = max(page_dates)
                    if newest_on_page < start_date:
                        print(f"\nReached dates older than start {start_date} (newest on page: {newest_on_page}). Stopping.")
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





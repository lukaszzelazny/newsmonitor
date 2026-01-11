"""Main scraper orchestration logic."""

import re
from typing import List, Optional
from datetime import date, datetime
from .providers import BaseProvider, NewsArticle
from backend.database import Database
from backend.ai.ai_analist import analyze_articles, is_article_analyzed, contains_pattern, NEGATIVE_KEYWORDS, save_not_analyzed, is_potential_contract


class Scraper:
    """Main scraper orchestrator."""
    
    def __init__(self, db: Database, telegram=None):
        self.db = db
        self.scraped_count = 0
        self.skipped_count = 0
        self.errors = []
        self.telegram = telegram
    
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
                        print(f"  [OK] Skipped (already exists): {article.title[:60]}")
                        continue

                    # Fetch article content and date
                    print(f"  -> Fetching: {article.title[:60]}")
                    article.content = provider.clean_content(provider.get_article_content(article))

                    if article.content:
                        # Save to database
                        self.db.add_article(article)
                        new_articles += 1
                        date_str = f" ({article.date})" if article.date else ""
                        print(f"    [OK] Saved{date_str}")
                    else:
                        print(f"    [X] Failed to fetch content")

        except Exception as e:
            print(f"\n[X] Error scraping from {provider.name}: {e}")
            self.errors.append(f"{provider.name}: {str(e)}")

        stats = {
            'provider': provider.name,
            'total_checked': total_articles,
            'new_articles': new_articles,
            'skipped_articles': skipped_articles
        }

        return stats

    def scrape_recommendations(self, provider: BaseProvider) -> dict:
        """
        Scrape brokerage recommendations from a provider.

        Args:
            provider: Recommendations provider instance

        Returns:
            Dictionary with scraping statistics
        """
        print(f"\n{'='*60}")
        print(f"Scraping recommendations from: {provider.name}")
        print(f"Base URL: {provider.base_url}")
        print(f"{'='*60}")

        total_recommendations = 0
        new_recommendations = 0
        skipped_recommendations = 0

        try:
            # Fetch the single page
            html = provider.fetch_page(0)

            if not html:
                print("[X] Failed to fetch recommendations page")
                return {
                    'provider': provider.name,
                    'total_recommendations': 0,
                    'new_recommendations': 0,
                    'skipped_recommendations': 0
                }

            # Parse recommendations
            recommendations = provider.parse_articles(html)

            if not recommendations:
                print("No recommendations found")
                return {
                    'provider': provider.name,
                    'total_recommendations': 0,
                    'new_recommendations': 0,
                    'skipped_recommendations': 0
                }

            print(f"\nFound {len(recommendations)} recommendations")

            # Process each recommendation
            for rec_data in recommendations:
                total_recommendations += 1

                # Generate unique identifier for this recommendation
                external_id = rec_data.get('external_id')

                # Check if already exists
                if self.db.exists_recommendation(external_id):
                    skipped_recommendations += 1
                    print(f"  [OK] Skipped (already exists): {rec_data['title'][:60]}")
                    continue

                # Save to database
                print(f"  -> Processing: {rec_data['title'][:60]}")

                try:
                    self.telegram.send_brokerage_alert(brokerage_house=rec_data.get('brokerage_house'),
                                                       price_old=rec_data.get('price_old').replace('zł', ''),
                                                       price_new=rec_data.get('price_new').replace('zł', ''),
                                                       recommendation=rec_data.get('price_recommendation'),
                                                       ticker=rec_data.get('ticker'),
                                                       title=rec_data.get('external_id')
                                                       )
                    rec_id = self.db.add_recommendation(rec_data)
                    if rec_id:
                        new_recommendations += 1
                        print(f"    [OK] Saved (ID: {rec_id})")
                    else:
                        print(f"    [X] Failed to save")
                except Exception as e:
                    print(f"    [X] Error saving: {e}")
                    self.errors.append(f"Recommendation {rec_data['title']}: {str(e)}")

        except Exception as e:
            print(f"\n[X] Error scraping recommendations: {e}")
            self.errors.append(f"{provider.name}: {str(e)}")

        stats = {
            'provider': provider.name,
            'total_recommendations': total_recommendations,
            'new_recommendations': new_recommendations,
            'skipped_recommendations': skipped_recommendations
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
                        continue

                    # Fetch content and infer date
                    print(f"  -> Fetching: {article.title[:60]}")
                    article.content = provider.get_article_content(article)
                    if article.date:
                        page_dates.append(article.date)

                    # Save only if date is within range
                    if article.content and article.date and (start_date <= article.date <= end_date):
                        self.db.add_article(article)
                        new_articles += 1
                        print(f"    [OK] Saved ({article.date})")
                    else:
                        skipped_articles += 1
                        print(f"    [OK] Skipped (out of range or no content/date: {article.date})")

                # Early stop: if the newest on page is older than start_date, remaining pages will be older
                if page_dates:
                    newest_on_page = max(page_dates)
                    if newest_on_page < start_date:
                        print(f"\nReached dates older than start {start_date} (newest on page: {newest_on_page}). Stopping.")
                        break

        except Exception as e:
            print(f"\n[X] Error scraping from {provider.name}: {e}")
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

    def scrape_ticker(self, provider: BaseProvider, company_name: str, page_from: int = 0, page_to: int = 4, use_custom_url: bool = False, stop_at_existing: bool = False, scrape_type: str = 'all') -> dict:
        """
        Scrape articles for a specific company.
        """
        # Simplify company name for better matching
        simple_company_name = company_name.replace(" SA", "").replace(" S.A.", "").strip()
        print(f"\n{'='*60}")
        print(f"Scraping for: {simple_company_name} (Original: {company_name})")
        print(f"Provider: {provider.name}")
        print(f"Page range: {page_from} to {page_to}")
        print(f"Using Custom URL: {use_custom_url}")
        print(f"Stop at existing: {stop_at_existing}")
        print(f"Scrape Type: {scrape_type}")
        print(f"{'='*60}")

        total_articles = 0
        new_articles = 0
        skipped_articles = 0
        found_articles = 0
        should_stop = False

        try:
            total_pages = page_to - page_from + 1
            print(f"Total pages to scrape: {total_pages}")

            for page_num in range(page_from, page_to + 1):
                if should_stop:
                    break
                print(f"\nProcessing page {page_num} ({page_num - page_from + 1}/{total_pages})...")
                articles = provider.get_articles_for_page(page_num)

                if not articles:
                    print(f"No articles found on page {page_num}")
                    continue

                for article in articles:
                    total_articles += 1

                    # Use regex with word boundaries for precise matching
                    pattern = r'\b' + re.escape(simple_company_name.lower()) + r'\b'
                    
                    is_match = False
                    
                    # If using custom URL, we assume all articles are relevant, but we might still check name if needed.
                    # However, users usually set custom URL to a ticker-specific page (e.g. news for a specific stock).
                    # So we can be more lenient or skip name check.
                    if use_custom_url:
                        is_match = True
                        print(f"  -> Matched (Custom URL): {article.title[:60]}")
                    else:
                        title_match = re.search(pattern, article.title.lower())
                        
                        # Fetch content once
                        if not article.content:
                            article.content = provider.clean_content(provider.get_article_content(article))

                        content_match = None
                        if article.content:
                            content_match = re.search(pattern, article.content.lower())
                            
                        if title_match or content_match:
                            is_match = True

                    if is_match:
                        # 0. Check scrape_type logic
                        if scrape_type == 'contracts':
                            is_contract_potential, contract_score = is_potential_contract(article.title)
                            if not is_contract_potential:
                                print(f"  - Skipped (not a contract, score={contract_score:.4f}): {article.title[:60]}")
                                continue
                            else:
                                print(f"  + Potential contract found (score={contract_score:.4f}): {article.title[:60]}")

                        # Fetch content if not fetched yet
                        if not article.content:
                            article.content = provider.clean_content(provider.get_article_content(article))
                        # 1. Check for negative keywords
                        has_negative, keyword = contains_pattern(NEGATIVE_KEYWORDS, article.title, article.content or "")
                        if has_negative:
                            print(f"  - Skipped (negative keyword '{keyword}'): {article.title[:60]}")
                            if not self.db.exists(article.url):
                                db_article = self.db.add_article(article)
                                save_not_analyzed(self.db, db_article.id, f"Contains negative keyword: '{keyword}'", 0.0)
                            continue

                        # 2. Process the article if no negative keywords
                        existing_article = self.db.get_article_by_url(article.url)
                        if existing_article:
                            is_analyzed = is_article_analyzed(self.db, existing_article.id)
                            
                            if stop_at_existing and is_analyzed:
                                print(f"  [OK] Stopping at existing ANALYZED article: {article.title[:60]}")
                                should_stop = True
                                break
                            
                            if not is_analyzed:
                                print(f"  -> Analyzing existing (unanalyzed) article ID: {existing_article.id}")
                                analyze_articles(self.db, mode='id', article_id=existing_article.id, skip_relevance_check=True)
                            else:
                                skipped_articles += 1
                                print(f"  [OK] Skipped (already exists and analyzed): {article.title[:60]}")
                        else:  # New article
                            if article.content:
                                db_article = self.db.add_article(article)
                                new_articles += 1
                                date_str = f" ({article.date})" if article.date else ""
                                print(f"    [OK] Saved{date_str} with ID: {db_article.id}")
                                
                                # Trigger AI analysis
                                print(f"    -> Triggering AI analysis for article ID: {db_article.id}")
                                analyze_articles(self.db, mode='id', article_id=db_article.id, skip_relevance_check=True)
                            else:
                                print(f"    [X] Failed to fetch content for new article")

        except Exception as e:
            print(f"\n[X] Error scraping for {company_name}: {e}")
            self.errors.append(f"{company_name}: {str(e)}")

        stats = {
            'provider': provider.name,
            'company_name': company_name,
            'total_checked': total_articles,
            'new_articles': new_articles,
            'skipped_articles': skipped_articles
        }
        return stats

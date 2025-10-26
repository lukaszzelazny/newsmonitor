"""Base interface for news providers."""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import date


class NewsArticle:
    """Represents a single news article."""
    
    def __init__(self, title: str, url: str, source: str, date: Optional[date] = None):
        self.title = title
        self.url = url
        self.source = source
        self.date = date
        self.content = None
        self.scraped_at = None


class BaseProvider(ABC):
    """Base interface for news providers."""
    
    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url
    
    @abstractmethod
    def get_articles_for_page(self, page: int) -> List[NewsArticle]:
        """
        Scrape articles from a specific page.
        
        Args:
            page: Page number (usually 0-indexed)
        
        Returns:
            List of NewsArticle objects
        """
        pass
    
    @abstractmethod
    def get_article_content(self, article: NewsArticle) -> str:
        """
        Fetch the full content of an article.
        
        Args:
            article: NewsArticle with title and url
        
        Returns:
            Full article content as string
        """
        pass
    
    @abstractmethod
    def get_total_pages(self, target_date: Optional[date] = None) -> int:
        """
        Determine total number of pages to scrape.
        
        Args:
            target_date: Optional date to filter pages
        
        Returns:
            Total number of pages
        """
        pass
    
    def filter_articles_by_date(self, articles: List[NewsArticle], target_date: date) -> List[NewsArticle]:
        """
        Filter articles by date (override for custom date filtering).
        
        Args:
            articles: List of articles to filter
            target_date: Target date for filtering
        
        Returns:
            Filtered list of articles
        """
        return [article for article in articles if article.date and article.date == target_date]





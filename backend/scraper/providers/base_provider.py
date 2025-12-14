"""Base interface for news providers."""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import date, datetime
import re

class NewsArticle:
    """Represents a single news article."""
    
    def __init__(self, title: str, url: str, source: str, date: Optional[date] = None, published_at: Optional[datetime] = None):
        self.title = title
        self.url = url
        self.source = source
        self.date = date
        self.published_at = published_at
        self.content = None
        self.scraped_at = None


class BaseProvider(ABC):
    """Base interface for news providers."""
    
    # Rozszerzone wzorce szumu do usunięcia
    NOISE_PATTERNS = [
        # Prawa autorskie - różne warianty
        r'Wszelkie materiały.*?(?:\n|$)',
        r'Materiał chroniony prawem autorskim.*?\.(?:\s|$)',
        r'©.*?Wszelkie prawa zastrzeżone.*?\.(?:\s|$)',
        r'Kopiowanie.*?bez zgody.*?zabronione.*?\.(?:\s|$)',
        r'Redakcja nie ponosi odpowiedzialności.*?\.(?:\s|$)',
        
        # Źródła i agencje
        r'Źródło:.*?(?:PAP|TVN|Onet|Interia|wp\.pl).*?(?:\n|$)',
        r'\(źródło:.*?\)(?:\s|$)',
        r'Autor:.*?(?:\n|$)',
        r'Fot\..*?(?:\n|$)',
        
        # Linki wewnętrzne i call-to-action
        r'Czytaj też:.*?(?=\n\n|\n[A-ZĄĆĘŁŃÓŚŹŻ]|\Z)',
        r'Zobacz też:.*?(?=\n\n|\n[A-ZĄĆĘŁŃÓŚŹŻ]|\Z)',
        r'Polecamy:.*?(?=\n\n|\n[A-ZĄĆĘŁŃÓŚŹŻ]|\Z)',
        r'Czytaj więcej:.*?(?=\n\n|\n[A-ZĄĆĘŁŃÓŚŹŻ]|\Z)',
        r'>>>.*?<<<',
        r'\[.*?\]',  # Linki w nawiasach kwadratowych
        
        # Reklamy i content marketing
        r'REKLAMA.*?(?:\n|$)',
        r'Czytaj więcej na.*?(?:\n|$)',
        r'Subskrybuj.*?(?:\n|$)',
        r'Dołącz do.*?(?:\n|$)',
        r'Śledź nas.*?(?:\n|$)',
        
        # Informacje redakcyjne
        r'Redakcja.*?(?:\n|$)',
        r'Aktualizacja:.*?(?:\n|$)',
        r'Opublikowano:.*?(?:\n|$)',
        
        r'Udostępnij.*?(?:\n|$)',
        r'Podziel się.*?(?:\n|$)',
        r'konsensus\s+tworzony\s+jest\s+na\s+podstawie\s+prognoz\s+biur\s+maklerskich.*pap\s+biznes'

    ]
    
    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url
    
    def clean_content(self, content: str) -> str:
        """Remove noise patterns from article content."""
        if not content:
            return content
        
        cleaned = content
        
        # Usuń wzorce szumu
        for pattern in self.NOISE_PATTERNS:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE | re.DOTALL)
        
        # Usuń nadmiarowe białe znaki
        cleaned = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned)  # Maksymalnie 2 newline
        cleaned = re.sub(r' +', ' ', cleaned)  # Wiele spacji -> jedna
        cleaned = re.sub(r'\t+', ' ', cleaned)  # Tabulatory -> spacja
        
        # Usuń białe znaki na początku i końcu linii
        lines = cleaned.split('\n')
        lines = [line.strip() for line in lines if line.strip()]
        cleaned = '\n\n'.join(lines)
        
        return cleaned.strip()
    
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
        
        IMPORTANT: This method should call self.clean_content() before returning
        to ensure content is cleaned.
        
        Args:
            article: NewsArticle with title and url
        
        Returns:
            Full article content as string (cleaned)
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

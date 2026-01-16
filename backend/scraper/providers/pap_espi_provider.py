"""PAP ESPI news provider."""

import requests
from bs4 import BeautifulSoup
from typing import List, Optional
from datetime import date, datetime
import time
import re

from .base_provider import BaseProvider, NewsArticle


class PapEspiProvider(BaseProvider):
    """Scraper for PAP ESPI reports."""
    
    def __init__(self, base_url: str):
        # Allow overriding base_url for specific company queries
        super().__init__("pap_espi", base_url)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_articles_for_page(self, page: int) -> List[NewsArticle]:
        """Scrape articles from a specific page."""
        try:
            # Handle pagination
            sep = '&' if '?' in self.base_url else '?'
            url = f"{self.base_url}{sep}page={page}"
            
            print(f"Fetching ESPI page: {url}")
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            articles = []
            
            # Find the main table or list containing reports
            # Usually ESPI reports are in a table
            
            # Strategy 1: Look for table with specific class or structure
            # Strategy 2: Look for links that look like report links
            
            all_links = soup.find_all('a', href=True)
            
            for link in all_links:
                href = link.get('href', '')
                title = link.get_text(strip=True)
                
                # Filter relevant links
                # ESPI links often contain '/espi/' or match the pattern
                if href and ('/espi/' in href or '/wiadomosci/' in href):
                    # Filter out purely navigation links if possible
                    if title and len(title) >= 10: 
                        # Convert relative URL to absolute
                        if not href.startswith('http'):
                            href = f"https://biznes.pap.pl{href}"
                        
                        # Try to extract date from nearby elements (often in the same row)
                        article_date = None
                        row = link.find_parent('tr')
                        if row:
                            # Try to find date in the row cells
                            cells = row.find_all('td')
                            for cell in cells:
                                text = cell.get_text(strip=True)
                                # Check for date pattern YYYY-MM-DD
                                match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
                                if match:
                                    try:
                                        article_date = datetime.strptime(match.group(1), '%Y-%m-%d').date()
                                        break
                                    except ValueError:
                                        pass

                        article = NewsArticle(
                            title=title,
                            url=href,
                            source=self.name,
                            date=article_date
                        )
                        articles.append(article)
            
            # Deduplicate
            seen_urls = set()
            unique_articles = []
            for art in articles:
                if art.url not in seen_urls:
                    seen_urls.add(art.url)
                    unique_articles.append(art)
            
            time.sleep(0.5)
            return unique_articles

        except requests.RequestException as e:
            print(f"Error fetching from {url}: {e}")
            return []

    def get_article_content(self, article: NewsArticle) -> str:
        """Fetch the full content of an article."""
        try:
            response = self.session.get(article.url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Try to refine date if not set
            if not article.date:
                # Look for date in common places
                date_elem = soup.find('div', class_='publicationDate') or soup.find('time')
                if date_elem:
                    text = date_elem.get_text(strip=True)
                    match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
                    if match:
                        try:
                            article.date = datetime.strptime(match.group(1), '%Y-%m-%d').date()
                        except ValueError:
                            pass

            # Find content
            # ESPI reports often have specific containers
            content_elem = (
                soup.find('div', class_='report-content') or
                soup.find('div', class_='field--name-body') or
                soup.find('div', class_='content') or
                soup.find('div', id='article-body') or
                soup.find('article')
            )
            
            if content_elem:
                # Clean up
                for tag in content_elem.find_all(['script', 'style', 'nav', 'header', 'footer']):
                    tag.decompose()
                
                text = content_elem.get_text(separator='\n', strip=True)
                return text
            
            return ""

        except requests.RequestException as e:
            print(f"Error fetching article content from {article.url}: {e}")
            return ""

    def get_total_pages(self, target_date: Optional[date] = None) -> int:
        """Determine total number of pages."""
        # Simple heuristic
        return 10

"""PAP (Polska Agencja Prasowa) news provider."""

import requests
from bs4 import BeautifulSoup
from typing import List, Optional
from datetime import date
import time
import re

from providers.base_provider import BaseProvider, NewsArticle


class PAPProvider(BaseProvider):
    """Scraper for PAP news website."""
    
    def __init__(self, base_url: str = "https://biznes.pap.pl/kategoria/depesze-pap"):
        super().__init__("pap", base_url)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_articles_for_page(self, page: int) -> List[NewsArticle]:
        """Scrape articles from a specific page."""
        # First get direct news from the URL
        direct_articles = self._scrape_from_url(f"{self.base_url}?page={page}")
        # Also scrape subcategories to increase coverage
        sub_articles = self._scrape_from_subcategories(page)

        # Deduplicate by URL
        seen_urls = set()
        merged: List[NewsArticle] = []
        for art in direct_articles + sub_articles:
            if art.url not in seen_urls:
                seen_urls.add(art.url)
                merged.append(art)
        
        return merged
    
    def _scrape_from_url(self, url: str) -> List[NewsArticle]:
        """Scrape articles directly from a URL."""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            articles = []
            
            # Find all links to news articles
            all_links = soup.find_all('a', href=True)
            
            for link in all_links:
                href = link.get('href', '')
                title = link.get_text(strip=True)

                # Only process actual news articles
                if href and '/kategoria/' not in href and re.search(r'/wiadomosci/', href):
                    if title and len(title) >= 15 and len(title.split()) >= 3:
                        # Convert relative URL to absolute
                        if not href.startswith('http'):
                            href = f"https://biznes.pap.pl{href}"

                        article = NewsArticle(
                            title=title,
                            url=href,
                            source=self.name,
                            date=None
                        )
                        articles.append(article)
            
            # Small delay to be polite
            time.sleep(0.5)
            
            return articles
        
        except requests.RequestException as e:
            print(f"Error fetching from {url}: {e}")
            return []
    
    def _scrape_from_subcategories(self, page: int) -> List[NewsArticle]:
        """Scrape articles from subcategories of a category page."""
        try:
            url = f"{self.base_url}?page={page}"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            articles = []
            
            # Find links to subcategories (like /kategoria/firmy, /kategoria/rynki)
            subcategory_links = soup.find_all('a', href=lambda x: x and '/kategoria/' in x and self.base_url not in x)
            
            # Visit each subcategory to get actual news
            # Visit more subcategories to improve coverage, but cap to avoid excess requests
            for link in subcategory_links[:10]:
                subcategory_url = link['href']
                if not subcategory_url.startswith('http'):
                    subcategory_url = f"https://biznes.pap.pl{subcategory_url}"
                # Ensure we request the same page index for subcategories (if supported)
                if 'page=' not in subcategory_url:
                    sep = '&' if '?' in subcategory_url else '?'
                    subcategory_url = f"{subcategory_url}{sep}page={page}"

                print(f"  Scraping from subcategory: {subcategory_url}")
                sub_articles = self._scrape_from_url(subcategory_url)
                articles.extend(sub_articles)
                
                if len(articles) >= 100:  # Limit total articles per page
                    break
            
            return articles
        
        except requests.RequestException as e:
            print(f"Error scraping subcategories: {e}")
            return []
    
    def _extract_date(self, element) -> Optional[date]:
        """Extract date from article element."""
        # Try to find time element or date-related elements
        date_elem = (
            element.find('time') or 
            element.find(class_=lambda x: x and 'date' in x.lower()) or
            element.find_parent().find('time') if element.find_parent() else None
        )
        
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            # Try to parse date
            try:
                from datetime import datetime
                for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y']:
                    try:
                        return datetime.strptime(date_text, fmt).date()
                    except ValueError:
                        continue
            except:
                pass
        
        return None
    
    def get_article_content(self, article: NewsArticle) -> str:
        """Fetch the full content of an article."""
        try:
            response = self.session.get(article.url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Extract date from publication date field
            from datetime import datetime
            import re
            
            # Try to find the publicationDate div (PAP specific)
            date_elem = soup.find('div', class_='publicationDate')
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                # Extract just the date part (format: "Publikacja: 2025-10-26 19:19" or "2025-10-26 19:19")
                match = re.search(r'(\d{4}-\d{2}-\d{2})', date_text)
                if match:
                    date_str = match.group(1)
                    try:
                        article.date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except ValueError:
                        pass
            
            # If not found, try alternative selectors
            if not article.date:
                date_elem = soup.find('time')
                if date_elem:
                    date_text = date_elem.get_text(strip=True)
                    match = re.search(r'(\d{4}-\d{2}-\d{2})', date_text)
                    if match:
                        date_str = match.group(1)
                        try:
                            article.date = datetime.strptime(date_str, '%Y-%m-%d').date()
                        except ValueError:
                            pass
            
            # Last resort: search for date patterns in article metadata
            if not article.date:
                main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content')
                if main_content:
                    # Look for "Publikacja:" text and get the date from same element
                    publikacja_elem = main_content.find(text=re.compile('Publikacja', re.I))
                    if publikacja_elem and publikacja_elem.parent:
                        parent_text = publikacja_elem.parent.get_text(strip=True) if publikacja_elem.parent else ""
                        # Also check grandparent
                        if not parent_text and publikacja_elem.parent.parent:
                            parent_text = publikacja_elem.parent.parent.get_text(strip=True)
                        
                        match = re.search(r'(\d{4}-\d{2}-\d{2})', parent_text)
                        if match:
                            date_str = match.group(1)
                            try:
                                article.date = datetime.strptime(date_str, '%Y-%m-%d').date()
                            except ValueError:
                                pass
            
            # PAP structure: content is usually in divs with article body
            # Try multiple possible selectors
            content_elem = (
                soup.find('div', class_='field--name-body') or
                soup.find('div', class_=lambda x: x and 'body' in str(x).lower()) or
                soup.find('div', class_='content') or
                soup.find('article') or
                soup.find('main')
            )
            
            if content_elem:
                # Remove unwanted elements
                for elem in content_elem.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                    elem.decompose()
                
                # Remove social media buttons, ads, etc.
                for elem in content_elem.find_all('div', class_=lambda x: x and any(
                    word in str(x).lower() for word in ['ad', 'social', 'share', 'comment']
                )):
                    elem.decompose()
                
                # Get text content - use get_text() directly to avoid duplication
                # This extracts text from all elements but avoids recursive nested extraction
                full_text = content_elem.get_text(separator='\n', strip=True)
                
                # Split into lines and deduplicate consecutive identical lines
                lines = full_text.split('\n')
                filtered_lines = []
                
                for line in lines:
                    line = line.strip()
                    if line and len(line) > 20:  # Filter out very short texts
                        # Only add if it's not a duplicate of the previous line
                        if not filtered_lines or line != filtered_lines[-1]:
                            filtered_lines.append(line)
                
                content = '\n\n'.join(filtered_lines)
                return content
            
            return ""
        
        except requests.RequestException as e:
            print(f"Error fetching article content from {article.url}: {e}")
            return ""
    
    def get_total_pages(self, target_date: Optional[date] = None) -> int:
        """
        Determine total number of pages to scrape.
        Since we don't know the exact number, we'll use a reasonable default
        and implement pagination detection.
        """
        # Try to fetch first page to determine pagination
        try:
            url = f"{self.base_url}?page=0"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Look for pagination info
            pagination = soup.find(class_='pagination')
            if pagination:
                page_links = pagination.find_all('a')
                page_numbers = []
                
                for link in page_links:
                    page_num = re.search(r'page=(\d+)', link.get('href', ''))
                    if page_num:
                        page_numbers.append(int(page_num.group(1)))
                
                if page_numbers:
                    # Ensure we check sufficiently deep pages; min 50 to cover ranges
                    return max(max(page_numbers) + 1, 50)
            
            # Default to checking first 50 pages if pagination not found
            return 50
        
        except requests.RequestException:
            # Return default if request fails
            return 50


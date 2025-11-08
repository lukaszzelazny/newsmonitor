"""Strefa Inwestorów news provider."""

import requests
from bs4 import BeautifulSoup
from typing import List, Optional
from datetime import date, datetime
import time
import re

from providers.base_provider import BaseProvider, NewsArticle


class StrefaInwestorowProvider(BaseProvider):
    """Scraper for Strefa Inwestorów news website."""

    def __init__(self, base_url: str = "https://strefainwestorow.pl/wiadomosci"):
        super().__init__("strefainwestorow", base_url)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def get_articles_for_page(self, page: int) -> List[NewsArticle]:
        """Scrape articles from a specific page."""
        try:
            url = f"{self.base_url}?page={page}"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'lxml')
            articles = []

            # Find all links to news articles
            all_links = soup.find_all('a', href=True)

            for link in all_links:
                href = link.get('href', '')
                title = link.get_text(strip=True)

                # Only process actual news articles (format: /wiadomosci/YYYYMMDD/...)
                if href and re.search(r'/wiadomosci/\d{8}/', href):
                    if title and len(title) >= 15 and len(title.split()) >= 3:
                        # Convert relative URL to absolute
                        if not href.startswith('http'):
                            href = f"https://strefainwestorow.pl{href}"

                        # Extract date from URL
                        date_match = re.search(r'/wiadomosci/(\d{4})(\d{2})(\d{2})/', href)
                        article_date = None
                        if date_match:
                            try:
                                year, month, day = date_match.groups()
                                article_date = date(int(year), int(month), int(day))
                            except ValueError:
                                pass

                        article = NewsArticle(
                            title=title,
                            url=href,
                            source=self.name,
                            date=article_date
                        )
                        articles.append(article)

            # Remove duplicates by URL
            seen_urls = set()
            unique_articles = []
            for article in articles:
                if article.url not in seen_urls:
                    seen_urls.add(article.url)
                    unique_articles.append(article)

            # Small delay to be polite
            time.sleep(0.5)

            return unique_articles

        except requests.RequestException as e:
            print(f"Error fetching from {url}: {e}")
            return []

    def _format_table(self, table) -> str:
        """Format HTML table to readable text preserving structure."""
        rows = []

        # Process all rows (from thead, tbody, tfoot)
        for row in table.find_all('tr'):
            cells = []
            for cell in row.find_all(['th', 'td']):
                cell_text = cell.get_text(strip=True)
                cells.append(cell_text)

            if cells:
                # Join cells with pipe separator
                rows.append(' | '.join(cells))

        # Join rows with newlines
        return '\n'.join(rows)

    def get_article_content(self, article: NewsArticle) -> str:
        """Fetch the full content of an article."""
        try:
            response = self.session.get(article.url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'lxml')

            # If date wasn't extracted from URL, try to find it in the article
            if not article.date:
                # Try to find date in various formats
                date_patterns = [
                    (r'(\d{2})\s+(stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|października|listopada|grudnia)\s+(\d{4})', 'polish'),
                    (r'(\d{4})-(\d{2})-(\d{2})', 'iso'),
                    (r'(\d{2})\.(\d{2})\.(\d{4})', 'dots'),
                ]

                page_text = soup.get_text()
                for pattern, fmt in date_patterns:
                    match = re.search(pattern, page_text)
                    if match:
                        try:
                            if fmt == 'polish':
                                day, month_name, year = match.groups()
                                months = {
                                    'stycznia': 1, 'lutego': 2, 'marca': 3, 'kwietnia': 4,
                                    'maja': 5, 'czerwca': 6, 'lipca': 7, 'sierpnia': 8,
                                    'września': 9, 'października': 10, 'listopada': 11, 'grudnia': 12
                                }
                                article.date = date(int(year), months[month_name], int(day))
                                break
                            elif fmt == 'iso':
                                year, month, day = match.groups()
                                article.date = date(int(year), int(month), int(day))
                                break
                            elif fmt == 'dots':
                                day, month, year = match.groups()
                                article.date = date(int(year), int(month), int(day))
                                break
                        except (ValueError, KeyError):
                            continue

            # Find the main content area
            # Try multiple possible selectors for Strefa Inwestorów structure
            content_elem = None

            # Step 1: Try to find the main content div using specific Drupal-related classes or IDs.
            # This list is ordered by specificity and likelihood of containing the main article text.
            content_selectors = [
                # Most common Drupal content fields
                {'name': 'div', 'attrs': {'class': 'field--name-field-body'}},
                {'name': 'div', 'attrs': {'class': 'field--name-body'}},
                {'name': 'div', 'attrs': {'class': 'field-name-body'}}, # Older Drupal versions
                {'name': 'div', 'attrs': {'property': 'content:encoded'}}, # Schema.org content
                {'name': 'div', 'attrs': {'class': 'node__content'}}, # Generic node content wrapper
                {'name': 'div', 'attrs': {'class': 'field--type-text-with-summary'}}, # Text field with summary
                # More general content containers
                {'name': 'div', 'attrs': {'class': 'article-content'}}, # Common article content class
                {'name': 'div', 'attrs': {'class': 'post-content'}}, # Common post content class
                {'name': 'div', 'attrs': {'class': 'entry-content'}}, # Common entry content class
                {'name': 'div', 'attrs': {'class': 'td-post-content'}}, # Specific to some themes
                {'name': 'div', 'attrs': {'class': 'td-pb-span8'}}, # Specific to some themes (often wraps content)
                {'name': 'div', 'attrs': {'class': 'td-post-content-wrap'}}, # Specific to some themes
                {'name': 'div', 'attrs': {'id': 'content'}}, # Generic ID for content
                {'name': 'main'}, # HTML5 main element
            ]

            content_elem = None
            for selector in content_selectors:
                content_elem = soup.find(selector['name'], selector['attrs'])
                if content_elem:
                    print(f"Found content using specific selector: {selector['name']} with {selector['attrs']}")
                    break

            # Step 2: If not found, try to find an <article> tag and then look for content within it.
            if not content_elem:
                article_tag = soup.find('article')
                if article_tag:
                    # Look for common content divs within the article tag
                    content_elem = article_tag.find('div', class_=lambda x: x and ('content' in str(x).lower() or 'body' in str(x).lower() or 'text' in str(x).lower()))
                    if not content_elem:
                        content_elem = article_tag # If no specific div, use the article tag itself
                    print(f"Found content within <article> tag.")

            # Step 3: Last resort - find a div with an ID starting with 'node-' (common Drupal node ID)
            if not content_elem:
                content_elem = soup.find('div', id=lambda x: x and x.startswith('node-'))
                if content_elem:
                    print(f"Found content using 'node-' ID.")

            # Step 4: If still no content element, log an error and return empty.
            if not content_elem:
                print(f"ERROR: Could not find content container for URL: {article.url}")
                return ""

            print(f"Content element identified: {content_elem.name}, id={content_elem.get('id')}, classes={content_elem.get('class', [])}")

            # Remove unwanted elements (scripts, styles, and potentially ads/social share buttons)
            # This should be done *after* identifying the main content_elem to avoid removing too much.
            for unwanted_tag in content_elem.find_all(['script', 'style', 'aside', 'nav', 'footer', 'header']):
                unwanted_tag.decompose()

            # Also remove common ad/social share divs that might be inside the content
            for ad_div in content_elem.find_all('div', class_=lambda x: x and any(c in x for c in ['ad', 'share', 'social', 'related-posts', 'wp-block-columns'])):
                ad_div.decompose()

            # Initialize table_texts list
            table_texts = []

            # Special handling for tables - check if there are actual <table> tags
            tables = content_elem.find_all('table')
            if tables:
                print(f"Found {len(tables)} HTML tables")
                # Process each table to ensure we get all cell data
                for idx, table in enumerate(tables):
                    # Check if table has data
                    cells = table.find_all(['td', 'th'])
                    print(f"  Table {idx+1} has {len(cells)} cells")

                    # Format table properly
                    formatted_table = self._format_table(table)
                    table_texts.append(formatted_table)
                    print(f"  Formatted table preview: {formatted_table[:200]}")

            # Check for <pre> tags which might contain formatted tables
            pre_tags = content_elem.find_all('pre')
            if pre_tags:
                print(f"Found {len(pre_tags)} <pre> tags (might contain tables)")
                for pre in pre_tags:
                    pre_text = pre.get_text(strip=True)
                    if '|' in pre_text:
                        table_texts.append(pre_text)

            # Get text content
            full_text = content_elem.get_text(separator='\n', strip=True)

            # If we extracted tables separately, append them to ensure they're included
            if table_texts:
                full_text = full_text + '\n\n' + '\n\n'.join(table_texts)

            # Get text content from the identified content element
            # Use get_text with a separator to ensure paragraphs are distinct
            full_text = content_elem.get_text(separator='\n', strip=True)

            # If we extracted tables separately, append them to ensure they're included
            if table_texts:
                full_text = full_text + '\n\n' + '\n\n'.join(table_texts)

            print(f"Full text length after initial cleanup: {len(full_text)}")

            # Fallback if the primary content element yielded too little text
            if not full_text or len(full_text) < 100: # Increased threshold for "too short"
                print("WARNING: Content from specific element is too short. Trying to get all visible text from page.")
                # Remove scripts and styles from the entire soup before getting all text
                for elem in soup.find_all(['script', 'style']):
                    elem.decompose()
                full_text = soup.get_text(separator='\n', strip=True)
                print(f"Full page text length (fallback): {len(full_text)}")

            # Split into lines for further processing
            lines = full_text.split('\n')
            print(f"Total lines before final filtering: {len(lines)}")
            processed_lines = []

            # Define phrases that indicate non-content sections (e.g., navigation, footer, ads)
            # Make this list more comprehensive and case-insensitive.
            # Removed 'pap biznes', '(pap)', 'pap' from skip_phrases as they can be part of legitimate content.
            skip_phrases = [
                'przejdź do treści', 'menu', 'nawigacja', 'strona główna',
                'twitter feed', 'najpopularniejsze tagi', 'footer', 'polityka prywatności',
                'copyrights', 'strefainwestorow.pl', 'strefa global', 'w zielonej strefie',
                'rekomendacje', 'czytaj więcej', 'konta użytkownika', 'główna nawigacja',
                'debiut, ipo', 'blog inwestorski', 'reklama', 'partnerzy', 'newsletter',
                'zobacz także', 'podobne artykuły', 'komentarze', 'udostępnij', 'źródło:',
                'tagi:', 'autor:', 'data publikacji:', 'wszystkie prawa zastrzeżone',
                'regulamin', 'kontakt', 'o nas', 'do góry', 'powrót', 'szukaj', 'wyszukaj',
                'zaloguj', 'zarejestruj', 'subskrybuj', 'polub nas', 'obserwuj nas',
                'zobacz również', 'więcej na ten temat', 'polecane artykuły', 'najnowsze wiadomości'
            ]

            # A more robust filtering approach:
            # 1. Remove empty lines and strip whitespace.
            # 2. Filter out lines that are clearly navigation/footer/ads.
            # 3. Keep lines that are reasonably long or part of a table.
            # 4. Introduce a minimum content length check after filtering.
            for line in lines:
                line = line.strip()

                if not line:
                    continue

                line_lower = line.lower()

                # Skip lines that are very short and likely not content (e.g., single words, numbers)
                # unless they contain alphanumeric characters or are part of a table.
                if len(line) < 5 and not any(char.isalpha() for char in line) and not ('|' in line):
                    continue

                # Skip lines containing known non-content phrases
                if any(phrase in line_lower for phrase in skip_phrases):
                    continue

                # Heuristic to identify potential table lines (contains '|')
                is_table_line_current = '|' in line

                # Keep the line if it's a table line or if it's reasonably long (e.g., > 15 characters)
                # The threshold is lowered to be more inclusive for shorter but meaningful sentences.
                if is_table_line_current or len(line) > 15:
                    # Avoid adding consecutive duplicate lines
                    if not processed_lines or line != processed_lines[-1]:
                        processed_lines.append(line)

            content = '\n\n'.join(processed_lines)
            print(f"Final content length after filtering: {len(content)}")
            print(f"Lines kept: {len(processed_lines)}")

            # Final check: if filtered content is too short, use the raw full_text as a fallback.
            # This is crucial for articles that are inherently short (e.g., brief news flashes).
            if len(content) < 100 and len(full_text) > 100: # If filtered content is very short but raw text was substantial
                print("WARNING: Filtered content is too short. Returning raw full_text as a fallback.")
                content = full_text
            elif not content and full_text: # If filtering removed everything, but full_text had content
                print("WARNING: Filtering removed all content. Returning raw full_text as a fallback.")
                content = full_text

            return content

        except requests.RequestException as e:
            print(f"Error fetching article content from {article.url}: {e}")
            return ""

    def get_total_pages(self, target_date: Optional[date] = None) -> int:
        """
        Determine total number of pages to scrape.
        """
        try:
            url = f"{self.base_url}?page=0"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'lxml')

            # Look for pagination info - try to find "Ostatnia strona" (Last page) link
            pagination_links = soup.find_all('a', href=lambda x: x and 'page=' in str(x))
            max_page = 0

            for link in pagination_links:
                href = link.get('href', '')
                page_match = re.search(r'page=(\d+)', href)
                if page_match:
                    page_num = int(page_match.group(1))
                    max_page = max(max_page, page_num)

                # Check for "Ostatnia strona" text which indicates the last page
                if 'ostatnia' in link.get_text().lower():
                    href = link.get('href', '')
                    page_match = re.search(r'page=(\d+)', href)
                    if page_match:
                        return int(page_match.group(1)) + 1

            # If we found pagination, return max page + some buffer
            if max_page > 0:
                return max(max_page + 1, 50)

            # Default to checking first 50 pages if pagination not found
            return 50

        except requests.RequestException:
            # Return default if request fails
            return 50
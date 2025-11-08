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

            # Strefa Inwestorów używa Drupala - szukajmy właściwych klas
            # Najpierw spróbuj bardzo specyficznych selektorów dla treści artykułu
            for selector in [
                ('div', {'class': 'field--name-field-body'}),
                ('div', {'class': 'field--name-body'}),
                ('div', {'class': 'field-name-body'}),
                ('div', {'property': 'content:encoded'}),
                ('div', {'class': 'node__content'}),
                ('div', {'class': 'field--type-text-with-summary'}),
            ]:
                content_elem = soup.find(selector[0], selector[1])
                if content_elem:
                    print(f"Found content using: {selector}")
                    break

            # Jeśli nie znaleziono, szukaj po atrybucie class zawierającym "field"
            if not content_elem:
                content_elem = soup.find('div', class_=lambda x: x and 'field--name' in ' '.join(x) if isinstance(x, list) else 'field--name' in str(x))
                if content_elem:
                    print(f"Found content using field--name class")

            # Spróbuj znaleźć główny article node
            if not content_elem:
                article = soup.find('article')
                if article:
                    # W article szukaj diva z treścią
                    content_elem = article.find('div', class_=lambda x: x and ('content' in str(x).lower() or 'body' in str(x).lower()))
                    if not content_elem:
                        content_elem = article
                    print(f"Found content in article tag")

            # Ostateczna deskwa ratunku - znajdź div z ID node-
            if not content_elem:
                content_elem = soup.find('div', id=lambda x: x and x.startswith('node-'))
                if content_elem:
                    print(f"Found content using node- id")

            if not content_elem:
                print("ERROR: Could not find content container!")
                return ""

            print(f"Content element: {content_elem.name}, id={content_elem.get('id')}, classes={content_elem.get('class', [])}")
            # Remove unwanted elements - MINIMAL removal to preserve content
            # Only remove scripts and styles - nothing else!
            for elem in content_elem.find_all(['script', 'style']):
                elem.decompose()

            # Remove unwanted elements - MINIMAL removal to preserve content
            # Only remove scripts and styles - nothing else!
            for elem in content_elem.find_all(['script', 'style']):
                elem.decompose()

            # Special handling for tables - check if there are actual <table> tags
            tables = content_elem.find_all('table')
            table_texts = []
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

            print(f"Full text length after cleanup: {len(full_text)}")

            if not full_text or len(full_text) < 50:
                print("ERROR: No content found or content too short!")
                print("Trying to get all text from soup...")
                # Last resort - get all visible text from page
                for elem in soup.find_all(['script', 'style']):
                    elem.decompose()
                full_text = soup.get_text(separator='\n', strip=True)
                print(f"Full page text length: {len(full_text)}")

            # Split into lines and filter - minimal filtering to preserve tables
            lines = full_text.split('\n')
            print(f"Total lines before filtering: {len(lines)}")
            filtered_lines = []

            # Words that indicate navigation/footer/menu (to skip)
            skip_phrases = [
                'przejdź do treści', 'menu', 'nawigacja', 'strona główna',
                'twitter feed', 'najpopularniejsze tagi', 'footer',
                'polityka prywatności', 'copyrights', 'strefainwestorow.pl',
                'strefa global', 'w zielonej strefie', 'rekomendacje',
                'czytaj więcej', 'konta użytkownika', 'główna nawigacja',
                'debiut, ipo', 'blog inwestorski'
            ]

            in_article_content = False
            article_started = False

            for i, line in enumerate(lines):
                line = line.strip()

                if not line:
                    continue

                line_lower = line.lower()

                # Skip navigation/menu lines
                if any(phrase in line_lower for phrase in skip_phrases):
                    continue

                # Detect start of actual article (after title)
                # Look for "Poniżej przedstawiamy" or similar intro text
                if not article_started and len(line) > 30 and ('poniżej' in line_lower or 'przedstawiamy' in line_lower):
                    article_started = True
                    in_article_content = True

                # If we see "(PAP Biznes)" we might be at the end
                if '(pap biznes)' in line_lower or '(pap)' in line_lower:
                    filtered_lines.append(line)
                    in_article_content = False
                    # Don't break - there might be more content
                    continue

                # Skip very short lines before article starts
                if not article_started and len(line) < 20:
                    continue

                # Once in article, be more permissive
                if article_started or in_article_content:
                    # Check next and previous lines for table context
                    next_line = lines[i+1].strip() if i+1 < len(lines) else ""
                    prev_line = lines[i-1].strip() if i > 0 else ""

                    # Keep line if:
                    # 1. It contains table separator |
                    # 2. It's reasonably long (>10 chars)
                    # 3. It's near a table line
                    is_table_line = '|' in line
                    is_near_table = '|' in next_line or '|' in prev_line
                    is_long_enough = len(line) > 10
                    is_table_context = is_near_table and len(line) > 3

                    should_keep = is_table_line or is_long_enough or is_table_context

                    # Avoid consecutive duplicates
                    if should_keep and (not filtered_lines or line != filtered_lines[-1]):
                        filtered_lines.append(line)

            content = '\n\n'.join(filtered_lines)
            print(f"Final content length: {len(content)}")
            print(f"Lines kept: {len(filtered_lines)}")

            if '|' in content:
                table_lines = [l for l in filtered_lines if '|' in l]
                print(f"Table lines found: {len(table_lines)}")

            return content

            print("ERROR: No content element found at all!")
            return ""

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
"""Provider for Strefa Inwestorow recommendations."""

from datetime import datetime, date
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import requests

from providers.base_provider import BaseProvider, NewsArticle


class RekomendacjeProvider(BaseProvider):
    """Provider for scraping brokerage recommendations from Strefa Inwestorow."""

    def get_article_content(self, article: NewsArticle) -> str:
        """Not used for recommendations."""
        return ""

    def get_total_pages(self, target_date: Optional[date] = None) -> int:
        """Always returns 1 for recommendations (single page)."""
        return 1

    def __init__(self):
        """Initialize the recommendations provider."""
        super().__init__(
            name="StrefaInwestorow_Rekomendacje",
            base_url="https://strefainwestorow.pl/rekomendacje/lista-rekomendacji"
        )
        # Define headers for HTTP requests - DON'T request gzip encoding
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

    def fetch_page(self, page: int = 0) -> Optional[str]:
        """
        Fetch the recommendations page.

        Args:
            page: Page number (ignored, only one page exists)

        Returns:
            HTML content or None if fetch fails
        """
        try:
            # Requests automatically handles gzip/deflate if we don't manually set Accept-Encoding
            response = requests.get(
                self.base_url,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()

            # Ensure we get text, not bytes
            response.encoding = response.apparent_encoding or 'utf-8'

            return response.text
        except requests.RequestException as e:
            print(f"Error fetching {self.base_url}: {e}")
            return None

    def parse_articles(self, html: str) -> List[Dict]:
        """
        Parse recommendations from HTML.

        Args:
            html: HTML content

        Returns:
            List of recommendation dictionaries
        """
        soup = BeautifulSoup(html, 'html.parser')
        recommendations = []

        # Find the table with class 'table-recommendations-desktop'
        table = soup.find('table', class_='table-recommendations-desktop')

        if not table:
            # Try alternative selector
            table = soup.find('table', class_='table-hover')

        if not table:
            print("Warning: Recommendations table not found")
            # Debug: print available tables
            all_tables = soup.find_all('table')
            print(f"Found {len(all_tables)} tables on page")
            if all_tables:
                for i, t in enumerate(all_tables[:3]):
                    print(f"Table {i+1} classes:", t.get('class'))
            return recommendations

        # Find tbody
        tbody = table.find('tbody')
        if not tbody:
            print("Warning: Table body not found")
            return recommendations

        # Find all rows
        rows = tbody.find_all('tr')
        print(f"Found {len(rows)} recommendation rows")

        # Parse each row
        for row in rows:
            try:
                rec = self._parse_row(row)
                if rec:
                    recommendations.append(rec)
            except Exception as e:
                print(f"Error parsing row: {e}")
                continue

        return recommendations

    def _parse_row(self, row) -> Optional[Dict]:
        """
        Parse a single table row into a recommendation dictionary.

        Table structure:
        0: Spółka (Company name + ticker)
        1: Rodzaj (Type: Kupuj/Trzymaj/Sprzedaj)
        2: Cena aktualna (Current price)
        3: Cena docelowa (Target price)
        4: Potencjał zmiany ceny (Price change potential)
        5: Cena w dniu publikacji (Price at publication)
        6: Instytucja (Institution/Brokerage)
        7: Data publikacji (Publication date)
        8: Raport (Report link)

        Args:
            row: BeautifulSoup table row element

        Returns:
            Dictionary with recommendation data or None
        """
        cols = row.find_all('td')
        if len(cols) < 8:
            return None

        try:
            # Column 0: Company name and ticker
            company_cell = cols[0]
            company_link = company_cell.find('a')
            if company_link:
                company_text = company_link.get_text(strip=True)
            else:
                company_text = company_cell.get_text(strip=True)

            # Extract ticker from text like "DOMDEV (DOM)"
            ticker = self._extract_ticker_from_text(company_text)
            company_name = company_text.split('(')[0].strip() if '(' in company_text else company_text

            # Column 1: Recommendation type (Kupuj, Trzymaj, Sprzedaj)
            recommendation_type = cols[1].get_text(strip=True)

            # Column 2: Current price (not needed for our purposes)
            # Column 3: Target price
            target_price = cols[3].get_text(strip=True).replace(' zł', '').replace(' ', '').replace(',', '.')

            # Column 5: Price at publication date
            price_at_publication = cols[5].get_text(strip=True).replace(' zł', '').replace(' ', '').replace(',', '.')

            # Column 6: Institution/Brokerage house
            brokerage_house = cols[6].get_text(strip=True)

            # Column 7: Publication date
            date_str = cols[7].get_text(strip=True)
            pub_date = self._parse_date(date_str)

            # Create recommendation dictionary
            return {
                'title': f"{company_name} - Rekomendacja {brokerage_house}",
                'url': self.base_url,
                'published_date': pub_date,
                'source': self.name,
                'external_id': self._generate_external_id(date_str, ticker, brokerage_house),
                # Additional fields for brokerage analysis
                'ticker': ticker,
                'brokerage_house': brokerage_house,
                'price_old': price_at_publication if price_at_publication else None,
                'price_new': target_price if target_price else None,
                'price_recommendation': recommendation_type,
                'price_comment': None
            }
        except Exception as e:
            print(f"Error parsing row details: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _extract_ticker_from_text(self, text: str) -> Optional[str]:
        """
        Extract ticker from text like "DOMDEV (DOM)" or "ABPL (ABE)".

        Args:
            text: Text containing company name and ticker

        Returns:
            Ticker symbol or None
        """
        if '(' in text and ')' in text:
            start = text.find('(') + 1
            end = text.find(')')
            ticker = text[start:end].strip()
            if ticker and len(ticker) <= 10:
                return ticker.upper()
        return None

    def _parse_date(self, date_str: str) -> datetime:
        """
        Parse date string to datetime object.
        Format: DD-MM-YYYY (e.g., "07-11-2025")

        Args:
            date_str: Date string

        Returns:
            datetime object
        """
        if not date_str:
            return datetime.now()

        date_str = date_str.strip()

        # Try different date formats
        formats = [
            '%d-%m-%Y',
            '%d.%m.%Y',
            '%Y-%m-%d',
            '%d/%m/%Y',
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # Fallback to current date
        print(f"Warning: Could not parse date '{date_str}', using current date")
        return datetime.now()

    def _generate_external_id(self, date_str: str, ticker: Optional[str],
                            brokerage: str) -> str:
        """
        Generate unique external ID for the recommendation.

        Args:
            date_str: Date string
            ticker: Company ticker
            brokerage: Brokerage house name

        Returns:
            Unique identifier string
        """
        ticker_part = ticker if ticker else "UNKNOWN"
        # Clean brokerage name for ID
        brokerage_clean = brokerage.replace(' ', '_').replace('.', '').replace(',', '')[:20]
        # Clean date for ID
        date_clean = date_str.replace('-', '').replace('.', '').replace('/', '')
        return f"REC_{date_clean}_{ticker_part}_{brokerage_clean}"

    def has_next_page(self, page: int, html: str) -> bool:
        """
        Check if there is a next page (always False for recommendations).

        Args:
            page: Current page number
            html: HTML content

        Returns:
            Always False (single page only)
        """
        return False

    def get_articles_for_page(self, page: int) -> List[Dict]:
        """
        Get recommendations for a page (only page 0 is valid).

        Args:
            page: Page number (should be 0)

        Returns:
            List of recommendation dictionaries
        """
        if page != 0:
            return []

        html = self.fetch_page(page)
        if not html:
            return []

        return self.parse_articles(html)
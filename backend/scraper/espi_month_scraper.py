import argparse
import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime, timedelta
import re
import sys
import os
import calendar

def scrape_espi_month(year: int, month: int):
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    # Calculate start and end date of the month
    start_date = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(year, month)[1]
    end_date = f"{year}-{month:02d}-{last_day}%2023%3A59"
    
    base_url = "https://espiebi.pap.pl/wyszukiwarka"
    
    page = 0
    results = []
    
    while True:
        url = f"{base_url}?created={start_date}&enddate={end_date}&page={page}"
        print(f"Fetching {url}...")
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            break
            
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        # Reports are grouped by day: div class="day"
        days = soup.find_all('div', class_='day')
        if not days:
            print("No days found on page. We reached the end or no reports exist.")
            break
            
        items_on_page = 0
        
        for day_div in days:
            date_h2 = day_div.find('h2', class_='date')
            if not date_h2:
                continue
            date_str = date_h2.get_text(strip=True)
            
            news_list = day_div.find('ul', class_='newsList')
            if not news_list:
                continue
                
            for news_item in news_list.find_all('li', class_='news'):
                # Extract ESPI or EBI badge
                badge_div = news_item.find('div', class_='badge')
                badge = badge_div.get_text(strip=True) if badge_div else ""
                
                # Check if it's ESPI
                if badge != "ESPI" and "ESPI" not in badge:
                    continue
                    
                hours_divs = news_item.find_all('div', class_='hour')
                time_val = hours_divs[0].get_text(strip=True) if len(hours_divs) > 0 else ""
                number = hours_divs[1].get_text(strip=True) if len(hours_divs) > 1 else ""
                
                link_tag = news_item.find('a', class_='link')
                if not link_tag:
                    continue
                    
                full_text = link_tag.get_text(strip=True)
                # Parse "COMPANY S.A. - Tytuł komunikatu"
                company = ""
                title = full_text
                if " - " in full_text:
                    parts = full_text.split(" - ", 1)
                    company = parts[0].strip()
                    title = parts[1].strip()
                    
                href = link_tag.get('href', '')
                if not href.startswith('http'):
                    link = f"https://espiebi.pap.pl{href}"
                else:
                    link = href
                    
                content = ""
                # Fetch full content
                time.sleep(0.1)
                try:
                    c_resp = session.get(link, timeout=15)
                    if c_resp.status_code == 200:
                        c_soup = BeautifulSoup(c_resp.content, 'html.parser')
                        node = c_soup.find('div', class_='node__content')
                        if node:
                            # Prefer specific field body XML if available
                            xml_content = node.find('div', class_='field-body-xml-content')
                            if xml_content:
                                content = xml_content.get_text(separator=' ', strip=True)
                            else:
                                for tag in node.find_all(class_=re.compile(r'field--name-field-report-type|footer|link|breadcrumb|pager')):
                                    tag.decompose()
                                content = node.get_text(separator='\n', strip=True)
                            
                            # Clean up start of report if it contains standard PKO/URSUS metadata
                            idx = content.find('RAPORT BIEŻĄCY')
                            if idx != -1:
                                content = content[idx:].strip()
                                
                            idx = content.find('MESSAGE (POLISH VERSION)')
                            if idx != -1:
                                content = content[idx + len('MESSAGE (POLISH VERSION)'):].strip()
                            elif 'MESSAGE (ENGLISH VERSION)' in content:
                                content = content.split('MESSAGE (ENGLISH VERSION)', 1)[0].strip()
                except Exception as e:
                    print(f"Error fetching article content {link}: {e}", file=sys.stderr)
                    
                results.append({
                    "data": date_str,
                    "godzina": time_val,
                    "numer": number,
                    "firma": company,
                    "tytuł": title,
                    "treść": content,
                    "link": link
                })
                items_on_page += 1
                
        print(f"Scraped {items_on_page} ESPI reports from page {page}")
        
        # Check if there is a 'Następna strona' (Next page) link
        next_page = False
        nav = soup.find('ul', class_='pagination')
        if nav:
            for l in nav.find_all('a', href=True):
                if 'page=' in l['href'] and ('Nast' in l.get_text() or '›' in l.get_text()):
                    next_page = True
                    break
        
        if not next_page:
            print("No 'Next page' link found. Stopping.")
            break
            
        page += 1
        time.sleep(1)

    output_file = f"espi_{year}_{month:02d}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
        
    print(f"Done. Successfully saved {len(results)} records to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape ESPI reports for a specific year and month to JSON")
    parser.add_argument("--year", type=int, required=True, help="Year to scrape (e.g. 2020)")
    parser.add_argument("--month", type=int, required=True, help="Month to scrape (1-12)")
    args = parser.parse_args()
    scrape_espi_month(args.year, args.month)

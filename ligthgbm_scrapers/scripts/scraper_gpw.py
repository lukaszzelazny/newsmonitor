import os
import json
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.biznesradar.pl"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "raw_data")
OUT_FILE = os.path.join(OUT_DIR, "tickers_gpw.json")

def fetch_profile_data(session, ticker, profile_url):
    print(f"[{ticker}] Fetching profile...")
    try:
        r = session.get(BASE_URL + profile_url, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        sector = ""
        ekd = ""
        indices = []
        isin = "" # Not easily available on Biznesradar without extra lists
        
        profile_table = soup.find('table', class_='profileSummary')
        if profile_table:
            rows = profile_table.find_all('tr')
            for row in rows:
                th = row.find('th')
                if th and "Sektor" in th.text:
                    td = row.find('td')
                    if td:
                        sector = td.text.strip().replace("Sektor:", "").strip()
        
        indices_div = soup.find(string=lambda x: x and "Wchodzi w skład indeksów:" in x)
        if indices_div and indices_div.parent:
            links = indices_div.parent.find_all('a')
            indices = [a.text.strip() for a in links]
            
        return {
            "sector": sector,
            "indices": indices,
            "ekd": ekd,
            "isin": isin
        }
    except Exception as e:
        print(f"[{ticker}] Error fetching profile: {e}")
        return {"sector": "", "indices": [], "ekd": "", "isin": ""}

def main():
    print("Fetching company list from Biznesradar...")
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    
    r = session.get(f"{BASE_URL}/gielda/akcje_gpw", timeout=15)
    soup = BeautifulSoup(r.text, 'html.parser')
    
    table = soup.find('table', class_='table--accent-header')
    if not table:
         table = soup.find('table') # fallback
         
    rows = table.find_all('tr')[1:] # skip header
    
    final_data = []
    total_rows = len(rows)
    print(f"Found {total_rows} companies.")
    
    for i, row in enumerate(rows):
        tds = row.find_all('td')
        if not tds: continue
        
        a_tag = tds[0].find('a')
        if not a_tag: continue
        
        text = a_tag.text.strip()
        title = a_tag.get('title', '').strip()
        href = a_tag.get('href', "")
        
        if "(" in text and ")" in text:
            ticker = text.split(" ")[0].strip()
            name_short = text.split("(")[1].replace(")", "").strip()
        else:
            ticker = text
            name_short = text
            
        name_full = title
        
        company_base = {
            "ticker": ticker,
            "name_short": name_short,
            "name_full": name_full,
        }
        
        # Sequentially fetch profile to avoid IP limits, sleep 0.5s
        time.sleep(0.5)
        profile_data = fetch_profile_data(session, ticker, href)
        company_base.update({
            "isin": profile_data["isin"],
            "indices": profile_data["indices"],
            "sector": profile_data["sector"],
            "ekd": profile_data["ekd"]
        })
        
        final_data.append(company_base)
        print(f"Progress: {i+1}/{total_rows}")
        
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_data, f, indent=2, ensure_ascii=False)
        
    print(f"Successfully saved {len(final_data)} companies to {OUT_FILE}")

if __name__ == "__main__":
    main()

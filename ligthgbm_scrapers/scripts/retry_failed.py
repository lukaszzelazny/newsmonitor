import json
import os
import time
import random
import requests
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = BASE_DIR / 'raw_data'
COMPANY_LIST_PATH = RAW_DATA_DIR / 'company_list.json'
AUTH_PATH = RAW_DATA_DIR / 'authorization'
OUTPUT_DIR = RAW_DATA_DIR / 'companies'
API_URL = 'https://web.gieldowyradar.pl/gieldowyradar_app/api/'

def main():
    if not OUTPUT_DIR.exists():
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(AUTH_PATH, 'r', encoding='utf-8') as f:
        auth_token = f.read().strip()
    if not auth_token.startswith('Bearer '):
        auth_token = f"Bearer {auth_token}"
    
    headers = {
        'Authorization': auth_token,
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }

    with open(COMPANY_LIST_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    companies = data.get('result', [])
    to_fetch = []
    
    for company in companies:
        company_id = company.get('id')
        if not company_id:
            continue
            
        output_file = OUTPUT_DIR / f"{company_id}.json"
        
        needs_fetch = False
        
        if not output_file.exists():
            needs_fetch = True
        else:
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    cdata = json.load(f)
                    # We accept result inside the output response
                    if 'result' not in cdata or cdata['result'] is None:
                        needs_fetch = True
            except (json.JSONDecodeError, UnicodeDecodeError):
                needs_fetch = True
                
        if needs_fetch:
            to_fetch.append(company_id)
            
    if not to_fetch:
        print("All companies are already downloaded successfully!")
        return
        
    print(f"Found {len(to_fetch)} companies that are missing or have invalid data. Starting fetch...")
    
    for i, company_id in enumerate(to_fetch, 1):
        output_file = OUTPUT_DIR / f"{company_id}.json"
        print(f"[{i}/{len(to_fetch)}] Fetching data for company {company_id}...")
        
        payload = {"request": "company", "companyId": company_id}
        
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=10)
            
            if response.status_code == 429:
                print("  -> Rate limited! (429 Too Many Requests). Sleeping for 60 seconds...")
                time.sleep(60)
                continue
                
            response.raise_for_status()
            
            try:
                response_data = response.json()
            except ValueError:
                print(f"  -> Error: Response is not valid JSON. Response text snippet: {response.text[:100]}")
                continue

            with open(output_file, 'w', encoding='utf-8') as out_f:
                json.dump(response_data, out_f, ensure_ascii=False, indent=2)
                
            print(f"  -> Successfully saved to {output_file.name}")
            
        except requests.exceptions.RequestException as e:
            print(f"  -> Error fetching company {company_id}: {e}")

        # Sleep to avoid getting banned
        time.sleep(random.uniform(1.5, 3.5))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")

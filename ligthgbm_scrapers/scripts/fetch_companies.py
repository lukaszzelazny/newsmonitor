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

# URL
API_URL = 'https://web.gieldowyradar.pl/gieldowyradar_app/api/'

def main():
    # Create output directory if it doesn't exist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Read authorization token
    if not AUTH_PATH.exists():
        print(f"Authorization file not found at {AUTH_PATH}")
        return

    with open(AUTH_PATH, 'r', encoding='utf-8') as f:
        auth_token = f.read().strip()
    
    # If the token in the file doesn't start with 'Bearer ', we add it
    if not auth_token.startswith('Bearer '):
        auth_token = f"Bearer {auth_token}"
    
    headers = {
        'Authorization': auth_token,
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }

    # Read company list
    if not COMPANY_LIST_PATH.exists():
        print(f"Company list not found at {COMPANY_LIST_PATH}")
        return

    with open(COMPANY_LIST_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    companies = data.get('result', [])
    total_companies = len(companies)
    print(f"Loaded {total_companies} companies to process.")

    for i, company in enumerate(companies, 1):
        company_id = company.get('id')
        if not company_id:
            continue
        
        output_file = OUTPUT_DIR / f"{company_id}.json"
        
        # Skip if already downloaded (useful for resuming after interruption)
        if output_file.exists():
            print(f"[{i}/{total_companies}] Skipping company {company_id} - already downloaded.")
            continue
            
        print(f"[{i}/{total_companies}] Fetching data for company {company_id}...")
        
        payload = {
            "request": "company",
            "companyId": company_id
        }
        
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=10)
            
            # Check for rate limiting
            if response.status_code == 429:
                print("  -> Rate limited! (429 Too Many Requests). Sleeping for 60 seconds...")
                time.sleep(60)
                # We could implement a retry logic here, but for simplicity we continue to the next loop iteration
                # or we can retry the same companyId
                continue
                
            response.raise_for_status()
            
            # Save the response JSON
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
        # Adding random delays between requests mimics human behavior
        sleep_time = random.uniform(1.5, 3.5)
        time.sleep(sleep_time)

if __name__ == "__main__":
    try:
        main()
        print("Scraping finished.")
    except KeyboardInterrupt:
        print("\nProcess interrupted by user. You can run the script again to resume.")

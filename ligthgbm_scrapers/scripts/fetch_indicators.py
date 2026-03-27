import argparse
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
INDICATOR_GROUP_LIST_PATH = RAW_DATA_DIR / 'indicator_group_list.json'
AUTH_PATH = RAW_DATA_DIR / 'authorization'
OUTPUT_DIR = RAW_DATA_DIR / 'indicators'

API_URL = 'https://web.gieldowyradar.pl/gieldowyradar_app/api/'

def parse_args():
    parser = argparse.ArgumentParser(
        description='Fetch indicators from GieldowyRadar API'
    )
    parser.add_argument(
        '--ticker',
        type=str,
        default=None,
        help='Ticker symbol to fetch/refresh (e.g. PKN, CDR). If not provided, fetches all companies.'
    )
    return parser.parse_args()


def main():
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
        
    indicator_ids = []
    if INDICATOR_GROUP_LIST_PATH.exists():
        with open(INDICATOR_GROUP_LIST_PATH, 'r', encoding='utf-8') as f:
            igl_data = json.load(f)
        for item in igl_data:
            if item.get("response") == "indicatorList":
                for ind in item.get("result", []):
                    indicator_ids.append(ind["id"])
                break
    else:
        indicator_ids = list(range(147))

    args = parse_args()
    target_ticker = args.ticker.upper() if args.ticker else None

    companies = data.get('result', [])

    if target_ticker:
        companies = [c for c in companies if c.get('shortName', '').upper() == target_ticker]
        if not companies:
            print(f"ERROR: Ticker '{target_ticker}' not found in company_list.json")
            return
        print(f"Mode: single ticker '{target_ticker}' — will refresh data unconditionally.")
    else:
        print(f"Mode: all companies ({len(companies)} total).")

    total_companies = len(companies)

    for i, company in enumerate(companies, 1):
        company_id = company.get('id')
        
        if not company_id:
            continue
            
        output_file = OUTPUT_DIR / f"{company_id}.json"
        
        # Skip if already downloaded correctly (only in all-companies mode)
        if not target_ticker and output_file.exists():
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    cdata = json.load(f)
                if 'result' in cdata and 'indicators' in cdata['result']:
                    if len(cdata['result']['indicators']) > 0:
                        continue
            except Exception:
                pass
                
        print(f"[{i}/{total_companies}] Fetching indicators for company {company_id}...")
        
        merged_result = None
        has_error = False
        remaining_indicators = indicator_ids.copy()
        current_chunk_size = 10 # Start with 10

        while remaining_indicators:
            chunk = remaining_indicators[:current_chunk_size]
            
            payload = {
                "request": "indicators",
                "companyId": company_id,
                "indicatorIds": chunk
            }
            
            try:
                response = requests.post(API_URL, headers=headers, json=payload, timeout=15)
                
                if response.status_code == 429:
                    print("  -> Rate limited! Sleeping for 60 seconds...")
                    time.sleep(60)
                    # We do not reduce chunk size for rate limit, just retry the same chunk
                    continue
                
                # If server returns 500 or other error, catch it
                response.raise_for_status()
                
                try:
                    response_data = response.json()
                except ValueError:
                    print(f"  -> Error: Response is not valid JSON. Snippet: {response.text[:100]}")
                    # Might be an underlying error with too many IDs
                    raise requests.exceptions.HTTPError("Invalid JSON")
                
                res_dict = response_data.get('result')
                if not res_dict or 'indicators' not in res_dict:
                    print(f"  -> Warning: No 'indicators' array in response.")
                    raise requests.exceptions.HTTPError("No indicators in response")
                    
                if merged_result is None:
                    merged_result = res_dict
                else:
                    merged_result['indicators'].extend(res_dict['indicators'])
                    
                # Success! Remove the processed indicators from our queue
                remaining_indicators = remaining_indicators[current_chunk_size:]
                
                # Small delay between chunks
                time.sleep(random.uniform(0.5, 1.0))
                
            except requests.exceptions.RequestException as e:
                # If we get an error, like 500 Internal Server error or failure to parse
                print(f"  -> Error fetching chunk (size {current_chunk_size}) for company {company_id}: {e}")
                
                # Reduce chunk size
                if current_chunk_size > 1:
                    current_chunk_size = max(1, current_chunk_size // 2)
                    print(f"  -> Reducing chunk size to {current_chunk_size} and retrying...")
                    time.sleep(2)
                else:
                    print(f"  -> Critical error: chunk size is 1 and still failing. Skipping remaining indicators for company {company_id}.")
                    has_error = True
                    break

        if not has_error and merged_result is not None:
            final_data = {
                "response": "indicators",
                "result": merged_result
            }
            with open(output_file, 'w', encoding='utf-8') as out_f:
                json.dump(final_data, out_f, ensure_ascii=False, indent=2)
            print(f"  -> Successfully saved {len(merged_result['indicators'])} indicators to {output_file.name}")
        
        # Longer delay between companies
        time.sleep(random.uniform(1.0, 2.0))

if __name__ == "__main__":
    try:
        main()
        print("Indicators fetching finished.")
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")

# Użycie:
#   python fetch_indicators.py                  # pobiera wszystkie spółki (pomija już pobrane)
#   python fetch_indicators.py --ticker PKN      # odświeża dane tylko dla PKN Orlen

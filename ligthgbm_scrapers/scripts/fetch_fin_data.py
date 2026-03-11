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
ENTRY_GROUP_LIST_PATH = RAW_DATA_DIR / 'entry_group_list.json'
AUTH_PATH = RAW_DATA_DIR / 'authorization'
OUTPUT_DIR = RAW_DATA_DIR / 'finData'

API_URL = 'https://web.gieldowyradar.pl/gieldowyradar_app/api/'

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
        
    # Wczytujemy możliwe grupy z entry_group_list.json żeby dla banków uderzać w poprawne pola
    non_bank_orders = []
    bank_orders = []
    if ENTRY_GROUP_LIST_PATH.exists():
        with open(ENTRY_GROUP_LIST_PATH, 'r', encoding='utf-8') as f:
            egl_data = json.load(f)
        for item in egl_data:
            if item.get("response") == "entryGroupList":
                for g in item["result"]["nonBank"]:
                    non_bank_orders.append(g["entryOrder"])
                for g in item["result"]["bank"]:
                    bank_orders.append(g["entryOrder"])
                break
    else:
        # Fallback do wskazanych przez Ciebie domyślnych
        non_bank_orders = [
            [33,2,3,34,35,36,37,38,39,40,41,42,43,0,44,4,5,45,6,7,46,47,48,49,50,51,52,53,54,55,56,57,58,59,1,28],
            [60,61,62,63,64,65,66,67,73,68,69,70,71,72,8,9,10,11],
            [12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27]
        ]
        bank_orders = non_bank_orders

    companies = data.get('result', [])
    total_companies = len(companies)

    for i, company in enumerate(companies, 1):
        company_id = company.get('id')
        trade_id = company.get('tradeId')  # 2 oznacza Banki
        
        if not company_id:
            continue
            
        output_file = OUTPUT_DIR / f"{company_id}.json"
        
        # Omijamy już poprawnie pobrane pliki
        if output_file.exists():
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    cdata = json.load(f)
                if isinstance(cdata, list) and len(cdata) > 0 and 'result' in cdata[0] and cdata[0]['result'] is not None:
                    continue
            except Exception:
                pass
                
        print(f"[{i}/{total_companies}] Fetching finData for company {company_id}...")
        
        # Wybieramy odpowiedni zestaw ID (Banki mają inne zestawy niż reszta)
        orders_to_use = bank_orders if trade_id == 2 else non_bank_orders
        
        payload = []
        for entry_order in orders_to_use:
            payload.append({
                "request": "finDataEntries",
                "companyId": company_id,
                "entryIds": entry_order,
                "quarterly": True
            })
        
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=15)
            
            if response.status_code == 429:
                print("  -> Rate limited! Sleeping for 60 seconds...")
                time.sleep(60)
                continue
                
            response.raise_for_status()
            
            try:
                response_data = response.json()
            except ValueError:
                print(f"  -> Error: Response is not valid JSON. Snippet: {response.text[:100]}")
                continue

            with open(output_file, 'w', encoding='utf-8') as out_f:
                json.dump(response_data, out_f, ensure_ascii=False, indent=2)
                
            print(f"  -> Successfully saved to {output_file.name}")
            
        except requests.exceptions.RequestException as e:
            print(f"  -> Error fetching finData for company {company_id}: {e}")

        # Optymalne opóźnienie
        time.sleep(random.uniform(1.5, 3.5))

if __name__ == "__main__":
    try:
        main()
        print("FinData fetching finished.")
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")

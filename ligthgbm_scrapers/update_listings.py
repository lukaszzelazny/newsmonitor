import json
import os
from sqlalchemy import create_engine, text

# Konfiguracja
SCHEMA_NAME = 'lgbm'
ENGINE_URL = 'postgresql:///?service=stock'
RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), 'raw_data')

def main():
    print("Connecting to DB to update listing_id and index_id...")
    engine = create_engine(ENGINE_URL)

    with engine.begin() as conn:
        # Dodanie nowych kolumn jeśli nie istnieją
        conn.execute(text(f"ALTER TABLE {SCHEMA_NAME}.companies ADD COLUMN IF NOT EXISTS listing_id INTEGER;"))
        conn.execute(text(f"ALTER TABLE {SCHEMA_NAME}.companies ADD COLUMN IF NOT EXISTS index_id INTEGER;"))
        
        # Wczytanie danych z JSON
        try:
            with open(os.path.join(RAW_DATA_DIR, 'company_list.json'), 'r') as f:
                c_data = json.load(f)
        except Exception as e:
            print(f"Błąd ładowania pliku JSON: {e}")
            return

        print("Updating companies table...")
        updates = []
        for r in c_data.get('result', []):
            cid = r.get('id')
            lid = r.get('listingId')
            iid = r.get('indexId')
            
            if cid is not None:
                updates.append({
                    'cid': cid,
                    'lid': lid,
                    'iid': iid
                })

        # Masowy update
        if updates:
            update_stmt = text(f"""
                UPDATE {SCHEMA_NAME}.companies 
                SET listing_id = :lid, index_id = :iid 
                WHERE id = :cid
            """)
            conn.execute(update_stmt, updates)
            
    print("Done! You can now query GPW companies using: SELECT * FROM lgbm.companies WHERE listing_id = 1;")

if __name__ == '__main__':
    main()

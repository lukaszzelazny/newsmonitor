import argparse
import json
import os
import glob
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Numeric, Text, ForeignKey, BigInteger, Date
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Konfiguracja
SCHEMA_NAME = 'lgbm'
# Korzystamy z definicji usługi 'stock' z piku .pg_service.conf
ENGINE_URL = 'postgresql:///?service=stock'
RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), 'raw_data')

engine = create_engine(ENGINE_URL)

# Utworzenie dedykowanego schematu
with engine.connect() as conn:
    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}"))
    conn.commit()

Base = declarative_base()

class Sector(Base):
    __tablename__ = 'sectors'
    __table_args__ = {'schema': SCHEMA_NAME}
    id = Column(Integer, primary_key=True)
    name = Column(String)

class FinDataDict(Base):
    __tablename__ = 'fin_data_dict'
    __table_args__ = {'schema': SCHEMA_NAME}
    id = Column(Integer, primary_key=True)
    type = Column(String, primary_key=True)
    name = Column(String)
    description = Column(Text)

class IndicatorDict(Base):
    __tablename__ = 'indicator_dict'
    __table_args__ = {'schema': SCHEMA_NAME}
    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(Text)

class Company(Base):
    __tablename__ = 'companies'
    __table_args__ = {'schema': SCHEMA_NAME}
    id = Column(Integer, primary_key=True)
    name = Column(String)
    short_name = Column(String)
    trade_id = Column(Integer)  # Brak ForeignKey dla elastyczności (w razie braków słownikowych)
    listing_id = Column(Integer)
    index_id = Column(Integer)
    isin = Column(String)
    stock_volume = Column(BigInteger)
    pkd = Column(String)
    description = Column(Text)
    ceo = Column(String)
    fin_data_type = Column(String)

class Dividend(Base):
    __tablename__ = 'dividends'
    __table_args__ = {'schema': SCHEMA_NAME}
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey(f'{SCHEMA_NAME}.companies.id'))
    year = Column(Integer)
    payout = Column(Numeric)
    currency = Column(String)
    dividend_day = Column(Date)
    payout_day = Column(Date)

class Recommendation(Base):
    __tablename__ = 'recommendations'
    __table_args__ = {'schema': SCHEMA_NAME}
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey(f'{SCHEMA_NAME}.companies.id'))
    issue_date = Column(Date)
    institution = Column(String)
    price = Column(Numeric)

class Employment(Base):
    __tablename__ = 'employment'
    __table_args__ = {'schema': SCHEMA_NAME}
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey(f'{SCHEMA_NAME}.companies.id'))
    year = Column(Integer)
    employee_count = Column(Integer)
    revenue_per_employee = Column(Numeric)

class Shareholder(Base):
    __tablename__ = 'shareholders'
    __table_args__ = {'schema': SCHEMA_NAME}
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey(f'{SCHEMA_NAME}.companies.id'))
    type = Column(String)
    name = Column(String)
    stock_percent = Column(Numeric)
    vote_percent = Column(Numeric)

class FinData(Base):
    __tablename__ = 'fin_data'
    __table_args__ = {'schema': SCHEMA_NAME}
    company_id = Column(Integer, ForeignKey(f'{SCHEMA_NAME}.companies.id'), primary_key=True)
    year = Column(Integer, primary_key=True)
    quarter = Column(Integer, primary_key=True)
    entry_id = Column(Integer, primary_key=True)
    value = Column(Numeric)

class Indicator(Base):
    __tablename__ = 'indicators'
    __table_args__ = {'schema': SCHEMA_NAME}
    company_id = Column(Integer, ForeignKey(f'{SCHEMA_NAME}.companies.id'), primary_key=True)
    year = Column(Integer, primary_key=True)
    quarter = Column(Integer, primary_key=True)
    indicator_id = Column(Integer, primary_key=True)
    value = Column(Numeric)


def ms_to_date(ms):
    if not ms: return None
    return datetime.fromtimestamp(ms/1000.0).date()


def parse_args():
    parser = argparse.ArgumentParser(
        description='Import financial data from JSON files into PostgreSQL (lgbm schema)'
    )
    parser.add_argument(
        '--ticker',
        type=str,
        default=None,
        help='Ticker symbol to import/refresh (e.g. PKN, CDR). If not provided, runs the full import.'
    )
    return parser.parse_args()


def resolve_company_id(ticker: str) -> int | None:
    """Find company_id for a given ticker symbol in company_list.json."""
    path = os.path.join(RAW_DATA_DIR, 'company_list.json')
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        for c in data.get('result', []):
            if c.get('shortName', '').upper() == ticker.upper():
                return c['id']
    except FileNotFoundError:
        pass
    return None


def import_findata_for_company(session, cid: int):
    """Import/update finData for a single company. Uses on_conflict_do_update to refresh rows."""
    ff = os.path.join(RAW_DATA_DIR, 'finData', f'{cid}.json')
    if not os.path.exists(ff):
        print(f"  -> finData file not found: {ff}")
        return

    try:
        with open(ff, 'r') as f:
            fdata = json.load(f)
    except Exception as e:
        print(f"  -> Error loading {ff}: {e}")
        return

    items = fdata if isinstance(fdata, list) else [fdata]
    insert_dicts = []
    seen_keys = set()

    for item in items:
        result = item.get('result', {})
        periods = result.get('periods', [])
        entries = result.get('entries', [])
        for ent in entries:
            eid = ent['entryId']
            vals = ent['values']
            for i, val in enumerate(vals):
                if val is not None and i < len(periods):
                    year = periods[i].get('year')
                    quarter = periods[i].get('quarter')
                    if year is not None and quarter is not None:
                        key = (cid, year, quarter, eid)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            insert_dicts.append({
                                'company_id': cid, 'year': year,
                                'quarter': quarter, 'entry_id': eid, 'value': val
                            })

    if insert_dicts:
        stmt = pg_insert(FinData).values(insert_dicts)
        stmt = stmt.on_conflict_do_update(
            index_elements=['company_id', 'year', 'quarter', 'entry_id'],
            set_={'value': stmt.excluded.value}
        )
        session.execute(stmt)
        session.commit()
        print(f"  -> Upserted {len(insert_dicts)} finData rows for company {cid}")


def import_indicators_for_company(session, cid: int):
    """Import/update indicators for a single company. Uses on_conflict_do_update to refresh rows."""
    inf = os.path.join(RAW_DATA_DIR, 'indicators', f'{cid}.json')
    if not os.path.exists(inf):
        print(f"  -> indicators file not found: {inf}")
        return

    try:
        with open(inf, 'r') as f:
            idata = json.load(f)
    except Exception as e:
        print(f"  -> Error loading {inf}: {e}")
        return

    items = idata if isinstance(idata, list) else [idata]
    insert_dicts = []
    seen_keys = set()

    for item in items:
        res = item.get('result', {})
        periods = res.get('periods', [])
        indicators = res.get('indicators', [])
        for ind in indicators:
            iid = ind.get('indicatorId')
            vals = ind.get('values', [])
            for i, val in enumerate(vals):
                if val is not None and i < len(periods):
                    year = periods[i].get('year')
                    quarter = periods[i].get('quarter')
                    if year is not None and quarter is not None:
                        key = (cid, year, quarter, iid)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            insert_dicts.append({
                                'company_id': cid, 'year': year,
                                'quarter': quarter, 'indicator_id': iid, 'value': val
                            })

    if insert_dicts:
        stmt = pg_insert(Indicator).values(insert_dicts)
        stmt = stmt.on_conflict_do_update(
            index_elements=['company_id', 'year', 'quarter', 'indicator_id'],
            set_={'value': stmt.excluded.value}
        )
        session.execute(stmt)
        session.commit()
        print(f"  -> Upserted {len(insert_dicts)} indicator rows for company {cid}")


def main():
    args = parse_args()
    target_ticker = args.ticker.upper() if args.ticker else None

    # --- Tryb: jeden ticker ---
    if target_ticker:
        cid = resolve_company_id(target_ticker)
        if cid is None:
            print(f"ERROR: Ticker '{target_ticker}' not found in company_list.json")
            return
        print(f"Mode: single ticker '{target_ticker}' (company_id={cid}) — upserting finData & indicators.")
        Session = sessionmaker(bind=engine)
        session = Session()
        import_findata_for_company(session, cid)
        import_indicators_for_company(session, cid)
        session.close()
        print("Single-ticker import finished.")
        return

    # --- Tryb: pełny import ---
    print("Mode: full import.")
    print("Creating tables if they don't exist...")
    # Base.metadata.drop_all(engine) # Zakończono z ciągłym kasowaniem bazy
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    # 1. Sektory
    print("Loading sectors from trade_list.json...")
    try:
        with open(os.path.join(RAW_DATA_DIR, 'trade_list.json'), 'r') as f:
            tr_data = json.load(f)
            for resp in tr_data:
                if resp.get('response') == 'tradeList':
                    for r in resp.get('result', []):
                        session.merge(Sector(id=r['id'], name=r['name']))
        session.commit()
    except FileNotFoundError:
        print("warning: trade_list.json not found")

    # 2. Słowniki Danych Finansowych
    print("Loading fin_data dict from entry_group_list.json...")
    try:
        with open(os.path.join(RAW_DATA_DIR, 'entry_group_list.json'), 'r') as f:
            eg_data = json.load(f)
            for resp in eg_data:
                if resp.get('response') == 'finDataEntryList':
                    res = resp.get('result', {})
                    for fin_type, entries in res.items():
                        for ent in entries:
                            session.merge(FinDataDict(
                                id=ent['id'], type=fin_type, 
                                name=ent['name'], description=ent.get('description')
                            ))
        session.commit()
    except FileNotFoundError:
        print("warning: entry_group_list.json not found")

    # 3. Słowniki Wskaźników
    print("Loading indicators dict from indicator_group_list.json...")
    try:
        with open(os.path.join(RAW_DATA_DIR, 'indicator_group_list.json'), 'r') as f:
            ig_data = json.load(f)
            for resp in ig_data:
                if resp.get('response') == 'indicatorList':
                    for ind in resp.get('result', []):
                        session.merge(IndicatorDict(
                            id=ind['id'], name=ind['name'], description=ind.get('description')
                        ))
        session.commit()
    except FileNotFoundError:
        print("warning: indicator_group_list.json not found")

    # 4. Spółki z glownej listy
    print("Loading companies details...")
    comp_basic_dict = {}
    try:
        with open(os.path.join(RAW_DATA_DIR, 'company_list.json'), 'r') as f:
            c_data = json.load(f)
            for r in c_data.get('result', []):
                comp_basic_dict[r['id']] = {
                    'name': r['name'],
                    'shortName': r['shortName'],
                    'tradeId': r.get('tradeId'),
                    'listingId': r.get('listingId'),
                    'indexId': r.get('indexId')
                }
    except FileNotFoundError:
        print("warning: company_list.json not found")

    comp_files = glob.glob(os.path.join(RAW_DATA_DIR, 'companies', '*.json'))
    for cf in comp_files:
        cid = int(os.path.basename(cf).replace('.json', ''))
        try:
            with open(cf, 'r') as f:
                cinfo = json.load(f).get('result', {})
        except Exception as e:
            print(f"Error loading {cf}: {e}")
            continue
            
        basic = comp_basic_dict.get(cid, {})
        comp = Company(
            id=cid,
            name=basic.get('name', cinfo.get('fullName')),
            short_name=basic.get('shortName', cinfo.get('shortName')),
            trade_id=basic.get('tradeId'),
            listing_id=basic.get('listingId', cinfo.get('listingId')),
            index_id=basic.get('indexId', cinfo.get('indexId')),
            isin=cinfo.get('isin'),
            stock_volume=cinfo.get('stockVolume'),
            pkd=cinfo.get('pkd'),
            description=cinfo.get('description'),
            ceo=cinfo.get('ceo'),
            fin_data_type=cinfo.get('finDataType')
        )
        session.merge(comp)
        
        # Poniższe dane (dywidendy itp) mogą się dublować, najbezpieczniej je zignorować 
        # (albo najpierw wyczyścić dla tej spółki jeśli robimy pełny update)
        session.execute(text(f"DELETE FROM {SCHEMA_NAME}.dividends WHERE company_id = :cid"), {"cid": cid})
        for div in cinfo.get('dividend', []):
            session.add(Dividend(
                company_id=cid, year=div.get('year'), payout=div.get('payout'),
                currency=div.get('currency'),
                dividend_day=ms_to_date(div.get('dividendDay')),
                payout_day=ms_to_date(div.get('payoutDay'))
            ))
            
        session.execute(text(f"DELETE FROM {SCHEMA_NAME}.recommendations WHERE company_id = :cid"), {"cid": cid})
        for rec in cinfo.get('recommendations', []):
            session.add(Recommendation(
                company_id=cid, issue_date=ms_to_date(rec.get('issueDate')),
                institution=rec.get('institution'), price=rec.get('price')
            ))
            
        session.execute(text(f"DELETE FROM {SCHEMA_NAME}.employment WHERE company_id = :cid"), {"cid": cid})
        for emp in cinfo.get('employment', []):
            session.add(Employment(
                company_id=cid, year=emp.get('year'),
                employee_count=emp.get('employeeCount'),
                revenue_per_employee=emp.get('revenuePerEmployee')
            ))
            
        session.execute(text(f"DELETE FROM {SCHEMA_NAME}.shareholders WHERE company_id = :cid"), {"cid": cid})
        for sh_type, sh_data in cinfo.get('stockHolders', {}).items():
            for val in sh_data.get('values', []):
                if val.get('name'):
                    session.add(Shareholder(
                        company_id=cid, type=sh_type, name=val.get('name'),
                        stock_percent=val.get('stockPercent'), vote_percent=val.get('votePercent')
                    ))

    session.commit()

    # 5. FinData Szeregi czasowe
    print("Loading financial entries timeseries (finData/**/*.json) ...")
    findata_files = glob.glob(os.path.join(RAW_DATA_DIR, 'finData', '*.json'))
    for ff in findata_files:
        cid = int(os.path.basename(ff).replace('.json', ''))
        try:
            with open(ff, 'r') as f:
                fdata = json.load(f)
        except Exception:
            continue
            
        # UWAGA: fdata to lista z odpowiedziami - wcześniej pobieraliśmy tylko [0]
        items = fdata if isinstance(fdata, list) else [fdata]
        
        insert_dicts = []
        seen_keys = set()
        
        for item in items:
            result = item.get('result', {})
            periods = result.get('periods', [])
            entries = result.get('entries', [])
            
            for ent in entries:
                eid = ent['entryId']
                vals = ent['values']
                for i, val in enumerate(vals):
                    if val is not None and i < len(periods):
                        year = periods[i].get('year')
                        quarter = periods[i].get('quarter')
                        
                        if year is not None and quarter is not None:
                            key = (cid, year, quarter, eid)
                            if key not in seen_keys:
                                seen_keys.add(key)
                                insert_dicts.append({
                                    'company_id': cid,
                                    'year': year,
                                    'quarter': quarter,
                                    'entry_id': eid,
                                    'value': val
                                })
                                
        if insert_dicts:
            # Wstawienie zbiorcze z on_conflict_do_nothing zapobiega duplikatom
            stmt = pg_insert(FinData).values(insert_dicts)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=['company_id', 'year', 'quarter', 'entry_id']
            )
            session.execute(stmt)
            session.commit()

    # 6. Wskaźniki
    print("Loading indicators timeseries (indicators/**/*.json) ...")
    ind_files = glob.glob(os.path.join(RAW_DATA_DIR, 'indicators', '*.json'))
    for inf in ind_files:
        cid = int(os.path.basename(inf).replace('.json', ''))
        try:
            with open(inf, 'r') as f:
                idata = json.load(f)
        except Exception:
            continue
            
        items = idata if isinstance(idata, list) else [idata]
        
        insert_dicts = []
        seen_keys = set()
        
        for item in items:
            res = item.get('result', {})
            periods = res.get('periods', [])
            indicators = res.get('indicators', [])
            
            for ind in indicators:
                iid = ind.get('indicatorId')
                vals = ind.get('values', [])
                for i, val in enumerate(vals):
                    if val is not None and i < len(periods):
                        year = periods[i].get('year')
                        quarter = periods[i].get('quarter')
                        
                        if year is not None and quarter is not None:
                            key = (cid, year, quarter, iid)
                            if key not in seen_keys:
                                seen_keys.add(key)
                                insert_dicts.append({
                                    'company_id': cid,
                                    'year': year,
                                    'quarter': quarter,
                                    'indicator_id': iid,
                                    'value': val
                                })
                                
        if insert_dicts:
            stmt = pg_insert(Indicator).values(insert_dicts)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=['company_id', 'year', 'quarter', 'indicator_id']
            )
            session.execute(stmt)
            session.commit()

    session.close()
    print("Data import finished successfully!")

if __name__ == '__main__':
    main()

# Użycie:
#   python import_to_postgres.py                  # pełny import wszystkich danych
#   python import_to_postgres.py --ticker PKN      # upsert finData + indicators tylko dla PKN Orlen

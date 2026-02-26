"""
Znajdz transakcje ktore sa w DB ale nie ma ich w pliku Excel brokera.
"""
import pandas as pd
import sys
sys.path.insert(0, 'c:/Users/ukasz/Documents/gielda/newsmonitor')

IKE_FILE = 'data/account_ike_51936682_pl_xlsx_2005-12-31_2026-02-18.xlsx'

# Wczytaj operacje brokera
df_raw = pd.read_excel(IKE_FILE, sheet_name='CASH OPERATION HISTORY', header=None)
data_rows = []
for i in range(11, len(df_raw)):
    row = df_raw.iloc[i].tolist()
    non_nan = [v for v in row if str(v) not in ['nan', 'None', '']]
    if non_nan:
        data_rows.append(df_raw.iloc[i].tolist())
max_cols = max(len(r) for r in data_rows)
padded = [r + [None]*(max_cols - len(r)) for r in data_rows]
cols = ['_', 'ID', 'Type', 'Time', 'Comment', 'Symbol', 'Amount'] + ['x%d' % i for i in range(max_cols - 7)]
broker_df = pd.DataFrame(padded, columns=cols[:max_cols])
broker_df['Amount'] = pd.to_numeric(broker_df['Amount'], errors='coerce')
broker_df = broker_df[broker_df['Type'].notna()].copy()

# Tickers w brokerze (bez .PL .US .UK)
def clean_sym(s):
    if not s or str(s) == 'nan': return ''
    return str(s).replace('.PL','').replace('.US','').replace('.UK','').replace('.DE','')

broker_df['ticker_clean'] = broker_df['Symbol'].apply(clean_sym)
broker_tickers = set(broker_df['ticker_clean'].unique()) - {'', 'nan'}
print('Tickers w brokerze IKE:', sorted(broker_tickers))

# Wczytaj transakcje z DB
from backend.database import Database, Transaction, TransactionType
db = Database()
session = db.Session()
txs = session.query(Transaction).filter_by(portfolio_id=1).order_by(Transaction.transaction_date).all()

db_tickers = set()
for t in txs:
    db_tickers.add(t.asset.ticker)

print('Tickers w DB IKE:', sorted(db_tickers))
print()
print('W DB ale NIE w brokerze:', sorted(db_tickers - broker_tickers - {'PLN'}))
print('W brokerze ale NIE w DB:', sorted(broker_tickers - db_tickers))

# Policz wartosc transakcji dla tickerow ktore sa tylko w DB
print()
print('=== TRANSAKCJE W DB KTORE NIE MA W BROKERZE ===')
missing_from_broker = db_tickers - broker_tickers - {'PLN'}
total_buy_missing = 0.0
total_sell_missing = 0.0
for t in txs:
    if t.asset.ticker not in missing_from_broker:
        continue
    tt = t.transaction_type.value if hasattr(t.transaction_type, 'value') else str(t.transaction_type)
    qty = float(t.quantity)
    price = float(t.price) if t.price else 0.0
    pv = float(t.purchase_value_pln) if t.purchase_value_pln else None
    sv = float(t.sale_value_pln) if t.sale_value_pln else None
    val = pv if (tt == 'BUY' and pv) else (sv if (tt == 'SELL' and sv) else qty * price)
    sign = '+' if tt == 'SELL' else '-'
    print('  %s  %-6s  %-10s  qty=%8.4f  price=%8.2f  val=%8.2f PLN' % (
        str(t.transaction_date), tt, t.asset.ticker, qty, price, val))
    if tt == 'BUY':
        total_buy_missing += val
    elif tt == 'SELL':
        total_sell_missing += val

print()
print('Suma zakupow (brak w brokerze):    %.2f' % total_buy_missing)
print('Suma sprzedazy (brak w brokerze):  %.2f' % total_sell_missing)
print('Wplyw netto na gotowke:            %.2f' % (total_sell_missing - total_buy_missing))

# Porownaj depozyty
print()
print('=== DEPOZYTY: DB vs BROKER ===')
broker_deps = broker_df[broker_df['Type'].str.contains('Deposit|deposit|Transfer', na=False)]
print('Broker depozyty/transfery:')
for _, r in broker_deps.iterrows():
    print('  %s  %-25s  %+10.2f' % (str(r['Time'])[:19], str(r['Type']), r['Amount']))
print('SUMA broker: %.2f' % broker_deps['Amount'].sum())

print()
db_dep_total = 0.0
print('DB depozyty:')
for t in txs:
    tt = t.transaction_type.value if hasattr(t.transaction_type, 'value') else str(t.transaction_type)
    if tt in ('DEPOSIT', 'WITHDRAWAL'):
        qty = float(t.quantity)
        pv = float(t.purchase_value_pln) if t.purchase_value_pln else qty
        sign = 1 if tt == 'DEPOSIT' else -1
        db_dep_total += sign * pv
        print('  %s  %-12s  %+10.2f' % (str(t.transaction_date), tt, sign * pv))
print('SUMA DB: %.2f' % db_dep_total)
print('ROZNICA depozytow: %.2f' % (db_dep_total - broker_deps['Amount'].sum()))

session.close()

from database import Database
from portfolio.models import Portfolio, Transaction

def main():
    db = Database()
    s = db.Session()
    try:
        print("ID\tNAME\tBROKER\tTX_COUNT")
        for p in s.query(Portfolio).order_by(Portfolio.id.asc()).all():
            cnt = s.query(Transaction).filter_by(portfolio_id=p.id).count()
            print(f"{p.id}\t{p.name}\t{p.broker}\t{cnt}")
    finally:
        s.close()

if __name__ == "__main__":
    main()

from sqlalchemy import create_engine, MetaData
from sqlalchemy.schema import CreateTable
from portfolio.models import Portfolio, Asset, Transaction, PortfolioSnapshot
from database import Base

def generate_schema_sql():
    """Generates the SQL for creating the portfolio tables."""
    
    # We need to bind the metadata to an engine to generate the SQL
    engine = create_engine('postgresql://', strategy='mock', executor=lambda sql, *multiparams, **params: None)
    
    # Set the schema for the tables
    Base.metadata.schema = "stock"
    
    sql_commands = []
    for table in [Portfolio.__table__, Asset.__table__, Transaction.__table__, PortfolioSnapshot.__table__]:
        sql_commands.append(str(CreateTable(table).compile(engine)).strip() + ";")
        
    return "\n\n".join(sql_commands)

if __name__ == '__main__':
    sql = generate_schema_sql()
    with open('migration.sql', 'w') as f:
        f.write(sql)
    print("SQL migration script 'migration.sql' generated successfully.")

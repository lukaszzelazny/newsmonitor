CREATE TABLE stock.portfolios (
    id SERIAL NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    broker VARCHAR(100), 
    description VARCHAR(500), 
    PRIMARY KEY (id)
);

CREATE TABLE stock.assets (
    id SERIAL NOT NULL, 
    ticker VARCHAR(32) NOT NULL, 
    name VARCHAR(200), 
    asset_type VARCHAR(50) NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (ticker)
);

CREATE TABLE stock.transactions (
    id SERIAL NOT NULL, 
    portfolio_id INTEGER NOT NULL, 
    asset_id INTEGER NOT NULL, 
    transaction_type VARCHAR(4) NOT NULL, 
    quantity FLOAT NOT NULL, 
    price FLOAT NOT NULL, 
    transaction_date DATE NOT NULL, 
    commission FLOAT, 
    PRIMARY KEY (id), 
    FOREIGN KEY(portfolio_id) REFERENCES stock.portfolios (id), 
    FOREIGN KEY(asset_id) REFERENCES stock.assets (id)
);

CREATE TABLE stock.portfolio_snapshots (
    id SERIAL NOT NULL, 
    portfolio_id INTEGER NOT NULL, 
    date DATE NOT NULL, 
    total_value FLOAT NOT NULL, 
    rate_of_return FLOAT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(portfolio_id) REFERENCES stock.portfolios (id)
);

CREATE INDEX ix_assets_ticker ON stock.assets (ticker);
CREATE INDEX ix_portfolio_snapshots_date ON stock.portfolio_snapshots (date);

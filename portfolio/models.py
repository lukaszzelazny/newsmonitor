"""Database models for the portfolio management feature."""

from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Float, Enum
from sqlalchemy.orm import relationship
from database import Base
import enum


class Portfolio(Base):
    """Represents an investment portfolio."""
    __tablename__ = 'portfolios'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    broker = Column(String(100), nullable=True)
    description = Column(String(500), nullable=True)

    transactions = relationship('Transaction', back_populates='portfolio', cascade="all, delete-orphan")
    snapshots = relationship('PortfolioSnapshot', back_populates='portfolio', cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Portfolio(id={self.id}, name='{self.name}')>"


class Asset(Base):
    """Represents a financial asset, like a stock or ETF."""
    __tablename__ = 'assets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(32), nullable=False, unique=True, index=True)
    name = Column(String(200), nullable=True)
    asset_type = Column(String(50), nullable=False)  # e.g., 'stock', 'etf'

    transactions = relationship('Transaction', back_populates='asset')

    def __repr__(self):
        return f"<Asset(id={self.id}, ticker='{self.ticker}')>"


class TransactionType(enum.Enum):
    BUY = "buy"
    SELL = "sell"


class Transaction(Base):
    """Represents a single transaction of an asset."""
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey('portfolios.id'), nullable=False)
    asset_id = Column(Integer, ForeignKey('assets.id'), nullable=False)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    transaction_date = Column(Date, nullable=False)
    commission = Column(Float, nullable=True)

    portfolio = relationship('Portfolio', back_populates='transactions')
    asset = relationship('Asset', back_populates='transactions')

    def __repr__(self):
        return f"<Transaction(id={self.id}, asset_id={self.asset_id}, type='{self.transaction_type}')>"


class PortfolioSnapshot(Base):
    """Stores a snapshot of portfolio performance at a point in time."""
    __tablename__ = 'portfolio_snapshots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey('portfolios.id'), nullable=False)
    date = Column(Date, nullable=False, index=True)
    total_value = Column(Float, nullable=False)
    rate_of_return = Column(Float, nullable=False)

    portfolio = relationship('Portfolio', back_populates='snapshots')

    def __repr__(self):
        return f"<PortfolioSnapshot(id={self.id}, date='{self.date}', value={self.total_value})>"

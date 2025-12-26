"""Database models and operations."""
import enum
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Date, Index, \
    ForeignKey, Float, Enum, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, date as date_type
from typing import Optional
from sqlalchemy.sql import func
Base = declarative_base()


class NewsArticle(Base):
    """News article database model."""
    
    __tablename__ = 'news_articles'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    content = Column(String, nullable=True)
    url = Column(String(1000), nullable=False, unique=True)
    source = Column(String(100), nullable=False)
    date = Column(Date, nullable=True)
    published_at = Column(DateTime, nullable=True)
    scraped_at = Column(DateTime, default=datetime.now, nullable=False)
    
    # Index for faster lookups
    __table_args__ = (
        Index('idx_url', 'url'),
        Index('idx_source_date', 'source', 'date'),
    )
    
    def __repr__(self):
        return f"<NewsArticle(id={self.id}, title='{self.title[:50]}...', source='{self.source}')>"


class AnalysisResult(Base):
    """AI analysis results for news articles."""

    __tablename__ = 'analysis_result'

    id = Column(Integer, primary_key=True, autoincrement=True)
    news_id = Column(Integer, ForeignKey('news_articles.id', ondelete='CASCADE'), nullable=True)
    summary = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    # Relations
    news = relationship('NewsArticle', backref='analyses')

    def __repr__(self):
        return f"<AnalysisResult(id={self.id}, news_id={self.news_id})>"


class Ticker(Base):
    """Dictionary of tickers and companies."""

    __tablename__ = 'tickers'

    ticker = Column(String(32), primary_key=True)
    company_name = Column(String(200), nullable=True)
    sector = Column(String(100), nullable=True)
    in_portfolio = Column(Integer, default=0, nullable=False)  # 0 = nie, 1 = tak

    def __repr__(self):
        return f"<Ticker(ticker='{self.ticker}')>"


class TickerSentiment(Base):
    """Per-ticker sentiment derived from an analysis."""

    __tablename__ = 'ticker_sentiment'

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey('analysis_result.id', ondelete='CASCADE'), nullable=False)
    ticker = Column(String(32), ForeignKey('tickers.ticker', ondelete='SET NULL'), nullable=True)
    sector = Column(String(100), nullable=True)
    impact = Column(Float, nullable=True)
    occasion = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=True)  # e.g. -1.0 .. 1.0

    # Relations
    analysis = relationship('AnalysisResult', backref='ticker_sentiments')
    ticker_ref = relationship('Ticker', backref='sentiments', foreign_keys=[ticker])

    def __repr__(self):
        return f"<TickerSentiment(id={self.id}, analysis_id={self.analysis_id}, ticker='{self.ticker}')>"


class SectorSentiment(Base):
    """Per-sector sentiment derived from an analysis."""

    __tablename__ = 'sector_sentiment'

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey('analysis_result.id', ondelete='CASCADE'), nullable=False)
    sector = Column(String(100), nullable=True)
    impact = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)

    # Relations
    analysis = relationship('AnalysisResult', backref='sector_sentiments')

    def __repr__(self):
        return f"<SectorSentiment(id={self.id}, analysis_id={self.analysis_id}, sector='{self.sector}')>"


class BrokerageAnalysis(Base):
    """Brokerage house analysis and price targets."""

    __tablename__ = 'brokerage_analysis'

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey('analysis_result.id', ondelete='CASCADE'), nullable=False)
    ticker = Column(String(32), ForeignKey('tickers.ticker', ondelete='SET NULL'), nullable=True)
    brokerage_house = Column(String(200), nullable=False)
    price_old = Column(String(50), nullable=True)
    price_new = Column(String(50), nullable=True)
    price_recommendation = Column(String(50), nullable=True)
    price_comment = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    # Relations
    analysis = relationship('AnalysisResult', backref='brokerage_analyses')
    ticker_ref = relationship('Ticker', backref='brokerage_analyses', foreign_keys=[ticker])

    def __repr__(self):
        return f"<BrokerageAnalysis(id={self.id}, brokerage_house='{self.brokerage_house}', ticker='{self.ticker}')>"

class NewsNotAnalyzed(Base):
    __tablename__ = 'news_not_analyzed'
    id = Column(Integer, primary_key=True)
    news_id = Column(Integer, ForeignKey('news_articles.id'), nullable=False)
    reason = Column(String, nullable=False)
    relevance_score = Column(Float)
    created_at = Column(DateTime, server_default=func.now())

    article = relationship("NewsArticle", backref="not_analyzed_records")


class Database:
    """Database operations manager."""
    
    def __init__(self):
        """Initialize database connection."""
        service = os.getenv('PG_SERVICE', 'stock')
        db_url = f"postgresql:///?service={service}"

        self.engine = create_engine(
            db_url,
            echo=False,
            connect_args={},
            execution_options={"schema_translate_map": {"stock": "stock"}}
        )
        Base.metadata.schema = "stock"
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
    
    def exists(self, url: str) -> bool:
        """Check if an article with given URL already exists."""
        session = self.Session()
        try:
            count = session.query(NewsArticle).filter(NewsArticle.url == url).count()
            return count > 0
        finally:
            session.close()
    
    def add_article(self, article) -> NewsArticle:
        """
        Add a news article to the database.
        
        Args:
            article: NewsArticle object from provider
        
        Returns:
            Database model instance
        """
        db_article = NewsArticle(
            title=article.title,
            content=article.content or "",
            url=article.url,
            source=article.source,
            date=article.date,
            published_at=article.published_at,
            scraped_at=datetime.now()
        )
        
        session = self.Session()
        try:
            session.add(db_article)
            session.commit()
            session.refresh(db_article)
            return db_article
        finally:
            session.close()

    def get_article_by_url(self, url: str) -> Optional[NewsArticle]:
        """Get a single article by its URL."""
        session = self.Session()
        try:
            return session.query(NewsArticle).filter(NewsArticle.url == url).first()
        finally:
            session.close()

    def get_articles_by_date(self, target_date: date_type):
        """Get articles by date."""
        session = self.Session()
        try:
            return session.query(NewsArticle).filter(NewsArticle.date == target_date).all()
        finally:
            session.close()
    
    def close(self):
        """Close database connection."""
        if self.engine:
            self.engine.dispose()

    def get_company_name_by_ticker(self, ticker: str) -> Optional[str]:
        """Get company name by ticker symbol."""
        session = self.Session()
        try:
            ticker_obj = session.query(Ticker).filter(Ticker.ticker == ticker).first()
            return ticker_obj.company_name if ticker_obj else None
        finally:
            session.close()

    """
    Add these methods to your Database class in database.py
    """

    def exists_recommendation(self, external_id: str) -> bool:
        """
        Check if a recommendation already exists by external_id.

        Args:
            external_id: Unique identifier for the recommendation

        Returns:
            True if recommendation exists, False otherwise
        """
        with self.Session() as session:
            try:
                result = session.query(BrokerageAnalysis).filter(
                    BrokerageAnalysis.price_comment == external_id
                    # Using price_comment to store external_id
                ).first()
                return result is not None
            except Exception as e:
                print(f"Error checking recommendation existence: {e}")
                return False


    def add_recommendation(self, rec_data: dict) -> Optional[int]:
        """
        Add a brokerage recommendation to the database.

        Args:
            rec_data: Dictionary containing recommendation data with keys:
                     - ticker: Company ticker symbol
                     - brokerage_house: Name of brokerage house
                     - price_old: Old price target
                     - price_new: New price target
                     - price_recommendation: Recommendation (buy/sell/hold)
                     - published_date: Publication date
                     - external_id: Unique identifier

        Returns:
            ID of created recommendation or None on failure
        """
        session = self.Session()
        try:
            published_date = rec_data.get('published_date', datetime.now())

            # Try to find existing NewsArticle by URL
            news_article = session.query(NewsArticle).filter(NewsArticle.url == rec_data.get('url')).first()

            # If not found, create a new NewsArticle placeholder
            if not news_article:
                news_article = NewsArticle(
                    title=rec_data.get('title', 'No title'),
                    content='',
                    url=rec_data.get('url', ''),
                    source=rec_data.get('source', 'unknown'),
                    date=published_date.date() if hasattr(published_date, 'date') else None,
                    scraped_at=datetime.now()
                )
                session.add(news_article)
                session.flush()  # Get the ID

            # Create AnalysisResult entry linked to news_article
            analysis_result = AnalysisResult(
                news_id=news_article.id,
                summary=f"Recommendation from {rec_data.get('brokerage_house')}",
                created_at=published_date
            )

            session.add(analysis_result)
            session.flush()  # Get the ID

            # Create BrokerageAnalysis entry
            brokerage_analysis = BrokerageAnalysis(
                analysis_id=analysis_result.id,
                ticker=rec_data.get('ticker'),
                brokerage_house=rec_data.get('brokerage_house'),
                price_old=rec_data.get('price_old'),
                price_new=rec_data.get('price_new'),
                price_recommendation=rec_data.get('price_recommendation'),
                price_comment=rec_data.get('external_id'),
                # Store external_id in price_comment for uniqueness check
                created_at=published_date
            )

            session.add(brokerage_analysis)
            session.commit()

            return brokerage_analysis.id

        except Exception as e:
            session.rollback()
            print(f"Error adding recommendation: {e}")
            import traceback
            traceback.print_exc()
            return None


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
    price_history = relationship('AssetPriceHistory', back_populates='asset', cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Asset(id={self.id}, ticker='{self.ticker}')>"


class TransactionType(enum.Enum):
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"


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
    purchase_value_pln = Column(Float, nullable=True)
    sale_value_pln = Column(Float, nullable=True)

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


class AssetPriceHistory(Base):
    """Stores historical price data for assets."""
    __tablename__ = 'asset_price_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey('assets.id'), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=True)
    adjusted_close = Column(Float, nullable=True)

    asset = relationship('Asset', back_populates='price_history')

    __table_args__ = (
        UniqueConstraint('asset_id', 'date', name='uix_asset_date'),
    )

    def __repr__(self):
        return f"<AssetPriceHistory(asset_id={self.asset_id}, date='{self.date}', close={self.close})>"

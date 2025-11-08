"""Database models and operations."""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Date, Index, ForeignKey, Float
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
    news_id = Column(Integer, ForeignKey('news_articles.id', ondelete='CASCADE'), nullable=False)
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
    
    def __init__(self, db_path: str):
        """Initialize database connection."""
        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
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
    
    def get_articles_by_source(self, source: str, limit: Optional[int] = None):
        """Get articles by source."""
        session = self.Session()
        try:
            query = session.query(NewsArticle).filter(NewsArticle.source == source)
            if limit:
                query = query.limit(limit)
            return query.all()
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







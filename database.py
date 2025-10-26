"""Database models and operations."""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Date, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, date as date_type
from typing import Optional

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





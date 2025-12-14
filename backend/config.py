"""Configuration management for the news monitor application."""

import os
from typing import List, Tuple
from datetime import datetime, timedelta


def parse_providers(providers_str: str) -> List[Tuple[str, str]]:
    """
    Parse providers string into list of (name, url) tuples.
    
    Args:
        providers_str: String in format "name1|url1;name2|url2"
    
    Returns:
        List of (name, url) tuples
    """
    if not providers_str:
        return []
    
    providers = []
    for provider_str in providers_str.split(';'):
        provider_str = provider_str.strip()
        if not provider_str:
            continue
        
        if '|' in provider_str:
            name, url = provider_str.split('|', 1)
            providers.append((name.strip(), url.strip()))
        else:
            # Default naming if no pipe
            providers.append((provider_str, provider_str))
    
    return providers


class Config:
    """Application configuration."""
    
    def __init__(self):
        # Database
        self.db_path = os.getenv('DB_PATH', 'news.db')
        
        # Providers (format: "name1|url1;name2|url2")
        providers_str = os.getenv('PROVIDERS', 'pap|https://biznes.pap.pl/kategoria/depesze-pap')
        self.providers = parse_providers(providers_str)
        
        # Scheduling
        self.scrape_hour = int(os.getenv('SCRAPE_HOUR', '5'))
        self.scrape_minute = int(os.getenv('SCRAPE_MINUTE', '0'))
        
        # Date range
        start_date_str = os.getenv('START_DATE', '')
        end_date_str = os.getenv('END_DATE', '')
        
        self.start_date = None
        self.end_date = None
        
        if start_date_str:
            try:
                self.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        if end_date_str:
            try:
                self.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
    
    def get_yesterday_date(self) -> datetime.date:
        """Get yesterday's date."""
        return (datetime.now() - timedelta(days=1)).date()
    
    def get_target_date(self) -> datetime.date:
        """Get the target date for scraping."""
        if self.end_date:
            return self.end_date
        return self.get_yesterday_date()







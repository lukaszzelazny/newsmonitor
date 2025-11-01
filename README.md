# News Monitor

A modular Python application for scraping and storing news articles from multiple sources.

## Features

- **Modular Architecture**: Interface-based design allowing easy addition of new news providers
- **Database Storage**: Stores scraped articles with automatic duplicate detection
- **Page Range Support**: Scrape specific page ranges from news sources
- **Scheduled Scraping**: Configure daily automated scraping (default: 5:00 AM)
- **Provider Configuration**: Manage news sources via .env file

## Installation

1. Create a virtual environment (recommended):
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your environment by copying `env.example` to `.env` and editing it:
```bash
cp env.example .env
```

4. Edit `.env` to configure news providers and settings

## Quick Test

```bash
# 1. Install dependencies
./setup.sh
# Or manually:
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Run a test scrape (first 5 pages)
python3 main.py 5

# 3. View what was scraped
python3 view_news_simple.py
```

## Usage

### Command Line Interface

```bash
# Scrape default range (pages 0-49, 50 pages total)
python main.py

# Scrape first N pages (from 0 to N-1)
python main.py 50

# Scrape specific page range
python main.py --from 0 --to 10

# Scrape starting from specific page to another
python main.py --from 10 --to 100
```

### Architecture

- `providers/` - News provider implementations
- `database/` - Database models and connection
- `core/` - Core scraping orchestration
- `config/` - Configuration management

### Viewing Scraped Data

After scraping, you can view what was downloaded:

```bash
# View all scraped articles
python3 view_news_simple.py

# View with detailed options
python3 view_news.py stats
python3 view_news.py all --limit 10
python3 view_news.py source pap
python3 view_news.py date 2025-10-25
```

### Adding New Providers

1. Create a new provider class in `providers/` implementing `BaseProvider`
2. Add the provider to the `.env` file
3. The application will automatically detect and use it

## Environment Variables

- `PROVIDERS` - Semicolon-separated list of providers (format: name|url)
- `DB_PATH` - Path to SQLite database file
- `SCRAPE_HOUR` - Hour for scheduled scraping (0-23)
- `SCRAPE_MINUTE` - Minute for scheduled scraping (0-59)

## Database Schema

- `id` - Primary key
- `title` - Article title
- `content` - Full article content
- `url` - Original article URL
- `source` - News provider name
- `date` - Article publication date
- `scraped_at` - Timestamp of scraping


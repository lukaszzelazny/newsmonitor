"""Debug PAP provider in detail."""

from bs4 import BeautifulSoup
import requests
from providers.base_provider import NewsArticle

def debug():
    url = "https://biznes.pap.pl/kategoria/depesze-pap?page=0"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    response = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(response.content, 'lxml')
    
    text_wrappers = soup.find_all('div', class_='textWrapper')
    print(f"Total textWrappers: {len(text_wrappers)}\n")
    
    articles_found = 0
    
    for i, wrapper in enumerate(text_wrappers, 1):
        link_elem = wrapper.find('a', href=True)
        if not link_elem:
            continue
        
        article_url = link_elem['href']
        if not article_url.startswith('http'):
            article_url = f"https://biznes.pap.pl{article_url}"
        
        title = link_elem.get_text(strip=True)
        
        # Show filtering steps
        is_category = '/kategoria/' in article_url
        is_short = len(title) < 20
        is_few_words = len(title.split()) < 3
        
        print(f"{i}. Title: {title[:70]}")
        print(f"   URL: {article_url}")
        print(f"   Filter: category={is_category}, short={is_short}, few_words={is_few_words}")
        
        if not is_category and not is_short and not is_few_words:
            articles_found += 1
            print(f"   ✓ Would be added as article")
        else:
            print(f"   ✗ Filtered out")
        print()

    print(f"\nTotal articles after filtering: {articles_found}")

if __name__ == '__main__':
    debug()







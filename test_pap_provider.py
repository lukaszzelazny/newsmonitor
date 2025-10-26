"""Test PAP provider directly to debug scraping."""

from providers.pap_provider import PAPProvider


def test_pap_provider():
    """Test PAP provider scraping."""
    print("="*80)
    print("TESTING PAP PROVIDER")
    print("="*80)
    
    # Create provider
    provider = PAPProvider()
    
    print(f"\nProvider: {provider.name}")
    print(f"Base URL: {provider.base_url}")
    
    # Test 1: Get articles from page 0
    print("\n" + "="*80)
    print("TEST 1: Fetching articles from page 0...")
    print("="*80)
    
    try:
        articles = provider.get_articles_for_page(0)
        print(f"\nFound {len(articles)} articles")
        
        if articles:
            print("\nFirst 3 articles:")
            for i, article in enumerate(articles[:3], 1):
                print(f"\n{i}. Title: {article.title}")
                print(f"   URL: {article.url}")
                print(f"   Date: {article.date}")
            
            # Test 2: Try to fetch content of first article
            print("\n" + "="*80)
            print("TEST 2: Fetching content from first article...")
            print("="*80)
            
            first_article = articles[0]
            print(f"\nTitle: {first_article.title}")
            print(f"URL: {first_article.url}")
            
            content = provider.get_article_content(first_article)
            if content:
                print(f"\n✓ Content fetched: {len(content)} characters")
                print(f"\nFirst 200 characters:")
                print(content[:200])
            else:
                print("\n✗ Failed to fetch content")
        else:
            print("\nNo articles found on page 0")
            print("This could mean:")
            print("  1. Website structure changed")
            print("  2. Selector needs adjustment")
            print("  3. Page requires different parameters")
    
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*80)
    print("TEST COMPLETED")
    print("="*80)


if __name__ == '__main__':
    test_pap_provider()





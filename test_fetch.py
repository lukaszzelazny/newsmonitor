"""Test script to check what HTML we actually receive."""

import requests
from bs4 import BeautifulSoup

url = "https://strefainwestorow.pl/rekomendacje/lista-rekomendacji"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
}

print(f"Fetching: {url}\n")

try:
    response = requests.get(url, headers=headers, timeout=30)
    print(f"Status code: {response.status_code}")
    print(f"Content length: {len(response.text)} characters\n")

    # Save full HTML
    with open('full_response.html', 'w', encoding='utf-8') as f:
        f.write(response.text)
    print("Saved full response to: full_response.html")

    # Parse and check for tables
    soup = BeautifulSoup(response.text, 'html.parser')

    all_tables = soup.find_all('table')
    print(f"\nTables found: {len(all_tables)}")

    for i, table in enumerate(all_tables):
        print(f"\nTable {i + 1}:")
        print(f"  Classes: {table.get('class')}")
        print(f"  ID: {table.get('id')}")

        # Count rows
        rows = table.find_all('tr')
        print(f"  Rows: {len(rows)}")

        # Show first few cells
        if rows:
            first_row = rows[0]
            cells = first_row.find_all(['th', 'td'])
            if cells:
                cell_texts = [cell.get_text(strip=True)[:30] for cell in cells[:5]]
                print(f"  First row: {cell_texts}")

    # Check for specific classes
    print("\n" + "=" * 80)
    print("Searching for specific elements:")

    rec_table = soup.find('table', class_='table-recommendations-desktop')
    print(f"table-recommendations-desktop: {'FOUND' if rec_table else 'NOT FOUND'}")

    hover_table = soup.find('table', class_='table-hover')
    print(f"table-hover: {'FOUND' if hover_table else 'NOT FOUND'}")

    tbody = soup.find('tbody')
    print(f"tbody: {'FOUND' if tbody else 'NOT FOUND'}")

    # Look for the main content
    main = soup.find('main', class_='main-content')
    if main:
        print(f"\nMain content found. Length: {len(str(main))} chars")
        # Save main content only
        with open('main_content.html', 'w', encoding='utf-8') as f:
            f.write(str(main))
        print("Saved main content to: main_content.html")

    print("\n" + "=" * 80)
    print("Check the saved HTML files to see what content we're receiving.")

except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
"""Debug script to inspect the recommendations page structure."""

import requests
from bs4 import BeautifulSoup

url = "https://strefainwestorow.pl/rekomendacje/lista-rekomendacji"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
}

print(f"Fetching: {url}\n")

try:
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    html = response.text
    soup = BeautifulSoup(html, 'html.parser')

    print("=" * 80)
    print("PAGE STRUCTURE ANALYSIS")
    print("=" * 80)

    # Check for tables
    all_tables = soup.find_all('table')
    print(f"\n1. TABLES FOUND: {len(all_tables)}")
    for i, table in enumerate(all_tables):
        classes = table.get('class', [])
        id_attr = table.get('id', '')
        print(f"   Table {i + 1}: classes={classes}, id={id_attr}")

        # Count rows
        rows = table.find_all('tr')
        print(f"           Rows: {len(rows)}")

        # Show first row
        if rows:
            first_row = rows[0]
            cells = first_row.find_all(['th', 'td'])
            print(f"           First row cells: {len(cells)}")
            if cells:
                headers_text = [cell.get_text(strip=True)[:30] for cell in cells[:6]]
                print(f"           Headers: {headers_text}")

    # Check for divs with common patterns
    print(f"\n2. DIVS WITH 'rekomendacje' IN CLASS:")
    rekomendacje_divs = soup.find_all('div',
                                      class_=lambda x: x and 'rekomendacje' in str(
                                          x).lower())
    for div in rekomendacje_divs[:5]:
        classes = div.get('class', [])
        print(f"   Found: {classes}")

    # Check for lists
    print(f"\n3. LISTS (ul/ol):")
    lists = soup.find_all(['ul', 'ol'])
    print(f"   Total lists: {len(lists)}")
    for lst in lists[:5]:
        classes = lst.get('class', [])
        items = lst.find_all('li')
        print(f"   List: classes={classes}, items={len(items)}")

    # Check main content area
    print(f"\n4. MAIN CONTENT AREAS:")
    main_selectors = [
        ('main', None),
        ('div', 'content'),
        ('div', 'main-content'),
        ('div', 'container'),
        ('article', None),
    ]

    for tag, class_name in main_selectors:
        if class_name:
            elements = soup.find_all(tag, class_=lambda x: x and class_name in str(
                x).lower())
        else:
            elements = soup.find_all(tag)

        if elements:
            print(
                f"   {tag} {f'with {class_name}' if class_name else ''}: {len(elements)} found")

    # Look for JavaScript data
    print(f"\n5. SCRIPT TAGS:")
    scripts = soup.find_all('script')
    print(f"   Total scripts: {len(scripts)}")

    for script in scripts:
        src = script.get('src', '')
        if 'rekomendacje' in src.lower() or 'recommendation' in src.lower():
            print(f"   Relevant: {src}")

        # Check for inline JSON data
        if script.string and (
                'recommendations' in script.string.lower() or 'rekomendacje' in script.string.lower()):
            snippet = script.string[:200].replace('\n', ' ')
            print(f"   Inline data found: {snippet}...")

    # Check for data attributes
    print(f"\n6. ELEMENTS WITH data-* ATTRIBUTES:")
    data_elements = soup.find_all(attrs={"data-recommendations": True})
    data_elements += soup.find_all(attrs={"data-rekomendacje": True})
    for elem in data_elements[:5]:
        print(f"   {elem.name}: {elem.attrs}")

    # Save sample HTML for inspection
    print(f"\n7. SAVING HTML SAMPLE")

    # Try to find the most relevant section
    body = soup.find('body')
    if body:
        # Save first 50KB of body content
        body_html = str(body)[:50000]

        with open('recommendations_page_sample.html', 'w', encoding='utf-8') as f:
            f.write(body_html)
        print(f"   Saved first 50KB to: recommendations_page_sample.html")

    print("\n" + "=" * 80)
    print("Analysis complete! Check the output above and the HTML sample file.")
    print("=" * 80)

except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
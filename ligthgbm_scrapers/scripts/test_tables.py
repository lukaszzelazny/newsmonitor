import requests
from bs4 import BeautifulSoup
import json

r = requests.get('https://www.gpw.pl/spolki')
soup = BeautifulSoup(r.text, 'html.parser')

# Find the main companies table
table = soup.find('table', {'class': 'table'})
if table:
    headers = [th.text.strip() for th in table.find_all('th')]
    print("Headers:", headers)
    rows = table.find('tbody').find_all('tr') if table.find('tbody') else table.find_all('tr')[1:]
    for row in rows[:3]:
        cells = [td.text.strip() for td in row.find_all('td')]
        print(cells)
else:
    print("No table with class 'table' found. Let's find all tables...")
    for t in soup.find_all('table'):
        print("Table class:", t.get('class'))
        headers = [th.text.strip() for th in t.find_all('th')]
        print(" Headers:", headers)
        rows = t.find_all('tr')
        if len(rows) > 1:
            print(" Row 1:", [td.text.strip() for td in rows[1].find_all('td')])

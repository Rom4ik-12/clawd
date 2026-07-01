import urllib.request
from bs4 import BeautifulSoup

url = "https://core.telegram.org/bots/api"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as response:
    html = response.read().decode('utf-8')

soup = BeautifulSoup(html, 'html.parser')
for h4 in soup.find_all('h4'):
    text = h4.get_text()
    if 'formatting' in text.lower():
        print("Found heading:", text)
        node = h4.next_sibling
        while node and node.name not in ['h3', 'h4']:
            if node.name:
                print(node.get_text())
            node = node.next_sibling

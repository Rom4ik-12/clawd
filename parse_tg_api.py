import urllib.request
from bs4 import BeautifulSoup

url = "https://core.telegram.org/bots/api"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as response:
    html = response.read().decode('utf-8')

soup = BeautifulSoup(html, 'html.parser')

def extract_section(anchor_name):
    print(f"\n--- SECTION: {anchor_name} ---")
    anchor = soup.find('a', {'name': anchor_name})
    if not anchor:
        print(f"Anchor '{anchor_name}' not found.")
        return
    
    header = anchor.parent
    node = header.next_sibling
    while node:
        if node.name in ['h3', 'h4']:
            break
        if node.name:
            print(node.get_text().strip())
        node = node.next_sibling

extract_section('richmessage')
extract_section('inputrichmessage')
extract_section('sendrichmessage')
extract_section('sendrichmessagedraft')

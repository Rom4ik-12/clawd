import urllib.request
import json
from config import PANEL_BOT_TOKEN, OWNER_ID

url = f'https://api.telegram.org/bot{PANEL_BOT_TOKEN}/sendMessage'
payload = {
  'chat_id': OWNER_ID,
  'text': 'Test\n\n```\n| A | B |\n|---|---|\n| C | D |\n```',
  'parse_mode': 'MarkdownV2'
}
req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req) as f:
        print('SUCCESS:', f.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print('FAILED:', e.code, e.read().decode('utf-8'))

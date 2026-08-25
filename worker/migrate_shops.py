import json
from urllib.parse import urlparse
import re
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data", "munition_daten.json")

def generate_id(caliber, brand, shop, amount):
    s = f"{caliber}-{brand}-{amount}-{shop}".lower()
    s = re.sub(r'[^a-z0-9]', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-')

if not os.path.exists(DATA_FILE):
    print("No data file found.")
    exit(0)

with open(DATA_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

new_data = {}
for item in data:
    parsed_domain = urlparse(item['url']).netloc.replace("www.", "")
    if parsed_domain:
        item['shop'] = parsed_domain
    
    new_id = generate_id(item['caliber'], item['brand'], item['shop'], item['amount'])
    item['id'] = new_id
    
    if new_id in new_data:
        # Merge histories
        new_data[new_id]['history'].extend(item['history'])
        # Sort history by date
        new_data[new_id]['history'].sort(key=lambda x: x['date'])
        
        # Take latest price
        if item['last_update'] > new_data[new_id]['last_update']:
            new_data[new_id]['current_price_per_round'] = item['current_price_per_round']
            new_data[new_id]['last_update'] = item['last_update']
    else:
        new_data[new_id] = item

final_list = list(new_data.values())
with open(DATA_FILE, 'w', encoding='utf-8') as f:
    json.dump(final_list, f, indent=2, ensure_ascii=False)

print(f"Migration complete. Merged {len(data) - len(final_list)} duplicates. Total items: {len(final_list)}.")

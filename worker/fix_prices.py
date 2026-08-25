import json
import os

DATA_FILE = "data/munition_daten.json"
with open(DATA_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

count = 0
for d in data:
    h = d.get('history', [])
    if len(h) > 1:
        prev_p = h[-2]['price_per_round']
        curr_p = h[-1]['price_per_round']
        
        # Check if price jumped by more than 15% (up or down)
        if prev_p > 0 and abs(curr_p - prev_p) / prev_p > 0.15:
            print(f"Fixing: {d['brand']} {d['caliber']} ({d['shop']}) | {prev_p} -> {curr_p}")
            # Fix it
            h.pop()
            d['current_price_per_round'] = h[-1].get('price_per_round', d.get('current_price_per_round'))
            d['last_update'] = "2020-01-01T00:00:00" # Force re-track
            if 'price_selector' in d:
                del d['price_selector']
            count += 1

with open(DATA_FILE, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"\nSuccessfully fixed {count} erroneous price jumps!")

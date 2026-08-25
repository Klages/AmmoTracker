import os
import json
import time
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from dotenv import load_dotenv
import argparse
from urllib.parse import urljoin, urlparse

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
URLS_FILE = os.path.join(DATA_DIR, "urls.json")
DATA_FILE = os.path.join(DATA_DIR, "munition_daten.json")

def normalize_caliber(k):
    if not k: return "IGNORE"
    k_lower = str(k).lower().replace(" ", "").replace("-", "")
    
    if "9mm" in k_lower or "9x19" in k_lower or "para" in k_lower or "luger" in k_lower:
        return "9x19mm"
    if "223" in k_lower or "5.56" in k_lower or "gp90" in k_lower:
        return ".223 Rem / 5.56x45"
    if "7.62x39" in k_lower:
        return "7.62x39mm"
    return "IGNORE"

def generate_id(caliber, brand, shop, amount):
    s = f"{caliber}-{brand}-{amount}-{shop}".lower()
    s = re.sub(r'[^a-z0-9]', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-')

def clean_html(html_content, base_url):
    soup = BeautifulSoup(html_content, "html.parser")
    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
        element.decompose()
    for a in soup.find_all('a'):
        href = a.get('href')
        if href and not href.startswith('#') and not href.startswith('javascript:'):
            abs_url = urljoin(base_url, href)
            a.replace_with(f" {a.get_text(strip=True)} (Link: {abs_url}) ")
    text = soup.get_text(separator=" ")
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:200000]

def ask_gemini(prompt, is_json=True):
    if not client:
        print("API Key missing!")
        return None
        
    models_to_try = [
        'gemini-2.5-flash',
        'gemini-1.5-flash',
        'gemini-1.5-pro'
    ]
    for model_name in models_to_try:
        try:
            if is_json:
                result = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
            else:
                result = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
            
            text = result.text.strip()
            if is_json:
                if text.startswith("```"):
                    lines = text.split('\n')
                    if lines[0].startswith("```"): lines = lines[1:]
                    if lines[-1].startswith("```"): lines = lines[:-1]
                    text = "\n".join(lines).strip()
                try:
                    return json.loads(text)
                except json.JSONDecodeError as e:
                    print(f"JSON Error on {model_name}: {e}. Output: {text[:200]}")
                    continue
            return text
        except Exception as e:
            print(f"Model {model_name} failed: {e}")
            continue
    return None

def fetch_html(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
    except requests.exceptions.SSLError:
        print(f"SSL certificate at {url} invalid, trying unsecured connection...")
        response = requests.get(url, headers=headers, timeout=15, verify=False)
    response.raise_for_status()
    return response.text

# ---------------------------------------------------------
# DISCOVERY MODE LOGIC
# ---------------------------------------------------------

def scrape_page(url, mode="both"):
    print(f"Scraping {url} (Mode: {mode})...")
    try:
        html = fetch_html(url)
        text = clean_html(html, url)
        
        if mode == "both":
            categories_anweisung = """
            ADDITIONALLY: Find all links in the navigation or on the page that lead to ammunition categories.
            Return a JSON object with two keys:
            - "products": (Array with the articles as defined below)
            - "categories": (Array of strings containing the found category URLs)
            """
        else:
            categories_anweisung = """
            ONLY return a JSON object with one key:
            - "products": (Array with the articles as defined below)
            """

        prompt = f"""
        You are an expert at extracting product data from e-commerce websites.
        Analyze the following text from a Swiss gun shop ({url}).
        
        TASK: Find **ALL** offers for ammunition, but **ONLY** for the following calibers:
        - 9mm (9x19, 9mm Para, 9mm Luger)
        - .223 Rem (or 5.56x45, GP90)
        - 7.62x39
        
        IMPORTANT: 
        1. Find EVERY package size.
        2. IGNORE airgun pellets, .22 LR, blank rounds, shotgun shells.
        3. STRICTLY IGNORE all reloading items: primers, bullets, empty brass, and powder! These are not complete rounds.
        
        {categories_anweisung}

        The "products" array must contain objects with the following keys:
        - "caliber": (String)
        - "brand": (String)
        - "shop": (String)
        - "total_price_chf": (Float)
        - "amount": (Integer)
        - "url": (String, the link to the offer or '{url}')
        - "in_stock": (Boolean)
        
        Text:
        {text}
        """
        
        data = ask_gemini(prompt, is_json=True)
        if not data or not isinstance(data, dict):
            return {"products": [], "categories": []}
            
        return {
            "products": data.get("products", []),
            "categories": data.get("categories", [])
        }
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return {"products": [], "categories": []}

def run_discovery():
    print(f"[{datetime.now().isoformat()}] Starting DISCOVERY run...")
    os.makedirs(DATA_DIR, exist_ok=True)
    
    if not os.path.exists(URLS_FILE):
        print(f"No {URLS_FILE} found. Creating empty.")
        with open(URLS_FILE, 'w') as f:
            json.dump([], f)
        return
        
    with open(URLS_FILE, 'r') as f:
        urls = json.load(f)
        
    data_dict = {}
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
            for item in existing_data:
                data_dict[item['id']] = item
                
    blacklist_ids = []
    BLACKLIST_FILE = os.path.join(DATA_DIR, "blacklist_ids.json")
    if os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, 'r') as f:
            blacklist_ids = json.load(f)
                
    all_new_items = []
    level_1_urls = set()
    
    print("--- PHASE 1: Start pages ---")
    for url in urls:
        result = scrape_page(url, mode="both")
        all_new_items.extend(result.get("products", []))
        for cat_url in result.get("categories", []):
            if cat_url not in urls:
                level_1_urls.add(cat_url)
        time.sleep(2) 
        
    if level_1_urls:
        print(f"--- PHASE 2: {len(level_1_urls)} Category pages discovered ---")
        for url in level_1_urls:
            result = scrape_page(url, mode="products")
            all_new_items.extend(result.get("products", []))
            time.sleep(2)
        
    current_time = datetime.now().isoformat()
    
    for item in all_new_items:
        try:
            caliber = normalize_caliber(item.get('caliber', 'Unknown'))
            if caliber == "IGNORE": continue
                
            brand = str(item.get('brand', 'Unknown')).strip().title()
            item_url = str(item.get('url', ''))
            
            parsed_domain = urlparse(item_url).netloc.replace("www.", "")
            shop = parsed_domain if parsed_domain else str(item.get('shop', 'Unknown'))
            
            preis = float(item.get('total_price_chf', 0))
            amount = int(item.get('amount', 1))
            
            if preis <= 0 or amount <= 0 or amount > 1000: continue
            price_per_round = round(preis / amount, 3)
            if price_per_round < 0.10: continue
            
            in_stock = item.get('in_stock')
            if in_stock is False or str(in_stock).lower() == "false": continue
                
            item_id = generate_id(caliber, brand, shop, amount)
            if item_id in blacklist_ids:
                print(f"  -> Skipping blacklisted item: {item_id}")
                continue
            
            history_entry = {
                "date": current_time,
                "total_price_chf": preis,
                "amount": amount,
                "price_per_round": price_per_round
            }
            
            if item_id in data_dict:
                history = data_dict[item_id].get('history', [])
                history.append(history_entry)
                data_dict[item_id]['history'] = history[-30:]
                data_dict[item_id]['last_update'] = current_time
                data_dict[item_id]['current_price_per_round'] = price_per_round
            else:
                data_dict[item_id] = {
                    "id": item_id,
                    "caliber": caliber,
                    "brand": brand,
                    "shop": shop,
                    "url": item_url,
                    "amount": amount,
                    "current_price_per_round": price_per_round,
                    "last_update": current_time,
                    "history": [history_entry]
                }
        except Exception as e:
            pass
            
    final_list = list(data_dict.values())
    final_list.sort(key=lambda x: x.get('current_price_per_round', 999))
    
    if os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, 'r') as f:
            current_blacklist = json.load(f)
        final_list = [item for item in final_list if item['id'] not in current_blacklist]

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_list, f, indent=2, ensure_ascii=False)
    print(f"[{datetime.now().isoformat()}] Discovery completed. Data saved.")


# ---------------------------------------------------------
# TRACKING MODE LOGIC (Hybrid CSS + LLM)
# ---------------------------------------------------------

def fallback_find_selector(url, html, brand, caliber, amount):
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
        element.decompose()
    dom_text = str(soup.body)[:100000] if soup.body else str(soup)[:100000]
    
    prompt = f"""
    You are a web scraping expert.
    Here is the HTML code of a website ({url}).
    We are looking for the EXACT price for this product in this amount: {brand} {caliber} ({amount} pieces).

    TASK:
    1. You MUST find the price for {amount} pieces! Attention: Often the price for a small package (e.g. 50 pieces) is prominently displayed at the top, while the price for {amount} pieces is further down in text (e.g. "1000 Stk / Fr. 229.00").
    2. Create a ROBUST CSS selector that ONLY extracts the price for {amount} pieces.
    3. If the price for {amount} pieces only exists as running text (without a unique class), set "css_selector" strictly to null.
    4. If this URL is obviously an overview or category page with many different products, set "is_list_page" to true.

    ONLY return a JSON object with:
    - "is_list_page": boolean
    - "css_selector": string or null (the robust CSS selector for {amount} pieces)
    - "current_price_chf": float or null (the exact extracted price for {amount} pieces)
    - "in_stock": boolean
    
    HTML:
    {dom_text}
    """
    return ask_gemini(prompt, is_json=True)

def run_tracking():
    print(f"[{datetime.now().isoformat()}] Starting TRACKING run...")
    if not os.path.exists(DATA_FILE):
        print("No data to track. Please run 'discover' first.")
        return
        
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    updated_count = 0
    current_time = datetime.now().isoformat()
    
    for item in data:
        url = item.get('url')
        if not url or "http" not in url:
            continue
            
        print(f"\nTracking {item['id']} at {url}...")
        
        try:
            html = fetch_html(url)
        except Exception as e:
            print(f"  -> Error fetching: {e}")
            continue
            
        selector = item.get('price_selector')
        price_found = False
        
        if selector and selector != "LIST":
            soup = BeautifulSoup(html, "html.parser")
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator=" ").strip()
                # Extrahiere Zahlen wie 12.50, 12,50, 12.- oder 1'200.50
                text_clean = text.replace("'", "")
                match = re.search(r'(\d+[\.,]\d{2}|\d+\.-)', text_clean)
                if match:
                    val = match.group(1).replace(',', '.').replace('.-', '.00')
                    try:
                        price = float(val)
                        if price > 0:
                            amount = item.get('amount')
                            if not isinstance(amount, (int, float)) or amount <= 0:
                                history = item.get('history', [])
                                amount = history[-1].get('amount', 1) if history else 1
                                item['amount'] = amount
                                
                            new_pps = round(price / amount, 3)
                            if new_pps < 0.10:
                                print(f"  -> [FAST-TRACK] Warning: Price {new_pps} CHF/round too low (Price={price}, Amount={amount}). Ignoring CSS.")
                                item['price_selector'] = None
                                price_found = False
                            else:
                                print(f"  -> [FAST-TRACK] Price via CSS ({selector}) found: {price} CHF")
                                item['current_price_per_round'] = new_pps
                                history_entry = {
                                    "date": current_time,
                                    "total_price_chf": price,
                                    "amount": item.get('amount'),
                                    "price_per_round": item['current_price_per_round']
                                }
                                item['history'].append(history_entry)
                                item['history'] = item['history'][-30:]
                                item['last_update'] = current_time
                                price_found = True
                                updated_count += 1
                    except ValueError:
                        pass
        
        if not price_found:
            print("  -> [SLOW-TRACK] Fallback to AI analysis...")
            if item.get('price_selector') == "LIST":
                print("  -> Marked as category page, skipping AI fallback for this item.")
                continue
                
            res = fallback_find_selector(url, html, item.get('brand'), item.get('caliber'), item.get('amount'))
            if res:
                if res.get('is_list_page'):
                    print("  -> AI reports: This is a category page. CSS tracking disabled.")
                    item['price_selector'] = "LIST"
                elif res.get('current_price_chf'):
                    price = float(res['current_price_chf'])
                    amount = item.get('amount')
                    if not isinstance(amount, (int, float)) or amount <= 0:
                        history = item.get('history', [])
                        amount = history[-1].get('amount', 1) if history else 1
                        item['amount'] = amount
                        
                    new_pps = round(price / amount, 3)
                    if new_pps < 0.10:
                        print(f"  -> [KI-FALLBACK] Warning: Price {new_pps} CHF/round too low (Price={price}, Amount={amount}). Discarding update.")
                    else:
                        css_selector = res.get('css_selector')
                        if css_selector:
                            print(f"  -> [KI-FALLBACK] New selector found: {css_selector} | Price: {price} CHF")
                            item['price_selector'] = css_selector
                        else:
                            print(f"  -> [KI-FALLBACK] No CSS selector possible for variant. AI price used: {price} CHF")
                            item['price_selector'] = None
                            
                        item['current_price_per_round'] = new_pps
                        history_entry = {
                            "date": current_time,
                            "total_price_chf": price,
                            "amount": item.get('amount'),
                            "price_per_round": item['current_price_per_round']
                        }
                        item['history'].append(history_entry)
                        item['history'] = item['history'][-30:]
                        item['last_update'] = current_time
                        updated_count += 1
                else:
                    print("  -> AI could not find price or selector is null.")
            time.sleep(2) # API Rate Limiting

    BLACKLIST_FILE = os.path.join(DATA_DIR, "blacklist_ids.json")
    if os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, 'r') as f:
            current_blacklist = json.load(f)
        data = [item for item in data if item['id'] not in current_blacklist]

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n[{datetime.now().isoformat()}] Tracking finished. {updated_count} prices updated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ammo Tracker Scraper")
    parser.add_argument("--mode", choices=["discover", "track"], default="track", 
                        help="discover: search for new products. track: update known products via CSS.")
    args = parser.parse_args()
    
    if args.mode == "discover":
        run_discovery()
    else:
        run_tracking()

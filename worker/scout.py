import os
import json
import time
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from google import genai
from google.genai import types
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
URLS_FILE = os.path.join(DATA_DIR, "urls.json")

SEARCH_QUERIES = [
    "9mm Munition kaufen Schweiz",
    "Waffenshop Schweiz online",
    "Pistolenmunition online bestellen ch",
    "GP90 Munition kaufen",
    "Schweizer Waffenhändler Munition",
    "Waffenbörse Schweiz Munition"
]

BLACKLIST_DOMAINS = [
    "wikipedia.org", "facebook.com", "instagram.com", "youtube.com",
    "admin.ch", "ch.ch", "twitter.com", "x.com", "amazon.de", 
    "ricardo.ch", "egun.ch", "tutti.ch", "pinterest.com", "reddit.com"
]

def get_base_url(url):
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/"
    except:
        return None

def get_domain(url):
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().replace("www.", "")
    except:
        return ""

def ask_gemini_validation(html_text, url):
    if not client:
        return False
        
    prompt = f"""
    You are a web classifier.
    Here is the raw text of the homepage of a website ({url}).
    
    TASK: Is this a real Swiss online shop (E-commerce) that sells firearms or real ammunition (like 9mm, .223 Rem, etc.)?
    - It MUST be a shop (with shopping cart / prices / offers), not just an informational site.
    - It MUST be located in Switzerland or deliver to Switzerland (often indicated by .ch, CHF prices, or addresses).
    - It MUST sell firearms or live ammunition (not purely an Airsoft, Paintball, or Knife shop).
    
    Reply ONLY with a JSON object with exactly this key:
    {{"is_ammo_shop": true}} or {{"is_ammo_shop": false}}
    
    TEXT OF THE HOMEPAGE:
    {html_text[:50000]}
    """
    
    try:
        result = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        text = result.text.strip()
        if text.startswith("```"):
            lines = text.split('\n')
            if lines[0].startswith("```"): lines = lines[1:]
            if lines[-1].startswith("```"): lines = lines[:-1]
            text = "\n".join(lines).strip()
        data = json.loads(text)
        return data.get("is_ammo_shop", False)
    except Exception as e:
        print(f"Error in AI validation for {url}: {e}")
        return False

def run_scout():
    print(f"[{datetime.now().isoformat()}] Starting SCOUT run...")
    
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
        
    known_urls = []
    if os.path.exists(URLS_FILE):
        with open(URLS_FILE, 'r') as f:
            known_urls = json.load(f)
            
    known_domains = set([get_domain(u) for u in known_urls if u])
    
    found_urls = set()
    
    # 1. Search using DuckDuckGo
    print("Searching for new URLs via DuckDuckGo...")
    try:
        with DDGS() as ddgs:
            for query in SEARCH_QUERIES:
                print(f" -> Query: '{query}'")
                results = ddgs.text(query, region='ch-de', max_results=15)
                for r in results:
                    url = r.get("href")
                    if url:
                        found_urls.add(url)
                time.sleep(2) # be nice
    except Exception as e:
        print(f"Error in DuckDuckGo search: {e}")
        
    new_base_urls = set()
    for url in found_urls:
        domain = get_domain(url)
        if not domain: continue
        
        # Blacklist check
        is_blacklisted = any(bl in domain for bl in BLACKLIST_DOMAINS)
        if is_blacklisted: continue
        
        # Already known?
        if domain in known_domains: continue
        
        base_url = get_base_url(url)
        if base_url:
            new_base_urls.add(base_url)
            
    print(f"{len(new_base_urls)} potentially new base URLs found.")
    
    new_shops_added = 0
    
    # 2. Validate with Gemini
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    for base_url in new_base_urls:
        print(f"\nChecking potential new shop: {base_url} ...")
        try:
            response = requests.get(base_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            for element in soup(["script", "style", "nav", "footer"]):
                element.decompose()
            text = soup.get_text(separator=" ", strip=True)
            
            is_shop = ask_gemini_validation(text, base_url)
            
            if is_shop:
                print(f" -> [SUCCESS] AI confirms: {base_url} is an ammo shop!")
                # Double check to prevent race conditions or duplicates
                if base_url not in known_urls:
                    known_urls.append(base_url)
                    known_domains.add(get_domain(base_url))
                    new_shops_added += 1
                    
                    # Save immediately so we don't lose it if it crashes
                    with open(URLS_FILE, 'w') as f:
                        json.dump(known_urls, f, indent=2)
            else:
                print(f" -> [REJECTED] AI says: Not a suitable shop.")
                
            time.sleep(2)
        except Exception as e:
            print(f" -> [ERROR] Could not check {base_url}: {e}")

    print(f"[{datetime.now().isoformat()}] SCOUT finished. {new_shops_added} new shops added.")

if __name__ == "__main__":
    run_scout()

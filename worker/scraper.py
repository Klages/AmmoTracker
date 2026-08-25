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

def normalize_kaliber(k):
    if not k: return "IGNORE"
    k_lower = str(k).lower().replace(" ", "").replace("-", "")
    
    if "9mm" in k_lower or "9x19" in k_lower or "para" in k_lower or "luger" in k_lower:
        return "9x19mm"
    if "223" in k_lower or "5.56" in k_lower or "gp90" in k_lower:
        return ".223 Rem / 5.56x45"
    if "7.62x39" in k_lower:
        return "7.62x39mm"
    return "IGNORE"

def generate_id(kaliber, marke, shop, menge):
    s = f"{kaliber}-{marke}-{menge}-{shop}".lower()
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
        print("API Key fehlt!")
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
                    print(f"JSON Error bei {model_name}: {e}. Output: {text[:200]}")
                    continue
            return text
        except Exception as e:
            print(f"Modell {model_name} fehlgeschlagen: {e}")
            continue
    return None

def fetch_html(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
    except requests.exceptions.SSLError:
        print(f"SSL Zertifikat bei {url} ungültig, versuche ungesicherte Verbindung...")
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
            kategorien_anweisung = """
            ZUSÄTZLICH: Finde alle Links in der Navigation oder auf der Seite, die zu Munitions-Kategorien führen.
            Gib ein JSON-Objekt mit zwei Schlüsseln zurück:
            - "produkte": (Array mit den Artikeln wie unten definiert)
            - "kategorien": (Array mit Strings, die die gefundenen Kategorie-URLs enthalten)
            """
        else:
            kategorien_anweisung = """
            Gib NUR ein JSON-Objekt mit einem Schlüssel zurück:
            - "produkte": (Array mit den Artikeln wie unten definiert)
            """

        prompt = f"""
        Du bist ein Experte im Extrahieren von Produktdaten aus E-Commerce Webseiten.
        Analysiere den folgenden Text von einem Schweizer Waffenshop ({url}).
        
        AUFGABE: Finde **ALLE** Angebote für Munition, aber **NUR** für folgende Kaliber:
        - 9mm (9x19, 9mm Para, 9mm Luger)
        - .223 Rem (oder 5.56x45, GP90)
        - 7.62x39
        
        WICHTIG: 
        1. Finde JEDE Packungsgrösse.
        2. IGNORIERE Luftgewehrkugeln, .22 LR, Schreckschuss, Schrotpatronen.
        3. IGNORIERE ZWINGEND alle Wiederladeartikel: Zündhütchen (Primers), Geschosse (Bullets), leere Hülsen (Brass), und Pulver! Dies sind keine Patronen.
        
        {kategorien_anweisung}

        Das Array "produkte" muss Objekte mit folgenden Schlüsseln enthalten:
        - "kaliber": (String)
        - "marke": (String)
        - "shop": (String)
        - "preis_total_chf": (Float)
        - "menge": (Integer)
        - "url": (String, der Link zum Angebot oder '{url}')
        - "auf_lager": (Boolean)
        
        Text:
        {text}
        """
        
        data = ask_gemini(prompt, is_json=True)
        if not data or not isinstance(data, dict):
            return {"produkte": [], "kategorien": []}
            
        return {
            "produkte": data.get("produkte", []),
            "kategorien": data.get("kategorien", [])
        }
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return {"produkte": [], "kategorien": []}

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
    
    print("--- PHASE 1: Startseiten ---")
    for url in urls:
        result = scrape_page(url, mode="both")
        all_new_items.extend(result.get("produkte", []))
        for cat_url in result.get("kategorien", []):
            if cat_url not in urls:
                level_1_urls.add(cat_url)
        time.sleep(2) 
        
    if level_1_urls:
        print(f"--- PHASE 2: {len(level_1_urls)} Kategorie-Seiten entdeckt ---")
        for url in level_1_urls:
            result = scrape_page(url, mode="products")
            all_new_items.extend(result.get("produkte", []))
            time.sleep(2)
        
    current_time = datetime.now().isoformat()
    
    for item in all_new_items:
        try:
            kaliber = normalize_kaliber(item.get('kaliber', 'Unknown'))
            if kaliber == "IGNORE": continue
                
            marke = str(item.get('marke', 'Unknown')).strip().title()
            item_url = str(item.get('url', ''))
            
            parsed_domain = urlparse(item_url).netloc.replace("www.", "")
            shop = parsed_domain if parsed_domain else str(item.get('shop', 'Unknown'))
            
            preis = float(item.get('preis_total_chf', 0))
            menge = int(item.get('menge', 1))
            
            if preis <= 0 or menge <= 0 or menge > 1000: continue
            preis_pro_schuss = round(preis / menge, 3)
            if preis_pro_schuss < 0.10: continue
            
            auf_lager = item.get('auf_lager')
            if auf_lager is False or str(auf_lager).lower() == "false": continue
                
            item_id = generate_id(kaliber, marke, shop, menge)
            if item_id in blacklist_ids:
                print(f"  -> Skipping blacklisted item: {item_id}")
                continue
            
            history_entry = {
                "date": current_time,
                "preis_total_chf": preis,
                "menge": menge,
                "preis_pro_schuss": preis_pro_schuss
            }
            
            if item_id in data_dict:
                history = data_dict[item_id].get('history', [])
                history.append(history_entry)
                data_dict[item_id]['history'] = history[-30:]
                data_dict[item_id]['letztes_update'] = current_time
                data_dict[item_id]['aktueller_preis_pro_schuss'] = preis_pro_schuss
            else:
                data_dict[item_id] = {
                    "id": item_id,
                    "kaliber": kaliber,
                    "marke": marke,
                    "shop": shop,
                    "url": item_url,
                    "menge": menge,
                    "aktueller_preis_pro_schuss": preis_pro_schuss,
                    "letztes_update": current_time,
                    "history": [history_entry]
                }
        except Exception as e:
            pass
            
    final_list = list(data_dict.values())
    final_list.sort(key=lambda x: x.get('aktueller_preis_pro_schuss', 999))
    
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

def fallback_find_selector(url, html, marke, kaliber, menge):
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
        element.decompose()
    dom_text = str(soup.body)[:100000] if soup.body else str(soup)[:100000]
    
    prompt = f"""
    Du bist ein Web-Scraping-Experte.
    Hier ist der HTML-Code einer Webseite ({url}).
    Wir suchen den Preis EXAKT für dieses Produkt in dieser Menge: {marke} {kaliber} ({menge} Stück).

    AUFGABE:
    1. Finde den Preis zwingend für {menge} Stück! Achtung: Häufig steht oben gross der Preis für eine kleine Packung (z.B. 50 Stück) und der Preis für {menge} Stück steht als Text weiter unten (z.B. "1000 Stk / Fr. 229.00").
    2. Erstelle einen ROBUSTEN CSS-Selektor, der NUR den Preis für {menge} Stück extrahiert.
    3. Wenn der Preis für {menge} Stück nur als Fliesstext (ohne eindeutige Klasse) existiert, setze "css_selector" zwingend auf null.
    4. Wenn diese URL offensichtlich eine Übersichts- oder Kategorie-Seite mit vielen verschiedenen Produkten ist, setze "is_list_page" auf true.

    Gib NUR ein JSON-Objekt zurück mit:
    - "is_list_page": boolean
    - "css_selector": string oder null (der robuste CSS-Selektor für {menge} Stück)
    - "current_price_chf": float oder null (der exakte extrahierte Preis für {menge} Stück)
    - "auf_lager": boolean
    
    HTML:
    {dom_text}
    """
    return ask_gemini(prompt, is_json=True)

def run_tracking():
    print(f"[{datetime.now().isoformat()}] Starting TRACKING run...")
    if not os.path.exists(DATA_FILE):
        print("Keine Daten zum Tracken. Bitte zuerst 'discover' ausführen.")
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
            print(f"  -> Fehler beim Abrufen: {e}")
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
                            menge = item.get('menge')
                            if not isinstance(menge, (int, float)) or menge <= 0:
                                history = item.get('history', [])
                                menge = history[-1].get('menge', 1) if history else 1
                                item['menge'] = menge
                                
                            new_pps = round(price / menge, 3)
                            if new_pps < 0.10:
                                print(f"  -> [FAST-TRACK] Warnung: Preis {new_pps} CHF/Schuss zu tief (Preis={price}, Menge={menge}). Ignoriere CSS.")
                                item['price_selector'] = None
                                price_found = False
                            else:
                                print(f"  -> [FAST-TRACK] Preis via CSS ({selector}) gefunden: {price} CHF")
                                item['aktueller_preis_pro_schuss'] = new_pps
                                history_entry = {
                                    "date": current_time,
                                    "preis_total_chf": price,
                                    "menge": item.get('menge'),
                                    "preis_pro_schuss": item['aktueller_preis_pro_schuss']
                                }
                                item['history'].append(history_entry)
                                item['history'] = item['history'][-30:]
                                item['letztes_update'] = current_time
                                price_found = True
                                updated_count += 1
                    except ValueError:
                        pass
        
        if not price_found:
            print("  -> [SLOW-TRACK] Fallback zur KI-Analyse...")
            if item.get('price_selector') == "LIST":
                print("  -> Ist als Kategorie-Seite markiert, überspringe KI-Fallback für dieses Item.")
                continue
                
            res = fallback_find_selector(url, html, item.get('marke'), item.get('kaliber'), item.get('menge'))
            if res:
                if res.get('is_list_page'):
                    print("  -> KI meldet: Dies ist eine Kategorie-Seite. CSS Tracking wird deaktiviert.")
                    item['price_selector'] = "LIST"
                elif res.get('current_price_chf'):
                    price = float(res['current_price_chf'])
                    menge = item.get('menge')
                    if not isinstance(menge, (int, float)) or menge <= 0:
                        history = item.get('history', [])
                        menge = history[-1].get('menge', 1) if history else 1
                        item['menge'] = menge
                        
                    new_pps = round(price / menge, 3)
                    if new_pps < 0.10:
                        print(f"  -> [KI-FALLBACK] Warnung: Preis {new_pps} CHF/Schuss zu tief (Preis={price}, Menge={menge}). Verwerfe Update.")
                    else:
                        css_selector = res.get('css_selector')
                        if css_selector:
                            print(f"  -> [KI-FALLBACK] Neuer Selector gefunden: {css_selector} | Preis: {price} CHF")
                            item['price_selector'] = css_selector
                        else:
                            print(f"  -> [KI-FALLBACK] Kein CSS-Selector für Variante möglich. KI-Preis verwendet: {price} CHF")
                            item['price_selector'] = None
                            
                        item['aktueller_preis_pro_schuss'] = new_pps
                        history_entry = {
                            "date": current_time,
                            "preis_total_chf": price,
                            "menge": item.get('menge'),
                            "preis_pro_schuss": item['aktueller_preis_pro_schuss']
                        }
                        item['history'].append(history_entry)
                        item['history'] = item['history'][-30:]
                        item['letztes_update'] = current_time
                        updated_count += 1
                else:
                    print("  -> KI konnte Preis nicht finden oder Selector ist null.")
            time.sleep(2) # API Rate Limiting

    BLACKLIST_FILE = os.path.join(DATA_DIR, "blacklist_ids.json")
    if os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, 'r') as f:
            current_blacklist = json.load(f)
        data = [item for item in data if item['id'] not in current_blacklist]

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n[{datetime.now().isoformat()}] Tracking beendet. {updated_count} Preise aktualisiert.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ammo Tracker Scraper")
    parser.add_argument("--mode", choices=["discover", "track"], default="track", 
                        help="discover: sucht nach neuen Produkten. track: updated bekannte Produkte via CSS.")
    args = parser.parse_args()
    
    if args.mode == "discover":
        run_discovery()
    else:
        run_tracking()

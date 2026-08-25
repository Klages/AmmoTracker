import os
import json
import threading
import time
import re
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import schedule
from scraper import run_discovery, run_tracking
from scout import run_scout
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
DATA_DIR = "/app/data"
URLS_FILE = os.path.join(DATA_DIR, "urls.json")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

class UrlRequest(BaseModel):
    url: str
    password: str

def discovery_job():
    run_discovery()

def tracking_job():
    run_tracking()
    
def scout_job():
    run_scout()

def run_schedule():
    # Scout runs every 14 days to find new shops
    schedule.every(14).days.do(scout_job)
    
    # Discovery every Monday at 02:00
    schedule.every().monday.at("02:00").do(discovery_job)
    
    # Tracking every day at 04:00
    schedule.every().day.at("04:00").do(tracking_job)
    
    # Run once at startup
    tracking_job()
    
    while True:
        schedule.run_pending()
        time.sleep(60)

# Start background thread for scheduler
@app.on_event("startup")
def startup_event():
    thread = threading.Thread(target=run_schedule, daemon=True)
    thread.start()

@app.get("/urls")
def get_urls():
    if not os.path.exists(URLS_FILE):
        return []
    with open(URLS_FILE, 'r') as f:
        return json.load(f)

@app.post("/urls")
def add_url(req: UrlRequest):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    url = req.url.strip()
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")
        
    urls = []
    if os.path.exists(URLS_FILE):
        with open(URLS_FILE, 'r') as f:
            urls = json.load(f)
            
    if url not in urls:
        urls.append(url)
        with open(URLS_FILE, 'w') as f:
            json.dump(urls, f, indent=2)
            
    return {"status": "success", "urls": urls}

class DeleteItemRequest(BaseModel):
    id: str
    password: str

@app.post("/delete-item")
def delete_item(req: DeleteItemRequest):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    DATA_FILE = os.path.join(DATA_DIR, "munition_daten.json")
    BLACKLIST_FILE = os.path.join(DATA_DIR, "blacklist_ids.json")
    
    # 1. Add to blacklist
    blacklist = []
    if os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, 'r') as f:
            blacklist = json.load(f)
            
    if req.id not in blacklist:
        blacklist.append(req.id)
        with open(BLACKLIST_FILE, 'w') as f:
            json.dump(blacklist, f, indent=2)
            
    # 2. Remove from active data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        new_data = [item for item in data if item['id'] != req.id]
        
        if len(new_data) < len(data):
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, indent=2, ensure_ascii=False)
                
    return {"status": "success"}

@app.post("/reset-item")
def reset_item(req: DeleteItemRequest):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    DATA_FILE = os.path.join(DATA_DIR, "munition_daten.json")
    if not os.path.exists(DATA_FILE):
        raise HTTPException(status_code=404, detail="No data file found")
        
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    for item in data:
        if item['id'] == req.id:
            if 'price_selector' in item:
                del item['price_selector']
            
            if 'history' in item and len(item['history']) > 1:
                item['history'].pop()
                last = item['history'][-1]
                item['aktueller_preis_pro_schuss'] = last.get('preis_pro_schuss', item.get('aktueller_preis_pro_schuss'))
            
            # Force immediate update
            item['letztes_update'] = "2020-01-01T00:00:00" 
            break
            
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    return {"status": "success"}

@app.post("/auto-repair")
def auto_repair(req: UrlRequest):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    DATA_FILE = os.path.join(DATA_DIR, "munition_daten.json")
    if not os.path.exists(DATA_FILE):
        raise HTTPException(status_code=404, detail="No data file found")
        
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    count = 0
    for item in data:
        history = item.get('history', [])
        if len(history) >= 3:
            prices = sorted([h['preis_pro_schuss'] for h in history])
            median = prices[len(prices)//2]
            
            new_history = []
            fixed = False
            removed_latest = False
            for i, h in enumerate(history):
                # If deviates by > 20% from median, it's an outlier
                if median > 0 and abs(h['preis_pro_schuss'] - median) / median > 0.20:
                    fixed = True
                    if i == len(history) - 1:
                        removed_latest = True
                else:
                    new_history.append(h)
                    
            if fixed and len(new_history) > 0:
                item['history'] = new_history
                last = new_history[-1]
                item['aktueller_preis_pro_schuss'] = last.get('preis_pro_schuss', item.get('aktueller_preis_pro_schuss'))
                
                # If we removed the latest price, we should force a re-track and clear selector
                if removed_latest:
                    item['letztes_update'] = "2020-01-01T00:00:00" 
                    if 'price_selector' in item:
                        del item['price_selector']
                        
                count += 1
                
    if count > 0:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
    return {"status": "success", "fixed_count": count}

@app.post("/clear-history")
def clear_history(req: DeleteItemRequest):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    DATA_FILE = os.path.join(DATA_DIR, "munition_daten.json")
    if not os.path.exists(DATA_FILE):
        raise HTTPException(status_code=404, detail="No data file found")
        
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    for item in data:
        if item['id'] == req.id:
            if 'history' in item and len(item['history']) > 0:
                last = item['history'][-1]
                item['history'] = [last]
            break
            
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    return {"status": "success"}

@app.post("/nuke-db")
def nuke_db(req: UrlRequest):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    DATA_FILE = os.path.join(DATA_DIR, "munition_daten.json")
    if os.path.exists(DATA_FILE):
        os.remove(DATA_FILE)
        
    # Also trigger a background re-discovery so the user doesn't have to wait a day
    def trigger_discovery():
        import subprocess
        subprocess.Popen(["python", "scraper.py", "--mode", "discover"])
        
    threading.Thread(target=trigger_discovery).start()
        
    return {"status": "success", "message": "Database deleted and discovery started"}

@app.post("/cleanup-duplicates")
def cleanup_duplicates(req: UrlRequest):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    DATA_FILE = os.path.join(DATA_DIR, "munition_daten.json")
    if not os.path.exists(DATA_FILE):
        return {"status": "success", "message": "No data file found.", "merged": 0}
        
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    def generate_id(kaliber, marke, shop, menge):
        s = f"{kaliber}-{marke}-{menge}-{shop}".lower()
        s = re.sub(r'[^a-z0-9]', '-', s)
        s = re.sub(r'-+', '-', s)
        return s.strip('-')

    new_data = {}
    merged_count = 0
    
    for item in data:
        parsed_domain = urlparse(item.get('url', '')).netloc.replace("www.", "")
        if parsed_domain:
            item['shop'] = parsed_domain
            
        kaliber = item.get('kaliber', 'unknown')
        marke = item.get('marke', 'unknown')
        shop = item.get('shop', 'unknown')
        menge = item.get('menge', 1)
            
        new_id = generate_id(str(kaliber), str(marke), str(shop), str(menge))
        item['id'] = new_id
        
        if new_id in new_data:
            # Merge history safely
            hist1 = new_data[new_id].get('history', [])
            hist2 = item.get('history', [])
            new_data[new_id]['history'] = hist1 + hist2
            # Sort by date safely
            new_data[new_id]['history'].sort(key=lambda x: x.get('date', ''))
            # Take latest price
            if item.get('letztes_update', '') > new_data[new_id].get('letztes_update', ''):
                new_data[new_id]['aktueller_preis_pro_schuss'] = item.get('aktueller_preis_pro_schuss', 0)
                new_data[new_id]['letztes_update'] = item.get('letztes_update', '')
            merged_count += 1
        else:
            new_data[new_id] = item
            
    final_list = list(new_data.values())
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_list, f, indent=2, ensure_ascii=False)
        
    return {"status": "success", "merged": merged_count}

@app.post("/verify-admin")
def verify_admin(req: UrlRequest):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"status": "success"}

@app.post("/scrape")
def trigger_scrape(req: UrlRequest):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Run discovery in background when triggered manually
    thread = threading.Thread(target=run_discovery, daemon=True)
    thread.start()
    return {"status": "Discovery triggered in background"}

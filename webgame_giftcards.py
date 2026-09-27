import json, logging, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

BASE_https://web-game.net/categoria/gift-card/ = "https://web-game.net/categoria/gift-card/"
GiftCardsEGORY = "GiftCards"
data/quarantine/webgame_giftcards = Path("data/quarantine/webgame_giftcards")
data/quarantine/webgame_giftcards.mkdir(parents=True, exist_ok=True)
webgame_giftcards.json_data/quarantine/webgame_giftcards = data/quarantine/webgame_giftcards / "webgame_giftcards.json"
webgame_giftcards.log_data/quarantine/webgame_giftcards = data/quarantine/webgame_giftcards / "webgame_giftcards.log"

logging.basicConfig(filename=webgame_giftcards.log_data/quarantine/webgame_giftcards, level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s")
logging.getLogger().addHandler(logging.StreamHandler())

def log(x): logging.info(x)

def parse_price(text):
    m = re.search(r"\$\s*([\d\.\,]+)", text or "")
    if not m: return None
    try: return float(m.group(1).replace(".", "").replace(",", "."))
    except ValueError: return None

def parse_products(html):
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("ul.products li.product")
    log(f"Productos encontrados en HTML: {len(items)}")
    out = []
    for item in items:
        title = item.select_one("h2")
        link = item.select_one("a[href]")
        if not title or not link: continue
        price = item.select_one("span.price")
        img = item.select_one("img")
        image = None
        if img:
            image = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            if image: image = urljoin(BASE_https://web-game.net/categoria/gift-card/, image)
        out.append({
            "title": title.get_text(" ", strip=True),
            "url": urljoin(BASE_https://web-game.net/categoria/gift-card/, link.get("href")),
            "price": parse_price(price.get_text(" ", strip=True) if price else ""),
            "price_text": price.get_text(" ", strip=True) if price else "",
            "image": image,
            "source": "Web Game",
            "category": GiftCardsEGORY
        })
    return out

def next_page(html):
    soup = BeautifulSoup(html, "html.parser")
    e = soup.select_one('link[rel="next"]')
    if e and e.get("href"): return urljoin(BASE_https://web-game.net/categoria/gift-card/, e["href"])
    for s in ('a[rel="next"]', "a.next.page-numbers", "a.next"):
        e = soup.select_one(s)
        if e and e.get("href"): return urljoin(BASE_https://web-game.net/categoria/gift-card/, e["href"])
    return None

def valid(url):
    p = urlparse(url)
    base = urlparse(BASE_https://web-game.net/categoria/gift-card/)
    return p.netloc == "web-game.net" and p.path.startswith(base.path.rstrip("/"))

def fetch(url):
    try:
        from curl_cffi import requests
        log("Intentando con curl_cffi / Chrome...")
        s = requests.Session(impersonate="chrome")
        r = s.get(url, headers={
            "accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "accept-language":"es-UY,es;q=0.9,en;q=0.8",
            "referer":"https://web-game.net/",
            "upgrade-insecure-requests":"1"
        }, timeout=30)
        log(f"curl_cffi HTTP {r.status_code} | {len(r.text)} bytes")
        if r.status_code == 200: return r.text
    except Exception as e: log(f"curl_cffi: {e}")

    time.sleep(2)
    try:
        import requests
        log("Intentando con requests...")
        r = requests.get(url, headers={
            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language":"es-UY,es;q=0.9,en;q=0.8",
            "Referer":"https://web-game.net/",
            "Upgrade-Insecure-Requests":"1"
        }, timeout=30)
        log(f"requests HTTP {r.status_code} | {len(r.text)} bytes")
        if r.status_code == 200: return r.text
    except Exception as e: log(f"requests: {e}")

    time.sleep(2)
    try:
        from playwright.sync_api import sync_playwright
        log("Intentando con Playwright / Chromium...")
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled","--no-sandbox","--disable-dev-shm-usage"])
            c = b.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36", locale="es-UY", viewport={"width":1366,"height":768})
            page = c.new_page()
            r = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            log(f"Playwright HTTP {r.status if r else 'none'} | https://web-game.net/categoria/gift-card/ final: {page.url}")
            page.wait_for_timeout(5000)
            html = page.content()
            log(f"Playwright HTML recibido: {len(html)} bytes")
            b.close()
            if html and len(html) > 1000: return html
    except Exception as e: log(f"Playwright: {e}")
    return None

def main():
    print("=== Web Game GiftCards - QUARANTINE ===")
    current = BASE_https://web-game.net/categoria/gift-card/
    visited, products, page_no = set(), [], 1
    while current:
        if current in visited: break
        visited.add(current)
        log(f"[PAGE {page_no}] GET {current}")
        html = fetch(current)
        if not html:
            log(f"[PAGE {page_no}] No se pudo obtener HTML.")
            if page_no == 1: sys.exit(1)
            break
        found = parse_products(html)
        log(f"[PAGE {page_no}] {len(found)} productos")
        products.extend(found)
        nxt = next_page(html)
        if nxt and valid(nxt):
            log(f"[PAGE {page_no}] Siguiente página: {nxt}")
            current, page_no = nxt, page_no + 1
            time.sleep(2)
        else:
            log(f"[PAGE {page_no}] Fin de paginación.")
            break
    unique = {p["url"]: p for p in products}
    products = list(unique.values())
    result = {"source":"Web Game","category":GiftCardsEGORY,"url":BASE_https://web-game.net/categoria/gift-card/,"pages_scraped":page_no,"products_count":len(products),"products":products}
    webgame_giftcards.json_data/quarantine/webgame_giftcards.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"TOTAL PRODUCTOS: {len(products)}")
    print(f"TOTAL PRODUCTOS: {len(products)}")
    if not products: sys.exit(2)


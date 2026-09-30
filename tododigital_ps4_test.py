import csv, re, time, random
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://tododigitalshop.com"
START_URL = f"{BASE_URL}/juegos-digitales-ps4/"
OUTPUT_CSV = "tododigital_ps4_test.csv"
LOG_FILE = "tododigital_ps4_test.log.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}

def log(msg, fh):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line); fh.write(line + "\n"); fh.flush()

def parse_price(text):
    if not text: return None
    s = re.sub(r"[^\d,.\-]", "", text.replace("\xa0", " "))
    if not s: return None
    if "," in s: s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1: s = s.replace(".", "")
    try: return float(s)
    except ValueError: return None

def extract_products(html, category):
    soup = BeautifulSoup(html, "html.parser")
    products, seen = [], set()
    for card in soup.select(".product-small"):
        name_el = card.select_one(".name.product-title.woocommerce-loop-product__title a")
        if not name_el: continue
        name, href = name_el.get_text(" ", strip=True), name_el.get("href")
        if not name or not href: continue
        url = urljoin(BASE_URL, href).split("#")[0]
        if url in seen: continue
        price_el = card.select_one(".woocommerce-Price-amount")
        price = parse_price(price_el.get_text(" ", strip=True) if price_el else "")
        products.append({"source":"TodoDigital","category":category,"name":name,
                         "price":price,"currency":"EUR","url":url})
        seen.add(url)
    return products

def find_next_url(html, current_url):
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one('link[rel="next"], a.next, a.next.page-number')
    if el and el.get("href"): return urljoin(current_url, el["href"])
    return None

def scrape_category(session, category, start_url, log_fh):
    all_products, seen_urls = [], set()
    page_url, page_number = start_url, 1
    while True:
        log(f"{category} | página {page_number} | {page_url}", log_fh)
        try:
            r = session.get(page_url, headers=HEADERS, timeout=45, allow_redirects=True)
        except requests.RequestException as e:
            log(f"ERROR de conexión: {e}", log_fh)
            return all_products, False
        log(f"{category} | página {page_number} | HTTP {r.status_code} | {len(r.text)} caracteres", log_fh)
        if r.status_code in (403,404):
            if page_number == 1:
                log(f"ERROR REAL: HTTP {r.status_code} en página 1.", log_fh)
                return all_products, False
            log(f"Fin de paginación: HTTP {r.status_code} en página {page_number}.", log_fh)
            break
        if r.status_code != 200:
            log(f"ERROR HTTP {r.status_code}.", log_fh); return all_products, False
        page_products = extract_products(r.text, category)
        if not page_products:
            log(f"{category} | página {page_number} | 0 productos. Fin.", log_fh); break
        new_count = 0
        for p in page_products:
            if p["url"] not in seen_urls:
                seen_urls.add(p["url"]); all_products.append(p); new_count += 1
        log(f"{category} | página {page_number} | {len(page_products)} encontrados | {new_count} nuevos | total {len(all_products)}", log_fh)
        next_url = find_next_url(r.text, page_url)
        if not next_url or next_url == page_url:
            log("No se encontró siguiente página. Fin.", log_fh); break
        page_url, page_number = next_url, page_number + 1
        time.sleep(random.uniform(2,4))
        if page_number > 100:
            log("Límite de seguridad: 100 páginas.", log_fh); break
    return all_products, True

def save_csv(products):
    fields = ["source","category","name","price","currency","url"]
    with open(OUTPUT_CSV,"w",newline="",encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(products)

def main():
    with open(LOG_FILE,"w",encoding="utf-8") as log_fh:
        log("=== TodoDigital - PRUEBA PS4 ===", log_fh)
        session = requests.Session(); session.headers.update(HEADERS)
        products, ok = scrape_category(session,"PS4",START_URL,log_fh)
        save_csv(products)
        log("=== RESUMEN ===", log_fh)
        log(f"Productos únicos: {len(products)}", log_fh)
        log(f"Estado: {'OK' if ok else 'ERROR'}", log_fh)
        log(f"CSV: {OUTPUT_CSV}", log_fh); log(f"Log: {LOG_FILE}", log_fh)
        for p in products[:5]:
            log(f"- {p['name']} | {p['price']} EUR | {p['url']}", log_fh)

if __name__ == "__main__":
    main()

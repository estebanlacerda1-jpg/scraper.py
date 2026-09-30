import csv, re, time, random
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL="https://tododigitalshop.com"
CATEGORIES=[
 ("PS4",f"{BASE_URL}/juegos-digitales-ps4/"),
 ("PS5",f"{BASE_URL}/juegos-digitales-ps5/"),
 ("Switch",f"{BASE_URL}/juegos-digitales-nintendo-switch/"),
]
OUTPUT_CSV="tododigital.csv"
LOG_FILE="tododigital.log.txt"
HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36","Accept-Language":"es-AR,es;q=0.9,en;q=0.8"}

def log(msg,fh):
    line=f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line); fh.write(line+"\n"); fh.flush()

def parse_price(text):
    if not text:return None
    s=re.sub(r"[^\d,.\-]","",text.replace("\xa0"," "))
    if not s:return None
    if "," in s:s=s.replace(".","").replace(",",".")
    elif s.count(".")>1:s=s.replace(".","")
    try:return float(s)
    except ValueError:return None

def extract_products(html,category):
    soup=BeautifulSoup(html,"html.parser"); products=[]; seen=set()
    for card in soup.select(".product-small"):
        el=card.select_one(".name.product-title.woocommerce-loop-product__title a")
        if not el:continue
        name=el.get_text(" ",strip=True); href=el.get("href")
        if not name or not href:continue
        url=urljoin(BASE_URL,href).split("#")[0]
        if url in seen:continue
        price_el=card.select_one(".woocommerce-Price-amount")
        price=parse_price(price_el.get_text(" ",strip=True) if price_el else "")
        products.append({"source":"TodoDigital","category":category,"name":name,"price":price,"currency":"EUR","url":url})
        seen.add(url)
    return products

def find_next_url(html,current_url):
    soup=BeautifulSoup(html,"html.parser")
    el=soup.select_one('link[rel="next"]')
    if el and el.get("href"):return urljoin(current_url,el["href"])
    el=soup.select_one("a.next,a.next.page-number,.pagination a.next")
    if el and el.get("href"):return urljoin(current_url,el["href"])
    return None

def scrape_category(session,category,start_url,fh):
    all_products=[]; seen=set(); page_url=start_url; page=1
    while True:
        log(f"{category} | página {page} | {page_url}",fh)
        try:r=session.get(page_url,headers=HEADERS,timeout=45,allow_redirects=True)
        except requests.RequestException as e:
            log(f"{category} | ERROR conexión: {e}",fh); return all_products,False
        log(f"{category} | página {page} | HTTP {r.status_code} | {len(r.text)} caracteres",fh)
        if r.status_code in (403,404):
            if page==1:
                log(f"{category} | ERROR REAL: HTTP {r.status_code} en página 1.",fh); return all_products,False
            log(f"{category} | Fin de paginación: HTTP {r.status_code} en página {page}.",fh); break
        if r.status_code!=200:
            log(f"{category} | ERROR HTTP {r.status_code}.",fh)
            return all_products,False
        found=extract_products(r.text,category)
        if not found:
            log(f"{category} | página {page} | 0 productos. Fin.",fh); break
        new=0
        for x in found:
            if x["url"] not in seen:
                seen.add(x["url"]); all_products.append(x); new+=1
        log(f"{category} | página {page} | {len(found)} encontrados | {new} nuevos | total {len(all_products)}",fh)
        nxt=find_next_url(r.text,page_url)
        if not nxt or nxt==page_url:
            log(f"{category} | No se encontró siguiente página. Fin.",fh); break
        page_url=nxt; page+=1; time.sleep(random.uniform(2,4))
        if page>100:
            log(f"{category} | Límite de seguridad: 100 páginas.",fh); break
    return all_products,True

def save_csv(products):
    fields=["source","category","name","price","currency","url"]
    with open(OUTPUT_CSV,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(products)

def main():
    all_products=[]; summary=[]
    with open(LOG_FILE,"w",encoding="utf-8") as fh:
        log("=== ABC Gaming - TodoDigital PS4 + PS5 + Switch ===",fh)
        session=requests.Session(); session.headers.update(HEADERS)
        for i,(category,url) in enumerate(CATEGORIES):
            if i: time.sleep(random.uniform(3,6))
            products,ok=scrape_category(session,category,url,fh)
            all_products.extend(products)
            summary.append((category,len(products),"OK" if ok else "ERROR"))
        save_csv(all_products)
        log("=== RESUMEN ===",fh)
        for c,n,s in summary:log(f"{c}: {n} productos | {s}",fh)
        log(f"TOTAL: {len(all_products)} productos",fh)
        log(f"CSV: {OUTPUT_CSV}",fh)

if __name__=="__main__":main()

import csv, logging, re, time
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE='https://uruguayjuegosdigitales.com'
SOURCE='UruguayDigital'; CURRENCY='UYU'
TIMEOUT=45; RETRIES=3; DELAY=1.0
HEADERS={'User-Agent':'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36','Accept-Language':'es-UY,es;q=0.9,en;q=0.8'}

CATEGORIES=[
('PS3','/product-category/juegos-digitales-ps3/'),
('PS4','/product-category/juegos-digitales-ps4/'),
('PS4 VR','/product-category/juegos-digitales-ps4/vr/'),
('PS5','/product-category/juegos-digitales-ps5/'),
('PC','/product-category/juegos-digitales-pc/todos-los-juegos-pc/'),
('Xbox Series X/S','/product-category/juegos-digitales-xbox/juegos-digitales-xbox-series-x-s/'),
('Xbox One','/product-category/juegos-digitales-xbox/juegos-digitales-xbox-one/'),
('Nintendo Switch 1','/product-category/juegos-nintendo/juegos-nintendo-switch/'),
('Nintendo Switch 2','/product-category/juegos-nintendo/nintendo-switch-2/'),
('Nintendo Membresía','/product-category/juegos-nintendo/nintendo-membresia/'),
('Eneba Gift Card','/product-category/gift-cards/eneba-gift-card/'),
('Xbox Game Pass','/product-category/gift-cards/xbox-membresia/'),
('Xbox Gift Cards','/product-category/gift-cards/xbox-gift-cards/'),
('PlayStation Plus','/product-category/gift-cards/psn-plus-usa/'),
('PSN Card USA y España','/product-category/gift-cards/psn-card-usa/'),
('Nintendo eShop USA','/product-category/gift-cards/nintendo-eshop-usa/'),
('Steam','/product-category/gift-cards/gift-card-steam/'),
('EA Play','/product-category/gift-cards/ea-play/'),
('Amazon','/product-category/gift-cards/amazon/'),
('Razer Gold','/product-category/gift-cards/razer/'),
('iTunes','/product-category/gift-cards/itunes/'),
('Valorant Points','/product-category/gift-cards/valorant-points/'),
('Diamantes Free Fire','/product-category/gift-cards/diamantes-free-fire/'),
('Pavos Fortnite','/product-category/gift-cards/pavos/'),
('Roblox Robux','/product-category/gift-cards/roblox-robux/'),
('Saldo Blizzard','/product-category/gift-cards/blizzard/'),
('Overwatch 2 Coins','/product-category/gift-cards/overwatch-2-coins-global/'),
]

logging.basicConfig(level=logging.INFO,format='%(asctime)s | %(levelname)s | %(message)s',handlers=[logging.FileHandler('uruguaydigital.log.txt',encoding='utf-8'),logging.StreamHandler()])
log=logging.getLogger('uruguaydigital')

def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def absurl(u): return urljoin(BASE,u or '').split('#',1)[0]

def price(s):
    s=re.sub(r'[^0-9,.\-]','',clean(s))
    if ',' in s and '.' in s: s=s.replace('.','').replace(',','.')
    elif ',' in s: s=s.replace(',','.')
    try: return f'{float(s):.2f}'
    except: return ''

def fetch(session,url):
    last=None
    for n in range(1,RETRIES+1):
        try:
            r=session.get(url,timeout=TIMEOUT,allow_redirects=True)
            if r.status_code==200 or r.status_code in (403,404): return r
            last=RuntimeError(f'HTTP {r.status_code}')
        except requests.RequestException as e: last=e
        log.warning('Intento %s/%s: %s | %s',n,RETRIES,last,url)
        if n<RETRIES: time.sleep(2*n)
    raise last

def parse(html,cat):
    soup=BeautifulSoup(html,'html.parser'); out=[]
    for card in soup.select('.product-small'):
        a=card.select_one('.woocommerce-loop-product__title a, .name.product-title.woocommerce-loop-product__title a, h2.woocommerce-loop-product__title a, h3.woocommerce-loop-product__title a')
        if a: name=clean(a.get_text(' ',strip=True)); url=absurl(a.get('href'))
        else:
            t=card.select_one('.woocommerce-loop-product__title, .name.product-title.woocommerce-loop-product__title'); a=card.select_one('a[href]')
            name=clean(t.get_text(' ',strip=True)) if t else ''; url=absurl(a.get('href')) if a else ''
        p=card.select_one('.woocommerce-Price-amount, .price .amount, .price')
        if name and url: out.append({'source':SOURCE,'category':cat,'name':name,'price':price(p.get_text(' ',strip=True) if p else ''),'currency':CURRENCY,'url':url})
    return out

def next_url(soup):
    a=soup.select_one('link[rel="next"], a.next.page-numbers[href], a.next[href]')
    return absurl(a.get('href')) if a and a.get('href') else ''

def scrape(session,cat,path):
    url=absurl(path); seen_pages=set(); seen_products=set(); allp=[]; page=1
    while url and url not in seen_pages:
        seen_pages.add(url); log.info('[%s] página %s | %s',cat,page,url)
        try: r=fetch(session,url)
        except Exception as e: log.error('[%s] ERROR: %s',cat,e); return [],False
        if r.status_code in (403,404):
            if page==1: log.error('[%s] página 1 HTTP %s',cat,r.status_code); return [],False
            log.info('[%s] HTTP %s en página posterior: fin',cat,r.status_code); break
        soup=BeautifulSoup(r.text,'html.parser'); items=parse(r.text,cat)
        if page==1:
            txt=clean(soup.get_text(' ',strip=True)); m=re.search(r'(?:Mostrando|Showing)\s+\d+\s*[–-]\s*\d+\s+(?:de|of)\s+([\d.]+)',txt,re.I)
            if m: log.info('[%s] contador del sitio: %s',cat,m.group(1))
        if not items:
            if page==1: log.error('[%s] página 1 sin productos',cat); return [],False
            break
        new=0
        for x in items:
            if x['url'] not in seen_products: seen_products.add(x['url']); allp.append(x); new+=1
        log.info('[%s] página %s: %s encontrados | %s nuevos',cat,page,len(items),new)
        url=next_url(soup); page+=1; time.sleep(DELAY)
    log.info('[%s] FINAL: %s productos únicos',cat,len(allp)); return allp,True

def main():
    log.info('='*70); log.info('URUGUAYDIGITAL DEFINITIVO | %s categorías',len(CATEGORIES)); log.info('='*70)
    s=requests.Session(); s.headers.update(HEADERS); products=[]; global_urls=set(); ok=bad=0
    for i,(cat,path) in enumerate(CATEGORIES,1):
        log.info('### %s/%s: %s',i,len(CATEGORIES),cat); items,success=scrape(s,cat,path)
        ok+=success; bad+=not success
        for x in items:
            if x['url'] not in global_urls: global_urls.add(x['url']); products.append(x)
        time.sleep(DELAY)
    with open('uruguaydigital.csv','w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['source','category','name','price','currency','url']); w.writeheader(); w.writerows(products)
    log.info('='*70); log.info('RESUMEN | categorías=%s | OK=%s | error=%s | productos únicos=%s',len(CATEGORIES),ok,bad,len(products)); log.info('='*70)
    return 0

if __name__=='__main__': raise SystemExit(main())

import csv,re,time
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
BASE='https://uruguayjuegosdigitales.com'; START=f'{BASE}/product-category/juegos-digitales-ps4/'
SOURCE='UruguayDigital'; CATEGORY='PS4'; CURRENCY='UYU'; CSV_OUT='uruguaydigital_ps4_test.csv'; LOG='uruguaydigital_ps4_test.log.txt'
DELAY=2.0; TIMEOUT=45; RETRIES=3
HEADERS={'User-Agent':'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36','Accept-Language':'es-UY,es;q=0.9,en;q=0.8'}
def log(s,f): print(s,flush=True); f.write(s+'\n'); f.flush()
def price(t):
    if not t:return ''
    x=re.sub(r'[^\d,.\-]','', ' '.join(t.split()))
    if not x:return ''
    if ',' in x and '.' in x:x=x.replace('.','').replace(',','.')
    elif ',' in x:x=x.replace(',','.')
    elif x.count('.')>1:x=x.replace('.','')
    elif '.' in x:
        a,b=x.rsplit('.',1)
        if len(b)==3 and a.replace('-','').isdigit():x=a+b
    try:return f'{float(x):.2f}'
    except:return ''
def get(s,u,n,f):
    for a in range(1,RETRIES+1):
        try:
            r=s.get(u,headers=HEADERS,timeout=TIMEOUT,allow_redirects=True); log(f'[Página {n}] HTTP {r.status_code} | {r.url} | intento {a}',f)
            if r.status_code in (403,404):return r
            r.raise_for_status(); return r
        except requests.RequestException as e:
            log(f'[Página {n}] Error intento {a}/{RETRIES}: {e}',f)
            if a<RETRIES:time.sleep(5)
    return None
def extract(html,page):
    soup=BeautifulSoup(html,'html.parser'); out=[]
    for card in soup.select('.product-small'):
        ne=card.select_one('.woocommerce-loop-product__title a') or card.select_one('.woocommerce-loop-product__title')
        pe=card.select_one('.woocommerce-Price-amount')
        if not ne:continue
        link=ne.get('href','').strip() if ne.name=='a' else (card.select_one('a[href]') or {}).get('href','') if card.select_one('a[href]') else ''
        name=ne.get_text(' ',strip=True); pt=pe.get_text(' ',strip=True) if pe else ''
        if name and link:out.append({'source':SOURCE,'category':CATEGORY,'name':name,'price':price(pt),'currency':CURRENCY,'url':urljoin(page,link)})
    return out,soup
def main():
    s=requests.Session(); rows=[]; seen=set(); pages=set(); u=START; n=1
    with open(LOG,'w',encoding='utf-8') as f:
        log('='*70,f); log('ABC Gaming - UruguayDigital PS4 TEST',f); log(f'URL inicial: {START}',f); log(f'Categoría: {CATEGORY}',f); log(f'Moneda: {CURRENCY}',f); log('='*70,f)
        while u:
            if u in pages:log(f'[Página {n}] URL repetida. Fin.',f);break
            pages.add(u); r=get(s,u,n,f)
            if r is None:log(f'[Página {n}] ERROR: no se pudo obtener.',f);break
            if r.status_code in (403,404):
                if n==1:log(f'[Página 1] ERROR CRÍTICO: HTTP {r.status_code}.',f);return 1
                log(f'[Página {n}] HTTP {r.status_code} posterior: fin de paginación.',f);break
            products,soup=extract(r.text,r.url); new=0
            for p in products:
                if p['url'] not in seen:seen.add(p['url']);rows.append(p);new+=1
            nxt=soup.select_one('link[rel="next"]') or soup.select_one('a.next[href]')
            nxt=urljoin(r.url,nxt.get('href')) if nxt and nxt.get('href') else None
            log(f'[Página {n}] Productos: {len(products)} | Nuevos: {new} | Total: {len(rows)}',f)
            if not nxt:log(f'[Página {n}] No hay rel="next". Fin.',f);break
            u=nxt;n+=1;time.sleep(DELAY)
        with open(CSV_OUT,'w',newline='',encoding='utf-8-sig') as cf:
            w=csv.DictWriter(cf,fieldnames=['source','category','name','price','currency','url']);w.writeheader();w.writerows(rows)
        log('='*70,f);log('RESUMEN FINAL',f);log(f'Páginas procesadas: {len(pages)}',f);log(f'Productos únicos: {len(rows)}',f);log(f'CSV: {CSV_OUT}',f);log('='*70,f)
    return 0
if __name__=='__main__':raise SystemExit(main())

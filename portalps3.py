import csv,re
from collections import deque
from urllib.parse import urljoin,urlparse,urlunparse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright,TimeoutError as PWTimeout

BASE='https://portalgames.com.ar'
ROOTS={'PS3':BASE+'/product-category/juegos-ps3/','PS4':BASE+'/product-category/juegos-ps4/','PS5':BASE+'/product-category/juegos-ps5/','Switch':BASE+'/product-category/nintendo-switch/'}
CSV='portalgames.csv'; LOG='portalgames.log.txt'
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'

def clean(x): return re.sub(r'\s+',' ',x or '').strip()
def norm(u):
    if not u:return ''
    u=urljoin(BASE,u); p=urlparse(u)
    if p.netloc and p.netloc!=urlparse(BASE).netloc:return ''
    p=p._replace(fragment=''); path=p.path or '/'
    if path!='/' and not path.endswith('/'):path+='/'
    return urlunparse(p)
def catbase(u):
    p=urlparse(norm(u)); return urlunparse(p._replace(path=re.sub(r'/page/\d+/?$','/',p.path)))
def price(s):
    m=re.search(r'\$?\s*([0-9][0-9\.\,]*)',clean(s))
    if not m:return ''
    x=m.group(1)
    if ',' in x:x=x.split(',')[0].replace('.','')
    elif x.count('.')==1 and len(x.split('.')[1])==3:x=x.replace('.','')
    try:return int(x.replace('.',''))
    except:return ''
def pop(page):
    for sel in ['button:has-text("Aceptar")','button:has-text("Cerrar")','.mfp-close','.pys-close','[aria-label="Close"]','[aria-label="Cerrar"]']:
        try:
            loc=page.locator(sel)
            for i in range(min(loc.count(),5)):
                try:
                    if loc.nth(i).is_visible(timeout=400):loc.nth(i).click(timeout=800)
                except:pass
        except:pass
def load(page,url,log):
    try:
        r=page.goto(norm(url),wait_until='domcontentloaded',timeout=90000); st=r.status if r else 0
        log.append(f'GET {norm(url)} -> HTTP {st}'); page.wait_for_timeout(5000); pop(page)
        for _ in range(5):
            try:page.mouse.wheel(0,5000);page.wait_for_timeout(1000)
            except:break
        pop(page); html=page.content()
        if any(x in html.lower() for x in ['just a moment','cf-chl-','challenge-platform','cf-mitigated']):log.append('AVISO: marcador Cloudflare presente; se continua porque puede haber HTML valido.')
        return html,st
    except PWTimeout:
        log.append(f'TIMEOUT {norm(url)}')
        try:return page.content(),0
        except:return '',0
    except Exception as e:log.append(f'ERROR {norm(url)}: {e}');return '',0

def products(html,block,cat,pn,log):
    s=BeautifulSoup(html,'html.parser'); out=[]; seen=set()
    for card in s.select('.product-small'):
        a=card.select_one('.name.product-title.woocommerce-loop-product__title a') or card.select_one('.woocommerce-loop-product__title a')
        if not a:continue
        name=clean(a.get_text(' ',strip=True)); u=norm(a.get('href'))
        if not name or not u or '/product/' not in urlparse(u).path or u in seen:continue
        seen.add(u); pr=card.select_one('.woocommerce-Price-amount'); cn=card.select_one('.product-cat')
        shown=clean(pr.get_text(' ',strip=True)) if pr else ''
        out.append({'fuente':'PortalGames','nombre':name,'categoria':clean(cn.get_text(' ',strip=True)) if cn else '','bloque':block,'precio':price(shown),'precio_mostrado':shown,'moneda':'ARS','url':u,'categoria_url':norm(cat),'pagina':pn})
    log.append(f'{block} | {norm(cat)} | pagina {pn} | productos {len(out)}');return out

def subcats(html,root):
    s=BeautifulSoup(html,'html.parser'); rp=urlparse(norm(root)).path.rstrip('/')+'/';out=set()
    for a in s.select('a[href]'):
        u=norm(a.get('href')); path=urlparse(u).path
        if not u or not path.startswith(rp):continue
        rel=path[len(rp):].strip('/'); parts=rel.split('/') if rel else []
        if not parts or 'page' in parts or 'feed' in parts:continue
        out.add(u)
    return sorted(out)

def pages(html,current):
    s=BeautifulSoup(html,'html.parser'); base=urlparse(catbase(current)).path.rstrip('/')+'/';out=set()
    for a in s.select('a[rel="next"],a.page-number,.page-numbers a[href],nav.woocommerce-pagination a[href]'):
        u=norm(a.get('href')); path=urlparse(u).path
        if u and path.startswith(base+'page/'):out.add(u)
        if u and 'paged=' in u and u!=norm(current):out.add(u)
    return sorted(out)

def discover(page,log):
    html,_=load(page,BASE+'/',log); roots={}
    labels={'PS3':'juegos ps3','PS4':'juegos ps4','PS5':'juegos ps5','Switch':'nintendo switch'}
    if html:
        for a in BeautifulSoup(html,'html.parser').select('a[href]'):
            t=clean(a.get_text(' ',strip=True)).lower();u=norm(a.get('href'))
            if not u or '/product-category/' not in urlparse(u).path:continue
            for b,l in labels.items():
                if b not in roots and l in t:roots[b]=u
    for b,u in ROOTS.items():roots.setdefault(b,u);log.append(f'RAIZ {b}: {roots[b]}')
    return roots

def block(page,b,root,log):
    cq=deque([norm(root)]); seen_cat=set(); allp={}
    while cq:
        cat=cq.popleft()
        if not cat or cat in seen_cat:continue
        seen_cat.add(cat);pq=deque([cat]);seen_page=set()
        while pq:
            u=pq.popleft()
            if not u or u in seen_page:continue
            seen_page.add(u);html,st=load(page,u,log)
            if not html:continue
            m=re.search(r'/page/(\d+)/?$',urlparse(u).path);pn=int(m.group(1)) if m else 1
            for p in products(html,b,cat,pn,log):allp[p['url']]=p
            for sc in subcats(html,root):
                if sc not in seen_cat:cq.append(sc)
            for nx in pages(html,u):
                if nx not in seen_page:pq.append(nx)
            if st in (403,404) and pn>1:log.append(f'HTTP {st} pagina {pn}: fin de paginacion')
    log.append(f'FIN {b}: {len(seen_cat)} categorias, {len(allp)} productos unicos');return allp,len(seen_cat)

def main():
    log=['PortalGames - scraper general PS3 / PS4 / PS5 / Switch','Playwright Chromium + BeautifulSoup','Deduplicacion global por URL','']
    allp={}; counts={}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--disable-blink-features=AutomationControlled'])
        ctx=browser.new_context(viewport={'width':1400,'height':900},user_agent=UA,locale='es-419',timezone_id='America/Montevideo',java_script_enabled=True)
        page=ctx.new_page();roots=discover(page,log)
        for b in ['PS3','PS4','PS5','Switch']:
            try:
                ps,n=block(page,b,roots[b],log);counts[b]=n;allp.update(ps)
            except Exception as e:log.append(f'ERROR BLOQUE {b}: {e}')
        browser.close()
    final=sorted(allp.values(),key=lambda x:(x['bloque'],x['categoria'],x['nombre'].lower()))
    with open(CSV,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['fuente','nombre','categoria','bloque','precio','precio_mostrado','moneda','url','categoria_url','pagina']);w.writeheader();w.writerows(final)
    log+=['','========================================',f'TOTAL PRODUCTOS UNICOS: {len(final)}','CATEGORIAS VISITADAS:']+[f'{b}: {n}' for b,n in counts.items()]+['========================================']
    open(LOG,'w',encoding='utf-8').write('\n'.join(log)+'\n');print('\n'.join(log));print(f'CSV generado: {CSV}');print(f'Log generado: {LOG}')

if __name__=='__main__':main()

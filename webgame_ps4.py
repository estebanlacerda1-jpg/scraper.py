#!/usr/bin/env python3
import json, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://web-game.net/categoria/juegos-ps4/"
OUT = Path("data/quarantine/webgame_ps4")
JSON_OUT = OUT / "webgame_ps4.json"
LOG_OUT = OUT / "webgame_ps4.log"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-UY,es;q=0.9,en;q=0.7",
    "Referer": "https://web-game.net/",
}

def log(msg):
    print(msg, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with LOG_OUT.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()

def price_uyu(s):
    m = re.search(r"\$\s*([\d\.\,]+)", clean(s))
    if not m:
        return None
    try:
        return int(m.group(1).replace(".", "").replace(",", ""))
    except ValueError:
        return None

def fetch(session, url):
    r = session.get(url, timeout=30, allow_redirects=True)
    if r.status_code == 404:
        return 404, ""
    r.raise_for_status()
    return r.status_code, r.text

def parse_products(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    result = []

    for item in soup.select("ul.products li.product"):
        title = item.select_one("h2")
        link = item.select_one("a[href]")
        price = item.select_one("span.price")
        image = item.select_one("img")

        if not title or not link:
            continue

        name = clean(title.get_text(" ", strip=True))
        url = urljoin(page_url, link.get("href", "").strip())
        if not name or not url:
            continue

        raw_price = clean(price.get_text(" ", strip=True)) if price else ""
        image_url = ""
        if image:
            image_url = (image.get("src") or image.get("data-src")
                         or image.get("data-lazy-src") or "")
            image_url = urljoin(page_url, image_url)

        result.append({
            "supplier": "Web Game",
            "platform": "PS4",
            "category": "juegos-ps4",
            "name": name,
            "url": url,
            "price_uyu": price_uyu(raw_price),
            "price_raw": raw_price,
            "image": image_url,
            "source_page": page_url,
        })
    return result

def next_url(html, current):
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one('link[rel="next"][href]')
    if node:
        return urljoin(current, node["href"])
    node = soup.select_one('a.next.page-numbers[href], a.next[href], a[rel="next"][href]')
    return urljoin(current, node["href"]) if node else None

def same_catalog(url):
    p = urlparse(url)
    return p.netloc == "web-game.net" and "/categoria/juegos-ps4" in p.path

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    LOG_OUT.write_text("", encoding="utf-8")

    session = requests.Session()
    session.headers.update(HEADERS)

    products, visited = [], set()
    current = BASE_URL
    page = 1

    log("=== Web Game PS4 - QUARANTINE ===")

    while current and current not in visited:
        visited.add(current)
        log(f"[PAGE {page}] GET {current}")

        try:
            status, html = fetch(session, current)
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status == 404 and products:
                log(f"[PAGE {page}] 404 -> fin de paginación")
                break
            log(f"[PAGE {page}] HTTP ERROR {status}: {e}")
            return 1
        except requests.RequestException as e:
            log(f"[PAGE {page}] NETWORK ERROR: {e}")
            return 1

        if status == 404:
            if products:
                log(f"[PAGE {page}] 404 -> fin de paginación")
                break
            log("[PAGE 1] 404 -> fuente no disponible")
            return 1

        found = parse_products(html, current)
        log(f"[PAGE {page}] productos: {len(found)}")
        products.extend(found)

        nxt = next_url(html, current)
        if nxt and same_catalog(nxt):
            log(f"[PAGE {page}] next -> {nxt}")
            current = nxt
            page += 1
            time.sleep(1)
        else:
            log(f"[PAGE {page}] sin next -> fin")
            break

    unique = {p["url"]: p for p in products}
    products = list(unique.values())

    data = {
        "source": "webgame_ps4_quarantine",
        "supplier": "Web Game",
        "platform": "PS4",
        "category": "juegos-ps4",
        "source_url": BASE_URL,
        "pages_scanned": page,
        "products_count": len(products),
        "products": products,
    }

    JSON_OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"TOTAL productos únicos: {len(products)}")
    log(f"JSON: {JSON_OUT}")

    return 0 if products else 2

if __name__ == "__main__":
    sys.exit(main())

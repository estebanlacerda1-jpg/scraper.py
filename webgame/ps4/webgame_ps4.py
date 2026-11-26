import json
import logging
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


BASE_URL = "https://web-game.net/categoria/juegos-ps4/"

OUTPUT_DIR = Path("data/quarantine/webgame_ps4")
OUTPUT_JSON = OUTPUT_DIR / "webgame_ps4.json"
OUTPUT_LOG = OUTPUT_DIR / "webgame_ps4.log"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=OUTPUT_LOG,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger().addHandler(console)


def log(message):
    logging.info(message)


def parse_price(text):
    if not text:
        return None

    # Ejemplo:
    # Desde: $ 1.490 UYU
    match = re.search(r"\$\s*([\d\.\,]+)", text)

    if not match:
        return None

    value = match.group(1).replace(".", "").replace(",", ".")

    try:
        return float(value)
    except ValueError:
        return None


def parse_products(html):
    soup = BeautifulSoup(html, "html.parser")

    products = []

    # WooCommerce de Web Game
    items = soup.select("ul.products li.product")

    log(f"Productos encontrados en HTML: {len(items)}")

    for item in items:
        title_el = item.select_one("h2")

        if not title_el:
            continue

        title = title_el.get_text(" ", strip=True)

        link_el = item.select_one("a[href]")

        if not link_el:
            continue

        product_url = urljoin(BASE_URL, link_el.get("href"))

        price_el = item.select_one("span.price")
        price_text = (
            price_el.get_text(" ", strip=True)
            if price_el
            else ""
        )

        image_url = None

        img = item.select_one("img")

        if img:
            image_url = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-lazy-src")
            )

            if image_url:
                image_url = urljoin(BASE_URL, image_url)

        products.append(
            {
                "title": title,
                "url": product_url,
                "price": parse_price(price_text),
                "price_text": price_text,
                "image": image_url,
                "source": "Web Game",
                "category": "PS4",
            }
        )

    return products


def get_next_page(html):
    soup = BeautifulSoup(html, "html.parser")

    # Primero usamos rel="next", que Web Game ya tiene
    next_link = soup.select_one('link[rel="next"]')

    if next_link and next_link.get("href"):
        return urljoin(BASE_URL, next_link["href"])

    # Fallbacks
    selectors = [
        'a[rel="next"]',
        "a.next.page-numbers",
        "a.next",
    ]

    for selector in selectors:
        element = soup.select_one(selector)

        if element and element.get("href"):
            return urljoin(BASE_URL, element["href"])

    return None


def valid_catalog_url(url):
    parsed = urlparse(url)

    return (
        parsed.netloc == "web-game.net"
        and parsed.path.startswith("/categoria/juegos-ps4")
    )


def fetch_with_curl_cffi(url):
    """
    Primer intento:
    curl_cffi imita el TLS/browser fingerprint de Chrome.
    Esto puede evitar algunos 403 que reciben requests normales.
    """

    try:
        from curl_cffi import requests
    except ImportError:
        log("curl_cffi no está instalado.")
        return None

    log("Intentando con curl_cffi / Chrome...")

    try:
        session = requests.Session(
            impersonate="chrome"
        )

        headers = {
            "accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,image/avif,image/webp,"
                "image/apng,*/*;q=0.8"
            ),
            "accept-language": "es-UY,es;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": "https://web-game.net/",
            "upgrade-insecure-requests": "1",
        }

        response = session.get(
            url,
            headers=headers,
            timeout=30,
            allow_redirects=True,
        )

        log(
            f"curl_cffi HTTP {response.status_code} "
            f"| {len(response.text)} bytes"
        )

        if response.status_code == 200:
            return response.text

        log(f"curl_cffi rechazado: HTTP {response.status_code}")

    except Exception as e:
        log(f"Error curl_cffi: {e}")

    return None


def fetch_with_requests(url):
    """
    Segundo intento: requests normal con una sesión
    y headers de navegador.
    """

    try:
        import requests
    except ImportError:
        return None

    log("Intentando con requests...")

    try:
        session = requests.Session()

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,image/avif,image/webp,"
                "*/*;q=0.8"
            ),
            "Accept-Language": "es-UY,es;q=0.9,en;q=0.8",
            "Referer": "https://web-game.net/",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        response = session.get(
            url,
            headers=headers,
            timeout=30,
            allow_redirects=True,
        )

        log(
            f"requests HTTP {response.status_code} "
            f"| {len(response.text)} bytes"
        )

        if response.status_code == 200:
            return response.text

        log(f"requests rechazado: HTTP {response.status_code}")

    except Exception as e:
        log(f"Error requests: {e}")

    return None


def fetch_with_playwright(url):
    """
    Tercer intento:
    navegador Chromium real mediante Playwright.
    """

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("Playwright no está instalado.")
        return None

    log("Intentando con Playwright / Chromium...")

    try:
        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/140.0.0.0 Safari/537.36"
                ),
                locale="es-UY",
                viewport={
                    "width": 1366,
                    "height": 768,
                },
            )

            page = context.new_page()

            page.set_extra_http_headers(
                {
                    "Accept-Language": "es-UY,es;q=0.9,en;q=0.8"
                }
            )

            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            if response:
                log(
                    f"Playwright HTTP {response.status} "
                    f"| URL final: {page.url}"
                )

            page.wait_for_timeout(5000)

            html = page.content()

            log(
                f"Playwright HTML recibido: "
                f"{len(html)} bytes"
            )

            browser.close()

            if html and len(html) > 1000:
                return html

    except Exception as e:
        log(f"Error Playwright: {e}")

    return None


def fetch_page(url):
    # 1. curl_cffi
    html = fetch_with_curl_cffi(url)

    if html:
        return html

    time.sleep(2)

    # 2. requests
    html = fetch_with_requests(url)

    if html:
        return html

    time.sleep(2)

    # 3. Playwright
    html = fetch_with_playwright(url)

    if html:
        return html

    return None


def main():

    print("=== Web Game PS4 - QUARANTINE ===")

    log("=== Web Game PS4 - QUARANTINE ===")

    all_products = []

    current_url = BASE_URL
    page_number = 1

    visited = set()

    while current_url:

        if current_url in visited:
            log(f"URL repetida, deteniendo: {current_url}")
            break

        visited.add(current_url)

        log(f"[PAGE {page_number}] GET {current_url}")

        html = fetch_page(current_url)

        if not html:

            log(
                f"[PAGE {page_number}] "
                "No se pudo obtener HTML."
            )

            if page_number == 1:
                print("ERROR: Web Game sigue devolviendo 403.")
                sys.exit(1)

            break

        products = parse_products(html)

        if not products:

            log(
                f"[PAGE {page_number}] "
                "HTML recibido pero 0 productos."
            )

        else:

            log(
                f"[PAGE {page_number}] "
                f"{len(products)} productos"
            )

            all_products.extend(products)

        next_url = get_next_page(html)

        if next_url and valid_catalog_url(next_url):

            log(
                f"[PAGE {page_number}] "
                f"Siguiente página: {next_url}"
            )

            current_url = next_url
            page_number += 1

            time.sleep(2)

        else:

            log(
                f"[PAGE {page_number}] "
                "Fin de paginación."
            )

            break

    # Deduplicar
    unique = {}

    for product in all_products:
        unique[product["url"]] = product

    all_products = list(unique.values())

    result = {
        "source": "Web Game",
        "category": "PS4",
        "url": BASE_URL,
        "pages_scraped": page_number,
        "products_count": len(all_products),
        "products": all_products,
    }

    with open(
        OUTPUT_JSON,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2,
        )

    log(
        f"TOTAL PRODUCTOS: {len(all_products)}"
    )

    print(
        f"TOTAL PRODUCTOS: {len(all_products)}"
    )

    if not all_products:
        print("ERROR: 0 productos encontrados.")
        sys.exit(2)

    print("OK")


if __name__ == "__main__":
    main()

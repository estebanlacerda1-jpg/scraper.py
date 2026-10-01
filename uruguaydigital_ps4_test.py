#!/usr/bin/env python3
import csv
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://uruguayjuegosdigitales.com"
SOURCE = "UruguayDigital"
CURRENCY = "UYU"

OUTPUT_CSV = "uruguaydigital.csv"
LOG_FILE = "uruguaydigital.log.txt"

# URLs extraídas y verificadas desde el HTML de la página central.
# No se agregan las subcategorías internas (Estrenos, Packs, Pre-orden, VR, etc.)
# porque las categorías madre ya incluyen sus productos y queremos un solo
# scraper por fuente, no uno por subcategoría.
CATEGORIES = {
    "PS3": f"{BASE_URL}/product-category/juegos-digitales-ps3/",
    "PS4": f"{BASE_URL}/product-category/juegos-digitales-ps4/",
    "PS5": f"{BASE_URL}/product-category/juegos-digitales-ps5/",
    "Xbox One": f"{BASE_URL}/product-category/juegos-digitales-xbox/juegos-digitales-xbox-one/",
    "Xbox XS": f"{BASE_URL}/product-category/juegos-digitales-xbox/juegos-digitales-xbox-series-x-s/",
    "Switch1": f"{BASE_URL}/product-category/juegos-nintendo/juegos-nintendo-switch/",
    "Switch2": f"{BASE_URL}/product-category/nintendo-switch-2",
    "GamePass": f"{BASE_URL}/product-category/gift-cards/xbox-membresia/",
    "PSN Plus": f"{BASE_URL}/product-category/gift-cards/psn-plus-usa/",
}

REQUEST_DELAY = 1.0
TIMEOUT = 45
MAX_RETRIES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "es-UY,es;q=0.9,en;q=0.8",
}


def log(msg, fh):
    print(msg, flush=True)
    fh.write(msg + "\n")
    fh.flush()


def normalize_price(text):
    if not text:
        return ""

    cleaned = re.sub(r"[^\d,.\-]", "", " ".join(text.split()))
    if not cleaned:
        return ""

    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")
    elif "." in cleaned:
        left, right = cleaned.rsplit(".", 1)
        if len(right) == 3 and left.replace("-", "").isdigit():
            cleaned = left + right

    try:
        return f"{float(cleaned):.2f}"
    except ValueError:
        return ""


def get_page(session, url, category, page, fh):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT,
                allow_redirects=True,
            )

            log(
                f"[{category} | Página {page}] HTTP {r.status_code} | "
                f"intento {attempt} | {r.url}",
                fh,
            )

            if r.status_code in (403, 404):
                return r

            r.raise_for_status()
            return r

        except requests.RequestException as exc:
            log(
                f"[{category} | Página {page}] "
                f"Error {attempt}/{MAX_RETRIES}: {exc}",
                fh,
            )

            if attempt < MAX_RETRIES:
                time.sleep(5)

    return None


def extract_products(html, page_url, category):
    soup = BeautifulSoup(html, "html.parser")
    products = []

    for card in soup.select(".product-small"):
        name_el = (
            card.select_one(".woocommerce-loop-product__title a")
            or card.select_one(".woocommerce-loop-product__title")
        )

        price_el = card.select_one(".woocommerce-Price-amount")

        if not name_el:
            continue

        if name_el.name == "a":
            link = name_el.get("href", "").strip()
        else:
            link_el = card.select_one("a[href]")
            link = link_el.get("href", "").strip() if link_el else ""

        if not link:
            continue

        products.append(
            {
                "source": SOURCE,
                "category": category,
                "name": name_el.get_text(" ", strip=True),
                "price": normalize_price(
                    price_el.get_text(" ", strip=True)
                    if price_el
                    else ""
                ),
                "currency": CURRENCY,
                "url": urljoin(page_url, link),
            }
        )

    return products, soup


def find_next_url(soup, current_url):
    link = soup.select_one('link[rel="next"]')

    if not link:
        link = soup.select_one("a.next[href]")

    if link and link.get("href"):
        return urljoin(current_url, link["href"])

    return None


def scrape_category(session, category, start_url, rows, seen, fh):
    url = start_url
    page = 1
    visited_pages = set()
    hits = 0
    new_products = 0

    log("", fh)
    log("=" * 70, fh)
    log(f"INICIANDO CATEGORÍA: {category}", fh)
    log(f"URL: {start_url}", fh)
    log("=" * 70, fh)

    while url:
        if url in visited_pages:
            log(
                f"[{category}] URL repetida. Se detiene la categoría.",
                fh,
            )
            break

        visited_pages.add(url)

        response = get_page(
            session,
            url,
            category,
            page,
            fh,
        )

        if response is None:
            log(
                f"[{category}] No se pudo obtener la página. "
                "Se detiene la categoría.",
                fh,
            )
            break

        status = response.status_code

        # Regla ABC Gaming:
        # 403/404 en página 1 = error real.
        # 403/404 después de página 1 = fin de paginación.
        if status in (403, 404):
            if page == 1:
                log(
                    f"[{category}] ERROR CRÍTICO: HTTP {status} "
                    "en la primera página.",
                    fh,
                )
            else:
                log(
                    f"[{category} | Página {page}] HTTP {status} "
                    "en página posterior. Fin de paginación.",
                    fh,
                )
            break

        products, soup = extract_products(
            response.text,
            response.url,
            category,
        )

        hits += len(products)
        page_new = 0

        for product in products:
            if product["url"] in seen:
                continue

            seen.add(product["url"])
            rows.append(product)
            new_products += 1
            page_new += 1

        log(
            f"[{category} | Página {page}] "
            f"Productos: {len(products)} | "
            f"Nuevos globales: {page_new} | "
            f"Total global: {len(rows)}",
            fh,
        )

        next_page = find_next_url(soup, response.url)

        if not next_page or next_page == url:
            log(
                f"[{category}] No hay siguiente página. "
                "Categoría finalizada.",
                fh,
            )
            break

        url = next_page
        page += 1
        time.sleep(REQUEST_DELAY)

    log(
        f"[{category}] FINALIZADA | "
        f"páginas: {len(visited_pages)} | "
        f"hits: {hits} | "
        f"nuevos globales: {new_products}",
        fh,
    )


def main():
    session = requests.Session()

    rows = []
    seen = set()

    with open(LOG_FILE, "w", encoding="utf-8") as fh:
        log("=" * 70, fh)
        log("ABC GAMING - URUGUAY DIGITAL DEFINITIVO", fh)
        log(f"Fuente: {SOURCE}", fh)
        log(f"Moneda: {CURRENCY}", fh)
        log(f"Categorías: {len(CATEGORIES)}", fh)
        log("=" * 70, fh)

        for category, url in CATEGORIES.items():
            scrape_category(
                session,
                category,
                url,
                rows,
                seen,
                fh,
            )

        with open(
            OUTPUT_CSV,
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as out:
            writer = csv.DictWriter(
                out,
                fieldnames=[
                    "source",
                    "category",
                    "name",
                    "price",
                    "currency",
                    "url",
                ],
            )

            writer.writeheader()
            writer.writerows(rows)

        log("", fh)
        log("=" * 70, fh)
        log("RESUMEN FINAL", fh)
        log("=" * 70, fh)
        log(f"Categorías procesadas: {len(CATEGORIES)}", fh)
        log(f"Productos únicos globales: {len(rows)}", fh)
        log(f"CSV: {OUTPUT_CSV}", fh)
        log(f"LOG: {LOG_FILE}", fh)
        log("=" * 70, fh)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

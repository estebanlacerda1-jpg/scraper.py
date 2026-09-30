import csv
import re
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


BASE = "https://portalgames.com.ar"

# Mapa cerrado de PortalGames.
# NO se descubren categorias automaticamente.
CATEGORIES = {
    "PS3": [
        ("Anime", f"{BASE}/product-category/juegos-ps3/anime/"),
        ("Aventura", f"{BASE}/product-category/juegos-ps3/aventura/"),
        ("Baile", f"{BASE}/product-category/juegos-ps3/baile/"),
        ("Carreras", f"{BASE}/product-category/juegos-ps3/carreras/"),
        ("Combos", f"{BASE}/product-category/juegos-ps3/combos/"),
        ("Deportes", f"{BASE}/product-category/juegos-ps3/deportes/"),
        ("Estrategia", f"{BASE}/product-category/juegos-ps3/estrategia-juegos-ps3/"),
        ("Ideal para juntadas", f"{BASE}/product-category/juegos-ps3/ideal-para-juntadas/"),
        ("Lucha", f"{BASE}/product-category/juegos-ps3/lucha/"),
        ("Multi Jugador Local", f"{BASE}/product-category/juegos-ps3/multi-jugador-local/"),
        ("Para niños", f"{BASE}/product-category/juegos-ps3/para-ninos/"),
        ("Plataformas", f"{BASE}/product-category/juegos-ps3/plataformas/"),
        ("Retro", f"{BASE}/product-category/juegos-ps3/retro/"),
        ("Shooter", f"{BASE}/product-category/juegos-ps3/shooter/"),
        ("Terror", f"{BASE}/product-category/juegos-ps3/terror/"),
        ("Zombies", f"{BASE}/product-category/juegos-ps3/zombies/"),
        ("DLC", f"{BASE}/product-category/juegos-ps3/dlc/"),
        ("Season Pass", f"{BASE}/product-category/juegos-ps3/season-pass/"),
    ],

    "PS4": [
        ("Anime", f"{BASE}/product-category/juegos-ps4/anime-juegos-ps4/"),
        ("Aventura", f"{BASE}/product-category/juegos-ps4/aventura-juegos-ps4/"),
        ("Baile", f"{BASE}/product-category/juegos-ps4/baile-juegos-ps4/"),
        ("Carreras", f"{BASE}/product-category/juegos-ps4/carreras-juegos-ps4/"),
        ("Combos", f"{BASE}/product-category/juegos-ps4/combos-juegos-ps4/"),
        ("Deportes", f"{BASE}/product-category/juegos-ps4/deportes-juegos-ps4/"),
        ("Estrategia", f"{BASE}/product-category/juegos-ps4/estrategia/"),
        ("Ideal para juntadas", f"{BASE}/product-category/juegos-ps4/ideal-para-juntadas-juegos-ps4/"),
        ("Lucha", f"{BASE}/product-category/juegos-ps4/lucha-juegos-ps4/"),
        ("Multijugador Local", f"{BASE}/product-category/juegos-ps4/multijugador-local/"),
        ("Para niños", f"{BASE}/product-category/juegos-ps4/para-ninos-juegos-ps4/"),
        ("Plataformas", f"{BASE}/product-category/juegos-ps4/plataformas-juegos-ps4/"),
        ("Preventas", f"{BASE}/product-category/juegos-ps4/preventas/"),
        ("Realidad Virtual", f"{BASE}/product-category/juegos-ps4/realidad-virtual/"),
        ("Retro", f"{BASE}/product-category/juegos-ps4/retro-juegos-ps4/"),
        ("Shooter", f"{BASE}/product-category/juegos-ps4/shooter-juegos-ps4/"),
        ("Simuladores", f"{BASE}/product-category/juegos-ps4/simuladores-juegos-ps4/"),
        ("Terror", f"{BASE}/product-category/juegos-ps4/terror-juegos-ps4/"),
        ("Zombies", f"{BASE}/product-category/juegos-ps4/zombies-juegos-ps4/"),
    ],

    "PS5": [
        ("Aventura", f"{BASE}/product-category/juegos-ps5/aventuraps5/"),
        ("Baile", f"{BASE}/product-category/juegos-ps5/baileps5/"),
        ("Carreras", f"{BASE}/product-category/juegos-ps5/carrerasps5/"),
        ("Deportes", f"{BASE}/product-category/juegos-ps5/deportesps5/"),
        ("Lucha", f"{BASE}/product-category/juegos-ps5/luchaps5/"),
        ("Para niños", f"{BASE}/product-category/juegos-ps5/ninosps5/"),
        ("Plataformas", f"{BASE}/product-category/juegos-ps5/plataformasps5/"),
        ("Shooter", f"{BASE}/product-category/juegos-ps5/shooterps5/"),
    ],

    "Switch": [
        ("Juegos", f"{BASE}/product-category/nintendo-switch/juegos/"),
    ],
}


OUTPUT_CSV = "portalgames.csv"
OUTPUT_LOG = "portalgames.log.txt"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_url(url):
    if not url:
        return ""

    absolute = urljoin(BASE, url)
    parsed = urlparse(absolute)

    if parsed.netloc and parsed.netloc != urlparse(BASE).netloc:
        return ""

    parsed = parsed._replace(fragment="")

    path = parsed.path or "/"

    if path != "/" and not path.endswith("/"):
        path += "/"

    return urlunparse(parsed)


def parse_price(text):
    """
    PortalGames usa precios como:
    $17.399,00
    $6.900,00
    $4.999,00

    Devuelve entero en ARS.
    """
    text = clean_text(text)

    match = re.search(r"\$?\s*([0-9][0-9\.\,]*)", text)

    if not match:
        return ""

    raw = match.group(1)

    if "," in raw:
        raw = raw.split(",")[0]
        raw = raw.replace(".", "")
    else:
        # Si hay un solo punto y son 3 cifras después,
        # lo tratamos como separador de miles.
        if raw.count(".") == 1:
            left, right = raw.split(".")
            if len(right) == 3:
                raw = left + right

        raw = raw.replace(".", "")

    try:
        return int(raw)
    except ValueError:
        return ""


def close_popups(page):
    selectors = [
        'button:has-text("Aceptar")',
        'button:has-text("ACEPTAR")',
        'button:has-text("Cerrar")',
        'button:has-text("CERRAR")',
        'button:has-text("No, gracias")',
        '.mfp-close',
        '.pys-close',
        '[aria-label="Close"]',
        '[aria-label="Cerrar"]',
    ]

    for selector in selectors:
        try:
            loc = page.locator(selector)
            count = min(loc.count(), 5)

            for i in range(count):
                try:
                    item = loc.nth(i)

                    if item.is_visible(timeout=500):
                        item.click(timeout=1000)
                        page.wait_for_timeout(300)

                except Exception:
                    pass

        except Exception:
            pass


def has_cloudflare_marker(html):
    text = (html or "").lower()

    markers = [
        "just a moment",
        "cf-chl-",
        "challenge-platform",
        "enable javascript and cookies to continue",
        "cf-mitigated",
    ]

    return any(marker in text for marker in markers)


def load_page(page, url, log):
    url = normalize_url(url)

    try:
        response = page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=90000,
        )

        status = response.status if response else 0

        log.append(f"GET {url} -> HTTP {status}")

        page.wait_for_timeout(5000)

        close_popups(page)

        # Scroll para activar contenido lazy.
        for _ in range(5):
            try:
                page.mouse.wheel(0, 5000)
                page.wait_for_timeout(1200)
            except Exception:
                break

        close_popups(page)

        html = page.content()

        # Solo es diagnóstico.
        # NO abortamos porque la prueba Anime funcionó aun
        # cuando aparecieron marcadores de Cloudflare.
        if has_cloudflare_marker(html):
            log.append(
                "AVISO: se detectaron marcadores de Cloudflare, "
                "pero se continúa con el HTML."
            )

        return html, status

    except PlaywrightTimeoutError as exc:
        log.append(f"TIMEOUT {url}: {exc}")

        try:
            return page.content(), 0
        except Exception:
            return "", 0

    except Exception as exc:
        log.append(f"ERROR {url}: {exc}")
        return "", 0


def extract_products(
    html,
    block,
    category_name,
    category_url,
    page_number,
    log,
):
    soup = BeautifulSoup(html, "html.parser")

    products = []
    seen_urls = set()

    # PortalGames / Flatsome / WooCommerce.
    for card in soup.select(".product-small"):
        name_link = card.select_one(
            ".name.product-title.woocommerce-loop-product__title a"
        )

        if not name_link:
            name_link = card.select_one(
                ".woocommerce-loop-product__title a"
            )

        if not name_link:
            continue

        name = clean_text(
            name_link.get_text(" ", strip=True)
        )

        product_url = normalize_url(
            name_link.get("href")
        )

        if not name or not product_url:
            continue

        # Evita links de categorías u otras URLs.
        if "/product/" not in urlparse(product_url).path:
            continue

        if product_url in seen_urls:
            continue

        seen_urls.add(product_url)

        price_node = card.select_one(
            ".woocommerce-Price-amount"
        )

        price_text = (
            clean_text(
                price_node.get_text(" ", strip=True)
            )
            if price_node
            else ""
        )

        category_node = card.select_one(
            ".product-cat"
        )

        category_display = (
            clean_text(
                category_node.get_text(" ", strip=True)
            )
            if category_node
            else category_name
        )

        products.append({
            "fuente": "PortalGames",
            "nombre": name,
            "categoria": category_display,
            "bloque": block,
            "clasificacion": category_name,
            "precio": parse_price(price_text),
            "precio_mostrado": price_text,
            "moneda": "ARS",
            "url": product_url,
            "categoria_url": category_url,
            "pagina": page_number,
        })

    log.append(
        f"{block} | {category_name} | "
        f"pagina {page_number} | "
        f"productos encontrados: {len(products)}"
    )

    return products


def pagination_urls(html, current_url):
    soup = BeautifulSoup(html, "html.parser")

    current = normalize_url(current_url)

    parsed_current = urlparse(current)

    # /product-category/.../categoria/
    base_path = re.sub(
        r"/page/\d+/?$",
        "/",
        parsed_current.path,
    )

    found = set()

    selectors = [
        'a[rel="next"]',
        '.page-numbers a[href]',
        'nav.woocommerce-pagination a[href]',
        '.woocommerce-pagination a[href]',
    ]

    for selector in selectors:
        for a in soup.select(selector):
            href = normalize_url(a.get("href"))

            if not href:
                continue

            parsed = urlparse(href)

            # Paginación estilo /page/2/
            if re.search(r"/page/\d+/?$", parsed.path):
                if parsed.path.startswith(base_path.rstrip("/") + "/page/"):
                    found.add(href)
                    continue

            # Por si el sitio usa ?paged=2
            if "paged=" in parsed.query:
                found.add(href)

    return sorted(found)


def scrape_category(
    page,
    block,
    category_name,
    category_url,
    log,
):
    """
    Procesa SOLO la URL concreta de clasificación.
    No descubre otras categorías.
    """

    category_url = normalize_url(category_url)

    page_queue = [category_url]
    pages_seen = set()

    products_by_url = {}

    while page_queue:
        url = page_queue.pop(0)

        if not url or url in pages_seen:
            continue

        pages_seen.add(url)

        match = re.search(
            r"/page/(\d+)/?$",
            urlparse(url).path,
        )

        page_number = (
            int(match.group(1))
            if match
            else 1
        )

        html, status = load_page(
            page,
            url,
            log,
        )

        if not html:
            log.append(
                f"{block} | {category_name} | "
                f"pagina {page_number}: HTML vacio."
            )
            continue

        products = extract_products(
            html,
            block,
            category_name,
            category_url,
            page_number,
            log,
        )

        for product in products:
            # Deduplicación dentro de toda PortalGames.
            products_by_url[product["url"]] = product

        # 403/404 en una página posterior = fin.
        if status in (403, 404) and page_number > 1:
            log.append(
                f"{block} | {category_name} | "
                f"HTTP {status} en pagina {page_number}: "
                f"fin de paginacion."
            )
            continue

        for next_url in pagination_urls(
            html,
            url,
        ):
            if next_url not in pages_seen:
                page_queue.append(next_url)

    log.append(
        f"FIN {block} | {category_name} | "
        f"paginas visitadas: {len(pages_seen)} | "
        f"productos unicos: {len(products_by_url)}"
    )

    return products_by_url


def main():
    log = [
        "========================================",
        "PORTALGAMES - SCRAPER DEFINITIVO",
        "========================================",
        "Metodo: Playwright Chromium + BeautifulSoup",
        "Categorias: mapa fijo de 46 URLs",
        "Descubrimiento automatico: DESACTIVADO",
        "Deduplicacion: URL de producto",
        "",
    ]

    total_categories = sum(
        len(items)
        for items in CATEGORIES.values()
    )

    log.append(
        f"Categorias configuradas: {total_categories}"
    )
    log.append("")

    all_products = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context = browser.new_context(
            viewport={
                "width": 1400,
                "height": 900,
            },
            user_agent=USER_AGENT,
            locale="es-419",
            timezone_id="America/Montevideo",
            java_script_enabled=True,
        )

        page = context.new_page()

        for block, categories in CATEGORIES.items():
            log.append("")
            log.append(
                f"######## BLOQUE {block} ########"
            )

            for category_name, category_url in categories:
                log.append("")
                log.append(
                    f"### {block} - {category_name}"
                )
                log.append(category_url)

                try:
                    products = scrape_category(
                        page,
                        block,
                        category_name,
                        category_url,
                        log,
                    )

                    for url, product in products.items():
                        all_products[url] = product

                except Exception as exc:
                    log.append(
                        f"ERROR EN {block} / "
                        f"{category_name}: {exc}"
                    )

        browser.close()

    final_products = sorted(
        all_products.values(),
        key=lambda item: (
            item["bloque"],
            item["clasificacion"],
            item["nombre"].lower(),
        ),
    )

    with open(
        OUTPUT_CSV,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "fuente",
                "nombre",
                "categoria",
                "bloque",
                "clasificacion",
                "precio",
                "precio_mostrado",
                "moneda",
                "url",
                "categoria_url",
                "pagina",
            ],
        )

        writer.writeheader()
        writer.writerows(final_products)

    # Resumen por bloque.
    counts = {}

    for product in final_products:
        block = product["bloque"]
        counts[block] = counts.get(block, 0) + 1

    log.extend([
        "",
        "========================================",
        "RESUMEN FINAL",
        "========================================",
        f"TOTAL CATEGORIAS: {total_categories}",
        f"TOTAL PRODUCTOS UNICOS: {len(final_products)}",
    ])

    for block in (
        "PS3",
        "PS4",
        "PS5",
        "Switch",
    ):
        log.append(
            f"{block}: {counts.get(block, 0)}"
        )

    log.extend([
        "========================================",
        f"CSV: {OUTPUT_CSV}",
        f"LOG: {OUTPUT_LOG}",
        "========================================",
    ])

    with open(
        OUTPUT_LOG,
        "w",
        encoding="utf-8",
    ) as f:
        f.write("\n".join(log) + "\n")

    print("\n".join(log))
    print("")
    print(f"CSV generado: {OUTPUT_CSV}")
    print(f"Log generado: {OUTPUT_LOG}")


if __name__ == "__main__":
    main()

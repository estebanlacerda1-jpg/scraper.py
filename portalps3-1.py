import asyncio
import csv
import os
import random
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

TEST_CATEGORIES = [
    ("PS3", "Anime", "https://portalgames.com.ar/product-category/juegos-ps3/anime/"),
    ("PS3", "Aventura", "https://portalgames.com.ar/product-category/juegos-ps3/aventura/"),
]

# HEADLESS=0 -> navegador "real" (usar con: xvfb-run python portalps3.py)
HEADLESS = os.getenv("HEADLESS", "1") != "0"
USE_REAL_CHROME = os.getenv("REAL_CHROME", "0") == "1"  # requiere: playwright install chrome
WAIT_BETWEEN_CATEGORIES = (12, 25)  # segundos, aleatorio
CHALLENGE_MAX_WAIT = 40             # segundos esperando que pase "Just a moment"
RETRIES_PER_CATEGORY = 2

LOG_FILE = "portalgames_test_2categorias.log.txt"
CSV_FILE = "portalgames_test_2categorias.csv"
PRODUCTS_CSV = "portalgames_productos.csv"
STATE_FILE = "portalgames_state.json"

CF_MARKERS = ["Just a moment", "cf-mitigated", "challenge-platform", "Enable JavaScript and cookies to continue"]


def log(message):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def parse_price(text):
    cleaned = re.sub(r"[^\d,.\-]", "", (text or "").strip())
    if not cleaned:
        return None
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


async def close_popups(page):
    for selector in ["button:has-text('Aceptar')", "button:has-text('Cerrar')", "button:has-text('No, gracias')",
                     ".close", ".mfp-close", "[aria-label='Close']"]:
        try:
            buttons = page.locator(selector)
            for i in range(min(await buttons.count(), 5)):
                try:
                    if await buttons.nth(i).is_visible():
                        await buttons.nth(i).click(timeout=1500)
                        await page.wait_for_timeout(500)
                except Exception:
                    pass
        except Exception:
            pass


async def extract_products(page):
    products = []
    cards = page.locator(".product-small")
    for i in range(await cards.count()):
        card = cards.nth(i)
        try:
            name_locator = card.locator(".name.product-title.woocommerce-loop-product__title a")
            name = (await name_locator.inner_text()).strip()
            url = (await name_locator.get_attribute("href") or "").strip()
        except Exception:
            name, url = "", ""
        try:
            price_raw = (await card.locator(".woocommerce-Price-amount").first.inner_text()).strip()
        except Exception:
            price_raw = ""
        try:
            category = (await card.locator(".product-cat").first.inner_text()).strip()
        except Exception:
            category = ""
        if name and url:
            products.append({"name": name, "url": url, "price_ars": parse_price(price_raw),
                             "price_raw": price_raw, "category": category})
    return list({p["url"]: p for p in products}.values())


async def wait_challenge(page):
    """Espera hasta CHALLENGE_MAX_WAIT s a que desaparezca el desafío de Cloudflare."""
    for _ in range(CHALLENGE_MAX_WAIT):
        try:
            title = (await page.title()).lower()
        except Exception:
            title = ""
        if "just a moment" not in title and "un momento" not in title:
            return True
        await page.wait_for_timeout(1000)
    return False


async def scrape_category(page, platform, category, url):
    log("=" * 70)
    log(f"INICIO {platform} | {category}")
    log(f"URL: {url}")
    result = {"platform": platform, "category": category, "url": url,
              "http_status": None, "html_chars": 0, "products": []}

    for attempt in range(1, RETRIES_PER_CATEGORY + 1):
        log(f"Intento {attempt}/{RETRIES_PER_CATEGORY}")
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=90000)
            status = response.status if response else None
            result["http_status"] = status
            log(f"HTTP inicial: {status}")

            passed = await wait_challenge(page)
            if not passed:
                log(f"El desafío de Cloudflare no se resolvió en {CHALLENGE_MAX_WAIT}s")

            await page.wait_for_timeout(random.randint(3000, 6000))
            await close_popups(page)

            # scroll gradual (más humano que un salto de 5000px)
            for _ in range(6):
                await page.mouse.wheel(0, random.randint(600, 1200))
                await page.wait_for_timeout(random.randint(700, 1500))

            html = await page.content()
            result["html_chars"] = len(html)
            markers = [m for m in CF_MARKERS if m.lower() in html.lower()]
            if markers:
                log("Marcadores Cloudflare presentes: " + ", ".join(markers))
            else:
                log("No se detectaron marcadores Cloudflare conocidos.")

            products = await extract_products(page)
            result["products"] = products
            log(f"HTML: {len(html)} caracteres")
            log(f"PRODUCTOS ENCONTRADOS: {len(products)}")
            for p in products[:10]:
                log(f"  - {p['name']} | {p['price_raw']} | {p['url']}")

            if products:
                return result

            try:
                log(f"Título de página: {await page.title()}")
            except Exception:
                pass
            try:
                log("Texto body: " + (await page.locator("body").inner_text())[:1000].replace("\n", " | "))
            except Exception:
                pass

            if attempt < RETRIES_PER_CATEGORY:
                espera = random.randint(20, 40)
                log(f"Sin productos. Reintentando en {espera}s (mismo contexto)...")
                await asyncio.sleep(espera)

        except PlaywrightTimeoutError as e:
            log(f"TIMEOUT: {e}")
        except Exception as e:
            log(f"ERROR: {type(e).__name__}: {e}")

    return result


async def main():
    Path(LOG_FILE).write_text("", encoding="utf-8")
    log("PORTALGAMES - TEST 2 CATEGORIAS")
    log("Un solo navegador/contexto para todas las categorías (se conserva la cookie cf_clearance)")
    log(f"headless={HEADLESS} | chrome real={USE_REAL_CHROME}")

    results = []
    async with async_playwright() as playwright:
        launch_kwargs = dict(
            headless=HEADLESS,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"],
        )
        if USE_REAL_CHROME:
            launch_kwargs["channel"] = "chrome"

        browser = await playwright.chromium.launch(**launch_kwargs)
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
            java_script_enabled=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = await context.new_page()

        try:
            for i, (platform, category, url) in enumerate(TEST_CATEGORIES):
                if i > 0:
                    espera = random.randint(*WAIT_BETWEEN_CATEGORIES)
                    log(f"Esperando {espera} segundos antes de la siguiente categoría (misma sesión)...")
                    await asyncio.sleep(espera)
                results.append(await scrape_category(page, platform, category, url))
                # guardar cookies tras cada categoría (útil para depurar)
                try:
                    await context.storage_state(path=STATE_FILE)
                except Exception:
                    pass
        finally:
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["platform", "category", "url", "http_status", "html_chars", "products_found"])
        writer.writeheader()
        for r in results:
            writer.writerow({"platform": r["platform"], "category": r["category"], "url": r["url"],
                             "http_status": r["http_status"], "html_chars": r["html_chars"],
                             "products_found": len(r["products"])})

    with open(PRODUCTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["platform", "category", "name", "price_ars", "price_raw", "url"])
        writer.writeheader()
        for r in results:
            for p in r["products"]:
                writer.writerow({"platform": r["platform"], "category": r["category"], "name": p["name"],
                                 "price_ars": p["price_ars"], "price_raw": p["price_raw"], "url": p["url"]})

    log("=" * 70)
    log("RESULTADO FINAL")
    for r in results:
        log(f"{r['platform']} | {r['category']} | HTTP {r['http_status']} | productos: {len(r['products'])} | HTML: {r['html_chars']} chars")
    log(f"CSV generado: {CSV_FILE}")
    log(f"Productos: {PRODUCTS_CSV}")
    log(f"LOG generado: {LOG_FILE}")


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import csv
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

TEST_CATEGORIES = [
    ("PS3", "Anime", "https://portalgames.com.ar/product-category/juegos-ps3/anime/"),
    ("PS3", "Aventura", "https://portalgames.com.ar/product-category/juegos-ps3/aventura/"),
]
WAIT_BETWEEN_CATEGORIES = 20
LOG_FILE = "portalgames_test_2categorias.log.txt"
CSV_FILE = "portalgames_test_2categorias.csv"

def log(message):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def parse_price(text):
    cleaned = re.sub(r"[^\d,.\-]", "", (text or "").strip())
    if not cleaned: return None
    if "," in cleaned: cleaned = cleaned.replace(".", "").replace(",", ".")
    else: cleaned = cleaned.replace(",", "")
    try: return float(cleaned)
    except ValueError: return None

async def close_popups(page):
    for selector in ["button:has-text('Aceptar')", "button:has-text('Cerrar')", "button:has-text('No, gracias')", ".close", ".mfp-close", "[aria-label='Close']"]:
        try:
            buttons = page.locator(selector)
            for i in range(min(await buttons.count(), 5)):
                try:
                    if await buttons.nth(i).is_visible():
                        await buttons.nth(i).click(timeout=1500)
                        await page.wait_for_timeout(500)
                except Exception: pass
        except Exception: pass

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
        try: price_raw = (await card.locator(".woocommerce-Price-amount").first.inner_text()).strip()
        except Exception: price_raw = ""
        try: category = (await card.locator(".product-cat").first.inner_text()).strip()
        except Exception: category = ""
        if name and url:
            products.append({"name": name, "url": url, "price_ars": parse_price(price_raw), "price_raw": price_raw, "category": category})
    return list({p["url"]: p for p in products}.values())

async def run_one_category(playwright, platform, category, url):
    log("=" * 70); log(f"INICIO {platform} | {category}"); log(f"URL: {url}"); log("Creando navegador NUEVO para esta categoría...")
    browser = context = None
    try:
        browser = await playwright.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(viewport={"width":1366,"height":768}, locale="es-AR", timezone_id="America/Argentina/Buenos_Aires", java_script_enabled=True, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
        page = await context.new_page()
        response = await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        status = response.status if response else None
        log(f"HTTP inicial: {status}")
        await page.wait_for_timeout(8000)
        await close_popups(page)
        for _ in range(5):
            await page.mouse.wheel(0, 5000); await page.wait_for_timeout(1200)
        html = await page.content()
        markers = [m for m in ["Just a moment", "cf-mitigated", "challenge-platform", "Enable JavaScript and cookies to continue"] if m.lower() in html.lower()]
        if markers: log("Marcadores Cloudflare presentes: " + ", ".join(markers) + " — se comprueba igualmente si hay productos.")
        else: log("No se detectaron marcadores Cloudflare conocidos.")
        products = await extract_products(page)
        log(f"HTML: {len(html)} caracteres"); log(f"PRODUCTOS ENCONTRADOS: {len(products)}")
        for p in products[:10]: log(f"  - {p['name']} | {p['price_raw']} | {p['url']}")
        if not products:
            try: log(f"Título de página: {await page.title()}")
            except Exception: pass
            try: log("Texto body: " + (await page.locator("body").inner_text())[:1000].replace("\n", " | "))
            except Exception: pass
        return {"platform":platform,"category":category,"url":url,"http_status":status,"html_chars":len(html),"products":products}
    except PlaywrightTimeoutError as e:
        log(f"TIMEOUT: {e}"); return {"platform":platform,"category":category,"url":url,"http_status":None,"html_chars":0,"products":[]}
    except Exception as e:
        log(f"ERROR: {type(e).__name__}: {e}"); return {"platform":platform,"category":category,"url":url,"http_status":None,"html_chars":0,"products":[]}
    finally:
        log("Cerrando navegador/contexto de esta categoría...")
        try:
            if context: await context.close()
        except Exception: pass
        try:
            if browser: await browser.close()
        except Exception: pass
        log("Navegador cerrado.")

async def main():
    Path(LOG_FILE).write_text("", encoding="utf-8")
    log("PORTALGAMES - TEST 2 CATEGORIAS"); log("Prueba de aislamiento de navegador/contexto"); log("Categorías a probar: 2")
    results = []
    async with async_playwright() as playwright:
        for i, (platform, category, url) in enumerate(TEST_CATEGORIES):
            if i > 0:
                log(f"Esperando {WAIT_BETWEEN_CATEGORIES} segundos antes del siguiente navegador...")
                await asyncio.sleep(WAIT_BETWEEN_CATEGORIES)
            results.append(await run_one_category(playwright, platform, category, url))
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["platform","category","url","http_status","html_chars","products_found"]); writer.writeheader()
        for r in results: writer.writerow({"platform":r["platform"],"category":r["category"],"url":r["url"],"http_status":r["http_status"],"html_chars":r["html_chars"],"products_found":len(r["products"])})
    log("=" * 70); log("RESULTADO FINAL")
    for r in results: log(f"{r['platform']} | {r['category']} | HTTP {r['http_status']} | productos: {len(r['products'])} | HTML: {r['html_chars']} chars")
    log(f"CSV generado: {CSV_FILE}"); log(f"LOG generado: {LOG_FILE}")

if __name__ == "__main__": asyncio.run(main())

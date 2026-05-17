# =========================================================
# ABC GAMING - SCRAPER UNIFICADO
# Fuentes: Catálogo Maestro + Flatsome/WooCommerce + Eneba
# Salida: catalogo_completo_abc_gaming.xlsx
# =========================================================

import re
import asyncio
import requests
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

HEADERS = {"User-Agent": "Mozilla/5.0"}
PAGINAS = 2


# =========================================================
# FUNCIONES AUXILIARES
# =========================================================

def normalizar_nombre(nombre):
    basura = [
        "DIGITAL", "PRIMARIO", "SECUNDARIO", "CUENTA",
        "OFFLINE", "ONLINE", "PS4", "PS5", "PS3",
        "XBOX", "NINTENDO", "STANDARD", "DELUXE", "ULTIMATE"
    ]
    nombre = nombre.upper()
    for b in basura:
        nombre = nombre.replace(b, "")
    return re.sub(r"\s+", " ", nombre).strip()


def limpiar_nombre_eneba(nombre):
    remover = [
        "Código de Steam", "Steam Key", "Steam",
        "GLOBAL", "LATAM", "EUROPE",
        "United States", "UNITED STATES",
        "Xbox Live", "Xbox", "PSN", "Nintendo",
        "Código de", "Código", "Key",
    ]
    for r in remover:
        nombre = nombre.replace(r, "")
    return re.sub(r"\s+", " ", nombre).strip()


def extraer_precio_eneba(texto):
    texto = texto.replace("Desde", "").replace("From", "").strip()
    match = re.search(r'(\d+[.,]?\d*)\s*US\$', texto)
    if match:
        try:
            return f"{float(match.group(1).replace(',', '.')):.2f} USD"
        except:
            pass
    match2 = re.search(r'\$\s*(\d+[.,]\d+)', texto)
    if match2:
        try:
            return f"{float(match2.group(1).replace(',', '.')):.2f} USD"
        except:
            pass
    return ""


# =========================================================
# SCRAPERS SÍNCRONOS (requests)
# =========================================================

def scrape_shopify(url, paginas=PAGINAS):
    productos = []
    for page in range(1, paginas + 1):
        page_url = f"{url}/products.json?limit=250&page={page}"
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=30)
            data = r.json()
            for p in data.get("products", []):
                try:
                    productos.append({
                        "nombre": p["title"],
                        "precio": float(p["variants"][0]["price"]),
                        "link": f"{url.replace('/collections', '/products')}/{p['handle']}"
                    })
                except:
                    continue
        except:
            continue
    return productos


def scrape_woocommerce(url, paginas=PAGINAS):
    productos = []
    selectors = [
        "li.product", "div.product", ".product-small",
        ".type-product", ".product-grid-item", ".wd-product", ".product-item"
    ]
    for page in range(1, paginas + 1):
        page_url = url if page == 1 else f"{url.rstrip('/')}/page/{page}/"
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=30)
            soup = BeautifulSoup(r.text, "html.parser")
            cards = []
            for sel in selectors:
                cards.extend(soup.select(sel))
            for c in cards:
                try:
                    nombre_el = c.select_one(
                        "h2, h3, h4, .product-title, .woocommerce-loop-product__title, .wd-entities-title"
                    )
                    precio_el = c.select_one(".price, .amount, bdi")
                    if not nombre_el or not precio_el:
                        continue
                    nombre = nombre_el.get_text(strip=True)
                    precio_txt = precio_el.get_text(strip=True)
                    nums = re.findall(r"\d+", precio_txt.replace(".", ""))
                    if not nums:
                        continue
                    precio = int(nums[0])
                    if precio < 100:
                        continue
                    link_el = c.select_one("a")
                    link = link_el["href"] if link_el else url
                    productos.append({"nombre": nombre, "precio": precio, "link": link})
                except:
                    continue
        except Exception as e:
            print("ERROR:", e)
    return productos


def scrape_tiendanube(url, paginas=PAGINAS):
    productos = []
    for page in range(1, paginas + 1):
        page_url = url if page == 1 else f"{url}?mpage={page}"
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=30)
            soup = BeautifulSoup(r.text, "html.parser")
            for c in soup.select(".js-item-product"):
                try:
                    nombre = c.select_one(".js-item-name").get_text(strip=True)
                    precio = c.select_one(".js-price-display").get_text(strip=True)
                    precio = int(re.findall(r"\d+", precio.replace(".", ""))[0])
                    link = c.select_one("a")["href"]
                    productos.append({"nombre": nombre, "precio": precio, "link": link})
                except:
                    continue
        except:
            continue
    return productos


def scrape_flatsome_requests(url, paginas=PAGINAS):
    productos = []
    for page in range(1, paginas + 1):
        page_url = url if page == 1 else f"{url.rstrip('/')}/page/{page}/"
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=30)
            soup = BeautifulSoup(r.text, "lxml")
            for c in soup.select(".product-small"):
                try:
                    nombre_tag = c.select_one(".woocommerce-loop-product__title")
                    if not nombre_tag:
                        continue
                    nombre = nombre_tag.get_text(strip=True)
                    precio_tag = c.select_one(".price")
                    if not precio_tag:
                        continue
                    precio_txt = precio_tag.get_text(" ", strip=True)
                    nums = re.findall(r"\d+[.,]?\d*", precio_txt.replace(".", ""))
                    if not nums:
                        continue
                    precio = float(nums[0].replace(",", "."))
                    a = c.select_one("a")
                    link = a["href"] if a else ""
                    productos.append({"nombre": nombre, "precio": precio, "link": link})
                except:
                    continue
        except Exception as e:
            print("ERROR:", e)
    return productos


# =========================================================
# FUNCIÓN ASYNC PRINCIPAL (Playwright)
# =========================================================

async def main():

    todos = []

    # =====================================================
    # PLAYWRIGHT FALLBACK PARA WOOCOMMERCE
    # =====================================================

    async def scrape_woocommerce_playwright(url, paginas=PAGINAS):
        prods = []
        selectors = [
            "li.product", "div.product", ".product-small",
            ".type-product", ".product-grid-item", ".wd-product", ".product-item"
        ]
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            page = await browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
            )
            for num in range(1, paginas + 1):
                page_url = url if num == 1 else f"{url.rstrip('/')}/page/{num}/"
                try:
                    await page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(3000)
                    html = await page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    cards = []
                    for sel in selectors:
                        cards.extend(soup.select(sel))
                    for c in cards:
                        try:
                            nombre_el = c.select_one(
                                "h2, h3, h4, .product-title, .woocommerce-loop-product__title, .wd-entities-title"
                            )
                            precio_el = c.select_one(".price, .amount, bdi")
                            if not nombre_el or not precio_el:
                                continue
                            nombre = nombre_el.get_text(strip=True)
                            precio_txt = precio_el.get_text(strip=True)
                            nums = re.findall(r"\d+", precio_txt.replace(".", ""))
                            if not nums:
                                continue
                            precio = int(nums[0])
                            if precio < 100:
                                continue
                            link_el = c.select_one("a")
                            link = link_el["href"] if link_el else url
                            prods.append({"nombre": nombre, "precio": precio, "link": link})
                        except:
                            continue
                except Exception as e:
                    print(f"   ERROR Playwright página {num}: {e}")
            await browser.close()
        return prods

    # =====================================================
    # PARTE 1: CATÁLOGO MAESTRO
    # =====================================================

    print("\n" + "="*60)
    print("PARTE 1: CATÁLOGO MAESTRO")
    print("="*60)

    CATALOGOS = {

        "Alpha PS5 Primaria":   {"tipo": "shopify",     "url": "https://alphajuegosdigitales.com/collections/ps5-principal"},
        "Alpha PS5 Secundaria": {"tipo": "shopify",     "url": "https://alphajuegosdigitales.com/collections/juegos-ps5"},
        "Alpha PS4 Primaria":   {"tipo": "shopify",     "url": "https://alphajuegosdigitales.com/collections/ps4-principal"},
        "Alpha PS4 Secundaria": {"tipo": "shopify",     "url": "https://alphajuegosdigitales.com/collections/juegos-ps4"},
        "Alpha Xbox":           {"tipo": "shopify",     "url": "https://alphajuegosdigitales.com/collections/juegos-xbox"},

        "DigitalWorld PS4":     {"tipo": "woocommerce", "url": "https://digitalworldpsn.com/es/juegos-digitales-ps4/?v=1b23f8a4c97c"},
        "DigitalWorld PS5":     {"tipo": "woocommerce", "url": "https://digitalworldpsn.com/es/juegos-digitales-ps5/?v=1b23f8a4c97c"},
        "DigitalWorld VR":      {"tipo": "woocommerce", "url": "https://digitalworldpsn.com/es/juegos-ps-vr-vr2/?v=1b23f8a4c97c"},
        "DigitalWorld Xbox":    {"tipo": "woocommerce", "url": "https://digitalworldpsn.com/es/juegos-digitales-xbox/?v=1b23f8a4c97c"},
        "DigitalWorld Switch":  {"tipo": "woocommerce", "url": "https://digitalworldpsn.com/es/juegos-digitales-switch/?v=1b23f8a4c97c"},

        "Dix Fortnite":         {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/tarjetas/fortnite/"},
        "Dix PS5":              {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/juegos/ps5/"},
        "Dix PS4":              {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/juegos/ps4/"},
        "Dix PS3":              {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/juegos/ps3/"},
        "Dix FC Points":        {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/tarjetas/fc-points/"},
        "Dix Nintendo":         {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/tarjetas/nintendo/"},
        "Dix Playstation":      {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/tarjetas/ps/"},
        "Dix Razer":            {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/tarjetas/razer-gold/"},
        "Dix Steam":            {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/tarjetas/steam/"},
        "Dix Xbox":             {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/tarjetas/xbox/"},

        "EstacionPlay PS4":     {"tipo": "tiendanube",  "url": "https://estacionplay.com/videojuegos/playstation-4/"},
        "EstacionPlay PS5":     {"tipo": "tiendanube",  "url": "https://estacionplay.com/videojuegos/playstation-5/"},
        "EstacionPlay Memb":    {"tipo": "tiendanube",  "url": "https://estacionplay.com/videojuegos/psn-card-y-plus/"},

        "GamerLab PS4":         {"tipo": "shopify",     "url": "https://juegosdigitalesgamerlab.com/collections/frontpage"},
        "GamerLab PS5":         {"tipo": "shopify",     "url": "https://juegosdigitalesgamerlab.com/collections/juegos-ps5"},
        "GamerLab EA Play":     {"tipo": "shopify",     "url": "https://juegosdigitalesgamerlab.com/collections/membresia-ea-play"},
        "GamerLab PSN":         {"tipo": "shopify",     "url": "https://juegosdigitalesgamerlab.com/collections/play-station-plus"},
        "GamerLab Giftcards":   {"tipo": "shopify",     "url": "https://juegosdigitalesgamerlab.com/collections/all"},

    }

    for nombre_tienda, cfg in CATALOGOS.items():
        print(f"\nScrapeando {nombre_tienda}")
        try:
            if cfg["tipo"] == "shopify":
                productos = scrape_shopify(cfg["url"])
            elif cfg["tipo"] == "woocommerce":
                productos = scrape_woocommerce(cfg["url"])
                if len(productos) == 0:
                    print("   -> requests dio 0, reintentando con Playwright...")
                    productos = await scrape_woocommerce_playwright(cfg["url"])
            elif cfg["tipo"] == "tiendanube":
                productos = scrape_tiendanube(cfg["url"])
            else:
                productos = []

            print(f" -> {len(productos)} productos")

            for p in productos:
                p["tienda"] = nombre_tienda
                p["fuente"] = "Catalogo Maestro"
                p["nombre_normalizado"] = normalizar_nombre(p["nombre"])

            todos.extend(productos)

        except Exception as e:
            print("ERROR:", e)

    # =====================================================
    # PARTE 2: FLATSOME / WOOCOMMERCE (Playwright)
    # =====================================================

    print("\n" + "="*60)
    print("PARTE 2: FLATSOME / WOOCOMMERCE (Playwright)")
    print("="*60)

    TIENDAS_FLATSOME = {
        "TodoDigital":  {"tipo": "playwright", "url": "https://tododigitalshop.com/juegos-digitales-ps4/"},
        "PortalGames":  {"tipo": "playwright", "url": "https://portalgames.com.ar/product-category/juegos-ps4/"},
        "UYDigital":    {"tipo": "requests",   "url": "https://uruguayjuegosdigitales.com/product-category/juegos-digitales-ps4/"},
        "MDQ":          {"tipo": "requests",   "url": "https://mdqstore.com/categoria-producto/juegos-ps4/"},
    }

    async def scrape_flatsome_playwright(url, paginas=PAGINAS):
        prods = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            for numero in range(1, paginas + 1):
                page_url = url if numero == 1 else f"{url.rstrip('/')}/page/{numero}/"
                print(f"   Página {numero}")
                try:
                    await page.goto(page_url, wait_until="networkidle", timeout=90000)
                    await page.wait_for_timeout(3000)
                    html = await page.content()
                    soup = BeautifulSoup(html, "lxml")
                    for c in soup.select(".product-small"):
                        try:
                            nombre_tag = c.select_one(".woocommerce-loop-product__title")
                            if not nombre_tag:
                                continue
                            nombre = nombre_tag.get_text(strip=True)
                            precio_tag = c.select_one(".price")
                            if not precio_tag:
                                continue
                            precio_txt = precio_tag.get_text(" ", strip=True)
                            nums = re.findall(r"\d+[.,]?\d*", precio_txt.replace(".", ""))
                            if not nums:
                                continue
                            precio = float(nums[0].replace(",", "."))
                            a = c.select_one("a")
                            link = a["href"] if a else ""
                            prods.append({"nombre": nombre, "precio": precio, "link": link})
                        except:
                            continue
                except Exception as e:
                    print("ERROR PAGINA:", e)
            await browser.close()
        return prods

    for nombre_tienda, cfg in TIENDAS_FLATSOME.items():
        print(f"\nScrapeando {nombre_tienda}")
        try:
            if cfg["tipo"] == "playwright":
                productos = await scrape_flatsome_playwright(cfg["url"])
            else:
                productos = scrape_flatsome_requests(cfg["url"])

            print(f" -> {len(productos)} productos")

            for p in productos:
                p["tienda"] = nombre_tienda
                p["fuente"] = "Flatsome"
                p["nombre_normalizado"] = normalizar_nombre(p["nombre"])

            todos.extend(productos)

        except Exception as e:
            print("ERROR:", e)

    # =====================================================
    # PARTE 3: ENEBA
    # =====================================================

    print("\n" + "="*60)
    print("PARTE 3: ENEBA")
    print("="*60)

    BASE_ENEBA = "https://www.eneba.com"

    PAGINAS_ENEBA = [
        ("FreeFire",      "https://www.eneba.com/latam/top-up-free-fire-diamonds-global",               "producto"),
        ("Genshin",       "https://www.eneba.com/latam/top-up-genshin-impact-genesis-crystals-latin-america", "producto"),
        ("Robux",         "https://www.eneba.com/latam/store/all?text=robux",                           "tienda"),
        ("PUBG",          "https://www.eneba.com/latam/store/all?text=pubg+uc",                        "tienda"),
        ("FC Points",     "https://www.eneba.com/latam/store/fc-points",                               "tienda"),
        ("FUT Points",    "https://www.eneba.com/latam/store/game-points-fut",                         "tienda"),
        ("GTA Shark",     "https://www.eneba.com/latam/store/gta-shark-cards",                         "tienda"),
        ("Valorant",      "https://www.eneba.com/latam/store/riot-valorant-points",                    "tienda"),
        ("COD Points",    "https://www.eneba.com/latam/store/cod-points",                              "tienda"),
        ("Fortnite",      "https://www.eneba.com/latam/store/fortnite-v-bucks-gift-cards",             "tienda"),
        ("Xbox",          "https://www.eneba.com/latam/store/xbox-gift-cards",                         "tienda"),
        ("Xbox Points",   "https://www.eneba.com/latam/store/xbox-game-points",                        "tienda"),
        ("Xbox GamePass", "https://www.eneba.com/latam/store/xbox-game-pass",                          "tienda"),
        ("Xbox Games",    "https://www.eneba.com/latam/store/xbox-games",                              "tienda"),
        ("PlayStation",   "https://www.eneba.com/latam/store/psn-games",                               "tienda"),
        ("PSN GiftCards", "https://www.eneba.com/latam/store/psn-gift-cards",                          "tienda"),
        ("PSN Plus",      "https://www.eneba.com/latam/store/psn-subscriptions",                       "tienda"),
        ("Nintendo",      "https://www.eneba.com/latam/store/nintendo-games",                          "tienda"),
        ("Nintendo Gift", "https://www.eneba.com/latam/store/nintendo-gift-cards",                     "tienda"),
        ("Nintendo Subs", "https://www.eneba.com/latam/store/nintendo-subscriptions",                  "tienda"),
        ("Steam",         "https://www.eneba.com/latam/store/steam-games",                             "tienda"),
        ("Steam Wallet",  "https://www.eneba.com/latam/store/steam-gift-cards",                        "tienda"),
        ("EA Play",       "https://www.eneba.com/latam/store/ea-play",                                 "tienda"),
        ("Origin",        "https://www.eneba.com/latam/store/origin-games",                            "tienda"),
        ("Ubisoft",       "https://www.eneba.com/latam/store/uplay-games",                             "tienda"),
        ("Epic Games",    "https://www.eneba.com/latam/store/epic-games",                              "tienda"),
        ("GOG",           "https://www.eneba.com/latam/store/gog-games",                               "tienda"),
        ("BattleNet",     "https://www.eneba.com/latam/store/battle-net-games",                        "tienda"),
        ("BattleNetPts",  "https://www.eneba.com/latam/store/battle-net-game-points",                  "tienda"),
        ("Gift Cards",    "https://www.eneba.com/latam/store/gift-cards",                              "tienda"),
        ("Razer Gold",    "https://www.eneba.com/latam/store/razer-gold-gift-cards",                   "tienda"),
        ("Discord",       "https://www.eneba.com/latam/store/discord-gift-cards",                      "tienda"),
        ("Twitch",        "https://www.eneba.com/latam/store/twitch-gift-cards",                       "tienda"),
        ("Blizzard",      "https://www.eneba.com/latam/store/blizzard-gift-card",                      "tienda"),
    ]

    async def cerrar_popups(page):
        for texto in ["Aceptar todo", "Accept all", "Entendido"]:
            try:
                b = await page.query_selector(f"button:has-text('{texto}')")
                if b:
                    await b.click()
                    await page.wait_for_timeout(1000)
            except:
                pass
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)
        except:
            pass

    vistos_eneba = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        for categoria, url, tipo in PAGINAS_ENEBA:
            print(f"\n{'='*40}")
            print(f"Eneba: {categoria}")

            try:
                page = await browser.new_page(
                    viewport={"width": 1366, "height": 768},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                    locale="es-419",
                    extra_http_headers={"Accept-Language": "es-419,es;q=0.9"}
                )
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(4000)
                await cerrar_popups(page)
                await page.wait_for_timeout(2000)

                for i in range(5):
                    await page.mouse.wheel(0, 5000)
                    await page.wait_for_timeout(1500)

                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                if tipo == "producto":
                    cards = soup.find_all("div", class_="vNgEk7")
                    print(f"Cards: {len(cards)}")
                    for card in cards:
                        try:
                            lineas = [l.strip() for l in card.get_text("\n").split("\n") if l.strip()]
                            nombre = lineas[0] if lineas else ""
                            precio = ""
                            for l in lineas:
                                p = extraer_precio_eneba(l)
                                if p:
                                    precio = p
                                    break
                            if not nombre or not precio:
                                continue
                            clave = (nombre, precio)
                            if clave in vistos_eneba:
                                continue
                            vistos_eneba.add(clave)
                            todos.append({
                                "nombre": nombre,
                                "precio": precio,
                                "link": url,
                                "tienda": f"Eneba - {categoria}",
                                "fuente": "Eneba",
                                "nombre_normalizado": limpiar_nombre_eneba(nombre)
                            })
                            print(f"  {nombre} | {precio}")
                        except:
                            pass

                elif tipo == "tienda":
                    cards = soup.find_all("div", class_="b3POZC")
                    print(f"Cards: {len(cards)}")
                    for card in cards:
                        try:
                            a = card.find("a", href=True)
                            if not a and card.parent:
                                a = card.parent.find("a", href=True)
                            nombre = ""
                            link = url
                            if a:
                                nombre = a.get("title", "").strip()
                                if not nombre:
                                    img = a.find("img")
                                    if img:
                                        nombre = img.get("alt", "").strip()
                                href = a.get("href", "")
                                link = BASE_ENEBA + href if href.startswith("/") else href
                            nombre = limpiar_nombre_eneba(nombre)
                            precio = ""
                            for l in card.get_text("\n").split("\n"):
                                p = extraer_precio_eneba(l.strip())
                                if p:
                                    precio = p
                                    break
                            if not nombre or not precio:
                                continue
                            clave = (nombre, precio)
                            if clave in vistos_eneba:
                                continue
                            vistos_eneba.add(clave)
                            todos.append({
                                "nombre": nombre,
                                "precio": precio,
                                "link": link,
                                "tienda": f"Eneba - {categoria}",
                                "fuente": "Eneba",
                                "nombre_normalizado": limpiar_nombre_eneba(nombre)
                            })
                            print(f"  {nombre} | {precio}")
                        except:
                            pass

                await page.close()

            except Exception as e:
                print(f"ERROR en {categoria}: {e}")

        await browser.close()

    # =====================================================
    # PARTE 4: ARMAR Y EXPORTAR EL EXCEL FINAL
    # =====================================================

    print("\n" + "="*60)
    print("ARMANDO EXCEL FINAL")
    print("="*60)

    df = pd.DataFrame(todos)
    print(f"\nTotal productos antes de filtrar: {len(df)}")

    # Columnas base (por si algún scraper no trajo 'nombre_normalizado')
    if "nombre_normalizado" not in df.columns:
        df["nombre_normalizado"] = df["nombre"].apply(normalizar_nombre)

    # Convertir precio a numérico (Eneba guarda "1.02 USD", el resto float/int)
    def normalizar_precio(p):
        try:
            if isinstance(p, str):
                # Extrae el primer número del string, ej: "1.02 USD" -> 1.02
                match = re.search(r"[\d.,]+", p.replace(",", "."))
                return float(match.group()) if match else None
            return float(p)
        except:
            return None

    df["precio_num"] = df["precio"].apply(normalizar_precio)

    # Ordenar por precio numérico
    df = df.sort_values("precio_num")

    df_final = df[[
        "fuente",
        "tienda",
        "nombre",
        "nombre_normalizado",
        "precio",
        "precio_num",
        "link"
    ]].copy()

    df_final.columns = [
        "Fuente",
        "Tienda",
        "Nombre Original",
        "Nombre Normalizado",
        "Precio Original",
        "Precio (número)",
        "Link"
    ]

    ARCHIVO = "catalogo_completo_abc_gaming.xlsx"
    df_final.to_excel(ARCHIVO, index=False)

    print(f"\nTotal productos exportados: {len(df_final)}")
    print(f"Archivo listo: {ARCHIVO}")


# =========================================================
# EJECUTAR
# =========================================================
if __name__ == "__main__":
    asyncio.run(main())

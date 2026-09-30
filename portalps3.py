import asyncio
import csv
import re
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


# ============================================================
# CONFIGURACIÓN
# ============================================================

URL = "https://portalgames.com.ar/product-category/juegos-ps3/anime/"

HTML_FILE = Path("portalps3_anime_debug.html")
TXT_FILE = Path("portalps3_anime_texto.txt")
CSV_FILE = Path("portalps3_anime.csv")
LOG_FILE = Path("portalps3_anime.log.txt")


# ============================================================
# LOG
# ============================================================

def log(text):
    print(text)

    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(text + "\n")


# ============================================================
# PRECIO
# ============================================================

def parse_price(text):

    if not text:
        return None

    text = text.replace("\xa0", " ")
    text = re.sub(r"[^\d,.]", "", text)

    if not text:
        return None

    # Formato argentino:
    # 17.399,00 -> 17399
    if "," in text:
        text = text.replace(".", "")
        text = text.replace(",", ".")
    else:
        text = text.replace(".", "")

    try:
        value = float(text)

        if value.is_integer():
            return int(value)

        return value

    except ValueError:
        return None


# ============================================================
# EXTRAER PRODUCTOS DEL HTML
# ============================================================

def extract_products(html):

    soup = BeautifulSoup(html, "html.parser")

    products = []
    seen = set()

    # Estructura real de PortalGames / Flatsome / WooCommerce
    links = soup.select(
        "p.name.product-title.woocommerce-loop-product__title a"
    )

    for link in links:

        name = link.get_text(" ", strip=True)
        url = link.get("href", "").strip()

        if not name:
            continue

        if not url:
            continue

        if url in seen:
            continue

        seen.add(url)

        container = link.find_parent(
            class_="product-small"
        )

        if not container:
            continue

        price_tag = container.select_one(
            ".woocommerce-Price-amount"
        )

        category_tag = container.select_one(
            ".product-cat"
        )

        shown_price = ""

        if price_tag:
            shown_price = price_tag.get_text(
                " ",
                strip=True
            )

        category = "Anime"

        if category_tag:
            category = category_tag.get_text(
                " ",
                strip=True
            )

        products.append({

            "fuente": "PortalGames",

            "nombre": name,

            "categoria": category,

            "precio": parse_price(
                shown_price
            ),

            "moneda": "ARS",

            "precio_mostrado": shown_price,

            "url": url

        })

    return products


# ============================================================
# CERRAR POPUPS
# ============================================================

async def close_popups(page):

    textos = [

        "Aceptar todo",

        "Accept all",

        "Aceptar",

        "Cerrar",

        "No"

    ]

    for texto in textos:

        try:

            boton = page.get_by_text(
                texto,
                exact=True
            ).first

            if await boton.count():

                await boton.click(
                    timeout=1500
                )

                await page.wait_for_timeout(
                    1000
                )

        except Exception:
            pass

    try:

        await page.keyboard.press(
            "Escape"
        )

    except Exception:
        pass


# ============================================================
# SCRAPER
# ============================================================

async def main():

    LOG_FILE.write_text(
        "",
        encoding="utf-8"
    )

    log("=" * 60)

    log(
        "PORTALGAMES PS3 - ANIME"
    )

    log(
        "Prueba Playwright basada en sistema antiguo de Colab"
    )

    log("=" * 60)

    log(
        f"URL: {URL}"
    )


    async with async_playwright() as p:

        # ----------------------------------------------------
        # Chromium
        # ----------------------------------------------------

        log(
            "Iniciando Chromium..."
        )

        browser = await p.chromium.launch(

            headless=True,

            args=[

                "--no-sandbox",

                "--disable-dev-shm-usage",

                "--disable-blink-features=AutomationControlled"

            ]

        )


        # ----------------------------------------------------
        # CONTEXTO
        # ----------------------------------------------------

        context = await browser.new_context(

            viewport={
                "width": 1400,
                "height": 900
            },

            user_agent=(
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/124.0.0.0 "
                "Safari/537.36"
            ),

            locale="es-419",

            timezone_id="America/Montevideo",

            java_script_enabled=True

        )


        page = await context.new_page()


        try:

            # ------------------------------------------------
            # ENTRAR
            # ------------------------------------------------

            log(
                "Abriendo PortalGames..."
            )

            try:

                response = await page.goto(

                    URL,

                    wait_until="networkidle",

                    timeout=90000

                )

            except Exception as e:

                log(
                    f"networkidle falló: {e}"
                )

                log(
                    "Intentando domcontentloaded..."
                )

                response = await page.goto(

                    URL,

                    wait_until="domcontentloaded",

                    timeout=60000

                )


            status = (
                response.status
                if response
                else 0
            )

            log(
                f"HTTP inicial: {status}"
            )


            # ------------------------------------------------
            # ESPERA
            # ------------------------------------------------

            log(
                "Esperando JavaScript..."
            )

            await page.wait_for_timeout(
                5000
            )


            # ------------------------------------------------
            # POPUPS
            # ------------------------------------------------

            await close_popups(page)

            await page.wait_for_timeout(
                1000
            )


            # ------------------------------------------------
            # SCROLL
            # ------------------------------------------------

            for i in range(5):

                log(
                    f"Scroll {i + 1}/5"
                )

                await page.mouse.wheel(
                    0,
                    5000
                )

                await page.wait_for_timeout(
                    2000
                )


            # ------------------------------------------------
            # HTML REAL DEL NAVEGADOR
            # ------------------------------------------------

            log(
                "Obteniendo HTML mediante page.content()..."
            )

            html = await page.content()


            # ------------------------------------------------
            # TEXTO VISIBLE
            # ------------------------------------------------

            text = await page.evaluate(
                "() => document.body ? document.body.innerText : ''"
            )


            # ------------------------------------------------
            # GUARDAR HTML
            # ------------------------------------------------

            HTML_FILE.write_text(
                html,
                encoding="utf-8"
            )


            TXT_FILE.write_text(
                text,
                encoding="utf-8"
            )


            log(
                f"HTML guardado: "
                f"{HTML_FILE} "
                f"({len(html)} caracteres)"
            )

            log(
                f"Texto guardado: "
                f"{TXT_FILE} "
                f"({len(text)} caracteres)"
            )


            # ------------------------------------------------
            # DETECTAR CLOUDFLARE
            # ------------------------------------------------

            if (
                "Just a moment" in html
                or
                "cf-chl" in html
                or
                "Enable JavaScript and cookies" in html
                or
                "challenge-platform" in html
            ):

                log(
                    "⚠️ CLOUDFLARE DETECTADO"
                )

            else:

                log(
                    "✅ No se detectó el HTML típico del Challenge"
                )


            # ------------------------------------------------
            # EXTRAER PRODUCTOS
            # ------------------------------------------------

            products = extract_products(
                html
            )


            log(
                f"PRODUCTOS ENCONTRADOS: "
                f"{len(products)}"
            )


            # ------------------------------------------------
            # CSV
            # ------------------------------------------------

            with CSV_FILE.open(

                "w",

                newline="",

                encoding="utf-8-sig"

            ) as f:

                fields = [

                    "fuente",

                    "nombre",

                    "categoria",

                    "precio",

                    "moneda",

                    "precio_mostrado",

                    "url"

                ]


                writer = csv.DictWriter(

                    f,

                    fieldnames=fields

                )


                writer.writeheader()

                writer.writerows(
                    products
                )


            log(
                f"CSV generado: "
                f"{CSV_FILE}"
            )


            # ------------------------------------------------
            # MOSTRAR PRODUCTOS
            # ------------------------------------------------

            for i, product in enumerate(
                products,
                1
            ):

                log(

                    f"{i:02d}. "
                    f"{product['nombre']} | "
                    f"{product['precio_mostrado']} | "
                    f"{product['url']}"

                )


            # ------------------------------------------------
            # DIAGNÓSTICO DE SELECTORES
            # ------------------------------------------------

            soup = BeautifulSoup(
                html,
                "html.parser"
            )


            log("")
            log(
                "--- DIAGNÓSTICO DE CARDS ---"
            )


            selectors = [

                "li.product",

                "div.product",

                ".product-small",

                ".type-product",

                ".products li",

                ".woocommerce-loop-product__title"

            ]


            for selector in selectors:

                count = len(
                    soup.select(
                        selector
                    )
                )

                if count:

                    log(
                        f"{selector} -> "
                        f"{count}"
                    )


            # ------------------------------------------------
            # TEXTO INICIAL
            # ------------------------------------------------

            log("")

            log(
                "--- PRIMEROS 1500 CARACTERES ---"
            )

            log(
                text[:1500]
                .replace(
                    "\n",
                    " | "
                )
            )


        except Exception as e:

            log(
                f"ERROR GENERAL: "
                f"{type(e).__name__}: {e}"
            )


        finally:

            await browser.close()


# ============================================================
# EJECUTAR
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
        )

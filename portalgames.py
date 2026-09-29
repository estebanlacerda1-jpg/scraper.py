import csv
import os
import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

import requests

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


# ============================================================
# CONFIGURACIÓN
# ============================================================

FUENTE = "PortalGames"

CATEGORIAS = {
    "PortalGames PS3": "https://portalgames.com.ar/product-category/juegos-ps3/"
}

CSV_SALIDA = "catalogo_cuarentena/portalgames_ps3.csv"
LOG_SALIDA = "catalogo_cuarentena/portalgames_ps3.log.txt"

PAUSA = 1.0


# ============================================================
# VARIABLES PLAYWRIGHT
# ============================================================

_playwright = None
_browser = None
_context = None
_page = None


# ============================================================
# LOG
# ============================================================

log_lines = []


def log(texto):
    print(texto)
    log_lines.append(texto)


# ============================================================
# PRECIO
# ============================================================

def parsear_precio(texto):
    """
    Convierte precios argentinos:

    $ 12.999       -> 12999.0
    $ 12.999,50    -> 12999.50
    $ 9990         -> 9990.0
    $ 999,50       -> 999.50
    """

    if not texto:
        return None

    texto = texto.strip()

    # Dejamos solamente números, puntos y comas
    texto = re.sub(r"[^\d.,]", "", texto)

    if not texto:
        return None

    # Ejemplo: 12.999,50
    if "." in texto and "," in texto:
        texto = texto.replace(".", "")
        texto = texto.replace(",", ".")

    # Ejemplo: 12.999
    elif "." in texto:
        partes = texto.split(".")

        if len(partes[-1]) == 3:
            # Punto como separador de miles
            texto = texto.replace(".", "")
        else:
            # Punto decimal
            texto = texto.replace(",", ".")

    # Ejemplo: 999,50
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return float(texto)

    except ValueError:
        return None


# ============================================================
# DETECTAR CLOUDFLARE
# ============================================================

def es_cloudflare(html):

    if not html:
        return False

    marcas = [
        "Just a moment...",
        "cf-chl-",
        "challenge-platform",
        "Enable JavaScript and cookies to continue",
    ]

    html_lower = html.lower()

    for marca in marcas:
        if marca.lower() in html_lower:
            return True

    return False


# ============================================================
# INICIAR PLAYWRIGHT
# ============================================================

def iniciar_navegador():

    global _playwright
    global _browser
    global _context
    global _page

    if _page is not None:
        return

    if sync_playwright is None:
        raise RuntimeError(
            "Playwright no está instalado."
        )

    log("🌐 Iniciando Chromium con Playwright...")

    _playwright = sync_playwright().start()

    _browser = _playwright.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )

    _context = _browser.new_context(
        viewport={
            "width": 1366,
            "height": 768,
        },
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        ),
        locale="es-AR",
        timezone_id="America/Argentina/Buenos_Aires",
        java_script_enabled=True,
    )

    _page = _context.new_page()

    _page.set_default_timeout(60000)


# ============================================================
# CERRAR PLAYWRIGHT
# ============================================================

def cerrar_navegador():

    global _playwright
    global _browser
    global _context
    global _page

    try:
        if _page:
            _page.close()
    except Exception:
        pass

    try:
        if _context:
            _context.close()
    except Exception:
        pass

    try:
        if _browser:
            _browser.close()
    except Exception:
        pass

    try:
        if _playwright:
            _playwright.stop()
    except Exception:
        pass

    _playwright = None
    _browser = None
    _context = None
    _page = None


# ============================================================
# DESCARGAR PÁGINA
# ============================================================

def descargar(url):

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        "Referer": "https://portalgames.com.ar/",
        "Connection": "keep-alive",
    }

    # ========================================================
    # 1. INTENTAR CURL_CFFI
    # ========================================================

    if curl_requests:

        try:

            r = curl_requests.get(
                url,
                headers=headers,
                impersonate="chrome",
                timeout=30,
            )

            html = r.text

            if (
                r.status_code == 200
                and (
                    "product-small" in html
                    or "woocommerce-loop-product__title" in html
                    or "woocommerce-LoopProduct-link" in html
                )
            ):

                log(
                    "   ✅ curl_cffi obtuvo HTML real"
                )

                return r.status_code, html

            log(
                f"   ⚠️ curl_cffi respondió HTTP {r.status_code}"
            )

            log(
                "   🔄 Intentando con Playwright..."
            )

        except Exception as e:

            log(
                f"   ⚠️ curl_cffi error: {e}"
            )

            log(
                "   🔄 Intentando con Playwright..."
            )

    # ========================================================
    # 2. PLAYWRIGHT
    # ========================================================

    try:

        iniciar_navegador()

        log(
            "   🌐 Abriendo página con Chromium..."
        )

        response = _page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        if response:
            status = response.status
        else:
            status = 0

        log(
            f"   🌐 Playwright HTTP: {status}"
        )

        # Esperar a que Cloudflare procese JavaScript
        time.sleep(5)

        html = _page.content()

        # Si todavía aparece Cloudflare
        if es_cloudflare(html):

            log(
                "   ⏳ Cloudflare todavía presente..."
            )

            time.sleep(8)

            html = _page.content()

        # ====================================================
        # COMPROBAR SI OBTUVIMOS PRODUCTOS
        # ====================================================

        if (
            "product-small" in html
            or "woocommerce-loop-product__title" in html
            or "woocommerce-LoopProduct-link" in html
        ):

            log(
                "   ✅ Playwright obtuvo HTML real de PortalGames"
            )

            return 200, html

        log(
            "   ❌ Playwright no obtuvo la página de productos"
        )

        return status, html

    except Exception as e:

        log(
            f"   ❌ Error de Playwright: {e}"
        )

        return 0, ""


# ============================================================
# EXTRAER PRODUCTOS
# ============================================================

def extraer_productos(html, categoria, pagina):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    productos = []

    # ========================================================
    # CONTENEDORES DE PRODUCTOS
    # ========================================================

    containers = soup.select(
        ".product-small"
    )

    if not containers:

        containers = soup.select(
            "li.product"
        )

    if not containers:

        containers = soup.select(
            ".product.type-product"
        )

    # ========================================================
    # PRODUCTOS
    # ========================================================

    for producto in containers:

        # ----------------------------------------------------
        # NOMBRE
        # ----------------------------------------------------

        nombre_el = producto.select_one(
            ".product-title a"
        )

        if not nombre_el:

            nombre_el = producto.select_one(
                ".woocommerce-loop-product__title"
            )

        if not nombre_el:

            nombre_el = producto.select_one(
                ".woocommerce-loop-product__title a"
            )

        if not nombre_el:
            continue

        nombre = nombre_el.get_text(
            " ",
            strip=True
        )

        if not nombre:
            continue

        # ----------------------------------------------------
        # URL
        # ----------------------------------------------------

        enlace = producto.select_one(
            "a.woocommerce-LoopProduct-link"
        )

        if not enlace:

            enlace = producto.select_one(
                'a[href*="/producto/"]'
            )

        if not enlace:

            if nombre_el.name == "a":
                enlace = nombre_el

        if not enlace:
            continue

        url = enlace.get(
            "href",
            ""
        ).strip()

        if not url:
            continue

        url = urljoin(
            "https://portalgames.com.ar/",
            url
        )

        # ----------------------------------------------------
        # PRECIO
        # ----------------------------------------------------

        precio_el = producto.select_one(
            ".woocommerce-Price-amount"
        )

        if not precio_el:

            precio_el = producto.select_one(
                ".price"
            )

        if not precio_el:
            continue

        precio_mostrado = precio_el.get_text(
            " ",
            strip=True
        )

        precio = parsear_precio(
            precio_mostrado
        )

        if precio is None:
            continue

        # ----------------------------------------------------
        # MONEDA
        # ----------------------------------------------------

        moneda_el = producto.select_one(
            ".woocommerce-Price-currencySymbol"
        )

        if moneda_el:

            moneda = moneda_el.get_text(
                " ",
                strip=True
            )

        else:

            moneda = "$"

        # ----------------------------------------------------
        # GUARDAR
        # ----------------------------------------------------

        productos.append({
            "fuente": FUENTE,
            "nombre": nombre,
            "categoria": categoria,
            "precio": precio,
            "precio_mostrado": precio_mostrado,
            "moneda": moneda,
            "url": url,
            "pagina": pagina,
        })

    return productos


# ============================================================
# SCRAPEAR CATEGORÍA
# ============================================================

def scrapear_categoria(
    categoria,
    url_base
):

    todos = []

    urls_vistas = set()

    pagina = 1

    while True:

        # ====================================================
        # URL
        # ====================================================

        if pagina == 1:

            url = url_base

        else:

            url = (
                url_base.rstrip("/")
                + f"/page/{pagina}/"
            )

        log("")
        log(
            f"📄 {categoria} - Página {pagina}"
        )

        log(
            f"   URL: {url}"
        )

        # ====================================================
        # DESCARGAR
        # ====================================================

        status, html = descargar(
            url
        )

        log(
            f"   HTTP: {status}"
        )

        # ====================================================
        # 403 / 404
        # ====================================================

        if status in (403, 404):

            if pagina > 1:

                log(
                    f"   🛑 HTTP {status} en página "
                    f"{pagina}: fin de paginación."
                )

                break

            else:

                log(
                    f"   ❌ HTTP {status} en página 1: "
                    "error real."
                )

                break

        # ====================================================
        # OTROS ERRORES
        # ====================================================

        if status != 200:

            log(
                f"   ❌ HTTP inesperado: {status}"
            )

            break

        # ====================================================
        # CLOUDFLARE
        # ====================================================

        if es_cloudflare(html):

            log(
                "   ❌ Cloudflare sigue bloqueando "
                "la página."
            )

            break

        # ====================================================
        # EXTRAER PRODUCTOS
        # ====================================================

        productos = extraer_productos(
            html,
            categoria,
            pagina
        )

        log(
            f"   🛒 Productos encontrados: "
           

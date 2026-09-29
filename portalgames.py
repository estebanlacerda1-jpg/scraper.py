import csv
import os
import re
import time
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

import requests


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
    Convierte formatos argentinos:

    $ 12.999       -> 12999.0
    $ 12.999,50    -> 12999.50
    $ 9990         -> 9990.0
    """

    if not texto:
        return None

    texto = texto.strip()

    # Dejar solamente números, punto y coma
    texto = re.sub(r"[^\d.,]", "", texto)

    if not texto:
        return None

    # Formato argentino:
    # 12.999,50
    if "." in texto and "," in texto:
        texto = texto.replace(".", "")
        texto = texto.replace(",", ".")

    # 12.999
    elif "." in texto:
        partes = texto.split(".")

        # Si son exactamente 3 dígitos después del punto,
        # normalmente es separador de miles.
        if len(partes[-1]) == 3:
            texto = texto.replace(".", "")
        else:
            texto = texto.replace(",", ".")

    # 12,50
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return None


# ============================================================
# PLAYWRIGHT
# ============================================================

_playwright = None
_browser = None
_context = None
_page = None


def iniciar_navegador():
    global _playwright, _browser, _context, _page

    if _page is not None:
        return

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
            "height": 768
        },
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        },
        locale="es-AR",
        timezone_id="America/Argentina/Buenos_Aires",
        java_script_enabled=True,
    )

    _page = _context.new_page()

    _page.set_default_timeout(60000)


def cerrar_navegador():
    global _playwright, _browser, _context, _page

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
# DESCARGA
# ============================================================

def descargar(url):

    # --------------------------------------------------------
    # PRIMERO: curl_cffi
    # --------------------------------------------------------

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

    if curl_requests:

        try:

            r = curl_requests.get(
                url,
                headers=headers,
                impersonate="chrome",
                timeout=30,
            )

            html = r.text

            # Si funciona, usamos directamente el HTML
            if (
                r.status_code == 200
                and (
                    "product-small" in html
                    or "woocommerce-loop-product__title" in html
                )
            ):
                log("   ✅ curl_cffi obtuvo HTML real")
                return r.status_code, html

            # Si da 403/Cloudflare, pasamos a Playwright
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

    # --------------------------------------------------------
    # SEGUNDO: PLAYWRIGHT
    # --------------------------------------------------------

    try:

        iniciar_navegador()

        log("   🌐 Abriendo página con Chromium...")

        response = _page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        status = response.status if response else 0

        log(
            f"   🌐 Playwright HTTP: {status}"
        )

        # Esperamos a que Cloudflare termine la comprobación
        time.sleep(5)

        html = _page.content()

        # Si todavía estamos en Cloudflare
        if es_cloudflare(html):

            log(
                "   ⏳ Cloudflare todavía presente, esperando..."
            )

            time.sleep(8)

            html = _page.content()

        # Verificar si finalmente obtuvimos productos
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

    # --------------------------------------------------------
    # 1) curl_cffi / Chrome impersonation
    # --------------------------------------------------------

    if curl_requests:
        try:
            r = curl_requests.get(
                url,
                headers=headers,
                impersonate="chrome",
                timeout=30,
            )

            html = r.text

            # Si tenemos una página real de WooCommerce,
            # la usamos.
            if (
                r.status_code == 200
                and (
                    "product-small" in html
                    or "woocommerce-loop-product__title" in html
                )
            ):
                return r.status_code, html

            # Si devuelve Cloudflare, igualmente devolvemos
            # la respuesta para que quede registrado.
            return r.status_code, html

        except Exception as e:
            log(f"  ⚠️ curl_cffi error: {e}")

    # --------------------------------------------------------
    # 2) requests normal
    # --------------------------------------------------------

    try:
        r = requests.get(
            url,
            headers=headers,
            timeout=30,
        )

        return r.status_code, r.text

    except Exception as e:
        log(f"  ❌ requests error: {e}")
        return 0, ""


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
        "Cloudflare",
        "Enable JavaScript and cookies to continue",
    ]

    html_lower = html.lower()

    return any(m.lower() in html_lower for m in marcas)


# ============================================================
# EXTRAER PRODUCTOS
# ============================================================

def extraer_productos(html, categoria, pagina):

    soup = BeautifulSoup(html, "html.parser")

    productos = []

    # PortalGames usa WooCommerce/Flatsome.
    # Intentamos primero el contenedor típico de Flatsome.
    containers = soup.select(".product-small")

    # Fallback WooCommerce estándar.
    if not containers:
        containers = soup.select("li.product")

    if not containers:
        containers = soup.select(".product.type-product")

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

        nombre = nombre_el.get_text(" ", strip=True)

        if not nombre:
            continue

        # ----------------------------------------------------
        # URL
        # ----------------------------------------------------

        enlace = producto.select_one(
            'a.woocommerce-LoopProduct-link'
        )

        if not enlace:
            enlace = producto.select_one(
                'a[href*="/producto/"]'
            )

        if not enlace:
            enlace = nombre_el if nombre_el.name == "a" else None

        if not enlace:
            continue

        url = enlace.get("href", "").strip()

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

        precio = parsear_precio(precio_mostrado)

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
                strip=True
            )
        else:
            # PortalGames muestra normalmente $
            moneda = "$"

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
# SCRAPER DE CATEGORÍA
# ============================================================

def scrapear_categoria(categoria, url_base):

    todos = []
    urls_vistas = set()

    pagina = 1

    while True:

        if pagina == 1:
            url = url_base
        else:
            url = url_base.rstrip("/") + f"/page/{pagina}/"

        log("")
        log(f"📄 {categoria} - Página {pagina}")
        log(f"   URL: {url}")

        status, html = descargar(url)

        log(f"   HTTP: {status}")

        # ----------------------------------------------------
        # 403 / 404
        # ----------------------------------------------------

        if status in (403, 404):

            if pagina > 1:
                log(
                    f"   🛑 HTTP {status} en página {pagina}: "
                    "fin de paginación."
                )
                break

            else:
                log(
                    f"   ❌ HTTP {status} en página 1: "
                    "error real."
                )
                break

        # ----------------------------------------------------
        # Otros errores
        # ----------------------------------------------------

        if status != 200:
            log(
                f"   ❌ HTTP inesperado: {status}"
            )
            break

        # ----------------------------------------------------
        # Cloudflare
        # ----------------------------------------------------

        if es_cloudflare(html):

            log(
                "   ❌ Cloudflare detectado. "
                "La descarga automática no obtuvo "
                "el HTML de productos."
            )

            break

        # ----------------------------------------------------
        # Productos
        # ----------------------------------------------------

        productos = extraer_productos(
            html,
            categoria,
            pagina
        )

        log(
            f"   🛒 Productos encontrados: "
            f"{len(productos)}"
        )

        if not productos:
            log(
                "   🛑 Página sin productos. "
                "Fin de paginación."
            )
            break

        nuevos = 0

        for producto in productos:

            if producto["url"] in urls_vistas:
                continue

            urls_vistas.add(producto["url"])
            todos.append(producto)
            nuevos += 1

        log(
            f"   ➕ Productos nuevos: {nuevos}"
        )

        # Si la página existe pero todos los productos
        # estaban repetidos, probablemente llegamos al final.
        if nuevos == 0:
            log(
                "   🛑 No aparecieron productos nuevos."
            )
            break

        # ----------------------------------------------------
        # Verificar si existe siguiente página
        # ----------------------------------------------------

        soup = BeautifulSoup(html, "html.parser")

        siguiente = soup.select_one(
            "a.next.page-numbers"
        )

        if not siguiente:
            siguiente = soup.select_one(
                "a.page-numbers[aria-label*='Página']"
            )

        # El canonical/next de WooCommerce es más confiable
        # cuando existe.
        link_next = soup.find(
            "link",
            rel="next"
        )

        if not siguiente and not link_next:
            log(
                "   ✅ No se detectó siguiente página."
            )
            break

        pagina += 1

        time.sleep(PAUSA)

    return todos


# ============================================================
# MAIN
# ============================================================

def main():

    os.makedirs(
        os.path.dirname(CSV_SALIDA),
        exist_ok=True
    )

    log("==============================================")
    log("PORTALGAMES - CUARENTENA PS3")
    log("==============================================")

    todos = []

    for categoria, url in CATEGORIAS.items():

        log("")
        log("==============================================")
        log(f"🎮 {categoria}")
        log("==============================================")

        productos = scrapear_categoria(
            categoria,
            url
        )

        todos.extend(productos)

        log("")
        log(
            f"✅ {categoria}: "
            f"{len(productos)} productos"
        )

    # ========================================================
    # CSV
    # ========================================================

    campos = [
        "fuente",
        "nombre",
        "categoria",
        "precio",
        "precio_mostrado",
        "moneda",
        "url",
        "pagina",
    ]

    with open(
        CSV_SALIDA,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=campos
        )

        writer.writeheader()

        for producto in todos:
            writer.writerow(producto)

    # ========================================================
    # LOG
    # ========================================================

    log("")
    log("==============================================")
    log(f"TOTAL PRODUCTOS: {len(todos)}")
    log("==============================================")

    with open(
        LOG_SALIDA,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "\n".join(log_lines)
        )

    print("")
    print("==============================================")
    print("✅ SCRAPER FINALIZADO")
    print(f"CSV: {CSV_SALIDA}")
    print(f"LOG: {LOG_SALIDA}")
    print(f"TOTAL: {len(todos)}")
    print("==============================================")


if __name__ == "__main__":
    main()

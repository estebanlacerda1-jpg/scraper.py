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

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


# ============================================================
# CONFIGURACION
# ============================================================

FUENTE = "PortalGames"

CATEGORIAS = {
    "PortalGames PS3": "https://portalgames.com.ar/product-category/juegos-ps3/"
}

CSV_SALIDA = "catalogo_cuarentena/portalgames_ps3.csv"
LOG_SALIDA = "catalogo_cuarentena/portalgames_ps3.log.txt"

PAUSA = 1.0


# ============================================================
# VARIABLES
# ============================================================

log_lines = []

playwright_instance = None
browser = None
context = None
page = None


# ============================================================
# LOG
# ============================================================

def log(texto):
    print(texto)
    log_lines.append(texto)


# ============================================================
# PRECIO
# ============================================================

def parsear_precio(texto):
    if not texto:
        return None

    texto = re.sub(r"[^\d.,]", "", texto)

    if not texto:
        return None

    # 12.999,50
    if "." in texto and "," in texto:
        texto = texto.replace(".", "")
        texto = texto.replace(",", ".")

    # 12.999
    elif "." in texto:
        partes = texto.split(".")

        if len(partes[-1]) == 3:
            texto = texto.replace(".", "")

    # 12,50
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return None


# ============================================================
# CLOUDFLARE
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

def iniciar_playwright():
    global playwright_instance
    global browser
    global context
    global page

    if page is not None:
        return

    if sync_playwright is None:
        raise RuntimeError("Playwright no esta instalado.")

    log("🌐 Iniciando Chromium...")

    playwright_instance = sync_playwright().start()

    browser = playwright_instance.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    )

    context = browser.new_context(
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

    page = context.new_page()
    page.set_default_timeout(60000)


# ============================================================
# CERRAR PLAYWRIGHT
# ============================================================

def cerrar_playwright():
    global playwright_instance
    global browser
    global context
    global page

    try:
        if page:
            page.close()
    except Exception:
        pass

    try:
        if context:
            context.close()
    except Exception:
        pass

    try:
        if browser:
            browser.close()
    except Exception:
        pass

    try:
        if playwright_instance:
            playwright_instance.stop()
    except Exception:
        pass

    playwright_instance = None
    browser = None
    context = None
    page = None


# ============================================================
# DESCARGAR CON PLAYWRIGHT
# ============================================================

def descargar_playwright(url):
    iniciar_playwright()

    log("   🌐 Abriendo con Chromium...")

    respuesta = page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    if respuesta:
        status = respuesta.status
    else:
        status = 0

    log(f"   🌐 Playwright HTTP: {status}")

    time.sleep(5)

    html = page.content()

    if es_cloudflare(html):
        log("   ⏳ Cloudflare detectado, esperando...")
        time.sleep(10)
        html = page.content()

    if (
        "product-small" in html
        or "woocommerce-loop-product__title" in html
        or "woocommerce-LoopProduct-link" in html
    ):
        log("   ✅ Playwright obtuvo HTML real")
        return 200, html

    log("   ❌ Playwright no obtuvo los productos")
    return status, html


# ============================================================
# DESCARGAR PAGINA
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
    }

    # Primer intento: curl_cffi
    if curl_requests:
        try:
            respuesta = curl_requests.get(
                url,
                headers=headers,
                impersonate="chrome",
                timeout=30,
            )

            html = respuesta.text

            if (
                respuesta.status_code == 200
                and not es_cloudflare(html)
                and (
                    "product-small" in html
                    or "woocommerce-loop-product__title" in html
                    or "woocommerce-LoopProduct-link" in html
                )
            ):
                log("   ✅ curl_cffi obtuvo HTML real")
                return 200, html

            log(f"   ⚠️ curl_cffi HTTP {respuesta.status_code}")

        except Exception as error:
            log(f"   ⚠️ curl_cffi error: {error}")

    # Segundo intento: Playwright
    try:
        return descargar_playwright(url)
    except Exception as error:
        log(f"   ❌ Error Playwright: {error}")
        return 0, ""


# ============================================================
# EXTRAER PRODUCTOS
# ============================================================

def extraer_productos(html, categoria, pagina):
    soup = BeautifulSoup(html, "html.parser")

    containers = soup.select(".product-small")

    if not containers:
        containers = soup.select("li.product")

    if not containers:
        containers = soup.select(".product.type-product")

    productos = []

    for producto in containers:

        # Nombre
        nombre_el = producto.select_one(".product-title a")

        if not nombre_el:
            nombre_el = producto.select_one(
                ".woocommerce-loop-product__title a"
            )

        if not nombre_el:
            nombre_el = producto.select_one(
                ".woocommerce-loop-product__title"
            )

        if not nombre_el:
            continue

        nombre = nombre_el.get_text(" ", strip=True)

        if not nombre:
            continue

        # URL
        enlace = producto.select_one(
            "a.woocommerce-LoopProduct-link"
        )

        if not enlace:
            enlace = producto.select_one(
                'a[href*="/producto/"]'
            )

        if not enlace and nombre_el.name == "a":
            enlace = nombre_el

        if not enlace:
            continue

        url_producto = enlace.get("href", "").strip()

        if not url_producto:
            continue

        url_producto = urljoin(
            "https://portalgames.com.ar/",
            url_producto,
        )

        # Precio
        precio_el = producto.select_one(
            ".woocommerce-Price-amount"
        )

        if not precio_el:
            precio_el = producto.select_one(".price")

        if not precio_el:
            continue

        precio_mostrado = precio_el.get_text(
            " ",
            strip=True,
        )

        precio = parsear_precio(precio_mostrado)

        if precio is None:
            continue

        # Moneda
        moneda_el = producto.select_one(
            ".woocommerce-Price-currencySymbol"
        )

        if moneda_el:
            moneda = moneda_el.get_text(
                " ",
                strip=True,
            )
        else:
            moneda = "$"

        productos.append(
            {
                "fuente": FUENTE,
                "nombre": nombre,
                "categoria": categoria,
                "precio": precio,
                "precio_mostrado": precio_mostrado,
                "moneda": moneda,
                "url": url_producto,
                "pagina": pagina,
            }
        )

    return productos


# ============================================================
# SCRAPEAR CATEGORIA
# ============================================================

def scrapear_categoria(categoria, url_base):
    todos = []
    urls_vistas = set()
    pagina = 1

    while True:

        if pagina == 1:
            url = url_base
        else:
            url = (
                url_base.rstrip("/")
                + f"/page/{pagina}/"
            )

        log("")
        log(f"📄 {categoria} - Página {pagina}")
        log(f"   URL: {url}")

        status, html = descargar(url)

        log(f"   HTTP: {status}")

        # 403 / 404
        if status in (403, 404):
            if pagina > 1:
                log(
                    f"   🛑 HTTP {status} en página "
                    f"{pagina}: fin de paginación."
                )
            else:
                log(
                    f"   ❌ HTTP {status} en página 1: "
                    "error real."
                )
            break

        # Otros errores
        if status != 200:
            log(f"   ❌ HTTP inesperado: {status}")
            break

        # Cloudflare
        if es_cloudflare(html):
            log("   ❌ Cloudflare sigue bloqueando.")
            break

        # Extraer
        productos = extraer_productos(
            html,
            categoria,
            pagina,
        )

        log(
            f"   🛒 Productos encontrados: "
            f"{len(productos)}"
        )

        if not productos:
            log("   🛑 Página sin productos. Fin.")
            break

        # Deduplicar
        nuevos = 0

        for producto in productos:
            url_producto = producto["url"]

            if url_producto in urls_vistas:
                continue

            urls_vistas.add(url_producto)
            todos.append(producto)
            nuevos += 1

        log(f"   ➕ Productos nuevos: {nuevos}")

        if nuevos == 0:
            log("   🛑 No aparecieron productos nuevos.")
            break

        pagina += 1

        time.sleep(PAUSA)

    return todos


# ============================================================
# MAIN
# ============================================================

def main():
    os.makedirs(
        "catalogo_cuarentena",
        exist_ok=True,
    )

    log("==============================================")
    log("PORTALGAMES - CUARENTENA PS3")
    log("==============================================")

    todos = []

    try:
        for categoria, url in CATEGORIAS.items():

            log("")
            log("==============================================")
            log(f"🎮 {categoria}")
            log("==============================================")

            productos = scrapear_categoria(
                categoria,
                url,
            )

            todos.extend(productos)

            log("")
            log(
                f"✅ {categoria}: "
                f"{len(productos)} productos"
            )

    finally:
        cerrar_playwright()

    # CSV
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
        encoding="utf-8-sig",
    ) as archivo:

        writer = csv.DictWriter(
            archivo,
            fieldnames=campos,
        )

        writer.writeheader()
        writer.writerows(todos)

    # Total
    log("")
    log("==============================================")
    log(f"TOTAL PRODUCTOS: {len(todos)}")
    log("==============================================")

    # Log
    with open(
        LOG_SALIDA,
        "w",
        encoding="utf-8",
    ) as archivo:

        archivo.write(
            "\n".join(log_lines)
        )

    print("")
    print("==============================================")
    print("✅ SCRAPER FINALIZADO")
    print(f"CSV: {CSV_SALIDA}")
    print(f"LOG: {LOG_SALIDA}")
    print(f"TOTAL: {len(todos)}")
    print("==============================================")


# ============================================================
# EJECUTAR
# ============================================================

if __name__ == "__main__":
    main()

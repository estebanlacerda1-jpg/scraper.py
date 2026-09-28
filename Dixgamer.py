import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests


# ============================================================
# DIXGAMER - SCRAPER GENERAL DE CUARENTENA
# ============================================================

CATEGORIAS = {
    "Dix FC Points":
        "https://dixgamer.com/categoria-producto/tarjetas/fc-points/",

    "Dix Fortnite":
        "https://dixgamer.com/categoria-producto/tarjetas/fortnite/",

    "Dix Nintendo":
        "https://dixgamer.com/categoria-producto/tarjetas/nintendo/",

    "Dix PS3":
        "https://dixgamer.com/categoria-producto/juegos/ps3/",

    "Dix PS4":
        "https://dixgamer.com/categoria-producto/juegos/ps4/",

    "Dix PS5":
        "https://dixgamer.com/categoria-producto/juegos/ps5/",

    "Dix Playstation":
        "https://dixgamer.com/categoria-producto/tarjetas/ps/",

    "Dix Razer":
        "https://dixgamer.com/categoria-producto/tarjetas/razer-gold/",

    "Dix Steam":
        "https://dixgamer.com/categoria-producto/tarjetas/steam/",

    "Dix Xbox":
        "https://dixgamer.com/categoria-producto/tarjetas/xbox/",
}


OUTPUT_DIR = Path("catalogo_cuarentena")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

JSON_PATH = OUTPUT_DIR / "dixgamer.json"
LOG_PATH = OUTPUT_DIR / "dixgamer.log.txt"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": "https://dixgamer.com/",
}


# ============================================================
# LOG
# ============================================================

def log(text):

    print(text)

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(text + "\n")


# ============================================================
# OBTENER HTML
# ============================================================

def obtener_html(url):

    # --------------------------------------------------------
    # 1. curl_cffi simulando Chrome
    # --------------------------------------------------------

    try:

        r = curl_requests.get(
            url,
            headers=HEADERS,
            impersonate="chrome",
            timeout=40,
        )

        if r.status_code == 200 and len(r.text) > 5000:
            return r.text, r.status_code

        log(
            f"   curl_cffi HTTP {r.status_code}"
        )

    except Exception as e:

        log(
            f"   curl_cffi ERROR: {e}"
        )

    # --------------------------------------------------------
    # 2. requests normal
    # --------------------------------------------------------

    try:

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=40,
        )

        return r.text, r.status_code

    except Exception as e:

        log(
            f"   requests ERROR: {e}"
        )

        return "", 0


# ============================================================
# PRECIO
# ============================================================

def extraer_precio(texto):

    if not texto:
        return None

    texto = texto.replace("\xa0", " ")
    texto = texto.strip()

    # Buscar el primer número
    match = re.search(
        r"\d[\d.,]*",
        texto
    )

    if not match:
        return None

    numero = match.group(0)

    # --------------------------------------------------------
    # Detectar separadores
    #
    # 20.603  -> 20603
    # 20,603  -> 20603
    # 34.90   -> 34.90
    # 189,75  -> 189.75
    # 1.234,56 -> 1234.56
    # --------------------------------------------------------

    if "," in numero and "." in numero:

        ultimo_punto = numero.rfind(".")
        ultima_coma = numero.rfind(",")

        if ultima_coma > ultimo_punto:

            numero = numero.replace(".", "")
            numero = numero.replace(",", ".")

        else:

            numero = numero.replace(",", "")

    elif "," in numero:

        parte_final = numero.split(",")[-1]

        if len(parte_final) == 2:

            numero = numero.replace(".", "")
            numero = numero.replace(",", ".")

        else:

            numero = numero.replace(",", "")

    elif "." in numero:

        partes = numero.split(".")

        if len(partes[-1]) == 2:

            # Decimal:
            # 34.90
            numero = numero.replace(",", "")

        else:

            # Miles:
            # 20.603
            numero = numero.replace(".", "")

    try:

        valor = float(numero)

    except ValueError:

        return None

    if valor <= 0:
        return None

    return valor


# ============================================================
# DETECTAR MONEDA
# ============================================================

def detectar_moneda(texto):

    if not texto:
        return ""

    texto = texto.upper()

    monedas = [
        "ARS",
        "BRL",
        "COP",
        "USD",
        "UYU",
        "EUR",
        "CLP",
        "MXN",
        "PEN",
    ]

    for moneda in monedas:

        if moneda in texto:
            return moneda

    return ""


# ============================================================
# EXTRAER PRODUCTOS
# ============================================================

def extraer_productos(
    html,
    categoria,
    pagina
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    cards = soup.select(
        "li.product"
    )

    if not cards:

        cards = soup.select(
            "ul.products li.product"
        )

    productos = []

    for card in cards:

        try:

            # ------------------------------------------------
            # NOMBRE
            # ------------------------------------------------

            nombre_el = card.select_one(
                ".woocommerce-loop-product__title"
            )

            if not nombre_el:

                nombre_el = card.select_one(
                    ".product-title"
                )

            if not nombre_el:
                continue

            nombre = nombre_el.get_text(
                " ",
                strip=True
            )

            # ------------------------------------------------
            # PRECIO
            # ------------------------------------------------

            precio_el = card.select_one(
                ".price"
            )

            if not precio_el:
                continue

            precio_original = precio_el.get_text(
                " ",
                strip=True
            )

            precio = extraer_precio(
                precio_original
            )

            if precio is None:
                continue

            moneda = detectar_moneda(
                precio_original
            )

            # ------------------------------------------------
            # LINK
            # ------------------------------------------------

            link = ""

            link_el = card.select_one(
                "a[href]"
            )

            if link_el:

                link = link_el.get(
                    "href",
                    ""
                )

            # ------------------------------------------------
            # IMAGEN
            # ------------------------------------------------

            imagen = ""

            imagen_el = card.select_one(
                "img"
            )

            if imagen_el:

                imagen = (
                    imagen_el.get("data-src")
                    or imagen_el.get("data-lazy-src")
                    or imagen_el.get("src")
                    or ""
                )

            # ------------------------------------------------
            # PRODUCTO
            # ------------------------------------------------

            productos.append({

                "nombre": nombre,

                "precio_original":
                    precio_original,

                "precio":
                    precio,

                "moneda":
                    moneda,

                "precio_uyu":
                    None,

                "link":
                    link,

                "imagen":
                    imagen,

                "categoria":
                    categoria,

                "pagina":
                    pagina,
            })

        except Exception:

            continue

    return productos


# ============================================================
# SCRAPEAR CATEGORÍA
# ============================================================

def scrapear_categoria(
    categoria,
    base_url
):

    log("")
    log("=" * 60)
    log(categoria)
    log("=" * 60)

    todos = []

    vistos = set()

    pagina = 1

    while True:

        # ----------------------------------------------------
        # URL
        # ----------------------------------------------------

        if pagina == 1:

            url = base_url

        else:

            url = (
                f"{base_url.rstrip('/')}"
                f"/page/{pagina}/"
            )

        log("")
        log(
            f"[{categoria}] Página {pagina}"
        )

        log(url)

        # ----------------------------------------------------
        # HTML
        # ----------------------------------------------------

        html, status = obtener_html(
            url
        )

        log(
            f"HTTP: {status}"
        )

        log(
            f"HTML: {len(html)} bytes"
        )

        # ----------------------------------------------------
        # PRIMERA PÁGINA
        # ----------------------------------------------------

        if pagina == 1:

            if status in (403, 404):

                log(
                    f"ERROR CRÍTICO: "
                    f"página inicial HTTP {status}"
                )

                return todos, False

            if status != 200:

                log(
                    f"ERROR CRÍTICO: "
                    f"página inicial HTTP {status}"
                )

                return todos, False

        # ----------------------------------------------------
        # PÁGINAS SIGUIENTES
        # ----------------------------------------------------

        else:

            if status in (403, 404):

                log(
                    f"HTTP {status} en página "
                    f"{pagina}: fin de paginación."
                )

                break

            if status != 200:

                log(
                    f"ERROR HTTP {status} "
                    f"en página {pagina}"
                )

                break

        # ----------------------------------------------------
        # EXTRAER
        # ----------------------------------------------------

        productos = extraer_productos(
            html,
            categoria,
            pagina
        )

        log(
            f"Productos encontrados: "
            f"{len(productos)}"
        )

        # Página válida pero sin productos
        if not productos:

            log(
                "Página sin productos: "
                "fin de paginación."
            )

            break

        nuevos = 0

        for producto in productos:

            clave = (
                producto["nombre"],
                producto["link"]
            )

            if clave in vistos:
                continue

            vistos.add(clave)

            todos.append(producto)

            nuevos += 1

        log(
            f"Productos nuevos: {nuevos}"
        )

        # Evitar repetir infinitamente
        # la misma página
        if nuevos == 0:

            log(
                "No aparecieron productos nuevos: "
                "fin de paginación."
            )

            break

        pagina += 1

        time.sleep(1)

    log("")
    log(
        f"{categoria} FINALIZADA"
    )

    log(
        f"TOTAL: {len(todos)} productos"
    )

    return todos, True


# ============================================================
# MAIN
# ============================================================

def main():

    LOG_PATH.write_text(
        "",
        encoding="utf-8"
    )

    log("=" * 60)
    log("DIXGAMER - SCRAPER GENERAL")
    log("CUARENTENA")
    log("=" * 60)

    todos_los_productos = []

    resultados = {}

    errores = []

    # --------------------------------------------------------
    # TODAS LAS CATEGORÍAS
    # --------------------------------------------------------

    for categoria, url in CATEGORIAS.items():

        productos, correcta = scrapear_categoria(
            categoria,
            url
        )

        resultados[categoria] = len(
            productos
        )

        todos_los_productos.extend(
            productos
        )

        if not correcta:

            errores.append(
                categoria
            )

    # --------------------------------------------------------
    # GUARDAR JSON
    # --------------------------------------------------------

    with open(
        JSON_PATH,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            todos_los_productos,
            f,
            ensure_ascii=False,
            indent=2
        )

    # --------------------------------------------------------
    # RESUMEN
    # --------------------------------------------------------

    log("")
    log("=" * 60)
    log("RESUMEN DIXGAMER")
    log("=" * 60)

    for categoria, cantidad in resultados.items():

        log(
            f"{categoria}: "
            f"{cantidad} productos"
        )

    log("")
    log(
        f"TOTAL GENERAL: "
        f"{len(todos_los_productos)} productos"
    )

    if errores:

        log("")
        log("CATEGORÍAS CON ERROR:")

        for categoria in errores:

            log(
                f" - {categoria}"
            )

    else:

        log("")
        log(
            "TODAS LAS CATEGORÍAS "
            "FINALIZARON CORRECTAMENTE."
        )

    log("")
    log("=" * 60)


if __name__ == "__main__":
    main()

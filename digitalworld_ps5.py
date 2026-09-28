import json
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup
import requests
from curl_cffi import requests as curl_requests


# ============================================================
# DIGITALWORLD - SCRAPER GENERAL DE CUARENTENA
# ============================================================

CATEGORIAS = {
    "DigitalWorld PS4": "https://digitalworldpsn.com/es/juegos-digitales-ps4/",
    "DigitalWorld PS5": "https://digitalworldpsn.com/es/juegos-digitales-ps5/",
    "DigitalWorld Switch": "https://digitalworldpsn.com/es/juegos-digitales-switch/",
    "DigitalWorld VR": "https://digitalworldpsn.com/es/juegos-ps-vr-vr2/",
    "DigitalWorld Xbox": "https://digitalworldpsn.com/es/juegos-digitales-xbox/",
}

PARAM = "?v=1b23f8a4c97c"

OUTPUT_DIR = Path("catalogo_cuarentena")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

JSON_PATH = OUTPUT_DIR / "digitalworld.json"
LOG_PATH = OUTPUT_DIR / "digitalworld.log.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
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

    # Primer intento: curl_cffi simulando Chrome
    try:
        r = curl_requests.get(
            url,
            headers=HEADERS,
            impersonate="chrome",
            timeout=40,
        )

        if r.status_code == 200 and len(r.text) > 10000:
            return r.text, r.status_code

        log(f"   curl_cffi HTTP {r.status_code}")

    except Exception as e:
        log(f"   curl_cffi ERROR: {e}")

    # Segundo intento: requests normal
    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=40,
        )

        return r.text, r.status_code

    except Exception as e:
        log(f"   requests ERROR: {e}")
        return "", 0


# ============================================================
# CONVERTIR PRECIO
# ============================================================

def limpiar_precio(texto):

    if not texto:
        return None

    texto = texto.replace("\xa0", " ")
    texto = texto.strip()

    # Buscar número
    match = re.search(r"[\d.,]+", texto)

    if not match:
        return None

    numero = match.group(0)

    # --------------------------------------------------------
    # Detectar formato:
    #
    # 278,00  -> 278.00
    # 1.278,00 -> 1278.00
    # 14.01 -> 14.01
    # 1.278 -> 1278
    # --------------------------------------------------------

    if "," in numero and "." in numero:

        # Ej: 1.278,00
        if numero.rfind(",") > numero.rfind("."):
            numero = numero.replace(".", "")
            numero = numero.replace(",", ".")

        # Ej: 1,278.00
        else:
            numero = numero.replace(",", "")

    elif "," in numero:

        parte_final = numero.split(",")[-1]

        if len(parte_final) == 2:
            # Decimal: 278,00
            numero = numero.replace(".", "")
            numero = numero.replace(",", ".")
        else:
            # Miles: 1,278
            numero = numero.replace(",", "")

    elif "." in numero:

        partes = numero.split(".")

        # 14.01 -> decimal
        if len(partes[-1]) == 2:
            numero = numero.replace(",", "")

        # 1.278 -> miles
        else:
            numero = numero.replace(".", "")

    try:
        valor = float(numero)
    except ValueError:
        return None

    if valor < 1:
        return None

    return valor


# ============================================================
# EXTRAER PRODUCTOS
# ============================================================

def extraer_productos(html, categoria, pagina):

    soup = BeautifulSoup(html, "html.parser")

    cards = soup.select("li.product")

    if not cards:
        cards = soup.select("ul.products li.product")

    productos = []

    for card in cards:

        try:

            nombre_el = card.select_one(
                ".woocommerce-loop-product__title"
            )

            precio_el = card.select_one(
                ".price .woocommerce-Price-amount"
            )

            link_el = card.select_one(
                "a.woocommerce-LoopProduct-link"
            )

            if not nombre_el or not precio_el:
                continue

            nombre = nombre_el.get_text(
                " ",
                strip=True
            )

            precio_original = precio_el.get_text(
                " ",
                strip=True
            )

            precio = limpiar_precio(
                precio_original
            )

            if precio is None:
                continue

            link = ""

            if link_el:
                link = link_el.get("href", "")

            # Imagen
            imagen = ""

            imagen_el = card.select_one("img")

            if imagen_el:

                imagen = (
                    imagen_el.get("data-src")
                    or imagen_el.get("data-lazy-src")
                    or imagen_el.get("src")
                    or ""
                )

            productos.append({
                "nombre": nombre,
                "precio_original": precio_original,
                "precio": precio,
                "moneda": "UYU",
                "precio_uyu": precio,
                "link": link,
                "imagen": imagen,
                "categoria": categoria,
                "pagina": pagina,
            })

        except Exception:
            continue

    return productos


# ============================================================
# SCRAPEAR UNA CATEGORÍA
# ============================================================

def scrapear_categoria(categoria, base_url):

    log("")
    log("================================================")
    log(f"{categoria}")
    log("================================================")

    todos = []
    vistos = set()

    pagina = 1

    while True:

        if pagina == 1:
            url = base_url + PARAM

        else:
            url = (
                f"{base_url.rstrip('/')}"
                f"/page/{pagina}/{PARAM}"
            )

        log("")
        log(f"[{categoria}] Página {pagina}")
        log(url)

        html, status = obtener_html(url)

        log(f"HTTP: {status}")
        log(f"HTML: {len(html)} bytes")

        # ----------------------------------------------------
        # PRIMERA PÁGINA
        # ----------------------------------------------------

        if pagina == 1:

            if status in (403, 404):

                log(
                    f"ERROR CRÍTICO: página inicial HTTP {status}"
                )

                return todos, False

            if status != 200:

                log(
                    f"ERROR CRÍTICO: página inicial HTTP {status}"
                )

                return todos, False

        # ----------------------------------------------------
        # PÁGINAS SIGUIENTES
        # ----------------------------------------------------

        else:

            if status in (403, 404):

                log(
                    f"HTTP {status} en página {pagina}: "
                    "fin de paginación."
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

        # Si una página válida no tiene productos,
        # asumimos que terminó la categoría.
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

        # Evita quedar atrapado si el sitio devuelve
        # exactamente la misma página repetidamente.
        if nuevos == 0:

            log(
                "No aparecieron productos nuevos: "
                "fin de paginación."
            )

            break

        pagina += 1

        # Pausa pequeña para no bombardear el servidor
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

    # Limpiar log anterior
    LOG_PATH.write_text(
        "",
        encoding="utf-8"
    )

    log("================================================")
    log("DIGITALWORLD - SCRAPER GENERAL")
    log("CUARENTENA")
    log("================================================")

    todos_los_productos = []

    resultados = {}

    errores = []

    # --------------------------------------------------------
    # RECORRER TODAS LAS CATEGORÍAS
    # --------------------------------------------------------

    for categoria, url in CATEGORIAS.items():

        productos, correcta = scrapear_categoria(
            categoria,
            url
        )

        resultados[categoria] = len(productos)

        todos_los_productos.extend(productos)

        if not correcta:
            errores.append(categoria)

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
    log("================================================")
    log("RESUMEN DIGITALWORLD")
    log("================================================")

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
            log(f" - {categoria}")

    else:

        log("")
        log(
            "TODAS LAS CATEGORÍAS "
            "FINALIZARON CORRECTAMENTE."
        )

    log("")
    log("================================================")


if __name__ == "__main__":
    main()

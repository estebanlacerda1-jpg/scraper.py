import csv
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://juegosdigitalesps4ps5.com"

CATEGORIAS = {
    "Juegos PS4": f"{BASE_URL}/juegos-ps4/",
    "Juegos PS5": f"{BASE_URL}/juegos-ps5/",
    "PS Plus": f"{BASE_URL}/membresias-ps-plus/",
    "Game Pass": f"{BASE_URL}/membresias-game-pass/",
}

CSV_FILE = "jdp4p5.csv"
LOG_FILE = "jdp4p5.log.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


def limpiar_texto(texto):
    if not texto:
        return ""
    return re.sub(r"\s+", " ", texto).strip()


def precio_a_numero(texto):
    """
    Convierte:
        $34.510 -> 34510
        $82.110 -> 82110
        $1.490  -> 1490
        $34.510,50 -> 34510.50

    No utiliza data-product-price porque queremos
    conservar exactamente el precio visible de la tienda.
    """
    if not texto:
        return ""

    texto = texto.strip()

    # Dejar solamente números, punto y coma decimal
    limpio = re.sub(r"[^\d.,]", "", texto)

    if not limpio:
        return ""

    # Caso 34.510,50
    if "," in limpio and "." in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")

    # Caso 34.510 -> miles
    elif "." in limpio:
        partes = limpio.split(".")
        if len(partes[-1]) == 3:
            limpio = limpio.replace(".", "")
        else:
            limpio = limpio.replace(",", "")

    # Caso 34510,50
    elif "," in limpio:
        partes = limpio.split(",")
        if len(partes[-1]) == 2:
            limpio = limpio.replace(",", ".")
        else:
            limpio = limpio.replace(",", "")

    try:
        numero = float(limpio)

        if numero.is_integer():
            return int(numero)

        return numero

    except ValueError:
        return ""


def obtener_pagina(session, url):
    try:
        response = session.get(
            url,
            headers=HEADERS,
            timeout=30,
            allow_redirects=True,
        )

        return response

    except requests.RequestException as e:
        logger.error(f"ERROR HTTP | {url} | {e}")
        return None


def extraer_productos(html, categoria, pagina):
    soup = BeautifulSoup(html, "html.parser")

    productos = []

    # Contenedor real confirmado en el HTML
    items = soup.select(".js-item-product")

    for item in items:

        # -------------------------
        # NOMBRE
        # -------------------------
        nombre_el = item.select_one(".js-item-name")

        if not nombre_el:
            continue

        nombre = limpiar_texto(nombre_el.get_text(" ", strip=True))

        if not nombre:
            continue

        # -------------------------
        # URL
        # -------------------------
        enlace = item.select_one('a[href*="/productos/"]')

        if not enlace:
            continue

        url = urljoin(BASE_URL, enlace.get("href", "").strip())

        if not url:
            continue

        # -------------------------
        # PRECIO ACTUAL
        # -------------------------
        precio_el = item.select_one(".js-price-display")

        precio = ""

        if precio_el:
            precio_texto = precio_el.get_text(" ", strip=True)
            precio = precio_a_numero(precio_texto)

        # -------------------------
        # PRECIO ANTERIOR
        # -------------------------
        precio_anterior_el = item.select_one(".js-compare-price-display")

        precio_anterior = ""

        if precio_anterior_el:
            precio_anterior_texto = precio_anterior_el.get_text(
                " ", strip=True
            )
            precio_anterior = precio_a_numero(precio_anterior_texto)

        productos.append(
            {
                "fuente": "JDP4P5",
                "nombre": nombre,
                "categoria": categoria,
                "precio": precio,
                "precio_anterior": precio_anterior,
                "url": url,
                "pagina": pagina,
            }
        )

    return productos


def siguiente_pagina_url(url, pagina):
    """
    Tiendanube utiliza normalmente:
        ?page=2

    Probamos primero ?page=N.
    """
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}page={pagina}"


def procesar_categoria(session, categoria, url):

    logger.info("=" * 70)
    logger.info(f"INICIANDO | {categoria} | {url}")

    todos = []
    urls_vistas = set()

    pagina = 1

    while True:

        if pagina == 1:
            pagina_url = url
        else:
            pagina_url = siguiente_pagina_url(url, pagina)

        logger.info(f"PAGINA {pagina} | {pagina_url}")

        response = obtener_pagina(session, pagina_url)

        if response is None:
            logger.error(
                f"ERROR REAL | No se pudo obtener pagina {pagina}"
            )
            break

        status = response.status_code

        logger.info(f"HTTP {status} | pagina {pagina}")

        # ------------------------------------------------
        # REGLA GENERAL:
        # 403/404 después de página 1 = fin de categoría
        # ------------------------------------------------
        if status in (403, 404):

            if pagina > 1:
                logger.info(
                    f"FIN PAGINACION | HTTP {status} "
                    f"en pagina {pagina}"
                )
                break

            logger.error(
                f"ERROR REAL | HTTP {status} "
                f"en primera pagina de {categoria}"
            )
            break

        if status != 200:
            logger.error(
                f"ERROR REAL | HTTP {status} "
                f"en pagina {pagina}"
            )
            break

        productos = extraer_productos(
            response.text,
            categoria,
            pagina,
        )

        if not productos:

            logger.info(
                f"FIN PAGINACION | 0 productos en pagina {pagina}"
            )
            break

        nuevos = 0

        for producto in productos:

            if producto["url"] in urls_vistas:
                continue

            urls_vistas.add(producto["url"])
            todos.append(producto)
            nuevos += 1

        logger.info(
            f"PAGINA {pagina} | "
            f"productos HTML: {len(productos)} | "
            f"nuevos: {nuevos} | "
            f"total acumulado: {len(todos)}"
        )

        # Si la página existe pero no aporta productos nuevos,
        # evitamos entrar en un bucle.
        if nuevos == 0:
            logger.info(
                f"FIN PAGINACION | pagina {pagina} "
                f"sin productos nuevos"
            )
            break

        pagina += 1

        # Pequeña pausa para no bombardear el servidor
        time.sleep(1)

    logger.info(
        f"FINALIZADA | {categoria} | "
        f"{len(todos)} productos"
    )

    return todos


def guardar_csv(productos):

    campos = [
        "fuente",
        "nombre",
        "categoria",
        "precio",
        "precio_anterior",
        "url",
        "pagina",
    ]

    with open(
        CSV_FILE,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as archivo:

        writer = csv.DictWriter(
            archivo,
            fieldnames=campos,
        )

        writer.writeheader()

        for producto in productos:
            writer.writerow(producto)


def main():

    logger.info("=" * 70)
    logger.info("JDP4P5 | INICIO DEL SCRAPER")

    session = requests.Session()

    todos_productos = []
    urls_globales = set()

    for categoria, url in CATEGORIAS.items():

        productos = procesar_categoria(
            session,
            categoria,
            url,
        )

        # Dedupe global por URL
        for producto in productos:

            if producto["url"] in urls_globales:
                continue

            urls_globales.add(producto["url"])
            todos_productos.append(producto)

    guardar_csv(todos_productos)

    logger.info("=" * 70)
    logger.info(
        f"JDP4P5 | FINALIZADO | "
        f"{len(todos_productos)} productos únicos"
    )

    print("=" * 60)
    print("JDP4P5 FINALIZADO")
    print(f"Productos únicos: {len(todos_productos)}")
    print(f"CSV: {CSV_FILE}")
    print(f"Log: {LOG_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()

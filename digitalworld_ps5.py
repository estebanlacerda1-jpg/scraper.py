import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests


BASE_URL = "https://digitalworldpsn.com/es/juegos-digitales-ps5/"
PARAM = "?v=1b23f8a4c97c"

OUTPUT_DIR = Path("catalogo_cuarentena")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

JSON_PATH = OUTPUT_DIR / "digitalworld_ps5.json"
LOG_PATH = OUTPUT_DIR / "digitalworld_ps5.log.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


def log(text):
    print(text)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(text + "\n")


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


def extraer_productos(html, pagina):
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

            nombre = nombre_el.get_text(" ", strip=True)
            precio_txt = precio_el.get_text(" ", strip=True)

            numero = re.search(r"[\d.,]+", precio_txt)

            if not numero:
                continue

            numero_txt = numero.group(0)

            # UYU: 319,00 -> 319
            numero_txt = numero_txt.replace(".", "").replace(",", ".")

            try:
                valor = float(numero_txt)
            except ValueError:
                continue

            if valor < 1:
                continue

            link = link_el.get("href") if link_el else BASE_URL

            imagen_el = card.select_one("img")

            imagen = ""

            if imagen_el:
                imagen = (
                    imagen_el.get("data-src")
                    or imagen_el.get("src")
                    or ""
                )

            productos.append({
                "nombre": nombre,
                "precio_original": precio_txt,
                "precio": valor,
                "moneda": "UYU",
                "precio_uyu": valor,
                "link": link,
                "imagen": imagen,
                "pagina": pagina,
            })

        except Exception:
            continue

    return productos


def main():

    # Limpiar log anterior
    LOG_PATH.write_text("", encoding="utf-8")

    todos = []
    vistos = set()

    # El HTML confirma 56 páginas
    MAX_PAGINAS = 56

    log("==============================================")
    log("DigitalWorld PS5 - SCRAPER CUARENTENA")
    log("==============================================")

    for pagina in range(1, MAX_PAGINAS + 1):

        if pagina == 1:
            url = BASE_URL + PARAM
        else:
            url = (
                f"{BASE_URL.rstrip('/')}/page/"
                f"{pagina}/{PARAM}"
            )

        log(f"\n[Página {pagina}/{MAX_PAGINAS}]")
        log(url)

        html, status = obtener_html(url)

        log(f"HTTP: {status}")
        log(f"HTML: {len(html)} bytes")

        if status != 200:
            log(f"ERROR HTTP {status}")
            continue

        productos = extraer_productos(html, pagina)

        log(f"Productos encontrados: {len(productos)}")

        nuevos = 0

        for producto in productos:

            clave = (
                producto["nombre"],
                producto["link"],
            )

            if clave in vistos:
                continue

            vistos.add(clave)
            todos.append(producto)
            nuevos += 1

        log(f"Productos nuevos: {nuevos}")

        time.sleep(1)

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(
            todos,
            f,
            ensure_ascii=False,
            indent=2,
        )

    log("\n==============================================")
    log(f"TOTAL PRODUCTOS: {len(todos)}")
    log("==============================================")


if __name__ == "__main__":
    main()

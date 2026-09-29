import csv
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://portalgames.com.ar"
ANIME_URL = f"{BASE_URL}/product-category/juegos-ps3/anime/"

HTML_FILE = Path("portalps3_anime.html")
CSV_FILE = Path("portalps3.csv")
LOG_FILE = Path("portalps3.log.txt")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Referer": BASE_URL + "/",
}


def log(mensaje):
    print(mensaje)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(mensaje + "\n")


def precio_ars(texto):
    if not texto:
        return None

    texto = texto.replace("\xa0", " ").strip()
    texto = re.sub(r"[^\d,.]", "", texto)

    if not texto:
        return None

    # PortalGames muestra ARS en formato argentino:
    # 17.399,00 -> 17399
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(".", "")

    try:
        valor = float(texto)
        return int(valor) if valor.is_integer() else valor
    except ValueError:
        return None


def extraer_productos(html):
    soup = BeautifulSoup(html, "html.parser")

    productos = []
    vistos = set()

    # Los productos reales están en estos enlaces.
    enlaces = soup.select(
        "p.name.product-title.woocommerce-loop-product__title a"
    )

    for enlace in enlaces:
        nombre = enlace.get_text(" ", strip=True)
        url = enlace.get("href", "").strip()

        if not nombre or not url or url in vistos:
            continue

        vistos.add(url)

        contenedor = enlace.find_parent(class_="product-small")
        if not contenedor:
            continue

        precio_tag = contenedor.select_one(".woocommerce-Price-amount")
        categoria_tag = contenedor.select_one(".product-cat")

        precio_mostrado = (
            precio_tag.get_text(" ", strip=True)
            if precio_tag else ""
        )

        categoria = (
            categoria_tag.get_text(" ", strip=True)
            if categoria_tag else "Anime"
        )

        productos.append({
            "fuente": "PortalGames",
            "nombre": nombre,
            "categoria": categoria,
            "precio": precio_ars(precio_mostrado),
            "moneda": "ARS",
            "precio_mostrado": precio_mostrado,
            "url": url,
        })

    return productos


def descargar_html():
    log(f"Descargando: {ANIME_URL}")

    try:
        r = requests.get(
            ANIME_URL,
            headers=HEADERS,
            timeout=30,
            allow_redirects=True,
        )

        log(f"HTTP: {r.status_code}")
        log(f"Content-Type: {r.headers.get('content-type', '')}")

        HTML_FILE.write_text(
            r.text,
            encoding="utf-8",
        )

        log(f"HTML guardado: {HTML_FILE}")

        return r.status_code, r.text

    except Exception as e:
        log(f"ERROR descargando HTML: {e}")
        return 0, ""


def main():
    LOG_FILE.write_text("", encoding="utf-8")

    log("=== PortalGames PS3 - prueba Anime ===")
    log(f"URL: {ANIME_URL}")

    status, html = descargar_html()

    # Si Cloudflare bloquea la descarga, igualmente intentamos
    # analizar un HTML previamente guardado.
    if not html or status >= 400:
        if HTML_FILE.exists():
            log("Usando HTML local previamente guardado.")
            html = HTML_FILE.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        else:
            log("No hay HTML disponible para analizar.")
            return

    productos = extraer_productos(html)

    with CSV_FILE.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        campos = [
            "fuente",
            "nombre",
            "categoria",
            "precio",
            "moneda",
            "precio_mostrado",
            "url",
        ]

        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(productos)

    log(f"PRODUCTOS ENCONTRADOS: {len(productos)}")
    log(f"CSV generado: {CSV_FILE}")

    for i, producto in enumerate(productos, 1):
        log(
            f"{i:02d}. {producto['nombre']} | "
            f"{producto['precio_mostrado']} | "
            f"{producto['url']}"
        )


if __name__ == "__main__":
    main()

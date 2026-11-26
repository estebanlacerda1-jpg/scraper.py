import csv
import re
import time
import requests
from bs4 import BeautifulSoup

URL = "https://mdqstore.com/categoria-producto/psn-card/"
CATEGORIA = "PSN Card"

CSV_SALIDA = "catalogo_cuarentena/mdq.csv"
LOG_SALIDA = "catalogo_cuarentena/mdq.log.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-UY,es;q=0.9,en;q=0.8",
}


def limpiar_precio(texto):
    """
    Convierte precios visibles como:
    $ 12.345,67
    $ 12.345
    $ 12345
    a número.
    """
    if not texto:
        return ""

    texto = texto.replace("\xa0", " ").strip()

    # Dejamos solamente números, puntos y comas
    valor = re.sub(r"[^\d.,]", "", texto)

    if not valor:
        return ""

    # Formato latino: 12.345,67
    if "." in valor and "," in valor:
        valor = valor.replace(".", "").replace(",", ".")

    # 12,50
    elif "," in valor:
        valor = valor.replace(",", ".")

    # 12.345 puede ser miles o decimal.
    # En este caso conservamos el valor mostrado como texto
    # y solamente convertimos si es claramente numérico.
    try:
        return float(valor)
    except ValueError:
        return ""


def obtener_productos():
    log = []

    log.append("=== MDQ STORE - PSN CARD ===")
    log.append(f"URL: {URL}")

    try:
        response = requests.get(
            URL,
            headers=HEADERS,
            timeout=30
        )
    except Exception as e:
        log.append(f"ERROR conexión: {e}")
        return [], log

    log.append(f"HTTP página 1: {response.status_code}")

    if response.status_code in (403, 404):
        log.append(
            "ERROR REAL: 403/404 en la página inicial. "
            "No se continúa."
        )
        return [], log

    if response.status_code != 200:
        log.append(f"ERROR HTTP: {response.status_code}")
        return [], log

    soup = BeautifulSoup(response.text, "html.parser")

    productos = []
    urls_vistas = set()

    containers = soup.select(".product-small")

    log.append(f"Contenedores encontrados: {len(containers)}")

    for producto in containers:

        # URL
        enlace = producto.select_one(
            'a[href*="/producto/"]'
        )

        if not enlace:
            continue

        url = enlace.get("href", "").strip()

        if not url or url in urls_vistas:
            continue

        urls_vistas.add(url)

        # Nombre
        nombre_tag = producto.select_one(
            ".product-title a"
        )

        nombre = (
            nombre_tag.get_text(" ", strip=True)
            if nombre_tag
            else ""
        )

        # Precio
        precio_tag = producto.select_one(
            ".woocommerce-Price-amount"
        )

        precio_texto = (
            precio_tag.get_text(" ", strip=True)
            if precio_tag
            else ""
        )

        precio = limpiar_precio(precio_texto)

        # Moneda
        moneda_tag = producto.select_one(
            ".woocommerce-Price-currencySymbol"
        )

        moneda = (
            moneda_tag.get_text(" ", strip=True)
            if moneda_tag
            else ""
        )

        # Categoría visible
        categoria_tag = producto.select_one(
            ".product-cat"
        )

        categoria = (
            categoria_tag.get_text(" ", strip=True)
            if categoria_tag
            else CATEGORIA
        )

        productos.append({
            "fuente": "MDQ Store",
            "nombre": nombre,
            "categoria": categoria,
            "precio": precio,
            "precio_mostrado": precio_texto,
            "moneda": moneda,
            "url": url,
            "pagina": 1,
        })

    log.append(f"Productos únicos encontrados: {len(productos)}")

    return productos, log


def guardar_csv(productos):
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
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=campos
        )

        writer.writeheader()
        writer.writerows(productos)


def guardar_log(log):
    with open(
        LOG_SALIDA,
        "w",
        encoding="utf-8"
    ) as f:
        f.write("\n".join(log))


def main():

    productos, log = obtener_productos()

    guardar_csv(productos)
    guardar_log(log)

    print("\n".join(log))
    print()
    print(f"CSV generado: {CSV_SALIDA}")
    print(f"Total productos: {len(productos)}")


if __name__ == "__main__":
    main()

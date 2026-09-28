import requests
from bs4 import BeautifulSoup
import json
import time

BASE_URL = "https://dixgamer.com/categoria-producto/juegos/ps4/"
MAX_PAGINAS = 999

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}

productos = {}
paginas_procesadas = 0

for pagina in range(1, MAX_PAGINAS + 1):

    if pagina == 1:
        url = BASE_URL
    else:
        url = f"{BASE_URL}page/{pagina}/"

    print(f"\n=== Página {pagina} ===")
    print(url)

    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        print(f"HTTP: {r.status_code}")

        # 403/404 en páginas posteriores = fin normal
        if r.status_code in (403, 404):
            if pagina == 1:
                print("ERROR: la primera página devuelve 403/404.")
                break

            print("403/404 en página posterior. Fin de paginación.")
            break

        if r.status_code != 200:
            print(f"ERROR HTTP {r.status_code}")
            break

        soup = BeautifulSoup(r.text, "html.parser")

        elementos = soup.select(".products .product-small")

        print(f"Elementos encontrados: {len(elementos)}")

        if not elementos:
            print("No hay productos. Fin de paginación.")
            break

        nuevos = 0

        for producto in elementos:

            titulo = producto.select_one(
                ".woocommerce-loop-product__title a"
            )

            if not titulo:
                continue

            nombre = titulo.get_text(" ", strip=True)
            url_producto = titulo.get("href", "").strip()

            if not url_producto:
                continue

            # El HTML contiene cada producto duplicado.
            # La URL identifica de forma única al producto.
            if url_producto in productos:
                continue

            categoria = producto.select_one(".product-cat")

            precio = producto.select_one(
                ".woocommerce-Price-amount bdi"
            )

            moneda = producto.select_one(
                ".woocommerce-Price-currencySymbol"
            )

            precio_usd = producto.select_one(
                "[data-price-usd]"
            )

            imagen = producto.select_one("img")

            productos[url_producto] = {
                "nombre": nombre,
                "categoria": (
                    categoria.get_text(" ", strip=True)
                    if categoria else ""
                ),
                "precio_mostrado": (
                    precio.get_text(" ", strip=True)
                    if precio else ""
                ),
                "moneda": (
                    moneda.get_text(" ", strip=True)
                    if moneda else ""
                ),
                "precio_usd": (
                    precio_usd.get("data-price-usd")
                    if precio_usd else None
                ),
                "url": url_producto,
                "imagen": (
                    imagen.get("src", "")
                    if imagen else ""
                ),
                "pagina": pagina
            }

            nuevos += 1

        print(f"Productos nuevos: {nuevos}")
        print(f"Total acumulado: {len(productos)}")

        paginas_procesadas = pagina

        # Si una página no aporta productos nuevos,
        # evitamos entrar en un bucle.
        if nuevos == 0:
            print("No hay productos nuevos. Fin.")
            break

        time.sleep(1)

    except Exception as e:
        print(f"ERROR: {e}")
        break


resultado = list(productos.values())

with open(
    "dixgamer_ps4.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        resultado,
        f,
        ensure_ascii=False,
        indent=2
    )

print("\n==============================")
print("DIXGAMER PS4 FINALIZADO")
print("==============================")
print(f"Páginas procesadas: {paginas_procesadas}")
print(f"Productos únicos: {len(resultado)}")
print("Archivo: dixgamer_ps4.json")

import requests
from bs4 import BeautifulSoup
import csv
import time
from datetime import datetime

# ============================================================
# DIXGAMER - SCRAPER COMPLETO
# ============================================================

CATEGORIAS = {
    "Dix FC Points": "https://dixgamer.com/categoria-producto/tarjetas/fc-points/",
    "Dix Fortnite": "https://dixgamer.com/categoria-producto/tarjetas/fortnite/",
    "Dix Nintendo": "https://dixgamer.com/categoria-producto/tarjetas/nintendo/",
    "Dix Playstation": "https://dixgamer.com/categoria-producto/tarjetas/ps/",
    "Dix Razer": "https://dixgamer.com/categoria-producto/tarjetas/razer-gold/",
    "Dix Steam": "https://dixgamer.com/categoria-producto/tarjetas/steam/",
    "Dix Xbox": "https://dixgamer.com/categoria-producto/tarjetas/xbox/",
    "Dix PS3": "https://dixgamer.com/categoria-producto/juegos/ps3/",
    "Dix PS4": "https://dixgamer.com/categoria-producto/juegos/ps4/",
    "Dix PS5": "https://dixgamer.com/categoria-producto/juegos/ps5/",
}

MAX_PAGINAS = 999

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}

CAMPOS = [
    "fuente",
    "nombre",
    "categoria",
    "precio_usd",
    "precio_mostrado",
    "moneda",
    "url",
    "pagina",
]

LOG = []


def log(mensaje):
    print(mensaje)
    LOG.append(mensaje)


def obtener_productos(categoria_nombre, base_url):

    log("")
    log("=" * 60)
    log(f"{categoria_nombre}")
    log("=" * 60)

    productos = {}
    paginas_procesadas = 0

    for pagina in range(1, MAX_PAGINAS + 1):

        if pagina == 1:
            url = base_url
        else:
            url = f"{base_url}page/{pagina}/"

        log("")
        log(f"Página {pagina}: {url}")

        try:
            respuesta = requests.get(
                url,
                headers=HEADERS,
                timeout=30
            )

            log(f"HTTP: {respuesta.status_code}")

            # ------------------------------------------------
            # 403 / 404
            # Página 1 = error real
            # Página posterior = fin de paginación
            # ------------------------------------------------
            if respuesta.status_code in (403, 404):

                if pagina == 1:
                    log(
                        f"ERROR: {categoria_nombre} "
                        f"devuelve HTTP {respuesta.status_code} "
                        "en la primera página."
                    )
                    return productos, paginas_procesadas, False

                log(
                    f"HTTP {respuesta.status_code} en página "
                    f"{pagina}. Fin de paginación."
                )
                break

            if respuesta.status_code != 200:
                log(
                    f"ERROR HTTP {respuesta.status_code}. "
                    "Se abandona esta categoría."
                )
                return productos, paginas_procesadas, False

            soup = BeautifulSoup(
                respuesta.text,
                "html.parser"
            )

            elementos = soup.select(
                ".products .product-small"
            )

            log(
                f"Elementos encontrados: "
                f"{len(elementos)}"
            )

            if not elementos:
                log(
                    "No se encontraron productos. "
                    "Fin de paginación."
                )
                break

            nuevos = 0

            for producto in elementos:

                # --------------------------------------------
                # NOMBRE + URL
                # --------------------------------------------
                titulo = producto.select_one(
                    ".woocommerce-loop-product__title a"
                )

                if not titulo:
                    continue

                nombre = titulo.get_text(
                    " ",
                    strip=True
                )

                url_producto = titulo.get(
                    "href",
                    ""
                ).strip()

                if not url_producto:
                    continue

                # --------------------------------------------
                # DEDUPLICACIÓN
                # --------------------------------------------
                if url_producto in productos:
                    continue

                # --------------------------------------------
                # CATEGORÍA
                # --------------------------------------------
                categoria = producto.select_one(
                    ".product-cat"
                )

                categoria_texto = (
                    categoria.get_text(
                        " ",
                        strip=True
                    )
                    if categoria
                    else ""
                )

                # --------------------------------------------
                # PRECIO MOSTRADO
                # --------------------------------------------
                precio = producto.select_one(
                    ".woocommerce-Price-amount bdi"
                )

                precio_mostrado = (
                    precio.get_text(
                        " ",
                        strip=True
                    )
                    if precio
                    else ""
                )

                # --------------------------------------------
                # MONEDA
                # --------------------------------------------
                moneda_elemento = producto.select_one(
                    ".woocommerce-Price-currencySymbol"
                )

                moneda = (
                    moneda_elemento.get_text(
                        " ",
                        strip=True
                    )
                    if moneda_elemento
                    else ""
                )

                # --------------------------------------------
                # PRECIO BASE USD
                # --------------------------------------------
                precio_usd_elemento = producto.select_one(
                    "[data-price-usd]"
                )

                precio_usd = None

                if precio_usd_elemento:
                    precio_usd = precio_usd_elemento.get(
                        "data-price-usd"
                    )

                # --------------------------------------------
                # GUARDAR
                # --------------------------------------------
                productos[url_producto] = {
                    "fuente": "DixGamer",
                    "nombre": nombre,
                    "categoria": categoria_texto,
                    "precio_usd": precio_usd,
                    "precio_mostrado": precio_mostrado,
                    "moneda": moneda,
                    "url": url_producto,
                    "pagina": pagina,
                }

                nuevos += 1

            log(f"Productos nuevos: {nuevos}")
            log(
                f"Total acumulado: "
                f"{len(productos)}"
            )

            paginas_procesadas = pagina

            # Si la página no aporta nada nuevo,
            # dejamos de recorrerla.
            if nuevos == 0:
                log(
                    "No hay productos nuevos. "
                    "Fin de paginación."
                )
                break

            time.sleep(1)

        except Exception as error:

            log(
                f"ERROR procesando página "
                f"{pagina}: {error}"
            )

            return productos, paginas_procesadas, False

    return productos, paginas_procesadas, True


# ============================================================
# EJECUCIÓN
# ============================================================

todos_los_productos = []

categorias_ok = []
categorias_error = []

inicio = datetime.now()

log("=" * 60)
log("DIXGAMER - SCRAPER COMPLETO")
log("=" * 60)
log(f"Inicio: {inicio}")
log(f"Categorías a procesar: {len(CATEGORIAS)}")


for nombre_categoria, url_categoria in CATEGORIAS.items():

    productos, paginas, correcto = obtener_productos(
        nombre_categoria,
        url_categoria
    )

    if correcto:
        categorias_ok.append(nombre_categoria)

    else:
        categorias_error.append(nombre_categoria)

    todos_los_productos.extend(
        productos.values()
    )

    log("")
    log(
        f"{nombre_categoria}: "
        f"{len(productos)} productos"
    )


# ============================================================
# CSV
# ============================================================

archivo_csv = "dixgamer.csv"

with open(
    archivo_csv,
    "w",
    newline="",
    encoding="utf-8-sig"
) as archivo:

    escritor = csv.DictWriter(
        archivo,
        fieldnames=CAMPOS
    )

    escritor.writeheader()

    for producto in todos_los_productos:
        escritor.writerow(producto)


# ============================================================
# LOG FINAL
# ============================================================

fin = datetime.now()

log("")
log("=" * 60)
log("DIXGAMER - FINALIZADO")
log("=" * 60)

log(
    f"Productos totales: "
    f"{len(todos_los_productos)}"
)

log(
    f"Categorías correctas: "
    f"{len(categorias_ok)}"
)

log(
    f"Categorías con error: "
    f"{len(categorias_error)}"
)

if categorias_error:
    log("")
    log("CATEGORÍAS CON ERROR:")

    for categoria in categorias_error:
        log(f"- {categoria}")

log("")
log(f"CSV generado: {archivo_csv}")
log(f"Fin: {fin}")


# Guardar log
with open(
    "dixgamer.log.txt",
    "w",
    encoding="utf-8"
) as archivo_log:

    archivo_log.write(
        "\n".join(LOG)
    )

print("")
print("=" * 60)
print("LISTO")
print("=" * 60)
print(f"CSV: {archivo_csv}")
print("LOG: dixgamer.log.txt")

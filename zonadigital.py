import re
import sys
import time
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://zonadigitalmd.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
    )
}

# Solo categorías seleccionadas para ABC Gaming.
CATEGORIAS = {
    "Juegos PS4": "/productos/juegosps4",
    "Juegos PS5": "/productos/juegosps5",
    "Juegos PC Código": "/productos/juegospccodigo",
    "Juegos PC Cuenta": "/productos/juegospccuenta",
    "Juegos Xbox": "/productos/juegosxbox",
    "PS Plus 1 consola PS4/PS5": "/productos/psplus1consolaps4ps5",
    "Xbox Game Pass / Suscripciones": "/productos/suscripcioncodigo",
    "EA Play Código": "/productos/eaplaycodigo",
    "Gift Card Steam": "/productos/giftcardsteam",
    "Gift Card Roblox": "/productos/giftcardroblox",
    "Gift Card Xbox": "/productos/giftcardxbox",
    "Gift Card Battle.net": "/productos/giftcardbattlenet",
    "Gift Card Riot LATAM": "/productos/giftcardriotlatam",
    "Gift Card Free Fire": "/productos/giftcardfreefire",
    "Gift Card Google Play USA": "/productos/giftcardgoogleplayusa",
    "Gift Card Apple USA": "/productos/giftcardusaapple",
    "Gift Card USA": "/productos/giftcardusa",
    "Código Windows": "/productos/codigowindows",
    "Código Avast": "/productos/codigoavast",
    "Monedas Apex Legends": "/productos/monedasapexlegends",
    "Gift Card Fortnite V-Bucks": "/productos/giftcardfortnite",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def normalizar_url(url):
    """Quita parámetros de paginación y fragmentos para deduplicar."""
    absoluta = urljoin(BASE_URL, url)
    p = urlparse(absoluta)
    params = [
        (k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
        if k.lower() not in {"page", "pagina"}
    ]
    return urlunparse((
        p.scheme, p.netloc, p.path.rstrip("/"), "",
        urlencode(params), ""
    ))


def obtener_respuesta(url):
    respuesta = SESSION.get(url, timeout=35)
    respuesta.raise_for_status()
    return respuesta


def diagnosticar_html(html, respuesta, pagina):
    soup = BeautifulSoup(html, "html.parser")
    titulo_pagina = soup.title.get_text(" ", strip=True) if soup.title else "(sin title)"
    tarjetas = len(soup.select("app-item-gift"))
    enlaces_producto = len(soup.select('a[href*="/producto/"]'))
    ids_producto = len(soup.select('[id^="product-"]'))
    print(
        f"DIAGNÓSTICO página {pagina}: HTTP {respuesta.status_code}; "
        f"{len(respuesta.content)} bytes; "
        f"Content-Type={respuesta.headers.get('Content-Type', 'no informado')}; "
        f"URL final={respuesta.url}"
    )
    print(
        f"DIAGNÓSTICO HTML: título={titulo_pagina!r}; "
        f"app-item-gift={tarjetas}; enlaces /producto/={enlaces_producto}; "
        f"IDs product-= {ids_producto}"
    )
    if tarjetas == 0 and enlaces_producto == 0:
        texto = soup.get_text(" ", strip=True)
        print(f"DIAGNÓSTICO sin tarjetas: texto visible={texto[:350]!r}")
        print(f"DIAGNÓSTICO inicio HTML={html[:350]!r}")


def extraer_productos(html):
    soup = BeautifulSoup(html, "html.parser")
    encontrados = {}

    # ZonaDigital entrega tarjetas app-item-gift con id product-N.
    # En algunas respuestas los enlaces no quedan anidados dentro de la tarjeta,
    # por eso primero se buscan los enlaces globalmente y luego se emparejan
    # por orden con las tarjetas identificadas.
    tarjetas = soup.select("app-item-gift")
    enlaces = soup.select('a[href*="producto"]')

    if not tarjetas:
        tarjetas = soup.select('[id^="product-"]')

    enlaces_validos = []
    vistos = set()
    for enlace in enlaces:
        href = enlace.get("href", "")
        if not href:
            continue
        url_producto = normalizar_url(href)
        if "producto" not in urlparse(url_producto).path.lower():
            continue
        if url_producto not in vistos:
            vistos.add(url_producto)
            enlaces_validos.append((enlace, url_producto))

    for indice, tarjeta in enumerate(tarjetas):
        enlace = tarjeta.select_one('a[href*="producto"]')
        url_producto = None

        if enlace:
            url_producto = normalizar_url(enlace.get("href", ""))
        elif indice < len(enlaces_validos):
            enlace, url_producto = enlaces_validos[indice]

        if not url_producto or "producto" not in urlparse(url_producto).path.lower():
            continue

        titulo = tarjeta.select_one(
            ".item-gift__content-title, .item-gift__title, [class*='title']"
        )
        nombre = titulo.get_text(" ", strip=True) if titulo else ""

        if not nombre and enlace:
            nombre = enlace.get_text(" ", strip=True)
        if not nombre:
            nombre = tarjeta.get("data-name", "").strip()
        if not nombre:
            nombre = tarjeta.get_text(" ", strip=True)

        if not nombre:
            continue

        precio_elemento = tarjeta.select_one(
            "app-item-price-gift .price, .item-gift__price .price, .price, [class*='price']"
        )
        precio = (
            precio_elemento.get_text(" ", strip=True)
            if precio_elemento else "No detectado"
        )

        encontrados[url_producto] = {
            "nombre": nombre,
            "url": url_producto,
            "precio": precio,
        }

    return encontrados


def escanear_categoria(nombre_categoria, ruta):
    url_base = urljoin(BASE_URL, ruta)
    productos_categoria = {}
    paginas_sin_novedades = 0
    hubo_error_http = False

    print(f"\n{'=' * 70}")
    print(f"CATEGORÍA: {nombre_categoria}")
    print(f"URL: {url_base}")
    print("=" * 70)

    # La paginación observada es acumulativa.
    for pagina in range(1, 101):
        url = url_base if pagina == 1 else f"{url_base}?page={pagina}"

        try:
            respuesta = obtener_respuesta(url)
            html = respuesta.text
            if pagina == 1:
                diagnosticar_html(html, respuesta, pagina)
            productos = extraer_productos(html)
        except requests.RequestException as error:
            print(f"[ERROR HTTP/RED] Página {pagina}: {error}")
            hubo_error_http = True
            break

        nuevos = 0
        for url_producto, producto in productos.items():
            if url_producto not in productos_categoria:
                productos_categoria[url_producto] = producto
                nuevos += 1

        print(
            f"Página {pagina}: {len(productos)} detectados en respuesta; "
            f"{nuevos} nuevos; total de categoría: "
            f"{len(productos_categoria)}"
        )

        if nuevos == 0:
            paginas_sin_novedades += 1
        else:
            paginas_sin_novedades = 0

        if pagina > 1 and paginas_sin_novedades >= 2:
            print("Fin probable del catálogo: no aparecen productos nuevos.")
            break

        time.sleep(0.4)

    for producto in productos_categoria.values():
        print(f"- {producto['nombre']}")
        print(f"  Precio: {producto['precio']}")
        print(f"  URL: {producto['url']}")

    print(f"Total observado en {nombre_categoria}: {len(productos_categoria)}")
    if len(productos_categoria) == 0:
        print(f"[ADVERTENCIA] La categoría {nombre_categoria} terminó con cero productos.")
    return productos_categoria, hubo_error_http


def main():
    catalogo_global = {}
    errores = []
    categorias_vacias = []

    print("ABC GAMING | ZONADIGITAL | MODO DE DIAGNÓSTICO")
    print("No se guardarán archivos.")
    print(f"Categorías configuradas: {len(CATEGORIAS)}")

    for nombre, ruta in CATEGORIAS.items():
        try:
            productos, hubo_error_http = escanear_categoria(nombre, ruta)
            if not productos:
                categorias_vacias.append(nombre)
            if hubo_error_http:
                errores.append((nombre, "Error HTTP/red; ver diagnóstico de página"))

            duplicados = sum(
                1 for url in productos if url in catalogo_global
            )

            for url, producto in productos.items():
                if url not in catalogo_global:
                    catalogo_global[url] = {
                        **producto,
                        "categoria": nombre,
                        "proveedor": "ZonaDigital",
                    }

            print(f"Duplicados con categorías anteriores: {duplicados}")

        except Exception as error:
            errores.append((nombre, str(error)))
            print(f"[ERROR] Categoría {nombre}: {error}")
            continue

    print("\n" + "=" * 70)
    print("RESUMEN FINAL")
    print("=" * 70)
    print(f"Categorías configuradas: {len(CATEGORIAS)}")
    print(f"Productos únicos globales: {len(catalogo_global)}")
    print(f"Categorías vacías: {len(categorias_vacias)}")
    print(f"Categorías con errores HTTP/red: {len(errores)}")

    if categorias_vacias:
        print("Categorías sin productos:")
        for categoria in categorias_vacias:
            print(f"- {categoria}")

    if errores:
        print("Errores:")
        for categoria, error in errores:
            print(f"- {categoria}: {error}")

    print("\nPrueba terminada. No se generaron archivos.")

    # Una ejecución sin productos no debe aparecer como exitosa en Actions.
    if not catalogo_global:
        print("[FALLO] No se detectó ningún producto. Revisar diagnóstico HTML.")
        sys.exit(1)


if __name__ == "__main__":
    main()

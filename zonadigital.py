
import re
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

def obtener_html(url):
    respuesta = SESSION.get(url, timeout=35)
    respuesta.raise_for_status()
    return respuesta.text

def extraer_productos(html):
    soup = BeautifulSoup(html, "html.parser")
    encontrados = {}

    # Selector observado en el HTML de ZonaDigital.
    tarjetas = soup.select("app-item-gift")

    # Alternativa por si alguna categoría usa tarjetas diferentes.
    if not tarjetas:
        enlaces = soup.select('a[href*="/producto/"]')
        tarjetas = []
        vistos = set()
        for enlace in enlaces:
            href = enlace.get("href", "")
            if href and href not in vistos:
                vistos.add(href)
                tarjetas.append(enlace)

    for tarjeta in tarjetas:
        enlace = tarjeta.select_one('a[href*="/producto/"]')
        titulo = tarjeta.select_one(".item-gift__content-title")

        if not enlace and tarjeta.name == "a":
            enlace = tarjeta

        if not enlace:
            continue

        url_producto = normalizar_url(enlace.get("href", ""))
        if "/producto/" not in url_producto:
            continue

        if titulo:
            nombre = titulo.get_text(" ", strip=True)
        else:
            nombre = enlace.get_text(" ", strip=True)

        if not nombre:
            nombre = enlace.get("title", "").strip()

        if not nombre:
            continue

        precio_elemento = tarjeta.select_one(
            "app-item-price-gift .price, .item-gift__price .price, .price"
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

    print(f"\n{'=' * 70}")
    print(f"CATEGORÍA: {nombre_categoria}")
    print(f"URL: {url_base}")
    print("=" * 70)

    # La paginación observada es acumulativa: page=5 puede devolver
    # más productos que page=1, no solo una página individual.
    for pagina in range(1, 101):
        if pagina == 1:
            url = url_base
        else:
            url = f"{url_base}?page={pagina}"

        try:
            html = obtener_html(url)
            productos = extraer_productos(html)
        except requests.RequestException as error:
            print(f"[ERROR] Página {pagina}: {error}")
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

        # Dos respuestas consecutivas sin novedades indican que
        # probablemente alcanzamos el final del catálogo.
        if pagina > 1 and paginas_sin_novedades >= 2:
            print("Fin probable del catálogo: no aparecen productos nuevos.")
            break

        time.sleep(0.4)

    for producto in productos_categoria.values():
        print(f"- {producto['nombre']}")
        print(f"  Precio: {producto['precio']}")
        print(f"  URL: {producto['url']}")

    print(f"Total observado en {nombre_categoria}: {len(productos_categoria)}")
    return productos_categoria

def main():
    catalogo_global = {}
    errores = []

    print("ABC GAMING | ZONADIGITAL | MODO DE PRUEBA")
    print("No se guardarán archivos.")
    print(f"Categorías configuradas: {len(CATEGORIAS)}")

    for nombre, ruta in CATEGORIAS.items():
        try:
            productos = escanear_categoria(nombre, ruta)

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
    print(f"Categorías con errores: {len(errores)}")

    if errores:
        for categoria, error in errores:
            print(f"- {categoria}: {error}")

    print("\nPrueba terminada. No se generaron archivos.")

if __name__ == "__main__":
    main()
  

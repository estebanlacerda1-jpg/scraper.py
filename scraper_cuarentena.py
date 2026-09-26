# =========================================================
# ABC GAMING - SCRAPER DE CUARENTENA
#
# Procesa solamente las categorías que fallaron en el scraper
# principal. NO modifica ni borra html_raw.
#
# Usa la configuración y parsers del scraper.py principal.
# Guarda los HTML/JSON para poder analizarlos posteriormente.
# =========================================================

import os
import csv
import json
import asyncio
import hashlib
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

import scraper as base


CARPETA_CUARENTENA = "cuarentena_raw"
REPORTE = "reporte_cuarentena.csv"

# Categorías que actualmente están dando 0 productos, 403, 404
# o errores de navegación según reporte_corrida.csv.
#
# La lista se puede ampliar sin tocar el scraper principal.
CUARENTENA = [
    "Alpha PS4 Secundaria",

    "DigitalWorld PS4",
    "DigitalWorld PS5",
    "DigitalWorld Switch",
    "DigitalWorld VR",
    "DigitalWorld Xbox",

    "Dix FC Points",
    "Dix Fortnite",
    "Dix Nintendo",
    "Dix PS3",
    "Dix PS4",
    "Dix PS5",
    "Dix Playstation",
    "Dix Razer",
    "Dix Steam",
    "Dix Xbox",

    "JDP4P5 Nintendo Online",
    "JDP4P5 Switch",

    "MDQ PSN Card",

    "PortalGames PS3",
    "PortalGames PS4",
    "PortalGames PS5",
    "PortalGames Switch",

    "TodoDigital PS4",
    "TodoDigital PS5",
    "TodoDigital Switch",

    "UruguayDigital GamePass",
    "UruguayDigital Nintendo",
    "UruguayDigital PS3",
    "UruguayDigital PS4",
    "UruguayDigital PS5",
    "UruguayDigital PSN Plus",
    "UruguayDigital Switch1",
    "UruguayDigital Switch2",
    "UruguayDigital Xbox One",
    "UruguayDigital Xbox XS",

    "UYJuegos GiftCard Amazon",
    "UYJuegos GiftCard iTunes",
    "UYJuegos Nintendo2",
    "UYJuegos PC",
    "UYJuegos PS4",
    "UYJuegos PS4 VR",
    "UYJuegos Xbox One",
    "UYJuegos Xbox XS",

    "WebGame GiftCards",
    "WebGame PS4",
    "WebGame PS5",

    "ZonaDigital Apple",
    "ZonaDigital Fortnite",
]


# ---------------------------------------------------------
# UTILIDADES
# ---------------------------------------------------------

def slug(texto):
    return base.slug(texto)


def carpeta_categoria(nombre):
    ruta = os.path.join(CARPETA_CUARENTENA, slug(nombre))
    os.makedirs(ruta, exist_ok=True)
    return ruta


def guardar(ruta, contenido):
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(contenido)


def firma(texto):
    return hashlib.md5(
        texto.encode("utf-8", errors="ignore")
    ).hexdigest()


def diagnostico_html(html):
    soup = BeautifulSoup(html, "html.parser")

    titulo = (
        soup.title.get_text(" ", strip=True)
        if soup.title
        else "(sin titulo)"
    )

    return {
        "bytes": len(html),
        "titulo": titulo[:200],
        "li_product": len(soup.select("li.product")),
        "div_product": len(soup.select("div.product")),
        "product_small": len(soup.select(".product-small")),
        "type_product": len(soup.select(".type-product")),
        "product_grid_item": len(soup.select(".product-grid-item")),
        "wd_product": len(soup.select(".wd-product")),
        "product_item": len(soup.select(".product-item")),
        "js_item_product": len(soup.select(".js-item-product")),
        "uruguaydigital_cards": len(
            soup.select(
                "li.d-flex.no-wrap.justify-content-start.align-items-center"
            )
        ),
        "jdp4p5_cards": len(soup.select("div.js-item-product")),
        "zonadigital_cards": len(soup.select("div.item-gift__content")),
    }


def nombre_categoria_real(nombre):
    if nombre not in base.CATALOGOS:
        raise KeyError(
            f"La categoría '{nombre}' no existe en CATALOGOS de scraper.py"
        )
    return base.CATALOGOS[nombre]


# ---------------------------------------------------------
# URLS
# ---------------------------------------------------------

def url_cuarentena(tipo, url, num):
    """
    Usa la misma lógica del scraper principal para poder comparar
    directamente los resultados.
    """
    return base.url_pagina(tipo, url, num)


# ---------------------------------------------------------
# DESCARGA HTTP
# ---------------------------------------------------------

def descargar_requests_cuarentena(
    tipo,
    url,
    nombre,
    filas,
    max_paginas=30,
):
    carpeta = carpeta_categoria(nombre)
    rutas = []
    firma_anterior = None

    for num in range(1, max_paginas + 1):
        pu = url_cuarentena(tipo, url, num)

        try:
            r = requests.get(
                pu,
                headers=base.HEADERS,
                timeout=30,
                allow_redirects=True,
            )

            html = r.text

            nombre_archivo = f"p{num}_http{r.status_code}.html"
            ruta = os.path.join(carpeta, nombre_archivo)
            guardar(ruta, html)

            diag = diagnostico_html(html)

            filas.append({
                "fecha_utc": datetime.now(timezone.utc).isoformat(),
                "tienda": nombre,
                "tipo": tipo,
                "pagina": num,
                "url": pu,
                "metodo": "requests",
                "http_status": r.status_code,
                "bytes": diag["bytes"],
                "titulo": diag["titulo"],
                "productos": "",
                "motivo": (
                    f"HTTP {r.status_code}"
                    if r.status_code >= 400
                    else ""
                ),
                "archivo_html": ruta,
            })

            # Si fue un 404/403/etc. dejamos el HTML guardado
            # y probamos Playwright más adelante.
            if r.status_code >= 400:
                break

            if not base.hay_cards(tipo, html):
                break

            f = firma(html)
            if f == firma_anterior:
                break

            firma_anterior = f
            rutas.append(ruta)

        except Exception as e:
            filas.append({
                "fecha_utc": datetime.now(timezone.utc).isoformat(),
                "tienda": nombre,
                "tipo": tipo,
                "pagina": num,
                "url": pu,
                "metodo": "requests",
                "http_status": "",
                "bytes": "",
                "titulo": "",
                "productos": "",
                "motivo": f"EXCEPCION: {e}",
                "archivo_html": "",
            })
            break

    return rutas


# ---------------------------------------------------------
# DESCARGA PLAYWRIGHT
# ---------------------------------------------------------

async def descargar_playwright_cuarentena(
    tipo,
    url,
    nombre,
    page,
    filas,
    max_paginas=30,
):
    carpeta = carpeta_categoria(nombre)
    rutas = []
    firma_anterior = None

    espera = "networkidle" if tipo == "zonadigital" else "domcontentloaded"
    timeout = 60000 if tipo == "zonadigital" else 50000

    for num in range(1, max_paginas + 1):
        pu = url_cuarentena(tipo, url, num)

        try:
            resp = await page.goto(
                pu,
                wait_until=espera,
                timeout=timeout,
            )

            status = resp.status if resp else ""

            await page.wait_for_timeout(
                6000 if tipo == "zonadigital" else 4000
            )

            if tipo == "zonadigital":
                for _ in range(6):
                    await page.mouse.wheel(0, 4000)
                    await page.wait_for_timeout(1200)

            html = await page.content()

            nombre_archivo = (
                f"p{num}_playwright"
                f"{('_http' + str(status)) if status else ''}.html"
            )
            ruta = os.path.join(carpeta, nombre_archivo)
            guardar(ruta, html)

            diag = diagnostico_html(html)

            filas.append({
                "fecha_utc": datetime.now(timezone.utc).isoformat(),
                "tienda": nombre,
                "tipo": tipo,
                "pagina": num,
                "url": pu,
                "metodo": "playwright",
                "http_status": status,
                "bytes": diag["bytes"],
                "titulo": diag["titulo"],
                "productos": "",
                "motivo": (
                    f"HTTP {status}"
                    if isinstance(status, int) and status >= 400
                    else ""
                ),
                "archivo_html": ruta,
            })

            # Aunque el servidor responda 403/404, conservamos
            # el HTML porque puede contener un challenge o página
            # alternativa útil para desarrollar el parser.
            if isinstance(status, int) and status >= 400:
                break

            if not base.hay_cards(tipo, html):
                break

            f = firma(html)
            if f == firma_anterior:
                break

            firma_anterior = f
            rutas.append(ruta)

        except Exception as e:
            filas.append({
                "fecha_utc": datetime.now(timezone.utc).isoformat(),
                "tienda": nombre,
                "tipo": tipo,
                "pagina": num,
                "url": pu,
                "metodo": "playwright",
                "http_status": "",
                "bytes": "",
                "titulo": "",
                "productos": "",
                "motivo": f"EXCEPCION: {e}",
                "archivo_html": "",
            })
            break

    return rutas


# ---------------------------------------------------------
# PARSEO
# ---------------------------------------------------------

def parsear_archivos(nombre, cfg, rutas):
    """
    Reutiliza exactamente los parsers del scraper principal.
    """
    if not rutas:
        return []

    return base.parsear_categoria(nombre, cfg, rutas)


def completar_filas_productos(filas, nombre, productos):
    """
    Agrega el resultado del parser al reporte.
    """
    for fila in reversed(filas):
        if fila["tienda"] == nombre:
            # Solo anotamos productos en las páginas que fueron
            # descargadas en esta categoría. El total de la categoría
            # queda además en una fila RESUMEN.
            pass

    filas.append({
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "tienda": nombre,
        "tipo": "RESUMEN",
        "pagina": "",
        "url": "",
        "metodo": "",
        "http_status": "",
        "bytes": "",
        "titulo": "",
        "productos": len(productos),
        "motivo": (
            "RECUPERADA"
            if productos
            else "SIN PRODUCTOS / REQUIERE PARSER"
        ),
        "archivo_html": "",
    })


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

async def main():
    os.makedirs(CARPETA_CUARENTENA, exist_ok=True)

    print("=" * 70)
    print("ABC GAMING - CUARENTENA")
    print("=" * 70)
    print(f"Categorías a revisar: {len(CUARENTENA)}")
    print()

    filas = []
    recuperadas = []
    sin_productos = []

    # Verificación temprana para no tener errores silenciosos
    for nombre in CUARENTENA:
        if nombre not in base.CATALOGOS:
            raise RuntimeError(
                f"CUARENTENA contiene una categoría que no existe: {nombre}"
            )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        page = await browser.new_page(
            user_agent=base.HEADERS["User-Agent"],
            locale="es-419",
            viewport={"width": 1366, "height": 768},
            extra_http_headers={
                "Accept-Language": "es-419,es;q=0.9"
            },
        )

        for nombre in CUARENTENA:
            cfg = base.CATALOGOS[nombre]
            tipo = cfg["tipo"]
            url = cfg["url"]

            print("-" * 70)
            print(f"[CUARENTENA] {nombre}")
            print(f"tipo={tipo}")
            print(f"url={url}")

            rutas = []

            try:
                # 1) Primero intentamos el mismo método del principal
                if tipo in (
                    "woocommerce",
                    "tiendanube",
                    "tiendanegocio",
                ):
                    rutas = descargar_requests_cuarentena(
                        tipo,
                        url,
                        nombre,
                        filas,
                    )

                # 2) Siempre hacemos un intento Playwright adicional
                # para las categorías problemáticas.
                rutas_pw = await descargar_playwright_cuarentena(
                    "playwright" if tipo == "woocommerce" else tipo,
                    url,
                    nombre,
                    page,
                    filas,
                )

                # Si Playwright consiguió páginas, usamos esas para parsear.
                if rutas_pw:
                    rutas = rutas_pw

                # Para tipos que ya son Playwright, el bloque anterior
                # es el intento principal.
                if tipo not in (
                    "woocommerce",
                    "tiendanube",
                    "tiendanegocio",
                ):
                    rutas = rutas_pw

            except Exception as e:
                filas.append({
                    "fecha_utc": datetime.now(timezone.utc).isoformat(),
                    "tienda": nombre,
                    "tipo": tipo,
                    "pagina": "",
                    "url": url,
                    "metodo": "",
                    "http_status": "",
                    "bytes": "",
                    "titulo": "",
                    "productos": "",
                    "motivo": f"ERROR GENERAL: {e}",
                    "archivo_html": "",
                })

            # Parseamos solamente HTML que tenga cards conocidas.
            productos = []

            try:
                rutas_parseables = []

                for ruta in rutas:
                    try:
                        with open(ruta, encoding="utf-8") as f:
                            html = f.read()

                        if base.hay_cards(
                            "playwright" if tipo == "woocommerce" else tipo,
                            html,
                        ):
                            rutas_parseables.append(ruta)
                    except Exception:
                        pass

                if rutas_parseables:
                    productos = parsear_archivos(
                        nombre,
                        cfg,
                        rutas_parseables,
                    )

            except Exception as e:
                filas.append({
                    "fecha_utc": datetime.now(timezone.utc).isoformat(),
                    "tienda": nombre,
                    "tipo": tipo,
                    "pagina": "",
                    "url": url,
                    "metodo": "parseo",
                    "http_status": "",
                    "bytes": "",
                    "titulo": "",
                    "productos": "",
                    "motivo": f"ERROR PARSEO: {e}",
                    "archivo_html": "",
                })

            completar_filas_productos(
                filas,
                nombre,
                productos,
            )

            if productos:
                recuperadas.append((nombre, len(productos)))
                print(f"  >>> RECUPERADA: {len(productos)} productos")
            else:
                sin_productos.append(nombre)
                print("  >>> SIGUE EN CUARENTENA: 0 productos")

        await browser.close()

    # -----------------------------------------------------
    # REPORTE CSV
    # -----------------------------------------------------

    campos = [
        "fecha_utc",
        "tienda",
        "tipo",
        "pagina",
        "url",
        "metodo",
        "http_status",
        "bytes",
        "titulo",
        "productos",
        "motivo",
        "archivo_html",
    ]

    with open(
        REPORTE,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=campos,
        )
        writer.writeheader()
        writer.writerows(filas)

    print()
    print("=" * 70)
    print("RESULTADO CUARENTENA")
    print("=" * 70)

    print(f"Recuperadas: {len(recuperadas)}")
    for nombre, cantidad in recuperadas:
        print(f"  OK {nombre}: {cantidad}")

    print()
    print(f"Siguen con problemas: {len(sin_productos)}")
    for nombre in sin_productos:
        print(f"  -- {nombre}")

    print()
    print(f"Reporte: {REPORTE}")
    print(f"HTML guardados en: {CARPETA_CUARENTENA}/")
    print()
    print(
        "IMPORTANTE: ningún HTML de cuarentena se borra automáticamente."
    )


if __name__ == "__main__":
    asyncio.run(main())

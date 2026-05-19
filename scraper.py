# =========================================================
# ABC GAMING - SCRAPER PRO FINAL
# NORMALIZACION + MONEDAS + MEJORES PRECIOS + MULTI HOJAS
# =========================================================

import asyncio


import re
import asyncio
import requests
import pandas as pd

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# =========================================================
# CONFIG
# =========================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

PAGINAS = 2

# =========================================================
# CONVERSIONES
# =========================================================

USD_TO_UYU = 40
ARS_TO_UYU = 0.035

# =========================================================
# NORMALIZACION NOMBRES
# =========================================================

def normalizar_nombre(nombre):

    basura = [
        "DIGITAL",
        "PRIMARIO",
        "SECUNDARIO",
        "CUENTA",
        "OFFLINE",
        "ONLINE",
        "PS4",
        "PS5",
        "PS3",
        "XBOX",
        "NINTENDO",
        "STANDARD",
        "DELUXE",
        "ULTIMATE",
        "LATAM",
        "GLOBAL",
        "STEAM KEY",
        "KEY",
        "PC"
    ]

    nombre = str(nombre).upper()

    for b in basura:
        nombre = nombre.replace(b, "")

    nombre = re.sub(r"\s+", " ", nombre)

    return nombre.strip()

# =========================================================
# DETECTAR MONEDA
# =========================================================

def detectar_moneda(precio_txt):

    txt = str(precio_txt).upper()

    if "USD" in txt or "US$" in txt:
        return "USD"

    if "ARS" in txt:
        return "ARS"

    if "$U" in txt or "UYU" in txt:
        return "UYU"

    return "UYU"

# =========================================================
# LIMPIAR PRECIO
# =========================================================

def limpiar_precio(precio_txt):

    txt = str(precio_txt).upper()

    moneda = detectar_moneda(txt)

    numero = re.search(r"[\d,.]+", txt)

    if not numero:
        return None, moneda

    valor = numero.group()

    # 1.299,99 -> 1299.99
    valor = valor.replace(".", "")
    valor = valor.replace(",", ".")

    try:
        valor = float(valor)
    except:
        return None, moneda

    return valor, moneda

# =========================================================
# CONVERTIR A UYU
# =========================================================

def convertir_a_uyu(valor, moneda):

    if valor is None:
        return None

    if moneda == "USD":
        return round(valor * USD_TO_UYU, 2)

    if moneda == "ARS":
        return round(valor * ARS_TO_UYU, 2)

    return round(valor, 2)

# =========================================================
# CLASIFICAR PLATAFORMA
# =========================================================

def detectar_plataforma(nombre, tienda):

    txt = f"{nombre} {tienda}".upper()

    if "PS5" in txt:
        return "PS5"

    if "PS4" in txt:
        return "PS4"

    if "XBOX" in txt:
        return "Xbox"

    if "NINTENDO" in txt or "SWITCH" in txt:
        return "Nintendo"

    if "STEAM" in txt:
        return "Steam"

    if "FORTNITE" in txt:
        return "Fortnite"

    if "ROBLOX" in txt or "ROBUX" in txt:
        return "Robux"

    if "GIFT" in txt or "CARD" in txt:
        return "GiftCards"

    return "Otros"

# =========================================================
# SCRAPER WOOCOMMERCE
# =========================================================

def scrape_woocommerce(url, paginas=PAGINAS):

    productos = []

    selectors = [
        "li.product",
        "div.product",
        ".product-small",
        ".type-product",
        ".product-grid-item"
    ]

    for page in range(1, paginas + 1):

        page_url = url if page == 1 else f"{url.rstrip('/')}/page/{page}/"

        try:

            r = requests.get(page_url, headers=HEADERS, timeout=30)

            soup = BeautifulSoup(r.text, "html.parser")

            cards = []

            for sel in selectors:
                cards.extend(soup.select(sel))

            for c in cards:

                try:

                    nombre_el = c.select_one(
                        "h2, h3, h4, .product-title, .woocommerce-loop-product__title"
                    )

                    precio_el = c.select_one(".price, .amount, bdi")

                    if not nombre_el or not precio_el:
                        continue

                    nombre = nombre_el.get_text(strip=True)

                    precio_txt = precio_el.get_text(" ", strip=True)

                    valor, moneda = limpiar_precio(precio_txt)

                    if valor is None:
                        continue

                    link_el = c.select_one("a")

                    link = link_el["href"] if link_el else url

                    productos.append({
                        "nombre": nombre,
                        "precio_original": precio_txt,
                        "precio": valor,
                        "moneda": moneda,
                        "precio_uyu": convertir_a_uyu(valor, moneda),
                        "link": link
                    })

                except:
                    continue

        except Exception as e:
            print("ERROR:", e)

    return productos

# =========================================================
# MAIN
# =========================================================

async def main():

    todos = []

    TIENDAS = {

        "DigitalWorld PS4": {
            "url": "https://digitalworldpsn.com/es/juegos-digitales-ps4/?v=1b23f8a4c97c"
        },

        "DigitalWorld PS5": {
            "url": "https://digitalworldpsn.com/es/juegos-digitales-ps5/?v=1b23f8a4c97c"
        },

        "Dix PS4": {
            "url": "https://dixgamer.com/categoria-producto/juegos/ps4/"
        },

        "Dix PS5": {
            "url": "https://dixgamer.com/categoria-producto/juegos/ps5/"
        }

    }

    # =====================================================
    # SCRAPING
    # =====================================================

    for tienda, cfg in TIENDAS.items():

        print(f"\nScrapeando {tienda}")

        productos = scrape_woocommerce(cfg["url"])

        print(f" -> {len(productos)} productos")

        for p in productos:

            p["tienda"] = tienda

            p["nombre_normalizado"] = normalizar_nombre(
                p["nombre"]
            )

            p["plataforma"] = detectar_plataforma(
                p["nombre"],
                tienda
            )

            todos.append(p)

    # =====================================================
    # DATAFRAME
    # =====================================================

    df = pd.DataFrame(todos)

    if len(df) == 0:
        print("NO HAY PRODUCTOS")
        return

    # =====================================================
    # FILTRO PRECIOS RAROS
    # =====================================================

    df = df[
        (df["precio_uyu"] > 5) &
        (df["precio_uyu"] < 50000)
    ]

    # =====================================================
    # ORDENAR
    # =====================================================

    df = df.sort_values("precio_uyu")

    # =====================================================
    # MEJOR PRECIO POR JUEGO
    # =====================================================

    idx = df.groupby(
        "nombre_normalizado"
    )["precio_uyu"].idxmin()

    mejores = df.loc[idx].copy()

    mejores = mejores.sort_values("precio_uyu")

    # =====================================================
    # EXPORTAR
    # =====================================================

    ARCHIVO = "catalogo_completo_abc_gaming.xlsx"

    with pd.ExcelWriter(
        ARCHIVO,
        engine="openpyxl"
    ) as writer:

        # TODO
        df.to_excel(
            writer,
            sheet_name="TODO",
            index=False
        )

        # MEJORES
        mejores.to_excel(
            writer,
            sheet_name="MEJORES_PRECIOS",
            index=False
        )

        # POR PLATAFORMA
        plataformas = df["plataforma"].unique()

        for plataforma in plataformas:

            temp = df[
                df["plataforma"] == plataforma
            ]

            if len(temp) == 0:
                continue

            nombre_hoja = plataforma[:31]

            temp.to_excel(
                writer,
                sheet_name=nombre_hoja,
                index=False
            )

        # ENEBA
        eneba = df[
            df["tienda"].str.contains(
                "ENEBA",
                case=False,
                na=False
            )
        ]

        if len(eneba) > 0:

            eneba.to_excel(
                writer,
                sheet_name="ENEBA",
                index=False
            )

    print("\n===================================")
    print("EXCEL EXPORTADO")
    print("===================================")

    print(f"Archivo: {ARCHIVO}")

    print(f"Total productos: {len(df)}")

    print(f"Mejores precios: {len(mejores)}")

# =========================================================
# EJECUTAR
# =========================================================

asyncio.run(main())

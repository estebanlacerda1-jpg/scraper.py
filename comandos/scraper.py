# =========================================================
# ABC GAMING - SCRAPER FINAL (v2 - fases separadas)
#
# Cambio de arquitectura respecto a la versión anterior:
#   FASE 1 - Descarga: recorre las ~20 tiendas + Eneba, baja el HTML
#            (o JSON, para Shopify) crudo de cada página y lo guarda
#            en disco, SIN parsear nombre/precio todavía.
#   FASE 2 - Parseo: lee esos archivos ya guardados y ahí sí aplica
#            los selectores de cada tienda para extraer productos.
#            No vuelve a tocar la red.
#   FASE 3 - Se borran los HTML/JSON de la corrida (no se commitean).
#   FASE 4 - Reporte: reporte_corrida.csv con páginas descargadas,
#            productos parseados y error (si hubo) por categoría —
#            para ver de un vistazo cuál falló, sin bucear en el log.
#   FASE 5 - Excel + CSV final (igual que la versión anterior).
#
# Todo lo demás (detección de moneda, limpieza de precios, detección
# de plataforma, formato del Excel) es igual que antes.
# =========================================================

import os
import re
import json
import shutil
import hashlib
import asyncio

import requests
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# =========================================================
# CONFIG GLOBAL
# =========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124 Safari/537.36"
    )
}

LIMITE_PAGINAS_DESCARGA = 30  # tope de seguridad para la fase de descarga
CARPETA_HTML = "html_raw"    # se borra al final de cada corrida

# =========================================================
# COTIZACIONES - valores de RESPALDO
#
# Estos son los que se usan si falla la consulta a las APIs
# (sin internet, API caída, cambio de formato, etc). Se
# actualizan automáticamente al arrancar main() llamando a
# actualizar_cotizaciones() - no hace falta tocarlos a mano,
# pero conviene refrescarlos cada tanto para que el respaldo
# no quede demasiado viejo si las APIs empiezan a fallar seguido.
# =========================================================

USD_TO_UYU = 40.5                  # 1 USD ≈ 40,5 UYU (venta, 14-sep-2026)
ARS_TO_UYU = 40.5 / 1545           # 1 USD ≈ 1.545 ARS (dólar blue, 14-sep-2026)
COP_TO_UYU = 40.5 / 3072           # 1 USD ≈ 3.072 COP (TRM, 14-sep-2026)
CLP_TO_UYU = 40.5 / 941            # 1 USD ≈ 941 CLP (14-sep-2026)
MXN_TO_UYU = 40.5 / 17.70          # 1 USD ≈ 17,70 MXN (14-sep-2026)
BRL_TO_UYU = 40.5 / 5.12           # 1 USD ≈ 5,12 BRL (14-sep-2026)
EUR_TO_UYU = 40.5 * 1.15           # 1 EUR ≈ 1,15 USD (14-sep-2026)


def actualizar_cotizaciones():
    """
    Pisa las constantes *_TO_UYU con la cotización del día, para no
    depender de valores fijos en el código (pensado para la corrida
    diaria automática en GitHub Actions).

    Fuentes, ambas gratuitas y sin API key:
      - open.er-api.com  -> USD, COP, CLP, MXN, BRL, EUR, UYU (tipo de
                             cambio de mercado/oficial)
      - dolarapi.com     -> dólar blue ARS (más realista que el oficial
                             para el mercado gamer/gift cards argentino;
                             si esta consulta falla, se usa el ARS oficial
                             que trae open.er-api.com como respaldo)

    Si ambas consultas fallan (sin internet, caídas, cambio de formato),
    quedan los valores de respaldo definidos arriba y el scraper sigue
    funcionando igual - nunca tira una excepción hacia afuera.
    """
    global USD_TO_UYU, ARS_TO_UYU, COP_TO_UYU, CLP_TO_UYU, MXN_TO_UYU, BRL_TO_UYU, EUR_TO_UYU

    uyu_por_usd = None
    ars_por_usd = None

    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("result") == "success":
            rates = data.get("rates", {})
            uyu_por_usd = rates.get("UYU")
            if uyu_por_usd:
                USD_TO_UYU = uyu_por_usd
                if rates.get("COP"):
                    COP_TO_UYU = uyu_por_usd / rates["COP"]
                if rates.get("CLP"):
                    CLP_TO_UYU = uyu_por_usd / rates["CLP"]
                if rates.get("MXN"):
                    MXN_TO_UYU = uyu_por_usd / rates["MXN"]
                if rates.get("BRL"):
                    BRL_TO_UYU = uyu_por_usd / rates["BRL"]
                if rates.get("EUR"):
                    EUR_TO_UYU = uyu_por_usd / rates["EUR"]
                ars_por_usd = rates.get("ARS")  # oficial - puede pisarlo el blue más abajo
                print(f"   Cotizaciones actualizadas (open.er-api.com) - USD/UYU: {uyu_por_usd:.3f}")
            else:
                print("   ATENCION: open.er-api.com no trajo UYU, se usan valores de respaldo")
        else:
            print("   ATENCION: respuesta inesperada de open.er-api.com, se usan valores de respaldo")
    except Exception as e:
        print(f"   ATENCION: no se pudo consultar open.er-api.com ({e}), se usan valores de respaldo")

    try:
        r = requests.get("https://dolarapi.com/v1/dolares/blue", timeout=10)
        r.raise_for_status()
        data = r.json()
        venta = float(data.get("venta") or 0)
        if venta > 0:
            ars_por_usd = venta
            print(f"   Dólar blue ARS actualizado (dolarapi.com): {venta}")
    except Exception as e:
        print(f"   ATENCION: no se pudo obtener el dólar blue ({e}), se usa ARS oficial/respaldo")

    if uyu_por_usd and ars_por_usd:
        ARS_TO_UYU = uyu_por_usd / ars_por_usd

    print(
        f"   Vigentes -> USD:{USD_TO_UYU:.3f}  ARS:{USD_TO_UYU/ARS_TO_UYU:.1f}  "
        f"COP:{USD_TO_UYU/COP_TO_UYU:.1f}  CLP:{USD_TO_UYU/CLP_TO_UYU:.1f}  "
        f"MXN:{USD_TO_UYU/MXN_TO_UYU:.2f}  BRL:{USD_TO_UYU/BRL_TO_UYU:.2f}  "
        f"EUR:{USD_TO_UYU/EUR_TO_UYU:.4f}"
        " (unidades por USD, salvo EUR que es USD por EUR)"
    )


# =========================================================
# MONEDAS POR TIENDA
#
# Si una tienda no está aquí, se detecta automáticamente
# del texto del precio. Las tiendas .com.ar siempre ARS.
# =========================================================

MONEDA_TIENDA = {
    # Shopify - precios en USD
    "Alpha PS5 Primaria": "USD",
    "Alpha PS5 Secundaria": "USD",
    "Alpha PS4 Primaria": "USD",
    "Alpha PS4 Secundaria": "USD",
    "Alpha Xbox": "USD",
    "GamerLab PS4": "USD",
    "GamerLab PS5": "USD",
    "GamerLab EA Play": "USD",
    "GamerLab PSN": "USD",
    "GamerLab All": "USD",

    # WooCommerce - precios en UYU
    "DigitalWorld PS4": "UYU",
    "DigitalWorld PS5": "UYU",
    "DigitalWorld VR": "UYU",
    "DigitalWorld Xbox": "UYU",
    "DigitalWorld Switch": "UYU",
    "UruguayDigital PS3": "UYU",
    "UruguayDigital PS4": "UYU",
    "UruguayDigital PS5": "UYU",
    "UruguayDigital Switch1": "UYU",
    "UruguayDigital Switch2": "UYU",
    "UruguayDigital Xbox One": "UYU",
    "UruguayDigital Xbox XS": "UYU",
    "UruguayDigital PSN Plus": "UYU",
    "UruguayDigital Nintendo": "UYU",
    "UruguayDigital GamePass": "UYU",
    "UYJuegos PS4": "UYU",
    "UYJuegos PS4 VR": "UYU",
    "UYJuegos PS5": "UYU",
    "UYJuegos PC": "UYU",
    "UYJuegos Xbox XS": "UYU",
    "UYJuegos Xbox One": "UYU",
    "UYJuegos Nintendo": "UYU",
    "UYJuegos Nintendo2": "UYU",
    "UYJuegos GiftCard Amazon": "UYU",
    "UYJuegos GiftCard iTunes": "UYU",
    "WebGame PS4": "UYU",
    "WebGame PS5": "UYU",
    "WebGame GiftCards": "UYU",

    # Tiendas argentinas - ARS
    "PortalGames PS3": "ARS",
    "PortalGames PS4": "ARS",
    "PortalGames PS5": "ARS",
    "PortalGames Switch": "ARS",
    "MDQ PS5": "ARS",
    "MDQ PS4": "ARS",
    "MDQ PS3": "ARS",
    "MDQ PS Plus": "ARS",
    "MDQ PSN Card": "ARS",
    "MDQ Fortnite": "ARS",
    "PlayX PS4": "ARS",
    "PlayX PS5": "ARS",
    "PlayX Xbox One": "ARS",
    "PlayX Xbox XS": "ARS",
    "PlayX Switch": "ARS",
    "PlayX Switch 2": "ARS",
    "PlayX Steam": "ARS",
    "PlayX PSN Plus": "ARS",
    "PlayX GamePass": "ARS",
    "PlayX Switch Online": "ARS",
    "TodoDigital PS4": "ARS",
    "TodoDigital PS5": "ARS",
    "TodoDigital Switch": "ARS",
    "JDP4P5 PS4": "ARS",
    "JDP4P5 PS5": "ARS",
    "JDP4P5 Switch": "ARS",
    "JDP4P5 PS Plus": "ARS",
    "JDP4P5 GamePass": "ARS",
    "JDP4P5 Nintendo Online": "ARS",

    # Dix - precios en UYU (salvo Steam/Xbox, en MXN)
    "Dix Fortnite": "UYU",
    "Dix PS5": "UYU",
    "Dix PS4": "UYU",
    "Dix PS3": "UYU",
    "Dix FC Points": "UYU",
    "Dix Nintendo": "UYU",
    "Dix Playstation": "UYU",
    "Dix Razer": "UYU",
    "Dix Steam": "MXN",
    "Dix Xbox": "MXN",

    # EstacionPlay - precios en ARS (tienda argentina)
    "EstacionPlay PS4": "ARS",
    "EstacionPlay PS5": "ARS",
    "EstacionPlay Memb": "ARS",

    # ZonaDigital - precios en CLP (pesos chilenos, sin etiqueta en el texto)
    "ZonaDigital PS4": "CLP",
    "ZonaDigital PS5": "CLP",
    "ZonaDigital PC Codigo": "CLP",
    "ZonaDigital PC Cuenta": "CLP",
    "ZonaDigital Xbox": "CLP",
    "ZonaDigital Apex": "CLP",
    "ZonaDigital Fortnite VB": "CLP",
    "ZonaDigital Fortnite": "CLP",
    "ZonaDigital GiftCard PSN": "CLP",
    "ZonaDigital GiftCard Steam": "CLP",
    "ZonaDigital Roblox": "CLP",
    "ZonaDigital GiftCard Xbox": "CLP",
    "ZonaDigital BattleNet": "CLP",
    "ZonaDigital Riot": "CLP",
    "ZonaDigital FreeFire": "CLP",
    "ZonaDigital Google Play": "CLP",
    "ZonaDigital Apple": "CLP",
    "ZonaDigital Switch": "CLP",
    "ZonaDigital Switch USA": "CLP",
    "ZonaDigital GamePass": "CLP",
    "ZonaDigital EA Play": "CLP",

    # Eneba - USD
    "Eneba": "USD",
}

# =========================================================
# NORMALIZACION
# =========================================================

BASURA_NOMBRES = [
    "DIGITAL", "PRIMARIO", "SECUNDARIO", "CUENTA",
    "OFFLINE", "ONLINE", "PS4", "PS5", "PS3",
    "XBOX", "NINTENDO", "STANDARD", "DELUXE", "ULTIMATE",
    "LATAM", "GLOBAL", "STEAM KEY", "KEY", "PC",
    "CODIGO", "CÓDIGO", "ACCOUNT",
]


def normalizar_nombre(nombre):
    nombre = str(nombre).upper()
    for b in BASURA_NOMBRES:
        nombre = nombre.replace(b, "")
    return re.sub(r"\s+", " ", nombre).strip()


def limpiar_nombre_eneba(nombre):
    remover = [
        "Código de Steam", "Steam Key", "Steam", "GLOBAL", "LATAM", "EUROPE",
        "United States", "UNITED STATES", "Xbox Live", "Xbox", "PSN", "Nintendo",
        "Código de", "Código", "Key",
    ]
    for r in remover:
        nombre = nombre.replace(r, "")
    return re.sub(r"\s+", " ", nombre).strip()


# =========================================================
# MONEDAS Y PRECIOS
# =========================================================

def detectar_moneda_texto(precio_txt):
    """Detecta moneda del texto del precio."""
    txt = str(precio_txt).upper()
    if "USD" in txt or "US$" in txt:
        return "USD"
    if "ARS" in txt:
        return "ARS"
    if "$U" in txt or "UYU" in txt:
        return "UYU"
    if "COP" in txt:
        return "COP"
    if "CLP" in txt:
        return "CLP"
    if "MXN" in txt:
        return "MXN"
    if "R$" in txt or "BRL" in txt:
        return "BRL"
    if "€" in txt or "EUR" in txt:
        return "EUR"
    return None  # No detectado - se usará moneda_tienda como fallback


def resolver_moneda(precio_txt, nombre_tienda):
    """
    Prioridad:
    1. Si el texto del precio tiene moneda explícita -> usar esa.
    2. Si la tienda tiene entrada en MONEDA_TIENDA -> usar esa.
    3. Fallback: UYU.
    """
    moneda_texto = detectar_moneda_texto(precio_txt)
    if moneda_texto:
        return moneda_texto
    tienda_moneda = MONEDA_TIENDA.get(nombre_tienda)
    if tienda_moneda:
        return tienda_moneda
    return "UYU"


def limpiar_numero(valor_txt):
    """
    Convierte un string numérico a float SIN asumir un formato fijo
    (latino "1.234,56" vs. estadounidense "1,234.56") - el formato se
    detecta por la posición de los separadores presentes.
    """
    tiene_punto = "." in valor_txt
    tiene_coma = "," in valor_txt

    if tiene_punto and tiene_coma:
        if valor_txt.rfind(",") > valor_txt.rfind("."):
            valor_txt = valor_txt.replace(".", "").replace(",", ".")  # 1.234,56
        else:
            valor_txt = valor_txt.replace(",", "")                    # 1,234.56
    elif tiene_coma:
        partes = valor_txt.split(",")
        if len(partes) == 2 and len(partes[1]) <= 2:
            valor_txt = valor_txt.replace(",", ".")
        else:
            valor_txt = valor_txt.replace(",", "")
    elif tiene_punto:
        partes = valor_txt.split(".")
        if not (len(partes) == 2 and len(partes[1]) <= 2):
            valor_txt = valor_txt.replace(".", "")

    return float(valor_txt)


def limpiar_precio(precio_txt, nombre_tienda=None):
    txt = str(precio_txt)

    if "MXN" in txt.upper():
        match_mxn = re.search(r'\$\s*(\d+(?:[.,]\d+)?)\s*(?:[^$]*?)\(\s*MXN\s*\)', txt, re.IGNORECASE)
        if not match_mxn:
            match_mxn = re.search(r'(\d+(?:[.,]\d+)?)\s*MXN', txt, re.IGNORECASE)
        if match_mxn:
            try:
                val = float(match_mxn.group(1).replace(",", "."))
                return val, "MXN"
            except Exception:
                pass

    moneda = resolver_moneda(txt, nombre_tienda or "")
    numero = re.search(r"[\d.,]+", txt)
    if not numero:
        return None, moneda

    valor_txt = numero.group().strip()
    try:
        return limpiar_numero(valor_txt), moneda
    except (ValueError, ZeroDivisionError):
        return None, moneda


def convertir_uyu(valor, moneda):
    if valor is None:
        return None
    if moneda == "USD":
        return round(valor * USD_TO_UYU, 2)
    if moneda == "ARS":
        return round(valor * ARS_TO_UYU, 2)
    if moneda == "COP":
        return round(valor * COP_TO_UYU, 2)
    if moneda == "CLP":
        return round(valor * CLP_TO_UYU, 2)
    if moneda == "MXN":
        return round(valor * MXN_TO_UYU, 2)
    if moneda == "BRL":
        return round(valor * BRL_TO_UYU, 2)
    if moneda == "EUR":
        return round(valor * EUR_TO_UYU, 2)
    return round(valor, 2)


def extraer_precio_eneba(texto):
    texto = texto.replace("Desde", "").replace("From", "").strip()
    match = re.search(r'(\d+[.,]?\d*)\s*US\$', texto)
    if match:
        try:
            return f"{float(match.group(1).replace(',', '.')):.2f} USD"
        except Exception:
            pass
    match2 = re.search(r'\$\s*(\d+[.,]\d+)', texto)
    if match2:
        try:
            return f"{float(match2.group(1).replace(',', '.')):.2f} USD"
        except Exception:
            pass
    return ""


def extraer_precio_real(card):
    """
    Extrae el precio VIGENTE de una card de WooCommerce, evitando el bug
    de tomar el `.price` completo cuando hay oferta (tachado + oferta).
    Prioriza el precio dentro de <ins> (oferta vigente).
    """
    ins_el = card.select_one(".price ins bdi, .price ins .amount, .price ins")
    if ins_el:
        return ins_el.get_text(" ", strip=True)

    bdi_el = card.select_one(".price bdi, bdi")
    if bdi_el:
        return bdi_el.get_text(" ", strip=True)

    amount_el = card.select_one(".price .amount, .amount")
    if amount_el:
        return amount_el.get_text(" ", strip=True)

    price_el = card.select_one(".price")
    if price_el:
        return price_el.get_text(" ", strip=True)

    return None


# =========================================================
# DETECTAR PLATAFORMA
# =========================================================

def detectar_plataforma(nombre, tienda, link="", tags=""):
    """
    Revisa nombre + tienda + link + tags - la plataforma real puede
    estar en el link (slug de la URL) o en los tags del producto
    aunque no esté en el nombre visible.
    """
    txt = f"{nombre} {tienda} {link} {tags}".upper()

    if "PS5" in txt:
        return "PS5"
    if "PS4" in txt:
        return "PS4"
    if "PS3" in txt:
        return "PS3"
    if "XBOX" in txt or "GAME PASS" in txt or "GAMEPASS" in txt:
        return "Xbox"
    if "NINTENDO" in txt or "SWITCH" in txt:
        return "Nintendo"
    if "STEAM" in txt:
        return "Steam"
    if "FORTNITE" in txt or "PAVOS" in txt or "V-BUCK" in txt:
        return "Fortnite"
    if "ROBLOX" in txt or "ROBUX" in txt:
        return "Robux"
    if "FREE FIRE" in txt or "FREEFIRE" in txt:
        return "Free Fire"
    if "GENSHIN" in txt:
        return "Genshin"
    if "VALORANT" in txt or "RIOT" in txt:
        return "Valorant"
    if "PUBG" in txt:
        return "PUBG"
    if "FC POINT" in txt or "FIFA" in txt or "FUT" in txt:
        return "FC Points"
    if "GTA" in txt or "SHARK" in txt:
        return "GTA"
    if "EA PLAY" in txt or "ORIGIN" in txt:
        return "EA Play"
    if "UBISOFT" in txt or "UPLAY" in txt:
        return "Ubisoft"
    if "EPIC" in txt:
        return "Epic Games"
    if "GOG" in txt:
        return "GOG"
    if "BATTLE" in txt or "BLIZZARD" in txt:
        return "BattleNet"
    if "DISCORD" in txt:
        return "Discord"
    if "TWITCH" in txt:
        return "Twitch"
    if "RAZER" in txt:
        return "Razer Gold"
    if "GOOGLE PLAY" in txt:
        return "Google Play"
    if "PSN" in txt or "PS PLUS" in txt or "PLAYSTATION PLUS" in txt:
        return "PSN Membresia"
    if "GIFT" in txt or "CARD" in txt or "GIFTCARD" in txt:
        return "Gift Cards"
    if "APEX" in txt:
        return "Apex Legends"
    return "Otros"


# =========================================================
# CATALOGO COMPLETO DE TIENDAS
# =========================================================

CATALOGOS = {
    # ---- ALPHA (Shopify) ----
    "Alpha PS5 Primaria": {"tipo": "shopify", "url": "https://alphajuegosdigitales.com/collections/ps5-principal"},
    "Alpha PS5 Secundaria": {"tipo": "shopify", "url": "https://alphajuegosdigitales.com/collections/juegos-ps5"},
    "Alpha PS4 Primaria": {"tipo": "shopify", "url": "https://alphajuegosdigitales.com/collections/ps4-principal"},
    "Alpha PS4 Secundaria": {"tipo": "shopify", "url": "https://alphajuegosdigitales.com/collections/juegos-ps4"},
    "Alpha Xbox": {"tipo": "shopify", "url": "https://alphajuegosdigitales.com/collections/juegos-xbox"},

    # ---- DIGITALWORLD (WooCommerce) ----
    "DigitalWorld PS4": {"tipo": "woocommerce", "url": "https://digitalworldpsn.com/es/juegos-digitales-ps4/?v=1b23f8a4c97c"},
    "DigitalWorld PS5": {"tipo": "woocommerce", "url": "https://digitalworldpsn.com/es/juegos-digitales-ps5/?v=1b23f8a4c97c"},
    "DigitalWorld VR": {"tipo": "woocommerce", "url": "https://digitalworldpsn.com/es/juegos-ps-vr-vr2/?v=1b23f8a4c97c"},
    "DigitalWorld Xbox": {"tipo": "woocommerce", "url": "https://digitalworldpsn.com/es/juegos-digitales-xbox/?v=1b23f8a4c97c"},
    "DigitalWorld Switch": {"tipo": "woocommerce", "url": "https://digitalworldpsn.com/es/juegos-digitales-switch/?v=1b23f8a4c97c"},

    # ---- DIXGAMER (WooCommerce) ----
    "Dix Fortnite": {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/tarjetas/fortnite/"},
    "Dix PS5": {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/juegos/ps5/"},
    "Dix PS4": {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/juegos/ps4/"},
    "Dix PS3": {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/juegos/ps3/"},
    "Dix FC Points": {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/tarjetas/fc-points/"},
    "Dix Nintendo": {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/tarjetas/nintendo/"},
    "Dix Playstation": {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/tarjetas/ps/"},
    "Dix Razer": {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/tarjetas/razer-gold/"},
    "Dix Steam": {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/tarjetas/steam/"},
    "Dix Xbox": {"tipo": "woocommerce", "url": "https://dixgamer.com/categoria-producto/tarjetas/xbox/"},

    # ---- ESTACIONPLAY (Tiendanube) - argentina -> ARS ----
    "EstacionPlay PS4": {"tipo": "tiendanube", "url": "https://estacionplay.com/videojuegos/playstation-4/"},
    "EstacionPlay PS5": {"tipo": "tiendanube", "url": "https://estacionplay.com/videojuegos/playstation-5/"},
    "EstacionPlay Memb": {"tipo": "tiendanube", "url": "https://estacionplay.com/videojuegos/psn-card-y-plus/"},

    # ---- GAMERLAB (Shopify) ----
    "GamerLab PS4": {"tipo": "shopify", "url": "https://juegosdigitalesgamerlab.com/collections/frontpage"},
    "GamerLab PS5": {"tipo": "shopify", "url": "https://juegosdigitalesgamerlab.com/collections/juegos-ps5"},
    "GamerLab EA Play": {"tipo": "shopify", "url": "https://juegosdigitalesgamerlab.com/collections/membresia-ea-play"},
    "GamerLab PSN": {"tipo": "shopify", "url": "https://juegosdigitalesgamerlab.com/collections/play-station-plus"},
    "GamerLab All": {"tipo": "shopify", "url": "https://juegosdigitalesgamerlab.com/collections/all"},

    # ---- JUEGOSDIGITALESPS4PS5 (Tiendanube con Playwright) - argentina -> ARS ----
    "JDP4P5 PS4": {"tipo": "jdp4p5", "url": "https://juegosdigitalesps4ps5.com/juegos-ps4/"},
    "JDP4P5 PS5": {"tipo": "jdp4p5", "url": "https://juegosdigitalesps4ps5.com/juegos-ps5/"},
    "JDP4P5 Switch": {"tipo": "jdp4p5", "url": "https://juegosdigitalesps4ps5.com/juegos-nintendo/"},
    "JDP4P5 PS Plus": {"tipo": "jdp4p5", "url": "https://juegosdigitalesps4ps5.com/membresias-ps-plus/"},
    "JDP4P5 GamePass": {"tipo": "jdp4p5", "url": "https://juegosdigitalesps4ps5.com/membresias-game-pass/"},
    "JDP4P5 Nintendo Online": {"tipo": "jdp4p5", "url": "https://juegosdigitalesps4ps5.com/suscripcion-nintendo-online/"},

    # ---- JUEGOSDIGITALESURUGUAY (sistema custom con Playwright) ----
    "UruguayDigital PS3": {"tipo": "uruguaydigital", "url": "https://juegosdigitalesuruguay.com/categorias/juegos-digitales-ps3"},
    "UruguayDigital PS4": {"tipo": "uruguaydigital", "url": "https://juegosdigitalesuruguay.com/categorias/juegos-digitales-ps4"},
    "UruguayDigital PS5": {"tipo": "uruguaydigital", "url": "https://juegosdigitalesuruguay.com/categorias/juegos-digitales-ps5"},
    "UruguayDigital Switch1": {"tipo": "uruguaydigital", "url": "https://juegosdigitalesuruguay.com/categorias/nintendo-switch/juegos-nintendo-switch"},
    "UruguayDigital Switch2": {"tipo": "uruguaydigital", "url": "https://www.juegosdigitalesuruguay.com/categorias/nintendo-switch-2"},
    "UruguayDigital Xbox One": {"tipo": "uruguaydigital", "url": "https://juegosdigitalesuruguay.com/categorias/xbox/juegos-xbox-one"},
    "UruguayDigital Xbox XS": {"tipo": "uruguaydigital", "url": "https://juegosdigitalesuruguay.com/categorias/xbox/juegos-xbox-series-xs"},
    "UruguayDigital PSN Plus": {"tipo": "uruguaydigital", "url": "https://juegosdigitalesuruguay.com/categorias/cuenta-psn-plus-global"},
    "UruguayDigital Nintendo": {"tipo": "uruguaydigital", "url": "https://juegosdigitalesuruguay.com/categorias/nintendo-membresia"},
    "UruguayDigital GamePass": {"tipo": "uruguaydigital", "url": "https://juegosdigitalesuruguay.com/categorias/membresias-xbox"},

    # ---- MDQ STORE (WooCommerce) - argentina -> ARS ----
    "MDQ PS5": {"tipo": "woocommerce", "url": "https://mdqstore.com/categoria-producto/juegos-ps5/"},
    "MDQ PS4": {"tipo": "woocommerce", "url": "https://mdqstore.com/categoria-producto/juegos-ps4/"},
    "MDQ PS3": {"tipo": "woocommerce", "url": "https://mdqstore.com/categoria-producto/juegos-ps3/"},
    "MDQ PS Plus": {"tipo": "woocommerce", "url": "https://mdqstore.com/categoria-producto/playstation-plus/"},
    "MDQ PSN Card": {"tipo": "woocommerce", "url": "https://mdqstore.com/categoria-producto/psn-card/"},
    "MDQ Fortnite": {"tipo": "woocommerce", "url": "https://mdqstore.com/categoria-producto/fornite/"},

    # ---- PLAYX DIGITAL (WooCommerce) - argentina -> ARS ----
    "PlayX PS4": {"tipo": "woocommerce", "url": "https://playxdigital.com/categoria-producto/psn/ps4"},
    "PlayX PS5": {"tipo": "woocommerce", "url": "https://playxdigital.com/categoria-producto/psn/ps5"},
    "PlayX Xbox One": {"tipo": "woocommerce", "url": "https://playxdigital.com/categoria-producto/xbox/xbox-one"},
    "PlayX Xbox XS": {"tipo": "woocommerce", "url": "https://playxdigital.com/categoria-producto/xbox/xbox-series-x-s"},
    "PlayX Switch": {"tipo": "woocommerce", "url": "https://playxdigital.com/categoria-producto/nintendo/nintendo-switch"},
    "PlayX Switch 2": {"tipo": "woocommerce", "url": "https://playxdigital.com/categoria-producto/nintendo/switch2/"},
    "PlayX Steam": {"tipo": "woocommerce", "url": "https://playxdigital.com/categoria-producto/steam"},
    "PlayX PSN Plus": {"tipo": "woocommerce", "url": "https://playxdigital.com/membresias/psn-plus"},
    "PlayX GamePass": {"tipo": "woocommerce", "url": "https://playxdigital.com/membresias/game-pass-ultimate"},
    "PlayX Switch Online": {"tipo": "woocommerce", "url": "https://playxdigital.com/membresias/swicth-online/"},

    # ---- PORTAL GAMES (Playwright) - argentina -> ARS ----
    "PortalGames PS3": {"tipo": "playwright", "url": "https://portalgames.com.ar/product-category/juegos-ps3/"},
    "PortalGames PS4": {"tipo": "playwright", "url": "https://portalgames.com.ar/product-category/juegos-ps4/"},
    "PortalGames PS5": {"tipo": "playwright", "url": "https://portalgames.com.ar/product-category/juegos-ps5/"},
    "PortalGames Switch": {"tipo": "playwright", "url": "https://portalgames.com.ar/product-category/nintendo-switch/"},

    # ---- TODO DIGITAL SHOP (Playwright) - argentina -> ARS ----
    "TodoDigital PS4": {"tipo": "playwright", "url": "https://tododigitalshop.com/juegos-digitales-ps4/"},
    "TodoDigital PS5": {"tipo": "playwright", "url": "https://tododigitalshop.com/juegos-digitales-ps5/"},
    "TodoDigital Switch": {"tipo": "playwright", "url": "https://tododigitalshop.com/juegos-digitales-nintendo-switch/"},

    # ---- URUGUAY JUEGOS DIGITALES (Playwright) ----
    "UYJuegos PS4": {"tipo": "playwright", "url": "https://uruguayjuegosdigitales.com/product-category/juegos-digitales-ps4/"},
    "UYJuegos PS4 VR": {"tipo": "playwright", "url": "https://uruguayjuegosdigitales.com/product-category/juegos-digitales-ps4/vr/"},
    "UYJuegos PS5": {"tipo": "playwright", "url": "https://uruguayjuegosdigitales.com/product-category/juegos-digitales-ps5/"},
    "UYJuegos PC": {"tipo": "playwright", "url": "https://uruguayjuegosdigitales.com/product-category/juegos-digitales-pc/todos-los-juegos-pc/"},
    "UYJuegos Xbox XS": {"tipo": "playwright", "url": "https://uruguayjuegosdigitales.com/product-category/juegos-digitales-xbox/juegos-digitales-xbox-series-x-s/"},
    "UYJuegos Xbox One": {"tipo": "playwright", "url": "https://uruguayjuegosdigitales.com/product-category/juegos-digitales-xbox/juegos-digitales-xbox-one/"},
    "UYJuegos Nintendo": {"tipo": "playwright", "url": "https://uruguayjuegosdigitales.com/product-category/juegos-nintendo/juegos-nintendo-switch/"},
    "UYJuegos Nintendo2": {"tipo": "playwright", "url": "https://uruguayjuegosdigitales.com/product-category/nintendo-switch-2"},
    "UYJuegos GiftCard Amazon": {"tipo": "playwright", "url": "https://uruguayjuegosdigitales.com/product-category/gift-cards/tarjetas-de-regalo-amazon/"},
    "UYJuegos GiftCard iTunes": {"tipo": "playwright", "url": "https://uruguayjuegosdigitales.com/product-category/gift-cards/itunes/"},

    # ---- WEB-GAME.NET (WooCommerce) ----
    "WebGame PS4": {"tipo": "woocommerce", "url": "https://web-game.net/categoria/juegos-ps4/"},
    "WebGame PS5": {"tipo": "woocommerce", "url": "https://web-game.net/categoria/juegos-ps5/"},
    "WebGame GiftCards": {"tipo": "woocommerce", "url": "https://web-game.net/categoria/gift-card/"},

    # ---- ZONADIGITALMD (Angular - requiere Playwright) ----
    "ZonaDigital PS4": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/juegosps4"},
    "ZonaDigital PS5": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/juegosps5"},
    "ZonaDigital PC Codigo": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/juegospccodigo"},
    "ZonaDigital PC Cuenta": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/juegospccuenta"},
    "ZonaDigital Xbox": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/juegosxbox"},
    "ZonaDigital Apex": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/monedasapexlegends"},
    "ZonaDigital Fortnite VB": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/fortnitevbucks"},
    "ZonaDigital Fortnite": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/cargafortnite"},
    "ZonaDigital GiftCard PSN": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/giftcardps3ps4ps5"},
    "ZonaDigital GiftCard Steam": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/giftcardsteam"},
    "ZonaDigital Roblox": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/giftcardroblox"},
    "ZonaDigital GiftCard Xbox": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/giftcardxbox"},
    "ZonaDigital BattleNet": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/giftcardbattlenet"},
    "ZonaDigital Riot": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/giftcardriotlatam"},
    "ZonaDigital FreeFire": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/giftcardfreefire"},
    "ZonaDigital Google Play": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/giftcardgoogleplayusa"},
    "ZonaDigital Apple": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/giftcardappleusa"},
    "ZonaDigital Switch": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/nintendoswitch"},
    "ZonaDigital Switch USA": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/giftcardusa"},
    "ZonaDigital GamePass": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/suscripcioncodigo"},
    "ZonaDigital EA Play": {"tipo": "zonadigital", "url": "zonadigitalmd.com/productos/eaplaycodigo"},
}

# =========================================================
# PAGINAS ENEBA
# =========================================================

PAGINAS_ENEBA = [
    ("FreeFire", "https://www.eneba.com/latam/top-up-free-fire-diamonds-global", "producto"),
    ("Genshin", "https://www.eneba.com/latam/top-up-genshin-impact-genesis-crystals-latin-america", "producto"),
    ("Robux", "https://www.eneba.com/latam/store/all?text=robux", "tienda"),
    ("PUBG", "https://www.eneba.com/latam/store/all?text=pubg+uc", "tienda"),
    ("FC Points", "https://www.eneba.com/latam/store/fc-points", "tienda"),
    ("FUT Points", "https://www.eneba.com/latam/store/game-points-fut", "tienda"),
    ("GTA Shark", "https://www.eneba.com/latam/store/gta-shark-cards", "tienda"),
    ("Valorant", "https://www.eneba.com/latam/store/riot-valorant-points", "tienda"),
    ("COD Points", "https://www.eneba.com/latam/store/cod-points", "tienda"),
    ("Fortnite", "https://www.eneba.com/latam/store/fortnite-v-bucks-gift-cards", "tienda"),
    ("Xbox", "https://www.eneba.com/latam/store/xbox-gift-cards", "tienda"),
    ("Xbox Points", "https://www.eneba.com/latam/store/xbox-game-points", "tienda"),
    ("Xbox GamePass", "https://www.eneba.com/latam/store/xbox-game-pass", "tienda"),
    ("Xbox Games", "https://www.eneba.com/latam/store/xbox-games", "tienda"),
    ("PlayStation", "https://www.eneba.com/latam/store/psn-games", "tienda"),
    ("PSN GiftCards", "https://www.eneba.com/latam/store/psn-gift-cards", "tienda"),
    ("PSN Plus", "https://www.eneba.com/latam/store/psn-subscriptions", "tienda"),
    ("Nintendo", "https://www.eneba.com/latam/store/nintendo-games", "tienda"),
    ("Nintendo Gift", "https://www.eneba.com/latam/store/nintendo-gift-cards", "tienda"),
    ("Nintendo Subs", "https://www.eneba.com/latam/store/nintendo-subscriptions", "tienda"),
    ("Steam", "https://www.eneba.com/latam/store/steam-games", "tienda"),
    ("Steam Wallet", "https://www.eneba.com/latam/store/steam-gift-cards", "tienda"),
    ("EA Play", "https://www.eneba.com/latam/store/ea-play", "tienda"),
    ("Origin", "https://www.eneba.com/latam/store/origin-games", "tienda"),
    ("Ubisoft", "https://www.eneba.com/latam/store/uplay-games", "tienda"),
    ("Epic Games", "https://www.eneba.com/latam/store/epic-games", "tienda"),
    ("GOG", "https://www.eneba.com/latam/store/gog-games", "tienda"),
    ("BattleNet", "https://www.eneba.com/latam/store/battle-net-games", "tienda"),
    ("BattleNetPts", "https://www.eneba.com/latam/store/battle-net-game-points", "tienda"),
    ("Google Play", "https://www.eneba.com/latam/store/google-play-gift-cards", "tienda"),
    ("Razer Gold", "https://www.eneba.com/latam/store/razer-gold-gift-cards", "tienda"),
    ("Discord", "https://www.eneba.com/latam/store/discord-gift-cards", "tienda"),
    ("Twitch", "https://www.eneba.com/latam/store/twitch-gift-cards", "tienda"),
    ("Blizzard", "https://www.eneba.com/latam/store/blizzard-gift-card", "tienda"),
]

BASE_ENEBA = "https://www.eneba.com"


# =========================================================
# FASE 1 - DESCARGA: solo bajar HTML/JSON crudo a disco.
# No se parsea nombre/precio acá (salvo lo mínimo para saber
# si hay que seguir bajando páginas: presencia de "cards").
# =========================================================

SELECTORES_CARDS = {
    "woocommerce": ["li.product", "div.product", ".product-small", ".type-product",
                     ".product-grid-item", ".wd-product", ".product-item"],
    "playwright": ["li.product", "div.product", ".product-small", ".type-product",
                    ".product-grid-item", ".wd-product", ".product-item"],
    "tiendanube": [".js-item-product"],
    "tiendanegocio": [".product-item", ".item-producto", "article.producto", ".card"],
    "uruguaydigital": ["li.d-flex.no-wrap.justify-content-start.align-items-center"],
    "jdp4p5": ["div.js-item-product"],
    "zonadigital": ["div.item-gift__content"],
}


def slug(nombre):
    return re.sub(r"[^a-z0-9]+", "_", nombre.lower()).strip("_")


def ruta_pagina(nombre_tienda, num, ext="html"):
    carpeta = os.path.join(CARPETA_HTML, slug(nombre_tienda))
    os.makedirs(carpeta, exist_ok=True)
    return os.path.join(carpeta, f"p{num}.{ext}")


def guardar_texto(ruta, contenido):
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(contenido)


def firma(texto):
    return hashlib.md5(texto.encode("utf-8", errors="ignore")).hexdigest()


def hay_cards(tipo, html):
    soup = BeautifulSoup(html, "html.parser")
    for sel in SELECTORES_CARDS.get(tipo, []):
        if soup.select(sel):
            return True
    return False


def url_pagina(tipo, url, num):
    if num == 1:
        return url
    if tipo in ("woocommerce", "playwright"):
        return f"{url.rstrip('/')}/page/{num}/"
    if tipo == "tiendanube":
        return f"{url}?mpage={num}"
    if tipo == "tiendanegocio":
        return f"{url}?pagina={num}"
    if tipo == "uruguaydigital":
        return f"{url}?pagina={num}"
    if tipo == "jdp4p5":
        return f"{url}?page={num}"
    if tipo == "zonadigital":
        return f"{url}?pagina={num}"
    return url


def _diagnostico_pagina_vacia(nombre_tienda, num, html, status=None):
    soup = BeautifulSoup(html, "html.parser")
    titulo = soup.title.get_text(strip=True) if soup.title else "(sin titulo)"
    extra = f"status={status} " if status is not None else ""
    print(
        f"   [DIAG {nombre_tienda}] {extra}pagina={num} bytes={len(html)} "
        f"titulo='{titulo[:60]}' -> ningún selector conocido matcheó"
    )


def descargar_requests(tipo, url, nombre_tienda, reporte):
    """Descarga por HTTP simple (sin JS) - woocommerce, tiendanube, tiendanegocio."""
    if tipo == "tiendanegocio" and not url.startswith("http"):
        url = "https://" + url

    rutas = []
    firma_anterior = None
    for num in range(1, LIMITE_PAGINAS_DESCARGA + 1):
        pu = url_pagina(tipo, url, num)
        try:
            r = requests.get(pu, headers=HEADERS, timeout=30)
            if r.url != pu and num > 1:
                break  # WooCommerce redirige a la última página real -> ya no hay más
            html = r.text
        except Exception as e:
            reporte.setdefault(nombre_tienda, {})["error_descarga"] = f"p{num}: {e}"
            break

        if not hay_cards(tipo, html):
            if num == 1:
                _diagnostico_pagina_vacia(nombre_tienda, num, html, status=r.status_code)
            break

        f = firma(html)
        if f == firma_anterior:
            break  # página idéntica a la anterior -> sin contenido nuevo
        firma_anterior = f

        ruta = ruta_pagina(nombre_tienda, num)
        guardar_texto(ruta, html)
        rutas.append(ruta)

    return rutas


async def descargar_playwright(tipo, url, nombre_tienda, page, reporte):
    """Descarga con navegador (contenido JS) - playwright, uruguaydigital, jdp4p5, zonadigital."""
    if tipo == "zonadigital" and not url.startswith("http"):
        url = "https://" + url

    rutas = []
    firma_anterior = None
    espera_carga = "networkidle" if tipo == "zonadigital" else "domcontentloaded"
    timeout_ms = 50000 if tipo == "zonadigital" else 40000

    for num in range(1, LIMITE_PAGINAS_DESCARGA + 1):
        pu = url_pagina(tipo, url, num)
        try:
            resp = await page.goto(pu, wait_until=espera_carga, timeout=timeout_ms)
            if resp and resp.status >= 400:
                reporte.setdefault(nombre_tienda, {})["error_descarga"] = f"p{num}: HTTP {resp.status}"
                break
            await page.wait_for_timeout(4000 if tipo == "zonadigital" else 3000)
            if tipo == "zonadigital":
                for _ in range(4):
                    await page.mouse.wheel(0, 4000)
                    await page.wait_for_timeout(1500)
            html = await page.content()
        except Exception as e:
            reporte.setdefault(nombre_tienda, {})["error_descarga"] = f"p{num}: {e}"
            break

        if not hay_cards(tipo, html):
            if num == 1:
                _diagnostico_pagina_vacia(nombre_tienda, num, html)
                # Guardamos igual la página 1 vacía -> sirve para ver a mano
                # qué devolvió el sitio (challenge de Cloudflare, cambio de
                # tema, selector viejo, etc.)
                ruta = ruta_pagina(nombre_tienda, num)
                guardar_texto(ruta, html)
                rutas.append(ruta)
            break

        f = firma(html)
        if f == firma_anterior:
            break
        firma_anterior = f

        ruta = ruta_pagina(nombre_tienda, num)
        guardar_texto(ruta, html)
        rutas.append(ruta)

    return rutas


def descargar_shopify(url, nombre_tienda, reporte):
    """Shopify no tiene HTML paginado -> baja el JSON crudo de products.json."""
    rutas = []
    for num in range(1, LIMITE_PAGINAS_DESCARGA + 1):
        pu = f"{url}/products.json?limit=250&page={num}"
        try:
            r = requests.get(pu, headers=HEADERS, timeout=30)
            data = r.json()
        except Exception as e:
            reporte.setdefault(nombre_tienda, {})["error_descarga"] = f"p{num}: {e}"
            break
        items = data.get("products", [])
        if not items:
            break
        ruta = ruta_pagina(nombre_tienda, num, ext="json")
        guardar_texto(ruta, r.text)
        rutas.append(ruta)
    return rutas


async def cerrar_popups(page):
    for texto in ["Aceptar todo", "Accept all", "Entendido"]:
        try:
            b = await page.query_selector(f"button:has-text('{texto}')")
            if b:
                await b.click()
                await page.wait_for_timeout(800)
        except Exception:
            pass
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass


async def descargar_eneba(categoria, url, browser, reporte):
    nombre_tienda = f"Eneba - {categoria}"
    try:
        page = await browser.new_page(
            viewport={"width": 1366, "height": 768},
            user_agent=HEADERS["User-Agent"],
            locale="es-419",
            extra_http_headers={"Accept-Language": "es-419,es;q=0.9"},
        )
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        await cerrar_popups(page)
        await page.wait_for_timeout(1500)
        for _ in range(4):
            await page.mouse.wheel(0, 4000)
            await page.wait_for_timeout(1200)
        html = await page.content()
        await page.close()
    except Exception as e:
        reporte.setdefault(nombre_tienda, {})["error_descarga"] = str(e)
        return []

    ruta = ruta_pagina(nombre_tienda, 1)
    guardar_texto(ruta, html)
    return [ruta]


# =========================================================
# FASE 2 - PARSEO: lee lo ya guardado en disco, sin red.
# =========================================================

def parsear_woocommerce_like(html, nombre_tienda, url, vistos):
    """Sirve para 'woocommerce' y para el 'playwright' genérico (mismos selectores/markup)."""
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for sel in SELECTORES_CARDS["woocommerce"]:
        cards.extend(soup.select(sel))

    productos = []
    for c in cards:
        try:
            nombre_el = c.select_one(
                "h2, h3, h4, .product-title, "
                ".woocommerce-loop-product__title, .wd-entities-title"
            )
            precio_txt = extraer_precio_real(c)
            if not nombre_el or not precio_txt:
                continue
            nombre = nombre_el.get_text(strip=True)
            valor, moneda = limpiar_precio(precio_txt, nombre_tienda)
            if valor is None or valor < 1:
                continue
            clave = (nombre, precio_txt)
            if clave in vistos:
                continue
            vistos.add(clave)
            link_el = c.select_one("a")
            link = link_el["href"] if link_el else url
            productos.append({
                "nombre": nombre,
                "precio_original": precio_txt,
                "precio": valor,
                "moneda": moneda,
                "precio_uyu": convertir_uyu(valor, moneda),
                "link": link,
            })
        except Exception:
            continue
    return productos


def parsear_tiendanube(html, nombre_tienda, url, vistos):
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".js-item-product")
    productos = []
    for c in cards:
        try:
            nombre = c.select_one(".js-item-name").get_text(strip=True)
            precio_txt = c.select_one(".js-price-display").get_text(strip=True)
            clave = (nombre, precio_txt)
            if clave in vistos:
                continue
            vistos.add(clave)
            valor, moneda = limpiar_precio(precio_txt, nombre_tienda)
            if valor is None:
                continue
            link = c.select_one("a")["href"]
            productos.append({
                "nombre": nombre,
                "precio_original": precio_txt,
                "precio": valor,
                "moneda": moneda,
                "precio_uyu": convertir_uyu(valor, moneda),
                "link": link,
            })
        except Exception:
            continue
    return productos


def parsear_tiendanegocio(html, nombre_tienda, url, vistos):
    soup = BeautifulSoup(html, "html.parser")
    productos = []
    for c in soup.select(".product-item, .item-producto, article.producto, .card"):
        try:
            nombre_el = c.select_one("h2, h3, h4, .product-name, .nombre")
            precio_el = c.select_one(".price, .precio, .product-price")
            if not nombre_el or not precio_el:
                continue
            nombre = nombre_el.get_text(strip=True)
            precio_txt = precio_el.get_text(strip=True)
            clave = (nombre, precio_txt)
            if clave in vistos:
                continue
            vistos.add(clave)
            valor, moneda = limpiar_precio(precio_txt, nombre_tienda)
            if valor is None:
                continue
            link_el = c.select_one("a")
            link = link_el["href"] if link_el else url
            productos.append({
                "nombre": nombre,
                "precio_original": precio_txt,
                "precio": valor,
                "moneda": moneda,
                "precio_uyu": convertir_uyu(valor, moneda),
                "link": link,
            })
        except Exception:
            continue
    return productos


def parsear_uruguaydigital(html, nombre_tienda, url, vistos):
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("li.d-flex.no-wrap.justify-content-start.align-items-center")
    productos = []
    for c in cards:
        try:
            texto = c.get_text("\n", strip=True)
            lineas = [l.strip() for l in texto.split("\n") if l.strip()]
            if len(lineas) < 2:
                continue
            nombre = ""
            precio_txt = ""
            for linea in lineas:
                if re.search(r"\$[\d.,]+", linea):
                    precio_txt = linea
                    break
                else:
                    nombre = linea
            if not nombre or not precio_txt:
                continue
            clave = (nombre, precio_txt)
            if clave in vistos:
                continue
            vistos.add(clave)
            valor, moneda = limpiar_precio(precio_txt, nombre_tienda)
            if valor is None or valor < 1:
                continue
            link_el = c.select_one("a")
            link = link_el["href"] if link_el else url
            if link and not link.startswith("http"):
                link = "https://juegosdigitalesuruguay.com" + link
            productos.append({
                "nombre": nombre,
                "precio_original": precio_txt,
                "precio": valor,
                "moneda": moneda,
                "precio_uyu": convertir_uyu(valor, moneda),
                "link": link,
            })
        except Exception:
            continue
    return productos


def parsear_jdp4p5(html, nombre_tienda, url, vistos):
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.js-item-product")
    productos = []
    for c in cards:
        try:
            link_el = c.select_one("a.item-link")
            nombre_el = c.select_one(".js-item-name, h2, h3")
            if link_el and not nombre_el:
                nombre = link_el.get_text("\n", strip=True).split("\n")[0].strip()
            elif nombre_el:
                nombre = nombre_el.get_text(strip=True)
            else:
                continue

            precio_el = c.select_one("span.js-price-display")
            if not precio_el:
                continue
            precio_txt = precio_el.get_text(strip=True)

            numero_match = re.search(r"[\d.,]+", precio_txt)
            if not numero_match:
                continue
            try:
                valor = limpiar_numero(numero_match.group().strip())
            except (ValueError, ZeroDivisionError):
                continue

            clave = (nombre, precio_txt)
            if clave in vistos:
                continue
            vistos.add(clave)

            moneda = MONEDA_TIENDA.get(nombre_tienda, "ARS")
            if valor < 1:
                continue

            link = link_el["href"] if link_el else url
            if link and not link.startswith("http"):
                link = "https://juegosdigitalesps4ps5.com" + link

            productos.append({
                "nombre": nombre,
                "precio_original": precio_txt,
                "precio": valor,
                "moneda": moneda,
                "precio_uyu": convertir_uyu(valor, moneda),
                "link": link,
            })
        except Exception:
            continue
    return productos


def parsear_zonadigital(html, nombre_tienda, url, vistos):
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.item-gift__content")
    productos = []
    for c in cards:
        try:
            nombre = ""
            for child in c.children:
                txt = child.get_text(strip=True) if hasattr(child, "get_text") else str(child).strip()
                if txt and not txt.startswith("De") and "$" not in txt:
                    nombre = txt
                    break
            if not nombre:
                continue

            precio_el = c.select_one("span:not([class])")
            if not precio_el:
                for sp in c.select("span"):
                    if "$" in sp.get_text():
                        precio_el = sp
                        break
            if not precio_el:
                continue
            precio_txt = precio_el.get_text(strip=True)

            clave = (nombre, precio_txt)
            if clave in vistos:
                continue
            vistos.add(clave)

            precio_limpio = re.sub(r"[^\d]", "", precio_txt)
            try:
                valor = float(precio_limpio)
            except Exception:
                continue

            moneda = MONEDA_TIENDA.get(nombre_tienda, "CLP")
            if valor < 1:
                continue

            link_el = c.select_one("a")
            link = link_el["href"] if link_el else url
            if link and not link.startswith("http"):
                link = "https://zonadigitalmd.com" + link

            productos.append({
                "nombre": nombre,
                "precio_original": precio_txt,
                "precio": valor,
                "moneda": moneda,
                "precio_uyu": convertir_uyu(valor, moneda),
                "link": link,
            })
        except Exception:
            continue
    return productos


def parsear_shopify_pagina(data, nombre_tienda, url):
    """`data` es el JSON ya cargado de una sola página de products.json."""
    moneda_forzada = MONEDA_TIENDA.get(nombre_tienda, "USD")
    base_url = url.split("/collections")[0]
    productos = []

    for p in data.get("products", []):
        try:
            tags_raw = p.get("tags", "")
            tags_txt = ", ".join(tags_raw) if isinstance(tags_raw, list) else str(tags_raw or "")
            product_type = str(p.get("product_type") or "")
            link = f"{base_url}/products/{p['handle']}"

            variantes = p.get("variants") or []
            variantes_reales = [
                v for v in variantes
                if str(v.get("title") or "").strip().lower() not in ("", "default title")
            ]

            if not variantes_reales:
                precio_raw = float(variantes[0]["price"])
                precio_uyu = convertir_uyu(precio_raw, moneda_forzada)
                productos.append({
                    "nombre": p["title"],
                    "precio_original": f"{precio_raw} {moneda_forzada}",
                    "precio": precio_raw,
                    "moneda": moneda_forzada,
                    "precio_uyu": precio_uyu,
                    "link": link,
                    "tags": f"{tags_txt} {product_type}".strip(),
                })
            else:
                for v in variantes_reales:
                    try:
                        precio_raw = float(v["price"])
                    except (TypeError, ValueError, KeyError):
                        continue
                    precio_uyu = convertir_uyu(precio_raw, moneda_forzada)
                    variante_nombre = str(v.get("title") or "").strip()
                    productos.append({
                        "nombre": f"{p['title']} - {variante_nombre}" if variante_nombre else p["title"],
                        "precio_original": f"{precio_raw} {moneda_forzada}",
                        "precio": precio_raw,
                        "moneda": moneda_forzada,
                        "precio_uyu": precio_uyu,
                        "link": link,
                        "tags": f"{tags_txt} {product_type} {variante_nombre}".strip(),
                    })
        except Exception:
            continue

    return productos


def parsear_pagina(tipo, html, nombre_tienda, url, vistos):
    if tipo in ("woocommerce", "playwright"):
        return parsear_woocommerce_like(html, nombre_tienda, url, vistos)
    if tipo == "tiendanube":
        return parsear_tiendanube(html, nombre_tienda, url, vistos)
    if tipo == "tiendanegocio":
        return parsear_tiendanegocio(html, nombre_tienda, url, vistos)
    if tipo == "uruguaydigital":
        return parsear_uruguaydigital(html, nombre_tienda, url, vistos)
    if tipo == "jdp4p5":
        return parsear_jdp4p5(html, nombre_tienda, url, vistos)
    if tipo == "zonadigital":
        return parsear_zonadigital(html, nombre_tienda, url, vistos)
    return []


def parsear_categoria(nombre_tienda, cfg, rutas):
    tipo = cfg["tipo"]
    url = cfg["url"]

    if tipo == "shopify":
        productos = []
        for ruta in rutas:
            with open(ruta, encoding="utf-8") as f:
                data = json.load(f)
            productos.extend(parsear_shopify_pagina(data, nombre_tienda, url))
        return productos

    vistos = set()
    productos = []
    for ruta in rutas:
        with open(ruta, encoding="utf-8") as f:
            html = f.read()
        productos.extend(parsear_pagina(tipo, html, nombre_tienda, url, vistos))
    return productos


def parsear_eneba(rutas, categoria, tipo_eneba, url, nombre_tienda, vistos_eneba):
    if not rutas:
        return []
    with open(rutas[0], encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")
    productos = []

    if tipo_eneba == "producto":
        cards = soup.find_all("div", class_="vNgEk7")
        for card in cards:
            try:
                lineas = [l.strip() for l in card.get_text("\n").split("\n") if l.strip()]
                nombre = lineas[0] if lineas else ""
                precio = next((extraer_precio_eneba(l) for l in lineas if extraer_precio_eneba(l)), "")
                if not nombre or not precio:
                    continue
                clave = (nombre, precio)
                if clave in vistos_eneba:
                    continue
                vistos_eneba.add(clave)
                valor, moneda = limpiar_precio(precio, "Eneba")
                productos.append({
                    "nombre": nombre,
                    "precio_original": precio,
                    "precio": valor,
                    "moneda": moneda,
                    "precio_uyu": convertir_uyu(valor, moneda),
                    "link": url,
                    "tienda": nombre_tienda,
                    "fuente": "Eneba",
                    "nombre_normalizado": limpiar_nombre_eneba(nombre),
                    "plataforma": detectar_plataforma(nombre, categoria),
                })
            except Exception:
                continue

    elif tipo_eneba == "tienda":
        cards = soup.find_all("div", class_="b3POZC")
        for card in cards:
            try:
                a = card.find("a", href=True)
                if not a and card.parent:
                    a = card.parent.find("a", href=True)
                nombre = ""
                link = url
                if a:
                    nombre = a.get("title", "").strip()
                    if not nombre:
                        img = a.find("img")
                        if img:
                            nombre = img.get("alt", "").strip()
                    href = a.get("href", "")
                    link = BASE_ENEBA + href if href.startswith("/") else href
                nombre = limpiar_nombre_eneba(nombre)
                precio = next(
                    (extraer_precio_eneba(l.strip()) for l in card.get_text("\n").split("\n") if extraer_precio_eneba(l.strip())),
                    "",
                )
                if not nombre or not precio:
                    continue
                clave = (nombre, precio)
                if clave in vistos_eneba:
                    continue
                vistos_eneba.add(clave)
                valor, moneda = limpiar_precio(precio, "Eneba")
                productos.append({
                    "nombre": nombre,
                    "precio_original": precio,
                    "precio": valor,
                    "moneda": moneda,
                    "precio_uyu": convertir_uyu(valor, moneda),
                    "link": link,
                    "tienda": nombre_tienda,
                    "fuente": "Eneba",
                    "nombre_normalizado": limpiar_nombre_eneba(nombre),
                    "plataforma": detectar_plataforma(nombre, categoria, link=link),
                })
            except Exception:
                continue

    return productos


# =========================================================
# MAIN
# =========================================================

async def main():
    print("\n" + "=" * 60)
    print("ACTUALIZANDO COTIZACIONES")
    print("=" * 60)
    actualizar_cotizaciones()

    # Por si quedó algo de una corrida anterior interrumpida
    if os.path.exists(CARPETA_HTML):
        shutil.rmtree(CARPETA_HTML)

    reporte = {}
    rutas_por_tienda = {}
    rutas_eneba = {}

    # -----------------------------------------------------
    # FASE 1: DESCARGAR TODO (HTML/JSON crudo, sin parsear)
    # -----------------------------------------------------
    print("\n" + "=" * 60)
    print("FASE 1 - DESCARGANDO HTML/JSON DE TODAS LAS TIENDAS")
    print("=" * 60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page(user_agent=HEADERS["User-Agent"], locale="es-419")

        for nombre_tienda, cfg in CATALOGOS.items():
            tipo, url = cfg["tipo"], cfg["url"]
            print(f"  {nombre_tienda}...", end=" ", flush=True)
            try:
                if tipo == "shopify":
                    rutas = descargar_shopify(url, nombre_tienda, reporte)
                elif tipo in ("tiendanube", "tiendanegocio"):
                    rutas = descargar_requests(tipo, url, nombre_tienda, reporte)
                elif tipo == "woocommerce":
                    rutas = descargar_requests(tipo, url, nombre_tienda, reporte)
                    if not rutas:
                        print("(retry playwright)", end=" ", flush=True)
                        rutas = await descargar_playwright("playwright", url, nombre_tienda, page, reporte)
                else:  # playwright, uruguaydigital, jdp4p5, zonadigital
                    rutas = await descargar_playwright(tipo, url, nombre_tienda, page, reporte)
            except Exception as e:
                reporte.setdefault(nombre_tienda, {})["error_descarga"] = str(e)
                rutas = []

            rutas_por_tienda[nombre_tienda] = (cfg, rutas)
            reporte.setdefault(nombre_tienda, {})
            reporte[nombre_tienda]["tipo"] = tipo
            reporte[nombre_tienda]["paginas_descargadas"] = len(rutas)
            print(f"{len(rutas)} páginas guardadas")

        print("\n  Eneba...")
        for categoria, url, tipo_eneba in PAGINAS_ENEBA:
            nombre_tienda = f"Eneba - {categoria}"
            print(f"    {nombre_tienda}...", end=" ", flush=True)
            rutas = await descargar_eneba(categoria, url, browser, reporte)
            rutas_eneba[nombre_tienda] = (tipo_eneba, categoria, url, rutas)
            reporte.setdefault(nombre_tienda, {})
            reporte[nombre_tienda]["tipo"] = f"eneba_{tipo_eneba}"
            reporte[nombre_tienda]["paginas_descargadas"] = len(rutas)
            print(f"{len(rutas)} páginas guardadas")

        await browser.close()

    # -----------------------------------------------------
    # FASE 2: PARSEAR TODO LO YA DESCARGADO (sin red)
    # -----------------------------------------------------
    print("\n" + "=" * 60)
    print("FASE 2 - PARSEANDO LO DESCARGADO")
    print("=" * 60)

    todos = []

    for nombre_tienda, (cfg, rutas) in rutas_por_tienda.items():
        try:
            productos = parsear_categoria(nombre_tienda, cfg, rutas)
        except Exception as e:
            reporte.setdefault(nombre_tienda, {})["error_parseo"] = str(e)
            productos = []

        reporte[nombre_tienda]["productos"] = len(productos)
        for p in productos:
            p["tienda"] = nombre_tienda
            p["fuente"] = cfg["tipo"].capitalize()
            p["nombre_normalizado"] = normalizar_nombre(p["nombre"])
            p["plataforma"] = detectar_plataforma(
                p["nombre"], nombre_tienda, link=p.get("link", ""), tags=p.get("tags", "")
            )
            todos.append(p)

    vistos_eneba = set()
    for nombre_tienda, (tipo_eneba, categoria, url, rutas) in rutas_eneba.items():
        try:
            productos = parsear_eneba(rutas, categoria, tipo_eneba, url, nombre_tienda, vistos_eneba)
        except Exception as e:
            reporte.setdefault(nombre_tienda, {})["error_parseo"] = str(e)
            productos = []
        reporte[nombre_tienda]["productos"] = len(productos)
        todos.extend(productos)

    print(f"Total de productos parseados: {len(todos)}")

    # -----------------------------------------------------
    # FASE 3: BORRAR LOS HTML/JSON DE ESTA CORRIDA
    # -----------------------------------------------------
    if os.path.exists(CARPETA_HTML):
        shutil.rmtree(CARPETA_HTML)
    print("HTML/JSON temporales de esta corrida borrados.")

    # -----------------------------------------------------
    # FASE 4: REPORTE - qué categoría dio error o 0 productos
    # -----------------------------------------------------
    filas_reporte = []
    for nombre_tienda, info in reporte.items():
        filas_reporte.append({
            "tienda": nombre_tienda,
            "tipo": info.get("tipo", ""),
            "paginas_descargadas": info.get("paginas_descargadas", 0),
            "productos": info.get("productos", 0),
            "error_descarga": info.get("error_descarga", ""),
            "error_parseo": info.get("error_parseo", ""),
        })
    df_reporte = pd.DataFrame(filas_reporte).sort_values(["productos", "tienda"])
    df_reporte.to_csv("reporte_corrida.csv", index=False)

    problemas = df_reporte[
        (df_reporte["productos"] == 0)
        | (df_reporte["error_descarga"] != "")
        | (df_reporte["error_parseo"] != "")
    ]
    print(f"\n{len(problemas)} categorías con 0 productos o error (detalle en reporte_corrida.csv):")
    for _, fila in problemas.iterrows():
        detalle = fila["error_descarga"] or fila["error_parseo"] or "0 productos, sin error explícito"
        print(f"   - {fila['tienda']}: {detalle}")

    # -----------------------------------------------------
    # FASE 5: ARMAR Y EXPORTAR EXCEL + CSV
    # -----------------------------------------------------
    print("\n" + "=" * 60)
    print("ARMANDO EXCEL")
    print("=" * 60)

    df = pd.DataFrame(todos)
    print(f"Total bruto: {len(df)} productos")
    if len(df) == 0:
        print("Sin datos. Saliendo.")
        return

    df = df[
        (df["precio_uyu"].notna()) & (df["precio_uyu"] > 5) & (df["precio_uyu"] < 500000)
    ].copy()
    df = df.sort_values("precio_uyu")

    idx_mejores = df.groupby("nombre_normalizado")["precio_uyu"].idxmin()
    mejores = df.loc[idx_mejores].sort_values("precio_uyu").copy()

    COLS_DISPLAY = [
        "fuente", "tienda", "nombre", "nombre_normalizado",
        "precio_original", "moneda", "precio_uyu", "plataforma", "link",
    ]
    COLS_LABELS = [
        "Fuente", "Tienda", "Nombre", "Nombre Limpio",
        "Precio Original", "Moneda", "Precio UYU", "Plataforma", "Link",
    ]
    COL_MAP = dict(zip(COLS_DISPLAY, COLS_LABELS))

    ARCHIVO = "catalogo_completo_abc_gaming.xlsx"
    df[COLS_DISPLAY].rename(columns=COL_MAP).to_csv("catalogo_completo_abc_gaming.csv", index=False)

    with pd.ExcelWriter(ARCHIVO, engine="openpyxl") as writer:
        df[COLS_DISPLAY].rename(columns=COL_MAP).to_excel(writer, sheet_name="TODO", index=False)
        mejores[COLS_DISPLAY].rename(columns=COL_MAP).to_excel(writer, sheet_name="MEJORES_PRECIOS", index=False)

        eneba_df = df[df["fuente"] == "Eneba"]
        if len(eneba_df) > 0:
            eneba_df[COLS_DISPLAY].rename(columns=COL_MAP).to_excel(writer, sheet_name="ENEBA", index=False)

        for plataforma in sorted(df["plataforma"].unique()):
            temp = df[df["plataforma"] == plataforma]
            if len(temp) == 0:
                continue
            nombre_hoja = plataforma[:31]
            temp[COLS_DISPLAY].rename(columns=COL_MAP).to_excel(writer, sheet_name=nombre_hoja, index=False)

    wb = load_workbook(ARCHIVO)
    HEADER_FILL = PatternFill("solid", start_color="1E1E2E", end_color="1E1E2E")
    HEADER_FONT = Font(bold=True, color="00D4FF", name="Arial", size=10)
    ALT_FILL = PatternFill("solid", start_color="F5F5F5", end_color="F5F5F5")
    LINK_FONT = Font(color="0000FF", underline="single")

    for ws in wb.worksheets:
        for cell in ws[1]:
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for i, row in enumerate(ws.iter_rows(min_row=2), start=2):
            if i % 2 == 0:
                for cell in row:
                    cell.fill = ALT_FILL

        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        if "Link" in headers:
            col_link = headers.index("Link") + 1
            for row in range(2, ws.max_row + 1):
                cell = ws.cell(row, col_link)
                if cell.value and str(cell.value).startswith("http"):
                    cell.hyperlink = cell.value
                    cell.font = LINK_FONT

        for col_idx, col in enumerate(ws.columns, start=1):
            max_len = max((len(str(c.value)) for c in col if c.value), default=10)
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 3, 60)

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    wb.save(ARCHIVO)

    print(f"\nTotal productos finales : {len(df)}")
    print(f"Juegos únicos (mejor precio): {len(mejores)}")
    print(f"Archivo generado: {ARCHIVO}")


# =========================================================
# EJECUTAR
# =========================================================

if __name__ == "__main__":
    asyncio.run(main())

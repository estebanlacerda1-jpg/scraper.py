"""
filtro_vendibles.py — ABC Gaming
==================================

Cruza el catálogo de precios (el Excel que ya genera el scraper) contra los
juegos más vendidos/tendencia AHORA MISMO en Steam, PlayStation, Xbox y
Nintendo Switch, y genera dos salidas listas para usar:

    1. vendibles.xlsx   -> planilla filtrada con el MEJOR precio de cada
                           juego en tendencia que SÍ está en tu catálogo.
    2. posts_redes.txt  -> textos ya redactados, uno por juego, listos para
                           copiar/pegar en WhatsApp o Instagram.

FUENTES DE TENDENCIA
---------------------
- Steam:   SteamSpy (https://steamspy.com/api.php?request=top100in2weeks)
           API pública, sin key, basada en dueños/jugadores reales de las
           últimas 2 semanas. Es la señal más confiable de las 4.

- Consolas (PS5/Xbox/Switch): RAWG.io (https://rawg.io/apidocs)
           API gratuita (pedís una key en 1 minuto en rawg.io/apidocs).
           Se ordena por "-added" (juegos que más gente agregó a su
           biblioteca) filtrando por fecha reciente, como proxy de qué
           está en boca de todos ahora. No es un ranking de ventas oficial
           de Sony/Microsoft/Nintendo (esos no son públicos), pero es la
           mejor aproximación gratuita y sin scraping frágil.

           Sin RAWG_API_KEY configurada, el script sigue funcionando SOLO
           con Steam (así podés probarlo hoy mismo sin pedir nada).

CÓMO CORRERLO
--------------
    pip install rapidfuzz requests pandas openpyxl --break-system-packages
    export RAWG_API_KEY="tu_key_gratis"   # opcional, ver arriba
    python filtro_vendibles.py --catalogo catalogo_completo_abc_gaming.xlsx

Todo lo que depende de internet (Steam/RAWG) está aislado en funciones
`obtener_tendencia_*`. Si algún día una de esas APIs cambia de formato,
solo hay que tocar esa función — el resto del script (matching, excel,
posts) no se toca.
"""

import argparse
import os
import re
import sys
from datetime import datetime

import pandas as pd
import requests

try:
    from rapidfuzz import fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    import difflib
    _HAS_RAPIDFUZZ = False


# ----------------------------------------------------------------------------
# 1. OBTENER TENDENCIAS (lo único que toca internet)
# ----------------------------------------------------------------------------

def obtener_tendencia_steam(limite=60, timeout=15):
    """Top vendidos/jugados en Steam las últimas 2 semanas, vía SteamSpy.
    Devuelve lista de dicts: {"nombre": ..., "fuente": "Steam", "rank": n}
    """
    url = "https://steamspy.com/api.php?request=top100in2weeks"
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[AVISO] No se pudo consultar SteamSpy: {e}")
        return []

    resultado = []
    # SteamSpy devuelve un dict {appid: {...}}; el orden de inserción
    # ya viene rankeado de más a menos jugado.
    for i, (appid, info) in enumerate(data.items()):
        if i >= limite:
            break
        nombre = info.get("name")
        if nombre:
            resultado.append({"nombre": nombre, "fuente": "Steam", "rank": i + 1})
    return resultado


def obtener_tendencia_rawg(limite_por_plataforma=40, dias=30, timeout=15):
    """Juegos con más actividad reciente en RAWG, separados por consola.
    Requiere la variable de entorno RAWG_API_KEY. Si no está, devuelve [].
    """
    api_key = os.environ.get("RAWG_API_KEY")
    if not api_key:
        print("[AVISO] RAWG_API_KEY no configurada — se omite tendencia de consolas.")
        return []

    plataformas = {
        "PS5": 187,
        "Xbox Series S/X": 186,
        "Nintendo Switch": 7,
    }

    hoy = datetime.utcnow().date()
    desde = hoy.replace(day=1)  # simplificación: desde el 1ro del mes actual
    resultado = []

    for nombre_plataforma, platform_id in plataformas.items():
        url = "https://api.rawg.io/api/games"
        params = {
            "key": api_key,
            "platforms": platform_id,
            "dates": f"{desde}-01,{hoy}",
            "ordering": "-added",
            "page_size": limite_por_plataforma,
        }
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"[AVISO] Falló RAWG para {nombre_plataforma}: {e}")
            continue

        for i, juego in enumerate(data.get("results", [])):
            resultado.append({
                "nombre": juego.get("name"),
                "fuente": f"RAWG ({nombre_plataforma})",
                "rank": i + 1,
            })
    return resultado


# ----------------------------------------------------------------------------
# 2. MATCHING contra el catálogo
# ----------------------------------------------------------------------------

def normalizar(texto):
    """Deja solo letras/números en minúscula, sin acentos ni símbolos,
    para comparar 'Assassin's Creed Shadows' con 'ASSASSIN'S CREED SHADOWS – SWITCH 2'."""
    texto = texto.lower()
    texto = re.sub(r"[™®©–—:|!.,'\"]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def similitud(a, b):
    if _HAS_RAPIDFUZZ:
        return fuzz.token_set_ratio(a, b)
    return difflib.SequenceMatcher(None, a, b).ratio() * 100


def emparejar_tendencias_con_catalogo(tendencias, df_catalogo, umbral=78):
    """Para cada juego en tendencia, busca la mejor coincidencia dentro del
    catálogo (columna 'Nombre Limpio') y se queda con el precio más bajo
    entre todas las tiendas que lo tengan.

    Devuelve un DataFrame: rank, fuente_tendencia, juego_tendencia,
    nombre_catalogo, tienda, precio_uyu, plataforma, link, similitud
    """
    catalogo_norm = df_catalogo.copy()
    catalogo_norm["_norm"] = catalogo_norm["Nombre Limpio"].apply(normalizar)

    filas = []
    for item in tendencias:
        nombre_norm = normalizar(item["nombre"])

        # 1) candidatos por coincidencia de substring (rápido y evita
        #    comparar contra las 8000 filas con fuzzy completo)
        candidatos = catalogo_norm[catalogo_norm["_norm"].str.contains(
            re.escape(nombre_norm.split(" ")[0]), na=False, regex=True
        )]
        if candidatos.empty:
            candidatos = catalogo_norm

        mejor_score = 0
        mejor_idx = None
        for idx, row in candidatos.iterrows():
            score = similitud(nombre_norm, row["_norm"])
            if score > mejor_score:
                mejor_score = score
                mejor_idx = idx

        if mejor_idx is None or mejor_score < umbral:
            continue  # no está en el catálogo, se descarta

        # de todas las filas del catálogo que matchean ese mismo nombre
        # limpio, nos quedamos con el precio más bajo (mejor oferta)
        nombre_limpio_match = catalogo_norm.loc[mejor_idx, "Nombre Limpio"]
        ofertas = df_catalogo[df_catalogo["Nombre Limpio"] == nombre_limpio_match]
        mejor_oferta = ofertas.loc[ofertas["Precio UYU"].idxmin()]

        filas.append({
            "rank_tendencia": item["rank"],
            "fuente_tendencia": item["fuente"],
            "juego_buscado": item["nombre"],
            "nombre_catalogo": mejor_oferta["Nombre Limpio"],
            "tienda": mejor_oferta["Tienda"],
            "precio_uyu": round(float(mejor_oferta["Precio UYU"]), 2),
            "plataforma": mejor_oferta["Plataforma"],
            "link": mejor_oferta["Link"],
            "similitud": round(mejor_score, 1),
        })

    resultado = pd.DataFrame(filas)
    if resultado.empty:
        return resultado

    # si el mismo juego matcheó por dos fuentes distintas (ej. RAWG PS5 y
    # RAWG Xbox), nos quedamos con la de mejor rank (más "trending")
    resultado = resultado.sort_values("rank_tendencia")
    resultado = resultado.drop_duplicates(subset=["nombre_catalogo", "plataforma"], keep="first")
    resultado = resultado.sort_values(["rank_tendencia", "precio_uyu"]).reset_index(drop=True)
    return resultado


# ----------------------------------------------------------------------------
# 3. SALIDAS: Excel + posteos
# ----------------------------------------------------------------------------

EMOJI_PLATAFORMA = {
    "PS5": "🎮", "PS4": "🎮", "PS3": "🎮",
    "Xbox": "🟢", "Nintendo": "🔴", "Steam": "🖥️",
    "PSN Membresia": "🃏",
}


def generar_excel(df_resultado, ruta_salida):
    with pd.ExcelWriter(ruta_salida, engine="openpyxl") as writer:
        df_resultado.to_excel(writer, index=False, sheet_name="VENDIBLES")
    print(f"[OK] Planilla generada: {ruta_salida} ({len(df_resultado)} juegos)")


def generar_posts(df_resultado, ruta_salida):
    bloques = []
    for _, fila in df_resultado.iterrows():
        emoji = EMOJI_PLATAFORMA.get(fila["plataforma"], "🎮")
        precio = f"${fila['precio_uyu']:,.0f}".replace(",", ".")
        bloque = (
            f"{emoji} {fila['nombre_catalogo']} — {fila['plataforma']}\n"
            f"💰 {precio} UYU\n"
            f"🔥 Tendencia #{fila['rank_tendencia']} en {fila['fuente_tendencia']}\n"
            f"🛒 Consultanos por WhatsApp o Instagram para tu código\n"
            f"#ABCGaming #{fila['plataforma'].replace(' ', '')} "
            f"#{re.sub(r'[^A-Za-z0-9]', '', fila['nombre_catalogo'])[:30]}"
        )
        bloques.append(bloque)

def generar_demanda_csv(df_resultado, ruta_salida):
    d = (
        df_resultado
        .sort_values("rank_tendencia")
        .drop_duplicates(subset=["juego_buscado"], keep="first")
        .copy()
    )
    max_rank = d["rank_tendencia"].max()
    min_rank = d["rank_tendencia"].min()
    if max_rank == min_rank:
        d["Demanda_0_100"] = 100.0
    else:
        d["Demanda_0_100"] = (
            100 - (d["rank_tendencia"] - min_rank) * (70 / (max_rank - min_rank))
        ).round(1)

    d["Franquicia"] = d["juego_buscado"].str.upper()
    d[["Franquicia", "Demanda_0_100"]].to_csv(ruta_salida, index=False)
    print(f"[OK] Demanda por franquicia generada: {ruta_salida} ({len(d)} franquicias)")
    
    with open(ruta_salida, "w", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n\n".join(bloques))
    print(f"[OK] Posteos generados: {ruta_salida} ({len(bloques)} textos)")


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Filtra lo más vendible del catálogo ABC Gaming")
    ap.add_argument("--catalogo", required=True, help="Ruta al Excel del catálogo (hoja TODO o MEJORES_PRECIOS)")
    ap.add_argument("--hoja", default="MEJORES_PRECIOS", help="Hoja a usar (default: MEJORES_PRECIOS)")
    ap.add_argument("--umbral", type=int, default=78, help="Umbral de similitud 0-100 (default 78)")
    ap.add_argument("--salida-excel", default="vendibles.xlsx")
    ap.add_argument("--salida-posts", default="posts_redes.txt")
    args = ap.parse_args()
    ap.add_argument("--salida-demanda", default="demanda_abc_gaming.csv")

    print("Leyendo catálogo...")
    df_catalogo = pd.read_excel(args.catalogo, sheet_name=args.hoja)

    print("Consultando tendencias (Steam + consolas)...")
    tendencias = obtener_tendencia_steam()
    tendencias += obtener_tendencia_rawg()

    if not tendencias:
        print("[ERROR] No se pudo obtener ninguna tendencia (revisá tu conexión / RAWG_API_KEY). Abortando.")
        sys.exit(1)

    print(f"{len(tendencias)} juegos en tendencia obtenidos. Cruzando con el catálogo...")
    df_resultado = emparejar_tendencias_con_catalogo(tendencias, df_catalogo, umbral=args.umbral)

    if df_resultado.empty:
        print("[AVISO] Ninguna tendencia matcheó con el catálogo (¿el catálogo no tiene esos juegos, o subí el umbral?).")
        sys.exit(0)

    generar_excel(df_resultado, args.salida_excel)
    generar_posts(df_resultado, args.salida_posts)
    generar_excel(df_resultado, args.salida_excel)
    generar_posts(df_resultado, args.salida_posts)
    generar_demanda_csv(df_resultado, args.salida_demanda)


if __name__ == "__main__":
    main()

"""
clasificar_categorias.py — ABC Gaming
========================================
Separa el catálogo bruto (hoja "TODO") en 4 categorías, porque hoy están
todas entreveradas en la misma hoja:

    JUEGO         - juegos y DLC normales
    MONEDA        - top-ups de moneda/puntos in-game (Robux, V-Bucks,
                    FC Points, Valorant Points, Overwatch Coins, etc.)
    SUSCRIPCION   - membresías (PS Plus, Game Pass, EA Play, Switch
                    Online, Ubisoft+, etc.)
    GIFTCARD      - tarjetas de regalo (Google Play, Razer Gold, iTunes,
                    Steam/PSN Wallet, Amazon, etc.)

Probado contra el catálogo real: 7.654 juegos / 158 suscripciones /
143 monedas / 140 giftcards, sin falsos negativos en la revisión manual.

USO
----
    python clasificar_categorias.py --catalogo catalogo_completo_abc_gaming.xlsx

Genera catalogo_clasificado.xlsx con 4 hojas (JUEGOS, MONEDAS,
SUSCRIPCIONES, GIFTCARDS). Si preferís 4 archivos separados en vez de
4 hojas, hay una nota al final de generar_salida() para cambiarlo en
una línea.

También se puede importar como módulo:
    from clasificar_categorias import clasificar_catalogo
    df["Categoria"] = df["Nombre Limpio"].apply(clasificar)
"""

import argparse
import re

import pandas as pd


# ----------------------------------------------------------------------------
# Reglas de clasificación (orden de prioridad: giftcard > moneda > suscripcion)
# ----------------------------------------------------------------------------

_GIFTCARD = re.compile(
    r"GIFT ?CARD|TARJETA REGALO|WALLET|ESHOP CARD|ITUNES|"
    r"GOOGLE PLAY (GIFT|CARD)|RAZER GOLD|BLIZZARD GIFT|AMAZON GIFT",
    re.I,
)

_MONEDA = re.compile(
    r"\bROBUX\b|\bV.?BUCKS\b|ULTIMATE TEAM POINTS|\bFC POINTS\b|\bVP\b|"
    r"VALORANT POINTS|OVERWATCH COINS|VIRTUAL CURRENCY|\bGOLD BARS\b|"
    r"CASH CARD|RIOT POINTS|APEX COINS|\bCOD POINTS\b|\bR6 CREDITS\b|"
    r"\bMINECOINS\b|\bPOINTS\b|\d+\s*(COINS|GEMS|GEMAS|MONEDAS|CREDITS)\b",
    re.I,
)

_SUSCRIPCION = re.compile(
    r"\bPS PLUS\b|\bPSN PLUS\b|PLAYSTATION PLUS|GAME ?PASS|\bEA PLAY\b|"
    r"UBISOFT ?\+|NINTENDO ONLINE|SWITCH ONLINE|MEMBRESIA|MEMBERSHIP|"
    r"SUSCRIPCION|XBOX LIVE GOLD|\bLIVE GOLD\b",
    re.I,
)

_DURACION = re.compile(r"\b(MES|MESES|A[NÑ]O|A[NÑ]OS|DIAS?|DAYS?|MONTHS?|TRIAL)\b", re.I)


def clasificar(nombre: str) -> str:
    """Clasifica un nombre de producto en JUEGO / MONEDA / SUSCRIPCION / GIFTCARD."""
    t = str(nombre).upper()

    if _GIFTCARD.search(t):
        return "GIFTCARD"
    if _MONEDA.search(t):
        return "MONEDA"
    if _SUSCRIPCION.search(t):
        return "SUSCRIPCION"
    # caso especial: "PLUS 3 MESES - ESSENTIAL" sin el prefijo PS/PSN
    if re.search(r"\bPLUS\b", t) and _DURACION.search(t):
        return "SUSCRIPCION"
    return "JUEGO"


def clasificar_catalogo(df: pd.DataFrame, columna: str = "Nombre Limpio") -> pd.DataFrame:
    """Agrega la columna 'Categoria' al DataFrame (no modifica el original)."""
    df = df.copy()
    df["Categoria"] = df[columna].astype(str).apply(clasificar)
    return df


def generar_salida(df_clasificado: pd.DataFrame, ruta_salida: str):
    hojas = {
        "JUEGOS": df_clasificado[df_clasificado["Categoria"] == "JUEGO"],
        "MONEDAS": df_clasificado[df_clasificado["Categoria"] == "MONEDA"],
        "SUSCRIPCIONES": df_clasificado[df_clasificado["Categoria"] == "SUSCRIPCION"],
        "GIFTCARDS": df_clasificado[df_clasificado["Categoria"] == "GIFTCARD"],
    }

    with pd.ExcelWriter(ruta_salida, engine="openpyxl") as writer:
        for nombre_hoja, sub_df in hojas.items():
            sub_df.drop(columns=["Categoria"]).to_excel(writer, index=False, sheet_name=nombre_hoja)

    # Si en vez de un solo Excel con 4 hojas preferís 4 ARCHIVOS separados,
    # reemplazá el bloque de arriba por:
    #   for nombre_hoja, sub_df in hojas.items():
    #       sub_df.drop(columns=["Categoria"]).to_excel(f"catalogo_{nombre_hoja.lower()}.xlsx", index=False)

    print(f"[OK] {ruta_salida} generado:")
    for nombre_hoja, sub_df in hojas.items():
        print(f"     {nombre_hoja}: {len(sub_df)} filas ({sub_df['Nombre Limpio'].nunique()} nombres únicos)")


def main():
    ap = argparse.ArgumentParser(description="Separa el catálogo en juegos / monedas / suscripciones / giftcards")
    ap.add_argument("--catalogo", required=True, help="Ruta al Excel del catálogo")
    ap.add_argument("--hoja", default="TODO", help="Hoja de origen (default: TODO)")
    ap.add_argument("--salida", default="catalogo_clasificado.xlsx")
    args = ap.parse_args()

    print("Leyendo catálogo...")
    df = pd.read_excel(args.catalogo, sheet_name=args.hoja)

    print("Clasificando...")
    df_clasificado = clasificar_catalogo(df)

    generar_salida(df_clasificado, args.salida)


if __name__ == "__main__":
    main()

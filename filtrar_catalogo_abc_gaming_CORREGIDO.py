# ABC Gaming - filtro comercial automático (CORREGIDO)
#
# Cambios respecto al original:
#   1. Ahora SÍ guarda los archivos (antes solo imprimía conteos).
#   2. Separa monedas/suscripciones/giftcards ANTES de calcular demanda y
#      ScoreVenta, así ese cálculo comercial solo corre sobre juegos reales
#      (antes les calculaba "Demanda de franquicia" a cosas como
#      "PS PLUS 12 MESES", lo cual no tenía sentido).
#   3. Saca la línea muerta MARGEN = MARGEN.
#
# Colocá junto al script:
#   catalogo_completo_abc_gaming.xlsx
#   demanda_abc_gaming.csv
#   clasificar_categorias.py   <-- nuevo, va en la misma carpeta
# y ejecutalo con: python filtrar_catalogo_abc_gaming_CORREGIDO.py

import os
import pandas as pd

from clasificar_categorias import clasificar_catalogo
MARGEN = 0.25
INPUT_FILE = "catalogo_completo_abc_gaming.xlsx"
DEMANDA_FILE = "demanda_abc_gaming.csv"
OUTPUT_DIR = "ABC_Gaming_filtrado"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- demanda por franquicia ---
import os

if os.path.exists(DEMANDA_FILE):
    dem = pd.read_csv(DEMANDA_FILE)
    dem["Franquicia"] = dem["Franquicia"].astype(str).str.upper()
    dd = dict(zip(dem["Franquicia"], dem["Demanda_0_100"]))
else:
    print(f"[AVISO] No se encontró {DEMANDA_FILE}; se sigue sin datos de demanda (score de demanda = 0 para todo).")
    dd = {}
    
# --- cargar catálogo y separar categorías ---
df_completo = pd.read_excel(INPUT_FILE, sheet_name="TODO")
for c in ["Nombre", "Nombre Limpio", "Plataforma", "Tienda", "Link"]:
    df_completo[c] = df_completo[c].fillna("").astype(str)
df_completo["Precio UYU"] = pd.to_numeric(df_completo["Precio UYU"], errors="coerce")
df_completo = df_completo[df_completo["Precio UYU"].notna() & (df_completo["Precio UYU"] > 0)].copy()

df_clasificado = clasificar_catalogo(df_completo)

# monedas / suscripciones / giftcards: se guardan aparte, sin scoring de demanda
# (ese cálculo es para decidir qué JUEGO promocionar, no aplica a un top-up)
for categoria, nombre_archivo in [
    ("MONEDA", "monedas.xlsx"),
    ("SUSCRIPCION", "suscripciones.xlsx"),
    ("GIFTCARD", "giftcards.xlsx"),
]:
    sub = df_clasificado[df_clasificado["Categoria"] == categoria].drop(columns=["Categoria"])
    sub.to_excel(os.path.join(OUTPUT_DIR, nombre_archivo), index=False)

# a partir de aquí, df es SOLO juegos (lo que antes se llamaba simplemente "df")
df = df_clasificado[df_clasificado["Categoria"] == "JUEGO"].drop(columns=["Categoria"]).copy()
df["NombreKey"] = df["Nombre Limpio"].str.upper().str.replace(r"\s+", " ", regex=True).str.strip()


def demanda(t):
    t = t.upper()
    vals = [v for k, v in dd.items() if k in t]
    return min(vals) if vals else 30


df["Demanda"] = df["NombreKey"].apply(demanda)
minp = df.groupby(["Plataforma", "NombreKey"])["Precio UYU"].transform("min")
df["Competitividad"] = (minp / df["Precio UYU"]).clip(upper=1)
df["ScoreVenta"] = (df["Demanda"] * 0.60 + df["Competitividad"] * 25 + 15).clip(0, 100).round(1)


def nivel(s):
    if s >= 85:
        return "TOP"
    if s >= 70:
        return "MUY ALTO"
    if s >= 55:
        return "ALTO"
    if s >= 40:
        return "MEDIO"
    return "BAJO"


df["Nivel"] = df["ScoreVenta"].apply(nivel)

best = (
    df.sort_values(
        ["Plataforma", "NombreKey", "ScoreVenta", "Precio UYU"],
        ascending=[True, True, False, True],
    )
    .drop_duplicates(["Plataforma", "NombreKey"])
    .copy()
)

best["Costo UYU"] = best["Precio UYU"].round(0)
best["Precio Venta UYU"] = (best["Costo UYU"] * (1 + MARGEN)).round(0)
best["Ganancia UYU"] = (best["Precio Venta UYU"] - best["Costo UYU"]).round(0)
best["Margen sobre venta %"] = (best["Ganancia UYU"] / best["Precio Venta UYU"] * 100).round(1)

redes = best[best["Nivel"].isin(["TOP", "MUY ALTO"])]
web = best[best["Nivel"].isin(["TOP", "MUY ALTO", "ALTO"])]

# --- ESTO ES LO QUE FALTABA: guardar todo ---
best.to_excel(os.path.join(OUTPUT_DIR, "catalogo_juegos_completo.xlsx"), index=False)
redes.to_excel(os.path.join(OUTPUT_DIR, "juegos_para_redes.xlsx"), index=False)
web.to_excel(os.path.join(OUTPUT_DIR, "juegos_para_web.xlsx"), index=False)

print("Catálogo actualizado. Archivos en:", OUTPUT_DIR)
print("Margen aplicado sobre costo:", MARGEN * 100, "%")
print("Juegos para redes:", len(redes))
print("Juegos recomendados para web:", len(web))
print("Juegos completos:", len(best))
print("Monedas separadas:", (df_clasificado["Categoria"] == "MONEDA").sum())
print("Suscripciones separadas:", (df_clasificado["Categoria"] == "SUSCRIPCION").sum())
print("Giftcards separadas:", (df_clasificado["Categoria"] == "GIFTCARD").sum())

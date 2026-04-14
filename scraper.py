!pip install requests beautifulsoup4 pandas openpyxl

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

headers = {
    "User-Agent": "Mozilla/5.0"
}

# 🔥 TUS CATEGORÍAS (exactas)
categorias = {
    "PS3": "https://juegosdigitalesuruguay.com/categorias/juegos-digitales-ps3",
    "PS4": "https://juegosdigitalesuruguay.com/categorias/juegos-digitales-ps4",
    "PS4 VR": "https://juegosdigitalesuruguay.com/categorias/juegos-digitales-ps4/vr",
    "PS5": "https://juegosdigitalesuruguay.com/categorias/juegos-digitales-ps5",
    "Nintendo Switch": "https://juegosdigitalesuruguay.com/categorias/nintendo-switch/juegos-nintendo-switch",
    "Nintendo Switch 2": "https://juegosdigitalesuruguay.com/categorias/nintendo-switch-2",
    "Xbox One": "https://juegosdigitalesuruguay.com/categorias/xbox/juegos-xbox-one",
    "Xbox Series X/S": "https://juegosdigitalesuruguay.com/categorias/xbox/juegos-xbox-series-xs",
    "PSN Plus": "https://juegosdigitalesuruguay.com/categorias/cuenta-psn-plus-global",
    "Nintendo Membresía": "https://juegosdigitalesuruguay.com/categorias/nintendo-membresia",
    "Xbox Membresía": "https://juegosdigitalesuruguay.com/categorias/membresias-xbox"
}

todos = []

# 🔁 recorrer cada categoría
for plataforma, base in categorias.items():
    print(f"\n🔥 SCRAPEANDO {plataforma}\n")

    for offset in range(0, 1500, 24):
        if offset == 0:
            url = base
        else:
            url = f"{base}/{offset}"

        print(f"Entrando a: {url}")

        try:
            res = requests.get(url, headers=headers)
            soup = BeautifulSoup(res.text, "html.parser")

            productos = soup.find_all("div")

            if not productos:
                break

            for prod in productos:
                texto = prod.text.strip()

                if "$" in texto and len(texto) > 20:

                    lineas = texto.split("\n")

                    nombre = None
                    precio = None

                    for l in lineas:
                        l = l.strip()

                        if not nombre and len(l) > 8 and "$" not in l:
                            nombre = l

                        if "$" in l and any(c.isdigit() for c in l):
                            precio = l

                    if nombre and precio:
                        todos.append({
                            "Plataforma": plataforma,
                            "Nombre": nombre,
                            "Precio": precio,
                            "URL": url
                        })

        except:
            print(f"Error en {url}")


# 📊 DataFrame
df = pd.DataFrame(todos)


# 🔧 LIMPIAR NOMBRES
def limpiar_nombre(nombre):
    nombre = nombre.upper().strip()

    basura = [
        "COMPRAR", "OFERTA", "NUEVO",
        "CUENTA PRIMARIA", "CUENTA SECUNDARIA",
        "DIGITAL", "EDICION", "EDITION"
    ]

    for b in basura:
        nombre = nombre.replace(b, "")

    nombre = re.sub(r"\s+", " ", nombre)

    return nombre.strip()

df["Nombre"] = df["Nombre"].apply(limpiar_nombre)


# 🔧 LIMPIAR PRECIOS
def limpiar_precio(precio):
    numeros = "".join(c for c in precio if c.isdigit())
    return int(numeros) if numeros else None

df["Precio_num"] = df["Precio"].apply(limpiar_precio)


# ❌ eliminar basura
df = df.dropna(subset=["Precio_num"])
df = df[df["Nombre"].str.len() > 10]


# 📉 ordenar
df = df.sort_values("Precio_num")


# 🔁 eliminar duplicados (por plataforma)
df = df.drop_duplicates(subset=["Plataforma", "Nombre"], keep="first")


# 🔄 reset índice
df = df.reset_index(drop=True)


# 💾 guardar Excel con múltiples hojas
with pd.ExcelWriter("catalogo_organizado.xlsx", engine="openpyxl") as writer:
    
    # 🔁 crear una hoja por cada plataforma
    for plataforma in df["Plataforma"].unique():
        df_filtrado = df[df["Plataforma"] == plataforma]
        
        # limitar nombre de hoja (Excel max 31 caracteres)
        nombre_hoja = plataforma[:31]
        
        df_filtrado.to_excel(writer, sheet_name=nombre_hoja, index=False)

print("✅ Excel organizado por hojas listo 🔥")



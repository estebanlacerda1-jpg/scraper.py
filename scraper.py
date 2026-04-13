import requests
from bs4 import BeautifulSoup
import pandas as pd

base_url = "https://juegosdigitalesuruguay.com/categorias/juegos-digitales-ps4"

juegos = []
page = 1
max_paginas = 20  # 🔥 bajamos para evitar exceso

while page <= max_paginas:
    print(f"Página {page}")
    
    url = f"{base_url}?page={page}"
    
    try:
        response = requests.get(url, timeout=10)
    except:
        break

    soup = BeautifulSoup(response.text, "html.parser")

    nombres = soup.find_all("h4")
    precios = soup.find_all("span", class_="price")

    if not nombres:
        break

    for nombre, precio in zip(nombres, precios):
        juegos.append({
            "Nombre": nombre.text.strip(),
            "Precio": precio.text.strip()
        })

    page += 1

# eliminar duplicados (CLAVE)
df = pd.DataFrame(juegos).drop_duplicates()

df.to_excel("juegos_ps4.xlsx", index=False)

print("✅ Excel creado")
